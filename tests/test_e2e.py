"""End-to-end integration tests for the Lakehouse Flight SQL server.

These tests start a **real** :class:`DuckDBFlightSqlServer` on a random free
port (no mocking) and connect with ``adbc-driver-flightsql`` over gRPC.
Each test fixture spins up a fresh server/client pair — cleanup shuts
everything down so no leaked threads or ports.

Protocol notes
--------------
* ADBC **always** calls ``CreatePreparedStatement`` before executing any
  query.  Our schema-inference (``LIMIT 0`` wrapper) cannot determine the
  result schema for DDL, DML, or parameterised queries with unbound ``?``
  placeholders, so an empty schema is returned for those.
* DDL statements (``CREATE TABLE``, ``DROP``, …) cannot be wrapped in
  ``SELECT * FROM (…) LIMIT 0`` — they fail at prepare time.  Tables that
  need to exist before querying are **pre-populated via the server's
  internal DuckDB handle** instead.
* Our auth middleware is header-based (``start_call``), not gRPC Handshake-
  based (``ServerAuthHandler``).  ADBC's ``username``/``password`` triggers
  a Handshake RPC, so we set the ``AUTHORIZATION_HEADER`` database option
  to pass Basic auth headers directly.

Test matrix
-----------
7.1  Simple query  — ``SELECT 1 AS value``, aggregation, DuckDB functions
7.2  Pre-seeded queries — filter, aggregate, multi-column on pre-populated table
7.3  Metadata      — GetCatalogs, GetTableTypes, GetInfo, GetTableSchema
7.4  Auth flow     — header-based Basic auth + wrong-password rejection
7.5  DDL/DML       — CREATE, INSERT, UPDATE, DELETE, CTAS, ALTER, DROP, views,
                      prepared inserts, multi-step lifecycle, transactions
7.6  Health probe  — gRPC health check over a real channel
"""

from __future__ import annotations

import base64
import socket
import threading
import time

import adbc_driver_flightsql
import adbc_driver_flightsql.dbapi as flightsql
import grpc
import pyarrow as pa
import pytest
from grpc_health.v1 import health_pb2, health_pb2_grpc

from lakehouse.auth import (
    AccessLogMiddlewareFactory,
    BasicAuthServerMiddlewareFactory,
    BearerAuthServerMiddlewareFactory,
    RequiredAuthServerMiddlewareFactory,
)
from lakehouse.health import BackgroundHealthPoller, HealthServer
from lakehouse.security import hash_password
from lakehouse.server import DuckDBFlightSqlServer

# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────


def _free_port() -> int:
    """Return a random unused TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(server: DuckDBFlightSqlServer) -> threading.Thread:
    """Start *server*.serve() in a daemon thread."""
    t = threading.Thread(target=server.serve, daemon=True)
    t.start()
    # Give the server a moment to bind
    time.sleep(0.3)
    return t


# ───────────────────────────────────────────────────────────────────────────
# Fixtures — plain server (no auth)
# ───────────────────────────────────────────────────────────────────────────


@pytest.fixture
def plain_server():
    """Start a plain (no-auth) Flight SQL server on a random port."""
    port = _free_port()
    location = f"grpc://127.0.0.1:{port}"
    srv = DuckDBFlightSqlServer(location=location, db_path=":memory:")
    _start_server(srv)
    yield srv, port
    srv.shutdown()


@pytest.fixture
def plain_conn(plain_server):
    """ADBC connection to the plain server."""
    _srv, port = plain_server
    conn = flightsql.connect(f"grpc://127.0.0.1:{port}")
    yield conn
    conn.close()


@pytest.fixture
def seeded_server():
    """Plain server pre-populated with ``test_data`` table via internal DuckDB."""
    port = _free_port()
    location = f"grpc://127.0.0.1:{port}"
    srv = DuckDBFlightSqlServer(location=location, db_path=":memory:")

    # Pre-populate data directly (bypasses ADBC prepare-path limitations)
    srv._db.execute("CREATE TABLE test_data (id INT, name TEXT, value DOUBLE)")
    srv._db.execute(
        "INSERT INTO test_data VALUES (1, 'alice', 10.5), (2, 'bob', 20.0), (3, 'carol', 30.5)"
    )

    _start_server(srv)
    yield srv, port
    srv.shutdown()


@pytest.fixture
def seeded_conn(seeded_server):
    """ADBC connection to the seeded server."""
    _srv, port = seeded_server
    conn = flightsql.connect(f"grpc://127.0.0.1:{port}")
    yield conn
    conn.close()


# ───────────────────────────────────────────────────────────────────────────
# Fixtures — auth server
# ───────────────────────────────────────────────────────────────────────────

_TEST_USERNAME = "lakehouse"
_TEST_PASSWORD = "s3cret!"
_TEST_SECRET = "integration-test-secret-key-0123456789ab"


@pytest.fixture
def auth_server():
    """Start a Flight SQL server with Basic + Bearer auth enabled."""
    port = _free_port()
    location = f"grpc://127.0.0.1:{port}"

    pw_hash = hash_password(_TEST_PASSWORD, _TEST_SECRET)
    middleware: dict[str, object] = {
        "access-log": AccessLogMiddlewareFactory(),
        "basic-auth": BasicAuthServerMiddlewareFactory(
            secret_key=_TEST_SECRET,
            password_hash=pw_hash,
            instance_id="",
        ),
        "bearer-auth": BearerAuthServerMiddlewareFactory(
            secret_key=_TEST_SECRET,
        ),
        "required-auth": RequiredAuthServerMiddlewareFactory(),
    }

    srv = DuckDBFlightSqlServer(
        location=location,
        db_path=":memory:",
        middleware=middleware,
    )
    _start_server(srv)
    yield srv, port
    srv.shutdown()


@pytest.fixture
def auth_conn(auth_server):
    """ADBC connection to the auth server with valid credentials.

    Uses header-based Basic auth (``authorization`` header) rather than
    the Flight Handshake RPC, because our server uses middleware-based auth.
    """
    _srv, port = auth_server
    basic_token = base64.b64encode(f"{_TEST_USERNAME}:{_TEST_PASSWORD}".encode()).decode()
    conn = flightsql.connect(
        f"grpc://127.0.0.1:{port}",
        db_kwargs={
            adbc_driver_flightsql.DatabaseOptions.AUTHORIZATION_HEADER.value: (
                f"Basic {basic_token}"
            ),
        },
    )
    yield conn
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# 7.1 — Simple query
# ═══════════════════════════════════════════════════════════════════════════


class TestE2EQuery:
    """End-to-end query execution over Flight SQL + ADBC."""

    def test_select_literal(self, plain_conn):
        cursor = plain_conn.execute("SELECT 1 AS value")
        rows = cursor.fetchall()
        assert rows == [(1,)]
        cursor.close()

    def test_select_multiple_rows(self, plain_conn):
        cursor = plain_conn.execute(
            "SELECT * FROM (VALUES (1, 'a'), (2, 'b'), (3, 'c')) AS t(id, letter)"
        )
        rows = cursor.fetchall()
        assert len(rows) == 3
        assert rows[0] == (1, "a")
        assert rows[2] == (3, "c")
        cursor.close()

    def test_cursor_description(self, plain_conn):
        cursor = plain_conn.execute("SELECT 42 AS answer, 'hello' AS greeting")
        assert cursor.description is not None
        col_names = [col[0] for col in cursor.description]
        assert col_names == ["answer", "greeting"]
        cursor.close()

    def test_fetch_arrow_table(self, plain_conn):
        cursor = plain_conn.execute("SELECT 1 AS a, 2 AS b")
        table = cursor.fetch_arrow_table()
        assert isinstance(table, pa.Table)
        assert table.num_rows == 1
        assert table.column_names == ["a", "b"]
        cursor.close()

    def test_aggregation_query(self, plain_conn):
        cursor = plain_conn.execute(
            "SELECT COUNT(*) AS cnt, SUM(v) AS total FROM (VALUES (10), (20), (30)) AS t(v)"
        )
        rows = cursor.fetchall()
        assert rows[0][0] == 3
        assert rows[0][1] == 60
        cursor.close()

    def test_duckdb_functions(self, plain_conn):
        """DuckDB-specific functions work end-to-end."""
        cursor = plain_conn.execute("SELECT list_value(1, 2, 3) AS arr")
        rows = cursor.fetchall()
        assert rows[0][0] == [1, 2, 3]
        cursor.close()


# ═══════════════════════════════════════════════════════════════════════════
# 7.2 — Pre-seeded query tests
# ═══════════════════════════════════════════════════════════════════════════


class TestE2ESeeded:
    """Queries against a pre-populated ``test_data`` table."""

    def test_select_all(self, seeded_conn):
        cursor = seeded_conn.execute("SELECT * FROM test_data ORDER BY id")
        rows = cursor.fetchall()
        assert len(rows) == 3
        assert rows[0][1] == "alice"
        cursor.close()

    def test_filter_by_id(self, seeded_conn):
        cursor = seeded_conn.execute("SELECT name FROM test_data WHERE id = 2")
        rows = cursor.fetchall()
        assert rows == [("bob",)]
        cursor.close()

    def test_aggregation(self, seeded_conn):
        cursor = seeded_conn.execute("SELECT COUNT(*) AS cnt, SUM(value) AS total FROM test_data")
        rows = cursor.fetchall()
        assert rows[0][0] == 3
        assert abs(rows[0][1] - 61.0) < 0.01
        cursor.close()

    def test_order_by(self, seeded_conn):
        cursor = seeded_conn.execute("SELECT name FROM test_data ORDER BY value DESC")
        rows = cursor.fetchall()
        assert rows[0] == ("carol",)
        assert rows[2] == ("alice",)
        cursor.close()

    def test_fetch_arrow_table(self, seeded_conn):
        cursor = seeded_conn.execute("SELECT id, name, value FROM test_data ORDER BY id")
        table = cursor.fetch_arrow_table()
        assert table.num_rows == 3
        assert table.column_names == ["id", "name", "value"]
        cursor.close()


# ═══════════════════════════════════════════════════════════════════════════
# 7.3 — Metadata
# ═══════════════════════════════════════════════════════════════════════════


class TestE2EMetadata:
    """End-to-end metadata queries via ADBC extensions."""

    def test_get_objects_catalogs(self, plain_conn):
        reader = plain_conn.adbc_get_objects(depth="catalogs")
        table = reader.read_all()
        assert table.num_rows >= 0
        assert "catalog_name" in table.column_names

    def test_get_table_types(self, plain_conn):
        table_types = plain_conn.adbc_get_table_types()
        assert isinstance(table_types, list)

    def test_get_info(self, plain_conn):
        info = plain_conn.adbc_get_info()
        assert isinstance(info, dict)
        assert len(info) > 0

    def test_get_table_schema_preseeded(self, seeded_conn):
        """Get schema for a pre-created table."""
        schema = seeded_conn.adbc_get_table_schema("test_data")
        assert isinstance(schema, pa.Schema)
        field_names = [f.name for f in schema]
        assert "id" in field_names
        assert "name" in field_names
        assert "value" in field_names


# ═══════════════════════════════════════════════════════════════════════════
# 7.4 — Auth flow (header-based Basic auth)
# ═══════════════════════════════════════════════════════════════════════════


class TestE2EAuth:
    """End-to-end authentication flow via header-based Basic auth."""

    def test_auth_query_works(self, auth_conn):
        """Authenticated client can execute a query."""
        cursor = auth_conn.execute("SELECT 1 AS value")
        rows = cursor.fetchall()
        assert rows == [(1,)]
        cursor.close()

    def test_auth_metadata(self, auth_conn):
        """Authenticated client can retrieve metadata."""
        info = auth_conn.adbc_get_info()
        assert isinstance(info, dict)

    def test_auth_select_preseeded(self, auth_server):
        """Authenticated client can query pre-seeded data."""
        srv, port = auth_server
        srv._db.execute("CREATE TABLE auth_data (id INT, val TEXT)")
        srv._db.execute("INSERT INTO auth_data VALUES (1, 'secret')")

        basic_token = base64.b64encode(f"{_TEST_USERNAME}:{_TEST_PASSWORD}".encode()).decode()
        conn = flightsql.connect(
            f"grpc://127.0.0.1:{port}",
            db_kwargs={
                adbc_driver_flightsql.DatabaseOptions.AUTHORIZATION_HEADER.value: (
                    f"Basic {basic_token}"
                ),
            },
        )
        cursor = conn.execute("SELECT val FROM auth_data")
        rows = cursor.fetchall()
        assert rows == [("secret",)]
        cursor.close()
        conn.close()

    def test_wrong_password_rejected(self, auth_server):
        """Connection with wrong password is rejected."""
        _srv, port = auth_server
        bad_token = base64.b64encode(f"{_TEST_USERNAME}:wrong-password".encode()).decode()
        with pytest.raises(Exception, match=r"UNAUTHENTICATED|Invalid credentials"):
            conn = flightsql.connect(
                f"grpc://127.0.0.1:{port}",
                db_kwargs={
                    adbc_driver_flightsql.DatabaseOptions.AUTHORIZATION_HEADER.value: (
                        f"Basic {bad_token}"
                    ),
                },
            )
            cursor = conn.execute("SELECT 1")
            cursor.fetchall()
            cursor.close()
            conn.close()

    def test_missing_auth_rejected(self, auth_server):
        """Connection without an auth header is rejected."""
        _srv, port = auth_server
        with pytest.raises(
            Exception,
            match=r"UNAUTHENTICATED|Authorization header is required",
        ):
            conn = flightsql.connect(f"grpc://127.0.0.1:{port}")
            cursor = conn.execute("SELECT 1")
            cursor.fetchall()
            cursor.close()
            conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# 7.5 — DDL / DML via Flight SQL
# ═══════════════════════════════════════════════════════════════════════════


class TestE2EDDL:
    """End-to-end DDL/DML tests executed THROUGH the Flight SQL protocol.

    Every table is created and mutated via ADBC ``cursor.execute()``
    (→ ``DoPutCommandStatementUpdate`` on the server), **not** via the
    internal ``server._db`` handle.  This is the layer that caught the
    ``write_metadata`` → ``write`` rename bug.
    """

    # ── CREATE TABLE ──────────────────────────────────────────────────

    def test_create_table(self, plain_conn):
        """CREATE TABLE via Flight SQL succeeds and table is queryable."""
        cur = plain_conn.execute("CREATE TABLE t_create (id INT, name TEXT)")
        cur.close()

        cur = plain_conn.execute("SELECT * FROM t_create")
        rows = cur.fetchall()
        assert rows == []
        cur.close()

    # ── INSERT ────────────────────────────────────────────────────────

    def test_insert(self, plain_conn):
        """INSERT rows via Flight SQL — data is queryable afterward."""
        plain_conn.execute("CREATE TABLE t_ins (id INT, val TEXT)").close()

        plain_conn.execute("INSERT INTO t_ins VALUES (1, 'alpha'), (2, 'beta')").close()

        cur = plain_conn.execute("SELECT id, val FROM t_ins ORDER BY id")
        rows = cur.fetchall()
        assert rows == [(1, "alpha"), (2, "beta")]
        cur.close()

    # ── UPDATE ────────────────────────────────────────────────────────

    def test_update(self, plain_conn):
        """UPDATE mutates rows visible through a subsequent query."""
        plain_conn.execute("CREATE TABLE t_upd (id INT, val TEXT)").close()
        plain_conn.execute("INSERT INTO t_upd VALUES (1, 'old'), (2, 'keep')").close()

        plain_conn.execute("UPDATE t_upd SET val = 'new' WHERE id = 1").close()

        cur = plain_conn.execute("SELECT val FROM t_upd WHERE id = 1")
        assert cur.fetchall() == [("new",)]
        cur.close()

    # ── DELETE ────────────────────────────────────────────────────────

    def test_delete(self, plain_conn):
        """DELETE removes rows visible through a subsequent query."""
        plain_conn.execute("CREATE TABLE t_del (id INT)").close()
        plain_conn.execute("INSERT INTO t_del VALUES (1), (2), (3)").close()

        plain_conn.execute("DELETE FROM t_del WHERE id = 2").close()

        cur = plain_conn.execute("SELECT id FROM t_del ORDER BY id")
        assert cur.fetchall() == [(1,), (3,)]
        cur.close()

    # ── CREATE TABLE AS SELECT ────────────────────────────────────────

    def test_create_table_as_select(self, plain_conn):
        """CTAS creates a table with pre-populated data."""
        plain_conn.execute("CREATE TABLE t_src (x INT)").close()
        plain_conn.execute("INSERT INTO t_src VALUES (10), (20)").close()

        plain_conn.execute("CREATE TABLE t_ctas AS SELECT x * 2 AS doubled FROM t_src").close()

        cur = plain_conn.execute("SELECT doubled FROM t_ctas ORDER BY doubled")
        assert cur.fetchall() == [(20,), (40,)]
        cur.close()

    # ── ALTER TABLE ───────────────────────────────────────────────────

    def test_alter_table_add_column(self, plain_conn):
        """ALTER TABLE ADD COLUMN — new column visible in schema."""
        plain_conn.execute("CREATE TABLE t_alt (id INT)").close()
        plain_conn.execute("INSERT INTO t_alt VALUES (1)").close()

        plain_conn.execute("ALTER TABLE t_alt ADD COLUMN label TEXT").close()

        cur = plain_conn.execute("SELECT id, label FROM t_alt")
        rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0][0] == 1
        assert rows[0][1] is None  # new column is NULL
        cur.close()

    # ── DROP TABLE ────────────────────────────────────────────────────

    def test_drop_table(self, plain_conn):
        """DROP TABLE removes the table — subsequent SELECT fails."""
        plain_conn.execute("CREATE TABLE t_drop (id INT)").close()
        plain_conn.execute("DROP TABLE t_drop").close()

        with pytest.raises(Exception):  # noqa: B017
            plain_conn.execute("SELECT * FROM t_drop")

    # ── Full write → read round-trip ─────────────────────────────────

    def test_insert_select_roundtrip(self, plain_conn):
        """Full INSERT → SELECT roundtrip with multiple types."""
        plain_conn.execute(
            "CREATE TABLE t_rt (id INT, name TEXT, amount DOUBLE, active BOOLEAN)"
        ).close()
        plain_conn.execute(
            "INSERT INTO t_rt VALUES (1, 'alice', 99.5, true), (2, 'bob', 0.0, false)"
        ).close()

        cur = plain_conn.execute("SELECT * FROM t_rt ORDER BY id")
        table = cur.fetch_arrow_table()
        assert table.num_rows == 2
        assert set(table.column_names) == {"id", "name", "amount", "active"}
        # Verify actual values
        assert table.column("name").to_pylist() == ["alice", "bob"]
        assert table.column("active").to_pylist() == [True, False]
        cur.close()

    # ── Prepared INSERT ───────────────────────────────────────────────

    def test_prepared_insert(self, plain_conn):
        """Prepared INSERT with bound parameters works end-to-end."""
        plain_conn.execute("CREATE TABLE t_prep (id INT, val TEXT)").close()

        stmt = plain_conn.execute("INSERT INTO t_prep VALUES (?, ?)", [1, "one"])
        stmt.close()
        stmt = plain_conn.execute("INSERT INTO t_prep VALUES (?, ?)", [2, "two"])
        stmt.close()

        cur = plain_conn.execute("SELECT id, val FROM t_prep ORDER BY id")
        assert cur.fetchall() == [(1, "one"), (2, "two")]
        cur.close()

    # ── CREATE VIEW ───────────────────────────────────────────────────

    def test_create_view(self, plain_conn):
        """CREATE VIEW and query through it."""
        plain_conn.execute("CREATE TABLE t_vbase (id INT, score INT)").close()
        plain_conn.execute("INSERT INTO t_vbase VALUES (1, 80), (2, 95), (3, 70)").close()

        plain_conn.execute("CREATE VIEW v_high AS SELECT * FROM t_vbase WHERE score >= 80").close()

        cur = plain_conn.execute("SELECT id FROM v_high ORDER BY id")
        assert cur.fetchall() == [(1,), (2,)]
        cur.close()

    # ── Multi-step DDL/DML lifecycle ─────────────────────────────────

    def test_multiple_ddl_sequence(self, plain_conn):
        """Full lifecycle: CREATE → INSERT → ALTER → UPDATE → DELETE → DROP."""
        # Create
        plain_conn.execute("CREATE TABLE t_life (id INT, val TEXT)").close()

        # Insert
        plain_conn.execute("INSERT INTO t_life VALUES (1, 'a'), (2, 'b'), (3, 'c')").close()
        cur = plain_conn.execute("SELECT COUNT(*) FROM t_life")
        assert cur.fetchall() == [(3,)]
        cur.close()

        # Alter — add column
        plain_conn.execute("ALTER TABLE t_life ADD COLUMN score INT").close()

        # Update — set new column
        plain_conn.execute("UPDATE t_life SET score = id * 10").close()
        cur = plain_conn.execute("SELECT score FROM t_life WHERE id = 2")
        assert cur.fetchall() == [(20,)]
        cur.close()

        # Delete — remove one row
        plain_conn.execute("DELETE FROM t_life WHERE id = 3").close()
        cur = plain_conn.execute("SELECT COUNT(*) FROM t_life")
        assert cur.fetchall() == [(2,)]
        cur.close()

        # Drop
        plain_conn.execute("DROP TABLE t_life").close()
        with pytest.raises(Exception):  # noqa: B017
            plain_conn.execute("SELECT 1 FROM t_life")

    # ── Transaction rollback ─────────────────────────────────────────

    def test_transaction_rollback(self, plain_conn):
        """ROLLBACK undoes changes made in the transaction."""
        plain_conn.execute("CREATE TABLE t_txn (id INT)").close()
        plain_conn.execute("INSERT INTO t_txn VALUES (1)").close()

        # Start explicit transaction, insert, then rollback
        plain_conn.execute("BEGIN TRANSACTION").close()
        plain_conn.execute("INSERT INTO t_txn VALUES (2)").close()
        plain_conn.execute("ROLLBACK").close()

        cur = plain_conn.execute("SELECT id FROM t_txn ORDER BY id")
        rows = cur.fetchall()
        assert rows == [(1,)]
        cur.close()


# ═══════════════════════════════════════════════════════════════════════════
# 7.6 — Health check
# ═══════════════════════════════════════════════════════════════════════════


class TestE2EHealth:
    """End-to-end gRPC health check probe."""

    def test_health_check_serving(self, plain_server):
        """Health server reports SERVING when started."""
        _srv, _flight_port = plain_server
        health_port = _free_port()
        health_srv = HealthServer(port=health_port)
        health_srv.start()
        try:
            time.sleep(0.2)

            channel = grpc.insecure_channel(f"127.0.0.1:{health_port}")
            stub = health_pb2_grpc.HealthStub(channel)
            response = stub.Check(
                health_pb2.HealthCheckRequest(service=""),
            )
            assert response.status == health_pb2.HealthCheckResponse.SERVING

            response = stub.Check(
                health_pb2.HealthCheckRequest(service="lakehouse.FlightSql"),
            )
            assert response.status == health_pb2.HealthCheckResponse.SERVING
            channel.close()
        finally:
            health_srv.stop()

    def test_health_check_not_serving(self):
        """Health server reports NOT_SERVING after explicit mark."""
        health_port = _free_port()
        health_srv = HealthServer(port=health_port)
        health_srv.start()
        try:
            time.sleep(0.2)
            health_srv.set_not_serving()

            channel = grpc.insecure_channel(f"127.0.0.1:{health_port}")
            stub = health_pb2_grpc.HealthStub(channel)
            response = stub.Check(
                health_pb2.HealthCheckRequest(service=""),
            )
            assert response.status == health_pb2.HealthCheckResponse.NOT_SERVING
            channel.close()
        finally:
            health_srv.stop()

    def test_health_poller_marks_serving(self, plain_server):
        """BackgroundHealthPoller marks SERVING when DuckDB is healthy."""
        srv, _port = plain_server
        health_port = _free_port()
        health_srv = HealthServer(port=health_port)
        health_srv.start()
        try:
            health_srv.set_not_serving()

            poller = BackgroundHealthPoller(health_srv, srv._db, interval=0.2)
            poller.start()
            time.sleep(0.5)

            channel = grpc.insecure_channel(f"127.0.0.1:{health_port}")
            stub = health_pb2_grpc.HealthStub(channel)
            response = stub.Check(
                health_pb2.HealthCheckRequest(service=""),
            )
            assert response.status == health_pb2.HealthCheckResponse.SERVING
            channel.close()
            poller.stop()
        finally:
            health_srv.stop()

    def test_full_stack_health(self, plain_server):
        """Full stack: Flight server + health server + poller, probe from client."""
        srv, flight_port = plain_server
        health_port = _free_port()
        health_srv = HealthServer(port=health_port)
        health_srv.start()
        poller = BackgroundHealthPoller(health_srv, srv._db, interval=0.2)
        poller.start()

        try:
            time.sleep(0.5)

            # Flight SQL still works
            conn = flightsql.connect(f"grpc://127.0.0.1:{flight_port}")
            cursor = conn.execute("SELECT 1")
            assert cursor.fetchall() == [(1,)]
            cursor.close()
            conn.close()

            # Health check works
            channel = grpc.insecure_channel(f"127.0.0.1:{health_port}")
            stub = health_pb2_grpc.HealthStub(channel)
            response = stub.Check(
                health_pb2.HealthCheckRequest(service=""),
            )
            assert response.status == health_pb2.HealthCheckResponse.SERVING
            channel.close()
        finally:
            poller.stop()
            health_srv.stop()

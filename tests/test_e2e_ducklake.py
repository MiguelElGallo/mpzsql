"""End-to-end DuckLake integration tests against real Azure infrastructure.

These tests start a Flight SQL server wired to a real DuckLake catalog
(PostgreSQL on Azure + Parquet on Azure Blob Storage) and exercise
DDL/DML through ADBC.  They are **skipped** unless the required
environment variables are set.

Required environment variables
------------------------------
``DUCKLAKE_PG_HOST``
    PostgreSQL server hostname (e.g. ``pg1-mpz.postgres.database.azure.com``).
``DUCKLAKE_PG_DATABASE``
    PostgreSQL database name (e.g. ``ducklake``).
``DUCKLAKE_PG_USER``
    PostgreSQL user — full Entra ID UPN.
``DUCKLAKE_AZURE_STORAGE_ACCOUNT``
    Azure Storage account name.
``DUCKLAKE_DATA_PATH``
    ``DATA_PATH`` for DuckLake ATTACH (e.g. ``az://lakehouse/data/``).

Optional
~~~~~~~~
``DUCKLAKE_PG_PORT`` (default ``5432``), ``DUCKLAKE_ALIAS`` (default ``lakehouse``).

Run locally
-----------
.. code-block:: bash

    export DUCKLAKE_PG_HOST=pg1-mpz.postgres.database.azure.com
    export DUCKLAKE_PG_DATABASE=ducklake
    export DUCKLAKE_PG_USER='neon_pesto1u_icloud.com#EXT#@neonpesto1uicloud.onmicrosoft.com'
    export DUCKLAKE_AZURE_STORAGE_ACCOUNT=stompz1
    export DUCKLAKE_DATA_PATH='az://lakehouse/data/'
    uv run pytest tests/test_e2e_ducklake.py -v
"""

from __future__ import annotations

import contextlib
import os
import socket
import threading
import time

import adbc_driver_flightsql.dbapi as flightsql
import pyarrow as pa
import pytest

from lakehouse.server import DuckDBFlightSqlServer

# ───────────────────────────────────────────────────────────────────────────
# Environment & skip logic
# ───────────────────────────────────────────────────────────────────────────

_REQUIRED_ENV = (
    "DUCKLAKE_PG_HOST",
    "DUCKLAKE_PG_DATABASE",
    "DUCKLAKE_PG_USER",
    "DUCKLAKE_AZURE_STORAGE_ACCOUNT",
    "DUCKLAKE_DATA_PATH",
)

_missing = [v for v in _REQUIRED_ENV if not os.environ.get(v)]

pytestmark = pytest.mark.skipif(
    bool(_missing),
    reason=f"DuckLake env vars missing: {', '.join(_missing)}",
)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(server: DuckDBFlightSqlServer) -> threading.Thread:
    t = threading.Thread(target=server.serve, daemon=True)
    t.start()
    time.sleep(0.5)  # DuckLake extensions take a moment
    return t


# Table names scoped to main schema inside the DuckLake catalog
_ALIAS = "lakehouse"
_SCHEMA = "main"


def _fq(table: str) -> str:
    """Return fully-qualified ``<alias>.<schema>.<table>``."""
    return f"{_ALIAS}.{_SCHEMA}.{table}"


# ───────────────────────────────────────────────────────────────────────────
# Fixtures
# ───────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def ducklake_server():
    """Start a Flight SQL server with full DuckLake wiring.

    Scope is ``module`` — one server for all tests to amortise extension
    install / ATTACH time (~5 s).  Tests use unique table names to avoid
    interference.
    """
    from lakehouse.azure_token import PostgresTokenManager
    from lakehouse.config import ServerConfig
    from lakehouse.ducklake import initialize_ducklake

    alias = _env("DUCKLAKE_ALIAS", _ALIAS)
    port = _free_port()
    location = f"grpc://127.0.0.1:{port}"

    config = ServerConfig(
        port=port,
        database=":memory:",
        azure_storage_account=_env("DUCKLAKE_AZURE_STORAGE_ACCOUNT"),
        ducklake_data_path=_env("DUCKLAKE_DATA_PATH"),
        pg_host=_env("DUCKLAKE_PG_HOST"),
        pg_port=int(_env("DUCKLAKE_PG_PORT", "5432")),
        pg_database=_env("DUCKLAKE_PG_DATABASE"),
        pg_user=_env("DUCKLAKE_PG_USER"),
        ducklake_alias=alias,
    )

    srv = DuckDBFlightSqlServer(
        location=location,
        db_path=":memory:",
        ducklake_alias=alias,
    )

    # DuckLake init: extensions, secrets, ATTACH, USE
    token_mgr = PostgresTokenManager(srv._db, config)
    token = token_mgr.get_initial_token()
    initialize_ducklake(srv._db, config, token=token)

    _start_server(srv)
    yield srv, port

    # Cleanup: drop all test tables (best-effort)
    _test_tables = [
        "t_dl_create",
        "t_dl_ins",
        "t_dl_upd",
        "t_dl_del",
        "t_dl_src",
        "t_dl_ctas",
        "t_dl_alt",
        "t_dl_drop",
        "t_dl_life",
    ]
    for t in _test_tables:
        with contextlib.suppress(Exception):
            srv._db.execute(f"DROP TABLE IF EXISTS {_fq(t)}")

    token_mgr.stop()
    srv.shutdown()


@pytest.fixture(scope="module")
def ducklake_conn(ducklake_server):
    """ADBC connection to the DuckLake-enabled server."""
    _srv, port = ducklake_server
    conn = flightsql.connect(f"grpc://127.0.0.1:{port}")
    yield conn
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# DuckLake DDL / DML Tests (via ADBC)
# ═══════════════════════════════════════════════════════════════════════════


class TestDuckLakeDDL:
    """DDL/DML against the real DuckLake catalog via Flight SQL (ADBC)."""

    def test_create_table(self, ducklake_conn):
        """CREATE TABLE in the DuckLake catalog."""
        fq = _fq("t_dl_create")
        ducklake_conn.execute(f"DROP TABLE IF EXISTS {fq}").close()
        ducklake_conn.execute(f"CREATE TABLE {fq} (id INT, name TEXT)").close()

        cur = ducklake_conn.execute(f"SELECT * FROM {fq}")
        rows = cur.fetchall()
        assert rows == []
        cur.close()

    def test_insert_select(self, ducklake_conn):
        """INSERT + SELECT roundtrip — data persisted to Parquet on Azure."""
        fq = _fq("t_dl_ins")
        ducklake_conn.execute(f"DROP TABLE IF EXISTS {fq}").close()
        ducklake_conn.execute(f"CREATE TABLE {fq} (id INT, val TEXT)").close()
        ducklake_conn.execute(f"INSERT INTO {fq} VALUES (1, 'alpha'), (2, 'beta')").close()

        cur = ducklake_conn.execute(f"SELECT id, val FROM {fq} ORDER BY id")
        rows = cur.fetchall()
        assert rows == [(1, "alpha"), (2, "beta")]
        cur.close()

    def test_update(self, ducklake_conn):
        """UPDATE mutates rows in the DuckLake catalog."""
        fq = _fq("t_dl_upd")
        ducklake_conn.execute(f"DROP TABLE IF EXISTS {fq}").close()
        ducklake_conn.execute(f"CREATE TABLE {fq} (id INT, val TEXT)").close()
        ducklake_conn.execute(f"INSERT INTO {fq} VALUES (1, 'old'), (2, 'keep')").close()
        ducklake_conn.execute(f"UPDATE {fq} SET val = 'new' WHERE id = 1").close()

        cur = ducklake_conn.execute(f"SELECT val FROM {fq} WHERE id = 1")
        assert cur.fetchall() == [("new",)]
        cur.close()

    def test_delete(self, ducklake_conn):
        """DELETE removes rows from the DuckLake catalog."""
        fq = _fq("t_dl_del")
        ducklake_conn.execute(f"DROP TABLE IF EXISTS {fq}").close()
        ducklake_conn.execute(f"CREATE TABLE {fq} (id INT)").close()
        ducklake_conn.execute(f"INSERT INTO {fq} VALUES (1), (2), (3)").close()
        ducklake_conn.execute(f"DELETE FROM {fq} WHERE id = 2").close()

        cur = ducklake_conn.execute(f"SELECT id FROM {fq} ORDER BY id")
        assert cur.fetchall() == [(1,), (3,)]
        cur.close()

    def test_create_table_as_select(self, ducklake_conn):
        """CTAS — create a table from a query result."""
        fq_src = _fq("t_dl_src")
        fq_ctas = _fq("t_dl_ctas")
        ducklake_conn.execute(f"DROP TABLE IF EXISTS {fq_ctas}").close()
        ducklake_conn.execute(f"DROP TABLE IF EXISTS {fq_src}").close()
        ducklake_conn.execute(f"CREATE TABLE {fq_src} (x INT)").close()
        ducklake_conn.execute(f"INSERT INTO {fq_src} VALUES (10), (20)").close()
        ducklake_conn.execute(
            f"CREATE TABLE {fq_ctas} AS SELECT x * 2 AS doubled FROM {fq_src}"
        ).close()

        cur = ducklake_conn.execute(f"SELECT doubled FROM {fq_ctas} ORDER BY doubled")
        assert cur.fetchall() == [(20,), (40,)]
        cur.close()

    def test_alter_table_add_column(self, ducklake_conn):
        """ALTER TABLE ADD COLUMN in the DuckLake catalog."""
        fq = _fq("t_dl_alt")
        ducklake_conn.execute(f"DROP TABLE IF EXISTS {fq}").close()
        ducklake_conn.execute(f"CREATE TABLE {fq} (id INT)").close()
        ducklake_conn.execute(f"INSERT INTO {fq} VALUES (1)").close()
        ducklake_conn.execute(f"ALTER TABLE {fq} ADD COLUMN label TEXT").close()

        cur = ducklake_conn.execute(f"SELECT id, label FROM {fq}")
        rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0][0] == 1
        assert rows[0][1] is None
        cur.close()

    def test_drop_table(self, ducklake_conn):
        """DROP TABLE removes it from the DuckLake catalog."""
        fq = _fq("t_dl_drop")
        ducklake_conn.execute(f"DROP TABLE IF EXISTS {fq}").close()
        ducklake_conn.execute(f"CREATE TABLE {fq} (id INT)").close()
        ducklake_conn.execute(f"DROP TABLE {fq}").close()

        with pytest.raises(Exception):  # noqa: B017
            ducklake_conn.execute(f"SELECT * FROM {fq}")

    def test_lifecycle(self, ducklake_conn):
        """Full lifecycle: CREATE → INSERT → UPDATE → DELETE → DROP."""
        fq = _fq("t_dl_life")
        ducklake_conn.execute(f"DROP TABLE IF EXISTS {fq}").close()

        # Create + Insert
        ducklake_conn.execute(f"CREATE TABLE {fq} (id INT, val TEXT)").close()
        ducklake_conn.execute(f"INSERT INTO {fq} VALUES (1, 'a'), (2, 'b'), (3, 'c')").close()

        cur = ducklake_conn.execute(f"SELECT COUNT(*) FROM {fq}")
        assert cur.fetchall() == [(3,)]
        cur.close()

        # Update
        ducklake_conn.execute(f"UPDATE {fq} SET val = 'z' WHERE id = 2").close()
        cur = ducklake_conn.execute(f"SELECT val FROM {fq} WHERE id = 2")
        assert cur.fetchall() == [("z",)]
        cur.close()

        # Delete
        ducklake_conn.execute(f"DELETE FROM {fq} WHERE id = 3").close()
        cur = ducklake_conn.execute(f"SELECT COUNT(*) FROM {fq}")
        assert cur.fetchall() == [(2,)]
        cur.close()

        # Fetch as Arrow table
        cur = ducklake_conn.execute(f"SELECT * FROM {fq} ORDER BY id")
        table = cur.fetch_arrow_table()
        assert isinstance(table, pa.Table)
        assert table.num_rows == 2
        cur.close()

        # Drop
        ducklake_conn.execute(f"DROP TABLE {fq}").close()
        with pytest.raises(Exception):  # noqa: B017
            ducklake_conn.execute(f"SELECT 1 FROM {fq}")

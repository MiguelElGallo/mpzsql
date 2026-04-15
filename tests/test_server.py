"""Tests for lakehouse.server — DuckDB Flight SQL server handlers.

Each handler is tested by instantiating a ``DuckDBFlightSqlServer`` with an
in-memory DuckDB and calling the handler methods directly with mock
``ServerCallContext``.  No gRPC transport is involved — these are pure
unit tests against the handler layer.

``RecordBatchStream`` is a C-level Flight streaming wrapper with no
``read_all()`` API.  Tests that verify query results therefore call the
same query via ``_execute_query`` independently, rather than attempting to
read from the stream object.  The handler return type is asserted as
``RecordBatchStream`` for contract verification.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import duckdb
import pyarrow as pa
import pyarrow.flight as flight
import pyarrow.ipc as ipc
import pytest

from lakehouse.proto import fs, pack_any, unpack_any
from lakehouse.server import (
    _SQL_INFO_SCHEMA,
    _XDBC_TYPE_INFO_SCHEMA,
    DuckDBFlightSqlServer,
    _arrow_type_to_sql,
    _build_sql_info_table,
    _build_xdbc_type_info_table,
    _execute_query,
    _get_flight_info_for_command,
    _get_session_id,
    _infer_parameter_schema,
    _prepare_get_tables_query,
    _record_batch_stream,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def server():
    """Create a DuckDBFlightSqlServer with an in-memory DuckDB.

    Bypasses ``FlightServerBase.__init__`` (no gRPC port bind) by using
    ``__new__`` and manually setting instance attributes.
    """
    srv = DuckDBFlightSqlServer.__new__(DuckDBFlightSqlServer)
    import duckdb

    srv._db = duckdb.connect(":memory:")
    from lakehouse.session import SessionManager

    srv._sessions = SessionManager(srv._db)
    srv._prepared_meta = {}
    return srv


@pytest.fixture
def ctx():
    """Mock ``ServerCallContext`` with peer ``"test-peer"``."""
    c = MagicMock(spec=flight.ServerCallContext)
    c.peer.return_value = "test-peer"
    return c


@pytest.fixture
def server_with_data(server, ctx):
    """Server with a pre-populated ``test_table``."""
    conn = server._get_session(ctx)
    conn.execute("CREATE TABLE test_table (id INT PRIMARY KEY, name TEXT, value DOUBLE)")
    conn.execute("INSERT INTO test_table VALUES (1, 'alice', 10.5), (2, 'bob', 20.0)")
    return server


def _make_descriptor(msg):
    """Build a CMD FlightDescriptor from a protobuf message."""
    any_bytes = pack_any(msg).SerializeToString()
    return flight.FlightDescriptor.for_command(any_bytes)


# ═══════════════════════════════════════════════════════════════════════════
#  Module-level helpers
# ═══════════════════════════════════════════════════════════════════════════
class TestGetFlightInfoForCommand:
    """Tests for ``_get_flight_info_for_command``."""

    def test_returns_flight_info_with_correct_schema(self):
        schema = pa.schema([pa.field("x", pa.int32())])
        descriptor = flight.FlightDescriptor.for_command(b"test")
        info = _get_flight_info_for_command(descriptor, schema)

        assert isinstance(info, flight.FlightInfo)
        assert info.schema == schema
        assert len(info.endpoints) == 1
        assert info.total_records == -1
        assert info.total_bytes == -1

    def test_ticket_contains_descriptor_command(self):
        descriptor = flight.FlightDescriptor.for_command(b"my-command")
        info = _get_flight_info_for_command(descriptor, pa.schema([]))
        ticket = info.endpoints[0].ticket
        assert ticket.ticket == b"my-command"


class TestExecuteQuery:
    """Tests for ``_execute_query``."""

    def test_basic_query(self):
        import duckdb

        conn = duckdb.connect()
        table = _execute_query(conn, "SELECT 1 AS x, 2 AS y")
        assert isinstance(table, pa.Table)
        assert table.num_rows == 1
        assert table.column("x")[0].as_py() == 1

    def test_parameterised_query(self):
        import duckdb

        conn = duckdb.connect()
        conn.execute("CREATE TABLE t (v INT)")
        conn.execute("INSERT INTO t VALUES (10), (20)")
        table = _execute_query(conn, "SELECT * FROM t WHERE v > ?", [15])
        assert table.num_rows == 1
        assert table.column("v")[0].as_py() == 20


class TestInferParameterSchema:
    """Tests for ``_infer_parameter_schema``."""

    def test_timestamp_columns_use_millisecond_precision(self):
        conn = duckdb.connect()
        conn.execute("CREATE TABLE t (created_at TIMESTAMP)")

        schema = _infer_parameter_schema(conn, "INSERT INTO t VALUES (?)", 1)

        assert schema.field(0).type == pa.timestamp("ms", tz="UTC")


class TestRecordBatchStream:
    """Tests for ``_record_batch_stream``."""

    def test_returns_record_batch_stream(self):
        table = pa.table({"a": [1, 2, 3]})
        stream = _record_batch_stream(table)
        assert isinstance(stream, flight.RecordBatchStream)


class TestGetSessionId:
    """Tests for ``_get_session_id``."""

    def test_returns_peer(self):
        ctx = MagicMock()
        ctx.peer.return_value = "peer-123"
        assert _get_session_id(ctx) == "peer-123"

    def test_returns_anonymous_for_none(self):
        ctx = MagicMock()
        ctx.peer.return_value = None
        assert _get_session_id(ctx) == "anonymous"

    def test_returns_anonymous_for_empty(self):
        ctx = MagicMock()
        ctx.peer.return_value = ""
        assert _get_session_id(ctx) == "anonymous"


class TestPrepareGetTablesQuery:
    """Tests for ``_prepare_get_tables_query``."""

    def test_no_filters(self):
        cmd = fs.CommandGetTables()
        query, params = _prepare_get_tables_query(cmd)
        assert "CURRENT_DATABASE()" not in query
        assert params == []

    def test_with_catalog(self):
        cmd = fs.CommandGetTables(catalog="mydb")
        query, params = _prepare_get_tables_query(cmd)
        assert "?" in query
        assert "mydb" in params

    def test_with_schema_filter(self):
        cmd = fs.CommandGetTables(db_schema_filter_pattern="main%")
        query, params = _prepare_get_tables_query(cmd)
        assert "LIKE" in query
        assert "main%" in params

    def test_with_table_filter(self):
        cmd = fs.CommandGetTables(table_name_filter_pattern="test%")
        query, params = _prepare_get_tables_query(cmd)
        assert "table_name LIKE" in query
        assert "test%" in params

    def test_with_table_types(self):
        cmd = fs.CommandGetTables(table_types=["BASE TABLE", "VIEW"])
        query, params = _prepare_get_tables_query(cmd)
        assert "IN (?, ?)" in query
        assert "BASE TABLE" in params
        assert "VIEW" in params


# ═══════════════════════════════════════════════════════════════════════════
#  DuckDBFlightSqlServer — construction
# ═══════════════════════════════════════════════════════════════════════════
class TestServerConstruction:
    """Tests for server initialisation."""

    def test_server_has_sessions(self, server):
        from lakehouse.session import SessionManager

        assert isinstance(server._sessions, SessionManager)

    def test_server_has_prepared_meta(self, server):
        assert server._prepared_meta == {}

    def test_get_session_creates_on_first_access(self, server, ctx):
        conn = server._get_session(ctx)
        assert conn is not None
        # Second call returns same connection
        conn2 = server._get_session(ctx)
        assert conn2 is conn

    def test_shutdown_closes_sessions(self, server, ctx):
        server._get_session(ctx)
        assert server._sessions.active_count == 1
        server._sessions.close_all()
        server._db.close()
        assert server._sessions.active_count == 0


# ═══════════════════════════════════════════════════════════════════════════
#  get_flight_info handlers
# ═══════════════════════════════════════════════════════════════════════════
class TestGetFlightInfoStatement:
    """Tests for ``get_flight_info_statement``."""

    def test_returns_flight_info_with_schema(self, server_with_data, ctx):
        cmd = fs.CommandStatementQuery(query="SELECT id, name FROM test_table")
        descriptor = _make_descriptor(cmd)
        info = server_with_data.get_flight_info_statement(ctx, cmd, descriptor)

        assert isinstance(info, flight.FlightInfo)
        assert info.schema.names == ["id", "name"]
        assert len(info.endpoints) == 1

    def test_ticket_encodes_query(self, server_with_data, ctx):
        query = "SELECT * FROM test_table"
        cmd = fs.CommandStatementQuery(query=query)
        descriptor = _make_descriptor(cmd)
        info = server_with_data.get_flight_info_statement(ctx, cmd, descriptor)

        ticket_bytes = info.endpoints[0].ticket.ticket
        any_msg = unpack_any(ticket_bytes, fs.TicketStatementQuery)
        assert any_msg.statement_handle.decode("utf-8") == query

    def test_schema_matches_query_columns(self, server_with_data, ctx):
        cmd = fs.CommandStatementQuery(query="SELECT value FROM test_table")
        descriptor = _make_descriptor(cmd)
        info = server_with_data.get_flight_info_statement(ctx, cmd, descriptor)
        assert info.schema.names == ["value"]


class TestGetSchema:
    """Tests for the Flight ``GetSchema`` RPC."""

    def test_statement_query_schema(self, server_with_data, ctx):
        cmd = fs.CommandStatementQuery(query="SELECT id, name FROM test_table")
        descriptor = _make_descriptor(cmd)

        result = server_with_data.get_schema(ctx, descriptor)

        assert isinstance(result, flight.SchemaResult)
        assert result.schema.names == ["id", "name"]

    def test_prepared_statement_schema_without_executing_ddl(self, server, ctx):
        create_req = fs.ActionCreatePreparedStatementRequest(
            query="CREATE TABLE schema_probe_side_effect (id INT)"
        )
        prepared = server.create_prepared_statement(ctx, create_req)
        cmd = fs.CommandPreparedStatementQuery(
            prepared_statement_handle=prepared.prepared_statement_handle
        )
        descriptor = _make_descriptor(cmd)

        result = server.get_schema(ctx, descriptor)

        assert isinstance(result, flight.SchemaResult)
        assert result.schema == pa.schema([])
        with pytest.raises(duckdb.CatalogException):
            server._get_session(ctx).execute("SELECT * FROM schema_probe_side_effect")

    def test_metadata_schema(self, server, ctx):
        cmd = fs.CommandGetTables(include_schema=True)
        descriptor = _make_descriptor(cmd)

        result = server.get_schema(ctx, descriptor)

        assert isinstance(result, flight.SchemaResult)
        assert result.schema.names == [
            "catalog_name",
            "db_schema_name",
            "table_name",
            "table_type",
            "table_schema",
        ]

    @pytest.mark.parametrize(
        "cmd",
        [
            fs.CommandGetImportedKeys(table="child"),
            fs.CommandGetExportedKeys(table="parent"),
        ],
    )
    def test_foreign_key_metadata_schema(self, server, ctx, cmd):
        descriptor = _make_descriptor(cmd)

        result = server.get_schema(ctx, descriptor)

        assert isinstance(result, flight.SchemaResult)
        assert "pk_table_name" in result.schema.names
        assert "fk_table_name" in result.schema.names


class TestGetFlightInfoCatalogs:
    def test_returns_catalogs_schema(self, server, ctx):
        cmd = fs.CommandGetCatalogs()
        descriptor = _make_descriptor(cmd)
        info = server.get_flight_info_catalogs(ctx, cmd, descriptor)
        assert info.schema.names == ["catalog_name"]


class TestGetFlightInfoDbSchemas:
    def test_returns_db_schemas_schema(self, server, ctx):
        cmd = fs.CommandGetDbSchemas()
        descriptor = _make_descriptor(cmd)
        info = server.get_flight_info_db_schemas(ctx, cmd, descriptor)
        assert info.schema.names == ["catalog_name", "db_schema_name"]


class TestGetFlightInfoTables:
    def test_without_include_schema(self, server, ctx):
        cmd = fs.CommandGetTables()
        descriptor = _make_descriptor(cmd)
        info = server.get_flight_info_tables(ctx, cmd, descriptor)
        assert "table_schema" not in info.schema.names

    def test_with_include_schema(self, server, ctx):
        cmd = fs.CommandGetTables(include_schema=True)
        descriptor = _make_descriptor(cmd)
        info = server.get_flight_info_tables(ctx, cmd, descriptor)
        assert "table_schema" in info.schema.names


class TestGetFlightInfoTableTypes:
    def test_returns_table_types_schema(self, server, ctx):
        cmd = fs.CommandGetTableTypes()
        descriptor = _make_descriptor(cmd)
        info = server.get_flight_info_table_types(ctx, cmd, descriptor)
        assert info.schema.names == ["table_type"]


class TestGetFlightInfoKeys:
    def test_primary_keys(self, server, ctx):
        cmd = fs.CommandGetPrimaryKeys(table="t")
        descriptor = _make_descriptor(cmd)
        info = server.get_flight_info_primary_keys(ctx, cmd, descriptor)
        assert "column_name" in info.schema.names

    def test_imported_keys(self, server, ctx):
        cmd = fs.CommandGetImportedKeys(table="t")
        descriptor = _make_descriptor(cmd)
        info = server.get_flight_info_imported_keys(ctx, cmd, descriptor)
        assert "pk_table_name" in info.schema.names

    def test_exported_keys(self, server, ctx):
        cmd = fs.CommandGetExportedKeys(table="t")
        descriptor = _make_descriptor(cmd)
        info = server.get_flight_info_exported_keys(ctx, cmd, descriptor)
        assert "fk_table_name" in info.schema.names

    def test_cross_reference(self, server, ctx):
        cmd = fs.CommandGetCrossReference(pk_table="t1", fk_table="t2")
        descriptor = _make_descriptor(cmd)
        info = server.get_flight_info_cross_reference(ctx, cmd, descriptor)
        assert "pk_table_name" in info.schema.names


# ═══════════════════════════════════════════════════════════════════════════
#  do_get handlers — return type + data verification via direct SQL
# ═══════════════════════════════════════════════════════════════════════════
class TestDoGetStatement:
    def test_returns_record_batch_stream(self, server_with_data, ctx):
        cmd = fs.TicketStatementQuery(statement_handle=b"SELECT * FROM test_table ORDER BY id")
        stream = server_with_data.do_get_statement(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)

    def test_data_correctness(self, server_with_data, ctx):
        conn = server_with_data._get_session(ctx)
        table = _execute_query(conn, "SELECT * FROM test_table ORDER BY id")
        assert table.num_rows == 2
        assert table.column("id")[0].as_py() == 1
        assert table.column("name")[1].as_py() == "bob"


class TestDoGetCatalogs:
    def test_returns_stream(self, server, ctx):
        cmd = fs.CommandGetCatalogs()
        stream = server.do_get_catalogs(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)

    def test_data_contains_memory(self, server, ctx):
        conn = server._get_session(ctx)
        table = _execute_query(
            conn,
            "SELECT DISTINCT catalog_name FROM information_schema.schemata",
        )
        catalogs = table.column("catalog_name").to_pylist()
        assert "memory" in catalogs


class TestDoGetDbSchemas:
    def test_returns_stream(self, server, ctx):
        cmd = fs.CommandGetDbSchemas()
        stream = server.do_get_db_schemas(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)

    def test_unfiltered_returns_rows(self, server, ctx):
        conn = server._get_session(ctx)
        table = _execute_query(
            conn,
            "SELECT catalog_name, schema_name AS db_schema_name "
            "FROM information_schema.schemata",
        )
        assert table.num_rows > 0
        assert "db_schema_name" in table.schema.names

    def test_filters_by_catalog(self, server, ctx):
        cmd = fs.CommandGetDbSchemas(catalog="memory")
        stream = server.do_get_db_schemas(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)

    def test_filters_by_schema_pattern(self, server, ctx):
        cmd = fs.CommandGetDbSchemas(db_schema_filter_pattern="main")
        stream = server.do_get_db_schemas(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)


class TestDoGetTables:
    def test_returns_stream(self, server_with_data, ctx):
        cmd = fs.CommandGetTables()
        stream = server_with_data.do_get_tables(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)

    def test_data_contains_test_table(self, server_with_data, ctx):
        conn = server_with_data._get_session(ctx)
        table = _execute_query(
            conn,
            "SELECT table_name FROM information_schema.tables",
        )
        names = table.column("table_name").to_pylist()
        assert "test_table" in names


@pytest.fixture
def server_with_attached_catalog(ctx):
    srv = DuckDBFlightSqlServer.__new__(DuckDBFlightSqlServer)
    srv._db = duckdb.connect(":memory:")
    srv._db.execute("ATTACH ':memory:' AS lakehouse")

    from lakehouse.session import SessionManager

    srv._sessions = SessionManager(srv._db, ducklake_alias="lakehouse")
    srv._prepared_meta = {}

    conn = srv._get_session(ctx)
    conn.execute('CREATE TABLE "lakehouse".main.alias_table (id INT PRIMARY KEY)')
    return srv


@pytest.fixture
def server_with_attached_fk_catalog(ctx):
    srv = DuckDBFlightSqlServer.__new__(DuckDBFlightSqlServer)
    srv._db = duckdb.connect(":memory:")
    srv._db.execute("ATTACH ':memory:' AS lakehouse")

    from lakehouse.session import SessionManager

    srv._sessions = SessionManager(srv._db, ducklake_alias="lakehouse")
    srv._prepared_meta = {}

    conn = srv._get_session(ctx)
    conn.execute("USE lakehouse.main")
    conn.execute("CREATE TABLE parent (id INT PRIMARY KEY)")
    conn.execute("CREATE TABLE child (fk INT REFERENCES parent(id))")
    conn.execute("USE memory.main")
    return srv


class TestCataloglessMetadataWithAttachedCatalog:
    def test_db_schemas_handler_accepts_catalogless_attached_catalog(self, server_with_attached_catalog, ctx):
        cmd = fs.CommandGetDbSchemas(db_schema_filter_pattern="main")
        with patch("lakehouse.server._record_batch_stream", side_effect=lambda table: table) as stream_factory:
            table = server_with_attached_catalog.do_get_db_schemas(ctx, cmd)

        assert stream_factory.call_count == 1
        assert isinstance(table, pa.Table)
        rows = list(
            zip(
                table.column("catalog_name").to_pylist(),
                table.column("db_schema_name").to_pylist(),
                strict=True,
            )
        )
        assert ("lakehouse", "main") in rows

    def test_tables_handler_accepts_catalogless_attached_catalog(self, server_with_attached_catalog, ctx):
        cmd = fs.CommandGetTables(db_schema_filter_pattern="main", table_name_filter_pattern="alias_table")
        with patch("lakehouse.server._record_batch_stream", side_effect=lambda table: table) as stream_factory:
            table = server_with_attached_catalog.do_get_tables(ctx, cmd)

        assert stream_factory.call_count == 1
        assert isinstance(table, pa.Table)
        assert table.num_rows == 1
        assert table.column("catalog_name")[0].as_py() == "lakehouse"
        assert table.column("db_schema_name")[0].as_py() == "main"
        assert table.column("table_name")[0].as_py() == "alias_table"

    def test_unfiltered_table_query_still_sees_attached_catalog(self, server_with_attached_catalog, ctx):
        conn = server_with_attached_catalog._get_session(ctx)
        query, params = _prepare_get_tables_query(
            fs.CommandGetTables(db_schema_filter_pattern="main", table_name_filter_pattern="alias_table")
        )
        table = _execute_query(conn, query, params or None)

        assert table.num_rows == 1
        assert table.column("catalog_name")[0].as_py() == "lakehouse"
        assert table.column("table_name")[0].as_py() == "alias_table"


class TestCataloglessKeyMetadataWithAttachedCatalog:
    def test_primary_keys_handler_accepts_catalogless_attached_catalog(self, server_with_attached_catalog, ctx):
        cmd = fs.CommandGetPrimaryKeys(table="alias_table", db_schema="main")
        with patch("lakehouse.server._record_batch_stream", side_effect=lambda table: table) as stream_factory:
            table = server_with_attached_catalog.do_get_primary_keys(ctx, cmd)

        assert stream_factory.call_count == 1
        assert isinstance(table, pa.Table)
        assert table.num_rows == 1
        assert table.column("catalog_name")[0].as_py() == "lakehouse"
        assert table.column("schema_name")[0].as_py() == "main"
        assert table.column("table_name")[0].as_py() == "alias_table"
        assert table.column("column_name")[0].as_py() == "id"

    def test_imported_keys_handler_accepts_catalogless_attached_catalog(self, server_with_attached_fk_catalog, ctx):
        cmd = fs.CommandGetImportedKeys(table="child", db_schema="main")
        with patch("lakehouse.server._record_batch_stream", side_effect=lambda table: table) as stream_factory:
            table = server_with_attached_fk_catalog.do_get_imported_keys(ctx, cmd)

        assert stream_factory.call_count == 1
        assert isinstance(table, pa.Table)
        assert table.num_rows == 1
        assert table.column("pk_catalog_name")[0].as_py() == "lakehouse"
        assert table.column("fk_catalog_name")[0].as_py() == "lakehouse"
        assert table.column("pk_table_name")[0].as_py() == "parent"
        assert table.column("fk_table_name")[0].as_py() == "child"

    def test_exported_keys_handler_accepts_catalogless_attached_catalog(self, server_with_attached_fk_catalog, ctx):
        cmd = fs.CommandGetExportedKeys(table="parent", db_schema="main")
        with patch("lakehouse.server._record_batch_stream", side_effect=lambda table: table) as stream_factory:
            table = server_with_attached_fk_catalog.do_get_exported_keys(ctx, cmd)

        assert stream_factory.call_count == 1
        assert isinstance(table, pa.Table)
        assert table.num_rows == 1
        assert table.column("pk_catalog_name")[0].as_py() == "lakehouse"
        assert table.column("fk_catalog_name")[0].as_py() == "lakehouse"
        assert table.column("pk_table_name")[0].as_py() == "parent"
        assert table.column("fk_table_name")[0].as_py() == "child"

    def test_cross_reference_handler_accepts_catalogless_attached_catalog(self, server_with_attached_fk_catalog, ctx):
        cmd = fs.CommandGetCrossReference(pk_table="parent", fk_table="child", pk_db_schema="main", fk_db_schema="main")
        with patch("lakehouse.server._record_batch_stream", side_effect=lambda table: table) as stream_factory:
            table = server_with_attached_fk_catalog.do_get_cross_reference(ctx, cmd)

        assert stream_factory.call_count == 1
        assert isinstance(table, pa.Table)
        assert table.num_rows == 1
        assert table.column("pk_catalog_name")[0].as_py() == "lakehouse"
        assert table.column("fk_catalog_name")[0].as_py() == "lakehouse"
        assert table.column("pk_table_name")[0].as_py() == "parent"
        assert table.column("fk_table_name")[0].as_py() == "child"

    def test_filters_by_table_type_view(self, server_with_data, ctx):
        cmd = fs.CommandGetTables(table_types=["VIEW"])
        stream = server_with_data.do_get_tables(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)

    def test_include_schema_adds_column(self, server_with_data, ctx):
        cmd = fs.CommandGetTables(include_schema=True)
        # Calling the handler should not raise — schema column gets appended
        stream = server_with_data.do_get_tables(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)


class TestDoGetTableTypes:
    def test_returns_stream(self, server, ctx):
        cmd = fs.CommandGetTableTypes()
        stream = server.do_get_table_types(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)

    def test_three_standard_types(self, server, ctx):
        conn = server._get_session(ctx)
        table = _execute_query(
            conn,
            "SELECT * FROM VALUES ('BASE TABLE'), ('LOCAL TEMPORARY'), ('VIEW') "
            "AS table_types (table_type)",
        )
        types = table.column("table_type").to_pylist()
        assert "BASE TABLE" in types
        assert "VIEW" in types
        assert "LOCAL TEMPORARY" in types
        assert len(types) == 3


class TestDoGetPrimaryKeys:
    def test_returns_stream(self, server_with_data, ctx):
        cmd = fs.CommandGetPrimaryKeys(table="test_table")
        stream = server_with_data.do_get_primary_keys(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)

    def test_pk_data_correct(self, server_with_data, ctx):
        conn = server_with_data._get_session(ctx)
        table = _execute_query(
            conn,
            "SELECT database_name AS catalog_name, schema_name, table_name, "
            "UNNEST(constraint_column_names) AS column_name, "
            "UNNEST(constraint_column_indexes) + 1 AS key_sequence, "
            "constraint_name AS key_name "
            "FROM duckdb_constraints() "
            "WHERE constraint_type = 'PRIMARY KEY' AND table_name = 'test_table'",
        )
        assert table.num_rows == 1
        assert table.column("column_name")[0].as_py() == "id"
        assert table.column("key_sequence")[0].as_py() == 1

    def test_returns_empty_for_no_pk(self, server, ctx):
        conn = server._get_session(ctx)
        conn.execute("CREATE TABLE no_pk (x INT, y INT)")
        cmd = fs.CommandGetPrimaryKeys(table="no_pk")
        stream = server.do_get_primary_keys(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)


class TestDoGetImportedKeys:
    def test_returns_stream(self, server, ctx):
        conn = server._get_session(ctx)
        conn.execute("CREATE TABLE parent (id INT PRIMARY KEY)")
        conn.execute("CREATE TABLE child (fk INT REFERENCES parent(id))")

        cmd = fs.CommandGetImportedKeys(table="child")
        stream = server.do_get_imported_keys(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)


class TestDoGetExportedKeys:
    def test_returns_stream(self, server, ctx):
        conn = server._get_session(ctx)
        conn.execute("CREATE TABLE parent2 (id INT PRIMARY KEY)")
        conn.execute("CREATE TABLE child2 (fk INT REFERENCES parent2(id))")

        cmd = fs.CommandGetExportedKeys(table="parent2")
        stream = server.do_get_exported_keys(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)


class TestDoGetCrossReference:
    def test_returns_stream(self, server, ctx):
        conn = server._get_session(ctx)
        conn.execute("CREATE TABLE pk_tbl (id INT PRIMARY KEY)")
        conn.execute("CREATE TABLE fk_tbl (ref INT REFERENCES pk_tbl(id))")

        cmd = fs.CommandGetCrossReference(pk_table="pk_tbl", fk_table="fk_tbl")
        stream = server.do_get_cross_reference(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)


# ═══════════════════════════════════════════════════════════════════════════
#  do_put handlers
# ═══════════════════════════════════════════════════════════════════════════
class TestDoPutStatementUpdate:
    def test_insert_returns_row_count(self, server, ctx):
        conn = server._get_session(ctx)
        conn.execute("CREATE TABLE upd (x INT)")

        reader = MagicMock()
        writer = MagicMock(spec=flight.FlightMetadataWriter)

        cmd = fs.CommandStatementUpdate(query="INSERT INTO upd VALUES (1), (2), (3)")
        server.do_put_statement_update(ctx, cmd, reader, writer)

        writer.write.assert_called_once()
        raw_bytes = writer.write.call_args[0][0]
        result = fs.DoPutUpdateResult()
        result.ParseFromString(raw_bytes)
        assert result.record_count == 3

    def test_delete_returns_row_count(self, server, ctx):
        conn = server._get_session(ctx)
        conn.execute("CREATE TABLE del_test (x INT)")
        conn.execute("INSERT INTO del_test VALUES (1), (2)")

        reader = MagicMock()
        writer = MagicMock(spec=flight.FlightMetadataWriter)

        cmd = fs.CommandStatementUpdate(query="DELETE FROM del_test WHERE x = 1")
        server.do_put_statement_update(ctx, cmd, reader, writer)

        raw_bytes = writer.write.call_args[0][0]
        result = fs.DoPutUpdateResult()
        result.ParseFromString(raw_bytes)
        assert result.record_count == 1

    def test_update_returns_row_count(self, server, ctx):
        conn = server._get_session(ctx)
        conn.execute("CREATE TABLE upd2 (x INT)")
        conn.execute("INSERT INTO upd2 VALUES (1), (2)")

        reader = MagicMock()
        writer = MagicMock(spec=flight.FlightMetadataWriter)

        cmd = fs.CommandStatementUpdate(query="UPDATE upd2 SET x = 99")
        server.do_put_statement_update(ctx, cmd, reader, writer)

        raw_bytes = writer.write.call_args[0][0]
        result = fs.DoPutUpdateResult()
        result.ParseFromString(raw_bytes)
        assert result.record_count == 2

    def test_raw_bytes_not_any_wrapped(self, server, ctx):
        """DoPutUpdateResult must be raw-serialised, not Any-wrapped."""
        conn = server._get_session(ctx)
        conn.execute("CREATE TABLE raw_test (x INT)")

        reader = MagicMock()
        writer = MagicMock(spec=flight.FlightMetadataWriter)

        cmd = fs.CommandStatementUpdate(query="INSERT INTO raw_test VALUES (1)")
        server.do_put_statement_update(ctx, cmd, reader, writer)

        raw_bytes = writer.write.call_args[0][0]
        # Raw DoPutUpdateResult for count=1 is very short (2-3 bytes)
        assert len(raw_bytes) < 10
        # Verify it's NOT an Any-wrapped message (Any would have a type_url)
        from google.protobuf.any_pb2 import Any as AnyPB

        any_test = AnyPB()
        any_test.ParseFromString(raw_bytes)
        assert any_test.type_url == ""


# ═══════════════════════════════════════════════════════════════════════════
#  Prepared statements (do_action + do_get + do_put)
# ═══════════════════════════════════════════════════════════════════════════
class TestPreparedStatements:
    def test_create_returns_handle_and_schema(self, server_with_data, ctx):
        request = fs.ActionCreatePreparedStatementRequest(query="SELECT id, name FROM test_table")
        result = server_with_data.create_prepared_statement(ctx, request)

        assert result.prepared_statement_handle != b""
        assert result.dataset_schema != b""
        schema = ipc.read_schema(pa.BufferReader(result.dataset_schema))
        assert schema.names == ["id", "name"]

    def test_create_stores_meta(self, server_with_data, ctx):
        request = fs.ActionCreatePreparedStatementRequest(query="SELECT * FROM test_table")
        result = server_with_data.create_prepared_statement(ctx, request)
        handle = result.prepared_statement_handle.decode("utf-8")

        key = ("test-peer", handle)
        assert key in server_with_data._prepared_meta
        meta = server_with_data._prepared_meta[key]
        assert meta.query == "SELECT * FROM test_table"
        assert isinstance(meta.schema, pa.Schema)

    def test_close_removes_meta(self, server_with_data, ctx):
        create_req = fs.ActionCreatePreparedStatementRequest(query="SELECT 1 AS x")
        result = server_with_data.create_prepared_statement(ctx, create_req)
        handle = result.prepared_statement_handle

        close_req = fs.ActionClosePreparedStatementRequest(prepared_statement_handle=handle)
        server_with_data.close_prepared_statement(ctx, close_req)
        assert ("test-peer", handle.decode("utf-8")) not in server_with_data._prepared_meta

    def test_get_flight_info_returns_real_schema(self, server_with_data, ctx):
        create_req = fs.ActionCreatePreparedStatementRequest(
            query="SELECT id, name FROM test_table"
        )
        result = server_with_data.create_prepared_statement(ctx, create_req)
        handle = result.prepared_statement_handle

        cmd = fs.CommandPreparedStatementQuery(prepared_statement_handle=handle)
        descriptor = _make_descriptor(cmd)
        info = server_with_data.get_flight_info_prepared_statement(ctx, cmd, descriptor)
        assert info.schema.names == ["id", "name"]

    def test_do_get_prepared_statement(self, server_with_data, ctx):
        create_req = fs.ActionCreatePreparedStatementRequest(
            query="SELECT * FROM test_table ORDER BY id"
        )
        result = server_with_data.create_prepared_statement(ctx, create_req)
        handle = result.prepared_statement_handle

        # Manually execute on the cursor so do_get can fetch results
        session_id = "test-peer"
        cursor = server_with_data._sessions.get_prepared_statement(
            session_id, handle.decode("utf-8")
        )
        cursor.execute("SELECT * FROM test_table ORDER BY id")

        cmd = fs.CommandPreparedStatementQuery(prepared_statement_handle=handle)
        stream = server_with_data.do_get_prepared_statement(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)


# ═══════════════════════════════════════════════════════════════════════════
#  Transactions
# ═══════════════════════════════════════════════════════════════════════════
class TestTransactions:
    def test_begin_returns_handle(self, server, ctx):
        server._get_session(ctx)  # session must exist first
        request = fs.ActionBeginTransactionRequest()
        result = server.begin_transaction(ctx, request)
        assert result.transaction_id != b""

    def test_end_commit(self, server, ctx):
        server._get_session(ctx)
        begin_result = server.begin_transaction(ctx, fs.ActionBeginTransactionRequest())
        txn_id = begin_result.transaction_id
        end_req = fs.ActionEndTransactionRequest(
            transaction_id=txn_id,
            action="END_TRANSACTION_COMMIT",
        )
        server.end_transaction(ctx, end_req)  # should not raise

    def test_end_rollback(self, server, ctx):
        server._get_session(ctx)
        begin_result = server.begin_transaction(ctx, fs.ActionBeginTransactionRequest())
        txn_id = begin_result.transaction_id
        end_req = fs.ActionEndTransactionRequest(
            transaction_id=txn_id,
            action="END_TRANSACTION_ROLLBACK",
        )
        server.end_transaction(ctx, end_req)  # should not raise

    def test_commit_persists_data(self, server, ctx):
        conn = server._get_session(ctx)
        conn.execute("CREATE TABLE txn_test (x INT)")

        begin_result = server.begin_transaction(ctx, fs.ActionBeginTransactionRequest())
        txn_id = begin_result.transaction_id

        conn.execute("INSERT INTO txn_test VALUES (42)")

        end_req = fs.ActionEndTransactionRequest(
            transaction_id=txn_id,
            action="END_TRANSACTION_COMMIT",
        )
        server.end_transaction(ctx, end_req)

        table = _execute_query(conn, "SELECT * FROM txn_test")
        assert table.num_rows == 1


# ═══════════════════════════════════════════════════════════════════════════
#  Edge cases & error handling
# ═══════════════════════════════════════════════════════════════════════════
class TestEdgeCases:
    def test_empty_table_returns_stream(self, server, ctx):
        conn = server._get_session(ctx)
        conn.execute("CREATE TABLE empty_tbl (a INT, b TEXT)")
        cmd = fs.TicketStatementQuery(statement_handle=b"SELECT * FROM empty_tbl")
        stream = server.do_get_statement(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)

    def test_get_flight_info_statement_bad_query_raises(self, server, ctx):
        cmd = fs.CommandStatementQuery(query="INVALID SQL !!!")
        descriptor = _make_descriptor(cmd)
        with pytest.raises((duckdb.ParserException, duckdb.CatalogException)):
            server.get_flight_info_statement(ctx, cmd, descriptor)

    def test_multiple_sessions_isolated(self, server):
        ctx1 = MagicMock(spec=flight.ServerCallContext)
        ctx1.peer.return_value = "peer-A"
        ctx2 = MagicMock(spec=flight.ServerCallContext)
        ctx2.peer.return_value = "peer-B"

        conn1 = server._get_session(ctx1)
        conn2 = server._get_session(ctx2)
        assert conn1 is not conn2

    def test_do_get_table_types_exact_count(self, server, ctx):
        conn = server._get_session(ctx)
        table = _execute_query(
            conn,
            "SELECT * FROM VALUES ('BASE TABLE'), ('LOCAL TEMPORARY'), ('VIEW') "
            "AS table_types (table_type)",
        )
        assert table.num_rows == 3

    def test_do_get_statement_large_result(self, server, ctx):
        conn = server._get_session(ctx)
        conn.execute("CREATE TABLE big_tbl AS SELECT range AS id FROM range(1000)")
        cmd = fs.TicketStatementQuery(statement_handle=b"SELECT * FROM big_tbl")
        stream = server.do_get_statement(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)

    def test_prepared_meta_survives_multiple_creates(self, server_with_data, ctx):
        handles = []
        for i in range(5):
            req = fs.ActionCreatePreparedStatementRequest(query=f"SELECT {i} AS val")
            result = server_with_data.create_prepared_statement(ctx, req)
            handles.append(result.prepared_statement_handle)

        assert len(server_with_data._prepared_meta) == 5

        # Close all
        for h in handles:
            close_req = fs.ActionClosePreparedStatementRequest(prepared_statement_handle=h)
            server_with_data.close_prepared_statement(ctx, close_req)

        assert len(server_with_data._prepared_meta) == 0


# ═══════════════════════════════════════════════════════════════════════════
# XDBC Type Info handlers
# ═══════════════════════════════════════════════════════════════════════════


class TestBuildXdbcTypeInfoTable:
    """Unit tests for the ``_build_xdbc_type_info_table`` helper."""

    def test_returns_all_14_types_unfiltered(self):
        table = _build_xdbc_type_info_table()
        assert table.num_rows == 14

    def test_schema_has_19_fields(self):
        table = _build_xdbc_type_info_table()
        assert len(table.schema) == 19
        assert table.schema == _XDBC_TYPE_INFO_SCHEMA

    def test_filter_by_integer_type(self):
        table = _build_xdbc_type_info_table(data_type_filter=4)
        assert table.num_rows == 1
        assert table.column("type_name")[0].as_py().upper() == "INTEGER"

    def test_filter_by_varchar_type(self):
        table = _build_xdbc_type_info_table(data_type_filter=12)
        assert table.num_rows == 1
        assert table.column("type_name")[0].as_py().upper() == "VARCHAR"

    def test_filter_by_bigint_returns_two(self):
        """BIGINT and HUGEINT both have data_type = -5."""
        table = _build_xdbc_type_info_table(data_type_filter=-5)
        assert table.num_rows == 2
        names = {table.column("type_name")[i].as_py().upper() for i in range(2)}
        assert names == {"BIGINT", "HUGEINT"}

    def test_filter_nonexistent_type_returns_empty(self):
        table = _build_xdbc_type_info_table(data_type_filter=9999)
        assert table.num_rows == 0
        assert table.schema == _XDBC_TYPE_INFO_SCHEMA

    def test_type_name_column_not_null(self):
        table = _build_xdbc_type_info_table()
        names = table.column("type_name").to_pylist()
        assert all(n is not None for n in names)

    def test_all_data_types_present(self):
        table = _build_xdbc_type_info_table()
        types = sorted(table.column("data_type").to_pylist())
        # expected: -5 (bigint, hugeint), -1 (text), 3 (decimal), 4 (integer),
        # 5 (smallint), 6 (float), 8 (double), 12 (varchar),
        # 16 (boolean), 91 (date), 92 (time), 93 (timestamp), -6 (tinyint)
        assert len(types) == 14


class TestGetFlightInfoXdbcTypeInfo:
    """Tests for ``get_flight_info_xdbc_type_info``."""

    def test_returns_flight_info(self, server, ctx):
        cmd = fs.CommandGetXdbcTypeInfo()
        desc = _make_descriptor(cmd)
        info = server.get_flight_info_xdbc_type_info(ctx, cmd, desc)
        assert isinstance(info, flight.FlightInfo)

    def test_schema_matches(self, server, ctx):
        cmd = fs.CommandGetXdbcTypeInfo()
        desc = _make_descriptor(cmd)
        info = server.get_flight_info_xdbc_type_info(ctx, cmd, desc)
        assert info.schema == _XDBC_TYPE_INFO_SCHEMA


class TestDoGetXdbcTypeInfo:
    """Tests for ``do_get_xdbc_type_info``."""

    def test_returns_record_batch_stream(self, server, ctx):
        cmd = fs.CommandGetXdbcTypeInfo()
        stream = server.do_get_xdbc_type_info(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)

    def test_filter_by_data_type(self, server, ctx):
        cmd = fs.CommandGetXdbcTypeInfo(data_type=4)
        stream = server.do_get_xdbc_type_info(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)
        # Verify result independently
        table = _build_xdbc_type_info_table(4)
        assert table.num_rows == 1

    def test_no_filter_returns_all(self, server, ctx):
        cmd = fs.CommandGetXdbcTypeInfo()
        stream = server.do_get_xdbc_type_info(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)


# ═══════════════════════════════════════════════════════════════════════════
# SQL Info handlers
# ═══════════════════════════════════════════════════════════════════════════


class TestBuildSqlInfoTable:
    """Unit tests for the ``_build_sql_info_table`` helper."""

    def test_returns_all_infos_unfiltered(self):
        table = _build_sql_info_table()
        assert table.num_rows >= 12

    def test_schema_matches(self):
        table = _build_sql_info_table()
        assert table.schema == _SQL_INFO_SCHEMA

    def test_filter_by_specific_ids(self):
        table = _build_sql_info_table([0, 1])  # server_name, version
        assert table.num_rows == 2

    def test_filter_by_single_id(self):
        table = _build_sql_info_table([0])
        assert table.num_rows == 1
        assert table.column("info_name")[0].as_py() == 0

    def test_filter_nonexistent_id_returns_empty(self):
        table = _build_sql_info_table([99999])
        assert table.num_rows == 0

    def test_server_name_is_lakehouse(self):
        table = _build_sql_info_table([0])
        # info_name 0 = FLIGHT_SQL_SERVER_NAME
        # Value is a dense union — extract the string_value child
        value_col = table.column("value")
        # First element is type_code 0 (string)
        assert value_col[0].as_py() == "lakehouse"

    def test_read_only_is_false(self):
        table = _build_sql_info_table([fs.FLIGHT_SQL_SERVER_READ_ONLY])
        value_col = table.column("value")
        assert value_col[0].as_py() is False

    def test_current_flight_sql_capability_ids_are_reported(self):
        current_capability_ids = [
            fs.FLIGHT_SQL_SERVER_READ_ONLY,
            fs.FLIGHT_SQL_SERVER_SQL,
            fs.FLIGHT_SQL_SERVER_SUBSTRAIT,
            fs.FLIGHT_SQL_SERVER_TRANSACTION,
            fs.FLIGHT_SQL_SERVER_CANCEL,
            fs.FLIGHT_SQL_SERVER_BULK_INGESTION,
            fs.FLIGHT_SQL_SERVER_INGEST_TRANSACTIONS_SUPPORTED,
        ]

        table = _build_sql_info_table(current_capability_ids)

        assert set(table.column("info_name").to_pylist()) == set(current_capability_ids)

    def test_transaction_sql_info_ids_are_reported(self):
        transaction_info_ids = [
            fs.SQL_DEFAULT_TRANSACTION_ISOLATION,
            fs.SQL_TRANSACTIONS_SUPPORTED,
            fs.SQL_SUPPORTED_TRANSACTIONS_ISOLATION_LEVELS,
            fs.SQL_DATA_DEFINITION_CAUSES_TRANSACTION_COMMIT,
            fs.SQL_DATA_DEFINITIONS_IN_TRANSACTIONS_IGNORED,
        ]

        table = _build_sql_info_table(transaction_info_ids)
        values = dict(
            zip(
                table.column("info_name").to_pylist(),
                table.column("value").to_pylist(),
                strict=True,
            )
        )

        assert values[fs.SQL_DEFAULT_TRANSACTION_ISOLATION] == fs.SQL_TRANSACTION_SERIALIZABLE
        assert values[fs.SQL_TRANSACTIONS_SUPPORTED] is True
        assert values[fs.SQL_SUPPORTED_TRANSACTIONS_ISOLATION_LEVELS] == (
            1 << fs.SQL_TRANSACTION_SERIALIZABLE
        )
        assert values[fs.SQL_DATA_DEFINITION_CAUSES_TRANSACTION_COMMIT] is False
        assert values[fs.SQL_DATA_DEFINITIONS_IN_TRANSACTIONS_IGNORED] is False

    def test_empty_filter_returns_all(self):
        table1 = _build_sql_info_table(None)
        table2 = _build_sql_info_table([])
        # Both should return all entries
        assert table1.num_rows == table2.num_rows


class TestGetFlightInfoSqlInfo:
    """Tests for ``get_flight_info_sql_info``."""

    def test_returns_flight_info(self, server, ctx):
        cmd = fs.CommandGetSqlInfo()
        desc = _make_descriptor(cmd)
        info = server.get_flight_info_sql_info(ctx, cmd, desc)
        assert isinstance(info, flight.FlightInfo)

    def test_schema_matches(self, server, ctx):
        cmd = fs.CommandGetSqlInfo()
        desc = _make_descriptor(cmd)
        info = server.get_flight_info_sql_info(ctx, cmd, desc)
        assert info.schema == _SQL_INFO_SCHEMA


class TestDoGetSqlInfo:
    """Tests for ``do_get_sql_info``."""

    def test_returns_record_batch_stream(self, server, ctx):
        cmd = fs.CommandGetSqlInfo()
        stream = server.do_get_sql_info(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)

    def test_with_filter(self, server, ctx):
        cmd = fs.CommandGetSqlInfo(info=[0, 1, 2])
        stream = server.do_get_sql_info(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)


# ═══════════════════════════════════════════════════════════════════════════
# do_put_statement_ingest handler
# ═══════════════════════════════════════════════════════════════════════════


class TestDoPutStatementIngest:
    """Tests for ``do_put_statement_ingest``."""

    @staticmethod
    def _make_reader(arrow_table: pa.Table):
        """Create a mock MetadataRecordBatchReader from a pa.Table."""
        batches = arrow_table.to_batches()
        call_count = 0

        def read_chunk():
            nonlocal call_count
            if call_count < len(batches):
                result = MagicMock()
                result.data = batches[call_count]
                call_count += 1
                return result
            raise StopIteration

        reader = MagicMock(spec=flight.MetadataRecordBatchReader)
        reader.read_chunk = read_chunk
        reader.schema = arrow_table.schema
        return reader

    def test_ingest_creates_table(self, server, ctx):
        data = pa.table({"x": [1, 2, 3], "y": ["a", "b", "c"]})
        reader = self._make_reader(data)
        writer = MagicMock()

        cmd = fs.CommandStatementIngest(table="ingest_test")
        server.do_put_statement_ingest(ctx, cmd, reader, writer)

        writer.write.assert_called_once()
        # Verify data landed
        conn = server._get_session(ctx)
        result = _execute_query(conn, "SELECT COUNT(*) AS cnt FROM ingest_test")
        assert result.column("cnt")[0].as_py() == 3

    def test_ingest_appends_to_existing(self, server, ctx):
        conn = server._get_session(ctx)
        conn.execute("CREATE TABLE append_tbl (x INT, y TEXT)")
        conn.execute("INSERT INTO append_tbl VALUES (0, 'z')")

        data = pa.table({"x": [1, 2], "y": ["a", "b"]})
        reader = self._make_reader(data)
        writer = MagicMock()

        cmd = fs.CommandStatementIngest(
            table="append_tbl",
            table_definition_options=fs.CommandStatementIngest.TableDefinitionOptions(
                if_not_exist="TABLE_NOT_EXIST_OPTION_CREATE",
                if_exists="TABLE_EXISTS_OPTION_APPEND",  # CREATE / APPEND
            ),
        )
        server.do_put_statement_ingest(ctx, cmd, reader, writer)

        result = _execute_query(conn, "SELECT COUNT(*) AS cnt FROM append_tbl")
        assert result.column("cnt")[0].as_py() == 3

    def test_ingest_replace_existing_table(self, server, ctx):
        conn = server._get_session(ctx)
        conn.execute("CREATE TABLE replace_tbl (x INT)")
        conn.execute("INSERT INTO replace_tbl VALUES (999)")

        data = pa.table({"x": [1, 2]})
        reader = self._make_reader(data)
        writer = MagicMock()

        cmd = fs.CommandStatementIngest(
            table="replace_tbl",
            table_definition_options=fs.CommandStatementIngest.TableDefinitionOptions(
                if_not_exist="TABLE_NOT_EXIST_OPTION_CREATE",
                if_exists="TABLE_EXISTS_OPTION_REPLACE",  # CREATE / REPLACE
            ),
        )
        server.do_put_statement_ingest(ctx, cmd, reader, writer)

        result = _execute_query(conn, "SELECT * FROM replace_tbl")
        assert result.num_rows == 2

    def test_ingest_fail_if_exists(self, server, ctx):
        conn = server._get_session(ctx)
        conn.execute("CREATE TABLE fail_tbl (x INT)")

        data = pa.table({"x": [1]})
        reader = self._make_reader(data)
        writer = MagicMock()

        cmd = fs.CommandStatementIngest(
            table="fail_tbl",
            table_definition_options=fs.CommandStatementIngest.TableDefinitionOptions(
                if_not_exist="TABLE_NOT_EXIST_OPTION_CREATE",
                if_exists="TABLE_EXISTS_OPTION_FAIL",  # CREATE / FAIL
            ),
        )
        with pytest.raises(flight.FlightServerError, match="already exists"):
            server.do_put_statement_ingest(ctx, cmd, reader, writer)

    def test_ingest_fail_if_not_exists(self, server, ctx):
        data = pa.table({"x": [1]})
        reader = self._make_reader(data)
        writer = MagicMock()

        cmd = fs.CommandStatementIngest(
            table="no_such_tbl",
            table_definition_options=fs.CommandStatementIngest.TableDefinitionOptions(
                if_not_exist="TABLE_NOT_EXIST_OPTION_FAIL",
                if_exists="TABLE_EXISTS_OPTION_APPEND",  # FAIL / APPEND
            ),
        )
        with pytest.raises(flight.FlightServerError, match="does not exist"):
            server.do_put_statement_ingest(ctx, cmd, reader, writer)

    def test_ingest_empty_reader_writes_zero(self, server, ctx):
        empty = pa.table({"x": pa.array([], type=pa.int64())})
        reader = self._make_reader(empty)
        writer = MagicMock()

        cmd = fs.CommandStatementIngest(table="empty_tbl")
        server.do_put_statement_ingest(ctx, cmd, reader, writer)

        writer.write.assert_called_once()
        # Verify DoPutUpdateResult with record_count = 0
        buf = writer.write.call_args[0][0]
        result = fs.DoPutUpdateResult()
        result.ParseFromString(buf)
        assert result.record_count == 0

    def test_ingest_with_schema_qualifier(self, server, ctx):
        data = pa.table({"id": [1], "val": [42]})
        reader = self._make_reader(data)
        writer = MagicMock()

        cmd = fs.CommandStatementIngest(
            table="qualified_tbl",
            schema="main",
        )
        server.do_put_statement_ingest(ctx, cmd, reader, writer)

        conn = server._get_session(ctx)
        result = _execute_query(conn, 'SELECT * FROM main."qualified_tbl"')
        assert result.num_rows == 1

    def test_ingest_writes_correct_row_count(self, server, ctx):
        data = pa.table({"v": list(range(50))})
        reader = self._make_reader(data)
        writer = MagicMock()

        cmd = fs.CommandStatementIngest(table="count_tbl")
        server.do_put_statement_ingest(ctx, cmd, reader, writer)

        buf = writer.write.call_args[0][0]
        result = fs.DoPutUpdateResult()
        result.ParseFromString(buf)
        assert result.record_count == 50


# ═══════════════════════════════════════════════════════════════════════════
# Arrow type to SQL mapping
# ═══════════════════════════════════════════════════════════════════════════


class TestArrowTypeToSql:
    """Unit tests for ``_arrow_type_to_sql``."""

    def test_int32(self):
        assert _arrow_type_to_sql(pa.int32()) == "INTEGER"

    def test_int64(self):
        assert _arrow_type_to_sql(pa.int64()) == "BIGINT"

    def test_string(self):
        assert _arrow_type_to_sql(pa.string()) == "VARCHAR"

    def test_float64(self):
        assert _arrow_type_to_sql(pa.float64()) == "DOUBLE"

    def test_bool(self):
        assert _arrow_type_to_sql(pa.bool_()) == "BOOLEAN"

    def test_date32(self):
        assert _arrow_type_to_sql(pa.date32()) == "DATE"

    def test_timestamp(self):
        assert _arrow_type_to_sql(pa.timestamp("us")) == "TIMESTAMP"

    def test_decimal(self):
        result = _arrow_type_to_sql(pa.decimal128(18, 3))
        assert "DECIMAL" in result.upper()

    def test_unknown_falls_back_to_varchar(self):
        assert _arrow_type_to_sql(pa.null()) == "VARCHAR"


# ═══════════════════════════════════════════════════════════════════════════
# Savepoint handlers
# ═══════════════════════════════════════════════════════════════════════════


class TestBeginSavepoint:
    """Tests for ``begin_savepoint`` — DuckDB does not support savepoints."""

    def test_raises_error(self, server, ctx):
        req = fs.ActionBeginSavepointRequest(
            transaction_id=b"test-txn",
            name="sp1",
        )
        with pytest.raises(flight.FlightServerError, match="not supported"):
            server.begin_savepoint(ctx, req)


class TestEndSavepoint:
    """Tests for ``end_savepoint`` — DuckDB does not support savepoints."""

    def test_release_raises_error(self, server, ctx):
        req = fs.ActionEndSavepointRequest(
            savepoint_id=b"sp_release",
            action="END_SAVEPOINT_RELEASE",
        )
        with pytest.raises(flight.FlightServerError, match="not supported"):
            server.end_savepoint(ctx, req)

    def test_rollback_raises_error(self, server, ctx):
        req = fs.ActionEndSavepointRequest(
            savepoint_id=b"sp_rollback",
            action="END_SAVEPOINT_ROLLBACK",
        )
        with pytest.raises(flight.FlightServerError, match="not supported"):
            server.end_savepoint(ctx, req)


# ═══════════════════════════════════════════════════════════════════════════
# cancel_query handler
# ═══════════════════════════════════════════════════════════════════════════


class TestCancelQuery:
    """Tests for ``cancel_query``."""

    def test_returns_cancelling(self, server, ctx):
        req = fs.ActionCancelQueryRequest(info=b"dummy-flight-info")
        result = server.cancel_query(ctx, req)
        assert isinstance(result, fs.ActionCancelQueryResult)
        # CANCEL_RESULT_CANCELLING = 2
        assert result.result == 2

    def test_return_type(self, server, ctx):
        req = fs.ActionCancelQueryRequest(info=b"dummy-flight-info")
        result = server.cancel_query(ctx, req)
        assert isinstance(result, fs.ActionCancelQueryResult)


# ═══════════════════════════════════════════════════════════════════════════
# Coverage: _arrow_type_to_sql — list type branch
# ═══════════════════════════════════════════════════════════════════════════
class TestArrowTypeToSqlListType:
    """Cover the list<*> fallback to VARCHAR[] in _arrow_type_to_sql."""

    def test_list_int_returns_varchar_array(self):
        assert _arrow_type_to_sql(pa.list_(pa.int32())) == "VARCHAR[]"

    def test_list_string_returns_varchar_array(self):
        assert _arrow_type_to_sql(pa.list_(pa.string())) == "VARCHAR[]"

    def test_large_list_returns_varchar_array(self):
        assert _arrow_type_to_sql(pa.large_list(pa.float64())) == "VARCHAR[]"


# ═══════════════════════════════════════════════════════════════════════════
# Coverage: do_get_prepared_statement — edge cases
# ═══════════════════════════════════════════════════════════════════════════
class TestDoGetPreparedStatementEdgeCases:
    """Cover prepared statement fallback paths in do_get_prepared_statement."""

    def test_no_prior_execution_falls_back_to_meta_query(self, server_with_data, ctx):
        """When cursor has no results, fallback to executing meta.query."""
        create_req = fs.ActionCreatePreparedStatementRequest(
            query="SELECT * FROM test_table ORDER BY id"
        )
        result = server_with_data.create_prepared_statement(ctx, create_req)
        handle = result.prepared_statement_handle

        # Call do_get WITHOUT first executing on the cursor — forces fallback
        cmd = fs.CommandPreparedStatementQuery(prepared_statement_handle=handle)
        stream = server_with_data.do_get_prepared_statement(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)

    def test_no_meta_no_fetch_returns_empty_table(self, server, ctx):
        """When there is no meta and no fetchable data, return empty table."""
        # Create a session and a cursor manually without metadata
        session_id = "test-peer"
        server._get_session(ctx)
        handle, _cursor = server._sessions.add_prepared_statement(session_id)

        cmd = fs.CommandPreparedStatementQuery(prepared_statement_handle=handle.encode("utf-8"))
        stream = server.do_get_prepared_statement(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)


# ═══════════════════════════════════════════════════════════════════════════
# Coverage: create_prepared_statement — DDL query empty schema fallback
# ═══════════════════════════════════════════════════════════════════════════
class TestCreatePreparedStatementDDL:
    """Cover the schema inference failure path for DDL queries."""

    def test_ddl_query_returns_empty_schema(self, server, ctx):
        """CREATE TABLE can't produce a SELECT schema → empty schema fallback."""
        server._get_session(ctx)
        request = fs.ActionCreatePreparedStatementRequest(query="CREATE TABLE ps_ddl_test (x INT)")
        result = server.create_prepared_statement(ctx, request)
        assert result.prepared_statement_handle != b""
        schema = ipc.read_schema(pa.BufferReader(result.dataset_schema))
        assert len(schema) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Coverage: do_get_primary_keys with catalog/schema filters
# ═══════════════════════════════════════════════════════════════════════════
class TestDoGetPrimaryKeysFilters:
    """Cover optional catalog and db_schema filter branches."""

    def test_with_explicit_catalog(self, server_with_data, ctx):
        cmd = fs.CommandGetPrimaryKeys(table="test_table", catalog="memory")
        stream = server_with_data.do_get_primary_keys(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)

    def test_with_schema_filter(self, server_with_data, ctx):
        cmd = fs.CommandGetPrimaryKeys(table="test_table", db_schema="main")
        stream = server_with_data.do_get_primary_keys(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)

    def test_with_both_catalog_and_schema(self, server_with_data, ctx):
        cmd = fs.CommandGetPrimaryKeys(table="test_table", catalog="memory", db_schema="main")
        stream = server_with_data.do_get_primary_keys(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)


# ═══════════════════════════════════════════════════════════════════════════
# Coverage: do_get_imported_keys with catalog/schema filters
# ═══════════════════════════════════════════════════════════════════════════
class TestDoGetImportedKeysFilters:
    """Cover optional catalog and db_schema filter branches."""

    @pytest.fixture
    def fk_server(self, server, ctx):
        conn = server._get_session(ctx)
        conn.execute("CREATE TABLE ik_parent (id INT PRIMARY KEY)")
        conn.execute("CREATE TABLE ik_child (fk INT REFERENCES ik_parent(id))")
        return server

    def test_with_explicit_catalog(self, fk_server, ctx):
        cmd = fs.CommandGetImportedKeys(table="ik_child", catalog="memory")
        stream = fk_server.do_get_imported_keys(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)

    def test_with_schema_filter(self, fk_server, ctx):
        cmd = fs.CommandGetImportedKeys(table="ik_child", db_schema="main")
        stream = fk_server.do_get_imported_keys(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)


# ═══════════════════════════════════════════════════════════════════════════
# Coverage: do_get_exported_keys with catalog/schema filters
# ═══════════════════════════════════════════════════════════════════════════
class TestDoGetExportedKeysFilters:
    """Cover optional catalog and db_schema filter branches."""

    @pytest.fixture
    def fk_server(self, server, ctx):
        conn = server._get_session(ctx)
        conn.execute("CREATE TABLE ek_parent (id INT PRIMARY KEY)")
        conn.execute("CREATE TABLE ek_child (fk INT REFERENCES ek_parent(id))")
        return server

    def test_with_explicit_catalog(self, fk_server, ctx):
        cmd = fs.CommandGetExportedKeys(table="ek_parent", catalog="memory")
        stream = fk_server.do_get_exported_keys(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)

    def test_with_schema_filter(self, fk_server, ctx):
        cmd = fs.CommandGetExportedKeys(table="ek_parent", db_schema="main")
        stream = fk_server.do_get_exported_keys(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)


# ═══════════════════════════════════════════════════════════════════════════
# Coverage: do_get_cross_reference with catalog/schema filters
# ═══════════════════════════════════════════════════════════════════════════
class TestDoGetCrossReferenceFilters:
    """Cover optional catalog and db_schema filter branches."""

    @pytest.fixture
    def fk_server(self, server, ctx):
        conn = server._get_session(ctx)
        conn.execute("CREATE TABLE cr_pk (id INT PRIMARY KEY)")
        conn.execute("CREATE TABLE cr_fk (ref INT REFERENCES cr_pk(id))")
        return server

    def test_with_pk_catalog(self, fk_server, ctx):
        cmd = fs.CommandGetCrossReference(pk_table="cr_pk", fk_table="cr_fk", pk_catalog="memory")
        stream = fk_server.do_get_cross_reference(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)

    def test_with_pk_schema(self, fk_server, ctx):
        cmd = fs.CommandGetCrossReference(pk_table="cr_pk", fk_table="cr_fk", pk_db_schema="main")
        stream = fk_server.do_get_cross_reference(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)

    def test_with_fk_catalog(self, fk_server, ctx):
        cmd = fs.CommandGetCrossReference(pk_table="cr_pk", fk_table="cr_fk", fk_catalog="memory")
        stream = fk_server.do_get_cross_reference(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)

    def test_with_fk_schema(self, fk_server, ctx):
        cmd = fs.CommandGetCrossReference(pk_table="cr_pk", fk_table="cr_fk", fk_db_schema="main")
        stream = fk_server.do_get_cross_reference(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)

    def test_with_all_filters(self, fk_server, ctx):
        cmd = fs.CommandGetCrossReference(
            pk_table="cr_pk",
            fk_table="cr_fk",
            pk_catalog="memory",
            pk_db_schema="main",
            fk_catalog="memory",
            fk_db_schema="main",
        )
        stream = fk_server.do_get_cross_reference(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)


# ═══════════════════════════════════════════════════════════════════════════
# Coverage: do_put_prepared_statement_update
# ═══════════════════════════════════════════════════════════════════════════
class TestDoPutPreparedStatementUpdate:
    """Cover do_put_prepared_statement_update handler."""

    def test_with_params(self, server, ctx):
        conn = server._get_session(ctx)
        conn.execute("CREATE TABLE ps_upd (x INT, y TEXT)")

        # Create prepared statement for INSERT
        create_req = fs.ActionCreatePreparedStatementRequest(
            query="INSERT INTO ps_upd VALUES (?, ?)"
        )
        result = server.create_prepared_statement(ctx, create_req)
        handle = result.prepared_statement_handle

        # Build a mock reader with parameter data
        batch = pa.record_batch(
            [pa.array([42]), pa.array(["hello"])],
            names=["p1", "p2"],
        )
        chunk = MagicMock()
        chunk.data = batch
        reader = MagicMock(spec=flight.MetadataRecordBatchReader)
        reader.read_chunk = MagicMock(side_effect=[chunk, StopIteration()])
        writer = MagicMock(spec=flight.FlightMetadataWriter)

        cmd = fs.CommandPreparedStatementUpdate(prepared_statement_handle=handle)
        server.do_put_prepared_statement_update(ctx, cmd, reader, writer)

        writer.write.assert_called_once()

    def test_without_params(self, server, ctx):
        conn = server._get_session(ctx)
        conn.execute("CREATE TABLE ps_upd2 (x INT)")
        conn.execute("INSERT INTO ps_upd2 VALUES (1), (2)")

        create_req = fs.ActionCreatePreparedStatementRequest(query="DELETE FROM ps_upd2")
        result = server.create_prepared_statement(ctx, create_req)
        handle = result.prepared_statement_handle

        reader = MagicMock(spec=flight.MetadataRecordBatchReader)
        reader.read_chunk = MagicMock(side_effect=StopIteration())
        writer = MagicMock(spec=flight.FlightMetadataWriter)

        cmd = fs.CommandPreparedStatementUpdate(prepared_statement_handle=handle)
        server.do_put_prepared_statement_update(ctx, cmd, reader, writer)

        writer.write.assert_called_once()
        raw_bytes = writer.write.call_args[0][0]
        update_result = fs.DoPutUpdateResult()
        update_result.ParseFromString(raw_bytes)
        assert update_result.record_count == 2


# ═══════════════════════════════════════════════════════════════════════════
# Coverage: do_put_prepared_statement_query
# ═══════════════════════════════════════════════════════════════════════════
class TestDoPutPreparedStatementQuery:
    """Cover do_put_prepared_statement_query handler."""

    def test_binds_params_and_allows_do_get(self, server_with_data, ctx):
        """Bind parameters then retrieve results with do_get."""
        create_req = fs.ActionCreatePreparedStatementRequest(
            query="SELECT * FROM test_table WHERE id = ?"
        )
        result = server_with_data.create_prepared_statement(ctx, create_req)
        handle = result.prepared_statement_handle

        # Build a reader with parameter value
        batch = pa.record_batch([pa.array([1])], names=["p1"])
        chunk = MagicMock()
        chunk.data = batch
        reader = MagicMock(spec=flight.MetadataRecordBatchReader)
        reader.read_chunk = MagicMock(side_effect=[chunk, StopIteration()])
        writer = MagicMock()

        cmd = fs.CommandPreparedStatementQuery(prepared_statement_handle=handle)
        server_with_data.do_put_prepared_statement_query(ctx, cmd, reader, writer)

        # Now do_get should return the parameterized results
        stream = server_with_data.do_get_prepared_statement(ctx, cmd)
        assert isinstance(stream, flight.RecordBatchStream)

    def test_no_meta_returns_early(self, server, ctx):
        """When there is no meta for the handle, do_put returns without error."""
        server._get_session(ctx)
        handle, _cursor = server._sessions.add_prepared_statement("test-peer")

        reader = MagicMock(spec=flight.MetadataRecordBatchReader)
        writer = MagicMock()

        cmd = fs.CommandPreparedStatementQuery(prepared_statement_handle=handle.encode("utf-8"))
        # Should not raise — just returns early
        server.do_put_prepared_statement_query(ctx, cmd, reader, writer)


# ═══════════════════════════════════════════════════════════════════════════
# Coverage: do_put_statement_ingest with catalog qualifier
# ═══════════════════════════════════════════════════════════════════════════
class TestDoPutStatementIngestCatalog:
    """Cover catalog qualifier branch in do_put_statement_ingest."""

    @staticmethod
    def _make_reader(arrow_table: pa.Table):
        batches = arrow_table.to_batches()
        call_count = 0

        def read_chunk():
            nonlocal call_count
            if call_count < len(batches):
                result = MagicMock()
                result.data = batches[call_count]
                call_count += 1
                return result
            raise StopIteration

        reader = MagicMock(spec=flight.MetadataRecordBatchReader)
        reader.read_chunk = read_chunk
        reader.schema = arrow_table.schema
        return reader

    def test_ingest_with_catalog_qualifier(self, server, ctx):
        """Ingest with catalog set exercises the catalog parts of table quoting."""
        data = pa.table({"id": [1], "val": [42]})
        reader = self._make_reader(data)
        writer = MagicMock()
        cmd = fs.CommandStatementIngest(table="cat_test", schema="main", catalog="memory")
        server.do_put_statement_ingest(ctx, cmd, reader, writer)
        writer.write.assert_called_once()
        conn = server._get_session(ctx)
        result = _execute_query(conn, "SELECT * FROM cat_test")
        assert result.num_rows == 1

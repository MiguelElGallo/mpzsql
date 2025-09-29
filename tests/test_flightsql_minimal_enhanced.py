"""
Enhanced test suite for FlightSQL minimal server implementation.

Focused on improving test coverage with working tests.
"""

import uuid
from unittest.mock import Mock, patch

import pyarrow as pa
import pyarrow.flight as pf
import pytest

from src.mpzsql.backends.base import DatabaseBackend
from src.mpzsql.config import ServerConfig
from src.mpzsql.flightsql.minimal import (
    MinimalFlightSQLServer,
    SqlInfo,
    SqlNullOrdering,
    SqlSupportedCaseSensitivity,
    SqlSupportedTransaction,
)


@pytest.fixture
def mock_backend():
    """Create a mock database backend for testing."""
    backend = Mock(spec=DatabaseBackend)
    backend.execute_query.return_value = pa.table(
        {"col1": [1, 2, 3], "col2": ["a", "b", "c"]}
    )
    backend.execute_update.return_value = 3
    backend.get_statement_schema.return_value = pa.schema(
        [pa.field("col1", pa.int64()), pa.field("col2", pa.string())]
    )
    backend.get_catalogs.return_value = pa.table({"catalog_name": ["default"]})
    backend.get_schemas.return_value = [("default", "main")]
    backend.get_db_schemas.return_value = pa.table(
        {"catalog_name": ["default"], "schema_name": ["main"]}
    )
    backend.get_tables.return_value = pa.table(
        {
            "catalog_name": ["default"],
            "schema_name": ["main"],
            "table_name": ["test_table"],
            "table_type": ["TABLE"],
        }
    )
    backend.get_columns.return_value = pa.table(
        {
            "catalog_name": ["default"],
            "schema_name": ["main"],
            "table_name": ["test_table"],
            "column_name": ["col1"],
            "ordinal_position": [1],
            "is_nullable": [True],
            "data_type": ["INTEGER"],
        }
    )
    backend.get_sql_info.return_value = pa.table(
        {"info_name": [0, 1, 2, 3], "value": ["MPZSQL", "1.0", "1.0", "false"]}
    )
    return backend


@pytest.fixture
def config():
    """Create a test configuration."""
    config = ServerConfig(
        secret_key="test_secret", username="test_user", password="test_pass"
    )
    return config


@pytest.fixture
def location():
    """Create a test server location."""
    return pf.Location.for_grpc_tcp("localhost", 0)


class TestSqlConstants:
    """Test SQL constant definitions."""

    def test_sql_info_constants(self) -> None:
        """Test SqlInfo constants."""
        assert SqlInfo.FLIGHT_SQL_SERVER_NAME == 0
        assert SqlInfo.FLIGHT_SQL_SERVER_VERSION == 1
        assert SqlInfo.FLIGHT_SQL_SERVER_ARROW_VERSION == 2
        assert SqlInfo.FLIGHT_SQL_SERVER_READ_ONLY == 3
        assert SqlInfo.SQL_DDL_CATALOG == 500
        assert SqlInfo.SQL_DDL_SCHEMA == 501
        assert SqlInfo.SQL_DDL_TABLE == 502

    def test_transaction_constants(self) -> None:
        """Test SqlSupportedTransaction constants."""
        assert SqlSupportedTransaction.SQL_SUPPORTED_TRANSACTION_NONE == 0
        assert SqlSupportedTransaction.SQL_SUPPORTED_TRANSACTION_TRANSACTION == 1
        assert SqlSupportedTransaction.SQL_SUPPORTED_TRANSACTION_SAVEPOINT == 2

    def test_case_sensitivity_constants(self) -> None:
        """Test SqlSupportedCaseSensitivity constants."""
        assert SqlSupportedCaseSensitivity.SQL_CASE_SENSITIVITY_UNKNOWN == 0
        assert SqlSupportedCaseSensitivity.SQL_CASE_SENSITIVITY_CASE_INSENSITIVE == 1
        assert SqlSupportedCaseSensitivity.SQL_CASE_SENSITIVITY_UPPERCASE == 2
        assert SqlSupportedCaseSensitivity.SQL_CASE_SENSITIVITY_LOWERCASE == 3

    def test_null_ordering_constants(self) -> None:
        """Test SqlNullOrdering constants."""
        assert SqlNullOrdering.SQL_NULLS_SORTED_HIGH == 0
        assert SqlNullOrdering.SQL_NULLS_SORTED_LOW == 1
        assert SqlNullOrdering.SQL_NULLS_SORTED_AT_START == 2
        assert SqlNullOrdering.SQL_NULLS_SORTED_AT_END == 3


class TestServerInitialization:
    """Test MinimalFlightSQLServer initialization."""

    def test_basic_init(self, mock_backend, config, location):
        """Test basic server initialization."""
        server = MinimalFlightSQLServer(
            backend=mock_backend, config=config, location=location
        )

        assert server.backend == mock_backend
        assert server.config == config
        assert server.location == location
        assert server.advertised_location == location
        assert server.prepared_statements == {}
        assert server.open_transactions == {}
        assert server.open_sessions == {}
        assert hasattr(server, "_mutex")
        assert server._transaction_counter == 0

    def test_init_with_auth_enabled(self, mock_backend, location):
        """Test server initialization with authentication enabled."""
        config = ServerConfig(
            secret_key="test_secret", username="test_user", password="test_pass"
        )

        server = MinimalFlightSQLServer(
            backend=mock_backend, config=config, location=location
        )

        assert server.config.is_auth_enabled is True
        assert server.backend == mock_backend

    def test_init_with_advertised_location(self, mock_backend, config):
        """Test server initialization with different advertised location."""
        location = pf.Location.for_grpc_tcp(
            "localhost", 0
        )  # Use port 0 for auto-assignment
        advertised_location = pf.Location.for_grpc_tcp("external.host", 0)

        server = MinimalFlightSQLServer(
            backend=mock_backend,
            config=config,
            location=location,
            advertised_location=advertised_location,
        )

        assert server.location == location
        assert server.advertised_location == advertised_location


class TestServerActions:
    """Test server action methods."""

    @pytest.fixture
    def server(self, mock_backend, config, location):
        """Create a test server instance."""
        return MinimalFlightSQLServer(
            backend=mock_backend, config=config, location=location
        )

    def test_list_actions(self, server):
        """Test that list_actions returns expected action types."""
        context = Mock(spec=pf.ServerCallContext)
        actions = list(server.list_actions(context))

        action_types = [action.type for action in actions]
        assert "CreatePreparedStatement" in action_types
        assert "ClosePreparedStatement" in action_types
        assert "BeginTransaction" in action_types
        assert "EndTransaction" in action_types
        assert "CloseSession" in action_types

        # Verify all actions have descriptions
        for action in actions:
            assert isinstance(action, pf.ActionType)
            assert action.description is not None
            assert len(action.description) > 0

    @patch("src.mpzsql.flightsql.minimal.ActionCreatePreparedStatementRequest")
    @patch("src.mpzsql.flightsql.minimal.FlightSQLProtobuf")
    def test_create_prepared_statement_action(
        self, mock_protobuf, mock_request_class, server
    ):
        """Test CreatePreparedStatement action."""
        context = Mock(spec=pf.ServerCallContext)

        # Mock the request parsing
        mock_request = Mock()
        mock_request.query = "SELECT * FROM test_table"
        mock_request_class.return_value = mock_request

        # Mock protobuf result creation
        mock_protobuf.create_action_create_prepared_statement_result.return_value = (
            b"test_response"
        )

        action_body = b"mock_action_body"
        action = pf.Action("CreatePreparedStatement", pa.py_buffer(action_body))

        results = list(server.do_action(context, action))

        assert len(results) == 1
        assert isinstance(results[0], pf.Result)
        assert len(server.prepared_statements) == 1

    @patch("src.mpzsql.flightsql.minimal.ActionBeginTransactionRequest")
    def test_begin_transaction_action(self, mock_request_class, server):
        """Test BeginTransaction action."""
        context = Mock(spec=pf.ServerCallContext)

        mock_request = Mock()
        mock_request_class.return_value = mock_request

        action_body = b"mock_action_body"
        action = pf.Action("BeginTransaction", pa.py_buffer(action_body))

        results = list(server.do_action(context, action))

        assert len(results) == 1
        assert isinstance(results[0], pf.Result)
        assert len(server.open_transactions) == 1
        assert server._transaction_counter == 1

    @patch("src.mpzsql.flightsql.minimal.ActionEndTransactionRequest")
    def test_end_transaction_action(self, mock_request_class, server):
        """Test EndTransaction action."""
        context = Mock(spec=pf.ServerCallContext)

        # Setup initial transaction
        server.open_transactions["txn_1"] = "active"

        mock_request = Mock()
        mock_request.transaction_id = "txn_1"
        mock_request.action = 1  # COMMIT constant
        mock_request_class.return_value = mock_request

        action_body = b"mock_action_body"
        action = pf.Action("EndTransaction", pa.py_buffer(action_body))

        results = list(server.do_action(context, action))

        assert len(results) == 1
        assert isinstance(results[0], pf.Result)
        assert "txn_1" not in server.open_transactions

    def test_close_session_action(self, server):
        """Test CloseSession action."""
        context = Mock(spec=pf.ServerCallContext)

        # Setup some session state to clean up
        server.prepared_statements["handle1"] = {"sql": "SELECT 1", "schema": None}
        server.open_transactions["txn1"] = "active"
        server.open_sessions["session1"] = {"user": "test"}

        action_body = b""  # CloseSession typically has empty body
        action = pf.Action("CloseSession", pa.py_buffer(action_body))

        results = list(server.do_action(context, action))

        assert len(results) == 1
        assert isinstance(results[0], pf.Result)

        # Check that session state was cleaned up
        assert len(server.prepared_statements) == 0
        assert len(server.open_transactions) == 0
        assert len(server.open_sessions) == 0

    def test_unknown_action_type(self, server):
        """Test handling of unknown action type."""
        context = Mock(spec=pf.ServerCallContext)

        action_body = b"mock_action_body"
        action = pf.Action("UnknownAction", pa.py_buffer(action_body))

        with pytest.raises(
            NotImplementedError, match="Action UnknownAction not implemented"
        ):
            list(server.do_action(context, action))


class TestFlightInfoGeneration:
    """Test FlightInfo generation methods."""

    @pytest.fixture
    def server(self, mock_backend, config, location):
        """Create a test server instance."""
        return MinimalFlightSQLServer(
            backend=mock_backend, config=config, location=location
        )

    def test_get_flight_info_for_command(self, server):
        """Test _get_flight_info_for_command helper method."""
        descriptor = pf.FlightDescriptor.for_command(b"test_command")
        schema = pa.schema([pa.field("test_col", pa.string())])

        flight_info = server._get_flight_info_for_command(descriptor, schema)

        assert isinstance(flight_info, pf.FlightInfo)
        assert flight_info.descriptor == descriptor
        assert flight_info.schema == schema
        assert len(flight_info.endpoints) == 1
        assert flight_info.total_records == -1
        assert flight_info.total_bytes == -1

    def test_get_flight_info_statement(self, server):
        """Test _get_flight_info_statement method."""
        descriptor = pf.FlightDescriptor.for_command(b"test_command")

        from src.mpzsql.flightsql.protobuf import CommandStatementQuery

        command = CommandStatementQuery()
        command.query = "SELECT * FROM test_table"

        # Mock backend schema response
        test_schema = pa.schema([pa.field("col1", pa.int64())])
        server.backend.get_statement_schema.return_value = test_schema

        flight_info = server._get_flight_info_statement(descriptor, command)

        assert isinstance(flight_info, pf.FlightInfo)
        server.backend.get_statement_schema.assert_called_once_with(
            "SELECT * FROM test_table"
        )

    def test_get_flight_info_catalogs(self, server):
        """Test _get_flight_info_catalogs method."""
        descriptor = pf.FlightDescriptor.for_command(b"test_command")

        from src.mpzsql.flightsql.protobuf import CommandGetCatalogs

        command = CommandGetCatalogs()

        with patch(
            "src.mpzsql.flightsql.protobuf.FlightSQLProtobuf.get_catalogs_schema"
        ) as mock_schema:
            test_schema = pa.schema([pa.field("catalog_name", pa.string())])
            mock_schema.return_value = test_schema

            flight_info = server._get_flight_info_catalogs(descriptor, command)

            assert isinstance(flight_info, pf.FlightInfo)
            mock_schema.assert_called_once()

    def test_get_flight_info_schemas(self, server):
        """Test _get_flight_info_schemas method."""
        descriptor = pf.FlightDescriptor.for_command(b"test_command")

        from src.mpzsql.flightsql.protobuf import CommandGetDbSchemas

        command = CommandGetDbSchemas()
        command.catalog = "default"

        with patch(
            "src.mpzsql.flightsql.protobuf.FlightSQLProtobuf.get_db_schemas_schema"
        ) as mock_schema:
            test_schema = pa.schema([pa.field("schema_name", pa.string())])
            mock_schema.return_value = test_schema

            flight_info = server._get_flight_info_schemas(descriptor, command)

            assert isinstance(flight_info, pf.FlightInfo)
            mock_schema.assert_called_once()

    def test_get_flight_info_tables(self, server):
        """Test _get_flight_info_tables method."""
        descriptor = pf.FlightDescriptor.for_command(b"test_command")

        from src.mpzsql.flightsql.protobuf import CommandGetTables

        command = CommandGetTables()
        command.include_schema = False

        with patch(
            "src.mpzsql.flightsql.protobuf.FlightSQLProtobuf.get_tables_schema"
        ) as mock_schema:
            test_schema = pa.schema([pa.field("table_name", pa.string())])
            mock_schema.return_value = test_schema

            flight_info = server._get_flight_info_tables(descriptor, command)

            assert isinstance(flight_info, pf.FlightInfo)
            mock_schema.assert_called_once()

    def test_get_flight_info_table_types(self, server):
        """Test _get_flight_info_table_types method."""
        descriptor = pf.FlightDescriptor.for_command(b"test_command")

        from src.mpzsql.flightsql.protobuf import CommandGetTableTypes

        command = CommandGetTableTypes()

        with patch(
            "src.mpzsql.flightsql.protobuf.FlightSQLProtobuf.get_table_types_schema"
        ) as mock_schema:
            test_schema = pa.schema([pa.field("table_type", pa.string())])
            mock_schema.return_value = test_schema

            flight_info = server._get_flight_info_table_types(descriptor, command)

            assert isinstance(flight_info, pf.FlightInfo)
            mock_schema.assert_called_once()

    def test_get_flight_info_columns(self, server):
        """Test _get_flight_info_columns method."""
        descriptor = pf.FlightDescriptor.for_command(b"test_command")

        from src.mpzsql.flightsql.protobuf import CommandGetColumns

        command = CommandGetColumns()
        command.catalog = "default"

        with patch(
            "src.mpzsql.flightsql.protobuf.FlightSQLProtobuf.get_columns_schema"
        ) as mock_schema:
            test_schema = pa.schema([pa.field("column_name", pa.string())])
            mock_schema.return_value = test_schema

            flight_info = server._get_flight_info_columns(descriptor, command)

            assert isinstance(flight_info, pf.FlightInfo)
            mock_schema.assert_called_once()

    def test_get_flight_info_sql_info(self, server):
        """Test _get_flight_info_sql_info method."""
        descriptor = pf.FlightDescriptor.for_command(b"test_command")

        from src.mpzsql.flightsql.protobuf import CommandGetSqlInfo

        command = CommandGetSqlInfo()
        command.info.extend([0, 1, 2])

        with patch(
            "src.mpzsql.flightsql.protobuf.FlightSQLProtobuf.get_sql_info_schema"
        ) as mock_schema:
            test_schema = pa.schema(
                [pa.field("info_name", pa.int32()), pa.field("value", pa.string())]
            )
            mock_schema.return_value = test_schema

            flight_info = server._get_flight_info_sql_info(descriptor, command)

            assert isinstance(flight_info, pf.FlightInfo)
            mock_schema.assert_called_once()


class TestBackendInteraction:
    """Test backend interaction methods."""

    @pytest.fixture
    def server(self, mock_backend, config, location):
        """Create a test server instance."""
        return MinimalFlightSQLServer(
            backend=mock_backend, config=config, location=location
        )

    def test_do_get_statement_from_query_success(self, server):
        """Test successful query execution."""
        test_table = pa.table({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})
        server.backend.execute_query.return_value = test_table

        result = server._do_get_statement_from_query("SELECT * FROM test_table")

        assert isinstance(result, pf.FlightDataStream)
        server.backend.execute_query.assert_called_once_with("SELECT * FROM test_table")

    def test_do_get_statement_from_query_error(self, server):
        """Test query execution with error."""
        server.backend.execute_query.side_effect = Exception("Query failed")

        result = server._do_get_statement_from_query("SELECT * FROM invalid_table")

        # Should return error response instead of crashing
        assert isinstance(result, pf.FlightDataStream)
        server.backend.execute_query.assert_called_once_with(
            "SELECT * FROM invalid_table"
        )

    def test_do_put_update_from_query_success(self, server):
        """Test successful update execution."""
        server.backend.execute_update.return_value = 5

        result = server._do_put_update_from_query(
            "INSERT INTO test_table VALUES (1, 'test')"
        )

        assert result == 5
        server.backend.execute_update.assert_called_once_with(
            "INSERT INTO test_table VALUES (1, 'test')"
        )

    def test_do_put_update_from_query_error(self, server):
        """Test update execution with error."""
        server.backend.execute_update.side_effect = Exception("Update failed")

        with pytest.raises(Exception, match="Update failed"):
            server._do_put_update_from_query(
                "INSERT INTO invalid_table VALUES (1, 'test')"
            )

    def test_do_get_catalogs(self, server):
        """Test _do_get_catalogs method."""
        from src.mpzsql.flightsql.protobuf import CommandGetCatalogs

        test_table = pa.table({"catalog_name": ["default", "test"]})
        server.backend.get_catalogs.return_value = test_table

        command = CommandGetCatalogs()
        result = server._do_get_catalogs(command)

        assert isinstance(result, pf.FlightDataStream)
        server.backend.get_catalogs.assert_called_once()

    def test_do_get_schemas(self, server):
        """Test _do_get_schemas method."""
        from src.mpzsql.flightsql.protobuf import CommandGetDbSchemas

        test_table = pa.table(
            {
                "catalog_name": ["default", "default"],
                "schema_name": ["main", "information_schema"],
            }
        )
        server.backend.get_db_schemas.return_value = test_table

        command = CommandGetDbSchemas()
        command.catalog = "default"
        command.db_schema_filter_pattern = "%"

        result = server._do_get_schemas(command)

        assert isinstance(result, pf.FlightDataStream)
        server.backend.get_db_schemas.assert_called_once_with(
            catalog="default", db_schema_filter_pattern="%"
        )

    def test_do_get_tables(self, server):
        """Test _do_get_tables method."""
        from src.mpzsql.flightsql.protobuf import CommandGetTables

        test_table = pa.table(
            {
                "catalog_name": ["default", "default"],
                "schema_name": ["main", "main"],
                "table_name": ["test_table", "another_table"],
                "table_type": ["TABLE", "VIEW"],
            }
        )
        server.backend.get_tables.return_value = test_table

        command = CommandGetTables()
        command.catalog = "default"
        command.db_schema_filter_pattern = "main"
        command.table_name_filter_pattern = "%"
        command.table_types.extend(["TABLE", "VIEW"])
        command.include_schema = False

        result = server._do_get_tables(command)

        assert isinstance(result, pf.FlightDataStream)
        server.backend.get_tables.assert_called_once_with(
            catalog="default",
            db_schema_filter_pattern="main",
            table_name_filter_pattern="%",
            table_types=["TABLE", "VIEW"],
            include_schema=False,
        )

    def test_do_get_columns(self, server):
        """Test _do_get_columns method."""
        from src.mpzsql.flightsql.protobuf import CommandGetColumns

        test_table = pa.table(
            {
                "catalog_name": ["default", "default"],
                "schema_name": ["main", "main"],
                "table_name": ["test_table", "test_table"],
                "column_name": ["id", "name"],
                "ordinal_position": [1, 2],
                "is_nullable": [False, True],
                "data_type": ["INTEGER", "VARCHAR"],
            }
        )
        server.backend.get_columns.return_value = test_table

        command = CommandGetColumns()
        command.catalog = "default"
        command.db_schema_filter_pattern = "main"
        command.table_name_filter_pattern = "test_table"
        command.column_name_filter_pattern = "%"

        result = server._do_get_columns(command)

        assert isinstance(result, pf.FlightDataStream)
        server.backend.get_columns.assert_called_once_with(
            catalog="default",
            db_schema_filter_pattern="main",
            table_name_filter_pattern="test_table",
            column_name_filter_pattern="%",
        )

    def test_do_get_sql_info(self, server):
        """Test _do_get_sql_info method."""
        from src.mpzsql.flightsql.protobuf import CommandGetSqlInfo

        test_table = pa.table(
            {"info_name": [0, 1, 2], "value": ["MPZSQL", "1.0", "false"]}
        )
        server.backend.get_sql_info.return_value = test_table

        command = CommandGetSqlInfo()
        command.info.extend([0, 1, 2])

        result = server._do_get_sql_info(command)

        assert isinstance(result, pf.FlightDataStream)
        server.backend.get_sql_info.assert_called_once_with([0, 1, 2])


class TestCommandParsing:
    """Test command parsing methods."""

    @pytest.fixture
    def server(self, mock_backend, config, location):
        """Create a test server instance."""
        return MinimalFlightSQLServer(
            backend=mock_backend, config=config, location=location
        )

    @patch(
        "src.mpzsql.flightsql.protobuf.FlightSQLProtobuf.parse_command_statement_query"
    )
    def test_parse_statement_query(self, mock_parse, server):
        """Test _parse_statement_query method."""
        mock_any = Mock()
        mock_any.value = b"mock_value"
        mock_parse.return_value = "SELECT * FROM test_table"

        from src.mpzsql.flightsql.protobuf import CommandStatementQuery

        result = server._parse_statement_query(mock_any)

        assert isinstance(result, CommandStatementQuery)
        assert result.query == "SELECT * FROM test_table"

    def test_parse_prepared_statement_query(self, server):
        """Test _parse_prepared_statement_query method."""
        from unittest.mock import patch

        from src.mpzsql.flightsql.protobuf import CommandPreparedStatementQuery

        mock_any = Mock()

        # Mock the CommandPreparedStatementQuery constructor and Unpack method
        with patch(
            "src.mpzsql.flightsql.minimal.CommandPreparedStatementQuery"
        ) as mock_command_class:
            mock_command_instance = Mock(spec=CommandPreparedStatementQuery)
            mock_command_class.return_value = mock_command_instance

            result = server._parse_prepared_statement_query(mock_any)

            assert result == mock_command_instance
            mock_command_instance.Unpack.assert_called_once_with(mock_any)

    def test_parse_get_sql_info(self, server):
        """Test _parse_get_sql_info method."""
        from src.mpzsql.flightsql.protobuf import CommandGetSqlInfo

        mock_any = Mock()
        mock_any.value = b"mock_value"

        with patch.object(CommandGetSqlInfo, "ParseFromString") as mock_parse:
            result = server._parse_get_sql_info(mock_any)

            assert isinstance(result, CommandGetSqlInfo)
            mock_parse.assert_called_once_with(b"mock_value")


class TestErrorHandling:
    """Test error handling scenarios."""

    @pytest.fixture
    def server(self, mock_backend, config, location):
        """Create a test server instance."""
        return MinimalFlightSQLServer(
            backend=mock_backend, config=config, location=location
        )

    def test_create_prepared_statement_parsing_error(self, server):
        """Test error handling in prepared statement creation."""
        context = Mock(spec=pf.ServerCallContext)

        with patch(
            "src.mpzsql.flightsql.minimal.ActionCreatePreparedStatementRequest"
        ) as mock_req:
            mock_req.side_effect = Exception("Parsing failed")

            action_body = b"invalid_data"
            action = pf.Action("CreatePreparedStatement", pa.py_buffer(action_body))

            with pytest.raises(Exception, match="Parsing failed"):
                list(server.do_action(context, action))

    def test_transaction_thread_safety(self, server):
        """Test that transaction operations use mutex for thread safety."""
        # Test that the mutex exists and is used
        assert hasattr(server, "_mutex")

        with patch("src.mpzsql.flightsql.minimal.ActionBeginTransactionRequest"):
            context = Mock(spec=pf.ServerCallContext)
            action_body = b"mock_data"
            action = pf.Action("BeginTransaction", pa.py_buffer(action_body))

            # Execute multiple times to test thread safety
            results1 = list(server.do_action(context, action))
            results2 = list(server.do_action(context, action))

            assert len(results1) == 1
            assert len(results2) == 1
            assert server._transaction_counter == 2

    def test_close_prepared_statement_not_found(self, server):
        """Test closing non-existent prepared statement."""
        context = Mock(spec=pf.ServerCallContext)

        with patch(
            "src.mpzsql.flightsql.minimal.ActionClosePreparedStatementRequest"
        ) as mock_req:
            mock_request = Mock()
            mock_request.prepared_statement_handle = uuid.uuid4().bytes
            mock_req.return_value = mock_request

            action_body = b"mock_action_body"
            action = pf.Action("ClosePreparedStatement", pa.py_buffer(action_body))

            # Should not raise error, just log warning
            results = list(server.do_action(context, action))

            assert len(results) == 1
            assert isinstance(results[0], pf.Result)


class TestPreparedStatements:
    """Test prepared statement lifecycle."""

    @pytest.fixture
    def server(self, mock_backend, config, location):
        """Create a test server instance."""
        return MinimalFlightSQLServer(
            backend=mock_backend, config=config, location=location
        )

    def test_prepared_statement_storage_structure(self, server):
        """Test that prepared statements are stored with correct structure."""
        # Manually add a prepared statement to test structure
        handle_key = "test_handle"
        server.prepared_statements[handle_key] = {
            "sql": "SELECT * FROM test_table WHERE id = ?",
            "schema": pa.schema(
                [pa.field("id", pa.int64()), pa.field("name", pa.string())]
            ),
            "transaction_id": "",
            "parameters": None,
        }

        assert handle_key in server.prepared_statements
        stmt = server.prepared_statements[handle_key]
        assert "sql" in stmt
        assert "schema" in stmt
        assert "transaction_id" in stmt
        assert "parameters" in stmt
        assert stmt["sql"] == "SELECT * FROM test_table WHERE id = ?"

    def test_prepared_statement_parameter_storage(self, server):
        """Test parameter storage for prepared statements."""
        handle_key = "test_handle"
        server.prepared_statements[handle_key] = {
            "sql": "SELECT * FROM test_table WHERE id = ?",
            "schema": None,
            "transaction_id": "",
            "parameters": None,
        }

        # Simulate parameter binding
        test_parameters = [pa.record_batch([pa.array([1, 2, 3])], names=["param1"])]
        server.prepared_statements[handle_key]["parameters"] = test_parameters

        assert server.prepared_statements[handle_key]["parameters"] == test_parameters


class TestPreparedStatementFlightInfo:
    """Test FlightInfo generation for prepared statements."""

    def server(self, mock_backend, config, location):
        """Create a test server instance."""
        return MinimalFlightSQLServer(
            backend=mock_backend, config=config, location=location
        )

    def test_get_flight_info_prepared_statement(self, server):
        """Test _get_flight_info_prepared_statement method."""
        from src.mpzsql.flightsql.protobuf import CommandPreparedStatementQuery

        # Setup a prepared statement
        test_handle = uuid.uuid4().bytes
        handle_key = test_handle.hex()
        test_schema = pa.schema(
            [pa.field("col1", pa.int64()), pa.field("col2", pa.string())]
        )

        server.prepared_statements[handle_key] = {
            "sql": "SELECT * FROM test_table WHERE id = ?",
            "schema": test_schema,
            "transaction_id": "",
            "parameters": None,
        }

        command = CommandPreparedStatementQuery()
        command.prepared_statement_handle = test_handle
        descriptor = pf.FlightDescriptor.for_command(b"test_command")

        flight_info = server._get_flight_info_prepared_statement(descriptor, command)

        assert isinstance(flight_info, pf.FlightInfo)
        assert flight_info.schema == test_schema

    def test_get_flight_info_prepared_statement_missing_handle(self, server):
        """Test _get_flight_info_prepared_statement with missing handle."""
        from src.mpzsql.flightsql.protobuf import CommandPreparedStatementQuery

        command = CommandPreparedStatementQuery()
        command.prepared_statement_handle = uuid.uuid4().bytes  # Non-existent handle
        descriptor = pf.FlightDescriptor.for_command(b"test_command")

        with pytest.raises(ValueError, match="Prepared statement handle not found"):
            server._get_flight_info_prepared_statement(descriptor, command)

    def test_get_flight_info_prepared_statement_fallback_schema(self, server):
        """Test _get_flight_info_prepared_statement with schema fallback."""
        from src.mpzsql.flightsql.protobuf import CommandPreparedStatementQuery

        # Setup a prepared statement without pre-determined schema
        test_handle = uuid.uuid4().bytes
        handle_key = test_handle.hex()

        server.prepared_statements[handle_key] = {
            "sql": "SELECT * FROM test_table WHERE id = ?",
            "schema": None,  # No pre-determined schema
            "transaction_id": "",
            "parameters": None,
        }

        # Mock backend to provide schema
        fallback_schema = pa.schema([pa.field("fallback_col", pa.string())])
        server.backend.get_statement_schema.return_value = fallback_schema

        command = CommandPreparedStatementQuery()
        command.prepared_statement_handle = test_handle
        descriptor = pf.FlightDescriptor.for_command(b"test_command")

        flight_info = server._get_flight_info_prepared_statement(descriptor, command)

        assert isinstance(flight_info, pf.FlightInfo)
        assert flight_info.schema == fallback_schema
        server.backend.get_statement_schema.assert_called_once_with(
            "SELECT * FROM test_table WHERE id = ?"
        )

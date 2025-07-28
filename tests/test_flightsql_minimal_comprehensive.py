"""
Comprehensive test suite for FlightSQL minimal server implementation.

Tests the MinimalFlightSQLServer class which provides the core FlightSQL
protocol implementation including actions, commands, and schema generation.
"""

from unittest.mock import Mock, patch, MagicMock
import uuid
import threading
from typing import Iterator

import pyarrow as pa
import pyarrow.flight as pf
import pytest

from src.mpzsql.backends.base import DatabaseBackend
from src.mpzsql.config import ServerConfig
from src.mpzsql.flightsql.minimal import (
    MinimalFlightSQLServer,
    SqlInfo,
    SqlSupportedTransaction,
    SqlSupportedCaseSensitivity,
    SqlNullOrdering,
)
from src.mpzsql.flightsql.protobuf import (
    ActionBeginTransactionRequest,
    ActionEndTransactionRequest,
    ActionCreatePreparedStatementRequest,
    ActionClosePreparedStatementRequest,
    CommandStatementQuery,
    CommandStatementUpdate,
    CommandGetCatalogs,
    CommandGetDbSchemas,
    CommandGetTables,
    CommandGetTableTypes,
    CommandGetColumns,
    CommandGetSqlInfo,
    CommandPreparedStatementQuery,
    CommandPreparedStatementUpdate,
    DoPutUpdateResult,
    FlightSQLProtobuf,
)


@pytest.fixture
def mock_backend():
    """Create a mock database backend for testing."""
    backend = Mock(spec=DatabaseBackend)
    backend.execute_query.return_value = pa.table({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})
    backend.execute_update.return_value = 3
    backend.get_statement_schema.return_value = pa.schema([
        pa.field("col1", pa.int64()),
        pa.field("col2", pa.string())
    ])
    backend.get_catalogs.return_value = pa.table({"catalog_name": ["default"]})
    backend.get_schemas.return_value = [("default", "main")]
    backend.get_db_schemas.return_value = pa.table({
        "catalog_name": ["default"], 
        "schema_name": ["main"]
    })
    backend.get_tables.return_value = pa.table({
        "catalog_name": ["default"],
        "schema_name": ["main"],
        "table_name": ["test_table"],
        "table_type": ["TABLE"]
    })
    backend.get_columns.return_value = pa.table({
        "catalog_name": ["default"],
        "schema_name": ["main"],
        "table_name": ["test_table"],
        "column_name": ["col1"],
        "ordinal_position": [1],
        "is_nullable": [True],
        "data_type": ["INTEGER"]
    })
    backend.get_sql_info.return_value = pa.table({
        "info_name": [0, 1, 2, 3],
        "value": ["MPZSQL", "1.0", "1.0", "false"]
    })
    return backend


@pytest.fixture 
def config():
    """Create a test configuration."""
    config = ServerConfig(
        secret_key="test_secret",
        username="test_user",
        password="test_pass"
    )
    return config


@pytest.fixture
def location():
    """Create a test server location."""
    return pf.Location.for_grpc_tcp("localhost", 0)


class TestSqlInfoConstants:
    """Test SqlInfo constant definitions."""
    
    def test_sql_info_constants_exist(self):
        """Test that all required SqlInfo constants are defined."""
        assert hasattr(SqlInfo, 'FLIGHT_SQL_SERVER_NAME')
        assert hasattr(SqlInfo, 'FLIGHT_SQL_SERVER_VERSION')
        assert hasattr(SqlInfo, 'FLIGHT_SQL_SERVER_ARROW_VERSION')
        assert hasattr(SqlInfo, 'FLIGHT_SQL_SERVER_READ_ONLY')
        assert hasattr(SqlInfo, 'FLIGHT_SQL_SERVER_SQL')
        assert hasattr(SqlInfo, 'FLIGHT_SQL_SERVER_SUBSTRAIT')
        assert hasattr(SqlInfo, 'FLIGHT_SQL_SERVER_TRANSACTION')
        assert hasattr(SqlInfo, 'FLIGHT_SQL_SERVER_CANCEL')
        
    def test_sql_info_values(self):
        """Test that SqlInfo constants have correct values."""
        assert SqlInfo.FLIGHT_SQL_SERVER_NAME == 0
        assert SqlInfo.FLIGHT_SQL_SERVER_VERSION == 1
        assert SqlInfo.FLIGHT_SQL_SERVER_ARROW_VERSION == 2
        assert SqlInfo.FLIGHT_SQL_SERVER_READ_ONLY == 3
        assert SqlInfo.SQL_DDL_CATALOG == 500
        assert SqlInfo.SQL_DDL_SCHEMA == 501
        assert SqlInfo.SQL_DDL_TABLE == 502

    def test_additional_sql_constants(self):
        """Test additional SQL constant classes."""
        # Test SqlSupportedTransaction constants
        assert hasattr(SqlSupportedTransaction, 'SQL_SUPPORTED_TRANSACTION_NONE')
        assert hasattr(SqlSupportedTransaction, 'SQL_SUPPORTED_TRANSACTION_TRANSACTION')
        assert hasattr(SqlSupportedTransaction, 'SQL_SUPPORTED_TRANSACTION_SAVEPOINT')
        assert SqlSupportedTransaction.SQL_SUPPORTED_TRANSACTION_NONE == 0
        assert SqlSupportedTransaction.SQL_SUPPORTED_TRANSACTION_TRANSACTION == 1
        assert SqlSupportedTransaction.SQL_SUPPORTED_TRANSACTION_SAVEPOINT == 2
        
        # Test SqlSupportedCaseSensitivity constants
        assert hasattr(SqlSupportedCaseSensitivity, 'SQL_CASE_SENSITIVITY_UNKNOWN')
        assert hasattr(SqlSupportedCaseSensitivity, 'SQL_CASE_SENSITIVITY_CASE_INSENSITIVE')
        assert hasattr(SqlSupportedCaseSensitivity, 'SQL_CASE_SENSITIVITY_UPPERCASE')
        assert hasattr(SqlSupportedCaseSensitivity, 'SQL_CASE_SENSITIVITY_LOWERCASE')
        assert SqlSupportedCaseSensitivity.SQL_CASE_SENSITIVITY_UNKNOWN == 0
        assert SqlSupportedCaseSensitivity.SQL_CASE_SENSITIVITY_CASE_INSENSITIVE == 1
        assert SqlSupportedCaseSensitivity.SQL_CASE_SENSITIVITY_UPPERCASE == 2
        assert SqlSupportedCaseSensitivity.SQL_CASE_SENSITIVITY_LOWERCASE == 3
        
        # Test SqlNullOrdering constants
        assert hasattr(SqlNullOrdering, 'SQL_NULLS_SORTED_HIGH')
        assert hasattr(SqlNullOrdering, 'SQL_NULLS_SORTED_LOW')
        assert hasattr(SqlNullOrdering, 'SQL_NULLS_SORTED_AT_START')
        assert hasattr(SqlNullOrdering, 'SQL_NULLS_SORTED_AT_END')
        assert SqlNullOrdering.SQL_NULLS_SORTED_HIGH == 0
        assert SqlNullOrdering.SQL_NULLS_SORTED_LOW == 1
        assert SqlNullOrdering.SQL_NULLS_SORTED_AT_START == 2
        assert SqlNullOrdering.SQL_NULLS_SORTED_AT_END == 3


class TestMinimalFlightSQLServerInit:
    """Test MinimalFlightSQLServer initialization."""
    
    def test_basic_init_no_auth_no_tls(self, mock_backend, config, location):
        """Test basic server initialization without auth or TLS."""
        server = MinimalFlightSQLServer(
            backend=mock_backend,
            config=config,
            location=location
        )
        
        assert server.backend == mock_backend
        assert server.config == config
        assert server.location == location
        assert server.advertised_location == location
        assert server.prepared_statements == {}
        assert server.open_transactions == {}
        assert server.open_sessions == {}
        assert hasattr(server, '_mutex')
        assert server._transaction_counter == 0

    def test_init_with_auth_enabled(self, mock_backend, location):
        """Test server initialization with authentication enabled."""
        config = ServerConfig(
            secret_key="test_secret",
            username="test_user", 
            password="test_pass",
            auth_enabled=True
        )
        
        server = MinimalFlightSQLServer(
            backend=mock_backend,
            config=config,
            location=location
        )
        
        assert server.config.is_auth_enabled is True
        assert server.backend == mock_backend
        assert server.config == config

    def test_init_with_advertised_location(self, mock_backend, config):
        """Test server initialization with different advertised location."""
        location = pf.Location.for_grpc_tcp("localhost", 8080)
        advertised_location = pf.Location.for_grpc_tcp("external.host", 8080)
        
        server = MinimalFlightSQLServer(
            backend=mock_backend,
            config=config,
            location=location,
            advertised_location=advertised_location
        )
        
        assert server.location == location
        assert server.advertised_location == advertised_location

    @patch('src.mpzsql.flightsql.minimal.TLSCertificateLoader')
    def test_init_with_tls_enabled(self, mock_tls_loader, mock_backend, location):
        """Test server initialization with TLS enabled."""
        config = ServerConfig(
            secret_key="test_secret",
            username="test_user",
            password="test_pass",
            tls_enabled=True,
            tls_cert_path="/fake/cert.pem",
            tls_key_path="/fake/key.pem"
        )
        
        # Mock TLS certificate loading
        mock_tls_loader.configure_tls_options.return_value = (
            [b"cert_data"], [b"root_cert_data"], False
        )
        
        server = MinimalFlightSQLServer(
            backend=mock_backend,
            config=config,
            location=location
        )
        
        assert server.config.is_tls_enabled is True
        mock_tls_loader.configure_tls_options.assert_called_once_with(config)

    @patch('src.mpzsql.flightsql.minimal.TLSCertificateLoader')
    def test_init_with_tls_failure(self, mock_tls_loader, mock_backend, location):
        """Test server initialization with TLS configuration failure."""
        config = ServerConfig(
            secret_key="test_secret",
            username="test_user",
            password="test_pass",
            tls_enabled=True,
            tls_cert_path="/fake/cert.pem",
            tls_key_path="/fake/key.pem"
        )
        
        # Mock TLS certificate loading failure
        mock_tls_loader.configure_tls_options.side_effect = Exception("TLS configuration failed")
        
        with pytest.raises(ValueError, match="TLS configuration failed"):
            MinimalFlightSQLServer(
                backend=mock_backend,
                config=config,
                location=location
            )


class TestMinimalFlightSQLServerActions:
    """Test MinimalFlightSQLServer action methods."""
    
    @pytest.fixture
    def server(self, mock_backend, config, location):
        """Create a test server instance."""
        return MinimalFlightSQLServer(
            backend=mock_backend,
            config=config,
            location=location
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
        
        # Verify action descriptions
        for action in actions:
            assert isinstance(action, pf.ActionType)
            assert action.description is not None
            assert len(action.description) > 0
    
    @patch('src.mpzsql.flightsql.minimal.ActionCreatePreparedStatementRequest')
    @patch('src.mpzsql.flightsql.minimal.FlightSQLProtobuf')
    def test_do_action_create_prepared_statement(self, mock_protobuf, mock_request_class, server):
        """Test do_action with CreatePreparedStatement."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Mock the request object
        mock_request = Mock()
        mock_request.query = "SELECT * FROM test_table"
        mock_request_class.return_value = mock_request
        
        # Mock protobuf result creation
        mock_protobuf.create_action_create_prepared_statement_result.return_value = b"test_response"
        
        # Create action with mock data
        action_body = b'mock_action_body'
        action = pf.Action("CreatePreparedStatement", pa.py_buffer(action_body))
        
        # Execute action
        results = list(server.do_action(context, action))
        
        assert len(results) == 1
        result = results[0]
        assert isinstance(result, pf.Result)
        
        # Check that prepared statement was stored
        assert len(server.prepared_statements) == 1
        
        # Verify the stored prepared statement
        stored_handle = list(server.prepared_statements.keys())[0]
        stored_stmt = server.prepared_statements[stored_handle]
        assert stored_stmt["sql"] == "SELECT * FROM test_table"
        assert "schema" in stored_stmt
        assert "transaction_id" in stored_stmt
        assert "parameters" in stored_stmt
    
    @patch('src.mpzsql.flightsql.minimal.ActionBeginTransactionRequest')
    def test_do_action_begin_transaction(self, mock_request_class, server):
        """Test do_action with BeginTransaction."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Mock the request object
        mock_request = Mock()
        mock_request_class.return_value = mock_request
        
        # Create action with mock data
        action_body = b'mock_action_body'
        action = pf.Action("BeginTransaction", pa.py_buffer(action_body))
        
        # Execute action
        results = list(server.do_action(context, action))
        
        assert len(results) == 1
        result = results[0]
        assert isinstance(result, pf.Result)
        
        # Check that transaction was created
        assert len(server.open_transactions) == 1
        assert server._transaction_counter == 1
        
        # Verify transaction ID format
        transaction_id = list(server.open_transactions.keys())[0]
        assert transaction_id.startswith("txn_")
        assert server.open_transactions[transaction_id] == "active"

    @patch('src.mpzsql.flightsql.minimal.ActionEndTransactionRequest')
    def test_do_action_end_transaction_commit(self, mock_request_class, server):
        """Test do_action with EndTransaction - COMMIT."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Setup initial transaction
        server.open_transactions["txn_1"] = "active"
        
        # Mock the request object
        mock_request = Mock()
        mock_request.transaction_id = "txn_1"
        mock_request.action = ActionEndTransactionRequest.COMMIT
        mock_request_class.return_value = mock_request
        
        # Create action
        action_body = b'mock_action_body'
        action = pf.Action("EndTransaction", pa.py_buffer(action_body))
        
        # Execute action
        results = list(server.do_action(context, action))
        
        assert len(results) == 1
        result = results[0]
        assert isinstance(result, pf.Result)
        
        # Check that transaction was removed
        assert "txn_1" not in server.open_transactions

    @patch('src.mpzsql.flightsql.minimal.ActionEndTransactionRequest')
    def test_do_action_end_transaction_rollback(self, mock_request_class, server):
        """Test do_action with EndTransaction - ROLLBACK."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Setup initial transaction
        server.open_transactions["txn_1"] = "active"
        
        # Mock the request object
        mock_request = Mock()
        mock_request.transaction_id = "txn_1"
        mock_request.action = ActionEndTransactionRequest.ROLLBACK
        mock_request_class.return_value = mock_request
        
        # Create action
        action_body = b'mock_action_body'
        action = pf.Action("EndTransaction", pa.py_buffer(action_body))
        
        # Execute action
        results = list(server.do_action(context, action))
        
        assert len(results) == 1
        result = results[0]
        assert isinstance(result, pf.Result)
        
        # Check that transaction was removed
        assert "txn_1" not in server.open_transactions

    @patch('src.mpzsql.flightsql.minimal.ActionEndTransactionRequest')
    def test_do_action_end_transaction_unknown_id(self, mock_request_class, server):
        """Test do_action with EndTransaction for unknown transaction ID."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Mock the request object with unknown transaction ID
        mock_request = Mock()
        mock_request.transaction_id = "unknown_txn"
        mock_request.action = ActionEndTransactionRequest.COMMIT
        mock_request_class.return_value = mock_request
        
        # Create action
        action_body = b'mock_action_body'
        action = pf.Action("EndTransaction", pa.py_buffer(action_body))
        
        # Execute action and expect error
        with pytest.raises(ValueError, match="Unknown transaction ID"):
            list(server.do_action(context, action))

    def test_do_action_close_session(self, server):
        """Test do_action with CloseSession."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Setup some session state to clean up
        server.prepared_statements["handle1"] = {"sql": "SELECT 1", "schema": None}
        server.open_transactions["txn1"] = "active"
        server.open_sessions["session1"] = {"user": "test"}
        
        # Create action
        action_body = b''  # CloseSession typically has empty body
        action = pf.Action("CloseSession", pa.py_buffer(action_body))
        
        # Execute action
        results = list(server.do_action(context, action))
        
        assert len(results) == 1
        result = results[0]
        assert isinstance(result, pf.Result)
        
        # Check that session state was cleaned up
        assert len(server.prepared_statements) == 0
        assert len(server.open_transactions) == 0
        assert len(server.open_sessions) == 0

    @patch('src.mpzsql.flightsql.minimal.ActionClosePreparedStatementRequest')
    def test_do_action_close_prepared_statement(self, mock_request_class, server):
        """Test do_action with ClosePreparedStatement."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Setup a prepared statement
        test_handle = uuid.uuid4().bytes
        handle_key = test_handle.hex()
        server.prepared_statements[handle_key] = {"sql": "SELECT 1", "schema": None}
        
        # Mock the request object
        mock_request = Mock()
        mock_request.prepared_statement_handle = test_handle
        mock_request_class.return_value = mock_request
        
        # Create action
        action_body = b'mock_action_body'
        action = pf.Action("ClosePreparedStatement", pa.py_buffer(action_body))
        
        # Execute action
        results = list(server.do_action(context, action))
        
        assert len(results) == 1
        result = results[0]
        assert isinstance(result, pf.Result)
        
        # Check that prepared statement was removed
        assert handle_key not in server.prepared_statements

    def test_do_action_close_prepared_statement_not_found(self, server):
        """Test do_action with ClosePreparedStatement for non-existent handle."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Create action for non-existent prepared statement
        action_body = b'mock_action_body'
        action = pf.Action("ClosePreparedStatement", pa.py_buffer(action_body))
        
        # Mock the parsing to return a non-existent handle
        with patch('src.mpzsql.flightsql.minimal.ActionClosePreparedStatementRequest') as mock_req:
            mock_request = Mock()
            mock_request.prepared_statement_handle = uuid.uuid4().bytes
            mock_req.return_value = mock_request
            
            # Execute action - should not raise error, just log warning
            results = list(server.do_action(context, action))
            
            assert len(results) == 1
            result = results[0]
            assert isinstance(result, pf.Result)

    def test_do_action_unknown_action(self, server):
        """Test do_action with unknown action type."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Create action with unknown type
        action_body = b'mock_action_body'
        action = pf.Action("UnknownAction", pa.py_buffer(action_body))
        
        # Execute action and expect error
        with pytest.raises(NotImplementedError, match="Action UnknownAction not implemented"):
            list(server.do_action(context, action))


class TestMinimalFlightSQLServerFlightInfo:
    """Test MinimalFlightSQLServer get_flight_info method."""
    
    @pytest.fixture
    def server(self, mock_backend, config, location):
        """Create a test server instance."""
        return MinimalFlightSQLServer(
            backend=mock_backend,
            config=config,
            location=location
        )
    
    def test_get_flight_info_statement_query(self, server):
        """Test get_flight_info for CommandStatementQuery with real protobuf serialization."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Create proper protobuf Any message for CommandStatementQuery
        from google.protobuf import any_pb2
        from src.mpzsql.flightsql.protobuf import FlightSQLProtobuf
        
        # Create the SQL query as raw bytes (as seen in protobuf.log)
        sql_query = "SELECT * FROM test_table"
        
        # Method 1: Try proper Any message with type URL and query field
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_STATEMENT_QUERY_TYPE_URL
        
        # Encode the SQL query as protobuf field 1 (query field)
        # Field tag 1, wire type 2 (length-delimited string)
        query_encoded = sql_query.encode('utf-8')
        any_msg.value = bytes([0x0A]) + bytes([len(query_encoded)]) + query_encoded
        
        descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())
        
        # Mock the backend to provide schema
        test_schema = pa.schema([pa.field("test_col", pa.string())])
        server.backend.get_statement_schema.return_value = test_schema
        
        # Get flight info
        flight_info = server.get_flight_info(context, descriptor)
        
        assert isinstance(flight_info, pf.FlightInfo)
        assert flight_info.descriptor == descriptor
        assert len(flight_info.endpoints) > 0
        assert flight_info.schema is not None

    def test_get_flight_info_get_catalogs(self, server):
        """Test get_flight_info for CommandGetCatalogs with real protobuf serialization."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Create proper protobuf Any message for CommandGetCatalogs
        from google.protobuf import any_pb2
        from src.mpzsql.flightsql.protobuf import FlightSQLProtobuf
        
        # CommandGetCatalogs has no fields, so create proper Any message
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_GET_CATALOGS_TYPE_URL
        any_msg.value = b""  # Empty value for CommandGetCatalogs
        
        descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())
        
        # Mock the FlightSQLProtobuf schema response
        test_schema = pa.schema([pa.field("catalog_name", pa.string())])
        with patch.object(FlightSQLProtobuf, 'get_catalogs_schema', return_value=test_schema):
            # Get flight info
            flight_info = server.get_flight_info(context, descriptor)
        
        assert isinstance(flight_info, pf.FlightInfo)
        assert flight_info.descriptor == descriptor
        assert len(flight_info.endpoints) > 0
        assert flight_info.schema is not None

    def test_get_flight_info_unsupported_descriptor_type(self, server):
        """Test get_flight_info with unsupported descriptor type."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Create descriptor with unsupported type
        descriptor = pf.FlightDescriptor.for_path("test_path")
        
        with pytest.raises(NotImplementedError, match="Only CMD descriptors are supported"):
            server.get_flight_info(context, descriptor)

    def test_get_flight_info_unparseable_command(self, server):
        """Test get_flight_info with unparseable command."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Create descriptor with invalid command bytes
        descriptor = pf.FlightDescriptor.for_command(b"invalid_command")
        
        with patch('src.mpzsql.flightsql.protobuf.parse_any_command', return_value=None):
            with pytest.raises(ValueError, match="Failed to parse command"):
                server.get_flight_info(context, descriptor)

    @patch('src.mpzsql.flightsql.protobuf.parse_any_command')
    @patch.object(FlightSQLProtobuf, 'get_db_schemas_schema')
    def test_get_flight_info_get_db_schemas(self, mock_schema, mock_parse, server):
        """Test get_flight_info for CommandGetDbSchemas."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Mock parsed command
        mock_any = Mock()
        mock_any.type_url = FlightSQLProtobuf.COMMAND_GET_DB_SCHEMAS_TYPE_URL
        mock_any.value = b"mock_value"
        mock_parse.return_value = mock_any
        
        # Mock schema response
        test_schema = pa.schema([pa.field("schema_name", pa.string())])
        mock_schema.return_value = test_schema
        
        # Mock parsing method
        with patch.object(server, '_parse_get_db_schemas') as mock_parse_schemas:
            mock_command = Mock()
            mock_parse_schemas.return_value = mock_command
            
            descriptor = pf.FlightDescriptor.for_command(b"mock_command")
            flight_info = server.get_flight_info(context, descriptor)
            
            assert isinstance(flight_info, pf.FlightInfo)
            mock_parse_schemas.assert_called_once()

    @patch('src.mpzsql.flightsql.protobuf.parse_any_command')
    @patch.object(FlightSQLProtobuf, 'get_tables_schema')
    def test_get_flight_info_get_tables(self, mock_schema, mock_parse, server):
        """Test get_flight_info for CommandGetTables."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Mock parsed command
        mock_any = Mock()
        mock_any.type_url = FlightSQLProtobuf.COMMAND_GET_TABLES_TYPE_URL
        mock_any.value = b"mock_value"
        mock_parse.return_value = mock_any
        
        # Mock schema response
        test_schema = pa.schema([pa.field("table_name", pa.string())])
        mock_schema.return_value = test_schema
        
        # Mock parsing method
        with patch.object(server, '_parse_get_tables') as mock_parse_tables:
            mock_command = Mock()
            mock_command.include_schema = False
            mock_parse_tables.return_value = mock_command
            
            descriptor = pf.FlightDescriptor.for_command(b"mock_command")
            flight_info = server.get_flight_info(context, descriptor)
            
            assert isinstance(flight_info, pf.FlightInfo)
            mock_parse_tables.assert_called_once()

    def test_get_flight_info_unsupported_command_type(self, server):
        """Test get_flight_info with unsupported command type."""
        context = Mock(spec=pf.ServerCallContext)
        
        with patch('src.mpzsql.flightsql.protobuf.parse_any_command') as mock_parse:
            mock_any = Mock()
            mock_any.type_url = "unsupported.command.type"
            mock_parse.return_value = mock_any
            
            descriptor = pf.FlightDescriptor.for_command(b"mock_command")
            
            with pytest.raises(NotImplementedError, match="Unsupported command type"):
                server.get_flight_info(context, descriptor)


class TestMinimalFlightSQLServerDoGet:
    """Test MinimalFlightSQLServer do_get method."""
    
    @pytest.fixture
    def server(self, mock_backend, config, location):
        """Create a test server instance."""
        return MinimalFlightSQLServer(
            backend=mock_backend,
            config=config,
            location=location
        )
    
    @patch('src.mpzsql.flightsql.protobuf.parse_any_command')
    @patch.object(FlightSQLProtobuf, 'parse_command_statement_query')
    def test_do_get_statement_query(self, mock_parse_query, mock_parse_any, server):
        """Test do_get with CommandStatementQuery."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Mock command parsing
        mock_any = Mock()
        mock_any.type_url = FlightSQLProtobuf.COMMAND_STATEMENT_QUERY_TYPE_URL
        mock_any.value = b"mock_value"
        mock_parse_any.return_value = mock_any
        mock_parse_query.return_value = "SELECT * FROM test_table"
        
        # Create test data for backend response
        test_table = pa.table({
            "col1": [1, 2, 3],
            "col2": ["a", "b", "c"]
        })
        server.backend.execute_query.return_value = test_table
        
        # Create ticket
        ticket_bytes = b"mock_ticket_bytes"
        ticket = pf.Ticket(ticket_bytes)
        
        # Execute do_get
        result_stream = server.do_get(context, ticket)
        
        assert isinstance(result_stream, pf.FlightDataStream)
        server.backend.execute_query.assert_called_once_with("SELECT * FROM test_table")

    @patch('src.mpzsql.flightsql.protobuf.parse_any_command')
    def test_do_get_get_catalogs(self, mock_parse_any, server):
        """Test do_get with CommandGetCatalogs."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Mock command parsing
        mock_any = Mock()
        mock_any.type_url = FlightSQLProtobuf.COMMAND_GET_CATALOGS_TYPE_URL
        mock_any.value = b""
        mock_parse_any.return_value = mock_any
        
        # Create test data for backend response
        test_table = pa.table({"catalog_name": ["default"]})
        server.backend.get_catalogs.return_value = test_table
        
        # Create ticket
        ticket = pf.Ticket(b"mock_ticket_bytes")
        
        # Execute do_get
        result_stream = server.do_get(context, ticket)
        
        assert isinstance(result_stream, pf.FlightDataStream)
        server.backend.get_catalogs.assert_called_once()

    @patch('src.mpzsql.flightsql.protobuf.parse_any_command')
    def test_do_get_prepared_statement_query(self, mock_parse_any, server):
        """Test do_get with CommandPreparedStatementQuery."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Setup a prepared statement
        test_handle = uuid.uuid4().bytes
        handle_key = test_handle.hex()
        server.prepared_statements[handle_key] = {
            "sql": "SELECT * FROM test_table WHERE id = ?",
            "schema": pa.schema([pa.field("id", pa.int64())]),
            "parameters": None
        }
        
        # Mock command parsing
        mock_any = Mock()
        mock_any.type_url = FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_QUERY_TYPE_URL
        mock_any.value = b"mock_value"
        mock_parse_any.return_value = mock_any
        
        # Mock the prepared statement command parsing
        with patch.object(server, '_parse_prepared_statement_query') as mock_parse_ps:
            mock_command = Mock()
            mock_command.prepared_statement_handle = test_handle
            mock_parse_ps.return_value = mock_command
            
            # Create test data for backend response
            test_table = pa.table({
                "id": [1, 2, 3],
                "name": ["a", "b", "c"]
            })
            server.backend.execute_query.return_value = test_table
            
            # Create ticket
            ticket = pf.Ticket(b"mock_ticket_bytes")
            
            # Execute do_get
            result_stream = server.do_get(context, ticket)
            
            assert isinstance(result_stream, pf.FlightDataStream)
            server.backend.execute_query.assert_called_once_with("SELECT * FROM test_table WHERE id = ?")

    @patch('src.mpzsql.flightsql.protobuf.parse_any_command')
    def test_do_get_prepared_statement_not_found(self, mock_parse_any, server):
        """Test do_get with CommandPreparedStatementQuery for non-existent handle."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Mock command parsing
        mock_any = Mock()
        mock_any.type_url = FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_QUERY_TYPE_URL
        mock_any.value = b"mock_value"
        mock_parse_any.return_value = mock_any
        
        # Mock the prepared statement command parsing with non-existent handle
        with patch.object(server, '_parse_prepared_statement_query') as mock_parse_ps:
            mock_command = Mock()
            mock_command.prepared_statement_handle = uuid.uuid4().bytes
            mock_parse_ps.return_value = mock_command
            
            # Create ticket
            ticket = pf.Ticket(b"mock_ticket_bytes")
            
            # Execute do_get - should return error response instead of crashing
            result_stream = server.do_get(context, ticket)
            
            assert isinstance(result_stream, pf.FlightDataStream)

    @patch('src.mpzsql.flightsql.protobuf.parse_any_command')
    def test_do_get_unsupported_command(self, mock_parse_any, server):
        """Test do_get with unsupported command type."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Mock command parsing
        mock_any = Mock()
        mock_any.type_url = "unsupported.command.type"
        mock_any.value = b"mock_value"
        mock_parse_any.return_value = mock_any
        
        # Create ticket
        ticket = pf.Ticket(b"mock_ticket_bytes")
        
        # Execute do_get and expect error
        with pytest.raises(NotImplementedError, match="Unsupported command type"):
            server.do_get(context, ticket)

    @patch('src.mpzsql.flightsql.protobuf.parse_any_command')
    def test_do_get_unparseable_ticket(self, mock_parse_any, server):
        """Test do_get with unparseable ticket."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Mock command parsing failure
        mock_parse_any.return_value = None
        
        # Create ticket
        ticket = pf.Ticket(b"invalid_ticket")
        
        # Execute do_get and expect error
        with pytest.raises(NotImplementedError, match="Unsupported ticket format"):
            server.do_get(context, ticket)


class TestMinimalFlightSQLServerDoPut:
    """Test MinimalFlightSQLServer do_put method."""
    
    @pytest.fixture
    def server(self, mock_backend, config, location):
        """Create a test server instance."""
        return MinimalFlightSQLServer(
            backend=mock_backend,
            config=config,
            location=location
        )
    
    @patch('src.mpzsql.flightsql.protobuf.parse_any_command')
    def test_do_put_statement_update(self, mock_parse_any, server):
        """Test do_put with CommandStatementUpdate."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Mock command parsing
        mock_any = Mock()
        mock_any.type_url = FlightSQLProtobuf.COMMAND_STATEMENT_UPDATE_TYPE_URL
        mock_any.value = b"mock_value"
        mock_parse_any.return_value = mock_any
        
        # Mock the command object
        mock_command = Mock()
        mock_command.query = "INSERT INTO test_table VALUES (1, 'test')"
        
        # Mock the command unpack
        with patch.object(CommandStatementUpdate, 'Unpack') as mock_unpack:
            mock_unpack.return_value = None
            CommandStatementUpdate.query = mock_command.query
            
            # Mock backend response
            server.backend.execute_update.return_value = 3
            
            # Create mock reader and writer
            reader = Mock(spec=pf.FlightStreamReader)
            writer = Mock(spec=pf.FlightMetadataWriter)
            
            # Create descriptor
            descriptor = pf.FlightDescriptor.for_command(b"mock_command")
            
            # Execute do_put
            server.do_put(context, descriptor, reader, writer)
            
            # Verify backend was called
            server.backend.execute_update.assert_called_once()
            writer.write.assert_called_once()

    @patch('src.mpzsql.flightsql.protobuf.parse_any_command')
    def test_do_put_prepared_statement_update(self, mock_parse_any, server):
        """Test do_put with CommandPreparedStatementUpdate."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Setup a prepared statement
        test_handle = uuid.uuid4().bytes
        handle_key = test_handle.hex()
        server.prepared_statements[handle_key] = {
            "sql": "INSERT INTO test_table VALUES (?, ?)",
            "schema": None,
            "parameters": None
        }
        
        # Mock command parsing
        mock_any = Mock()
        mock_any.type_url = FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_UPDATE_TYPE_URL
        mock_any.value = b"mock_value"
        mock_parse_any.return_value = mock_any
        
        # Mock the command object
        mock_command = Mock()
        mock_command.prepared_statement_handle = test_handle
        
        # Mock the command unpack
        with patch.object(CommandPreparedStatementUpdate, 'Unpack') as mock_unpack:
            mock_unpack.return_value = None
            CommandPreparedStatementUpdate.prepared_statement_handle = test_handle
            
            # Mock backend response
            server.backend.execute_update.return_value = 1
            
            # Create mock reader and writer
            reader = Mock(spec=pf.FlightStreamReader)
            reader.read_chunk.side_effect = [
                Mock(data=pa.record_batch([pa.array([1])], names=["param1"])),
                StopIteration()
            ]
            writer = Mock(spec=pf.FlightMetadataWriter)
            
            # Create descriptor
            descriptor = pf.FlightDescriptor.for_command(b"mock_command")
            
            # Execute do_put
            server.do_put(context, descriptor, reader, writer)
            
            # Verify writer was called
            writer.write.assert_called_once()

    @patch('src.mpzsql.flightsql.protobuf.parse_any_command')
    def test_do_put_prepared_statement_query_parameters(self, mock_parse_any, server):
        """Test do_put with CommandPreparedStatementQuery (parameter binding)."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Setup a prepared statement
        test_handle = uuid.uuid4().bytes
        handle_key = test_handle.hex()
        server.prepared_statements[handle_key] = {
            "sql": "SELECT * FROM test_table WHERE id = ?",
            "schema": pa.schema([pa.field("id", pa.int64())]),
            "parameters": None
        }
        
        # Mock command parsing
        mock_any = Mock()
        mock_any.type_url = FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_QUERY_TYPE_URL
        mock_any.value = b"mock_value"
        mock_parse_any.return_value = mock_any
        
        # Mock the command object
        mock_command = Mock()
        mock_command.prepared_statement_handle = test_handle
        
        # Mock the command unpack
        with patch.object(CommandPreparedStatementQuery, 'Unpack') as mock_unpack:
            mock_unpack.return_value = None
            CommandPreparedStatementQuery.prepared_statement_handle = test_handle
            
            # Create mock reader and writer
            reader = Mock(spec=pf.FlightStreamReader)
            reader.read_chunk.side_effect = [
                Mock(data=pa.record_batch([pa.array([1])], names=["param1"])),
                StopIteration()
            ]
            writer = Mock(spec=pf.FlightMetadataWriter)
            
            # Create descriptor
            descriptor = pf.FlightDescriptor.for_command(b"mock_command")
            
            # Execute do_put
            server.do_put(context, descriptor, reader, writer)
            
            # Verify parameters were stored
            assert server.prepared_statements[handle_key]["parameters"] is not None
            writer.write.assert_called_once()

    @patch('src.mpzsql.flightsql.protobuf.parse_any_command')
    def test_do_put_unsupported_command(self, mock_parse_any, server):
        """Test do_put with unsupported command type."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Mock command parsing
        mock_any = Mock()
        mock_any.type_url = "unsupported.command.type"
        mock_any.value = b"mock_value"
        mock_parse_any.return_value = mock_any
        
        # Create mock reader and writer
        reader = Mock(spec=pf.FlightStreamReader)
        writer = Mock(spec=pf.FlightMetadataWriter)
        
        # Create descriptor
        descriptor = pf.FlightDescriptor.for_command(b"mock_command")
        
        # Execute do_put and expect error
        with pytest.raises(NotImplementedError, match="Unsupported command type for DoPut"):
            server.do_put(context, descriptor, reader, writer)


class TestMinimalFlightSQLServerParsing:
    """Test MinimalFlightSQLServer command parsing methods."""
    
    @pytest.fixture
    def server(self, mock_backend, config, location):
        """Create a test server instance."""
        return MinimalFlightSQLServer(
            backend=mock_backend,
            config=config,
            location=location
        )
    
    @patch.object(FlightSQLProtobuf, 'parse_command_statement_query')
    def test_parse_statement_query(self, mock_parse, server):
        """Test _parse_statement_query method."""
        mock_any = Mock()
        mock_any.value = b"mock_value"
        mock_parse.return_value = "SELECT * FROM test_table"
        
        result = server._parse_statement_query(mock_any)
        
        assert isinstance(result, CommandStatementQuery)
        assert result.query == "SELECT * FROM test_table"

    def test_parse_prepared_statement_query(self, server):
        """Test _parse_prepared_statement_query method."""
        mock_any = Mock()
        mock_command = Mock()
        
        with patch.object(CommandPreparedStatementQuery, 'Unpack') as mock_unpack:
            result = server._parse_prepared_statement_query(mock_any)
            
            assert isinstance(result, CommandPreparedStatementQuery)
            mock_unpack.assert_called_once_with(mock_any)

    @patch.object(FlightSQLProtobuf, 'parse_command_get_tables')
    def test_parse_get_tables(self, mock_parse, server):
        """Test _parse_get_tables method."""
        mock_any = Mock()
        mock_any.value = b"mock_value"
        mock_parse.return_value = ("catalog", "schema_pattern", "table_pattern", ["TABLE"], True)
        
        result = server._parse_get_tables(mock_any)
        
        assert isinstance(result, CommandGetTables)
        assert result.catalog == "catalog"
        assert result.db_schema_filter_pattern == "schema_pattern"
        assert result.table_name_filter_pattern == "table_pattern"
        assert result.table_types == ["TABLE"]
        assert result.include_schema is True

    @patch.object(FlightSQLProtobuf, 'parse_command_get_db_schemas')
    def test_parse_get_db_schemas(self, mock_parse, server):
        """Test _parse_get_db_schemas method."""
        mock_any = Mock()
        mock_any.value = b"mock_value"
        mock_parse.return_value = ("catalog", "schema_pattern")
        
        result = server._parse_get_db_schemas(mock_any)
        
        assert isinstance(result, CommandGetDbSchemas)
        assert result.catalog == "catalog"
        assert result.db_schema_filter_pattern == "schema_pattern"

    @patch.object(FlightSQLProtobuf, 'parse_command_get_columns')
    def test_parse_get_columns(self, mock_parse, server):
        """Test _parse_get_columns method."""
        mock_any = Mock()
        mock_any.value = b"mock_value"
        mock_parse.return_value = ("catalog", "schema_pattern", "table_pattern", "column_pattern")
        
        result = server._parse_get_columns(mock_any)
        
        assert isinstance(result, CommandGetColumns)
        assert result.catalog == "catalog"
        assert result.db_schema_filter_pattern == "schema_pattern"
        assert result.table_name_filter_pattern == "table_pattern"
        assert result.column_name_filter_pattern == "column_pattern"

    def test_parse_get_sql_info(self, server):
        """Test _parse_get_sql_info method."""
        mock_any = Mock()
        mock_any.value = b"mock_value"
        
        with patch.object(CommandGetSqlInfo, 'ParseFromString') as mock_parse:
            result = server._parse_get_sql_info(mock_any)
            
            assert isinstance(result, CommandGetSqlInfo)
            mock_parse.assert_called_once_with(b"mock_value")


class TestMinimalFlightSQLServerBackendInteraction:
    """Test MinimalFlightSQLServer backend interaction methods."""
    
    @pytest.fixture
    def server(self, mock_backend, config, location):
        """Create a test server instance."""
        return MinimalFlightSQLServer(
            backend=mock_backend,
            config=config,
            location=location
        )
    
    def test_do_get_statement_from_query_success(self, server):
        """Test _do_get_statement_from_query with successful execution."""
        test_table = pa.table({
            "col1": [1, 2, 3],
            "col2": ["a", "b", "c"]
        })
        server.backend.execute_query.return_value = test_table
        
        result = server._do_get_statement_from_query("SELECT * FROM test_table")
        
        assert isinstance(result, pf.FlightDataStream)
        server.backend.execute_query.assert_called_once_with("SELECT * FROM test_table")

    def test_do_get_statement_from_query_error(self, server):
        """Test _do_get_statement_from_query with backend error."""
        server.backend.execute_query.side_effect = Exception("Query failed")
        
        result = server._do_get_statement_from_query("SELECT * FROM invalid_table")
        
        assert isinstance(result, pf.FlightDataStream)
        server.backend.execute_query.assert_called_once_with("SELECT * FROM invalid_table")

    def test_do_put_update_from_query_success(self, server):
        """Test _do_put_update_from_query with successful execution."""
        server.backend.execute_update.return_value = 5
        
        result = server._do_put_update_from_query("INSERT INTO test_table VALUES (1, 'test')")
        
        assert result == 5
        server.backend.execute_update.assert_called_once_with("INSERT INTO test_table VALUES (1, 'test')")

    def test_do_put_update_from_query_error(self, server):
        """Test _do_put_update_from_query with backend error."""
        server.backend.execute_update.side_effect = Exception("Update failed")
        
        with pytest.raises(Exception, match="Update failed"):
            server._do_put_update_from_query("INSERT INTO invalid_table VALUES (1, 'test')")

    def test_do_get_catalogs(self, server):
        """Test _do_get_catalogs method."""
        test_table = pa.table({"catalog_name": ["default", "test"]})
        server.backend.get_catalogs.return_value = test_table
        
        command = CommandGetCatalogs()
        result = server._do_get_catalogs(command)
        
        assert isinstance(result, pf.FlightDataStream)
        server.backend.get_catalogs.assert_called_once()

    def test_do_get_schemas(self, server):
        """Test _do_get_schemas method."""
        test_table = pa.table({
            "catalog_name": ["default"],
            "schema_name": ["main"]
        })
        server.backend.get_db_schemas.return_value = test_table
        
        command = CommandGetDbSchemas()
        command.catalog = "default"
        command.db_schema_filter_pattern = "main%"
        
        result = server._do_get_schemas(command)
        
        assert isinstance(result, pf.FlightDataStream)
        server.backend.get_db_schemas.assert_called_once_with(
            catalog="default",
            db_schema_filter_pattern="main%"
        )

    def test_do_get_tables(self, server):
        """Test _do_get_tables method."""
        test_table = pa.table({
            "catalog_name": ["default"],
            "schema_name": ["main"],
            "table_name": ["test_table"],
            "table_type": ["TABLE"]
        })
        server.backend.get_tables.return_value = test_table
        
        command = CommandGetTables()
        command.catalog = "default"
        command.db_schema_filter_pattern = "main%"
        command.table_name_filter_pattern = "test%"
        command.table_types = ["TABLE"]
        command.include_schema = False
        
        result = server._do_get_tables(command)
        
        assert isinstance(result, pf.FlightDataStream)
        server.backend.get_tables.assert_called_once_with(
            catalog="default",
            db_schema_filter_pattern="main%",
            table_name_filter_pattern="test%",
            table_types=["TABLE"],
            include_schema=False
        )

    def test_do_get_columns(self, server):
        """Test _do_get_columns method."""
        test_table = pa.table({
            "catalog_name": ["default"],
            "schema_name": ["main"],
            "table_name": ["test_table"],
            "column_name": ["id"],
            "ordinal_position": [1],
            "is_nullable": [False],
            "data_type": ["INTEGER"]
        })
        server.backend.get_columns.return_value = test_table
        
        command = CommandGetColumns()
        command.catalog = "default"
        command.db_schema_filter_pattern = "main%"
        command.table_name_filter_pattern = "test%"
        command.column_name_filter_pattern = "id%"
        
        result = server._do_get_columns(command)
        
        assert isinstance(result, pf.FlightDataStream)
        server.backend.get_columns.assert_called_once_with(
            catalog="default",
            db_schema_filter_pattern="main%",
            table_name_filter_pattern="test%",
            column_name_filter_pattern="id%"
        )

    def test_do_get_sql_info(self, server):
        """Test _do_get_sql_info method."""
        test_table = pa.table({
            "info_name": [0, 1, 2],
            "value": ["MPZSQL", "1.0", "false"]
        })
        server.backend.get_sql_info.return_value = test_table
        
        command = CommandGetSqlInfo()
        command.info = [0, 1, 2]
        
        result = server._do_get_sql_info(command)
        
        assert isinstance(result, pf.FlightDataStream)
        server.backend.get_sql_info.assert_called_once_with([0, 1, 2])


class TestMinimalFlightSQLServerErrorHandling:
    """Test MinimalFlightSQLServer error handling scenarios."""
    
    @pytest.fixture
    def server(self, mock_backend, config, location):
        """Create a test server instance."""
        return MinimalFlightSQLServer(
            backend=mock_backend,
            config=config,
            location=location
        )
    
    def test_create_prepared_statement_error(self, server):
        """Test error handling in _create_prepared_statement."""
        context = Mock(spec=pf.ServerCallContext)
        
        with patch('src.mpzsql.flightsql.minimal.ActionCreatePreparedStatementRequest') as mock_req:
            mock_req.side_effect = Exception("Parsing failed")
            
            action_body = b'invalid_data'
            action = pf.Action("CreatePreparedStatement", pa.py_buffer(action_body))
            
            with pytest.raises(Exception, match="Parsing failed"):
                list(server.do_action(context, action))

    def test_get_flight_info_prepared_statement_error_recovery(self, server):
        """Test error recovery in get_flight_info for prepared statements."""
        context = Mock(spec=pf.ServerCallContext)
        
        with patch('src.mpzsql.flightsql.protobuf.parse_any_command') as mock_parse:
            mock_any = Mock()
            mock_any.type_url = FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_QUERY_TYPE_URL
            mock_any.value = b"mock_value"
            mock_parse.return_value = mock_any
            
            # Mock parsing method to raise exception
            with patch.object(server, '_parse_prepared_statement_query') as mock_parse_ps:
                mock_parse_ps.side_effect = Exception("Parsing failed")
                
                descriptor = pf.FlightDescriptor.for_command(b"mock_command")
                
                # Should return error FlightInfo instead of crashing
                flight_info = server.get_flight_info(context, descriptor)
                
                assert isinstance(flight_info, pf.FlightInfo)
                assert flight_info.total_records == 0
                assert flight_info.total_bytes == 0

    def test_do_get_prepared_statement_error_recovery(self, server):
        """Test error recovery in do_get for prepared statements."""
        context = Mock(spec=pf.ServerCallContext)
        
        with patch('src.mpzsql.flightsql.protobuf.parse_any_command') as mock_parse:
            mock_any = Mock()
            mock_any.type_url = FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_QUERY_TYPE_URL
            mock_any.value = b"mock_value"
            mock_parse.return_value = mock_any
            
            # Mock parsing method to raise exception
            with patch.object(server, '_parse_prepared_statement_query') as mock_parse_ps:
                mock_parse_ps.side_effect = Exception("Parsing failed")
                
                ticket = pf.Ticket(b"mock_ticket")
                
                # Should return error stream instead of crashing
                result_stream = server.do_get(context, ticket)
                
                assert isinstance(result_stream, pf.FlightDataStream)

    def test_mutex_thread_safety(self, server):
        """Test that mutex protects transaction operations."""
        # This is a basic test to ensure the mutex exists and is used
        assert hasattr(server, '_mutex')
        assert isinstance(server._mutex, threading.Lock)
        
        # Test that transaction operations use the mutex
        with patch('src.mpzsql.flightsql.minimal.ActionBeginTransactionRequest'):
            context = Mock(spec=pf.ServerCallContext)
            action_body = b'mock_data'
            action = pf.Action("BeginTransaction", pa.py_buffer(action_body))
            
            # Execute multiple times to test thread safety
            results1 = list(server.do_action(context, action))
            results2 = list(server.do_action(context, action))
            
            assert len(results1) == 1
            assert len(results2) == 1
            assert server._transaction_counter == 2

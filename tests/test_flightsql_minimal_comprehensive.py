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
            password="test_pass"
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
        location = pf.Location.for_grpc_tcp("localhost", 0)  # Use port 0 for auto-assignment
        advertised_location = pf.Location.for_grpc_tcp("external.host", 0)
        
        server = MinimalFlightSQLServer(
            backend=mock_backend,
            config=config,
            location=location,
            advertised_location=advertised_location
        )
        
        assert server.location == location
        assert server.advertised_location == advertised_location


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
        mock_request.action = 0  # 0 for COMMIT
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
        mock_request.action = 1  # 1 for ROLLBACK
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
        mock_request.action = 0  # 0 for COMMIT
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
        
        # Create a mock descriptor with truly unsupported type (UNKNOWN)
        # Note: PATH descriptors are now supported for raw Flight do_put functionality
        descriptor = Mock(spec=pf.FlightDescriptor)
        descriptor.descriptor_type = pf.DescriptorType.UNKNOWN
        descriptor.command = None  # No command for UNKNOWN type
        
        with pytest.raises(NotImplementedError, match="Only CMD descriptors are supported"):
            server.get_flight_info(context, descriptor)

    def test_get_flight_info_path_descriptor_support(self, server):
        """Test get_flight_info with PATH descriptor - currently not implemented."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Create descriptor with PATH type
        descriptor = pf.FlightDescriptor.for_path("test_table")
        
        # PATH descriptors are not currently supported
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


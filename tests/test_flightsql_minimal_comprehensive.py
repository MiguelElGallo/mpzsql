"""
Comprehensive test suite for FlightSQL minimal server implementation.

Tests the MinimalFlightSQLServer class which provides the core FlightSQL
protocol implementation including actions, commands, and schema generation.
"""

from unittest.mock import Mock, patch

import pyarrow as pa
import pyarrow.flight as pf
import pytest

from src.mpzsql.backends.base import DatabaseBackend
from src.mpzsql.config import ServerConfig
from src.mpzsql.flightsql.minimal import (
    MinimalFlightSQLServer,
    SqlInfo,
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
    
    def test_do_action_create_prepared_statement(self, server):
        """Test do_action with CreatePreparedStatement."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Create action with mock data (since our classes don't serialize)
        action_body = b'\x08\x01SELECT * FROM test_table'  # Mock protobuf data
        action = pf.Action("CreatePreparedStatement", pa.py_buffer(action_body))
        
        # Execute action
        results = list(server.do_action(context, action))
        
        assert len(results) == 1
        result = results[0]
        assert isinstance(result, pf.Result)
        
        # Check that prepared statement was stored
        assert len(server.prepared_statements) == 1
    
    def test_do_action_begin_transaction(self, server):
        """Test do_action with BeginTransaction."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Create action with mock data
        action_body = b'\x08\x01'  # Mock protobuf data
        action = pf.Action("BeginTransaction", pa.py_buffer(action_body))
        
        # Execute action
        results = list(server.do_action(context, action))
        
        assert len(results) == 1
        result = results[0]
        assert isinstance(result, pf.Result)
        
        # Check that transaction was created
        assert len(server.open_transactions) == 1


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
        from mpzsql.flightsql.protobuf import FlightSQLProtobuf
        
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
        from mpzsql.flightsql.protobuf import FlightSQLProtobuf
        
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

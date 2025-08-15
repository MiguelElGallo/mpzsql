"""
Comprehensive test suite for Phase 2 FlightSQL methods.

This module tests the core data manipulation and query execution FlightSQL methods
implemented in MinimalFlightSQLServer:

**Data Retrieval (do_get methods):**
1. get_flight_info - Flight information for FlightSQL commands
2. do_get - Query execution and data retrieval
3. Metadata queries (catalogs, schemas, tables, columns, sql_info)

**Data Manipulation (do_put methods):**
4. do_put - Data uploads and statement updates 
5. Statement updates (INSERT, UPDATE, DELETE)
6. PATH descriptor uploads for raw Arrow data

**Prepared Statements (do_action methods):**
7. CreatePreparedStatement - Create parameterized queries
8. ClosePreparedStatement - Clean up prepared statements
9. Prepared statement execution and parameter binding

**Transaction Management:**
10. BeginTransaction - Start database transactions
11. EndTransaction - Commit or rollback transactions
12. CloseSession - Session cleanup and resource management

These tests verify the complete Phase 2 FlightSQL implementation including
proper protobuf message handling, Arrow data streaming, parameter binding,
and backend integration.
"""

import pytest
import uuid
import time
import threading
from unittest.mock import Mock, MagicMock, patch
from google.protobuf import any_pb2

import pyarrow as pa
import pyarrow.flight as pf

from src.mpzsql.backends.base import DatabaseBackend
from src.mpzsql.config import ServerConfig
from src.mpzsql.flightsql.minimal import MinimalFlightSQLServer
from src.mpzsql.flightsql.protobuf import (
    FlightSQLProtobuf, 
    parse_any_command,
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
    DoPutUpdateResult
)


@pytest.fixture
def mock_backend():
    """Create a comprehensive mock database backend for testing."""
    backend = MagicMock()
    
    # Mock query execution responses
    backend.execute_query.return_value = pa.table({
        "id": [1, 2, 3],
        "name": ["Alice", "Bob", "Charlie"],
        "age": [25, 30, 35]
    })
    
    backend.execute_update.return_value = 3  # 3 rows affected
    
    # Mock schema methods
    backend.get_statement_schema.return_value = pa.schema([
        pa.field("id", pa.int64()),
        pa.field("name", pa.string()),
        pa.field("age", pa.int32())
    ])
    
    # Mock metadata responses
    backend.get_catalogs.return_value = pa.table({
        "catalog_name": ["default", "main", "test"]
    })
    
    backend.get_db_schemas.return_value = pa.table({
        "catalog_name": ["default", "default", "test"],
        "db_schema_name": ["main", "information_schema", "public"]
    })
    
    backend.get_tables.return_value = pa.table({
        "catalog_name": ["default", "default"],
        "db_schema_name": ["main", "main"],
        "table_name": ["users", "orders"],
        "table_type": ["TABLE", "TABLE"]
    })
    
    backend.get_table_types.return_value = pa.table({
        "table_type": ["TABLE", "VIEW", "SYSTEM TABLE"]
    })
    
    backend.get_columns.return_value = pa.table({
        "catalog_name": ["default"],
        "db_schema_name": ["main"],
        "table_name": ["users"],
        "column_name": ["id"],
        "ordinal_position": [1],
        "is_nullable": [False],
        "data_type": ["INTEGER"]
    })
    
    backend.get_sql_info.return_value = pa.table({
        "info_name": [0, 1, 2],
        "value": ["MPZSQL", "1.0", "14.0"]
    })
    
    # Mock table schema and operations for PATH uploads
    backend.get_table_schema.return_value = pa.schema([
        pa.field("col1", pa.int64()),
        pa.field("col2", pa.string())
    ])
    backend.get_table_row_count.return_value = 100
    backend.create_table_from_schema.return_value = None
    backend.append_table_from_arrow.return_value = None
    
    return backend


@pytest.fixture
def config():
    """Create a test configuration."""
    return ServerConfig(
        secret_key="test_secret",
        username="test_user",
        password="test_pass",
        hostname="localhost", 
        port=8080
    )


@pytest.fixture
def location():
    """Create a test server location."""
    return pf.Location.for_grpc_tcp("localhost", 0)


@pytest.fixture
def server(mock_backend, config, location):
    """Create a test server instance."""
    return MinimalFlightSQLServer(
        backend=mock_backend,
        config=config,
        location=location
    )


class TestPhase2GetFlightInfo:
    """Test Phase 2 get_flight_info method for FlightSQL commands."""

    def test_get_flight_info_statement_query(self, server):
        """Test get_flight_info for SQL statement queries."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Create protobuf command for statement query
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_STATEMENT_QUERY_TYPE_URL
        
        sql_query = "SELECT * FROM users WHERE age > 25"
        query_encoded = sql_query.encode("utf-8")
        any_msg.value = bytes([0x0A]) + bytes([len(query_encoded)]) + query_encoded
        
        descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())
        
        # Mock backend schema response
        test_schema = pa.schema([
            pa.field("id", pa.int64()),
            pa.field("name", pa.string()),
            pa.field("age", pa.int32())
        ])
        server.backend.get_statement_schema.return_value = test_schema
        
        flight_info = server.get_flight_info(context, descriptor)
        
        assert isinstance(flight_info, pf.FlightInfo)
        assert flight_info.schema == test_schema
        assert len(flight_info.endpoints) == 1
        assert flight_info.descriptor == descriptor

    def test_get_flight_info_get_catalogs(self, server):
        """Test get_flight_info for GetCatalogs command."""
        context = Mock(spec=pf.ServerCallContext)
        
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_GET_CATALOGS_TYPE_URL
        any_msg.value = b""
        
        descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())
        
        flight_info = server.get_flight_info(context, descriptor)
        
        assert isinstance(flight_info, pf.FlightInfo)
        assert flight_info.schema is not None
        assert len(flight_info.endpoints) == 1

    def test_get_flight_info_get_db_schemas(self, server):
        """Test get_flight_info for GetDbSchemas command.""" 
        context = Mock(spec=pf.ServerCallContext)
        
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_GET_DB_SCHEMAS_TYPE_URL
        any_msg.value = b""
        
        descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())
        
        flight_info = server.get_flight_info(context, descriptor)
        
        assert isinstance(flight_info, pf.FlightInfo)
        assert flight_info.schema is not None
        assert len(flight_info.endpoints) == 1

    def test_get_flight_info_get_tables(self, server):
        """Test get_flight_info for GetTables command."""
        context = Mock(spec=pf.ServerCallContext)
        
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_GET_TABLES_TYPE_URL
        any_msg.value = b""
        
        descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())
        
        flight_info = server.get_flight_info(context, descriptor)
        
        assert isinstance(flight_info, pf.FlightInfo)
        assert flight_info.schema is not None
        assert len(flight_info.endpoints) == 1

    def test_get_flight_info_prepared_statement(self, server):
        """Test get_flight_info for prepared statement queries."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Setup a prepared statement
        test_handle = uuid.uuid4().bytes
        handle_key = test_handle.hex()
        test_schema = pa.schema([
            pa.field("id", pa.int64()),
            pa.field("name", pa.string())
        ])
        
        server.prepared_statements[handle_key] = {
            "sql": "SELECT * FROM users WHERE id = ?",
            "schema": test_schema,
            "transaction_id": "",
            "parameters": None
        }
        
        # Create protobuf command 
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_QUERY_TYPE_URL
        any_msg.value = bytes([0x0A]) + bytes([len(test_handle)]) + test_handle
        
        descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())
        
        flight_info = server.get_flight_info(context, descriptor)
        
        assert isinstance(flight_info, pf.FlightInfo)
        assert flight_info.schema == test_schema
        assert len(flight_info.endpoints) == 1

    def test_get_flight_info_path_descriptor_table(self, server):
        """Test get_flight_info for PATH descriptor table access."""
        context = Mock(spec=pf.ServerCallContext)
        
        descriptor = pf.FlightDescriptor.for_path("test_table")
        
        # Mock backend responses
        test_schema = pa.schema([pa.field("col1", pa.int64())])
        server.backend.get_table_schema.return_value = test_schema
        server.backend.get_table_row_count.return_value = 42
        
        flight_info = server.get_flight_info(context, descriptor)
        
        assert isinstance(flight_info, pf.FlightInfo)
        assert flight_info.schema == test_schema
        assert flight_info.total_records == 42
        assert len(flight_info.endpoints) == 1


class TestPhase2DoGet:
    """Test Phase 2 do_get method for data retrieval."""

    def test_do_get_statement_query(self, server):
        """Test do_get for SQL statement execution."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Create protobuf command
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_STATEMENT_QUERY_TYPE_URL
        
        sql_query = "SELECT * FROM users"
        query_encoded = sql_query.encode("utf-8")
        any_msg.value = bytes([0x0A]) + bytes([len(query_encoded)]) + query_encoded
        
        ticket = pf.Ticket(any_msg.SerializeToString())
        
        # Mock backend response
        result_table = pa.table({
            "id": [1, 2, 3],
            "name": ["Alice", "Bob", "Charlie"]
        })
        server.backend.execute_query.return_value = result_table
        
        stream = server.do_get(context, ticket)
        
        assert isinstance(stream, pf.FlightDataStream)
        # Verify backend was called with correct query
        server.backend.execute_query.assert_called_once_with("SELECT * FROM users")

    def test_do_get_catalogs(self, server):
        """Test do_get for catalogs metadata."""
        context = Mock(spec=pf.ServerCallContext)
        
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_GET_CATALOGS_TYPE_URL
        any_msg.value = b""
        
        ticket = pf.Ticket(any_msg.SerializeToString())
        
        stream = server.do_get(context, ticket)
        
        assert isinstance(stream, pf.FlightDataStream)
        # Verify backend method was called
        server.backend.get_catalogs.assert_called_once()

    def test_do_get_schemas(self, server):
        """Test do_get for schemas metadata."""
        context = Mock(spec=pf.ServerCallContext)
        
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_GET_DB_SCHEMAS_TYPE_URL
        any_msg.value = b""
        
        ticket = pf.Ticket(any_msg.SerializeToString())
        
        stream = server.do_get(context, ticket)
        
        assert isinstance(stream, pf.FlightDataStream)
        # Verify backend method was called
        server.backend.get_db_schemas.assert_called_once()

    def test_do_get_tables(self, server):
        """Test do_get for tables metadata."""
        context = Mock(spec=pf.ServerCallContext)
        
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_GET_TABLES_TYPE_URL
        any_msg.value = b""
        
        ticket = pf.Ticket(any_msg.SerializeToString())
        
        stream = server.do_get(context, ticket)
        
        assert isinstance(stream, pf.FlightDataStream)
        # Verify backend method was called
        server.backend.get_tables.assert_called_once()

    def test_do_get_table_types(self, server):
        """Test do_get for table types metadata."""
        context = Mock(spec=pf.ServerCallContext)
        
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_GET_TABLE_TYPES_TYPE_URL
        any_msg.value = b""
        
        ticket = pf.Ticket(any_msg.SerializeToString())
        
        stream = server.do_get(context, ticket)
        
        assert isinstance(stream, pf.FlightDataStream)
        # Verify backend method was called
        server.backend.get_table_types.assert_called_once()

    def test_do_get_columns(self, server):
        """Test do_get for columns metadata.""" 
        context = Mock(spec=pf.ServerCallContext)
        
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_GET_COLUMNS_TYPE_URL
        any_msg.value = b""
        
        ticket = pf.Ticket(any_msg.SerializeToString())
        
        stream = server.do_get(context, ticket)
        
        assert isinstance(stream, pf.FlightDataStream)
        # Verify backend method was called
        server.backend.get_columns.assert_called_once()

    def test_do_get_sql_info(self, server):
        """Test do_get for SQL info metadata."""
        context = Mock(spec=pf.ServerCallContext)
        
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_GET_SQL_INFO_TYPE_URL
        any_msg.value = b""
        
        ticket = pf.Ticket(any_msg.SerializeToString())
        
        stream = server.do_get(context, ticket)
        
        assert isinstance(stream, pf.FlightDataStream)
        # Verify backend method was called
        server.backend.get_sql_info.assert_called_once()

    def test_do_get_prepared_statement(self, server):
        """Test do_get for prepared statement execution."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Setup prepared statement
        test_handle = uuid.uuid4().bytes
        handle_key = test_handle.hex()
        
        # Create parameter as Arrow RecordBatch
        param_batch = pa.record_batch([
            pa.array([1])  # Parameter value for id = ?
        ], schema=pa.schema([pa.field("param1", pa.int64())]))
        
        server.prepared_statements[handle_key] = {
            "sql": "SELECT * FROM users WHERE id = ?",
            "schema": pa.schema([pa.field("id", pa.int64()), pa.field("name", pa.string())]),
            "transaction_id": "",
            "parameters": [param_batch]  # Store as Arrow RecordBatch
        }
        
        # Create protobuf command
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_QUERY_TYPE_URL
        any_msg.value = bytes([0x0A]) + bytes([len(test_handle)]) + test_handle
        
        ticket = pf.Ticket(any_msg.SerializeToString())
        
        # Mock backend response
        result_table = pa.table({
            "id": [1],
            "name": ["Alice"]
        })
        server.backend.execute_query.return_value = result_table
        
        stream = server.do_get(context, ticket)
        
        assert isinstance(stream, pf.FlightDataStream)
        # Verify backend was called with the prepared statement query and parameters
        server.backend.execute_query.assert_called_once_with("SELECT * FROM users WHERE id = ?", [1])

    def test_do_get_unsupported_command(self, server):
        """Test do_get with unsupported command type."""
        context = Mock(spec=pf.ServerCallContext)
        
        any_msg = any_pb2.Any()
        any_msg.type_url = "type.googleapis.com/arrow.flight.protocol.sql.UnsupportedCommand"
        any_msg.value = b""
        
        ticket = pf.Ticket(any_msg.SerializeToString())
        
        with pytest.raises(NotImplementedError, match="Unsupported command type"):
            server.do_get(context, ticket)

    def test_do_get_invalid_ticket(self, server):
        """Test do_get with invalid ticket data."""
        context = Mock(spec=pf.ServerCallContext)
        
        ticket = pf.Ticket(b"invalid_protobuf_data")
        
        with pytest.raises(NotImplementedError, match="Unsupported ticket format"):
            server.do_get(context, ticket)


class TestPhase2DoPut:
    """Test Phase 2 do_put method for data uploads and updates."""

    def test_do_put_statement_update(self, server):
        """Test do_put for SQL statement updates."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Create protobuf command
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_STATEMENT_UPDATE_TYPE_URL
        
        sql_update = "INSERT INTO users (name, age) VALUES ('David', 28)"
        update_encoded = sql_update.encode("utf-8")
        any_msg.value = bytes([0x0A]) + bytes([len(update_encoded)]) + update_encoded
        
        descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())
        
        # Mock reader and writer
        reader = Mock(spec=pf.FlightStreamReader)
        writer = Mock(spec=pf.FlightMetadataWriter)
        
        # Mock backend response
        server.backend.execute_update.return_value = 1  # 1 row affected
        
        server.do_put(context, descriptor, reader, writer)
        
        # Verify writer was called with result
        writer.write.assert_called_once()
        # Verify backend was called
        server.backend.execute_update.assert_called_once_with("INSERT INTO users (name, age) VALUES ('David', 28)")

    def test_do_put_prepared_statement_update(self, server):
        """Test do_put for prepared statement updates."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Setup prepared statement
        test_handle = uuid.uuid4().bytes
        handle_key = test_handle.hex()
        
        server.prepared_statements[handle_key] = {
            "sql": "UPDATE users SET age = ? WHERE id = ?",
            "schema": None,
            "transaction_id": "",
            "parameters": None
        }
        
        # Create protobuf command
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_UPDATE_TYPE_URL
        any_msg.value = bytes([0x0A]) + bytes([len(test_handle)]) + test_handle
        
        descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())
        
        # Mock reader with parameter data
        reader = Mock(spec=pf.FlightStreamReader)
        param_batch = pa.record_batch([
            pa.array([30]),  # age = 30
            pa.array([1])    # id = 1
        ], schema=pa.schema([
            pa.field("age", pa.int32()),
            pa.field("id", pa.int64())
        ]))
        
        # Mock reader.read_chunk() to return parameter batch then stop
        reader.read_chunk.side_effect = [
            Mock(data=param_batch),
            StopIteration()
        ]
        
        writer = Mock(spec=pf.FlightMetadataWriter)
        
        # Mock backend response
        server.backend.execute_update.return_value = 1
        
        server.do_put(context, descriptor, reader, writer)
        
        # Verify parameters were stored
        assert server.prepared_statements[handle_key]["parameters"] is not None
        
        # Verify writer was called
        writer.write.assert_called_once()

    def test_do_put_prepared_statement_query_binding(self, server):
        """Test do_put for prepared statement parameter binding."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Setup prepared statement
        test_handle = uuid.uuid4().bytes
        handle_key = test_handle.hex()
        
        server.prepared_statements[handle_key] = {
            "sql": "SELECT * FROM users WHERE age > ?",
            "schema": pa.schema([pa.field("result", pa.string())]),
            "transaction_id": "",
            "parameters": None
        }
        
        # Create protobuf command
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_QUERY_TYPE_URL
        any_msg.value = bytes([0x0A]) + bytes([len(test_handle)]) + test_handle
        
        descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())
        
        # Mock reader with parameter data
        reader = Mock(spec=pf.FlightStreamReader)
        param_batch = pa.record_batch([
            pa.array([25])  # age > 25
        ], schema=pa.schema([pa.field("age", pa.int32())]))
        
        reader.read_chunk.side_effect = [
            Mock(data=param_batch),
            StopIteration()
        ]
        
        writer = Mock(spec=pf.FlightMetadataWriter)
        
        server.do_put(context, descriptor, reader, writer)
        
        # Verify parameters were stored
        assert len(server.prepared_statements[handle_key]["parameters"]) == 1
        
        # Verify acknowledgment was sent
        writer.write.assert_called_once_with(pa.py_buffer(b""))

    def test_do_put_path_upload(self, server):
        """Test do_put for PATH descriptor table uploads."""
        context = Mock(spec=pf.ServerCallContext)
        
        descriptor = pf.FlightDescriptor.for_path("new_table")
        
        # Mock reader with table data
        reader = Mock(spec=pf.FlightStreamReader)
        reader.schema = pa.schema([
            pa.field("id", pa.int64()),
            pa.field("name", pa.string())
        ])
        
        # Mock data chunks
        chunk1 = Mock()
        chunk1.data = pa.record_batch([
            pa.array([1, 2]),
            pa.array(["Alice", "Bob"])
        ], schema=reader.schema)
        
        chunk2 = Mock()
        chunk2.data = None  # End of stream
        
        reader.read_chunk.side_effect = [chunk1, StopIteration()]
        
        writer = Mock(spec=pf.FlightMetadataWriter)
        
        server.do_put(context, descriptor, reader, writer)
        
        # Verify backend methods were called
        server.backend.create_table_from_schema.assert_called_once_with("new_table", reader.schema)
        server.backend.append_table_from_arrow.assert_called_once()
        
        # Verify acknowledgment was sent
        writer.write.assert_called_once()

    def test_do_put_unsupported_command(self, server):
        """Test do_put with unsupported command type."""
        context = Mock(spec=pf.ServerCallContext)
        
        any_msg = any_pb2.Any()
        any_msg.type_url = "type.googleapis.com/arrow.flight.protocol.sql.UnsupportedCommand"
        any_msg.value = b""
        
        descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())
        reader = Mock(spec=pf.FlightStreamReader)
        writer = Mock(spec=pf.FlightMetadataWriter)
        
        with pytest.raises(NotImplementedError, match="Unsupported command type for DoPut"):
            server.do_put(context, descriptor, reader, writer)

    def test_do_put_invalid_command(self, server):
        """Test do_put with invalid command data."""
        context = Mock(spec=pf.ServerCallContext)
        
        descriptor = pf.FlightDescriptor.for_command(b"invalid_protobuf")
        reader = Mock(spec=pf.FlightStreamReader)
        writer = Mock(spec=pf.FlightMetadataWriter)
        
        with pytest.raises(ValueError, match="Failed to parse command"):
            server.do_put(context, descriptor, reader, writer)


class TestPhase2PreparedStatements:
    """Test Phase 2 prepared statement management via do_action."""

    def test_create_prepared_statement_select(self, server):
        """Test creating a prepared statement for SELECT queries.""" 
        context = Mock(spec=pf.ServerCallContext)
        
        # Mock protobuf request
        with patch('src.mpzsql.flightsql.minimal.ActionCreatePreparedStatementRequest') as mock_req:
            mock_request = Mock()
            mock_request.query = "SELECT * FROM users WHERE id = ?"
            mock_req.return_value = mock_request
            
            # Mock backend schema response
            test_schema = pa.schema([
                pa.field("id", pa.int64()),
                pa.field("name", pa.string())
            ])
            server.backend.get_statement_schema.return_value = test_schema
            
            action_body = b"mock_request_data"
            action = pf.Action("CreatePreparedStatement", pa.py_buffer(action_body))
            
            results = list(server.do_action(context, action))
            
            assert len(results) == 1
            result = results[0]
            assert isinstance(result, pf.Result)
            
            # Verify prepared statement was stored
            assert len(server.prepared_statements) == 1
            
            # Verify the stored statement
            stored_stmt = list(server.prepared_statements.values())[0]
            assert stored_stmt["sql"] == "SELECT * FROM users WHERE id = ?"
            assert stored_stmt["schema"] == test_schema

    def test_create_prepared_statement_update(self, server):
        """Test creating a prepared statement for UPDATE queries."""
        context = Mock(spec=pf.ServerCallContext)
        
        with patch('src.mpzsql.flightsql.minimal.ActionCreatePreparedStatementRequest') as mock_req:
            mock_request = Mock()
            mock_request.query = "UPDATE users SET age = ? WHERE id = ?"
            mock_req.return_value = mock_request
            
            action_body = b"mock_request_data"
            action = pf.Action("CreatePreparedStatement", pa.py_buffer(action_body))
            
            results = list(server.do_action(context, action))
            
            assert len(results) == 1
            
            # Verify prepared statement was stored
            assert len(server.prepared_statements) == 1
            
            stored_stmt = list(server.prepared_statements.values())[0]
            assert stored_stmt["sql"] == "UPDATE users SET age = ? WHERE id = ?"
            # UPDATE queries should not have schema set
            assert stored_stmt["schema"] is None

    def test_close_prepared_statement(self, server):
        """Test closing a prepared statement."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Setup existing prepared statement
        test_handle = uuid.uuid4().bytes
        handle_key = test_handle.hex()
        
        server.prepared_statements[handle_key] = {
            "sql": "SELECT * FROM users",
            "schema": pa.schema([pa.field("id", pa.int64())]),
            "transaction_id": "",
            "parameters": None
        }
        
        with patch('src.mpzsql.flightsql.minimal.ActionClosePreparedStatementRequest') as mock_req:
            mock_request = Mock()
            mock_request.prepared_statement_handle = test_handle
            mock_req.return_value = mock_request
            
            action_body = b"mock_request_data"
            action = pf.Action("ClosePreparedStatement", pa.py_buffer(action_body))
            
            results = list(server.do_action(context, action))
            
            assert len(results) == 1
            
            # Verify prepared statement was removed
            assert handle_key not in server.prepared_statements

    def test_close_nonexistent_prepared_statement(self, server):
        """Test closing a non-existent prepared statement."""
        context = Mock(spec=pf.ServerCallContext)
        
        with patch('src.mpzsql.flightsql.minimal.ActionClosePreparedStatementRequest') as mock_req:
            mock_request = Mock()
            mock_request.prepared_statement_handle = uuid.uuid4().bytes
            mock_req.return_value = mock_request
            
            action_body = b"mock_request_data"
            action = pf.Action("ClosePreparedStatement", pa.py_buffer(action_body))
            
            # Should not raise error, just log warning
            results = list(server.do_action(context, action))
            assert len(results) == 1

    def test_prepared_statement_lifecycle(self, server):
        """Test complete prepared statement lifecycle: create -> bind -> execute -> close."""
        context = Mock(spec=pf.ServerCallContext)
        
        # 1. Create prepared statement
        with patch('src.mpzsql.flightsql.minimal.ActionCreatePreparedStatementRequest') as mock_req:
            mock_request = Mock()
            mock_request.query = "SELECT * FROM users WHERE age > ?"
            mock_req.return_value = mock_request
            
            test_schema = pa.schema([pa.field("id", pa.int64()), pa.field("name", pa.string())])
            server.backend.get_statement_schema.return_value = test_schema
            
            action_body = b"mock_request_data"
            action = pf.Action("CreatePreparedStatement", pa.py_buffer(action_body))
            
            results = list(server.do_action(context, action))
            assert len(results) == 1
            assert len(server.prepared_statements) == 1
            
            # Get the handle
            handle_key = list(server.prepared_statements.keys())[0]
            test_handle = bytes.fromhex(handle_key)
        
        # 2. Bind parameters via do_put
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_QUERY_TYPE_URL
        any_msg.value = bytes([0x0A]) + bytes([len(test_handle)]) + test_handle
        
        descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())
        reader = Mock(spec=pf.FlightStreamReader)
        
        param_batch = pa.record_batch([pa.array([25])], schema=pa.schema([pa.field("age", pa.int32())]))
        reader.read_chunk.side_effect = [Mock(data=param_batch), StopIteration()]
        
        writer = Mock(spec=pf.FlightMetadataWriter)
        
        server.do_put(context, descriptor, reader, writer)
        
        # Verify parameters were stored
        assert server.prepared_statements[handle_key]["parameters"] is not None
        
        # 3. Execute via do_get
        ticket = pf.Ticket(any_msg.SerializeToString())
        
        result_table = pa.table({"id": [1, 2], "name": ["Alice", "Bob"]})
        server.backend.execute_query.return_value = result_table
        
        stream = server.do_get(context, ticket)
        assert isinstance(stream, pf.FlightDataStream)
        
        # 4. Close prepared statement
        with patch('src.mpzsql.flightsql.minimal.ActionClosePreparedStatementRequest') as mock_close_req:
            mock_close_request = Mock()
            mock_close_request.prepared_statement_handle = test_handle
            mock_close_req.return_value = mock_close_request
            
            close_action = pf.Action("ClosePreparedStatement", pa.py_buffer(b"close_data"))
            results = list(server.do_action(context, close_action))
            
            # Verify prepared statement was removed
            assert handle_key not in server.prepared_statements


class TestPhase2TransactionManagement:
    """Test Phase 2 transaction management via do_action."""

    def test_begin_transaction(self, server):
        """Test beginning a transaction."""
        context = Mock(spec=pf.ServerCallContext)
        
        with patch('src.mpzsql.flightsql.minimal.ActionBeginTransactionRequest') as mock_req:
            mock_request = Mock()
            mock_req.return_value = mock_request
            
            action_body = b"mock_request_data"
            action = pf.Action("BeginTransaction", pa.py_buffer(action_body))
            
            results = list(server.do_action(context, action))
            
            assert len(results) == 1
            result = results[0]
            assert isinstance(result, pf.Result)
            
            # Verify transaction was created
            assert len(server.open_transactions) == 1
            assert server._transaction_counter == 1
            
            # Verify transaction ID format
            transaction_id = list(server.open_transactions.keys())[0]
            assert transaction_id.startswith("txn_")
            assert server.open_transactions[transaction_id] == "active"

    def test_end_transaction_commit(self, server):
        """Test ending a transaction with commit."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Setup existing transaction
        server.open_transactions["txn_1"] = "active"
        
        with patch('src.mpzsql.flightsql.minimal.ActionEndTransactionRequest') as mock_req:
            mock_request = Mock()
            mock_request.transaction_id = "txn_1"
            mock_request.action = 0  # COMMIT
            mock_req.return_value = mock_request
            
            action_body = b"mock_request_data"
            action = pf.Action("EndTransaction", pa.py_buffer(action_body))
            
            results = list(server.do_action(context, action))
            
            assert len(results) == 1
            
            # Verify transaction was removed
            assert "txn_1" not in server.open_transactions

    def test_end_transaction_rollback(self, server):
        """Test ending a transaction with rollback."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Setup existing transaction
        server.open_transactions["txn_1"] = "active"
        
        with patch('src.mpzsql.flightsql.minimal.ActionEndTransactionRequest') as mock_req:
            mock_request = Mock()
            mock_request.transaction_id = "txn_1"
            mock_request.action = 1  # ROLLBACK
            mock_req.return_value = mock_request
            
            action_body = b"mock_request_data"
            action = pf.Action("EndTransaction", pa.py_buffer(action_body))
            
            results = list(server.do_action(context, action))
            
            assert len(results) == 1
            
            # Verify transaction was removed
            assert "txn_1" not in server.open_transactions

    def test_end_unknown_transaction(self, server):
        """Test ending a transaction with unknown ID."""
        context = Mock(spec=pf.ServerCallContext)
        
        with patch('src.mpzsql.flightsql.minimal.ActionEndTransactionRequest') as mock_req:
            mock_request = Mock()
            mock_request.transaction_id = "unknown_txn"
            mock_request.action = 0  # COMMIT
            mock_req.return_value = mock_request
            
            action_body = b"mock_request_data"
            action = pf.Action("EndTransaction", pa.py_buffer(action_body))
            
            with pytest.raises(ValueError, match="Unknown transaction ID"):
                list(server.do_action(context, action))

    def test_close_session(self, server):
        """Test closing a session and cleaning up resources."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Setup session state
        server.prepared_statements["handle1"] = {"sql": "SELECT 1"}
        server.open_transactions["txn1"] = "active"
        server.open_sessions["session1"] = {"user": "test"}
        
        action_body = b""  # CloseSession has empty body
        action = pf.Action("CloseSession", pa.py_buffer(action_body))
        
        results = list(server.do_action(context, action))
        
        assert len(results) == 1
        
        # Verify all session state was cleaned up
        assert len(server.prepared_statements) == 0
        assert len(server.open_transactions) == 0
        assert len(server.open_sessions) == 0

    def test_transaction_lifecycle(self, server):
        """Test complete transaction lifecycle: begin -> operations -> commit."""
        context = Mock(spec=pf.ServerCallContext)
        
        # 1. Begin transaction
        with patch('src.mpzsql.flightsql.minimal.ActionBeginTransactionRequest') as mock_begin_req:
            mock_begin_request = Mock()
            mock_begin_req.return_value = mock_begin_request
            
            begin_action = pf.Action("BeginTransaction", pa.py_buffer(b"begin_data"))
            results = list(server.do_action(context, begin_action))
            
            assert len(results) == 1
            assert len(server.open_transactions) == 1
            
            transaction_id = list(server.open_transactions.keys())[0]
        
        # 2. Perform operations within transaction (this would normally involve SQL commands)
        # For this test, we'll just verify the transaction exists
        assert server.open_transactions[transaction_id] == "active"
        
        # 3. Commit transaction
        with patch('src.mpzsql.flightsql.minimal.ActionEndTransactionRequest') as mock_end_req:
            mock_end_request = Mock()
            mock_end_request.transaction_id = transaction_id
            mock_end_request.action = 0  # COMMIT
            mock_end_req.return_value = mock_end_request
            
            end_action = pf.Action("EndTransaction", pa.py_buffer(b"end_data"))
            results = list(server.do_action(context, end_action))
            
            assert len(results) == 1
            
            # Verify transaction was removed
            assert transaction_id not in server.open_transactions


class TestPhase2Integration:
    """Test Phase 2 methods working together in realistic scenarios."""

    def test_complete_query_workflow(self, server):
        """Test complete query workflow: get_flight_info -> do_get."""
        context = Mock(spec=pf.ServerCallContext)
        
        # 1. Get flight info for a query
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_STATEMENT_QUERY_TYPE_URL
        
        sql_query = "SELECT * FROM users WHERE age > 25"
        query_encoded = sql_query.encode("utf-8")
        any_msg.value = bytes([0x0A]) + bytes([len(query_encoded)]) + query_encoded
        
        descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())
        
        test_schema = pa.schema([pa.field("id", pa.int64()), pa.field("name", pa.string())])
        server.backend.get_statement_schema.return_value = test_schema
        
        flight_info = server.get_flight_info(context, descriptor)
        
        assert isinstance(flight_info, pf.FlightInfo)
        assert flight_info.schema == test_schema
        assert len(flight_info.endpoints) == 1
        
        # 2. Execute the query using the ticket from flight info
        ticket = flight_info.endpoints[0].ticket
        
        result_table = pa.table({
            "id": [1, 2],
            "name": ["Alice", "Bob"]
        })
        server.backend.execute_query.return_value = result_table
        
        stream = server.do_get(context, ticket)
        assert isinstance(stream, pf.FlightDataStream)

    def test_complete_update_workflow(self, server):
        """Test complete update workflow: get_flight_info -> do_put."""
        context = Mock(spec=pf.ServerCallContext)
        
        # 1. Get flight info for an update
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_STATEMENT_UPDATE_TYPE_URL
        
        sql_update = "INSERT INTO users (name, age) VALUES ('Charlie', 35)"
        update_encoded = sql_update.encode("utf-8")
        any_msg.value = bytes([0x0A]) + bytes([len(update_encoded)]) + update_encoded
        
        descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())
        
        # 2. Execute the update
        reader = Mock(spec=pf.FlightStreamReader)
        writer = Mock(spec=pf.FlightMetadataWriter)
        
        server.backend.execute_update.return_value = 1
        
        server.do_put(context, descriptor, reader, writer)
        
        # Verify update was executed and result written
        server.backend.execute_update.assert_called_once()
        writer.write.assert_called_once()

    def test_metadata_discovery_workflow(self, server):
        """Test metadata discovery workflow: catalogs -> schemas -> tables -> columns."""
        context = Mock(spec=pf.ServerCallContext)
        
        # 1. Get catalogs
        catalogs_cmd = any_pb2.Any()
        catalogs_cmd.type_url = FlightSQLProtobuf.COMMAND_GET_CATALOGS_TYPE_URL
        catalogs_cmd.value = b""
        
        catalogs_ticket = pf.Ticket(catalogs_cmd.SerializeToString())
        catalogs_stream = server.do_get(context, catalogs_ticket)
        assert isinstance(catalogs_stream, pf.FlightDataStream)
        
        # 2. Get schemas
        schemas_cmd = any_pb2.Any()
        schemas_cmd.type_url = FlightSQLProtobuf.COMMAND_GET_DB_SCHEMAS_TYPE_URL
        schemas_cmd.value = b""
        
        schemas_ticket = pf.Ticket(schemas_cmd.SerializeToString())
        schemas_stream = server.do_get(context, schemas_ticket)
        assert isinstance(schemas_stream, pf.FlightDataStream)
        
        # 3. Get tables
        tables_cmd = any_pb2.Any()
        tables_cmd.type_url = FlightSQLProtobuf.COMMAND_GET_TABLES_TYPE_URL
        tables_cmd.value = b""
        
        tables_ticket = pf.Ticket(tables_cmd.SerializeToString())
        tables_stream = server.do_get(context, tables_ticket)
        assert isinstance(tables_stream, pf.FlightDataStream)
        
        # 4. Get columns
        columns_cmd = any_pb2.Any()
        columns_cmd.type_url = FlightSQLProtobuf.COMMAND_GET_COLUMNS_TYPE_URL
        columns_cmd.value = b""
        
        columns_ticket = pf.Ticket(columns_cmd.SerializeToString())
        columns_stream = server.do_get(context, columns_ticket)
        assert isinstance(columns_stream, pf.FlightDataStream)

    def test_transaction_with_operations(self, server):
        """Test transaction workflow with actual operations."""
        context = Mock(spec=pf.ServerCallContext)
        
        # 1. Begin transaction
        with patch('src.mpzsql.flightsql.minimal.ActionBeginTransactionRequest') as mock_begin_req:
            mock_begin_request = Mock()
            mock_begin_req.return_value = mock_begin_request
            
            begin_action = pf.Action("BeginTransaction", pa.py_buffer(b"begin_data"))
            results = list(server.do_action(context, begin_action))
            
            transaction_id = list(server.open_transactions.keys())[0]
        
        # 2. Perform update operation
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_STATEMENT_UPDATE_TYPE_URL
        
        sql_update = "UPDATE users SET age = 26 WHERE id = 1"
        update_encoded = sql_update.encode("utf-8")
        any_msg.value = bytes([0x0A]) + bytes([len(update_encoded)]) + update_encoded
        
        descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())
        reader = Mock(spec=pf.FlightStreamReader)
        writer = Mock(spec=pf.FlightMetadataWriter)
        
        server.backend.execute_update.return_value = 1
        server.do_put(context, descriptor, reader, writer)
        
        # 3. Commit transaction
        with patch('src.mpzsql.flightsql.minimal.ActionEndTransactionRequest') as mock_end_req:
            mock_end_request = Mock()
            mock_end_request.transaction_id = transaction_id
            mock_end_request.action = 0  # COMMIT
            mock_end_req.return_value = mock_end_request
            
            end_action = pf.Action("EndTransaction", pa.py_buffer(b"end_data"))
            list(server.do_action(context, end_action))
            
            # Verify transaction completed
            assert transaction_id not in server.open_transactions


class TestPhase2ErrorHandling:
    """Test Phase 2 error handling and edge cases."""

    def test_backend_failure_in_do_get(self, server):
        """Test backend failure during do_get operation."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Setup backend to fail
        server.backend.execute_query.side_effect = Exception("Database connection lost")
        
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_STATEMENT_QUERY_TYPE_URL
        
        sql_query = "SELECT * FROM users"
        query_encoded = sql_query.encode("utf-8")
        any_msg.value = bytes([0x0A]) + bytes([len(query_encoded)]) + query_encoded
        
        ticket = pf.Ticket(any_msg.SerializeToString())
        
        # The server should return a FlightDataStream even on error (error handling is internal)
        stream = server.do_get(context, ticket)
        assert isinstance(stream, pf.FlightDataStream)

    def test_backend_failure_in_do_put(self, server):
        """Test backend failure during do_put operation."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Setup backend to fail
        server.backend.execute_update.side_effect = Exception("Table locked")
        
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_STATEMENT_UPDATE_TYPE_URL
        
        sql_update = "DELETE FROM users WHERE id = 1"
        update_encoded = sql_update.encode("utf-8")
        any_msg.value = bytes([0x0A]) + bytes([len(update_encoded)]) + update_encoded
        
        descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())
        reader = Mock(spec=pf.FlightStreamReader)
        writer = Mock(spec=pf.FlightMetadataWriter)
        
        with pytest.raises(Exception, match="Table locked"):
            server.do_put(context, descriptor, reader, writer)

    def test_malformed_prepared_statement_handle(self, server):
        """Test handling of malformed prepared statement handles."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Create command with invalid handle
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_QUERY_TYPE_URL
        any_msg.value = b"\x0A\x10invalid_handle_data"  # Invalid handle
        
        ticket = pf.Ticket(any_msg.SerializeToString())
        
        # The server should handle the error and return a FlightDataStream (with error info)
        stream = server.do_get(context, ticket)
        assert isinstance(stream, pf.FlightDataStream)

    def test_concurrent_transaction_operations(self, server):
        """Test concurrent transaction operations for thread safety."""
        context = Mock(spec=pf.ServerCallContext)
        
        def create_transaction():
            with patch('src.mpzsql.flightsql.minimal.ActionBeginTransactionRequest') as mock_req:
                mock_request = Mock()
                mock_req.return_value = mock_request
                
                action = pf.Action("BeginTransaction", pa.py_buffer(b"data"))
                list(server.do_action(context, action))
        
        # Run multiple transactions concurrently
        threads = [threading.Thread(target=create_transaction) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        
        # Verify all transactions were created with unique IDs
        assert len(server.open_transactions) == 5
        assert server._transaction_counter == 5
        
        # Verify all transaction IDs are unique
        transaction_ids = list(server.open_transactions.keys())
        assert len(set(transaction_ids)) == 5

    def test_large_parameter_batch_handling(self, server):
        """Test handling of large parameter batches."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Setup prepared statement
        test_handle = uuid.uuid4().bytes
        handle_key = test_handle.hex()
        
        server.prepared_statements[handle_key] = {
            "sql": "INSERT INTO users (name, age) VALUES (?, ?)",
            "schema": None,
            "transaction_id": "",
            "parameters": None
        }
        
        # Create large parameter batch
        num_params = 1000
        names = [f"User{i}" for i in range(num_params)]
        ages = list(range(20, 20 + num_params))
        
        large_batch = pa.record_batch([
            pa.array(names),
            pa.array(ages)
        ], schema=pa.schema([
            pa.field("name", pa.string()),
            pa.field("age", pa.int32())
        ]))
        
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_UPDATE_TYPE_URL
        any_msg.value = bytes([0x0A]) + bytes([len(test_handle)]) + test_handle
        
        descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())
        reader = Mock(spec=pf.FlightStreamReader)
        reader.read_chunk.side_effect = [Mock(data=large_batch), StopIteration()]
        
        writer = Mock(spec=pf.FlightMetadataWriter)
        server.backend.execute_update.return_value = num_params
        
        server.do_put(context, descriptor, reader, writer)
        
        # Verify large batch was handled
        assert len(server.prepared_statements[handle_key]["parameters"]) == 1
        writer.write.assert_called_once()


class TestPhase2PerformanceAndScalability:
    """Test Phase 2 performance characteristics and scalability."""

    def test_multiple_concurrent_queries(self, server):
        """Test handling multiple concurrent queries."""
        context = Mock(spec=pf.ServerCallContext)
        
        def execute_query(query_id):
            any_msg = any_pb2.Any()
            any_msg.type_url = FlightSQLProtobuf.COMMAND_STATEMENT_QUERY_TYPE_URL
            
            sql_query = f"SELECT * FROM users WHERE id = {query_id}"
            query_encoded = sql_query.encode("utf-8")
            any_msg.value = bytes([0x0A]) + bytes([len(query_encoded)]) + query_encoded
            
            ticket = pf.Ticket(any_msg.SerializeToString())
            
            # Each query returns different data
            result_table = pa.table({
                "id": [query_id],
                "name": [f"User{query_id}"]
            })
            server.backend.execute_query.return_value = result_table
            
            stream = server.do_get(context, ticket)
            return stream  # Return the stream itself, not data
        
        # Execute multiple queries concurrently
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(execute_query, i) for i in range(1, 11)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        # Verify all queries completed successfully
        assert len(results) == 10
        for stream in results:
            assert isinstance(stream, pf.FlightDataStream)

    def test_prepared_statement_cache_management(self, server):
        """Test prepared statement cache behavior with many statements."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Create many prepared statements
        num_statements = 100
        handles = []
        
        for i in range(num_statements):
            with patch('src.mpzsql.flightsql.minimal.ActionCreatePreparedStatementRequest') as mock_req:
                mock_request = Mock()
                mock_request.query = f"SELECT * FROM table{i} WHERE id = ?"
                mock_req.return_value = mock_request
                
                test_schema = pa.schema([pa.field("id", pa.int64())])
                server.backend.get_statement_schema.return_value = test_schema
                
                action = pf.Action("CreatePreparedStatement", pa.py_buffer(b"data"))
                results = list(server.do_action(context, action))
                
                # Extract handle from result
                handle_key = list(server.prepared_statements.keys())[-1]
                handles.append(handle_key)
        
        # Verify all statements were stored
        assert len(server.prepared_statements) == num_statements
        
        # Close all statements
        for i, handle_key in enumerate(handles):
            with patch('src.mpzsql.flightsql.minimal.ActionClosePreparedStatementRequest') as mock_req:
                mock_request = Mock()
                mock_request.prepared_statement_handle = bytes.fromhex(handle_key)
                mock_req.return_value = mock_request
                
                action = pf.Action("ClosePreparedStatement", pa.py_buffer(b"data"))
                list(server.do_action(context, action))
        
        # Verify all statements were removed
        assert len(server.prepared_statements) == 0

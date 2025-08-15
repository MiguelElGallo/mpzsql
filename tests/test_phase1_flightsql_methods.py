"""
Comprehensive test suite for Phase 1 FlightSQL methods.

This module tests the three core Phase 1 FlightSQL methods that were implemented
in MinimalFlightSQLServer:
1. list_flights - Lists available Flight endpoints
2. get_schema - Retrieves schema information for commands  
3. handshake - Performs authentication handshake

These tests verify the complete Phase 1 FlightSQL implementation including
both PATH and CMD descriptor support, proper schema generation, and
authentication capabilities.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from google.protobuf import any_pb2

import pyarrow as pa
import pyarrow.flight as pf

from src.mpzsql.backends.base import DatabaseBackend
from src.mpzsql.config import ServerConfig
from src.mpzsql.flightsql.minimal import MinimalFlightSQLServer
from src.mpzsql.flightsql.protobuf import FlightSQLProtobuf, parse_any_command


@pytest.fixture
def mock_backend():
    """Create a mock database backend for testing."""
    backend = Mock(spec=DatabaseBackend)
    
    # Mock basic query execution
    backend.execute_query.return_value = pa.table(
        {"col1": [1, 2, 3], "col2": ["a", "b", "c"]}
    )
    
    # Mock schema methods
    backend.get_statement_schema.return_value = pa.schema([
        pa.field("col1", pa.int64()),
        pa.field("col2", pa.string())
    ])
    
    # Mock metadata methods
    backend.get_catalogs.return_value = pa.table({"catalog_name": ["default", "main", "test"]})
    backend.get_schemas.return_value = [("default", "main")]
    backend.get_db_schemas.return_value = pa.table({
        "catalog_name": ["default", "default"], 
        "schema_name": ["main", "information_schema"]
    })
    backend.get_tables.return_value = pa.table({
        "catalog_name": ["default"],
        "schema_name": ["main"],
        "table_name": ["test_table"],
        "table_type": ["TABLE"],
    })
    
    # Make it a MagicMock to support additional methods that might be called
    backend = MagicMock(spec=DatabaseBackend)
    backend.execute_query.return_value = pa.table(
        {"col1": [1, 2, 3], "col2": ["a", "b", "c"]}
    )
    backend.get_statement_schema.return_value = pa.schema([
        pa.field("col1", pa.int64()),
        pa.field("col2", pa.string())
    ])
    backend.get_catalogs.return_value = pa.table({"catalog_name": ["default", "main", "test"]})
    
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


class TestPhase1ListFlights:
    """Test Phase 1 list_flights method implementation."""

    def test_list_flights_basic(self, server):
        """Test basic list_flights functionality."""
        context = Mock(spec=pf.ServerCallContext)
        criteria = b""  # Empty criteria
        
        flights = list(server.list_flights(context, criteria))
        
        # Should return metadata endpoints
        assert len(flights) == 5
        flight_paths = [flight.descriptor.path[0].decode() for flight in flights]
        
        expected_paths = ["catalogs", "schemas", "tables", "table_types", "sql_info"]
        for expected_path in expected_paths:
            assert expected_path in flight_paths

    def test_list_flights_metadata_endpoints(self, server):
        """Test that list_flights returns correct metadata endpoints."""
        context = Mock(spec=pf.ServerCallContext)
        criteria = b""
        
        flights = list(server.list_flights(context, criteria))
        
        # Verify each flight has proper structure
        for flight in flights:
            assert isinstance(flight, pf.FlightInfo)
            assert flight.descriptor.descriptor_type == pf.DescriptorType.PATH
            assert len(flight.descriptor.path) == 1
            assert len(flight.endpoints) == 1
            assert flight.schema is not None
            assert len(flight.schema) == 2  # name, description fields
            assert flight.schema.field(0).name == "name"
            assert flight.schema.field(1).name == "description"

    def test_list_flights_endpoint_structure(self, server):
        """Test that flight endpoints have correct structure."""
        context = Mock(spec=pf.ServerCallContext)
        criteria = b""
        
        flights = list(server.list_flights(context, criteria))
        
        for flight in flights:
            endpoint = flight.endpoints[0]
            assert isinstance(endpoint, pf.FlightEndpoint)
            assert endpoint.ticket is not None
            assert len(endpoint.locations) > 0 if hasattr(server, 'advertised_location') else True

    def test_list_flights_with_criteria(self, server):
        """Test list_flights with non-empty criteria."""
        context = Mock(spec=pf.ServerCallContext)
        criteria = b"some_filter_criteria"
        
        # Should still return all flights (criteria not implemented yet)
        flights = list(server.list_flights(context, criteria))
        assert len(flights) == 5

    def test_list_flights_error_handling(self, server):
        """Test list_flights error handling."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Mock an error by setting advertised_location to invalid type
        original_location = server.advertised_location
        server.advertised_location = Mock()  # Invalid location type
        
        try:
            # Should handle errors gracefully by raising the error
            with pytest.raises(TypeError, match="Argument locations must contain Location instances"):
                list(server.list_flights(context, b""))
        finally:
            # Restore original location
            server.advertised_location = original_location


class TestPhase1GetSchema:
    """Test Phase 1 get_schema method implementation."""

    def test_get_schema_path_descriptor_catalogs(self, server):
        """Test get_schema with PATH descriptor for catalogs."""
        context = Mock(spec=pf.ServerCallContext)
        descriptor = pf.FlightDescriptor.for_path("catalogs")
        
        schema = server.get_schema(context, descriptor)
        
        assert isinstance(schema, pa.Schema)
        # Should return catalogs schema
        assert len(schema) >= 1
        # Verify it contains catalog-related fields
        field_names = [field.name for field in schema]
        assert any("catalog" in name.lower() for name in field_names)

    def test_get_schema_path_descriptor_schemas(self, server):
        """Test get_schema with PATH descriptor for schemas."""
        context = Mock(spec=pf.ServerCallContext)
        descriptor = pf.FlightDescriptor.for_path("schemas")
        
        schema = server.get_schema(context, descriptor)
        
        assert isinstance(schema, pa.Schema)
        assert len(schema) >= 1
        field_names = [field.name for field in schema]
        assert any("schema" in name.lower() for name in field_names)

    def test_get_schema_path_descriptor_tables(self, server):
        """Test get_schema with PATH descriptor for tables."""
        context = Mock(spec=pf.ServerCallContext)
        descriptor = pf.FlightDescriptor.for_path("tables")
        
        schema = server.get_schema(context, descriptor)
        
        assert isinstance(schema, pa.Schema)
        assert len(schema) >= 1
        field_names = [field.name for field in schema]
        assert any("table" in name.lower() for name in field_names)

    def test_get_schema_path_descriptor_table_types(self, server):
        """Test get_schema with PATH descriptor for table_types."""
        context = Mock(spec=pf.ServerCallContext)
        descriptor = pf.FlightDescriptor.for_path("table_types")
        
        schema = server.get_schema(context, descriptor)
        
        assert isinstance(schema, pa.Schema)
        assert len(schema) >= 1
        field_names = [field.name for field in schema]
        assert any("table_type" in name.lower() for name in field_names)

    def test_get_schema_path_descriptor_sql_info(self, server):
        """Test get_schema with PATH descriptor for sql_info."""
        context = Mock(spec=pf.ServerCallContext)
        descriptor = pf.FlightDescriptor.for_path("sql_info")
        
        schema = server.get_schema(context, descriptor)
        
        assert isinstance(schema, pa.Schema)
        assert len(schema) >= 1
        field_names = [field.name for field in schema]
        assert any("info" in name.lower() for name in field_names)

    def test_get_schema_path_descriptor_unknown_path(self, server):
        """Test get_schema with unknown PATH descriptor."""
        context = Mock(spec=pf.ServerCallContext)
        descriptor = pf.FlightDescriptor.for_path("unknown_path")
        
        schema = server.get_schema(context, descriptor)
        
        # Should return generic schema for unknown paths
        assert isinstance(schema, pa.Schema)
        assert len(schema) == 2
        assert schema.field(0).name == "name"
        assert schema.field(1).name == "value"

    def test_get_schema_path_descriptor_empty_path(self, server):
        """Test get_schema with empty PATH descriptor."""
        context = Mock(spec=pf.ServerCallContext)
        descriptor = Mock(spec=pf.FlightDescriptor)
        descriptor.descriptor_type = pf.DescriptorType.PATH
        descriptor.path = []
        
        with pytest.raises(ValueError, match="Empty path in descriptor"):
            server.get_schema(context, descriptor)

    def test_get_schema_path_descriptor_bytes_conversion(self, server):
        """Test get_schema handles bytes path parts correctly."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Create descriptor with mixed bytes/string path
        descriptor = Mock(spec=pf.FlightDescriptor)
        descriptor.descriptor_type = pf.DescriptorType.PATH
        descriptor.path = [b"catalogs"]  # bytes instead of string
        
        schema = server.get_schema(context, descriptor)
        
        assert isinstance(schema, pa.Schema)
        assert len(schema) >= 1

    def test_get_schema_cmd_descriptor_statement_query(self, server):
        """Test get_schema with CMD descriptor for statement query."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Create proper protobuf Any message for CommandStatementQuery
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_STATEMENT_QUERY_TYPE_URL
        
        # Encode SQL query as protobuf
        sql_query = "SELECT * FROM test_table"
        query_encoded = sql_query.encode("utf-8")
        any_msg.value = bytes([0x0A]) + bytes([len(query_encoded)]) + query_encoded
        
        descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())
        
        # The server will use its _get_statement_query_schema method which 
        # executes DESCRIBE and parses the result
        # Mock backend to return describe result instead of schema directly
        describe_result = [("test_col", "VARCHAR")]
        server.backend.execute_query.return_value = describe_result
        
        schema = server.get_schema(context, descriptor)
        
        assert isinstance(schema, pa.Schema)
        assert len(schema) == 1
        assert schema.field(0).name == "test_col"
        assert schema.field(0).type == pa.string()

    def test_get_schema_cmd_descriptor_get_catalogs(self, server):
        """Test get_schema with CMD descriptor for GetCatalogs."""
        context = Mock(spec=pf.ServerCallContext)
        
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_GET_CATALOGS_TYPE_URL
        any_msg.value = b""  # Empty value for GetCatalogs
        
        descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())
        
        schema = server.get_schema(context, descriptor)
        
        assert isinstance(schema, pa.Schema)
        # Should contain catalog-related fields
        field_names = [field.name for field in schema]
        assert any("catalog" in name.lower() for name in field_names)

    def test_get_schema_cmd_descriptor_get_db_schemas(self, server):
        """Test get_schema with CMD descriptor for GetDbSchemas."""
        context = Mock(spec=pf.ServerCallContext)
        
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_GET_DB_SCHEMAS_TYPE_URL
        any_msg.value = b""  # Simplified - real implementation would encode parameters
        
        descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())
        
        schema = server.get_schema(context, descriptor)
        
        assert isinstance(schema, pa.Schema)
        field_names = [field.name for field in schema]
        assert any("schema" in name.lower() for name in field_names)

    def test_get_schema_cmd_descriptor_unsupported_command(self, server):
        """Test get_schema with unsupported CMD descriptor."""
        context = Mock(spec=pf.ServerCallContext)
        
        any_msg = any_pb2.Any()
        any_msg.type_url = "type.googleapis.com/arrow.flight.protocol.sql.UnsupportedCommand"
        any_msg.value = b""
        
        descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())
        
        with pytest.raises(NotImplementedError, match="Schema not implemented for command type"):
            server.get_schema(context, descriptor)

    def test_get_schema_unsupported_descriptor_type(self, server):
        """Test get_schema with unsupported descriptor type."""
        context = Mock(spec=pf.ServerCallContext)
        
        descriptor = Mock(spec=pf.FlightDescriptor)
        descriptor.descriptor_type = pf.DescriptorType.UNKNOWN
        
        with pytest.raises(ValueError, match="Unsupported descriptor type"):
            server.get_schema(context, descriptor)

    def test_get_schema_cmd_unparseable_command(self, server):
        """Test get_schema with unparseable CMD descriptor."""
        context = Mock(spec=pf.ServerCallContext)
        
        descriptor = pf.FlightDescriptor.for_command(b"invalid_protobuf_data")
        
        with pytest.raises(ValueError, match="Failed to parse command from descriptor"):
            server.get_schema(context, descriptor)


class TestPhase1Handshake:
    """Test Phase 1 handshake method implementation."""

    def test_handshake_initial_empty_request(self, server):
        """Test handshake with empty initial request."""
        context = Mock(spec=pf.ServerCallContext)
        incoming_bytes = b""
        
        response, peer_identity = server.handshake(context, incoming_bytes)
        
        assert isinstance(response, bytes)
        assert b"MPZSQL Flight Server" in response
        assert peer_identity == "anonymous"

    def test_handshake_with_authentication_data(self, server):
        """Test handshake with authentication data."""
        context = Mock(spec=pf.ServerCallContext)
        incoming_bytes = b"user:password"
        
        response, peer_identity = server.handshake(context, incoming_bytes)
        
        assert isinstance(response, bytes)
        assert b"Authentication accepted" in response
        assert peer_identity.startswith("user_")
        assert peer_identity != "anonymous"

    def test_handshake_with_utf8_auth_data(self, server):
        """Test handshake with UTF-8 authentication data."""
        context = Mock(spec=pf.ServerCallContext)
        incoming_bytes = "test_user:test_password".encode("utf-8")
        
        response, peer_identity = server.handshake(context, incoming_bytes)
        
        assert isinstance(response, bytes)
        assert b"Authentication accepted" in response
        assert peer_identity.startswith("user_")

    def test_handshake_with_invalid_utf8_data(self, server):
        """Test handshake with invalid UTF-8 data."""
        context = Mock(spec=pf.ServerCallContext)
        incoming_bytes = b"\xff\xfe\xfd"  # Invalid UTF-8
        
        response, peer_identity = server.handshake(context, incoming_bytes)
        
        assert isinstance(response, bytes)
        assert b"Authentication accepted" in response
        assert peer_identity == "unknown_user"

    def test_handshake_deterministic_identity(self, server):
        """Test that handshake generates deterministic peer identity for same auth data."""
        context = Mock(spec=pf.ServerCallContext)
        auth_data = b"consistent_user_data"
        
        # Call handshake twice with same data
        response1, identity1 = server.handshake(context, auth_data)
        response2, identity2 = server.handshake(context, auth_data)
        
        # Should generate same identity for same input
        assert identity1 == identity2
        assert identity1.startswith("user_")

    def test_handshake_different_identities(self, server):
        """Test that handshake generates different identities for different auth data."""
        context = Mock(spec=pf.ServerCallContext)
        
        response1, identity1 = server.handshake(context, b"user1:pass1")
        response2, identity2 = server.handshake(context, b"user2:pass2")
        
        # Should generate different identities for different inputs
        assert identity1 != identity2
        assert identity1.startswith("user_")
        assert identity2.startswith("user_")

    def test_handshake_response_format(self, server):
        """Test handshake response format."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Test initial handshake
        response1, identity1 = server.handshake(context, b"")
        assert b"MPZSQL Flight Server v1.0" == response1
        assert identity1 == "anonymous"
        
        # Test auth handshake
        response2, identity2 = server.handshake(context, b"auth_data")
        assert b"Authentication accepted" == response2
        assert identity2 != "anonymous"

    def test_handshake_logging(self, server):
        """Test that handshake performs proper logging."""
        context = Mock(spec=pf.ServerCallContext)
        
        with patch('src.mpzsql.flightsql.minimal.actions_logger') as mock_logger:
            server.handshake(context, b"test_auth")
            
            # Verify logging calls were made
            assert mock_logger.info.called
            
            # Check that the logging includes relevant information
            call_args = [call[0] for call in mock_logger.info.call_args_list]
            assert any("Handshake" in str(args) for args in call_args)


class TestPhase1Integration:
    """Integration tests for Phase 1 methods working together."""

    def test_list_flights_then_get_schema(self, server):
        """Test list_flights followed by get_schema for discovered endpoints."""
        context = Mock(spec=pf.ServerCallContext)
        
        # First, list available flights
        flights = list(server.list_flights(context, b""))
        assert len(flights) > 0
        
        # Then get schema for each flight
        for flight in flights:
            schema = server.get_schema(context, flight.descriptor)
            assert isinstance(schema, pa.Schema)
            assert len(schema) > 0

    def test_handshake_then_list_flights(self, server):
        """Test handshake followed by list_flights (typical client flow)."""
        context = Mock(spec=pf.ServerCallContext)
        
        # First, perform handshake
        response, peer_identity = server.handshake(context, b"client_auth")
        assert isinstance(response, bytes)
        assert peer_identity != "anonymous"
        
        # Then list flights
        flights = list(server.list_flights(context, b""))
        assert len(flights) == 5

    def test_full_phase1_client_flow(self, server):
        """Test complete Phase 1 client flow: handshake -> list_flights -> get_schema."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Step 1: Handshake
        response, peer_identity = server.handshake(context, b"test_client")
        assert b"Authentication accepted" in response
        
        # Step 2: List available flights
        flights = list(server.list_flights(context, b""))
        assert len(flights) == 5
        
        # Step 3: Get schema for a specific flight
        catalogs_flight = next(f for f in flights if f.descriptor.path[0].decode() == "catalogs")
        schema = server.get_schema(context, catalogs_flight.descriptor)
        assert isinstance(schema, pa.Schema)

    def test_error_handling_across_methods(self, server):
        """Test error handling consistency across Phase 1 methods."""
        context = Mock(spec=pf.ServerCallContext)
        
        # All methods should handle context properly
        assert server.handshake(context, b"") is not None
        assert len(list(server.list_flights(context, b""))) > 0
        
        # get_schema should raise appropriate errors for invalid input
        with pytest.raises(ValueError):
            invalid_descriptor = Mock(spec=pf.FlightDescriptor)
            invalid_descriptor.descriptor_type = pf.DescriptorType.UNKNOWN
            server.get_schema(context, invalid_descriptor)


class TestPhase1SchemaHelperMethods:
    """Test the schema helper methods used by get_schema."""

    def test_get_catalogs_schema(self, server):
        """Test _get_catalogs_schema helper method."""
        schema = server._get_catalogs_schema()
        
        assert isinstance(schema, pa.Schema)
        assert len(schema) >= 1
        field_names = [field.name for field in schema]
        assert any("catalog" in name.lower() for name in field_names)

    def test_get_schemas_schema(self, server):
        """Test _get_schemas_schema helper method."""
        schema = server._get_schemas_schema()
        
        assert isinstance(schema, pa.Schema)
        assert len(schema) >= 1
        field_names = [field.name for field in schema]
        assert any("schema" in name.lower() for name in field_names)

    def test_get_tables_schema(self, server):
        """Test _get_tables_schema helper method."""
        schema = server._get_tables_schema()
        
        assert isinstance(schema, pa.Schema)
        assert len(schema) >= 1
        field_names = [field.name for field in schema]
        assert any("table" in name.lower() for name in field_names)

    def test_get_table_types_schema(self, server):
        """Test _get_table_types_schema helper method."""
        schema = server._get_table_types_schema()
        
        assert isinstance(schema, pa.Schema)
        assert len(schema) >= 1
        field_names = [field.name for field in schema]
        assert any("table_type" in name.lower() for name in field_names)

    def test_get_sql_info_schema(self, server):
        """Test _get_sql_info_schema helper method."""
        schema = server._get_sql_info_schema()
        
        assert isinstance(schema, pa.Schema)
        assert len(schema) >= 1
        field_names = [field.name for field in schema]
        assert any("info" in name.lower() for name in field_names)

    def test_get_statement_query_schema(self, server):
        """Test _get_statement_query_schema helper method."""
        test_query = "SELECT col1, col2 FROM test_table"
        
        # Mock the backend's describe functionality
        describe_result = [
            ("col1", "INTEGER", None),
            ("col2", "VARCHAR", None)
        ]
        server.backend.execute_query.return_value = describe_result
        
        schema = server._get_statement_query_schema(test_query)
        
        assert isinstance(schema, pa.Schema)
        assert len(schema) == 2
        assert schema.field(0).name == "col1"
        assert schema.field(1).name == "col2"


class TestPhase1EdgeCases:
    """Test edge cases and boundary conditions for Phase 1 methods."""

    def test_list_flights_large_criteria(self, server):
        """Test list_flights with large criteria data."""
        context = Mock(spec=pf.ServerCallContext)
        large_criteria = b"x" * 10000  # 10KB criteria
        
        flights = list(server.list_flights(context, large_criteria))
        assert len(flights) == 5  # Should still return standard flights

    def test_handshake_large_auth_data(self, server):
        """Test handshake with large authentication data."""
        context = Mock(spec=pf.ServerCallContext)
        large_auth = b"a" * 1000  # 1KB auth data
        
        response, peer_identity = server.handshake(context, large_auth)
        assert isinstance(response, bytes)
        assert peer_identity.startswith("user_")

    def test_get_schema_complex_path(self, server):
        """Test get_schema with complex multi-part path."""
        context = Mock(spec=pf.ServerCallContext)
        descriptor = pf.FlightDescriptor.for_path("catalog", "schema", "table")
        
        schema = server.get_schema(context, descriptor)
        
        # Should return generic schema for complex unknown paths
        assert isinstance(schema, pa.Schema)
        assert len(schema) == 2
        assert schema.field(0).name == "name"
        assert schema.field(1).name == "value"

    def test_backend_error_handling(self, server):
        """Test handling of backend errors in Phase 1 methods."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Mock backend error for describe query
        server.backend.execute_query.side_effect = Exception("Backend unavailable")
        
        # get_schema should handle backend errors gracefully and return fallback schema
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_STATEMENT_QUERY_TYPE_URL
        sql_query = "SELECT 1"
        query_encoded = sql_query.encode("utf-8")
        any_msg.value = bytes([0x0A]) + bytes([len(query_encoded)]) + query_encoded
        descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())
        
        # Should return fallback schema instead of raising error
        schema = server.get_schema(context, descriptor)
        assert isinstance(schema, pa.Schema)
        assert len(schema) == 1
        assert schema.field(0).name == "result"
        assert schema.field(0).type == pa.string()

    def test_concurrent_access_simulation(self, server):
        """Test Phase 1 methods under simulated concurrent access."""
        import threading
        import time
        
        context = Mock(spec=pf.ServerCallContext)
        results = []
        errors = []
        
        def test_method():
            try:
                # Test all three Phase 1 methods
                handshake_result = server.handshake(context, b"concurrent_user")
                flights = list(server.list_flights(context, b""))
                schema = server.get_schema(context, pf.FlightDescriptor.for_path("catalogs"))
                results.append((handshake_result, len(flights), len(schema)))
            except Exception as e:
                errors.append(e)
        
        # Run multiple threads
        threads = [threading.Thread(target=test_method) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        
        # All threads should succeed
        assert len(errors) == 0
        assert len(results) == 5
        
        # All results should be consistent
        for handshake_result, flight_count, schema_len in results:
            assert handshake_result[1].startswith("user_")  # peer_identity
            assert flight_count == 5
            assert schema_len > 0

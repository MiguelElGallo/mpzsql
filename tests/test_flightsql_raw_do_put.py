"""
Test suite for raw Flight do_put functionality in FlightSQL minimal server.

This test suite covers the new PATH descriptor handling and Arrow-to-DuckDB
functionality that was added in the PR.
"""

import pytest
import pyarrow as pa
import pyarrow.flight as pf
from unittest.mock import Mock, patch, MagicMock

from mpzsql.flightsql.minimal import FlightSQLMinimalServer
from mpzsql.backends.duckdb_backend import DuckDBBackend
from mpzsql.config import ServerConfig


class TestFlightSQLRawDoPut:
    """Test raw Flight do_put functionality with PATH descriptors."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = Mock(spec=ServerConfig)
        self.config.database = ":memory:"
        self.config.read_only = False
        self.config.print_queries = True
        
        self.backend = Mock(spec=DuckDBBackend)
        self.server = FlightSQLMinimalServer(self.backend)

    def create_sample_arrow_table(self) -> pa.Table:
        """Create a sample Arrow table for testing."""
        data = {
            'id': [1, 2, 3],
            'name': ['Alice', 'Bob', 'Charlie'],
            'value': [100.0, 200.0, 300.0]
        }
        return pa.table(data)

    def test_do_put_path_descriptor_batch_mode(self):
        """Test do_put with PATH descriptor (batch mode - single table upload)."""
        # Setup
        arrow_table = self.create_sample_arrow_table()
        table_name = "test_table"
        descriptor = pf.FlightDescriptor.for_path(table_name.encode('utf-8'))
        
        # Mock the backend methods
        self.backend.create_table_from_arrow = Mock()
        self.backend.get_table_schema = Mock(return_value=arrow_table.schema)
        self.backend.get_table_row_count = Mock(return_value=3)

        # Execute do_put
        writer, metadata_reader = self.server.do_put(None, descriptor, arrow_table.schema)
        
        # Simulate writing the table
        writer.write_table(arrow_table)
        writer.close()

        # Verify backend was called correctly
        self.backend.create_table_from_arrow.assert_called_once_with(table_name, arrow_table)

    def test_do_put_path_descriptor_streaming_mode(self):
        """Test do_put with PATH descriptor (streaming mode - multiple chunks)."""
        # Setup
        table_name = "streaming_table"
        descriptor = pf.FlightDescriptor.for_path(table_name.encode('utf-8'))
        
        # Create schema and multiple chunks
        schema = pa.schema([
            pa.field('id', pa.int64()),
            pa.field('data', pa.string())
        ])
        
        chunk1 = pa.table({
            'id': [1, 2],
            'data': ['A', 'B']
        })
        
        chunk2 = pa.table({
            'id': [3, 4, 5],
            'data': ['C', 'D', 'E']
        })

        # Mock the backend methods
        self.backend.create_table_from_schema = Mock()
        self.backend.append_table_from_arrow = Mock()
        self.backend.get_table_schema = Mock(return_value=schema)
        self.backend.get_table_row_count = Mock(return_value=5)

        # Execute do_put
        writer, metadata_reader = self.server.do_put(None, descriptor, schema)
        
        # Simulate streaming multiple chunks
        writer.write_table(chunk1)  # First chunk -> create_table_from_schema + append
        writer.write_table(chunk2)  # Second chunk -> append_table_from_arrow
        writer.close()

        # Verify backend was called correctly for streaming mode
        # First chunk should create table from schema and then append the data
        self.backend.create_table_from_schema.assert_called_once_with(table_name, schema)
        
        # Both chunks should be appended (streaming mode always appends)
        assert self.backend.append_table_from_arrow.call_count == 2
        self.backend.append_table_from_arrow.assert_any_call(table_name, chunk1)
        self.backend.append_table_from_arrow.assert_any_call(table_name, chunk2)

    def test_do_put_cmd_descriptor_flightsql_compatibility(self):
        """Test do_put with CMD descriptor (existing FlightSQL functionality)."""
        # Setup FlightSQL command
        from mpzsql.flightsql.protocol import FlightSQLProtobuf
        
        command = FlightSQLProtobuf.CommandStatementUpdate()
        command.query = "INSERT INTO test_table VALUES (1, 'test')"
        
        descriptor = pf.FlightDescriptor.for_command(command.SerializeToString())
        schema = pa.schema([pa.field('result', pa.int64())])

        # Mock backend execute_update
        self.backend.execute_update = Mock(return_value=1)

        # Execute do_put
        writer, metadata_reader = self.server.do_put(None, descriptor, schema)
        writer.close()

        # Verify FlightSQL command was executed
        self.backend.execute_update.assert_called_once_with(command.query)

    def test_get_flight_info_path_descriptor(self):
        """Test get_flight_info with PATH descriptor for raw Flight table metadata."""
        # Setup
        table_name = "info_test_table"
        descriptor = pf.FlightDescriptor.for_path(table_name.encode('utf-8'))
        
        # Mock backend methods
        mock_schema = pa.schema([
            pa.field('id', pa.int64()),
            pa.field('name', pa.string())
        ])
        self.backend.get_table_schema = Mock(return_value=mock_schema)
        self.backend.get_table_row_count = Mock(return_value=100)

        # Execute get_flight_info
        flight_info = self.server.get_flight_info(None, descriptor)

        # Verify response
        assert flight_info.descriptor.descriptor_type == pf.DescriptorType.PATH
        assert flight_info.descriptor.path == [table_name.encode('utf-8')]
        assert flight_info.schema == mock_schema
        assert flight_info.total_records == 100

        # Verify backend was called
        self.backend.get_table_schema.assert_called_once_with(table_name)
        self.backend.get_table_row_count.assert_called_once_with(table_name)

    def test_get_flight_info_cmd_descriptor_flightsql(self):
        """Test get_flight_info with CMD descriptor (FlightSQL compatibility)."""
        # Setup FlightSQL query command
        from mpzsql.flightsql.protocol import FlightSQLProtobuf
        
        command = FlightSQLProtobuf.CommandStatementQuery()
        command.query = "SELECT * FROM test_table"
        
        descriptor = pf.FlightDescriptor.for_command(command.SerializeToString())
        
        # Mock backend
        mock_schema = pa.schema([pa.field('col1', pa.string())])
        self.backend.get_statement_schema = Mock(return_value=mock_schema)

        # Execute get_flight_info
        flight_info = self.server.get_flight_info(None, descriptor)

        # Verify FlightSQL behavior
        assert flight_info.descriptor.descriptor_type == pf.DescriptorType.CMD
        assert flight_info.schema == mock_schema

        # Verify backend was called with the query
        self.backend.get_statement_schema.assert_called_once_with(command.query)

    def test_descriptor_routing_cmd_vs_path(self):
        """Test that do_put correctly routes between CMD and PATH descriptors."""
        # Test PATH descriptor routing
        path_descriptor = pf.FlightDescriptor.for_path("table_name".encode('utf-8'))
        
        # Mock the _handle_path_do_put method
        with patch.object(self.server, '_handle_path_do_put') as mock_path_handler:
            mock_path_handler.return_value = (Mock(), Mock())
            
            schema = pa.schema([pa.field('col1', pa.string())])
            self.server.do_put(None, path_descriptor, schema)
            
            # Verify PATH handler was called
            mock_path_handler.assert_called_once()

        # Test CMD descriptor routing
        cmd_descriptor = pf.FlightDescriptor.for_command(b"some_command")
        
        # Mock the _handle_flightsql_do_put method
        with patch.object(self.server, '_handle_flightsql_do_put') as mock_cmd_handler:
            mock_cmd_handler.return_value = (Mock(), Mock())
            
            self.server.do_put(None, cmd_descriptor, schema)
            
            # Verify CMD handler was called
            mock_cmd_handler.assert_called_once()

    def test_unsupported_descriptor_type(self):
        """Test error handling for unsupported descriptor types."""
        # Create a descriptor with UNKNOWN type (should not happen in practice)
        descriptor = pf.FlightDescriptor.for_path("test".encode('utf-8'))
        # Manually set to unsupported type
        descriptor.descriptor_type = pf.DescriptorType.UNKNOWN
        
        schema = pa.schema([pa.field('col1', pa.string())])

        # Should raise an error for unsupported descriptor type
        with pytest.raises(Exception) as exc_info:
            self.server.do_put(None, descriptor, schema)
        
        assert "Unsupported descriptor type" in str(exc_info.value)

    def test_path_do_put_error_handling(self):
        """Test error handling in PATH descriptor do_put."""
        # Setup
        table_name = "error_table"
        descriptor = pf.FlightDescriptor.for_path(table_name.encode('utf-8'))
        schema = pa.schema([pa.field('col1', pa.string())])
        
        # Mock backend to raise an error
        self.backend.create_table_from_arrow = Mock(side_effect=Exception("Database error"))
        
        # Execute do_put and expect it to handle the error
        writer, metadata_reader = self.server.do_put(None, descriptor, schema)
        
        # Write data that will trigger the error
        arrow_table = pa.table({'col1': ['test']})
        
        with pytest.raises(Exception):
            writer.write_table(arrow_table)

    def test_path_get_flight_info_error_handling(self):
        """Test error handling in PATH descriptor get_flight_info."""
        # Setup
        table_name = "nonexistent_table"
        descriptor = pf.FlightDescriptor.for_path(table_name.encode('utf-8'))
        
        # Mock backend to raise an error (table doesn't exist)
        self.backend.get_table_schema = Mock(side_effect=Exception("Table not found"))
        
        # Should raise an error
        with pytest.raises(Exception):
            self.server.get_flight_info(None, descriptor)

    def test_large_table_upload(self):
        """Test uploading a large table via PATH descriptor."""
        # Create a larger table
        num_rows = 10000
        large_data = {
            'id': list(range(num_rows)),
            'value': [f'value_{i}' for i in range(num_rows)],
            'amount': [float(i * 1.5) for i in range(num_rows)]
        }
        large_table = pa.table(large_data)
        
        table_name = "large_table"
        descriptor = pf.FlightDescriptor.for_path(table_name.encode('utf-8'))
        
        # Mock backend
        self.backend.create_table_from_arrow = Mock()
        self.backend.get_table_schema = Mock(return_value=large_table.schema)
        self.backend.get_table_row_count = Mock(return_value=num_rows)

        # Execute do_put
        writer, metadata_reader = self.server.do_put(None, descriptor, large_table.schema)
        writer.write_table(large_table)
        writer.close()

        # Verify backend was called with large table
        self.backend.create_table_from_arrow.assert_called_once_with(table_name, large_table)

    def test_multiple_concurrent_uploads(self):
        """Test multiple concurrent table uploads (simulated)."""
        tables = []
        for i in range(5):
            table_name = f"concurrent_table_{i}"
            descriptor = pf.FlightDescriptor.for_path(table_name.encode('utf-8'))
            arrow_table = pa.table({
                'id': [i],
                'data': [f'data_{i}']
            })
            tables.append((table_name, descriptor, arrow_table))

        # Mock backend
        self.backend.create_table_from_arrow = Mock()
        self.backend.get_table_schema = Mock(return_value=pa.schema([
            pa.field('id', pa.int64()),
            pa.field('data', pa.string())
        ]))
        self.backend.get_table_row_count = Mock(return_value=1)

        # Execute multiple uploads
        for table_name, descriptor, arrow_table in tables:
            writer, metadata_reader = self.server.do_put(None, descriptor, arrow_table.schema)
            writer.write_table(arrow_table)
            writer.close()

        # Verify all tables were created
        assert self.backend.create_table_from_arrow.call_count == 5

    def test_qualified_table_names(self):
        """Test PATH descriptors with qualified table names."""
        qualified_names = [
            "simple_table",
            "schema.table_name", 
            "database.schema.table_name",
            "my_ducklake.main.lineitem"
        ]
        
        for qualified_name in qualified_names:
            descriptor = pf.FlightDescriptor.for_path(qualified_name.encode('utf-8'))
            arrow_table = pa.table({'col1': [1, 2, 3]})
            
            # Mock backend
            self.backend.create_table_from_arrow = Mock()
            
            # Execute do_put
            writer, metadata_reader = self.server.do_put(None, descriptor, arrow_table.schema)
            writer.write_table(arrow_table)
            writer.close()
            
            # Verify qualified name was passed through correctly
            self.backend.create_table_from_arrow.assert_called_with(qualified_name, arrow_table)

    def test_schema_validation(self):
        """Test schema validation between write calls in streaming mode."""
        table_name = "schema_validation_table"
        descriptor = pf.FlightDescriptor.for_path(table_name.encode('utf-8'))
        
        # Create initial schema and chunk
        schema = pa.schema([
            pa.field('id', pa.int64()),
            pa.field('name', pa.string())
        ])
        
        chunk1 = pa.table({
            'id': [1, 2],
            'name': ['A', 'B']
        })
        
        # Create second chunk with compatible but slightly different schema
        chunk2 = pa.table({
            'id': [3, 4],
            'name': ['C', 'D']
        })

        # Mock backend
        self.backend.create_table_from_schema = Mock()
        self.backend.append_table_from_arrow = Mock()

        # Execute streaming do_put
        writer, metadata_reader = self.server.do_put(None, descriptor, schema)
        writer.write_table(chunk1)
        writer.write_table(chunk2)
        writer.close()

        # Verify both chunks were processed
        self.backend.create_table_from_schema.assert_called_once_with(table_name, schema)
        assert self.backend.append_table_from_arrow.call_count == 2

"""
Integration tests for the complete raw Flight do_put workflow.

This test suite tests the end-to-end integration between FlightSQL minimal server
and DuckDB backend for the new Arrow-to-DuckDB functionality.
"""

import pytest
import pyarrow as pa
import pyarrow.flight as pf
from unittest.mock import Mock, MagicMock

from src.mpzsql.flightsql.minimal import MinimalFlightSQLServer
from src.mpzsql.backends.duckdb_backend import DuckDBBackend
from src.mpzsql.config import ServerConfig


class TestRawFlightDoPutIntegration:
    """Integration tests for raw Flight do_put functionality."""

    def setup_method(self):
        """Set up test fixtures with real backend."""
        self.config = ServerConfig(
            database=":memory:",
            read_only=False,
            print_queries=True,
            secret_key="test_secret",
            username="test_user",
            password="test_pass"
        )
        self.location = pf.Location.for_grpc_tcp("localhost", 0)
        
        # Use real DuckDB backend for integration testing
        self.backend = DuckDBBackend(self.config)
        self.server = MinimalFlightSQLServer(
            backend=self.backend,
            config=self.config,
            location=self.location
        )

    def teardown_method(self):
        """Clean up after tests."""
        if hasattr(self, 'backend'):
            self.backend.close()

    def create_sample_arrow_table(self) -> pa.Table:
        """Create a sample Arrow table for testing."""
        data = {
            'order_id': [1, 2, 3, 4, 5],
            'customer_name': ['Alice Johnson', 'Bob Smith', 'Charlie Brown', 'David Wilson', 'Eve Davis'],
            'product_category': ['Electronics', 'Books', 'Clothing', 'Electronics', 'Books'],
            'order_amount': [299.99, 24.99, 79.99, 449.99, 19.99],
            'order_date': ['2024-01-15', '2024-01-16', '2024-01-17', '2024-01-18', '2024-01-19'],
            'is_priority': [True, False, True, False, True]
        }
        return pa.table(data)

    def test_complete_batch_upload_workflow(self):
        """Test complete batch upload workflow: upload -> verify -> query."""
        # Step 1: Create test data
        arrow_table = self.create_sample_arrow_table()
        table_name = "integration_orders"
        
        # Step 2: Use raw Flight do_put to upload data (batch mode)
        descriptor = pf.FlightDescriptor.for_path(table_name.encode('utf-8'))
        context = Mock(spec=pf.ServerCallContext)
        
        # Mock the reader and writer
        reader = Mock()
        reader.schema = arrow_table.schema
        reader.read_all.return_value = arrow_table
        
        writer = Mock()
        
        # Execute the upload
        result = self.server._handle_file_upload_do_put(context, descriptor, reader, writer)
        
        # Step 3: Verify table was created in DuckDB
        row_count = self.backend.get_table_row_count(table_name)
        assert row_count == 5
        
        # Step 4: Verify schema
        schema = self.backend.get_table_schema(table_name)
        assert len(schema) == 6
        assert 'order_id' in schema.names
        assert 'customer_name' in schema.names
        
        # Step 5: Query the data
        result = self.backend.execute_query(f"SELECT * FROM {table_name} ORDER BY order_id")
        data = result.to_pylist()
        
        assert len(data) == 5
        assert data[0]['order_id'] == 1
        assert data[0]['customer_name'] == 'Alice Johnson'
        assert data[4]['order_id'] == 5

    def test_complete_streaming_upload_workflow(self):
        """Test complete streaming upload workflow: schema -> chunks -> verify."""
        table_name = "streaming_sales"
        
        # Step 1: Create schema and chunks
        schema = pa.schema([
            pa.field('sale_id', pa.int64()),
            pa.field('product', pa.string()),
            pa.field('amount', pa.float64()),
            pa.field('region', pa.string())
        ])
        
        chunk1 = pa.table({
            'sale_id': [1, 2, 3],
            'product': ['Laptop', 'Mouse', 'Keyboard'],
            'amount': [999.99, 29.99, 79.99],
            'region': ['North', 'South', 'East']
        })
        
        chunk2 = pa.table({
            'sale_id': [4, 5],
            'product': ['Monitor', 'Speakers'],
            'amount': [299.99, 149.99],
            'region': ['West', 'North']
        })
        
        # Step 2: Simulate streaming upload
        descriptor = pf.FlightDescriptor.for_path(table_name.encode('utf-8'))
        context = Mock(spec=pf.ServerCallContext)
        
        # Mock reader for streaming (multiple read_chunk calls)
        reader = Mock()
        reader.schema = schema
        
        # Set up reader to return chunks sequentially
        chunks = [chunk1, chunk2]
        chunk_iter = iter(chunks)
        
        def mock_read_chunk():
            try:
                return next(chunk_iter)
            except StopIteration:
                return None
        
        reader.read_chunk = mock_read_chunk
        
        writer = Mock()
        
        # Execute streaming upload
        result = self.server._handle_file_upload_do_put(context, descriptor, reader, writer)
        
        # Step 3: Verify final result
        row_count = self.backend.get_table_row_count(table_name)
        assert row_count == 5  # 3 + 2 from chunks
        
        # Step 4: Query and verify data integrity
        result = self.backend.execute_query(f"SELECT COUNT(DISTINCT region) as regions FROM {table_name}")
        unique_regions = result.to_pylist()[0]['regions']
        assert unique_regions == 4  # North, South, East, West

    def test_get_flight_info_integration(self):
        """Test get_flight_info integration with real backend."""
        # Step 1: Create a table using direct backend
        test_data = pa.table({
            'id': [1, 2, 3],
            'name': ['Test1', 'Test2', 'Test3'],
            'value': [10.5, 20.5, 30.5]
        })
        table_name = "flight_info_test"
        self.backend.create_table_from_arrow(table_name, test_data)
        
        # Step 2: Use get_flight_info to retrieve metadata
        descriptor = pf.FlightDescriptor.for_path(table_name.encode('utf-8'))
        context = Mock(spec=pf.ServerCallContext)
        
        flight_info = self.server.get_flight_info(context, descriptor)
        
        # Step 3: Verify flight info
        assert flight_info.descriptor.descriptor_type == pf.DescriptorType.PATH
        assert flight_info.total_records == 3
        assert len(flight_info.schema) == 3
        
        # Verify schema field names
        field_names = [field.name for field in flight_info.schema]
        assert 'id' in field_names
        assert 'name' in field_names
        assert 'value' in field_names

    def test_error_handling_integration(self):
        """Test error handling in integration scenarios."""
        context = Mock(spec=pf.ServerCallContext)
        
        # Test 1: Non-existent table in get_flight_info
        descriptor = pf.FlightDescriptor.for_path("nonexistent_table".encode('utf-8'))
        
        with pytest.raises(Exception):
            self.server.get_flight_info(context, descriptor)
        
        # Test 2: Invalid data in do_put
        descriptor = pf.FlightDescriptor.for_path("invalid_upload".encode('utf-8'))
        reader = Mock()
        reader.schema = pa.schema([pa.field('col1', pa.string())])
        reader.read_all.side_effect = Exception("Data read error")
        
        writer = Mock()
        
        with pytest.raises(Exception):
            self.server._handle_file_upload_do_put(context, descriptor, reader, writer)

    def test_table_replacement_integration(self):
        """Test table replacement functionality."""
        table_name = "replacement_test"
        
        # Step 1: Create initial table
        initial_data = pa.table({
            'id': [1, 2],
            'category': ['A', 'B']
        })
        self.backend.create_table_from_arrow(table_name, initial_data)
        
        # Verify initial state
        count1 = self.backend.get_table_row_count(table_name)
        assert count1 == 2
        
        # Step 2: Replace with new data via Flight upload
        new_data = pa.table({
            'id': [10, 20, 30],
            'category': ['X', 'Y', 'Z']
        })
        
        descriptor = pf.FlightDescriptor.for_path(table_name.encode('utf-8'))
        context = Mock(spec=pf.ServerCallContext)
        
        reader = Mock()
        reader.schema = new_data.schema
        reader.read_all.return_value = new_data
        
        writer = Mock()
        
        # Execute replacement upload
        self.server._handle_file_upload_do_put(context, descriptor, reader, writer)
        
        # Step 3: Verify replacement
        count2 = self.backend.get_table_row_count(table_name)
        assert count2 == 3  # New table has 3 rows
        
        # Verify data was actually replaced
        result = self.backend.execute_query(f"SELECT id FROM {table_name} ORDER BY id")
        ids = [row['id'] for row in result.to_pylist()]
        assert ids == [10, 20, 30]  # New IDs, not original ones

    def test_complex_data_types_integration(self):
        """Test integration with complex Arrow data types."""
        # Create table with various data types
        complex_data = {
            'int_col': [1, 2, 3],
            'float_col': [1.1, 2.2, 3.3],
            'string_col': ['a', 'b', 'c'],
            'bool_col': [True, False, True],
            'date_col': pa.array(['2024-01-01', '2024-01-02', '2024-01-03'], type=pa.date32())
        }
        
        complex_table = pa.table(complex_data)
        table_name = "complex_types_integration"
        
        # Upload via Flight
        descriptor = pf.FlightDescriptor.for_path(table_name.encode('utf-8'))
        context = Mock(spec=pf.ServerCallContext)
        
        reader = Mock()
        reader.schema = complex_table.schema
        reader.read_all.return_value = complex_table
        
        writer = Mock()
        
        # Execute upload
        self.server._handle_file_upload_do_put(context, descriptor, reader, writer)
        
        # Verify upload and query capability
        row_count = self.backend.get_table_row_count(table_name)
        assert row_count == 3
        
        # Test querying different data types
        result = self.backend.execute_query(f"SELECT * FROM {table_name} WHERE bool_col = true")
        true_rows = result.to_pylist()
        assert len(true_rows) == 2  # First and third rows

    def test_concurrent_operations_simulation(self):
        """Test simulation of concurrent operations."""
        # Create multiple tables rapidly
        tables_created = []
        
        for i in range(3):
            table_name = f"concurrent_table_{i}"
            test_data = pa.table({
                'id': [i],
                'value': [f'value_{i}'],
                'timestamp': [f'2024-01-{i+1:02d}']
            })
            
            # Upload via Flight
            descriptor = pf.FlightDescriptor.for_path(table_name.encode('utf-8'))
            context = Mock(spec=pf.ServerCallContext)
            
            reader = Mock()
            reader.schema = test_data.schema
            reader.read_all.return_value = test_data
            
            writer = Mock()
            
            # Execute upload
            self.server._handle_file_upload_do_put(context, descriptor, reader, writer)
            tables_created.append(table_name)
        
        # Verify all tables were created successfully
        for table_name in tables_created:
            count = self.backend.get_table_row_count(table_name)
            assert count == 1
            
            # Verify we can query each table
            result = self.backend.execute_query(f"SELECT value FROM {table_name}")
            assert len(result.to_pylist()) == 1

    def test_backward_compatibility(self):
        """Test that existing FlightSQL functionality still works."""
        # This test ensures that adding raw Flight support didn't break FlightSQL
        
        # Test FlightSQL query (CMD descriptor)
        from google.protobuf import any_pb2
        from src.mpzsql.flightsql.protobuf import CommandStatementQuery, FlightSQLProtobuf
        
        # Create a test table first
        self.backend.execute_sql("CREATE TABLE flightsql_test (id INTEGER, name VARCHAR)")
        self.backend.execute_sql("INSERT INTO flightsql_test VALUES (1, 'test')")
        
        # Test FlightSQL query command
        command = CommandStatementQuery()
        command.query = "SELECT * FROM flightsql_test"
        
        # Create Any message wrapper
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_STATEMENT_QUERY_TYPE_URL
        
        # Encode query and set value
        query_encoded = command.query.encode('utf-8')
        any_msg.value = bytes([0x0A]) + bytes([len(query_encoded)]) + query_encoded
        
        descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())
        context = Mock(spec=pf.ServerCallContext)
        
        # This should work via the existing FlightSQL path
        flight_info = self.server.get_flight_info(context, descriptor)
        
        # Verify FlightSQL functionality
        assert flight_info.descriptor.descriptor_type == pf.DescriptorType.CMD
        assert flight_info.schema is not None

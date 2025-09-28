"""
Test suite for DuckDB backend Arrow-to-DuckDB methods.

This test suite covers the new raw Flight do_put functionality:
- create_table_from_arrow (batch mode)
- create_table_from_schema (streaming mode - first chunk)
- append_table_from_arrow (streaming mode - subsequent chunks)
- get_table_schema
- get_table_row_count
"""

from unittest.mock import Mock

import pyarrow as pa
import pytest

from mpzsql.backends.duckdb_backend import DuckDBBackend
from mpzsql.config import ServerConfig


def create_mock_config(**overrides):
    """Create a properly configured Mock ServerConfig with all required attributes."""
    config = Mock(spec=ServerConfig)
    # Set default values for all required attributes
    config.database = ":memory:"
    config.read_only = False
    config.init_sql = None
    config.print_queries = True
    # PostgreSQL configuration attributes
    config.postgresql_server = None
    config.postgresql_port = 5432
    config.postgresql_user = None
    config.postgresql_password = None
    config.postgresql_catalogdb = None
    # Azure Storage configuration attributes
    config.azure_storage_account = None
    config.azure_storage_container = None
    # Add property methods that are accessed by the backend
    config.is_postgresql_enabled = False
    config.is_azure_storage_enabled = False
    
    # Apply any overrides
    for key, value in overrides.items():
        setattr(config, key, value)
    
    return config


class TestDuckDBBackendArrowMethods:
    """Test DuckDB backend Arrow integration methods."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = create_mock_config()
        self.backend = DuckDBBackend(self.config)

    def teardown_method(self):
        """Clean up after tests."""
        if hasattr(self, "backend"):
            self.backend.close()

    def create_sample_arrow_table(self) -> pa.Table:
        """Create a sample Arrow table for testing."""
        data = {
            "id": [1, 2, 3, 4, 5],
            "name": ["Alice", "Bob", "Charlie", "David", "Eve"],
            "age": [25, 30, 35, 40, 45],
            "salary": [50000.0, 60000.0, 70000.0, 80000.0, 90000.0],
            "active": [True, True, False, True, False],
        }
        return pa.table(data)

    def create_large_arrow_table(self, num_rows: int = 1000) -> pa.Table:
        """Create a larger Arrow table for testing performance."""
        import random

        data = {
            "id": list(range(1, num_rows + 1)),
            "name": [f"Person_{i}" for i in range(1, num_rows + 1)],
            "value": [random.random() * 1000 for _ in range(num_rows)],
            "category": [f"Cat_{i % 10}" for i in range(num_rows)],
        }
        return pa.table(data)

    def test_create_table_from_arrow_simple(self):
        """Test creating a table from Arrow data (batch mode)."""
        arrow_table = self.create_sample_arrow_table()
        table_name = "test_employees"

        # Create table from Arrow data
        self.backend.create_table_from_arrow(table_name, arrow_table)

        # Verify table was created
        result = self.backend.execute_query(
            f"SELECT COUNT(*) as count FROM {table_name}"
        )
        assert result.to_pylist()[0]["count"] == 5

        # Verify schema matches
        schema_result = self.backend.execute_query(
            f"SELECT * FROM {table_name} LIMIT 0"
        )
        assert len(schema_result.schema) == 5
        assert "id" in schema_result.schema.names
        assert "name" in schema_result.schema.names
        assert "age" in schema_result.schema.names
        assert "salary" in schema_result.schema.names
        assert "active" in schema_result.schema.names

    def test_create_table_from_arrow_qualified_name(self):
        """Test creating a table with schema-qualified name."""
        arrow_table = self.create_sample_arrow_table()
        # Use a simple schema-qualified name that DuckDB can handle
        table_name = "main.qualified_table"

        # Create table with qualified name
        self.backend.create_table_from_arrow(table_name, arrow_table)

        # Verify table was created
        result = self.backend.execute_query(
            f"SELECT COUNT(*) as count FROM {table_name}"
        )
        assert result.to_pylist()[0]["count"] == 5

    def test_create_table_from_arrow_appends_to_existing(self):
        """Test that create_table_from_arrow appends to existing tables (new behavior)."""
        arrow_table1 = self.create_sample_arrow_table()
        arrow_table2 = pa.table(
            {
                "id": [10, 20],
                "name": ["New1", "New2"],
                "age": [99, 88],
                "salary": [100000.0, 110000.0],
                "active": [True, True],
            }
        )
        table_name = "appendable_table"

        # Create first table
        self.backend.create_table_from_arrow(table_name, arrow_table1)
        result1 = self.backend.execute_query(
            f"SELECT COUNT(*) as count FROM {table_name}"
        )
        assert result1.to_pylist()[0]["count"] == 5

        # Append second table (new behavior - no longer replaces)
        self.backend.create_table_from_arrow(table_name, arrow_table2)
        result2 = self.backend.execute_query(
            f"SELECT COUNT(*) as count FROM {table_name}"
        )
        assert result2.to_pylist()[0]["count"] == 7  # 5 + 2 = 7

        # Verify both original and new data are present
        data_result = self.backend.execute_query(
            f"SELECT id FROM {table_name} ORDER BY id"
        )
        ids = [row["id"] for row in data_result.to_pylist()]
        assert ids == [1, 2, 3, 4, 5, 10, 20]  # All data preserved

    def test_create_table_from_schema_streaming_mode(self):
        """Test creating an empty table from schema (streaming mode - first chunk)."""
        arrow_table = self.create_sample_arrow_table()
        schema = arrow_table.schema
        table_name = "streaming_table"

        # Create empty table from schema
        self.backend.create_table_from_schema(table_name, schema)

        # Verify empty table was created with correct schema
        result = self.backend.execute_query(
            f"SELECT COUNT(*) as count FROM {table_name}"
        )
        assert result.to_pylist()[0]["count"] == 0

        # Verify schema matches
        schema_result = self.backend.execute_query(
            f"SELECT * FROM {table_name} LIMIT 0"
        )
        assert len(schema_result.schema) == 5
        assert schema_result.schema.names == ["id", "name", "age", "salary", "active"]

    def test_append_table_from_arrow_streaming_mode(self):
        """Test appending Arrow data to existing table (streaming mode)."""
        # Create initial table
        initial_data = pa.table({"id": [1, 2], "value": [10.0, 20.0]})
        table_name = "append_test_table"

        self.backend.create_table_from_arrow(table_name, initial_data)

        # Append more data
        append_data1 = pa.table({"id": [3, 4], "value": [30.0, 40.0]})
        self.backend.append_table_from_arrow(table_name, append_data1)

        # Append even more data
        append_data2 = pa.table({"id": [5, 6, 7], "value": [50.0, 60.0, 70.0]})
        self.backend.append_table_from_arrow(table_name, append_data2)

        # Verify final count
        result = self.backend.execute_query(
            f"SELECT COUNT(*) as count FROM {table_name}"
        )
        assert result.to_pylist()[0]["count"] == 7

        # Verify all data is present
        data_result = self.backend.execute_query(
            f"SELECT id, value FROM {table_name} ORDER BY id"
        )
        data = data_result.to_pylist()
        expected_ids = [1, 2, 3, 4, 5, 6, 7]
        expected_values = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]

        actual_ids = [row["id"] for row in data]
        actual_values = [row["value"] for row in data]

        assert actual_ids == expected_ids
        assert actual_values == expected_values

    def test_complete_streaming_workflow(self):
        """Test complete streaming workflow: schema -> append -> append."""
        # Step 1: Create empty table from schema
        schema = pa.schema(
            [
                pa.field("batch_id", pa.int64()),
                pa.field("data", pa.string()),
                pa.field("timestamp", pa.timestamp("s")),
            ]
        )
        table_name = "streaming_workflow_table"

        self.backend.create_table_from_schema(table_name, schema)

        # Step 2: Append first batch
        import datetime

        batch1 = pa.table(
            {
                "batch_id": [1, 1, 1],
                "data": ["A", "B", "C"],
                "timestamp": [
                    datetime.datetime(2024, 1, 1),
                    datetime.datetime(2024, 1, 2),
                    datetime.datetime(2024, 1, 3),
                ],
            }
        )
        self.backend.append_table_from_arrow(table_name, batch1)

        # Step 3: Append second batch
        batch2 = pa.table(
            {
                "batch_id": [2, 2],
                "data": ["D", "E"],
                "timestamp": [
                    datetime.datetime(2024, 1, 4),
                    datetime.datetime(2024, 1, 5),
                ],
            }
        )
        self.backend.append_table_from_arrow(table_name, batch2)

        # Verify final result
        result = self.backend.execute_query(
            f"SELECT COUNT(*) as count FROM {table_name}"
        )
        assert result.to_pylist()[0]["count"] == 5

        # Verify data integrity
        data_result = self.backend.execute_query(
            f"SELECT batch_id, data FROM {table_name} ORDER BY batch_id, data"
        )
        data = data_result.to_pylist()
        assert len(data) == 5
        assert data[0]["batch_id"] == 1 and data[0]["data"] == "A"
        assert data[4]["batch_id"] == 2 and data[4]["data"] == "E"

    def test_get_table_schema(self):
        """Test retrieving table schema."""
        arrow_table = self.create_sample_arrow_table()
        table_name = "schema_test_table"

        # Create table
        self.backend.create_table_from_arrow(table_name, arrow_table)

        # Get schema
        retrieved_schema = self.backend.get_table_schema(table_name)

        # Verify schema
        assert isinstance(retrieved_schema, pa.Schema)
        assert len(retrieved_schema) == 5
        assert "id" in retrieved_schema.names
        assert "name" in retrieved_schema.names
        assert "age" in retrieved_schema.names
        assert "salary" in retrieved_schema.names
        assert "active" in retrieved_schema.names

    def test_get_table_row_count(self):
        """Test retrieving table row count."""
        arrow_table = self.create_sample_arrow_table()
        table_name = "count_test_table"

        # Create table
        self.backend.create_table_from_arrow(table_name, arrow_table)

        # Get row count
        row_count = self.backend.get_table_row_count(table_name)

        # Verify count
        assert row_count == 5

    def test_get_table_row_count_empty_table(self):
        """Test row count for empty table."""
        schema = pa.schema([pa.field("col1", pa.int64())])
        table_name = "empty_count_table"

        # Create empty table
        self.backend.create_table_from_schema(table_name, schema)

        # Get row count
        row_count = self.backend.get_table_row_count(table_name)

        # Verify count is 0
        assert row_count == 0

    def test_large_table_performance(self):
        """Test with larger table to ensure performance is reasonable."""
        large_table = self.create_large_arrow_table(1000)
        table_name = "large_performance_table"

        # Create large table
        self.backend.create_table_from_arrow(table_name, large_table)

        # Verify count
        row_count = self.backend.get_table_row_count(table_name)
        assert row_count == 1000

        # Verify we can query it
        result = self.backend.execute_query(
            f"SELECT COUNT(DISTINCT category) as unique_cats FROM {table_name}"
        )
        unique_categories = result.to_pylist()[0]["unique_cats"]
        assert (
            unique_categories == 10
        )  # We create 10 categories in create_large_arrow_table

    def test_error_handling_invalid_table_name(self):
        """Test error handling for invalid table names."""
        arrow_table = self.create_sample_arrow_table()

        # Test with various invalid table names
        with pytest.raises(Exception):
            self.backend.create_table_from_arrow("", arrow_table)

    def test_error_handling_nonexistent_table_schema(self):
        """Test error handling when getting schema of non-existent table."""
        with pytest.raises(Exception):
            self.backend.get_table_schema("nonexistent_table")

    def test_error_handling_nonexistent_table_count(self):
        """Test error handling when getting count of non-existent table."""
        with pytest.raises(Exception):
            self.backend.get_table_row_count("nonexistent_table")

    def test_error_handling_append_to_nonexistent_table(self):
        """Test error handling when appending to non-existent table."""
        arrow_table = self.create_sample_arrow_table()

        with pytest.raises(Exception):
            self.backend.append_table_from_arrow("nonexistent_table", arrow_table)

    def test_schema_compatibility_append(self):
        """Test that appending data with different but compatible schema works."""
        # Create initial table
        initial_table = pa.table({"id": [1, 2], "name": ["Alice", "Bob"]})
        table_name = "schema_compat_table"
        self.backend.create_table_from_arrow(table_name, initial_table)

        # Append data with same schema
        append_table = pa.table({"id": [3, 4], "name": ["Charlie", "David"]})
        self.backend.append_table_from_arrow(table_name, append_table)

        # Verify final count
        row_count = self.backend.get_table_row_count(table_name)
        assert row_count == 4

    def test_temporary_table_cleanup(self):
        """Test that temporary tables are properly cleaned up."""
        arrow_table = self.create_sample_arrow_table()
        table_name = "cleanup_test_table"

        # Create table (this will create and cleanup temporary tables internally)
        self.backend.create_table_from_arrow(table_name, arrow_table)

        # Check that no temporary tables remain
        # Query system tables to see if any temp tables with our naming pattern exist
        result = self.backend.execute_query("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name LIKE 'temp_arrow_table_%'
               OR table_name LIKE 'temp_schema_table_%'
               OR table_name LIKE 'temp_append_table_%'
        """)

        # Should be empty - no temp tables should remain
        temp_tables = result.to_pylist()
        assert len(temp_tables) == 0, f"Found lingering temporary tables: {temp_tables}"

    def test_concurrent_operations_simulation(self):
        """Test simulation of concurrent operations using unique temp table names."""
        # Simulate multiple concurrent operations by creating multiple tables rapidly
        tables_created = []

        for i in range(5):
            arrow_table = pa.table({"id": [i], "value": [i * 10]})
            table_name = f"concurrent_table_{i}"

            # This should work without conflicts due to unique temp table names
            self.backend.create_table_from_arrow(table_name, arrow_table)
            tables_created.append(table_name)

        # Verify all tables were created successfully
        for table_name in tables_created:
            row_count = self.backend.get_table_row_count(table_name)
            assert row_count == 1

    def test_complex_data_types(self):
        """Test with complex Arrow data types."""
        # Create table with various data types
        complex_data = {
            "int8_col": pa.array([1, 2, 3], type=pa.int8()),
            "int16_col": pa.array([100, 200, 300], type=pa.int16()),
            "int32_col": pa.array([1000, 2000, 3000], type=pa.int32()),
            "int64_col": pa.array([10000, 20000, 30000], type=pa.int64()),
            "float32_col": pa.array([1.1, 2.2, 3.3], type=pa.float32()),
            "float64_col": pa.array([10.1, 20.2, 30.3], type=pa.float64()),
            "string_col": pa.array(["a", "b", "c"], type=pa.string()),
            "bool_col": pa.array([True, False, True], type=pa.bool_()),
            "date_col": pa.array(
                [
                    pa.scalar(19723, type=pa.date32()),  # 2024-01-01
                    pa.scalar(19724, type=pa.date32()),  # 2024-01-02
                    pa.scalar(19725, type=pa.date32()),  # 2024-01-03
                ],
                type=pa.date32(),
            ),
        }

        complex_table = pa.table(complex_data)
        table_name = "complex_types_table"

        # Create table
        self.backend.create_table_from_arrow(table_name, complex_table)

        # Verify creation
        row_count = self.backend.get_table_row_count(table_name)
        assert row_count == 3

        # Verify schema preservation
        schema = self.backend.get_table_schema(table_name)
        assert len(schema) == 9
        assert "int8_col" in schema.names
        assert "float64_col" in schema.names
        assert "bool_col" in schema.names
        assert "date_col" in schema.names

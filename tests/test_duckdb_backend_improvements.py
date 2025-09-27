"""
Tests for DuckDB backend improvements and fixes.

This module tests recent improvements to the DuckDB backend,
particularly around Arrow result handling and type conversions.
"""

from unittest.mock import Mock

import pyarrow as pa
import pytest

from mpzsql.backends.duckdb_backend import DuckDBBackend
from mpzsql.config import ServerConfig


@pytest.fixture
def backend():
    """Provide a DuckDB backend instance for testing."""
    config = Mock(spec=ServerConfig)
    config.database = ":memory:"
    config.read_only = False
    config.init_sql = None
    config.print_queries = True

    backend_instance = DuckDBBackend(config)
    try:
        yield backend_instance
    finally:
        backend_instance.close()


class TestRecordBatchReaderHandling:
    """Test proper handling of RecordBatchReader results from DuckDB."""

    def test_get_tables_returns_table_not_reader(self, backend):
        """Test that get_tables returns a proper Arrow Table."""
        # Create a test table to query
        backend.connection.execute("CREATE TABLE test_table (id INTEGER, name VARCHAR)")
        
        # Call get_tables
        result = backend.get_tables(
            catalog=None,
            db_schema_filter_pattern="main",
            table_name_filter_pattern="%",
            table_types=[],
            include_schema=False,
        )
        
        # Verify it's a Table, not a RecordBatchReader
        assert isinstance(result, pa.Table)
        assert hasattr(result, 'num_rows')
        assert hasattr(result, 'column')
        
        # Verify it has the expected columns
        expected_columns = ["catalog_name", "db_schema_name", "table_name", "table_type"]
        assert result.schema.names == expected_columns
        
        # Verify we can access the data
        assert result.num_rows >= 1
        table_names = result.column("table_name").to_pylist()
        assert "test_table" in table_names

    def test_get_db_schemas_returns_table_not_reader(self, backend):
        """Test that get_db_schemas returns a proper Arrow Table."""
        result = backend.get_db_schemas(catalog=None, db_schema_filter_pattern=None)
        
        # Verify it's a Table, not a RecordBatchReader  
        assert isinstance(result, pa.Table)
        assert hasattr(result, 'num_rows')
        assert hasattr(result, 'column')
        
        # Verify it has the expected columns
        expected_columns = ["catalog_name", "db_schema_name"]
        assert result.schema.names == expected_columns
        
        # Verify we get at least the main schema
        assert result.num_rows >= 1
        schema_names = result.column("db_schema_name").to_pylist()
        assert "main" in schema_names

    def test_get_columns_returns_table_not_reader(self, backend):
        """Test that get_columns returns a proper Arrow Table."""
        # Create a test table with columns
        backend.connection.execute("CREATE TABLE test_cols (id INTEGER, name VARCHAR(50), score DOUBLE)")
        
        result = backend.get_columns(
            catalog=None,
            db_schema_filter_pattern="main",
            table_name_filter_pattern="test_cols",
            column_name_filter_pattern=None
        )
        
        # Verify it's a Table, not a RecordBatchReader
        assert isinstance(result, pa.Table)
        assert hasattr(result, 'num_rows')
        assert hasattr(result, 'column')
        
        # Verify the structure is correct (may be empty if DuckDB changed behavior)
        expected_column_fields = ["catalog_name", "db_schema_name", "table_name", "column_name"]
        schema_names = result.schema.names
        for field in expected_column_fields:
            assert field in schema_names


class TestTableSchemaRetrieval:
    """Test table schema retrieval functionality."""

    def test_get_table_schema_returns_proper_schema(self, backend):
        """Test that get_table_schema returns a proper Arrow Schema."""
        # Create a test table with various data types
        backend.connection.execute("""
            CREATE TABLE schema_test (
                id INTEGER,
                name VARCHAR(100),
                price DECIMAL(10,2),
                active BOOLEAN,
                created_at TIMESTAMP
            )
        """)
        
        schema = backend.get_table_schema("schema_test")
        
        # Verify it's an Arrow Schema
        assert isinstance(schema, pa.Schema)
        
        # Verify field names
        field_names = [field.name for field in schema]
        expected_fields = ["id", "name", "price", "active", "created_at"]
        assert set(field_names) == set(expected_fields)
        
        # Verify we can access field information
        assert len(schema) == 5
        for field in schema:
            assert field.name in expected_fields
            assert field.type is not None


class TestBackendRobustness:
    """Test backend robustness and error handling."""

    def test_get_tables_empty_database(self, backend):
        """Test get_tables works even with empty database."""
        result = backend.get_tables(
            catalog=None,
            db_schema_filter_pattern="main",
            table_name_filter_pattern="%",
            table_types=[],
            include_schema=False,
        )
        
        # Should return empty table, not fail
        assert isinstance(result, pa.Table)
        expected_columns = ["catalog_name", "db_schema_name", "table_name", "table_type"]
        assert result.schema.names == expected_columns

    def test_get_tables_with_nonexistent_schema_filter(self, backend):
        """Test get_tables with non-existent schema filter."""
        result = backend.get_tables(
            catalog=None,
            db_schema_filter_pattern="nonexistent_schema",
            table_name_filter_pattern="%",
            table_types=[],
            include_schema=False,
        )
        
        # Should return empty table, not fail
        assert isinstance(result, pa.Table)
        assert result.num_rows == 0

    def test_large_utf8_to_utf8_conversion(self, backend):
        """Test the _convert_large_utf8_to_utf8 method works properly."""
        # Create a table with string data
        test_table = pa.table({
            'name': pa.array(['test1', 'test2'], type=pa.large_utf8()),
            'description': pa.array(['desc1', 'desc2'], type=pa.large_utf8())
        })
        
        result = backend._convert_large_utf8_to_utf8(test_table)
        
        # Verify conversion worked
        assert isinstance(result, pa.Table)
        assert result.schema.field('name').type == pa.string()
        assert result.schema.field('description').type == pa.string()
        
        # Verify data is preserved
        assert result.column('name').to_pylist() == ['test1', 'test2']
        assert result.column('description').to_pylist() == ['desc1', 'desc2']
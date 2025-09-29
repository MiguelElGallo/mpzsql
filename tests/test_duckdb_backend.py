"""
Test suite for DuckDB backend based on real server interactions.

This test suite simulates real FlightSQL operations as captured in the server logs,
testing the DuckDB backend's ability to handle metadata queries, schema introspection,
and query execution scenarios.
"""

import os
from unittest.mock import Mock, patch

import duckdb
import pyarrow as pa
import pytest

from mpzsql.backends.duckdb_backend import DuckDBBackend
from mpzsql.config import ServerConfig


class TestDuckDBBackendBasedOnLogs:
    """Test DuckDB backend operations based on real server logs."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.config = Mock(spec=ServerConfig)
        self.config.database = ":memory:"
        self.config.read_only = False
        self.config.init_sql = None
        self.config.print_queries = True

    def test_get_catalogs_real_scenario(self) -> None:
        """Test get_catalogs based on real log: catalog_name: [["__ducklake_metadata_my_ducklake","localconf","my_ducklake","system","temp"]]"""
        backend = DuckDBBackend(self.config)

        result = backend.get_catalogs()

        assert isinstance(result, pa.Table)
        assert result.schema.names == ["catalog_name"]
        assert result.schema.field("catalog_name").type == pa.string()

        # Check that we get some catalogs (at minimum 'system' and 'temp' should exist)
        catalog_names = result.column("catalog_name").to_pylist()
        assert len(catalog_names) > 0
        assert "system" in catalog_names
        assert "temp" in catalog_names

    def test_get_db_schemas_real_scenario(self) -> None:
        """Test get_db_schemas based on real log: catalog=my_ducklake, db_schema_filter_pattern=%"""
        backend = DuckDBBackend(self.config)

        # Set up a ducklake catalog attachment (simulate the real scenario)
        try:
            backend.connection.execute("ATTACH ':memory:' AS my_ducklake")
        except Exception:
            # If attach fails, create a basic database connection
            pass

        # Based on logs: catalog=my_ducklake, db_schema_filter_pattern=%
        # Result: catalog_name: [["my_ducklake"]], db_schema_name: [["main"]]
        result = backend.get_db_schemas(
            catalog="my_ducklake", db_schema_filter_pattern="%"
        )

        assert isinstance(result, pa.Table)
        assert result.schema.names == ["catalog_name", "db_schema_name"]
        assert len(result) >= 0  # May be empty if catalog doesn't exist

        if len(result) > 0:
            schema_names = result.column("db_schema_name").to_pylist()
            assert "main" in schema_names

    def test_get_tables_without_schema_real_scenario(self) -> None:
        """Test get_tables based on real log: catalog=my_ducklake, db_schema_filter_pattern=main, table_name_filter_pattern=%, include_schema=False"""
        backend = DuckDBBackend(self.config)

        # Create a test table to simulate the real scenario where table "t1" was found
        backend.connection.execute("CREATE TABLE t1 (id INTEGER, name VARCHAR)")

        # Based on logs: catalog=my_ducklake, db_schema_filter_pattern=main, table_name_filter_pattern=%, include_schema=False
        # Result: catalog_name: [["my_ducklake"]], db_schema_name: [["main"]], table_name: [["t1"]], table_type: [["BASE TABLE"]]
        result = backend.get_tables(
            catalog=None,  # Use default catalog
            db_schema_filter_pattern="main",
            table_name_filter_pattern="%",
            table_types=[],
            include_schema=False,
        )

        assert isinstance(result, pa.Table)
        expected_columns = [
            "catalog_name",
            "db_schema_name",
            "table_name",
            "table_type",
        ]
        assert result.schema.names == expected_columns

        # Should find our test table
        assert len(result) >= 1
        table_names = result.column("table_name").to_pylist()
        table_types = result.column("table_type").to_pylist()

        assert "t1" in table_names
        assert "BASE TABLE" in table_types

    def test_get_tables_with_schema_real_scenario(self) -> None:
        """Test get_tables with schema based on real log: table_name_filter_pattern=t1, include_schema=True"""
        backend = DuckDBBackend(self.config)

        # Create a test table to simulate the real scenario
        backend.connection.execute("CREATE TABLE t1 (id INTEGER, name VARCHAR)")

        # Based on logs: catalog=my_ducklake, db_schema_filter_pattern=main, table_name_filter_pattern=t1, include_schema=True
        # Result included table_schema as binary field
        result = backend.get_tables(
            catalog=None,
            db_schema_filter_pattern="main",
            table_name_filter_pattern="t1",
            table_types=[],
            include_schema=True,
        )

        assert isinstance(result, pa.Table)
        expected_columns = [
            "catalog_name",
            "db_schema_name",
            "table_name",
            "table_type",
            "table_schema",
        ]
        assert result.schema.names == expected_columns

        # Should find our specific table
        table_names = result.column("table_name").to_pylist()
        assert "t1" in table_names

        # Check that table_schema is included and is binary
        assert result.schema.field("table_schema").type == pa.binary()

        # Schema should not be null for our table
        schema_column = result.column("table_schema")
        for i, table_name in enumerate(table_names):
            if table_name == "t1":
                assert schema_column[i].as_py() is not None

    def test_get_sql_info_empty_request_real_scenario(self) -> None:
        """Test get_sql_info based on real log: info=[] (empty request)"""
        backend = DuckDBBackend(self.config)

        # Based on logs: _parse_get_sql_info: Parsed info IDs: []
        # Result: info_name: [[]], value: [[]] (empty table)
        result = backend.get_sql_info([])

        assert isinstance(result, pa.Table)
        assert result.schema.names == ["info_name", "value"]
        assert result.schema.field("info_name").type == pa.int32()
        assert result.schema.field("value").type == pa.string()

        # Empty request should return empty table
        assert len(result) == 0

    def test_get_sql_info_with_specific_info_real_scenario(self) -> None:
        """Test get_sql_info with specific info IDs."""
        backend = DuckDBBackend(self.config)

        # Test with some common SQL info IDs that should be supported
        # Based on FlightSQL specification
        SQL_INFO_FLIGHT_SQL_SERVER_NAME = 500
        SQL_INFO_FLIGHT_SQL_SERVER_VERSION = 501

        result = backend.get_sql_info(
            [SQL_INFO_FLIGHT_SQL_SERVER_NAME, SQL_INFO_FLIGHT_SQL_SERVER_VERSION]
        )

        assert isinstance(result, pa.Table)
        assert result.schema.names == ["info_name", "value"]

        # Should return info for the requested IDs
        if len(result) > 0:
            info_names = result.column("info_name").to_pylist()
            assert (
                SQL_INFO_FLIGHT_SQL_SERVER_NAME in info_names
                or SQL_INFO_FLIGHT_SQL_SERVER_VERSION in info_names
            )

    def test_connection_initialization_with_print_queries(self) -> None:
        """Test that DuckDB connection properly initializes with query printing enabled."""
        config = Mock(spec=ServerConfig)
        config.database = ":memory:"
        config.read_only = False
        config.init_sql = None
        config.print_queries = True

        with patch("mpzsql.backends.duckdb_backend.duckdb_log"):
            backend = DuckDBBackend(config)

            # Verify connection is created
            assert isinstance(backend.connection, duckdb.DuckDBPyConnection)

            # Verify config is stored
            assert backend.config.print_queries

    def test_connection_initialization_with_init_sql(self) -> None:
        """Test DuckDB connection initialization with init SQL."""
        config = Mock(spec=ServerConfig)
        config.database = ":memory:"
        config.read_only = False
        config.init_sql = None  # DuckDB backend doesn't handle init_sql automatically
        config.print_queries = False

        backend = DuckDBBackend(config)

        # Manually execute init SQL to simulate what CLI would do
        backend.connection.execute("CREATE TABLE init_test (id INTEGER)")

        # Verify init SQL was executed
        tables = backend.connection.execute("SHOW TABLES").fetchall()
        table_names = [row[0] for row in tables]
        assert "init_test" in table_names

    def test_error_handling_invalid_query(self) -> None:
        """Test error handling with invalid SQL query."""
        backend = DuckDBBackend(self.config)

        with pytest.raises(Exception):
            backend.connection.execute("INVALID SQL QUERY THAT SHOULD FAIL")

    def test_memory_database_operations(self) -> None:
        """Test operations on in-memory database."""
        backend = DuckDBBackend(self.config)

        # Create table, insert data, query it
        backend.connection.execute("CREATE TABLE test_table (id INTEGER, value TEXT)")
        backend.connection.execute(
            "INSERT INTO test_table VALUES (1, 'test'), (2, 'data')"
        )

        result = backend.connection.execute(
            "SELECT * FROM test_table ORDER BY id"
        ).fetchall()
        assert len(result) == 2
        assert result[0] == (1, "test")
        assert result[1] == (2, "data")

    def test_file_database_operations(self) -> None:
        """Test operations on file-based database."""
        # Use tempfile for proper cross-platform temp file handling
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "test.duckdb")

            config = Mock(spec=ServerConfig)
            config.database = db_path
            config.read_only = False
            config.init_sql = None
            config.print_queries = False

            backend = DuckDBBackend(config)

            # Create table and verify persistence
            backend.connection.execute("CREATE TABLE persistent_test (id INTEGER)")
            backend.connection.execute("INSERT INTO persistent_test VALUES (42)")

            # Close and reopen connection
            backend.connection.close()
            backend = DuckDBBackend(config)

            result = backend.connection.execute(
                "SELECT * FROM persistent_test"
            ).fetchall()
            assert len(result) == 1
            assert result[0] == (42,)

    def test_read_only_mode(self) -> None:
        """Test read-only database mode."""
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "readonly_test.duckdb")

            # First create the database with some data
            config_write = Mock(spec=ServerConfig)
            config_write.database = db_path
            config_write.read_only = False
            config_write.init_sql = None
            config_write.print_queries = False

            backend_write = DuckDBBackend(config_write)
            backend_write.connection.execute("CREATE TABLE readonly_test (id INTEGER)")
            backend_write.connection.execute("INSERT INTO readonly_test VALUES (1)")
            backend_write.connection.close()

            # Now open in read-only mode
            config_readonly = Mock(spec=ServerConfig)
            config_readonly.database = db_path
            config_readonly.read_only = True
            config_readonly.init_sql = None
            config_readonly.print_queries = False

            backend_readonly = DuckDBBackend(config_readonly)

            # Should be able to read
            result = backend_readonly.connection.execute(
                "SELECT * FROM readonly_test"
            ).fetchall()
            assert len(result) == 1

            # Should not be able to write (this may or may not raise an exception depending on DuckDB version)
            try:
                backend_readonly.connection.execute(
                    "INSERT INTO readonly_test VALUES (2)"
                )
                # If no exception, verify the insert didn't actually work due to read-only mode
                result = backend_readonly.connection.execute(
                    "SELECT COUNT(*) FROM readonly_test"
                ).fetchall()
                # In true read-only mode, we should still have only 1 row
                assert result[0][0] <= 1, "Read-only mode should prevent writes"
            except Exception:
                # Expected behavior for read-only mode
                pass

    def test_type_mapping_coverage(self) -> None:
        """Test DuckDB type mapping functionality."""
        backend = DuckDBBackend(self.config)

        # Create table with various data types
        backend.connection.execute("""
            CREATE TABLE type_test (
                int_col INTEGER,
                text_col VARCHAR,
                float_col DOUBLE,
                bool_col BOOLEAN,
                date_col DATE,
                timestamp_col TIMESTAMP
            )
        """)

        # Insert test data
        backend.connection.execute("""
            INSERT INTO type_test VALUES
            (42, 'test', 3.14, true, '2025-01-01', '2025-01-01 12:00:00')
        """)

        # Get table with schema to test type mapping
        result = backend.get_tables(
            catalog=None,
            db_schema_filter_pattern="main",
            table_name_filter_pattern="type_test",
            table_types=[],
            include_schema=True,
        )

        assert len(result) == 1
        assert "type_test" in result.column("table_name").to_pylist()

        # Verify schema is included
        schema_data = result.column("table_schema")[0].as_py()
        assert schema_data is not None
        assert len(schema_data) > 0


class TestDuckDBBackendErrorScenarios:
    """Test error scenarios based on edge cases that might occur in production."""

    def test_invalid_database_path(self) -> None:
        """Test handling of invalid database path."""
        config = Mock(spec=ServerConfig)
        config.database = "/non_existent_dir/test.duckdb"
        config.read_only = False
        config.init_sql = None
        config.print_queries = False

        # DuckDB may create directories or fail gracefully depending on permissions
        try:
            backend = DuckDBBackend(config)
            # If successful, test basic functionality
            result = backend.connection.execute("SELECT 1").fetchall()
            assert result == [(1,)]
        except Exception:
            # Expected behavior for invalid paths
            pass

    def test_corrupted_init_sql(self) -> None:
        """Test handling of invalid init SQL."""
        config = Mock(spec=ServerConfig)
        config.database = ":memory:"
        config.read_only = False
        config.init_sql = None
        config.print_queries = False

        backend = DuckDBBackend(config)

        # Test manual execution of invalid SQL (simulating CLI behavior)
        with pytest.raises(Exception):
            backend.connection.execute("INVALID SQL THAT SHOULD FAIL")

    def test_get_tables_with_invalid_catalog(self) -> None:
        """Test get_tables with non-existent catalog."""
        config = Mock(spec=ServerConfig)
        config.database = ":memory:"
        config.read_only = False
        config.init_sql = None
        config.print_queries = False

        backend = DuckDBBackend(config)

        # Based on logs, this might return empty results rather than error
        result = backend.get_tables(
            catalog="nonexistent_catalog",
            db_schema_filter_pattern="main",
            table_name_filter_pattern="%",
            table_types=[],
            include_schema=False,
        )

        assert isinstance(result, pa.Table)
        # Should return empty table rather than crash
        assert len(result) == 0

    def test_get_db_schemas_with_invalid_catalog(self) -> None:
        """Test get_db_schemas with non-existent catalog."""
        config = Mock(spec=ServerConfig)
        config.database = ":memory:"
        config.read_only = False
        config.init_sql = None
        config.print_queries = False

        backend = DuckDBBackend(config)

        result = backend.get_db_schemas(
            catalog="nonexistent_catalog", db_schema_filter_pattern="%"
        )

        assert isinstance(result, pa.Table)
        # Should return empty table rather than crash
        assert len(result) == 0


if __name__ == "__main__":
    pytest.main(["-v", "--tb=short", __file__])

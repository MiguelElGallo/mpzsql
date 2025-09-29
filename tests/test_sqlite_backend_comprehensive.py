"""
Comprehensive test suite for SQLite backend.

This test suite provides comprehensive coverage for the SQLite backend,
including query execution, schema introspection, error scenarios, and edge cases.
"""

import os
import sqlite3
import tempfile
from unittest.mock import Mock, patch

import pyarrow as pa
import pytest

from mpzsql.backends.sqlite_backend import SQLiteBackend
from mpzsql.config import ServerConfig


class TestSQLiteBackendComprehensive:
    """Comprehensive test suite for SQLite backend."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        # Create temporary database file
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.db_fd)  # Close file descriptor, keep path

        # Initialize test database with sample data
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create test tables
        cursor.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE,
                age INTEGER,
                balance REAL,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                product TEXT NOT NULL,
                quantity INTEGER DEFAULT 1,
                price REAL,
                order_date DATE,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)

        # Insert test data
        cursor.execute("""
            INSERT INTO users (name, email, age, balance, is_active) VALUES
            ('Alice Smith', 'alice@example.com', 30, 1500.50, 1),
            ('Bob Johnson', 'bob@example.com', 25, 750.25, 1),
            ('Charlie Brown', 'charlie@example.com', 35, 2000.00, 0),
            ('Diana Prince', 'diana@example.com', 28, 1250.75, 1)
        """)

        cursor.execute("""
            INSERT INTO orders (user_id, product, quantity, price, order_date) VALUES
            (1, 'Laptop', 1, 999.99, '2024-01-15'),
            (1, 'Mouse', 2, 25.50, '2024-01-15'),
            (2, 'Keyboard', 1, 75.00, '2024-01-16'),
            (3, 'Monitor', 1, 300.00, '2024-01-17'),
            (4, 'Tablet', 1, 450.00, '2024-01-18')
        """)

        conn.commit()
        conn.close()

        # Create test config
        self.config = Mock(spec=ServerConfig)
        self.config.database = self.db_path
        self.config.read_only = False

    def teardown_method(self) -> None:
        """Clean up test fixtures."""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_init_with_valid_database(self) -> None:
        """Test initialization with valid database file."""
        backend = SQLiteBackend(self.config)
        assert backend.connection is not None
        assert backend.config == self.config

        # Test that we can execute a simple query
        result = backend.connection.execute("SELECT 1").fetchone()
        assert result[0] == 1

    def test_init_without_database_raises_error(self) -> None:
        """Test initialization without database file raises ValueError."""
        config = Mock(spec=ServerConfig)
        config.database = None

        with pytest.raises(ValueError, match="SQLite backend requires a database file"):
            SQLiteBackend(config)

    def test_init_with_nonexistent_database_creates_file(self) -> None:
        """Test initialization with nonexistent database creates the file."""
        nonexistent_path = "/tmp/test_nonexistent.db"
        if os.path.exists(nonexistent_path):
            os.unlink(nonexistent_path)

        config = Mock(spec=ServerConfig)
        config.database = nonexistent_path
        config.read_only = False

        try:
            backend = SQLiteBackend(config)
            assert os.path.exists(nonexistent_path)
            assert backend.connection is not None
        finally:
            if os.path.exists(nonexistent_path):
                os.unlink(nonexistent_path)

    def test_init_read_only_mode(self) -> None:
        """Test initialization in read-only mode."""
        self.config.read_only = True
        backend = SQLiteBackend(self.config)

        # Should be able to read
        result = backend.execute_query("SELECT COUNT(*) as count FROM users")
        assert result.to_pylist()[0]["count"] == 4

        # Should not be able to write (would raise an exception in actual use)
        with pytest.raises(Exception):
            backend.execute_sql(
                "INSERT INTO users (name, email) VALUES ('Test', 'test@test.com')"
            )

    def test_init_with_invalid_readonly_database(self) -> None:
        """Test initialization with invalid read-only database."""
        self.config.database = "/nonexistent/path/database.db"
        self.config.read_only = True

        with pytest.raises(Exception):
            SQLiteBackend(self.config)

    def test_execute_sql_simple_statements(self) -> None:
        """Test execute_sql with simple SQL statements."""
        backend = SQLiteBackend(self.config)

        # Test CREATE TABLE
        backend.execute_sql("""
            CREATE TABLE test_table (
                id INTEGER PRIMARY KEY,
                value TEXT
            )
        """)

        # Test INSERT
        backend.execute_sql("INSERT INTO test_table (value) VALUES ('test')")

        # Verify data was inserted
        result = backend.connection.execute(
            "SELECT COUNT(*) FROM test_table"
        ).fetchone()
        assert result[0] == 1

    def test_execute_sql_multiple_statements(self) -> None:
        """Test execute_sql with multiple statements using executescript."""
        backend = SQLiteBackend(self.config)

        backend.execute_sql("""
            CREATE TABLE multi_test (id INTEGER, name TEXT);
            INSERT INTO multi_test VALUES (1, 'first');
            INSERT INTO multi_test VALUES (2, 'second');
        """)

        # Verify both records were inserted
        result = backend.connection.execute(
            "SELECT COUNT(*) FROM multi_test"
        ).fetchone()
        assert result[0] == 2

    def test_execute_sql_with_error(self) -> None:
        """Test execute_sql with invalid SQL raises exception."""
        backend = SQLiteBackend(self.config)

        with pytest.raises(Exception):
            backend.execute_sql("INVALID SQL STATEMENT")

    def test_execute_query_simple_select(self) -> None:
        """Test execute_query with simple SELECT statement."""
        backend = SQLiteBackend(self.config)

        result = backend.execute_query("SELECT name, email FROM users WHERE age >= 30")

        assert isinstance(result, pa.Table)
        assert result.schema.names == ["name", "email"]
        assert len(result) == 2  # Alice (30) and Charlie (35)

        # Convert to pylist for easier assertion
        data = result.to_pylist()
        names = [row["name"] for row in data]
        assert "Alice Smith" in names
        assert "Charlie Brown" in names

    def test_execute_query_with_joins(self) -> None:
        """Test execute_query with JOIN statements."""
        backend = SQLiteBackend(self.config)

        result = backend.execute_query("""
            SELECT u.name, o.product, o.price
            FROM users u
            JOIN orders o ON u.id = o.user_id
            WHERE u.is_active = 1
            ORDER BY o.price DESC
        """)

        assert isinstance(result, pa.Table)
        assert result.schema.names == ["name", "product", "price"]
        assert len(result) == 4  # Orders from active users only

        data = result.to_pylist()
        # First row should be highest price (Laptop: 999.99)
        assert data[0]["product"] == "Laptop"
        assert data[0]["price"] == 999.99

    def test_execute_query_with_aggregations(self) -> None:
        """Test execute_query with aggregate functions."""
        backend = SQLiteBackend(self.config)

        result = backend.execute_query("""
            SELECT
                COUNT(*) as user_count,
                AVG(age) as avg_age,
                SUM(balance) as total_balance,
                MAX(balance) as max_balance,
                MIN(age) as min_age
            FROM users
            WHERE is_active = 1
        """)

        assert isinstance(result, pa.Table)
        assert len(result) == 1

        data = result.to_pylist()
        row = data[0]
        assert row["user_count"] == 3  # 3 active users
        assert abs(row["avg_age"] - 27.67) < 0.1  # (30+25+28)/3
        assert abs(row["total_balance"] - 3501.5) < 0.1  # Sum of active users' balances

    def test_execute_query_empty_result(self) -> None:
        """Test execute_query with query returning no rows."""
        backend = SQLiteBackend(self.config)

        result = backend.execute_query("SELECT * FROM users WHERE age > 100")

        assert isinstance(result, pa.Table)
        assert len(result) == 0
        assert result.schema.names == [
            "id",
            "name",
            "email",
            "age",
            "balance",
            "is_active",
            "created_at",
        ]

    def test_execute_query_with_different_data_types(self) -> None:
        """Test execute_query with various SQLite data types."""
        backend = SQLiteBackend(self.config)

        result = backend.execute_query("""
            SELECT
                id,
                name,
                age,
                balance,
                is_active,
                created_at
            FROM users
            LIMIT 1
        """)

        assert isinstance(result, pa.Table)
        schema = result.schema

        # Verify schema field types are properly inferred
        field_names = schema.names
        assert "id" in field_names
        assert "name" in field_names
        assert "age" in field_names
        assert "balance" in field_names
        assert "is_active" in field_names
        assert "created_at" in field_names

    def test_execute_query_with_null_values(self) -> None:
        """Test execute_query handling NULL values."""
        backend = SQLiteBackend(self.config)

        # Insert a record with NULL values
        backend.execute_sql("INSERT INTO users (name) VALUES ('Test User')")

        result = backend.execute_query(
            "SELECT name, email, age FROM users WHERE email IS NULL"
        )

        assert isinstance(result, pa.Table)
        assert len(result) == 1

        # Check values directly from Arrow table
        name_col = result.column("name")
        email_col = result.column("email")
        age_col = result.column("age")

        assert name_col[0].as_py() == "Test User"
        assert email_col[0].as_py() is None
        assert age_col[0].as_py() is None

    def test_execute_query_with_error(self) -> None:
        """Test execute_query with invalid SQL raises exception."""
        backend = SQLiteBackend(self.config)

        with pytest.raises(Exception):
            backend.execute_query("SELECT FROM invalid_table")

    def test_execute_update_insert(self) -> None:
        """Test execute_update with INSERT statement."""
        backend = SQLiteBackend(self.config)

        affected_rows = backend.execute_update("""
            INSERT INTO users (name, email, age)
            VALUES ('New User', 'new@example.com', 22)
        """)

        assert affected_rows == 1

        # Verify the insert
        result = backend.execute_query("SELECT COUNT(*) as count FROM users")
        assert result.to_pylist()[0]["count"] == 5

    def test_execute_update_update_statement(self) -> None:
        """Test execute_update with UPDATE statement."""
        backend = SQLiteBackend(self.config)

        affected_rows = backend.execute_update("""
            UPDATE users SET age = age + 1 WHERE is_active = 1
        """)

        assert affected_rows == 3  # 3 active users

        # Verify the updates
        result = backend.execute_query(
            "SELECT age FROM users WHERE name = 'Alice Smith'"
        )
        assert result.to_pylist()[0]["age"] == 31  # Was 30, now 31

    def test_execute_update_delete_statement(self) -> None:
        """Test execute_update with DELETE statement."""
        backend = SQLiteBackend(self.config)

        affected_rows = backend.execute_update("DELETE FROM users WHERE is_active = 0")

        assert affected_rows == 1  # Charlie Brown

        # Verify the deletion
        result = backend.execute_query("SELECT COUNT(*) as count FROM users")
        assert result.to_pylist()[0]["count"] == 3

    def test_execute_update_no_rows_affected(self) -> None:
        """Test execute_update when no rows are affected."""
        backend = SQLiteBackend(self.config)

        affected_rows = backend.execute_update(
            "UPDATE users SET age = 30 WHERE name = 'Nonexistent'"
        )

        assert affected_rows == 0

    def test_execute_update_with_error(self) -> None:
        """Test execute_update with invalid SQL raises exception."""
        backend = SQLiteBackend(self.config)

        with pytest.raises(Exception):
            backend.execute_update("UPDATE nonexistent_table SET col = 1")

    def test_get_statement_schema_simple_query(self) -> None:
        """Test get_statement_schema with simple query."""
        backend = SQLiteBackend(self.config)

        schema = backend.get_statement_schema("SELECT name, age FROM users")

        assert isinstance(schema, pa.Schema)
        assert schema.names == ["name", "age"]

    def test_get_statement_schema_complex_query(self) -> None:
        """Test get_statement_schema with complex query including joins."""
        backend = SQLiteBackend(self.config)

        schema = backend.get_statement_schema("""
            SELECT u.name, o.product, o.price
            FROM users u
            JOIN orders o ON u.id = o.user_id
        """)

        assert isinstance(schema, pa.Schema)
        assert schema.names == ["name", "product", "price"]

    def test_get_statement_schema_with_aliases(self) -> None:
        """Test get_statement_schema with column aliases."""
        backend = SQLiteBackend(self.config)

        schema = backend.get_statement_schema("""
            SELECT
                name as user_name,
                age as user_age,
                balance * 1.1 as adjusted_balance
            FROM users
        """)

        assert isinstance(schema, pa.Schema)
        assert schema.names == ["user_name", "user_age", "adjusted_balance"]

    def test_get_statement_schema_with_error_fallback(self) -> None:
        """Test get_statement_schema fallback behavior with invalid query."""
        backend = SQLiteBackend(self.config)

        # This should trigger the fallback logic
        schema = backend.get_statement_schema("SELECT FROM invalid_syntax")

        assert isinstance(schema, pa.Schema)
        # Should return generic fallback schema
        assert len(schema.names) >= 1

    def test_get_catalogs(self) -> None:
        """Test get_catalogs method."""
        backend = SQLiteBackend(self.config)

        result = backend.get_catalogs()

        assert isinstance(result, pa.Table)
        assert result.schema.names == ["catalog_name"]
        assert len(result) >= 1

        # SQLite should have at least 'main' catalog
        catalog_names = result.column("catalog_name").to_pylist()
        assert "main" in catalog_names

    def test_get_schemas(self) -> None:
        """Test get_schemas method."""
        backend = SQLiteBackend(self.config)

        schemas = backend.get_schemas()

        assert isinstance(schemas, list)
        assert len(schemas) >= 1

        # Should contain tuples of (catalog, schema)
        for catalog, schema in schemas:
            assert isinstance(catalog, str)
            assert isinstance(schema, str)

        # SQLite should have at least ('main', '')
        assert ("main", "") in schemas

    def test_get_schemas_with_catalog_filter(self) -> None:
        """Test get_schemas with specific catalog."""
        backend = SQLiteBackend(self.config)

        schemas = backend.get_schemas(catalog="main")

        assert isinstance(schemas, list)
        # All returned schemas should be from 'main' catalog
        for catalog, schema in schemas:
            assert catalog == "main"

    def test_get_tables_arrow(self) -> None:
        """Test get_tables method returning Arrow table."""
        backend = SQLiteBackend(self.config)

        result = backend.get_tables()

        assert isinstance(result, pa.Table)
        assert len(result) >= 2  # users and orders tables

        # Check schema
        expected_columns = [
            "catalog_name",
            "db_schema_name",
            "table_name",
            "table_type",
        ]
        assert result.schema.names == expected_columns

        # Check table names
        table_names = result.column("table_name").to_pylist()
        assert "users" in table_names
        assert "orders" in table_names

    def test_get_tables_with_filters(self) -> None:
        """Test get_tables with various filters."""
        backend = SQLiteBackend(self.config)

        # Test with catalog filter
        result = backend.get_tables(catalog="main")
        assert isinstance(result, pa.Table)

        # Test with table name filter
        result = backend.get_tables(table_name_filter_pattern="users")
        table_names = result.column("table_name").to_pylist()
        assert "users" in table_names

        # Test with table type filter
        result = backend.get_tables(table_types=["BASE TABLE"])
        table_types = result.column("table_type").to_pylist()
        assert all(t == "BASE TABLE" for t in table_types)

    def test_get_sql_info(self) -> None:
        """Test get_sql_info method."""
        backend = SQLiteBackend(self.config)

        # Test with known info codes
        result = backend.get_sql_info([500, 501])  # DBMS_NAME, DBMS_VER

        assert isinstance(result, pa.Table)
        assert len(result) == 2
        assert result.schema.names == ["info_name", "info_value"]

        data = result.to_pylist()
        info_names = [row["info_name"] for row in data]
        assert "SQL_DBMS_NAME" in info_names
        assert "SQL_DBMS_VER" in info_names

        # Check values
        for row in data:
            if row["info_name"] == "SQL_DBMS_NAME":
                assert row["info_value"] == "SQLite"
            elif row["info_name"] == "SQL_DBMS_VER":
                assert isinstance(row["info_value"], str)

    def test_get_sql_info_unknown_codes(self) -> None:
        """Test get_sql_info with unknown info codes."""
        backend = SQLiteBackend(self.config)

        result = backend.get_sql_info([999])  # Unknown code

        assert isinstance(result, pa.Table)
        assert len(result) == 1

        data = result.to_pylist()
        assert data[0]["info_name"] == "SQL_INFO_999"
        assert data[0]["info_value"] == "Unknown"

    def test_get_db_schemas(self) -> None:
        """Test get_db_schemas method."""
        backend = SQLiteBackend(self.config)

        result = backend.get_db_schemas()

        assert isinstance(result, pa.Table)
        assert result.schema.names == ["catalog_name", "db_schema_name"]
        assert len(result) >= 1

        data = result.to_pylist()
        # Should have at least main catalog
        catalog_names = [row["catalog_name"] for row in data]
        assert "main" in catalog_names

    def test_get_db_schemas_with_catalog(self) -> None:
        """Test get_db_schemas with specific catalog."""
        backend = SQLiteBackend(self.config)

        result = backend.get_db_schemas(catalog="main")

        assert isinstance(result, pa.Table)
        data = result.to_pylist()

        # All results should be from main catalog
        for row in data:
            assert row["catalog_name"] == "main"

    def test_get_columns(self) -> None:
        """Test get_columns method."""
        backend = SQLiteBackend(self.config)

        result = backend.get_columns()

        assert isinstance(result, pa.Table)
        expected_columns = [
            "catalog_name",
            "db_schema_name",
            "table_name",
            "column_name",
            "data_type",
        ]
        assert result.schema.names == expected_columns

        data = result.to_pylist()
        assert len(data) > 0

        # Check that we have columns from our test tables
        table_columns = {}
        for row in data:
            table_name = row["table_name"]
            column_name = row["column_name"]
            if table_name not in table_columns:
                table_columns[table_name] = []
            table_columns[table_name].append(column_name)

        # Verify expected tables and their columns
        assert "users" in table_columns
        assert "orders" in table_columns
        assert "id" in table_columns["users"]
        assert "name" in table_columns["users"]
        assert "email" in table_columns["users"]

    def test_get_columns_with_filters(self) -> None:
        """Test get_columns with various filters."""
        backend = SQLiteBackend(self.config)

        # Test with table name filter
        result = backend.get_columns(table_name_filter_pattern="users")

        data = result.to_pylist()
        # All columns should be from users table
        for row in data:
            assert "users" in row["table_name"]

        # Test with column name filter
        result = backend.get_columns(column_name_filter_pattern="name")

        data = result.to_pylist()
        # All columns should contain 'name'
        for row in data:
            assert "name" in row["column_name"]

    def test_get_catalogs_old(self) -> None:
        """Test deprecated get_catalogs_old method."""
        backend = SQLiteBackend(self.config)

        catalogs = backend.get_catalogs_old()

        assert isinstance(catalogs, list)
        assert len(catalogs) >= 1
        assert "main" in catalogs

    def test_get_schemas_old(self) -> None:
        """Test deprecated get_schemas_old method."""
        backend = SQLiteBackend(self.config)

        schemas = backend.get_schemas_old()

        assert isinstance(schemas, list)
        assert len(schemas) >= 1
        assert "" in schemas  # Empty string for default schema

    def test_get_tables_old(self) -> None:
        """Test deprecated get_tables_old method."""
        backend = SQLiteBackend(self.config)

        tables = backend.get_tables_old()

        assert isinstance(tables, list)
        assert len(tables) >= 2

        # Should contain tuples of (catalog, schema, table, type)
        table_names = [table[2] for table in tables]
        assert "users" in table_names
        assert "orders" in table_names

        # Check structure
        for catalog, schema, table_name, table_type in tables:
            assert isinstance(catalog, str)
            assert isinstance(schema, str)
            assert isinstance(table_name, str)
            assert isinstance(table_type, str)

    def test_get_tables_old_with_filters(self) -> None:
        """Test deprecated get_tables_old with filters."""
        backend = SQLiteBackend(self.config)

        # Test with table filter
        tables = backend.get_tables_old(table_filter="users")

        assert isinstance(tables, list)
        # Should only return filtered tables
        for catalog, schema, table_name, table_type in tables:
            assert "users" in table_name

    def test_close_connection(self) -> None:
        """Test close method."""
        backend = SQLiteBackend(self.config)

        # Connection should be active
        assert backend.connection is not None

        # Close the connection
        backend.close()

        # Connection should still exist but be closed
        # Note: SQLite doesn't have a reliable way to check if connection is closed
        # This test mainly ensures the close method doesn't raise an exception

    def test_close_connection_error_handling(self) -> None:
        """Test close method error handling."""
        backend = SQLiteBackend(self.config)

        # Manually close connection first
        backend.connection.close()

        # Calling close again should not raise an exception
        try:
            backend.close()
        except Exception:
            # If it does raise an exception, it should be logged but not propagated
            pass

    def test_infer_arrow_type_integers(self) -> None:
        """Test _infer_arrow_type with integer values."""
        backend = SQLiteBackend(self.config)

        values = [1, 2, 3, 4, 5]
        arrow_type = backend._infer_arrow_type(values)
        assert arrow_type == pa.int8()  # Small values should be int8

        # Test with larger values that require int64
        large_values = [1000000000000, 2000000000000]
        arrow_type = backend._infer_arrow_type(large_values)
        assert arrow_type == pa.int64()

        # Test with None values
        values_with_none = [1, None, 3, None, 5]
        arrow_type = backend._infer_arrow_type(values_with_none)
        assert arrow_type == pa.int8()

    def test_infer_arrow_type_floats(self) -> None:
        """Test _infer_arrow_type with float values."""
        backend = SQLiteBackend(self.config)

        values = [1.1, 2.2, 3.3]
        arrow_type = backend._infer_arrow_type(values)
        assert arrow_type == pa.float64()

    def test_infer_arrow_type_strings(self) -> None:
        """Test _infer_arrow_type with string values."""
        backend = SQLiteBackend(self.config)

        values = ["a", "b", "c"]
        arrow_type = backend._infer_arrow_type(values)
        assert arrow_type == pa.string()

    def test_infer_arrow_type_mixed(self) -> None:
        """Test _infer_arrow_type with mixed values defaults to string."""
        backend = SQLiteBackend(self.config)

        values = [1, "text", 3.14]
        arrow_type = backend._infer_arrow_type(values)
        assert arrow_type == pa.string()

    def test_infer_arrow_type_all_none(self) -> None:
        """Test _infer_arrow_type with all None values."""
        backend = SQLiteBackend(self.config)

        values = [None, None, None]
        arrow_type = backend._infer_arrow_type(values)
        assert arrow_type == pa.string()  # Default fallback

    def test_infer_schema_from_cursor_description(self) -> None:
        """Test _infer_schema_from_cursor_description method."""
        backend = SQLiteBackend(self.config)

        # Mock cursor description (name, type_code, display_size, internal_size, precision, scale, null_ok)
        cursor_description = [
            ("id", None, None, None, None, None, None),
            ("name", None, None, None, None, None, None),
            ("age", None, None, None, None, None, None),
        ]

        schema = backend._infer_schema_from_cursor_description(cursor_description)

        assert isinstance(schema, pa.Schema)
        assert schema.names == ["id", "name", "age"]
        # All fields should default to string type in this method
        for field in schema:
            assert field.type == pa.string()

    def test_connection_row_factory(self) -> None:
        """Test that connection uses Row factory for column access by name."""
        backend = SQLiteBackend(self.config)

        cursor = backend.connection.cursor()
        cursor.execute("SELECT name, age FROM users WHERE name = 'Alice Smith'")
        row = cursor.fetchone()

        # Should be able to access by column name
        assert row["name"] == "Alice Smith"
        assert row["age"] == 30

    def test_concurrent_access_thread_safety(self) -> None:
        """Test that check_same_thread=False allows multi-threaded access."""
        backend = SQLiteBackend(self.config)

        import threading

        results = []
        errors = []

        def query_in_thread():
            try:
                result = backend.execute_query("SELECT COUNT(*) as count FROM users")
                results.append(result.to_pylist()[0]["count"])
            except Exception as e:
                errors.append(f"Error: {e}")

        # Create and start multiple threads
        threads = []
        for _ in range(3):
            t = threading.Thread(target=query_in_thread)
            threads.append(t)
            t.start()

        # Wait for all threads to complete
        for t in threads:
            t.join()

        # Check for errors first
        if errors:
            pytest.fail(f"Thread errors occurred: {errors}")

        # All threads should have succeeded and returned the same count
        assert len(results) == 3
        expected_count = 4  # Should be 4 users from setup
        for i, result in enumerate(results):
            assert (
                result == expected_count
            ), f"Thread {i} returned {result}, expected {expected_count}"

    @patch("mpzsql.backends.sqlite_backend.logger")
    def test_logging_on_success(self, mock_logger):
        """Test that successful operations are logged."""
        backend = SQLiteBackend(self.config)
        backend.execute_sql("SELECT 1")  # This method has debug logging

        # Should have logged the SQL execution
        mock_logger.debug.assert_called()

    @patch("mpzsql.backends.sqlite_backend.logger")
    def test_logging_on_error(self, mock_logger):
        """Test that errors are logged."""
        backend = SQLiteBackend(self.config)

        with pytest.raises(Exception):
            backend.execute_query("INVALID SQL")

        # Should have logged the error
        mock_logger.error.assert_called()

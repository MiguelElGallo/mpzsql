"""
Test suite for DuckDB backend type conversion functionality.

This test suite covers the _duckdb_type_to_arrow method that was missing
and causing coverage issues.
"""

from unittest.mock import Mock

import pyarrow as pa

from mpzsql.backends.duckdb_backend import DuckDBBackend
from mpzsql.config import ServerConfig


class TestDuckDBTypeConversion:
    """Test DuckDB to Arrow type conversion."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.config = Mock(spec=ServerConfig)
        self.config.database = ":memory:"
        self.config.read_only = False
        self.config.init_sql = None
        self.config.print_queries = True
        self.backend = DuckDBBackend(self.config)

    def teardown_method(self) -> None:
        """Clean up after tests."""
        if hasattr(self, "backend"):
            self.backend.close()

    def test_integer_type_conversions(self) -> None:
        """Test conversion of integer types."""
        test_cases = [
            ("TINYINT", pa.int8()),
            ("SMALLINT", pa.int16()),
            ("INTEGER", pa.int32()),
            ("INT", pa.int32()),
            ("BIGINT", pa.int64()),
            ("UTINYINT", pa.uint8()),
            ("USMALLINT", pa.uint16()),
            ("UINTEGER", pa.uint32()),
            ("UBIGINT", pa.uint64()),
        ]

        for duckdb_type, expected_arrow_type in test_cases:
            result = self.backend._duckdb_type_to_arrow(duckdb_type)
            assert result == expected_arrow_type, f"Failed for {duckdb_type}"

    def test_floating_point_type_conversions(self) -> None:
        """Test conversion of floating point types."""
        test_cases = [
            ("REAL", pa.float32()),
            ("FLOAT", pa.float32()),
            ("DOUBLE", pa.float64()),
        ]

        for duckdb_type, expected_arrow_type in test_cases:
            result = self.backend._duckdb_type_to_arrow(duckdb_type)
            assert result == expected_arrow_type, f"Failed for {duckdb_type}"

    def test_string_type_conversions(self) -> None:
        """Test conversion of string types."""
        test_cases = [
            ("VARCHAR", pa.string()),
            ("TEXT", pa.string()),
            ("STRING", pa.string()),
            ("CHAR", pa.string()),
            ("VARCHAR(50)", pa.string()),
            ("CHAR(10)", pa.string()),
        ]

        for duckdb_type, expected_arrow_type in test_cases:
            result = self.backend._duckdb_type_to_arrow(duckdb_type)
            assert result == expected_arrow_type, f"Failed for {duckdb_type}"

    def test_boolean_type_conversions(self) -> None:
        """Test conversion of boolean types."""
        test_cases = [
            ("BOOLEAN", pa.bool_()),
            ("BOOL", pa.bool_()),
        ]

        for duckdb_type, expected_arrow_type in test_cases:
            result = self.backend._duckdb_type_to_arrow(duckdb_type)
            assert result == expected_arrow_type, f"Failed for {duckdb_type}"

    def test_datetime_type_conversions(self) -> None:
        """Test conversion of date/time types."""
        test_cases = [
            ("DATE", pa.date32()),
            ("TIME", pa.time64("us")),
            ("TIMESTAMP", pa.timestamp("us")),
            ("TIMESTAMPTZ", pa.timestamp("us", tz="UTC")),
            ("INTERVAL", pa.duration("us")),
        ]

        for duckdb_type, expected_arrow_type in test_cases:
            result = self.backend._duckdb_type_to_arrow(duckdb_type)
            assert result == expected_arrow_type, f"Failed for {duckdb_type}"

    def test_binary_type_conversions(self) -> None:
        """Test conversion of binary types."""
        test_cases = [
            ("BLOB", pa.binary()),
            ("BYTEA", pa.binary()),
        ]

        for duckdb_type, expected_arrow_type in test_cases:
            result = self.backend._duckdb_type_to_arrow(duckdb_type)
            assert result == expected_arrow_type, f"Failed for {duckdb_type}"

    def test_uuid_type_conversion(self) -> None:
        """Test conversion of UUID type."""
        result = self.backend._duckdb_type_to_arrow("UUID")
        assert result == pa.string()  # UUID maps to string in Arrow

    def test_decimal_type_conversions(self) -> None:
        """Test conversion of decimal types."""
        test_cases = [
            ("DECIMAL", pa.decimal128(18, 3)),  # Default precision/scale
            ("NUMERIC", pa.decimal128(18, 3)),  # Default precision/scale
            ("DECIMAL(10)", pa.decimal128(10, 0)),  # Precision only
            ("DECIMAL(10,2)", pa.decimal128(10, 2)),  # Precision and scale
            ("NUMERIC(15,4)", pa.decimal128(15, 4)),  # Precision and scale
        ]

        for duckdb_type, expected_arrow_type in test_cases:
            result = self.backend._duckdb_type_to_arrow(duckdb_type)
            assert result == expected_arrow_type, f"Failed for {duckdb_type}"

    def test_complex_type_conversions(self) -> None:
        """Test conversion of complex types."""
        # LIST type
        result = self.backend._duckdb_type_to_arrow("LIST")
        assert pa.types.is_list(result)

        # Array notation
        result = self.backend._duckdb_type_to_arrow("INTEGER[]")
        assert pa.types.is_list(result)

        # STRUCT type
        result = self.backend._duckdb_type_to_arrow("STRUCT")
        assert pa.types.is_struct(result)

        # MAP type
        result = self.backend._duckdb_type_to_arrow("MAP")
        assert pa.types.is_map(result)

    def test_case_insensitive_conversion(self) -> None:
        """Test that type conversion is case insensitive."""
        test_cases = [
            ("varchar", pa.string()),
            ("VARCHAR", pa.string()),
            ("VarChar", pa.string()),
            ("integer", pa.int32()),
            ("INTEGER", pa.int32()),
            ("Integer", pa.int32()),
        ]

        for duckdb_type, expected_arrow_type in test_cases:
            result = self.backend._duckdb_type_to_arrow(duckdb_type)
            assert result == expected_arrow_type, f"Failed for {duckdb_type}"

    def test_unknown_type_fallback(self) -> None:
        """Test that unknown types fall back to string."""
        unknown_types = [
            "UNKNOWN_TYPE",
            "CUSTOM_TYPE",
            "WEIRD_TYPE(100)",
            "",
        ]

        for unknown_type in unknown_types:
            result = self.backend._duckdb_type_to_arrow(unknown_type)
            assert result == pa.string(), f"Failed for unknown type: {unknown_type}"

    def test_parameterized_types_edge_cases(self) -> None:
        """Test edge cases in parameterized type parsing."""
        test_cases = [
            ("DECIMAL()", pa.decimal128(18, 3)),  # Empty params
            ("DECIMAL(abc)", pa.decimal128(18, 3)),  # Invalid params
            ("VARCHAR()", pa.string()),  # Empty params for varchar
            ("DECIMAL(10,)", pa.decimal128(18, 3)),  # Malformed params
            ("DECIMAL(,2)", pa.decimal128(18, 3)),  # Malformed params
        ]

        for duckdb_type, expected_arrow_type in test_cases:
            result = self.backend._duckdb_type_to_arrow(duckdb_type)
            assert result == expected_arrow_type, f"Failed for {duckdb_type}"

    def test_whitespace_handling(self) -> None:
        """Test that whitespace in type strings is handled correctly."""
        test_cases = [
            (" VARCHAR ", pa.string()),
            ("INTEGER ", pa.int32()),
            (" DECIMAL(10, 2) ", pa.decimal128(10, 2)),
            ("BIGINT\t", pa.int64()),
        ]

        for duckdb_type, expected_arrow_type in test_cases:
            result = self.backend._duckdb_type_to_arrow(duckdb_type)
            assert result == expected_arrow_type, f"Failed for {duckdb_type}"

    def test_real_world_schema_conversion(self) -> None:
        """Test conversion with a realistic schema scenario."""
        # Simulate a real DuckDB schema from DESCRIBE output
        duckdb_schema_types = [
            ("BIGINT", pa.int64()),
            ("VARCHAR", pa.string()),
            ("DOUBLE", pa.float64()),
            ("BOOLEAN", pa.bool_()),
            ("DATE", pa.date32()),
            ("TIMESTAMP", pa.timestamp("us")),
            ("DECIMAL(10,2)", pa.decimal128(10, 2)),
        ]

        # Convert all types
        for duckdb_type, expected_arrow_type in duckdb_schema_types:
            result = self.backend._duckdb_type_to_arrow(duckdb_type)
            assert result == expected_arrow_type, f"Failed for {duckdb_type}"

    def test_integration_with_get_statement_schema(self) -> None:
        """Test integration with get_statement_schema method."""
        # Create a test table
        self.backend.execute_sql("""
            CREATE TABLE test_types_table (
                id BIGINT,
                name VARCHAR(50),
                amount DECIMAL(10,2),
                created_date DATE,
                is_active BOOLEAN
            )
        """)

        # Get schema using the method that uses _duckdb_type_to_arrow
        schema = self.backend.get_statement_schema("SELECT * FROM test_types_table")

        # Verify the schema has the expected fields and types
        assert len(schema) == 5
        assert "id" in schema.names
        assert "name" in schema.names
        assert "amount" in schema.names
        assert "created_date" in schema.names
        assert "is_active" in schema.names

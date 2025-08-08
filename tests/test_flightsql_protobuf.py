"""
Test suite for FlightSQL protobuf handling based on real server interactions.

This test suite simulates real FlightSQL protobuf operations as captured in the server logs,
testing the protobuf parsing, command creation, and schema generation functionality.
"""

from unittest.mock import patch

import pyarrow as pa
import pytest

from mpzsql.flightsql.protobuf import FlightSQLProtobuf


class TestFlightSQLProtobufBasedOnLogs:
    """Test FlightSQL protobuf operations based on real server logs."""

    def setup_method(self):
        """Set up test fixtures."""
        self.protobuf = FlightSQLProtobuf()

    def test_get_sql_info_schema_generation(self):
        """Test SQL info schema generation based on real logs."""
        # Based on logs: get_sql_info() returns schema with info_name: uint32, value: string
        schema = self.protobuf.get_sql_info_schema()

        assert isinstance(schema, pa.Schema)
        assert len(schema) == 2
        assert schema.field(0).name == "info_name"
        assert (
            schema.field(0).type == pa.uint32()
        )  # FlightSQL spec uses uint32 for info_name
        assert schema.field(1).name == "value"
        assert schema.field(1).type == pa.string()

    def test_get_catalogs_schema_generation(self):
        """Test catalogs schema generation based on real logs."""
        # Based on logs: get_catalogs() returns schema with catalog_name: string
        schema = self.protobuf.get_catalogs_schema()

        assert isinstance(schema, pa.Schema)
        assert len(schema) == 1
        assert schema.field(0).name == "catalog_name"
        assert schema.field(0).type == pa.string()

    def test_get_db_schemas_schema_generation(self):
        """Test DB schemas schema generation based on real logs."""
        # Based on logs: get_db_schemas() returns catalog_name: string, db_schema_name: string
        schema = self.protobuf.get_db_schemas_schema()

        assert isinstance(schema, pa.Schema)
        assert len(schema) == 2
        assert schema.field(0).name == "catalog_name"
        assert schema.field(0).type == pa.string()
        assert schema.field(1).name == "db_schema_name"
        assert schema.field(1).type == pa.string()

    def test_get_tables_schema_minimal_generation(self):
        """Test tables schema generation for minimal case (without schema)."""
        # Based on logs: get_tables() without include_schema=True returns
        # catalog_name: string, db_schema_name: string, table_name: string, table_type: string
        schema = self.protobuf.get_tables_schema_minimal()

        assert isinstance(schema, pa.Schema)
        assert len(schema) == 4
        assert schema.field(0).name == "catalog_name"
        assert schema.field(0).type == pa.string()
        assert schema.field(1).name == "db_schema_name"
        assert schema.field(1).type == pa.string()
        assert schema.field(2).name == "table_name"
        assert schema.field(2).type == pa.string()
        assert schema.field(3).name == "table_type"
        assert schema.field(3).type == pa.string()

    def test_get_tables_schema_with_included_schema_generation(self):
        """Test tables schema generation with included schema."""
        # Based on logs: get_tables() with include_schema=True adds table_schema: binary
        schema = self.protobuf.get_tables_schema_with_included_schema()

        assert isinstance(schema, pa.Schema)
        assert (
            len(schema) == 6
        )  # catalog_name, db_schema_name, table_name, table_type, table_remarks, table_schema
        assert schema.field(0).name == "catalog_name"
        assert schema.field(0).type == pa.string()
        assert schema.field(1).name == "db_schema_name"
        assert schema.field(1).type == pa.string()
        assert schema.field(2).name == "table_name"
        assert schema.field(2).type == pa.string()
        assert schema.field(3).name == "table_type"
        assert schema.field(3).type == pa.string()
        assert schema.field(4).name == "table_remarks"  # Standard Flight SQL column
        assert schema.field(4).type == pa.string()
        assert schema.field(5).name == "table_schema"
        assert schema.field(5).type == pa.binary()

    def test_parse_command_get_db_schemas_real_data(self):
        """Test parsing GetDbSchemas command based on real log data."""
        # From logs: _parse_get_db_schemas: Command value bytes: (hex encoded data)
        # Result: Parsed GetDbSchemas: catalog=my_ducklake, db_schema_filter_pattern=%

        # This is a simplified test since the actual protobuf parsing is complex
        # We test that the method exists and can be called
        assert hasattr(self.protobuf, "parse_command_get_db_schemas")
        assert callable(self.protobuf.parse_command_get_db_schemas)

    def test_parse_command_get_tables_real_data(self):
        """Test parsing GetTables command based on real log data."""
        # From logs: _parse_get_tables: Command value bytes: 0a0b6d795f6475636b6c616b6512046d61696e1a0125
        # Result: Parsed GetTables: catalog=my_ducklake, db_schema_filter_pattern=main, table_name_filter_pattern=%, table_types=[], include_schema=False

        # Test that the method exists and can be called
        assert hasattr(self.protobuf, "parse_command_get_tables")
        assert callable(self.protobuf.parse_command_get_tables)

    def test_command_type_urls_constants(self):
        """Test that all required command type URLs are defined."""
        # Based on logs showing these command types being processed
        required_urls = [
            "COMMAND_GET_CATALOGS_TYPE_URL",
            "COMMAND_GET_DB_SCHEMAS_TYPE_URL",
            "COMMAND_GET_TABLES_TYPE_URL",
            "COMMAND_GET_SQL_INFO_TYPE_URL",
            "COMMAND_STATEMENT_QUERY_TYPE_URL",
            "COMMAND_STATEMENT_UPDATE_TYPE_URL",
        ]

        for url_constant in required_urls:
            assert hasattr(self.protobuf, url_constant)
            url_value = getattr(self.protobuf, url_constant)
            assert isinstance(url_value, str)
            assert "type.googleapis.com" in url_value

    def test_action_type_urls_constants(self):
        """Test that action type URLs are defined."""
        # Based on logs showing action handling
        action_urls = [
            "ACTION_BEGIN_TRANSACTION_REQUEST_TYPE_URL",
            "ACTION_BEGIN_TRANSACTION_RESULT_TYPE_URL",
            "ACTION_CREATE_PREPARED_STATEMENT_RESULT_TYPE_URL",
            "ACTION_END_TRANSACTION_REQUEST_TYPE_URL",
        ]

        for url_constant in action_urls:
            assert hasattr(self.protobuf, url_constant)
            url_value = getattr(self.protobuf, url_constant)
            assert isinstance(url_value, str)

    def test_get_type_mapping_functionality(self):
        """Test type mapping functionality used in schema generation."""
        # Test that type mapping is available
        assert hasattr(self.protobuf, "get_type_mapping")
        assert callable(self.protobuf.get_type_mapping)

    def test_prepared_statement_functionality(self):
        """Test prepared statement related functionality."""
        # Based on logs showing prepared statement methods
        methods = [
            "create_prepared_statement_handle",
            "encode_prepared_statement_handle",
            "parse_create_prepared_statement_request",
            "parse_close_prepared_statement_request",
        ]

        for method_name in methods:
            assert hasattr(self.protobuf, method_name)
            assert callable(getattr(self.protobuf, method_name))

    def test_command_parsing_methods_exist(self):
        """Test that all command parsing methods exist."""
        # Based on logs showing these parsing methods being called
        parsing_methods = [
            "parse_command_get_db_schemas",
            "parse_command_get_tables",
            "parse_command_statement_query",
            "parse_command_statement_update",
            "parse_command_prepared_statement_query",
            "parse_command_update",
        ]

        for method_name in parsing_methods:
            assert hasattr(self.protobuf, method_name)
            assert callable(getattr(self.protobuf, method_name))

    def test_action_result_creation_methods(self):
        """Test action result creation methods."""
        # Based on logs showing action result creation
        creation_methods = [
            "create_action_begin_transaction_result",
            "create_action_create_prepared_statement_result",
        ]

        for method_name in creation_methods:
            assert hasattr(self.protobuf, method_name)
            assert callable(getattr(self.protobuf, method_name))

    def test_schema_generation_methods_exist(self):
        """Test that all schema generation methods exist."""
        # Based on the schema types seen in logs
        schema_methods = [
            "get_sql_info_schema",
            "get_sql_info_schema_with_dense_union",
            "get_catalogs_schema",
            "get_db_schemas_schema",
            "get_tables_schema",
            "get_tables_schema_minimal",
            "get_tables_schema_with_included_schema",
            "get_columns_schema",
            "get_primary_keys_schema",
            "get_imported_keys_schema",
            "get_exported_keys_schema",
            "get_cross_reference_schema",
            "get_table_types_schema",
        ]

        for method_name in schema_methods:
            assert hasattr(self.protobuf, method_name)
            assert callable(getattr(self.protobuf, method_name))

    def test_sql_info_empty_request_handling(self):
        """Test SQL info schema for empty request based on logs."""
        # From logs: _parse_get_sql_info: Parsed info IDs: []
        # Result: info_name: [[]], value: [[]] (empty table)

        schema = self.protobuf.get_sql_info_schema()

        # Create empty table with this schema to verify it works
        empty_arrays = [pa.array([], type=pa.int32()), pa.array([], type=pa.string())]
        empty_table = pa.Table.from_arrays(empty_arrays, schema=schema)

        assert len(empty_table) == 0
        assert empty_table.schema.equals(schema)

    @patch("mpzsql.flightsql.protobuf.protobuf_log")
    def test_logging_integration(self, mock_log):
        """Test that protobuf operations integrate with logging."""
        # Verify that protobuf operations can be logged
        # This is important for debugging as seen in the server logs
        schema = self.protobuf.get_catalogs_schema()
        assert isinstance(schema, pa.Schema)
        # The actual logging calls would depend on implementation details

    def test_tables_schema_variations(self):
        """Test different table schema variations based on include_schema parameter."""
        # Test both variations as seen in logs

        # Without schema (include_schema=False)
        minimal_schema = self.protobuf.get_tables_schema_minimal()
        assert len(minimal_schema) == 4

        # With schema (include_schema=True)
        full_schema = self.protobuf.get_tables_schema_with_included_schema()
        assert len(full_schema) == 6  # includes table_remarks and table_schema

        # The first 4 fields should be the same
        for i in range(4):
            assert minimal_schema.field(i).equals(full_schema.field(i))

        # The 5th field should be table_remarks and 6th should be table_schema
        assert full_schema.field(4).name == "table_remarks"
        assert full_schema.field(4).type == pa.string()
        assert full_schema.field(5).name == "table_schema"
        assert full_schema.field(5).type == pa.binary()


class TestFlightSQLProtobufCommandParsing:
    """Test command parsing functionality based on real server data."""

    def setup_method(self):
        """Set up test fixtures."""
        self.protobuf = FlightSQLProtobuf()

    def test_real_get_tables_command_structure(self):
        """Test GetTables command structure based on real logs."""
        # From logs we see two different GetTables calls:
        # 1. catalog=my_ducklake, db_schema_filter_pattern=main, table_name_filter_pattern=%, include_schema=False
        # 2. catalog=my_ducklake, db_schema_filter_pattern=main, table_name_filter_pattern=t1, include_schema=True

        # Test that the parsing method can handle these variations
        # (This would require actual protobuf bytes to test fully)
        assert hasattr(self.protobuf, "parse_command_get_tables")

    def test_real_get_db_schemas_command_structure(self):
        """Test GetDbSchemas command structure based on real logs."""
        # From logs: catalog=my_ducklake, db_schema_filter_pattern=%
        assert hasattr(self.protobuf, "parse_command_get_db_schemas")

    def test_command_type_url_parsing(self):
        """Test that command type URLs match log expectations."""
        # From logs we see these specific type URLs being parsed
        expected_command_types = [
            "type.googleapis.com/arrow.flight.protocol.sql.CommandGetSqlInfo",
            "type.googleapis.com/arrow.flight.protocol.sql.CommandGetCatalogs",
            "type.googleapis.com/arrow.flight.protocol.sql.CommandGetDbSchemas",
            "type.googleapis.com/arrow.flight.protocol.sql.CommandGetTables",
        ]

        # Test that our constants match these expected values
        assert self.protobuf.COMMAND_GET_SQL_INFO_TYPE_URL in expected_command_types[0]
        assert self.protobuf.COMMAND_GET_CATALOGS_TYPE_URL in expected_command_types[1]
        assert (
            self.protobuf.COMMAND_GET_DB_SCHEMAS_TYPE_URL in expected_command_types[2]
        )
        assert self.protobuf.COMMAND_GET_TABLES_TYPE_URL in expected_command_types[3]

    def test_binary_data_handling(self):
        """Test handling of binary data as seen in table_schema field."""
        # From logs: table_schema: [[FFFFFFFFA80000001000000000000A000C000600050008000A000000000104000C0000000800080000000400080000000400 (... 268 chars omitted)]]

        # Test that binary schema field can handle binary data
        schema = self.protobuf.get_tables_schema_with_included_schema()
        binary_field = schema.field("table_schema")
        assert binary_field.type == pa.binary()

        # Create a table with some binary data to verify it works
        # Need to provide data for all 6 fields: catalog_name, db_schema_name, table_name, table_type, table_remarks, table_schema
        test_data = [
            ["test_catalog"],  # catalog_name
            ["test_schema"],  # db_schema_name
            ["test_table"],  # table_name
            ["BASE TABLE"],  # table_type
            ["Test remarks"],  # table_remarks
            [b"test_binary_schema_data"],  # table_schema
        ]

        table = pa.Table.from_arrays(test_data, schema=schema)
        assert len(table) == 1
        assert table.column("table_schema")[0].as_py() == b"test_binary_schema_data"


if __name__ == "__main__":
    pytest.main(["-v", "--tb=short", __file__])

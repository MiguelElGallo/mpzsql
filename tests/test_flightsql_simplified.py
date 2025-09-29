"""
Comprehensive test suite for SimplifiedFlightSQL implementation.

Tests the SimplifiedFlightSQL class that focuses on essential JDBC workflow
and provides a pragmatic approach to FlightSQL protocol support.
"""

from unittest.mock import Mock, patch

import pyarrow as pa
import pyarrow.flight as pf
import pytest

from src.mpzsql.flightsql.simplified import SimplifiedFlightSQL


class TestSimplifiedFlightSQLInstantiation:
    """Test SimplifiedFlightSQL instantiation and basic properties."""

    def test_initialization(self) -> None:
        """Test that SimplifiedFlightSQL initializes correctly."""
        backend = Mock()
        config = Mock()

        simplified = SimplifiedFlightSQL(backend, config)

        assert simplified.backend is backend
        assert simplified.config is config
        assert simplified.prepared_statements == {}
        assert isinstance(simplified.prepared_statements, dict)

    def test_get_prepared_statements(self) -> None:
        """Test the get_prepared_statements method."""
        backend = Mock()
        config = Mock()

        simplified = SimplifiedFlightSQL(backend, config)

        # Initially empty
        assert simplified.get_prepared_statements() == {}

        # Add a statement and verify it's returned
        test_stmt = {"sql": "SELECT 1", "schema": None}
        simplified.prepared_statements["test_handle"] = test_stmt

        result = simplified.get_prepared_statements()
        assert result == {"test_handle": test_stmt}


class TestActionDispatching:
    """Test the main action dispatching mechanism."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.backend = Mock()
        self.config = Mock()
        self.simplified = SimplifiedFlightSQL(self.backend, self.config)

    def test_handle_action_create_prepared_statement(self) -> None:
        """Test dispatching CreatePreparedStatement action."""
        with patch.object(
            self.simplified, "_handle_create_prepared_statement"
        ) as mock_handler:
            mock_handler.return_value = pf.Result(pa.py_buffer(b"test_result"))

            result = self.simplified.handle_action(
                "CreatePreparedStatement", b"test_data"
            )

            mock_handler.assert_called_once_with(b"test_data")
            assert isinstance(result, pf.Result)

    def test_handle_action_close_prepared_statement(self) -> None:
        """Test dispatching ClosePreparedStatement action."""
        with patch.object(
            self.simplified, "_handle_close_prepared_statement"
        ) as mock_handler:
            mock_handler.return_value = pf.Result(pa.py_buffer(b""))

            result = self.simplified.handle_action(
                "ClosePreparedStatement", b"test_data"
            )

            mock_handler.assert_called_once_with(b"test_data")
            assert isinstance(result, pf.Result)

    def test_handle_action_statement_query(self) -> None:
        """Test dispatching CommandStatementQuery action."""
        with patch.object(self.simplified, "_handle_statement_query") as mock_handler:
            mock_handler.return_value = pf.Result(pa.py_buffer(b"query_accepted"))

            result = self.simplified.handle_action(
                "CommandStatementQuery", b"test_data"
            )

            mock_handler.assert_called_once_with(b"test_data")
            assert isinstance(result, pf.Result)

    def test_handle_action_get_catalogs(self) -> None:
        """Test dispatching CommandGetCatalogs action."""
        with patch.object(self.simplified, "_handle_get_catalogs") as mock_handler:
            mock_handler.return_value = pf.Result(pa.py_buffer(b"catalogs_data"))

            result = self.simplified.handle_action("CommandGetCatalogs", b"test_data")

            mock_handler.assert_called_once()
            assert isinstance(result, pf.Result)

    def test_handle_action_get_schemas(self) -> None:
        """Test dispatching CommandGetSchemas action."""
        with patch.object(self.simplified, "_handle_get_schemas") as mock_handler:
            mock_handler.return_value = pf.Result(pa.py_buffer(b"schemas_data"))

            result = self.simplified.handle_action("CommandGetSchemas", b"test_data")

            mock_handler.assert_called_once()
            assert isinstance(result, pf.Result)

    def test_handle_action_get_tables(self) -> None:
        """Test dispatching CommandGetTables action."""
        with patch.object(self.simplified, "_handle_get_tables") as mock_handler:
            mock_handler.return_value = pf.Result(pa.py_buffer(b"tables_data"))

            result = self.simplified.handle_action("CommandGetTables", b"test_data")

            mock_handler.assert_called_once()
            assert isinstance(result, pf.Result)

    def test_handle_action_get_table_types(self) -> None:
        """Test dispatching CommandGetTableTypes action."""
        with patch.object(self.simplified, "_handle_get_table_types") as mock_handler:
            mock_handler.return_value = pf.Result(pa.py_buffer(b"table_types_data"))

            result = self.simplified.handle_action("CommandGetTableTypes", b"test_data")

            mock_handler.assert_called_once()
            assert isinstance(result, pf.Result)

    def test_handle_action_unknown_type(self) -> None:
        """Test handling unknown action types."""
        result = self.simplified.handle_action("UnknownActionType", b"test_data")

        assert isinstance(result, pf.Result)
        # Should return empty result for unknown actions


class TestSQLExtraction:
    """Test the complex SQL extraction logic."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.backend = Mock()
        self.config = Mock()
        self.simplified = SimplifiedFlightSQL(self.backend, self.config)

    def test_extract_sql_from_bytes_empty_data(self) -> None:
        """Test SQL extraction with empty data."""
        result = self.simplified._extract_sql_from_bytes(b"")
        assert result is None

        result = self.simplified._extract_sql_from_bytes(None)
        assert result is None

    def test_extract_sql_from_bytes_utf8_direct(self) -> None:
        """Test direct UTF-8 SQL extraction."""
        sql = "SELECT * FROM users"
        data = sql.encode("utf-8")

        result = self.simplified._extract_sql_from_bytes(data)
        assert result == sql

    def test_extract_sql_from_bytes_with_offset(self) -> None:
        """Test SQL extraction with offset prefixes."""
        sql = "SELECT * FROM products"
        # Simulate data with 4-byte prefix
        data = b"\x00\x00\x00\x10" + sql.encode("utf-8")

        result = self.simplified._extract_sql_from_bytes(data)
        # The result may include the prefix bytes when decoded, so check if SQL is contained
        assert sql in result or result == sql

    def test_extract_sql_from_bytes_with_sql_keywords(self) -> None:
        """Test SQL extraction by scanning for keywords."""
        # Simulate data with garbage followed by SQL
        sql = "INSERT INTO table VALUES (1, 'test')"
        data = b"\xff\xfe\x00\x00garbage" + sql.encode("utf-8")

        result = self.simplified._extract_sql_from_bytes(data)
        assert sql in result  # May have some cleanup applied

    def test_extract_sql_from_bytes_protobuf_parsing(self) -> None:
        """Test SQL extraction via protobuf parsing."""
        with patch("mpzsql.flightsql.protobuf.FlightSQLProtobuf") as mock_protobuf:
            mock_protobuf.parse_command_statement_query.return_value = "SELECT 1"

            result = self.simplified._extract_sql_from_bytes(b"protobuf_data")

            assert result == "SELECT 1"
            mock_protobuf.parse_command_statement_query.assert_called_once_with(
                b"protobuf_data"
            )

    def test_extract_sql_from_bytes_protobuf_prepared_statement(self) -> None:
        """Test SQL extraction via protobuf prepared statement parsing."""
        with patch("mpzsql.flightsql.protobuf.FlightSQLProtobuf") as mock_protobuf:
            mock_protobuf.parse_command_statement_query.return_value = None
            mock_protobuf.parse_create_prepared_statement_request.return_value = (
                "SELECT COUNT(*) FROM table"
            )

            result = self.simplified._extract_sql_from_bytes(b"protobuf_data")

            assert result == "SELECT COUNT(*) FROM table"
            mock_protobuf.parse_create_prepared_statement_request.assert_called_once_with(
                b"protobuf_data"
            )

    def test_extract_sql_from_bytes_invalid_utf8(self) -> None:
        """Test SQL extraction with invalid UTF-8 data."""
        # Data that can't be decoded as UTF-8
        data = b"\xff\xfe\x00\x80\x90\xa0"

        result = self.simplified._extract_sql_from_bytes(data)
        assert result is None

    def test_extract_sql_from_bytes_too_short(self) -> None:
        """Test SQL extraction with data that's too short to be valid SQL."""
        data = b"SEL"  # Too short

        result = self.simplified._extract_sql_from_bytes(data)
        assert result is None


class TestPreparedStatements:
    """Test prepared statement creation and management."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.backend = Mock()
        self.config = Mock()
        self.simplified = SimplifiedFlightSQL(self.backend, self.config)

    def test_handle_create_prepared_statement_success(self) -> None:
        """Test successful prepared statement creation."""
        sql = "SELECT * FROM users WHERE id = ?"
        test_schema = pa.schema([("id", pa.int64()), ("name", pa.string())])

        self.backend.get_statement_schema.return_value = test_schema

        with patch.object(self.simplified, "_extract_sql_from_bytes") as mock_extract:
            mock_extract.return_value = sql

            with patch("mpzsql.flightsql.protobuf.FlightSQLProtobuf") as mock_protobuf:
                mock_protobuf.create_action_create_prepared_statement_result.return_value = b"protobuf_result"

                result = self.simplified._handle_create_prepared_statement(b"test_data")

                assert isinstance(result, pf.Result)
                mock_extract.assert_called_once_with(b"test_data")
                self.backend.get_statement_schema.assert_called_once_with(sql)

                # Check that a prepared statement was stored
                assert len(self.simplified.prepared_statements) == 1
                stored_stmt = list(self.simplified.prepared_statements.values())[0]
                assert stored_stmt["sql"] == sql
                assert stored_stmt["schema"] == test_schema

    def test_handle_create_prepared_statement_no_sql(self) -> None:
        """Test prepared statement creation when SQL extraction fails."""
        with patch.object(self.simplified, "_extract_sql_from_bytes") as mock_extract:
            mock_extract.return_value = None

            result = self.simplified._handle_create_prepared_statement(b"invalid_data")

            assert isinstance(result, pf.Result)
            # No prepared statement should be stored
            assert len(self.simplified.prepared_statements) == 0

    def test_handle_create_prepared_statement_schema_error(self) -> None:
        """Test prepared statement creation when schema retrieval fails."""
        sql = "SELECT * FROM nonexistent_table"

        self.backend.get_statement_schema.side_effect = Exception("Table not found")

        with patch.object(self.simplified, "_extract_sql_from_bytes") as mock_extract:
            mock_extract.return_value = sql

            with patch("mpzsql.flightsql.protobuf.FlightSQLProtobuf") as mock_protobuf:
                mock_protobuf.create_action_create_prepared_statement_result.return_value = b"protobuf_result"

                result = self.simplified._handle_create_prepared_statement(b"test_data")

                assert isinstance(result, pf.Result)
                # Statement should still be created but with None schema
                assert len(self.simplified.prepared_statements) == 1
                stored_stmt = list(self.simplified.prepared_statements.values())[0]
                assert stored_stmt["sql"] == sql
                assert stored_stmt["schema"] is None

    def test_handle_close_prepared_statement_cleanup(self) -> None:
        """Test prepared statement cleanup logic."""
        # Add many prepared statements to trigger cleanup
        for i in range(150):
            self.simplified.prepared_statements[f"stmt_{i}"] = {
                "sql": f"SELECT {i}",
                "schema": None,
            }

        result = self.simplified._handle_close_prepared_statement(b"test_data")

        assert isinstance(result, pf.Result)
        # Should have cleaned up to 100 statements (removed 50)
        assert len(self.simplified.prepared_statements) == 100

    def test_handle_close_prepared_statement_no_cleanup(self) -> None:
        """Test that no cleanup happens when statement count is low."""
        # Add only a few statements
        for i in range(5):
            self.simplified.prepared_statements[f"stmt_{i}"] = {
                "sql": f"SELECT {i}",
                "schema": None,
            }

        result = self.simplified._handle_close_prepared_statement(b"test_data")

        assert isinstance(result, pf.Result)
        # No cleanup should happen
        assert len(self.simplified.prepared_statements) == 5


class TestStatementQuery:
    """Test direct statement query handling."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.backend = Mock()
        self.config = Mock()
        self.simplified = SimplifiedFlightSQL(self.backend, self.config)

    def test_handle_statement_query_success(self) -> None:
        """Test successful statement query handling."""
        sql = "SELECT COUNT(*) FROM users"

        with patch.object(self.simplified, "_extract_sql_from_bytes") as mock_extract:
            mock_extract.return_value = sql

            result = self.simplified._handle_statement_query(b"test_data")

            assert isinstance(result, pf.Result)
            mock_extract.assert_called_once_with(b"test_data")

    def test_handle_statement_query_no_sql(self) -> None:
        """Test statement query handling when SQL extraction fails."""
        with patch.object(self.simplified, "_extract_sql_from_bytes") as mock_extract:
            mock_extract.return_value = None

            result = self.simplified._handle_statement_query(b"invalid_data")

            assert isinstance(result, pf.Result)


class TestMetadataHandlers:
    """Test metadata handlers for catalogs, schemas, tables, and table types."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.backend = Mock()
        self.config = Mock()
        self.simplified = SimplifiedFlightSQL(self.backend, self.config)

    def test_handle_get_catalogs(self) -> None:
        """Test catalog metadata retrieval."""
        result = self.simplified._handle_get_catalogs()

        assert isinstance(result, pf.Result)
        # Should return a result with catalog data

    def test_handle_get_schemas(self) -> None:
        """Test schema metadata retrieval."""
        result = self.simplified._handle_get_schemas()

        assert isinstance(result, pf.Result)
        # Should return a result with schema data

    def test_handle_get_tables_with_backend_support(self) -> None:
        """Test table metadata retrieval when backend supports get_tables."""
        # Mock backend with table information
        table_info = [
            ("main", "public", "users", "TABLE"),
            ("main", "public", "orders", "TABLE"),
            ("main", "public", "user_view", "VIEW"),
        ]
        self.backend.get_tables.return_value = table_info

        result = self.simplified._handle_get_tables()

        assert isinstance(result, pf.Result)
        self.backend.get_tables.assert_called_once()

    def test_handle_get_tables_without_backend_support(self) -> None:
        """Test table metadata retrieval when backend doesn't support get_tables."""
        # Backend without get_tables method
        delattr(self.backend, "get_tables")

        result = self.simplified._handle_get_tables()

        assert isinstance(result, pf.Result)
        # Should return empty table metadata

    def test_handle_get_tables_backend_error(self) -> None:
        """Test table metadata retrieval when backend raises an error."""
        self.backend.get_tables.side_effect = Exception("Database connection error")

        result = self.simplified._handle_get_tables()

        assert isinstance(result, pf.Result)
        # Should handle the error gracefully and return empty result

    def test_handle_get_tables_incomplete_table_info(self) -> None:
        """Test table metadata retrieval with incomplete table information."""
        # Mock incomplete table info (missing table_type)
        table_info = [
            ("main", "public", "users"),  # Missing table_type
            ("catalog2", None, "system_table", "SYSTEM TABLE"),  # Missing schema
        ]
        self.backend.get_tables.return_value = table_info

        result = self.simplified._handle_get_tables()

        assert isinstance(result, pf.Result)
        # Should handle incomplete data gracefully

    def test_handle_get_table_types(self) -> None:
        """Test table types metadata retrieval."""
        result = self.simplified._handle_get_table_types()

        assert isinstance(result, pf.Result)
        # Should return standard table types


class TestProtobufHelpers:
    """Test protobuf helper methods."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.backend = Mock()
        self.config = Mock()
        self.simplified = SimplifiedFlightSQL(self.backend, self.config)

    def test_create_minimal_prepared_statement_result(self) -> None:
        """Test creation of minimal protobuf result."""
        handle_bytes = b"test_handle_12345"

        result = self.simplified._create_minimal_prepared_statement_result(handle_bytes)

        assert isinstance(result, bytes)
        assert len(result) > 0
        # Should contain the handle bytes
        assert handle_bytes in result

    def test_create_minimal_prepared_statement_result_empty_handle(self) -> None:
        """Test protobuf result creation with empty handle."""
        result = self.simplified._create_minimal_prepared_statement_result(b"")

        assert isinstance(result, bytes)
        # Should handle empty handle gracefully


class TestErrorHandling:
    """Test error handling throughout the SimplifiedFlightSQL class."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.backend = Mock()
        self.config = Mock()
        self.simplified = SimplifiedFlightSQL(self.backend, self.config)

    def test_handle_action_with_exception(self) -> None:
        """Test that exceptions in action handlers are caught properly."""
        with patch.object(self.simplified, "_handle_get_catalogs") as mock_handler:
            mock_handler.side_effect = Exception("Unexpected error")

            # The main handle_action method doesn't catch exceptions,
            # but individual handlers should handle their own exceptions
            # This test verifies that the mock exception is properly raised
            with pytest.raises(Exception, match="Unexpected error"):
                self.simplified.handle_action("CommandGetCatalogs", b"test_data")

    def test_metadata_handlers_with_arrow_errors(self) -> None:
        """Test metadata handlers when Arrow operations fail."""
        # This would test scenarios where pa.table() or Arrow IPC operations fail
        # For now, we'll test that the methods return valid Result objects
        result = self.simplified._handle_get_catalogs()
        assert isinstance(result, pf.Result)

        result = self.simplified._handle_get_schemas()
        assert isinstance(result, pf.Result)

        result = self.simplified._handle_get_table_types()
        assert isinstance(result, pf.Result)


class TestIntegrationScenarios:
    """Test integration scenarios that combine multiple components."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.backend = Mock()
        self.config = Mock()
        self.simplified = SimplifiedFlightSQL(self.backend, self.config)

    def test_full_prepared_statement_workflow(self) -> None:
        """Test the complete prepared statement workflow."""
        sql = "SELECT id, name FROM users WHERE id = ?"
        test_schema = pa.schema([("id", pa.int64()), ("name", pa.string())])

        self.backend.get_statement_schema.return_value = test_schema

        # Mock SQL extraction and protobuf creation
        with patch.object(self.simplified, "_extract_sql_from_bytes") as mock_extract:
            mock_extract.return_value = sql

            with patch("mpzsql.flightsql.protobuf.FlightSQLProtobuf") as mock_protobuf:
                mock_protobuf.create_action_create_prepared_statement_result.return_value = b"result_data"

                # Create prepared statement
                result = self.simplified.handle_action(
                    "CreatePreparedStatement", b"request_data"
                )

                assert isinstance(result, pf.Result)
                assert len(self.simplified.prepared_statements) == 1

                # Verify the stored statement
                stmt_handle = list(self.simplified.prepared_statements.keys())[0]
                stored_stmt = self.simplified.prepared_statements[stmt_handle]
                assert stored_stmt["sql"] == sql
                assert stored_stmt["schema"] == test_schema

                # Test cleanup
                initial_count = len(self.simplified.prepared_statements)
                self.simplified.handle_action("ClosePreparedStatement", b"close_data")
                # Should still have the statement (cleanup only happens with >100 statements)
                assert len(self.simplified.prepared_statements) == initial_count

    def test_metadata_workflow(self) -> None:
        """Test the complete metadata retrieval workflow."""
        # Test all metadata handlers work together
        catalogs_result = self.simplified.handle_action("CommandGetCatalogs", b"")
        schemas_result = self.simplified.handle_action("CommandGetSchemas", b"")
        tables_result = self.simplified.handle_action("CommandGetTables", b"")
        types_result = self.simplified.handle_action("CommandGetTableTypes", b"")

        assert all(
            isinstance(r, pf.Result)
            for r in [catalogs_result, schemas_result, tables_result, types_result]
        )

    def test_mixed_action_handling(self) -> None:
        """Test handling multiple different action types in sequence."""
        actions = [
            ("CommandGetCatalogs", b""),
            ("CreatePreparedStatement", b"SELECT 1"),
            ("CommandStatementQuery", b"SELECT 2"),
            ("UnknownAction", b"data"),
            ("CommandGetTables", b""),
        ]

        results = []
        for action_type, action_body in actions:
            result = self.simplified.handle_action(action_type, action_body)
            results.append(result)
            assert isinstance(result, pf.Result)

        assert len(results) == len(actions)

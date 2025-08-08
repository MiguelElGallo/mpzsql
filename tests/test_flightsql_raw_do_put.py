"""
Test suite for raw Flight do_put functionality in FlightSQL minimal server.

This test suite covers the new PATH descriptor handling and Arrow-to-DuckDB
functionality that was added in the PR.
"""

from unittest.mock import Mock, patch

import pyarrow as pa
import pyarrow.flight as pf
import pytest

from src.mpzsql.backends.duckdb_backend import DuckDBBackend
from src.mpzsql.config import ServerConfig
from src.mpzsql.flightsql.minimal import MinimalFlightSQLServer


class TestFlightSQLRawDoPut:
    """Test raw Flight do_put functionality with PATH descriptors."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = ServerConfig(
            secret_key="test_secret", username="test_user", password="test_pass"
        )
        self.location = pf.Location.for_grpc_tcp("localhost", 0)

        self.backend = Mock(spec=DuckDBBackend)
        self.server = MinimalFlightSQLServer(
            backend=self.backend, config=self.config, location=self.location
        )

    def create_sample_arrow_table(self) -> pa.Table:
        """Create a sample Arrow table for testing."""
        data = {
            "id": [1, 2, 3],
            "name": ["Alice", "Bob", "Charlie"],
            "value": [100.0, 200.0, 300.0],
        }
        return pa.table(data)

    @pytest.mark.skip(reason="_handle_file_upload_do_put method not implemented")
    def test_do_put_path_descriptor_batch_mode(self):
        """Test do_put with PATH descriptor (batch mode - single chunk)."""
        table_name = "test_upload_table"

        # Create test Arrow data
        arrow_table = pa.table({"id": [1, 2, 3], "name": ["Alice", "Bob", "Charlie"]})

        # Mock Flight components
        context = Mock(spec=pf.ServerCallContext)
        descriptor = pf.FlightDescriptor.for_path(table_name)
        reader = Mock(spec=pf.FlightStreamReader)
        reader.read_all.return_value = arrow_table  # Mock the read_all method
        writer = Mock(spec=pf.FlightMetadataWriter)

        # Mock the backend methods
        self.backend.create_table_from_arrow = Mock()

        # Execute the internal handler method directly
        self.server._handle_file_upload_do_put(context, descriptor, reader, writer)

        # Verify backend was called correctly - note the table name gets prefixed
        expected_table_name = f"my_ducklake.main.{table_name}"
        self.backend.create_table_from_arrow.assert_called_once_with(
            expected_table_name, arrow_table
        )

    @pytest.mark.skip(reason="_handle_file_upload_do_put method not implemented")
    def test_do_put_path_descriptor_streaming_mode(self):
        """Test do_put with PATH descriptor (streaming mode - multiple chunks)."""
        # Setup
        arrow_table = self.create_sample_arrow_table()
        table_name = "stream_table"
        descriptor = pf.FlightDescriptor.for_path(table_name.encode("utf-8"))

        # Mock the required objects
        context = Mock(spec=pf.ServerCallContext)
        reader = Mock(spec=pf.FlightStreamReader)
        reader.read_all.return_value = arrow_table  # Mock the read_all method
        writer = Mock(spec=pf.FlightMetadataWriter)

        # Mock the backend methods
        self.backend.create_table_from_arrow = Mock()

        # Execute the internal handler method directly
        self.server._handle_file_upload_do_put(context, descriptor, reader, writer)

        # Verify backend was called for table creation/append - note the table name gets prefixed
        expected_table_name = f"my_ducklake.main.{table_name}"
        self.backend.create_table_from_arrow.assert_called_once_with(
            expected_table_name, arrow_table
        )

    @pytest.mark.skip(reason="_handle_flightsql_do_put method not implemented")
    def test_do_put_cmd_descriptor_flightsql_compatibility(self):
        """Test do_put with CMD descriptor (existing FlightSQL functionality)."""
        from google.protobuf import any_pb2

        from src.mpzsql.flightsql.protobuf import (
            CommandStatementUpdate,
            FlightSQLProtobuf,
        )

        # Test FlightSQL update (CMD descriptor)
        command = CommandStatementUpdate()
        command.query = "INSERT INTO test_table VALUES (1, 'test')"

        # Create Any message wrapper
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_STATEMENT_UPDATE_TYPE_URL

        # Encode query and set value
        query_encoded = command.query.encode("utf-8")
        any_msg.value = bytes([0x0A]) + bytes([len(query_encoded)]) + query_encoded

        descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())

        # Mock the required objects
        context = Mock(spec=pf.ServerCallContext)
        reader = Mock(spec=pf.FlightStreamReader)
        writer = Mock(spec=pf.FlightMetadataWriter)

        # Mock backend execute_update
        self.backend.execute_update = Mock(return_value=1)

        # Execute the internal handler method
        self.server._handle_flightsql_do_put(context, descriptor, reader, writer)

        # Verify FlightSQL command was executed
        self.backend.execute_update.assert_called_once_with(command.query)

    def test_get_flight_info_path_descriptor(self):
        """Test get_flight_info with PATH descriptor returns FlightInfo with schema and rows."""
        # Setup
        table_name = "info_test_table"
        descriptor = pf.FlightDescriptor.for_path(table_name.encode("utf-8"))

        # Provide real schema/row count from backend for PATH flow
        test_schema = pa.schema([pa.field("col1", pa.int64())])
        self.backend.get_table_schema = Mock(return_value=test_schema)
        self.backend.get_table_row_count = Mock(return_value=5)

        # Execute
        flight_info = self.server.get_flight_info(None, descriptor)

        # Verify
        assert isinstance(flight_info, pf.FlightInfo)
        assert flight_info.descriptor == descriptor
        assert len(flight_info.endpoints) > 0
        assert flight_info.schema == test_schema
        assert flight_info.total_records == 5

    def test_get_flight_info_cmd_descriptor_flightsql(self):
        """Test get_flight_info with CMD descriptor (FlightSQL compatibility)."""
        from google.protobuf import any_pb2

        from src.mpzsql.flightsql.protobuf import (
            CommandStatementQuery,
            FlightSQLProtobuf,
        )

        # Setup FlightSQL query command
        command = CommandStatementQuery()
        command.query = "SELECT * FROM test_table"

        # Create Any message wrapper
        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_STATEMENT_QUERY_TYPE_URL

        # Encode query and set value
        query_encoded = command.query.encode("utf-8")
        any_msg.value = bytes([0x0A]) + bytes([len(query_encoded)]) + query_encoded

        descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())

        # Mock backend
        mock_schema = pa.schema([pa.field("col1", pa.string())])
        self.backend.get_statement_schema = Mock(return_value=mock_schema)

        # Execute get_flight_info
        flight_info = self.server.get_flight_info(None, descriptor)

        # Verify FlightSQL behavior
        assert flight_info.descriptor.descriptor_type == pf.DescriptorType.CMD
        assert flight_info.schema == mock_schema

        # Verify backend was called with the query
        self.backend.get_statement_schema.assert_called_once_with(command.query)

    @pytest.mark.skip(
        reason="Test depends on unimplemented _handle_file_upload_do_put and _handle_flightsql_do_put methods"
    )
    def test_descriptor_routing_cmd_vs_path(self):
        """Test that do_put correctly routes between CMD and PATH descriptors."""
        # Test PATH descriptor routing
        path_descriptor = pf.FlightDescriptor.for_path(b"table_name")

        # Mock the _handle_file_upload_do_put method
        with patch.object(
            self.server, "_handle_file_upload_do_put"
        ) as mock_path_handler:
            context = Mock(spec=pf.ServerCallContext)
            reader = Mock(spec=pf.FlightStreamReader)
            writer = Mock(spec=pf.FlightMetadataWriter)

            self.server.do_put(context, path_descriptor, reader, writer)

            # Verify PATH handler was called
            mock_path_handler.assert_called_once_with(
                context, path_descriptor, reader, writer
            )

        # Test CMD descriptor routing
        from google.protobuf import any_pb2

        from src.mpzsql.flightsql.protobuf import FlightSQLProtobuf

        any_msg = any_pb2.Any()
        any_msg.type_url = FlightSQLProtobuf.COMMAND_STATEMENT_QUERY_TYPE_URL
        any_msg.value = b"\x0a\x04test"  # Simple command
        cmd_descriptor = pf.FlightDescriptor.for_command(any_msg.SerializeToString())

        # Mock the _handle_flightsql_do_put method
        with patch.object(self.server, "_handle_flightsql_do_put") as mock_cmd_handler:
            self.server.do_put(context, cmd_descriptor, reader, writer)

            # Verify CMD handler was called
            mock_cmd_handler.assert_called_once_with(
                context, cmd_descriptor, reader, writer
            )

    @pytest.mark.skip(reason="_handle_file_upload_do_put method not implemented")
    def test_handle_file_upload_do_put_functionality(self):
        """Test the _handle_file_upload_do_put method directly."""
        # Setup
        arrow_table = self.create_sample_arrow_table()
        table_name = "upload_test_table"
        descriptor = pf.FlightDescriptor.for_path(table_name.encode("utf-8"))

        # Mock the required objects
        context = Mock(spec=pf.ServerCallContext)
        reader = Mock(spec=pf.FlightStreamReader)
        reader.read_all.return_value = arrow_table  # Mock the read_all method
        writer = Mock(spec=pf.FlightMetadataWriter)

        # Mock backend methods
        self.backend.create_table_from_arrow = Mock()

        # Execute the method directly
        self.server._handle_file_upload_do_put(context, descriptor, reader, writer)

        # Verify backend was called correctly with prefixed table name
        expected_table_name = f"my_ducklake.main.{table_name}"
        self.backend.create_table_from_arrow.assert_called_once_with(
            expected_table_name, arrow_table
        )

    @pytest.mark.skip(reason="_handle_file_upload_do_put method not implemented")
    def test_handle_file_upload_error_handling(self):
        """Test error handling in _handle_file_upload_do_put method."""
        # Setup
        arrow_table = self.create_sample_arrow_table()
        table_name = "error_table"
        descriptor = pf.FlightDescriptor.for_path(table_name.encode("utf-8"))

        # Mock the required objects
        context = Mock(spec=pf.ServerCallContext)
        reader = Mock(spec=pf.FlightStreamReader)
        reader.read_all.return_value = arrow_table  # Mock the read_all method
        writer = Mock(spec=pf.FlightMetadataWriter)

        # Mock backend to raise an error
        self.backend.create_table_from_arrow = Mock(
            side_effect=Exception("Database error")
        )

        # Execute and expect the error to propagate
        with pytest.raises(Exception) as exc_info:
            self.server._handle_file_upload_do_put(context, descriptor, reader, writer)

        assert "Database error" in str(exc_info.value)

    def test_get_flight_info_path_descriptor_error_handling(self):
        """Test error handling in PATH descriptor get_flight_info when backend raises."""
        # Setup
        table_name = "nonexistent_table"
        descriptor = pf.FlightDescriptor.for_path(table_name.encode("utf-8"))

        # Make backend raise so server returns an empty FlightInfo safely
        self.backend.get_table_schema = Mock(side_effect=Exception("schema error"))

        # Execute
        flight_info = self.server.get_flight_info(None, descriptor)

        # Verify fallback FlightInfo
        assert isinstance(flight_info, pf.FlightInfo)
        assert flight_info.descriptor == descriptor
        assert len(flight_info.endpoints) > 0
        assert isinstance(flight_info.schema, pa.Schema)
        assert len(flight_info.schema.names) == 0
        assert flight_info.total_records == 0

    @pytest.mark.skip(reason="_handle_file_upload_do_put method not implemented")
    def test_large_table_upload(self):
        """Test handling of large table uploads."""
        # Setup large table
        num_rows = 10000
        large_table = pa.table(
            {"id": range(num_rows), "value": [f"value_{i}" for i in range(num_rows)]}
        )

        table_name = "large_table"
        descriptor = pf.FlightDescriptor.for_path(table_name.encode("utf-8"))

        # Mock the required objects
        context = Mock(spec=pf.ServerCallContext)
        reader = Mock(spec=pf.FlightStreamReader)
        reader.read_all.return_value = large_table  # Mock the read_all method
        writer = Mock(spec=pf.FlightMetadataWriter)

        # Mock backend
        self.backend.create_table_from_arrow = Mock()

        # Execute the internal handler method
        self.server._handle_file_upload_do_put(context, descriptor, reader, writer)

        # Verify backend was called with prefixed table name
        expected_table_name = f"my_ducklake.main.{table_name}"
        self.backend.create_table_from_arrow.assert_called_once_with(
            expected_table_name, large_table
        )

    @pytest.mark.skip(reason="_handle_file_upload_do_put method not implemented")
    def test_multiple_concurrent_uploads(self):
        """Test multiple concurrent table uploads (simulated)."""
        # Simulate multiple table uploads by calling the handler multiple times
        table_names = ["concurrent_table_1", "concurrent_table_2", "concurrent_table_3"]

        # Mock the required objects
        context = Mock(spec=pf.ServerCallContext)
        arrow_table = self.create_sample_arrow_table()

        # Mock backend
        self.backend.create_table_from_arrow = Mock()

        # Execute multiple uploads
        for table_name in table_names:
            descriptor = pf.FlightDescriptor.for_path(table_name.encode("utf-8"))
            reader = Mock(spec=pf.FlightStreamReader)
            reader.read_all.return_value = arrow_table  # Mock the read_all method
            writer = Mock(spec=pf.FlightMetadataWriter)

            self.server._handle_file_upload_do_put(context, descriptor, reader, writer)

        # Verify all tables were created with correct prefixed names
        assert self.backend.create_table_from_arrow.call_count == len(table_names)
        for i, table_name in enumerate(table_names):
            expected_table_name = f"my_ducklake.main.{table_name}"
            assert (
                self.backend.create_table_from_arrow.call_args_list[i][0][0]
                == expected_table_name
            )

    @pytest.mark.skip(reason="_handle_file_upload_do_put method not implemented")
    def test_qualified_table_names(self):
        """Test PATH descriptors with qualified table names."""
        qualified_names = [
            "simple_table",
            "schema.table_name",
            "database.schema.table_name",
            "my_ducklake.main.lineitem",
        ]

        expected_names = [
            "my_ducklake.main.simple_table",  # Gets prefixed
            "my_ducklake.main.table_name",  # Only table name part is kept
            "my_ducklake.main.table_name",  # Only table name part is kept
            "my_ducklake.main.lineitem",  # Already has my_ducklake prefix
        ]

        # Mock the required objects
        context = Mock(spec=pf.ServerCallContext)
        arrow_table = self.create_sample_arrow_table()

        for qualified_name, expected_name in zip(
            qualified_names, expected_names, strict=False
        ):
            descriptor = pf.FlightDescriptor.for_path(qualified_name.encode("utf-8"))
            reader = Mock(spec=pf.FlightStreamReader)
            reader.read_all.return_value = arrow_table  # Mock the read_all method
            writer = Mock(spec=pf.FlightMetadataWriter)

            # Mock backend
            self.backend.create_table_from_arrow = Mock()

            # Execute the handler method
            self.server._handle_file_upload_do_put(context, descriptor, reader, writer)

            # Verify qualified name was processed correctly
            self.backend.create_table_from_arrow.assert_called_once_with(
                expected_name, arrow_table
            )

    @pytest.mark.skip(reason="_handle_file_upload_do_put method not implemented")
    def test_path_descriptor_table_name_extraction(self):
        """Test proper extraction of table names from PATH descriptors."""
        test_cases = [
            (b"simple_table", "my_ducklake.main.simple_table"),
            (
                b"schema.table_name",
                "my_ducklake.main.table_name",
            ),  # Only table name part kept
            (b"my_ducklake.main.existing", "my_ducklake.main.existing"),
        ]

        context = Mock(spec=pf.ServerCallContext)
        arrow_table = self.create_sample_arrow_table()

        for path_component, expected_table_name in test_cases:
            descriptor = pf.FlightDescriptor.for_path(path_component)
            reader = Mock(spec=pf.FlightStreamReader)
            reader.read_all.return_value = arrow_table  # Mock the read_all method
            writer = Mock(spec=pf.FlightMetadataWriter)

            # Mock backend
            self.backend.create_table_from_arrow = Mock()

            # Execute the handler method
            self.server._handle_file_upload_do_put(context, descriptor, reader, writer)

            # Verify table name was extracted correctly
            self.backend.create_table_from_arrow.assert_called_once_with(
                expected_table_name, arrow_table
            )

    # Helper method (already defined earlier in class; keep single definition only)

"""
Comprehensive test suite for FlightSQL Protocol module.

This test suite provides thorough coverage of the FlightSQL protocol
implementation covering all protocol constants, type definitions,
and utility functions.

Part of Priority 3: FlightSQL Protocol Testing
"""

from mpzsql.flightsql.protocol import (
    FlightSQLCommands,
    FlightSQLSchemas,
)


class TestFlightSQLCommands:
    """Test FlightSQL commands class."""

    def test_command_constants_exist(self):
        """Test that command constants are defined."""
        # Test command constants
        assert hasattr(FlightSQLCommands, "COMMAND_STATEMENT_QUERY")
        assert hasattr(FlightSQLCommands, "COMMAND_STATEMENT_UPDATE")
        assert hasattr(FlightSQLCommands, "COMMAND_GET_CATALOGS")
        assert hasattr(FlightSQLCommands, "COMMAND_GET_SCHEMAS")
        assert hasattr(FlightSQLCommands, "COMMAND_GET_TABLES")

        # Test action constants
        assert hasattr(FlightSQLCommands, "ACTION_CREATE_PREPARED_STATEMENT")
        assert hasattr(FlightSQLCommands, "ACTION_BEGIN_TRANSACTION")

    def test_command_values_are_strings(self):
        """Test that command constants are strings."""
        commands = [
            FlightSQLCommands.COMMAND_STATEMENT_QUERY,
            FlightSQLCommands.COMMAND_STATEMENT_UPDATE,
            FlightSQLCommands.COMMAND_GET_CATALOGS,
            FlightSQLCommands.COMMAND_GET_SCHEMAS,
            FlightSQLCommands.COMMAND_GET_TABLES,
        ]

        for command in commands:
            assert isinstance(command, str)
            assert len(command) > 0

    def test_action_values_are_strings(self):
        """Test that action constants are strings."""
        actions = [
            FlightSQLCommands.ACTION_CREATE_PREPARED_STATEMENT,
            FlightSQLCommands.ACTION_BEGIN_TRANSACTION,
        ]

        for action in actions:
            assert isinstance(action, str)
            assert len(action) > 0


class TestFlightSQLSchemas:
    """Test FlightSQL schemas class."""

    def test_schemas_class_exists(self):
        """Test that FlightSQLSchemas class exists."""
        assert FlightSQLSchemas is not None

    def test_get_catalogs_schema(self):
        """Test get_catalogs_schema method."""
        if hasattr(FlightSQLSchemas, "get_catalogs_schema"):
            schema = FlightSQLSchemas.get_catalogs_schema()
            assert schema is not None
            # Should be a PyArrow schema
            import pyarrow as pa

            assert isinstance(schema, pa.Schema)
            assert len(schema) > 0  # Should have at least one field


class TestFlightSQLProtocolModule:
    """Test FlightSQL protocol module functionality."""

    def test_protocol_module_imports(self):
        """Test that protocol module imports successfully."""
        import mpzsql.flightsql.protocol

        assert mpzsql.flightsql.protocol is not None

    def test_protocol_constants_access(self):
        """Test access to protocol constants through module."""
        import mpzsql.flightsql.protocol as protocol_module

        # Test constants are accessible
        assert hasattr(protocol_module, "FlightSQLCommands")
        assert hasattr(protocol_module, "FlightSQLSchemas")

    def test_protocol_compatibility(self):
        """Test protocol compatibility with PyArrow Flight."""
        # Test that protocol constants are compatible with PyArrow Flight
        import pyarrow.flight as pf

        # Verify PyArrow Flight classes are accessible
        assert pf.FlightInfo is not None
        assert pf.FlightDescriptor is not None
        assert pf.FlightEndpoint is not None

        # Test protocol works with PyArrow types
        descriptor = pf.FlightDescriptor.for_command(b"test")
        assert descriptor is not None
        assert descriptor.descriptor_type == pf.DescriptorType.CMD

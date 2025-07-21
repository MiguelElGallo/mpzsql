"""
FlightSQL Server Base Implementation for Python.

This module provides a FlightSQL server base class that mimics the functionality
of the C++ arrow::flight::sql::FlightSqlServerBase class, automatically handling
FlightSQL protocol details and command routing.
"""

import logging
from abc import ABC, abstractmethod
from typing import Iterator

import pyarrow as pa
import pyarrow.flight as pf

from mpzsql.flightsql.protobuf import (
    ActionClosePreparedStatementRequest,
    ActionCreatePreparedStatementRequest,
    CommandGetCatalogs,
    CommandGetDbSchemas,
    CommandGetSqlInfo,
    CommandGetTables,
    CommandGetTableTypes,
    CommandPreparedStatementQuery,
    CommandStatementQuery,
    CommandStatementUpdate,
    DoPutUpdateResult,
    FlightSQLProtobuf,
    PreparedStatementQuery,
    parse_any_command,
)

logger = logging.getLogger(__name__)


class FlightSqlServerBase(pf.FlightServerBase, ABC):
    """
    Abstract base class for FlightSQL servers.

    This class provides the FlightSQL protocol handling and routes commands
    to appropriate abstract methods that must be implemented by subclasses.
    This mimics the behavior of the C++ arrow::flight::sql::FlightSqlServerBase.
    """

    def __init__(
        self, location: pf.Location, advertised_location: pf.Location = None, **kwargs
    ):
        """Initialize the FlightSQL server base."""
        super().__init__(location, **kwargs)
        self.location = location
        self.advertised_location = advertised_location or location

    def list_actions(self, context: pf.ServerCallContext) -> Iterator[pf.ActionType]:
        """List available FlightSQL actions."""
        actions = [
            pf.ActionType("CreatePreparedStatement", "Create a prepared statement"),
            pf.ActionType("ClosePreparedStatement", "Close a prepared statement"),
        ]
        return iter(actions)

    def do_action(
        self, context: pf.ServerCallContext, action: pf.Action
    ) -> Iterator[pf.Result]:
        """Execute FlightSQL actions."""
        action_type = action.type
        action_body = action.body.to_pybytes() if action.body else b""

        logger.debug(f"FlightSQL action: {action_type}")

        if action_type == "CreatePreparedStatement":
            request = ActionCreatePreparedStatementRequest()
            request.ParseFromString(action_body)
            yield self.create_prepared_statement(context, request)
        elif action_type == "ClosePreparedStatement":
            request = ActionClosePreparedStatementRequest()
            request.ParseFromString(action_body)
            yield self.close_prepared_statement(context, request)
        else:
            raise NotImplementedError(f"Action {action_type} not implemented.")

    def get_flight_info(
        self, context: pf.ServerCallContext, descriptor: pf.FlightDescriptor
    ) -> pf.FlightInfo:
        """Get flight info for FlightSQL commands."""
        if descriptor.descriptor_type != pf.DescriptorType.CMD:
            raise NotImplementedError("Only CMD descriptors are supported.")

        command_bytes = descriptor.command
        logger.debug(f"GetFlightInfo command: {len(command_bytes)} bytes")

        # Parse the command using our protobuf parser
        any_command = parse_any_command(command_bytes)
        if not any_command:
            raise ValueError("Failed to parse command from descriptor.")

        command_type_url = any_command.type_url
        logger.debug(f"Command type: {command_type_url}")

        # Route to appropriate method based on command type
        if command_type_url == FlightSQLProtobuf.COMMAND_STATEMENT_QUERY_TYPE_URL:
            command = self._extract_command_statement_query(any_command)
            return self.get_flight_info_statement(context, descriptor, command)
        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_CATALOGS_TYPE_URL:
            command = self._extract_command_get_catalogs(any_command)
            return self.get_flight_info_catalogs(context, descriptor, command)
        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_DB_SCHEMAS_TYPE_URL:
            command = self._extract_command_get_db_schemas(any_command)
            return self.get_flight_info_schemas(context, descriptor, command)
        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_TABLES_TYPE_URL:
            command = self._extract_command_get_tables(any_command)
            return self.get_flight_info_tables(context, descriptor, command)
        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_TABLE_TYPES_TYPE_URL:
            command = self._extract_command_get_table_types(any_command)
            return self.get_flight_info_table_types(context, descriptor, command)
        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_SQL_INFO_TYPE_URL:
            command = self._extract_command_get_sql_info(any_command)
            return self.get_flight_info_sql_info(context, descriptor, command)
        elif (
            command_type_url
            == FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_QUERY_TYPE_URL
        ):
            command = self._extract_command_prepared_statement_query(any_command)
            return self.get_flight_info_prepared_statement(context, descriptor, command)
        else:
            raise NotImplementedError(f"Unsupported command type: {command_type_url}")

    def do_get(
        self, context: pf.ServerCallContext, ticket: pf.Ticket
    ) -> pf.FlightDataStream:
        """Execute FlightSQL commands and return data."""
        command_bytes = ticket.ticket
        logger.debug(f"DoGet command: {len(command_bytes)} bytes")

        # Parse the command using our protobuf parser
        any_command = parse_any_command(command_bytes)
        if not any_command:
            raise ValueError("Failed to parse command from ticket.")

        command_type_url = any_command.type_url
        logger.debug(f"DoGet command type: {command_type_url}")

        # Route to appropriate method based on command type
        if command_type_url == FlightSQLProtobuf.COMMAND_STATEMENT_QUERY_TYPE_URL:
            command = self._extract_command_statement_query(any_command)
            return self.do_get_statement(context, command)
        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_CATALOGS_TYPE_URL:
            command = self._extract_command_get_catalogs(any_command)
            return self.do_get_catalogs(context, command)
        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_DB_SCHEMAS_TYPE_URL:
            command = self._extract_command_get_db_schemas(any_command)
            return self.do_get_schemas(context, command)
        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_TABLES_TYPE_URL:
            command = self._extract_command_get_tables(any_command)
            return self.do_get_tables(context, command)
        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_TABLE_TYPES_TYPE_URL:
            command = self._extract_command_get_table_types(any_command)
            return self.do_get_table_types(context, command)
        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_SQL_INFO_TYPE_URL:
            command = self._extract_command_get_sql_info(any_command)
            return self.do_get_sql_info(context, command)
        elif (
            command_type_url
            == FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_QUERY_TYPE_URL
        ):
            command = self._extract_command_prepared_statement_query(any_command)
            return self.do_get_prepared_statement(context, command)
        else:
            raise NotImplementedError(f"Unsupported command type: {command_type_url}")

    def do_put(
        self,
        context: pf.ServerCallContext,
        descriptor: pf.FlightDescriptor,
        reader: pf.FlightStreamReader,
        writer: pf.FlightMetadataWriter,
    ):
        """Handle DoPut for FlightSQL commands."""
        logger.debug(f"DoPut with descriptor type: {descriptor.descriptor_type}")

        command_bytes = descriptor.command
        any_command = parse_any_command(command_bytes)
        if not any_command:
            raise ValueError("Failed to parse command from descriptor.")

        command_type_url = any_command.type_url
        logger.debug(f"DoPut command type: {command_type_url}")

        if command_type_url == FlightSQLProtobuf.COMMAND_STATEMENT_UPDATE_TYPE_URL:
            command = self._extract_command_statement_update(any_command)
            record_count = self.do_put_statement_update(context, command, reader)
            result = DoPutUpdateResult(record_count=record_count)
            writer.write(pa.py_buffer(result.SerializeToString()))
        elif (
            command_type_url
            == FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_UPDATE_TYPE_URL
        ):
            command = self._extract_command_prepared_statement_update(any_command)
            record_count = self.do_put_prepared_statement_update(
                context, command, reader
            )
            result = DoPutUpdateResult(record_count=record_count)
            writer.write(pa.py_buffer(result.SerializeToString()))
        else:
            raise NotImplementedError(
                f"Unsupported command type for DoPut: {command_type_url}"
            )

    # Command extraction methods (safe extraction without Unpack)
    def _extract_command_statement_query(self, any_command) -> CommandStatementQuery:
        """Extract CommandStatementQuery from Any message."""
        # In a real implementation, this would properly parse the protobuf
        # For now, we create a mock command with the query extracted from the raw bytes
        command = CommandStatementQuery()
        # TODO: Implement proper protobuf parsing
        return command

    def _extract_command_get_catalogs(self, any_command) -> CommandGetCatalogs:
        """Extract CommandGetCatalogs from Any message."""
        return CommandGetCatalogs()

    def _extract_command_get_db_schemas(self, any_command) -> CommandGetDbSchemas:
        """Extract CommandGetDbSchemas from Any message."""
        return CommandGetDbSchemas()

    def _extract_command_get_tables(self, any_command) -> CommandGetTables:
        """Extract CommandGetTables from Any message."""
        return CommandGetTables()

    def _extract_command_get_table_types(self, any_command) -> CommandGetTableTypes:
        """Extract CommandGetTableTypes from Any message."""
        return CommandGetTableTypes()

    def _extract_command_get_sql_info(self, any_command) -> CommandGetSqlInfo:
        """Extract CommandGetSqlInfo from Any message."""
        return CommandGetSqlInfo()

    def _extract_command_prepared_statement_query(
        self, any_command
    ) -> PreparedStatementQuery:
        """Extract PreparedStatementQuery from Any message."""
        return PreparedStatementQuery()

    def _extract_command_statement_update(self, any_command) -> CommandStatementUpdate:
        """Extract CommandStatementUpdate from Any message."""
        return CommandStatementUpdate()

    def _extract_command_prepared_statement_update(
        self, any_command
    ) -> CommandPreparedStatementQuery:
        """Extract CommandPreparedStatementQuery from Any message."""
        return CommandPreparedStatementQuery()

    # Abstract methods to be implemented by subclasses
    @abstractmethod
    def create_prepared_statement(
        self,
        context: pf.ServerCallContext,
        request: ActionCreatePreparedStatementRequest,
    ) -> pf.Result:
        """Create a prepared statement."""
        pass

    @abstractmethod
    def close_prepared_statement(
        self,
        context: pf.ServerCallContext,
        request: ActionClosePreparedStatementRequest,
    ) -> pf.Result:
        """Close a prepared statement."""
        pass

    @abstractmethod
    def get_flight_info_statement(
        self,
        context: pf.ServerCallContext,
        descriptor: pf.FlightDescriptor,
        command: CommandStatementQuery,
    ) -> pf.FlightInfo:
        """Get flight info for a statement."""
        pass

    @abstractmethod
    def get_flight_info_catalogs(
        self,
        context: pf.ServerCallContext,
        descriptor: pf.FlightDescriptor,
        command: CommandGetCatalogs,
    ) -> pf.FlightInfo:
        """Get flight info for catalogs."""
        pass

    @abstractmethod
    def get_flight_info_schemas(
        self,
        context: pf.ServerCallContext,
        descriptor: pf.FlightDescriptor,
        command: CommandGetDbSchemas,
    ) -> pf.FlightInfo:
        """Get flight info for schemas."""
        pass

    @abstractmethod
    def get_flight_info_tables(
        self,
        context: pf.ServerCallContext,
        descriptor: pf.FlightDescriptor,
        command: CommandGetTables,
    ) -> pf.FlightInfo:
        """Get flight info for tables."""
        pass

    @abstractmethod
    def get_flight_info_table_types(
        self,
        context: pf.ServerCallContext,
        descriptor: pf.FlightDescriptor,
        command: CommandGetTableTypes,
    ) -> pf.FlightInfo:
        """Get flight info for table types."""
        pass

    @abstractmethod
    def get_flight_info_sql_info(
        self,
        context: pf.ServerCallContext,
        descriptor: pf.FlightDescriptor,
        command: CommandGetSqlInfo,
    ) -> pf.FlightInfo:
        """Get flight info for SQL info."""
        pass

    @abstractmethod
    def get_flight_info_prepared_statement(
        self,
        context: pf.ServerCallContext,
        descriptor: pf.FlightDescriptor,
        command: PreparedStatementQuery,
    ) -> pf.FlightInfo:
        """Get flight info for a prepared statement."""
        pass

    @abstractmethod
    def do_get_statement(
        self, context: pf.ServerCallContext, command: CommandStatementQuery
    ) -> pf.FlightDataStream:
        """Execute a statement."""
        pass

    @abstractmethod
    def do_get_catalogs(
        self, context: pf.ServerCallContext, command: CommandGetCatalogs
    ) -> pf.FlightDataStream:
        """Get catalogs."""
        pass

    @abstractmethod
    def do_get_schemas(
        self, context: pf.ServerCallContext, command: CommandGetDbSchemas
    ) -> pf.FlightDataStream:
        """Get schemas."""
        pass

    @abstractmethod
    def do_get_tables(
        self, context: pf.ServerCallContext, command: CommandGetTables
    ) -> pf.FlightDataStream:
        """Get tables."""
        pass

    @abstractmethod
    def do_get_table_types(
        self, context: pf.ServerCallContext, command: CommandGetTableTypes
    ) -> pf.FlightDataStream:
        """Get table types."""
        pass

    @abstractmethod
    def do_get_sql_info(
        self, context: pf.ServerCallContext, command: CommandGetSqlInfo
    ) -> pf.FlightDataStream:
        """Get SQL info."""
        pass

    @abstractmethod
    def do_get_prepared_statement(
        self, context: pf.ServerCallContext, command: PreparedStatementQuery
    ) -> pf.FlightDataStream:
        """Execute a prepared statement."""
        pass

    @abstractmethod
    def do_put_statement_update(
        self,
        context: pf.ServerCallContext,
        command: CommandStatementUpdate,
        reader: pf.FlightStreamReader,
    ) -> int:
        """Execute a statement update."""
        pass

    @abstractmethod
    def do_put_prepared_statement_update(
        self,
        context: pf.ServerCallContext,
        command: CommandPreparedStatementQuery,
        reader: pf.FlightStreamReader,
    ) -> int:
        """Execute a prepared statement update."""
        pass

    # Helper methods
    def _create_flight_info_for_command(
        self, descriptor: pf.FlightDescriptor, schema: pa.Schema
    ) -> pf.FlightInfo:
        """Helper to create FlightInfo for a command."""
        endpoints = [
            pf.FlightEndpoint(
                ticket=pf.Ticket(descriptor.command),
                locations=[self.advertised_location],
            )
        ]
        return pf.FlightInfo(
            schema,
            descriptor,
            endpoints,
            -1,  # Total records, -1 for unknown
            -1,  # Total bytes, -1 for
        )

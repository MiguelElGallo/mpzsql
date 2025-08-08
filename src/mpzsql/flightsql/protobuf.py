"""
FlightSQL protobuf message definitions and handling.

This module implements the protobuf message formats expected by FlightSQL clients,
based on the Apache Arrow FlightSQL specification.
"""

import logging
import struct
import uuid
from typing import Optional, Tuple

import pyarrow as pa
from google.protobuf import any_pb2

from mpzsql.flightsql.generated.FlightSql_pb2 import (
    ActionBeginTransactionRequest as GeneratedActionBeginTransactionRequest,
)
from mpzsql.flightsql.generated.FlightSql_pb2 import (
    ActionBeginTransactionResult as GeneratedActionBeginTransactionResult,
)
from mpzsql.flightsql.generated.FlightSql_pb2 import (
    ActionClosePreparedStatementRequest as GeneratedActionClosePreparedStatementRequest,
)

# Import generated protobuf classes for gradual replacement
from mpzsql.flightsql.generated.FlightSql_pb2 import (
    ActionCreatePreparedStatementRequest as GeneratedActionCreatePreparedStatementRequest,
)
from mpzsql.flightsql.generated.FlightSql_pb2 import (
    ActionCreatePreparedStatementResult as GeneratedActionCreatePreparedStatementResult,
)
from mpzsql.flightsql.generated.FlightSql_pb2 import (
    ActionEndTransactionRequest as GeneratedActionEndTransactionRequest,
)
from mpzsql.flightsql.generated.FlightSql_pb2 import (
    CommandGetDbSchemas as GeneratedCommandGetDbSchemas,
)
from mpzsql.flightsql.generated.FlightSql_pb2 import (
    CommandGetTables as GeneratedCommandGetTables,
)
from mpzsql.flightsql.generated.FlightSql_pb2 import (
    CommandPreparedStatementQuery as GeneratedCommandPreparedStatementQuery,
)
from mpzsql.flightsql.generated.FlightSql_pb2 import (
    CommandPreparedStatementUpdate as GeneratedCommandPreparedStatementUpdate,
)
from mpzsql.flightsql.generated.FlightSql_pb2 import (
    CommandStatementQuery as GeneratedCommandStatementQuery,
)
from mpzsql.flightsql.generated.FlightSql_pb2 import (
    CommandStatementUpdate as GeneratedCommandStatementUpdate,
)
from mpzsql.flightsql.generated.FlightSql_pb2 import (
    DoPutUpdateResult as GeneratedDoPutUpdateResult,
)
from mpzsql.logfire_config import get_protobuf_logger

logger = logging.getLogger(__name__)

# Initialize logfire logger for protobuf operations
protobuf_logger = get_protobuf_logger()

# Keep legacy file logging for backward compatibility
# Set up protobuf logger
protobuf_log = logging.getLogger("server_protobuf")
protobuf_log.setLevel(logging.DEBUG)

# Create a file handler for the protobuf logger
protobuf_fh = logging.FileHandler("server_protobuf.log", mode="w")
protobuf_fh.setLevel(logging.DEBUG)

# Create a formatter and set it for the handler
protobuf_formatter = logging.Formatter("%(asctime)s - %(message)s")
protobuf_fh.setFormatter(protobuf_formatter)

# Add the handler to the logger
protobuf_log.addHandler(protobuf_fh)
protobuf_log.propagate = False  # Prevent propagation to root logger

# Test both loggers
protobuf_logger.info("Protobuf logfire logger initialized")
protobuf_log.info("Legacy protobuf logger initialized")


def parse_any_command(command_bytes: bytes) -> Optional[any_pb2.Any]:
    """Parse command bytes into a protobuf Any message."""
    try:
        # Guard against None/empty input (e.g., PATH descriptors)
        if not command_bytes:
            protobuf_log.info(
                "parse_any_command called with empty bytes; returning None"
            )
            return None
        protobuf_log.info(
            f"parse_any_command called with {len(command_bytes)} bytes: {command_bytes.hex()}"
        )
        protobuf_logger.info(
            "Parsing protobuf Any command",
            bytes_length=len(command_bytes),
            bytes_hex=command_bytes.hex(),
        )
        any_message = any_pb2.Any()
        any_message.ParseFromString(command_bytes)
        protobuf_log.info(
            f"Successfully parsed Any message with type_url: {any_message.type_url}"
        )
        protobuf_logger.info(
            "Successfully parsed Any message", type_url=any_message.type_url
        )
        return any_message
    except Exception as e:
        protobuf_log.error(f"Could not parse command as protobuf Any: {e}")
        protobuf_logger.error("Failed to parse protobuf Any command", error=str(e))
        logger.debug(f"Could not parse command as protobuf Any: {e}")
        return None


class ActionCreatePreparedStatementRequest:
    """
    ActionCreatePreparedStatementRequest using generated protobuf class.
    Now much simpler and more maintainable!
    """

    def __init__(self):
        self._generated = GeneratedActionCreatePreparedStatementRequest()

    @property
    def query(self):
        return self._generated.query

    @query.setter
    def query(self, value):
        self._generated.query = value

    def ParseFromString(self, data: bytes):
        """
        Parse using generated protobuf class - much simpler and more reliable!
        """
        try:
            logger.info(
                f"ActionCreatePreparedStatementRequest: parsing {len(data)} bytes: {data.hex()}"
            )

            # Try parsing as Any message first (wrapper format)
            any_msg = any_pb2.Any()
            any_msg.ParseFromString(data)

            # Extract the inner message
            self._generated.ParseFromString(any_msg.value)
            logger.info(
                f"Successfully parsed ActionCreatePreparedStatementRequest query: '{self.query}'"
            )

        except Exception:
            # Fallback: try parsing directly (no Any wrapper)
            try:
                self._generated.ParseFromString(data)
                logger.info(
                    f"Successfully parsed ActionCreatePreparedStatementRequest (direct) query: '{self.query}'"
                )
            except Exception as e:
                logger.error(f"Error parsing ActionCreatePreparedStatementRequest: {e}")
                self._generated.query = ""


class ActionClosePreparedStatementRequest:
    """
    Request to close a prepared statement.

    Now using generated protobuf class for proper and reliable parsing!
    """

    def __init__(self):
        self._generated = GeneratedActionClosePreparedStatementRequest()

    @property
    def prepared_statement_handle(self) -> bytes:
        """Get the prepared statement handle."""
        return self._generated.prepared_statement_handle

    @prepared_statement_handle.setter
    def prepared_statement_handle(self, value: bytes):
        """Set the prepared statement handle."""
        self._generated.prepared_statement_handle = value

    def ParseFromString(self, data: bytes):
        """
        Parse using generated protobuf class - much simpler and more reliable!
        """
        try:
            self._generated.ParseFromString(data)
            logger.info(
                f"Successfully parsed ActionClosePreparedStatementRequest using generated class: {self.prepared_statement_handle.hex()}"
            )
        except Exception as e:
            logger.error(
                f"Error parsing ActionClosePreparedStatementRequest using generated class: {e}"
            )
            self._generated.prepared_statement_handle = b""


class ActionBeginTransactionRequest:
    """
    Request to begin a transaction.

    Now using generated protobuf class for proper and reliable parsing!
    """

    def __init__(self):
        self._generated = GeneratedActionBeginTransactionRequest()

    def ParseFromString(self, data: bytes):
        """Parse using generated protobuf class - much simpler and more reliable!"""
        try:
            self._generated.ParseFromString(data)
            logger.debug(
                "Successfully parsed ActionBeginTransactionRequest using generated class"
            )
        except Exception as e:
            logger.error(
                f"Error parsing ActionBeginTransactionRequest using generated class: {e}"
            )


class ActionEndTransactionRequest:
    """
    Request to end a transaction.

    Now using generated protobuf class for proper and reliable parsing!
    """

    def __init__(self, transaction_id: bytes = b"", action: int = 0):
        self._generated = GeneratedActionEndTransactionRequest()
        if transaction_id:
            self._generated.transaction_id = transaction_id
        self._generated.action = action

    @property
    def transaction_id(self) -> bytes:
        """Get the transaction ID."""
        return self._generated.transaction_id

    @transaction_id.setter
    def transaction_id(self, value: bytes):
        """Set the transaction ID."""
        self._generated.transaction_id = value

    @property
    def action(self) -> int:
        """Get the action (0 for COMMIT, 1 for ROLLBACK)."""
        return self._generated.action

    @action.setter
    def action(self, value: int):
        """Set the action (0 for COMMIT, 1 for ROLLBACK)."""
        self._generated.action = value

    def ParseFromString(self, data: bytes):
        """Parse using generated protobuf class - much simpler and more reliable!"""
        try:
            self._generated.ParseFromString(data)
            logger.debug(
                f"Successfully parsed ActionEndTransactionRequest using generated class: transaction_id={self.transaction_id.hex()}, action={self.action}"
            )
        except Exception as e:
            logger.error(
                f"Error parsing ActionEndTransactionRequest using generated class: {e}"
            )


class DoPutUpdateResult:
    """Represents a DoPutUpdateResult.

    Now using generated protobuf class with manual compatibility wrapper.
    """

    def __init__(self, record_count=0):
        self._generated = GeneratedDoPutUpdateResult()
        self._generated.record_count = record_count

    @property
    def record_count(self):
        return self._generated.record_count

    @record_count.setter
    def record_count(self, value):
        self._generated.record_count = value

    def SerializeToString(self) -> bytes:
        """Use generated protobuf class for proper serialization."""
        return self._generated.SerializeToString()


class CommandGetCatalogs:
    """Represents a CommandGetCatalogs."""

    def __init__(self):
        pass


class CommandGetDbSchemas:
    """Represents a CommandGetDbSchemas."""

    def __init__(self):
        self.catalog = None
        self.db_schema_filter_pattern = None

    def ParseFromString(self, data: bytes):
        pass


class CommandGetTables:
    """Represents a CommandGetTables."""

    def __init__(self):
        self.catalog = None
        self.db_schema_filter_pattern = None
        self.table_name_filter_pattern = None
        self.table_types = []
        self.include_schema = False

    def ParseFromString(self, data: bytes):
        pass


class CommandGetTableTypes:
    """Represents a CommandGetTableTypes."""

    def __init__(self):
        pass


class CommandGetColumns:
    """Represents a CommandGetColumns."""

    def __init__(self):
        self.catalog = None
        self.db_schema_filter_pattern = None
        self.table_name_filter_pattern = None
        self.column_name_filter_pattern = None

    def ParseFromString(self, data: bytes):
        pass


class CommandGetSqlInfo:
    """Represents a CommandGetSqlInfo."""

    def __init__(self):
        self.info = []

    def ParseFromString(self, data: bytes):
        pass


class CommandStatementQuery:
    """Represents a CommandStatementQuery.

    Now using generated protobuf class for simpler and more reliable parsing.
    """

    def __init__(self):
        self._generated = GeneratedCommandStatementQuery()

    @property
    def query(self):
        return self._generated.query

    @query.setter
    def query(self, value):
        self._generated.query = value

    def ParseFromString(self, data: bytes):
        """Parse using generated protobuf class - much simpler!"""
        try:
            self._generated.ParseFromString(data)
        except Exception as e:
            logger.error(f"Error parsing CommandStatementQuery: {e}")
            self._generated.query = ""


class CommandStatementUpdate:
    """Represents a CommandStatementUpdate.

    Now using generated protobuf class for simpler and more reliable parsing.
    """

    def __init__(self):
        self._generated = GeneratedCommandStatementUpdate()

    @property
    def query(self):
        return self._generated.query

    @query.setter
    def query(self, value):
        self._generated.query = value

    def ParseFromString(self, data: bytes):
        """Parse using generated protobuf class - much simpler!"""
        try:
            self._generated.ParseFromString(data)
        except Exception as e:
            logger.error(f"Error parsing CommandStatementUpdate: {e}")
            self._generated.query = ""

    def Unpack(self, any_command):
        """Parse from Any protobuf message using generated class."""
        try:
            self._generated.ParseFromString(any_command.value)
            logger.info(
                f"Successfully parsed CommandStatementUpdate query: {self.query}"
            )
        except Exception as e:
            logger.error(f"Error unpacking CommandStatementUpdate: {e}")
            self._generated.query = ""


class CommandPreparedStatementQuery:
    """Represents a CommandPreparedStatementQuery.

    Now using generated protobuf class for simpler and more reliable parsing.
    """

    def __init__(self):
        self._generated = GeneratedCommandPreparedStatementQuery()

    @property
    def prepared_statement_handle(self):
        return self._generated.prepared_statement_handle

    @prepared_statement_handle.setter
    def prepared_statement_handle(self, value):
        self._generated.prepared_statement_handle = value

    def ParseFromString(self, data: bytes):
        """Parse using generated protobuf class - much simpler!"""
        try:
            self._generated.ParseFromString(data)
        except Exception as e:
            logger.error(f"Error parsing CommandPreparedStatementQuery: {e}")
            self._generated.prepared_statement_handle = b""

    def Unpack(self, any_message):
        """Parse from Any protobuf message using generated class."""
        try:
            self._generated.ParseFromString(any_message.value)
        except Exception as e:
            logger.error(f"Error unpacking CommandPreparedStatementQuery: {e}")
            self._generated.prepared_statement_handle = b""


class CommandPreparedStatementUpdate:
    """Represents a CommandPreparedStatementUpdate.

    Now using generated protobuf class for simpler and more reliable parsing.
    """

    def __init__(self):
        self._generated = GeneratedCommandPreparedStatementUpdate()

    @property
    def prepared_statement_handle(self):
        return self._generated.prepared_statement_handle

    @prepared_statement_handle.setter
    def prepared_statement_handle(self, value):
        self._generated.prepared_statement_handle = value

    def ParseFromString(self, data: bytes):
        """Parse using generated protobuf class - much simpler!"""
        try:
            self._generated.ParseFromString(data)
        except Exception as e:
            logger.error(f"Error parsing CommandPreparedStatementUpdate: {e}")
            self._generated.prepared_statement_handle = b""

    def Unpack(self, any_message):
        """Parse from Any protobuf message using generated class."""
        try:
            self._generated.ParseFromString(any_message.value)
        except Exception as e:
            logger.error(f"Error unpacking CommandPreparedStatementUpdate: {e}")
            self._generated.prepared_statement_handle = b""


class PreparedStatementQuery:
    """Represents a PreparedStatementQuery."""

    def __init__(self):
        self.prepared_statement_handle = b""

    def ParseFromString(self, data: bytes):
        if data and data[0] == 0x0A:
            length = data[1]
            if len(data) >= 2 + length:
                self.prepared_statement_handle = data[2 : 2 + length]

    def Unpack(self, any_message):
        """Parse the handle from the PreparedStatementQuery protobuf message."""
        self.ParseFromString(any_message.value)


class FlightSQLProtobuf:
    """Helper class for creating FlightSQL protobuf messages."""

    # FlightSQL protobuf type URLs (based on Arrow FlightSQL spec)
    COMMAND_STATEMENT_QUERY_TYPE_URL = (
        "type.googleapis.com/arrow.flight.protocol.sql.CommandStatementQuery"
    )
    COMMAND_STATEMENT_UPDATE_TYPE_URL = (
        "type.googleapis.com/arrow.flight.protocol.sql.CommandStatementUpdate"
    )
    ACTION_CREATE_PREPARED_STATEMENT_RESULT_TYPE_URL = "type.googleapis.com/arrow.flight.protocol.sql.ActionCreatePreparedStatementResult"
    COMMAND_PREPARED_STATEMENT_QUERY_TYPE_URL = (
        "type.googleapis.com/arrow.flight.protocol.sql.CommandPreparedStatementQuery"
    )
    COMMAND_PREPARED_STATEMENT_UPDATE_TYPE_URL = (
        "type.googleapis.com/arrow.flight.protocol.sql.CommandPreparedStatementUpdate"
    )
    COMMAND_GET_CATALOGS_TYPE_URL = (
        "type.googleapis.com/arrow.flight.protocol.sql.CommandGetCatalogs"
    )
    COMMAND_GET_DB_SCHEMAS_TYPE_URL = (
        "type.googleapis.com/arrow.flight.protocol.sql.CommandGetDbSchemas"
    )
    COMMAND_GET_TABLES_TYPE_URL = (
        "type.googleapis.com/arrow.flight.protocol.sql.CommandGetTables"
    )
    COMMAND_GET_TABLE_TYPES_TYPE_URL = (
        "type.googleapis.com/arrow.flight.protocol.sql.CommandGetTableTypes"
    )
    COMMAND_GET_COLUMNS_TYPE_URL = (
        "type.googleapis.com/arrow.flight.protocol.sql.CommandGetColumns"
    )
    COMMAND_GET_SQL_INFO_TYPE_URL = (
        "type.googleapis.com/arrow.flight.protocol.sql.CommandGetSqlInfo"
    )
    COMMAND_GET_PRIMARY_KEYS_TYPE_URL = (
        "type.googleapis.com/arrow.flight.protocol.sql.CommandGetPrimaryKeys"
    )
    COMMAND_GET_IMPORTED_KEYS_TYPE_URL = (
        "type.googleapis.com/arrow.flight.protocol.sql.CommandGetImportedKeys"
    )
    COMMAND_GET_EXPORTED_KEYS_TYPE_URL = (
        "type.googleapis.com/arrow.flight.protocol.sql.CommandGetExportedKeys"
    )
    COMMAND_GET_CROSS_REFERENCE_TYPE_URL = (
        "type.googleapis.com/arrow.flight.protocol.sql.CommandGetCrossReference"
    )
    ACTION_BEGIN_TRANSACTION_REQUEST_TYPE_URL = (
        "type.googleapis.com/arrow.flight.protocol.sql.ActionBeginTransactionRequest"
    )
    ACTION_END_TRANSACTION_REQUEST_TYPE_URL = (
        "type.googleapis.com/arrow.flight.protocol.sql.ActionEndTransactionRequest"
    )
    ACTION_BEGIN_TRANSACTION_RESULT_TYPE_URL = (
        "type.googleapis.com/arrow.flight.protocol.sql.ActionBeginTransactionResult"
    )

    @staticmethod
    def create_action_create_prepared_statement_result(
        prepared_statement_handle: bytes,
        dataset_schema: bytes = None,
        parameter_schema: bytes = None,
    ) -> bytes:
        """
        Create ActionCreatePreparedStatementResult protobuf message.

        Now using generated protobuf class for proper and reliable serialization!
        """
        try:
            # Use generated protobuf class - much simpler and more reliable!
            result = GeneratedActionCreatePreparedStatementResult()
            result.prepared_statement_handle = prepared_statement_handle

            if dataset_schema:
                result.dataset_schema = dataset_schema
            if parameter_schema:
                result.parameter_schema = parameter_schema

            # Wrap in protobuf Any message
            any_message = any_pb2.Any()
            any_message.type_url = (
                FlightSQLProtobuf.ACTION_CREATE_PREPARED_STATEMENT_RESULT_TYPE_URL
            )
            any_message.value = result.SerializeToString()

            serialized = any_message.SerializeToString()
            logger.debug(
                f"Created ActionCreatePreparedStatementResult using generated class: {serialized.hex()}"
            )
            return serialized

        except Exception as e:
            logger.error(f"Error creating ActionCreatePreparedStatementResult: {e}")
            # Fallback: create a minimal binary message
            return prepared_statement_handle

    @staticmethod
    def parse_command_prepared_statement_query(command_bytes: bytes) -> Optional[str]:
        """
        Parse CommandPreparedStatementQuery protobuf message to extract prepared statement handle.

        Now using our improved CommandPreparedStatementQuery class!
        """
        try:
            # Use our already-improved class with generated protobuf
            command = CommandPreparedStatementQuery()

            # Try parsing as protobuf Any message first
            try:
                any_message = any_pb2.Any()
                any_message.ParseFromString(command_bytes)

                if (
                    any_message.type_url
                    == FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_QUERY_TYPE_URL
                ):
                    command.Unpack(any_message)
                    if command.prepared_statement_handle:
                        # Convert bytes to string if needed
                        if isinstance(command.prepared_statement_handle, bytes):
                            handle = command.prepared_statement_handle.decode("utf-8")
                        else:
                            handle = str(command.prepared_statement_handle)
                        logger.debug(f"Extracted prepared statement handle: {handle}")
                        return handle
            except Exception as e:
                logger.debug(f"Not a protobuf Any message: {e}")
                pass

            # Fallback: try direct parsing
            command.ParseFromString(command_bytes)
            if command.prepared_statement_handle:
                if isinstance(command.prepared_statement_handle, bytes):
                    handle = command.prepared_statement_handle.decode("utf-8")
                else:
                    handle = str(command.prepared_statement_handle)
                return handle

            # Additional fallback: try direct decode but validate it's actually a prepared statement handle
            try:
                handle = command_bytes.decode("utf-8")
                if handle and len(handle.strip()) > 0:
                    # Only return if it looks like a prepared statement handle
                    # Don't return type URLs or other protobuf content
                    if handle.startswith("stmt_") or (
                        handle.isalnum() and len(handle) > 5
                    ):
                        return handle.strip()
            except UnicodeDecodeError:
                pass

            # Final fallback: scan for prepared statement handle pattern
            try:
                decoded = command_bytes.decode("utf-8", errors="ignore")
                if "stmt_" in decoded:
                    # Extract handle starting from stmt_
                    start_idx = decoded.find("stmt_")
                    if start_idx >= 0:
                        # Handle is typically stmt_<hex> format
                        handle = ""
                        for i in range(start_idx, len(decoded)):
                            char = decoded[i]
                            if char.isalnum() or char == "_":
                                handle += char
                            else:
                                break
                        if len(handle) > 5:  # More than just "stmt_"
                            return handle
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Error parsing CommandPreparedStatementQuery: {e}")

        logger.debug(f"Could not extract handle from {len(command_bytes)} bytes")
        return None

    @staticmethod
    def parse_command_statement_query(command_bytes: bytes) -> Optional[str]:
        """
        Parse CommandStatementQuery protobuf message to extract SQL.

        Now using generated protobuf class for proper and reliable parsing!
        """
        try:
            protobuf_log.info(
                f"parse_command_statement_query called with {len(command_bytes)} bytes: {command_bytes.hex()}"
            )

            # Try parsing as protobuf Any message first
            try:
                any_message = any_pb2.Any()
                any_message.ParseFromString(command_bytes)
                protobuf_log.info(
                    f"Parsed as Any message with type_url: {any_message.type_url}"
                )

                if (
                    any_message.type_url
                    == FlightSQLProtobuf.COMMAND_STATEMENT_QUERY_TYPE_URL
                ):
                    # Use generated protobuf class - much simpler and more reliable!
                    command = GeneratedCommandStatementQuery()
                    command.ParseFromString(any_message.value)

                    if command.query:
                        sql = command.query
                        protobuf_log.info(
                            f"Successfully extracted SQL using generated class: {sql}"
                        )
                        return sql

            except Exception as e:
                protobuf_log.debug(f"Not a protobuf Any message: {e}")
                logger.debug(f"Not a protobuf Any message: {e}")

            # Fallback: try direct parsing with generated class
            try:
                command = GeneratedCommandStatementQuery()
                command.ParseFromString(command_bytes)

                if command.query:
                    sql = command.query
                    protobuf_log.info(
                        f"Successfully extracted SQL using generated class (direct): {sql}"
                    )
                    return sql
            except Exception as e:
                protobuf_log.debug(f"Direct parsing with generated class failed: {e}")

            # Final fallback: try direct decode if it looks like SQL
            try:
                sql = command_bytes.decode("utf-8")
                if sql and len(sql.strip()) > 0:
                    # Only return if it looks like valid text (not a binary prefix)
                    sql_stripped = sql.strip()
                    if (
                        len(sql_stripped) > 2
                        and sql_stripped.isprintable()
                        and not sql_stripped.startswith("\x00")
                        and not sql_stripped.startswith("\x01")
                        and (" " in sql_stripped or len(sql_stripped) > 3)
                    ):
                        protobuf_log.info(
                            f"Successfully decoded SQL (fallback decode): {sql_stripped}"
                        )
                        return sql_stripped
            except UnicodeDecodeError:
                pass

            protobuf_log.warning(
                f"Could not extract SQL from {len(command_bytes)} bytes"
            )
            logger.warning(f"Could not extract SQL from {len(command_bytes)} bytes")
            return None

        except Exception as e:
            protobuf_log.error(f"Error parsing CommandStatementQuery: {e}")
            logger.error(f"Error parsing CommandStatementQuery: {e}")
            return None

    @staticmethod
    def parse_command_get_db_schemas(
        command_bytes: bytes,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Parse CommandGetDbSchemas protobuf message to extract catalog and schema filter.

        Now using generated protobuf class for proper and reliable parsing!

        Returns:
            Tuple of (catalog, db_schema_filter_pattern)
        """
        try:
            protobuf_log.info(
                f"parse_command_get_db_schemas called with {len(command_bytes)} bytes: {command_bytes.hex()}"
            )

            # Use generated protobuf class - much simpler and more reliable!
            command = GeneratedCommandGetDbSchemas()
            command.ParseFromString(command_bytes)

            catalog = command.catalog if command.catalog else None
            db_schema_filter_pattern = (
                command.db_schema_filter_pattern
                if command.db_schema_filter_pattern
                else None
            )

            protobuf_log.info(
                f"Parsed GetDbSchemas using generated class: catalog={catalog}, db_schema_filter_pattern={db_schema_filter_pattern}"
            )
            return catalog, db_schema_filter_pattern

        except Exception as e:
            protobuf_log.error(f"Error parsing CommandGetDbSchemas: {e}")
            return None, None

    @staticmethod
    def parse_command_get_tables(
        command_bytes: bytes,
    ) -> Tuple[Optional[str], Optional[str], Optional[str], list, bool]:
        """
        Parse CommandGetTables protobuf message to extract parameters.

        Now using generated protobuf class for proper and reliable parsing!

        Returns:
            Tuple of (catalog, db_schema_filter_pattern, table_name_filter_pattern, table_types, include_schema)
        """
        try:
            protobuf_log.info(
                f"parse_command_get_tables called with {len(command_bytes)} bytes: {command_bytes.hex()}"
            )

            # Try parsing as protobuf Any message first
            try:
                any_message = any_pb2.Any()
                any_message.ParseFromString(command_bytes)

                if (
                    any_message.type_url
                    == FlightSQLProtobuf.COMMAND_GET_TABLES_TYPE_URL
                ):
                    # Use generated protobuf class - much simpler and more reliable!
                    command = GeneratedCommandGetTables()
                    command.ParseFromString(any_message.value)

                    catalog = command.catalog if command.catalog else None
                    db_schema_filter_pattern = (
                        command.db_schema_filter_pattern
                        if command.db_schema_filter_pattern
                        else None
                    )
                    table_name_filter_pattern = (
                        command.table_name_filter_pattern
                        if command.table_name_filter_pattern
                        else None
                    )
                    table_types = (
                        list(command.table_types) if command.table_types else []
                    )
                    include_schema = (
                        command.include_schema
                        if hasattr(command, "include_schema")
                        else False
                    )

                    protobuf_log.info(
                        f"Parsed GetTables using generated class: catalog={catalog}, db_schema_filter_pattern={db_schema_filter_pattern}, table_name_filter_pattern={table_name_filter_pattern}, table_types={table_types}, include_schema={include_schema}"
                    )
                    return (
                        catalog,
                        db_schema_filter_pattern,
                        table_name_filter_pattern,
                        table_types,
                        include_schema,
                    )

            except Exception as e:
                protobuf_log.debug(f"Not a protobuf Any message: {e}")

            # Try parsing directly as command bytes (without Any wrapper)
            try:
                command = GeneratedCommandGetTables()
                command.ParseFromString(command_bytes)

                catalog = command.catalog if command.catalog else None
                db_schema_filter_pattern = (
                    command.db_schema_filter_pattern
                    if command.db_schema_filter_pattern
                    else None
                )
                table_name_filter_pattern = (
                    command.table_name_filter_pattern
                    if command.table_name_filter_pattern
                    else None
                )
                table_types = list(command.table_types) if command.table_types else []
                include_schema = (
                    command.include_schema
                    if hasattr(command, "include_schema")
                    else False
                )

                protobuf_log.info(
                    f"Parsed GetTables using generated class (direct): catalog={catalog}, db_schema_filter_pattern={db_schema_filter_pattern}, table_name_filter_pattern={table_name_filter_pattern}, table_types={table_types}, include_schema={include_schema}"
                )
                return (
                    catalog,
                    db_schema_filter_pattern,
                    table_name_filter_pattern,
                    table_types,
                    include_schema,
                )

            except Exception as e:
                protobuf_log.debug(f"Direct parsing with generated class failed: {e}")

            protobuf_log.warning(
                f"Could not parse GetTables from {len(command_bytes)} bytes"
            )
            return None, None, None, [], False

        except Exception as e:
            protobuf_log.error(f"Error parsing CommandGetTables: {e}")
            return None, None, None, [], False

    @staticmethod
    def create_prepared_statement_handle() -> str:
        """Generate a unique prepared statement handle."""
        return f"stmt_{uuid.uuid4().hex[:16]}"

    @staticmethod
    def encode_prepared_statement_handle(handle: str) -> bytes:
        """Encode prepared statement handle for protobuf message."""
        # Simple encoding: length prefix + UTF-8 string
        handle_bytes = handle.encode("utf-8")
        length = len(handle_bytes)
        return struct.pack("<I", length) + handle_bytes

    @staticmethod
    def parse_create_prepared_statement_request(action_body: bytes) -> Optional[str]:
        """
        Parse CreatePreparedStatement request to extract SQL.

        Now using generated protobuf class for proper and reliable parsing!
        """
        try:
            # Parse as protobuf Any message
            any_message = any_pb2.Any()
            any_message.ParseFromString(action_body)

            # Use our already-improved ActionCreatePreparedStatementRequest class
            request = ActionCreatePreparedStatementRequest()
            request.ParseFromString(action_body)

            if request.query:
                logger.info(
                    f"Extracted query from ActionCreatePreparedStatementRequest using generated class: {request.query}"
                )
                return request.query

            logger.warning("Query not found in ActionCreatePreparedStatementRequest")
            return None

        except Exception as e:
            logger.error(f"Error parsing CreatePreparedStatement request: {e}")
            return None

    @staticmethod
    def parse_close_prepared_statement_request(action_body: bytes) -> Optional[bytes]:
        """
        Parse ClosePreparedStatement request to extract prepared statement handle.

        Now using our improved ActionClosePreparedStatementRequest class!
        """
        try:
            # Use our already-defined class with manual parsing
            request = ActionClosePreparedStatementRequest()
            request.ParseFromString(action_body)

            if request.prepared_statement_handle:
                logger.info(
                    f"Extracted prepared statement handle from ActionClosePreparedStatementRequest: {request.prepared_statement_handle.hex()}"
                )
                return request.prepared_statement_handle

            logger.warning(
                "Prepared statement handle not found in ActionClosePreparedStatementRequest"
            )
            return None

        except Exception as e:
            logger.error(f"Error parsing ClosePreparedStatement request: {e}")
            return None

    @staticmethod
    def parse_command_update(command_bytes: bytes) -> Optional[bytes]:
        """
        Parse CommandPreparedStatementUpdate protobuf message to extract prepared statement handle.

        Now using generated protobuf class for proper and reliable parsing!
        """
        try:
            # Try parsing as protobuf Any message first
            try:
                any_message = any_pb2.Any()
                any_message.ParseFromString(command_bytes)

                if (
                    any_message.type_url
                    == FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_UPDATE_TYPE_URL
                ):
                    # Use generated protobuf class - much simpler and more reliable!
                    command = GeneratedCommandPreparedStatementUpdate()
                    command.ParseFromString(any_message.value)

                    if command.prepared_statement_handle:
                        handle = command.prepared_statement_handle
                        logger.debug(
                            f"Extracted prepared statement handle using generated class: {handle.hex()}"
                        )
                        return handle

            except Exception as e:
                logger.debug(f"Not a PreparedStatementUpdate protobuf message: {e}")

            # Fallback: try direct parsing with generated class
            try:
                command = GeneratedCommandPreparedStatementUpdate()
                command.ParseFromString(command_bytes)

                if command.prepared_statement_handle:
                    handle = command.prepared_statement_handle
                    logger.debug(
                        f"Extracted prepared statement handle using generated class (direct): {handle.hex()}"
                    )
                    return handle
            except Exception as e:
                logger.debug(f"Direct parsing with generated class failed: {e}")

            # Final fallback: try direct decode but validate it's actually a prepared statement handle
            try:
                handle = command_bytes.decode("utf-8")
                if handle and len(handle.strip()) > 0:
                    # Only return if it looks like a prepared statement handle
                    # Don't return type URLs or other protobuf content
                    if handle.startswith("stmt_") or (
                        handle.isalnum() and len(handle) > 5
                    ):
                        return handle.strip().encode("utf-8")
            except UnicodeDecodeError:
                pass

            # Final fallback: scan for prepared statement handle pattern
            try:
                decoded = command_bytes.decode("utf-8", errors="ignore")
                if "stmt_" in decoded:
                    # Extract handle starting from stmt_
                    start_idx = decoded.find("stmt_")
                    if start_idx >= 0:
                        # Handle is typically stmt_<hex> format
                        handle = ""
                        for i in range(start_idx, len(decoded)):
                            char = decoded[i]
                            if char.isalnum() or char == "_":
                                handle += char
                            else:
                                break
                        if len(handle) > 5:  # More than just "stmt_"
                            return handle.encode("utf-8")
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Error parsing CommandPreparedStatementUpdate: {e}")

        logger.debug(f"Could not extract handle from {len(command_bytes)} bytes")
        return None

    @staticmethod
    def parse_command_statement_update(command_bytes: bytes) -> Optional[str]:
        """
        Parse CommandStatementUpdate protobuf message to extract SQL.

        Now using generated protobuf class for proper and reliable parsing!
        """
        try:
            # Try parsing as protobuf Any message first
            try:
                any_message = any_pb2.Any()
                any_message.ParseFromString(command_bytes)

                if (
                    any_message.type_url
                    == FlightSQLProtobuf.COMMAND_STATEMENT_UPDATE_TYPE_URL
                ):
                    # Use generated protobuf class - much simpler and more reliable!
                    command = GeneratedCommandStatementUpdate()
                    command.ParseFromString(any_message.value)

                    if command.query:
                        sql = command.query
                        logger.debug(
                            f"Successfully extracted SQL using generated class: {sql}"
                        )
                        return sql

            except Exception as e:
                logger.debug(f"Not a protobuf Any message: {e}")

            # Fallback: try direct parsing with generated class
            try:
                command = GeneratedCommandStatementUpdate()
                command.ParseFromString(command_bytes)

                if command.query:
                    sql = command.query
                    logger.debug(
                        f"Successfully extracted SQL using generated class (direct): {sql}"
                    )
                    return sql
            except Exception as e:
                logger.debug(f"Direct parsing with generated class failed: {e}")

            # Final fallback: try direct decode if it looks like SQL
            try:
                sql = command_bytes.decode("utf-8")
                if sql and len(sql.strip()) > 0:
                    # Only return if it looks like valid text (not a binary prefix)
                    sql_stripped = sql.strip()
                    if (
                        len(sql_stripped) > 2
                        and sql_stripped.isprintable()
                        and not sql_stripped.startswith("\x00")
                        and not sql_stripped.startswith("\x01")
                        and (" " in sql_stripped or len(sql_stripped) > 3)
                    ):
                        return sql_stripped
            except UnicodeDecodeError:
                pass

            logger.warning(f"Could not extract SQL from {len(command_bytes)} bytes")
            return None

        except Exception as e:
            logger.error(f"Error parsing CommandStatementUpdate: {e}")
            return None

    @staticmethod
    def get_tables_schema():
        """Get the standard Flight SQL schema for GetTables command.

        This is the 5-column schema including REMARKS as per JDBC spec.
        Only used when include_schema=False in the command.
        Uses standard Arrow Flight SQL column names.
        """
        return pa.schema(
            [
                ("catalog_name", pa.string()),
                ("db_schema_name", pa.string()),
                ("table_name", pa.string()),
                ("table_type", pa.string()),
                ("table_remarks", pa.string()),
            ]
        )

    @staticmethod
    def get_tables_schema_minimal():
        """Get the minimal Flight SQL schema for GetTables command without table_schema.

        This is the minimal schema according to the Flight SQL specification,
        but most JDBC drivers expect the table_schema column.
        """
        return pa.schema(
            [
                ("catalog_name", pa.string()),
                ("db_schema_name", pa.string()),
                ("table_name", pa.string()),
                ("table_type", pa.string()),
            ]
        )

    @staticmethod
    def get_catalogs_schema():
        """Get the standard Flight SQL schema for GetCatalogs command."""
        # Match Examples server: lowercase field name, regular string type
        return pa.schema([("catalog_name", pa.string())])

    @staticmethod
    def get_db_schemas_schema():
        """Get the standard Flight SQL schema for GetDbSchemas command."""
        # Match Examples server: lowercase field names
        return pa.schema(
            [
                ("catalog_name", pa.string()),
                ("db_schema_name", pa.string()),
            ]
        )

    @staticmethod
    def get_table_types_schema():
        """Get the standard Flight SQL schema for GetTableTypes command."""
        return pa.schema([("table_type", pa.string())])

    @staticmethod
    def get_tables_schema_with_included_schema():
        """Get the extended Flight SQL schema for GetTables command with table schema included.
        Uses standard Arrow Flight SQL column names.
        """
        return pa.schema(
            [
                ("catalog_name", pa.string()),
                ("db_schema_name", pa.string()),
                ("table_name", pa.string()),
                ("table_type", pa.string()),
                (
                    "table_remarks",
                    pa.string(),
                ),  # Standard Flight SQL column for comments/remarks
                (
                    "table_schema",
                    pa.binary(),
                ),  # This contains the Arrow schema as bytes
            ]
        )

    @staticmethod
    def get_sql_info_schema():
        """Get the standard Flight SQL schema for GetSqlInfo command.

        The schema for SQL info responses should contain:
        - info_name: uint32 NOT NULL (the SQL info code)
        - value: string (simplified - we'll use string values for all info)

        Based on the Arrow Flight SQL specification, the proper schema would use
        a dense_union for the value field, but we're simplifying to strings for now.
        """
        return pa.schema(
            [
                ("info_name", pa.uint32()),
                ("value", pa.string()),
            ]
        )

    @staticmethod
    def get_sql_info_schema_with_dense_union():
        """Get the proper Flight SQL schema for GetSqlInfo command with dense_union.

        This is the proper implementation according to the Arrow Flight SQL specification,
        but it's more complex to implement. The value field should be a dense_union
        that can contain different types (string, int64, bool, etc.).

        For now, we're using the simplified string-based schema above.
        """
        # This would be the proper implementation with dense_union
        # but it's complex to implement properly
        union_fields = [
            pa.field("string_value", pa.string()),
            pa.field("bool_value", pa.bool_()),
            pa.field("int64_value", pa.int64()),
            pa.field("int32_value", pa.int32()),
            pa.field("string_list_value", pa.list_(pa.string())),
            pa.field(
                "int32_to_int32_list_map_value",
                pa.map_(pa.int32(), pa.list_(pa.int32())),
            ),
        ]

        # Create dense union type
        union_type = pa.union(union_fields, mode="dense")

        return pa.schema(
            [
                ("info_name", pa.uint32()),
                ("value", union_type),
            ]
        )

    @staticmethod
    def get_primary_keys_schema():
        """Get the standard Flight SQL schema for GetPrimaryKeys command."""
        # Match Examples server: lowercase field names
        return pa.schema(
            [
                ("catalog_name", pa.string()),
                ("schema_name", pa.string()),
                ("table_name", pa.string()),
                ("column_name", pa.string()),
                ("key_sequence", pa.int32()),
                ("key_name", pa.string()),
            ]
        )

    @staticmethod
    def get_imported_keys_schema():
        """Get the standard Flight SQL schema for GetImportedKeys command."""
        return pa.schema(
            [
                ("pk_catalog_name", pa.string()),
                ("pk_schema_name", pa.string()),
                ("pk_table_name", pa.string()),
                ("pk_column_name", pa.string()),
                ("fk_catalog_name", pa.string()),
                ("fk_schema_name", pa.string()),
                ("fk_table_name", pa.string()),
                ("fk_column_name", pa.string()),
                ("key_sequence", pa.int32()),
                ("fk_key_name", pa.string()),
                ("pk_key_name", pa.string()),
                ("update_rule", pa.int8()),
                ("delete_rule", pa.int8()),
            ]
        )

    @staticmethod
    def get_exported_keys_schema():
        """Get the standard Flight SQL schema for GetExportedKeys command."""
        # Same as imported keys
        return FlightSQLProtobuf.get_imported_keys_schema()

    @staticmethod
    def get_cross_reference_schema():
        """Get the standard Flight SQL schema for GetCrossReference command."""
        # Same as imported/exported keys
        return FlightSQLProtobuf.get_imported_keys_schema()

    @staticmethod
    def get_columns_schema():
        """Get the standard Flight SQL schema for GetColumns command."""
        return pa.schema(
            [
                ("catalog_name", pa.string()),
                ("db_schema_name", pa.string()),
                ("table_name", pa.string()),
                ("column_name", pa.string()),
                ("data_type", pa.int32()),
                ("type_name", pa.string()),
                ("column_size", pa.int32()),
                ("buffer_length", pa.int32()),
                ("decimal_digits", pa.int32()),
                ("num_prec_radix", pa.int32()),
                ("nullable", pa.int32()),
                ("remarks", pa.string()),
                ("column_def", pa.string()),
                ("sql_data_type", pa.int32()),
                ("sql_datetime_sub", pa.int32()),
                ("char_octet_length", pa.int32()),
                ("ordinal_position", pa.int32()),
                ("is_nullable", pa.string()),
                ("is_autoincrement", pa.string()),
                ("is_generatedcolumn", pa.string()),
            ]
        )

    @staticmethod
    def create_action_begin_transaction_result(transaction_id: str) -> bytes:
        """
        Create ActionBeginTransactionResult protobuf message.

        Now using generated protobuf class for proper and reliable serialization!
        """
        try:
            # Use generated protobuf class - much simpler and more reliable!
            result = GeneratedActionBeginTransactionResult()
            result.transaction_id = transaction_id.encode("utf-8")

            # Wrap in Any message
            any_message = any_pb2.Any()
            any_message.type_url = (
                FlightSQLProtobuf.ACTION_BEGIN_TRANSACTION_RESULT_TYPE_URL
            )
            any_message.value = result.SerializeToString()

            serialized = any_message.SerializeToString()
            logger.debug(
                f"Created ActionBeginTransactionResult using generated class: {serialized.hex()}"
            )
            return serialized
        except Exception as e:
            logger.error(f"Error creating ActionBeginTransactionResult: {e}")
            return transaction_id.encode("utf-8")

    @staticmethod
    def get_type_mapping():
        """Get mapping from database types to Arrow types, matching Examples implementation."""
        return {
            # Numeric types
            "INTEGER": pa.int32(),
            "BIGINT": pa.int64(),
            "SMALLINT": pa.int16(),
            "TINYINT": pa.int8(),
            "HUGEINT": pa.decimal128(38, 0),
            "DECIMAL": pa.decimal128(38, 10),  # Default precision/scale
            "FLOAT": pa.float32(),
            "REAL": pa.float32(),
            "DOUBLE": pa.float64(),
            # String types
            "VARCHAR": pa.string(),
            "CHAR": pa.string(),
            "TEXT": pa.string(),
            "STRING": pa.string(),
            "BLOB": pa.binary(),
            # Boolean
            "BOOLEAN": pa.bool_(),
            "BOOL": pa.bool_(),
            # Date/Time types
            "DATE": pa.date32(),
            "TIME": pa.time64("us"),
            "TIMESTAMP": pa.timestamp("us"),
            "TIMESTAMP_MS": pa.timestamp("ms"),
            "TIMESTAMP_NS": pa.timestamp("ns"),
            "TIMESTAMP_S": pa.timestamp("s"),
            "INTERVAL": pa.duration("us"),
            # Unsigned types
            "UINTEGER": pa.uint32(),
            "UBIGINT": pa.uint64(),
            "USMALLINT": pa.uint16(),
            "UTINYINT": pa.uint8(),
            # Special types
            "UUID": pa.string(),  # UUID as string
            "JSON": pa.string(),  # JSON as string
            # Default
            "UNKNOWN": pa.null(),
        }


# Transaction Action Request/Result classes
class ActionBeginTransactionResult:
    """Result of beginning a transaction."""

    def __init__(self, transaction_id: bytes):
        self.transaction_id = transaction_id


class EndTransaction:
    """Enum for transaction end actions."""

    UNSPECIFIED = 0
    COMMIT = 1
    ROLLBACK = 2


class ActionBeginSavepointRequest:
    """Request to begin a savepoint."""

    def __init__(self, transaction_id: bytes, name: str):
        self.transaction_id = transaction_id
        self.name = name


class ActionBeginSavepointResult:
    """Result of beginning a savepoint."""

    def __init__(self, savepoint_id: bytes):
        self.savepoint_id = savepoint_id


class ActionEndSavepointRequest:
    """Request to end a savepoint."""

    def __init__(self, savepoint_id: bytes, action: int):
        self.savepoint_id = savepoint_id
        self.action = action


class EndSavepoint:
    """Enum for savepoint end actions."""

    UNSPECIFIED = 0
    RELEASE = 1
    ROLLBACK = 2

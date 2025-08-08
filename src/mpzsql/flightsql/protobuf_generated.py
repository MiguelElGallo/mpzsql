"""FlightSQL protobuf message definitions and handling.

This module implements the protobuf message formats expected by FlightSQL clients,
based on the Apache Arrow FlightSQL specification.
"""

import logging
import uuid

import pyarrow as pa
from google.protobuf import any_pb2

from mpzsql.logfire_config import get_protobuf_logger

# Import generated protobuf classes - these are required
try:
    from .generated import FlightSql_pb2 as flight_sql_pb2
    from .generated.Flight_pb2 import *  # noqa: F403, F401

    # Export all generated protobuf classes
    from .generated.FlightSql_pb2 import *  # noqa: F403, F401

    PROTOBUF_AVAILABLE = True
except ImportError as e:
    raise ImportError(
        "Generated protobuf files not found. Please run: python scripts/generate_protobuf.py"
    ) from e

logger = logging.getLogger(__name__)

# Initialize logfire logger for protobuf operations
protobuf_logger = get_protobuf_logger()

# Set up legacy file logging for backward compatibility
protobuf_log = logging.getLogger("server_protobuf")
protobuf_log.setLevel(logging.DEBUG)
protobuf_fh = logging.FileHandler("server_protobuf.log", mode="w")
protobuf_fh.setLevel(logging.DEBUG)
protobuf_formatter = logging.Formatter("%(asctime)s - %(message)s")
protobuf_fh.setFormatter(protobuf_formatter)
protobuf_log.addHandler(protobuf_fh)
protobuf_log.propagate = False

protobuf_logger.info("Protobuf module initialized with generated classes")
protobuf_log.info("Protobuf module initialized with generated classes")


# Export generated protobuf classes directly with added constants
ActionCreatePreparedStatementRequest = (
    flight_sql_pb2.ActionCreatePreparedStatementRequest
)
ActionClosePreparedStatementRequest = flight_sql_pb2.ActionClosePreparedStatementRequest
ActionBeginTransactionRequest = flight_sql_pb2.ActionBeginTransactionRequest

# ActionEndTransactionRequest with constants
ActionEndTransactionRequest = flight_sql_pb2.ActionEndTransactionRequest
# Add the missing constants for compatibility
ActionEndTransactionRequest.COMMIT = 0
ActionEndTransactionRequest.ROLLBACK = 1

DoPutUpdateResult = flight_sql_pb2.DoPutUpdateResult
CommandGetCatalogs = flight_sql_pb2.CommandGetCatalogs
CommandGetDbSchemas = flight_sql_pb2.CommandGetDbSchemas
CommandGetTables = flight_sql_pb2.CommandGetTables
CommandGetTableTypes = flight_sql_pb2.CommandGetTableTypes
CommandGetSqlInfo = flight_sql_pb2.CommandGetSqlInfo
CommandStatementQuery = flight_sql_pb2.CommandStatementQuery
CommandStatementUpdate = flight_sql_pb2.CommandStatementUpdate
CommandPreparedStatementQuery = flight_sql_pb2.CommandPreparedStatementQuery
CommandPreparedStatementUpdate = flight_sql_pb2.CommandPreparedStatementUpdate

# Add CommandGetColumns if not available in generated protobuf
try:
    CommandGetColumns = flight_sql_pb2.CommandGetColumns
except AttributeError:
    # Create a minimal stub if not available in generated files
    class CommandGetColumns:
        def __init__(self):
            self.catalog = None
            self.db_schema_filter_pattern = None
            self.table_name_filter_pattern = None
            self.column_name_filter_pattern = None

        def ParseFromString(self, data: bytes):
            pass


class FlightSQLProtobuf:
    """Helper class for FlightSQL protobuf type URLs and utilities."""

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

    # Additional type URLs that tests expect
    ACTION_BEGIN_TRANSACTION_REQUEST_TYPE_URL = (
        "type.googleapis.com/arrow.flight.protocol.sql.ActionBeginTransactionRequest"
    )
    ACTION_END_TRANSACTION_REQUEST_TYPE_URL = (
        "type.googleapis.com/arrow.flight.protocol.sql.ActionEndTransactionRequest"
    )
    ACTION_CREATE_PREPARED_STATEMENT_REQUEST_TYPE_URL = "type.googleapis.com/arrow.flight.protocol.sql.ActionCreatePreparedStatementRequest"
    ACTION_CLOSE_PREPARED_STATEMENT_REQUEST_TYPE_URL = "type.googleapis.com/arrow.flight.protocol.sql.ActionClosePreparedStatementRequest"
    ACTION_BEGIN_TRANSACTION_RESULT_TYPE_URL = (
        "type.googleapis.com/arrow.flight.protocol.sql.ActionBeginTransactionResult"
    )

    @staticmethod
    def create_action_create_prepared_statement_result(
        prepared_statement_handle: bytes,
        dataset_schema: bytes = None,
        parameter_schema: bytes = None,
    ) -> bytes:
        """Create ActionCreatePreparedStatementResult using generated protobuf."""
        result = flight_sql_pb2.ActionCreatePreparedStatementResult()
        result.prepared_statement_handle = (
            prepared_statement_handle.encode()
            if isinstance(prepared_statement_handle, str)
            else prepared_statement_handle
        )
        if dataset_schema:
            if hasattr(dataset_schema, "serialize"):
                # It's a PyArrow schema, serialize it to bytes
                result.dataset_schema = dataset_schema.serialize().to_pybytes()
            else:
                # It's already bytes
                result.dataset_schema = dataset_schema
        if parameter_schema:
            if hasattr(parameter_schema, "serialize"):
                # It's a PyArrow schema, serialize it to bytes
                result.parameter_schema = parameter_schema.serialize().to_pybytes()
            else:
                # It's already bytes
                result.parameter_schema = parameter_schema

        # Wrap in Any message
        any_message = any_pb2.Any()
        any_message.Pack(result)

        protobuf_logger.info(
            "Created ActionCreatePreparedStatementResult using generated protobuf"
        )
        return any_message.SerializeToString()

    # Schema generation methods using PyArrow (matching the old implementation)
    @staticmethod
    def get_catalogs_schema():
        """Get the standard Flight SQL schema for GetCatalogs command."""
        return pa.schema([("catalog_name", pa.string())])

    @staticmethod
    def get_db_schemas_schema():
        """Get the standard Flight SQL schema for GetDbSchemas command."""
        return pa.schema(
            [
                ("catalog_name", pa.string()),
                ("db_schema_name", pa.string()),
            ]
        )

    @staticmethod
    def get_tables_schema():
        """Get the standard Flight SQL schema for GetTables command."""
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
        """Get the minimal Flight SQL schema for GetTables command without table_schema."""
        return pa.schema(
            [
                ("catalog_name", pa.string()),
                ("db_schema_name", pa.string()),
                ("table_name", pa.string()),
                ("table_type", pa.string()),
            ]
        )

    @staticmethod
    def get_tables_schema_with_included_schema():
        """Get the extended Flight SQL schema for GetTables command with table schema included."""
        return pa.schema(
            [
                ("catalog_name", pa.string()),
                ("db_schema_name", pa.string()),
                ("table_name", pa.string()),
                ("table_type", pa.string()),
                ("table_remarks", pa.string()),
                ("table_schema", pa.binary()),
            ]
        )

    @staticmethod
    def get_table_types_schema():
        """Get the standard Flight SQL schema for GetTableTypes command."""
        return pa.schema([("table_type", pa.string())])

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
                ("scope_catalog", pa.string()),
                ("scope_schema", pa.string()),
                ("scope_table", pa.string()),
                ("source_data_type", pa.int32()),
                ("is_autoincrement", pa.string()),
                ("is_generatedcolumn", pa.string()),
            ]
        )

    @staticmethod
    def get_sql_info_schema():
        """Get the standard Flight SQL schema for GetSqlInfo command."""
        return pa.schema(
            [
                ("info_name", pa.uint32()),
                ("value", pa.string()),
            ]
        )

    @staticmethod
    def get_sql_info_schema_with_dense_union():
        """Get the proper Flight SQL schema for GetSqlInfo command with dense_union."""
        # Create a dense union for the value field to support different types
        union_type = pa.union(
            [
                pa.field("string_value", pa.string()),
                pa.field("int_value", pa.int64()),
                pa.field("bool_value", pa.bool_()),
            ],
            mode="dense",
        )

        return pa.schema(
            [
                ("info_name", pa.uint32()),
                ("value", union_type),
            ]
        )

    @staticmethod
    def get_primary_keys_schema():
        """Get the standard Flight SQL schema for GetPrimaryKeys command."""
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
                ("update_rule", pa.int32()),
                ("delete_rule", pa.int32()),
                ("fk_name", pa.string()),
                ("pk_name", pa.string()),
                ("deferrability", pa.int32()),
            ]
        )

    @staticmethod
    def get_exported_keys_schema():
        """Get the standard Flight SQL schema for GetExportedKeys command."""
        return FlightSQLProtobuf.get_imported_keys_schema()

    @staticmethod
    def get_cross_reference_schema():
        """Get the standard Flight SQL schema for GetCrossReference command."""
        return FlightSQLProtobuf.get_imported_keys_schema()

    # Utility methods for prepared statements
    @staticmethod
    def create_prepared_statement_handle() -> str:
        """Generate a unique prepared statement handle."""
        return f"stmt_{uuid.uuid4().hex[:16]}"

    @staticmethod
    def encode_prepared_statement_handle(handle: str) -> bytes:
        """Encode a prepared statement handle as bytes."""
        return handle.encode("utf-8")

    @staticmethod
    def create_action_begin_transaction_result(transaction_id: str) -> bytes:
        """Create ActionBeginTransactionResult using generated protobuf."""
        result = flight_sql_pb2.ActionBeginTransactionResult()
        result.transaction_id = transaction_id.encode("utf-8")
        return result.SerializeToString()

    @staticmethod
    def get_type_mapping():
        """Get mapping from database types to Arrow types."""
        return {
            # Numeric types
            "BIGINT": pa.int64(),
            "INTEGER": pa.int32(),
            "SMALLINT": pa.int16(),
            "TINYINT": pa.int8(),
            "DOUBLE": pa.float64(),
            "FLOAT": pa.float32(),
            "REAL": pa.float32(),
            "DECIMAL": pa.decimal128(38, 18),
            "NUMERIC": pa.decimal128(38, 18),
            # String types
            "VARCHAR": pa.string(),
            "CHAR": pa.string(),
            "TEXT": pa.string(),
            "STRING": pa.string(),
            # Binary types
            "BINARY": pa.binary(),
            "VARBINARY": pa.binary(),
            "BLOB": pa.binary(),
            # Date/time types
            "DATE": pa.date32(),
            "TIME": pa.time64("us"),
            "TIMESTAMP": pa.timestamp("us"),
            "TIMESTAMPTZ": pa.timestamp("us", tz="UTC"),
            # Boolean
            "BOOLEAN": pa.bool_(),
            "BOOL": pa.bool_(),
            # JSON (as string for now)
            "JSON": pa.string(),
        }

    @staticmethod
    def parse_command_from_any(any_message: any_pb2.Any):
        """Parse a command from an Any message using generated protobuf classes."""
        type_url = any_message.type_url

        if type_url == FlightSQLProtobuf.COMMAND_STATEMENT_QUERY_TYPE_URL:
            command = CommandStatementQuery()
            command.ParseFromString(any_message.value)
            return command
        if type_url == FlightSQLProtobuf.COMMAND_STATEMENT_UPDATE_TYPE_URL:
            command = CommandStatementUpdate()
            command.ParseFromString(any_message.value)
            return command
        if type_url == FlightSQLProtobuf.COMMAND_GET_TABLES_TYPE_URL:
            command = CommandGetTables()
            command.ParseFromString(any_message.value)
            return command
        if type_url == FlightSQLProtobuf.COMMAND_GET_CATALOGS_TYPE_URL:
            command = CommandGetCatalogs()
            command.ParseFromString(any_message.value)
            return command
        if type_url == FlightSQLProtobuf.COMMAND_GET_DB_SCHEMAS_TYPE_URL:
            command = CommandGetDbSchemas()
            command.ParseFromString(any_message.value)
            return command
        if type_url == FlightSQLProtobuf.COMMAND_GET_SQL_INFO_TYPE_URL:
            command = CommandGetSqlInfo()
            command.ParseFromString(any_message.value)
            return command
        if type_url == FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_QUERY_TYPE_URL:
            command = CommandPreparedStatementQuery()
            command.ParseFromString(any_message.value)
            return command
        if type_url == FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_UPDATE_TYPE_URL:
            command = CommandPreparedStatementUpdate()
            command.ParseFromString(any_message.value)
            return command

        logger.warning(f"Unknown command type URL: {type_url}")
        return None

    # Specific command parsing methods for backward compatibility
    @staticmethod
    def parse_command_get_db_schemas(command_bytes):
        """Parse CommandGetDbSchemas from command bytes."""
        # Handle both Any message and direct bytes
        if isinstance(command_bytes, any_pb2.Any):
            any_message = command_bytes
        else:
            # Parse as Any message first
            any_message = parse_any_command(command_bytes)
            if not any_message:
                # Fallback: try to parse directly
                command = CommandGetDbSchemas()
                command.ParseFromString(command_bytes)
                return command

        command = CommandGetDbSchemas()
        command.ParseFromString(any_message.value)
        return command

    @staticmethod
    def parse_command_get_tables(command_bytes):
        """Parse CommandGetTables from command bytes."""
        try:
            # Handle both Any message and direct bytes
            if isinstance(command_bytes, any_pb2.Any):
                any_message = command_bytes
                command = CommandGetTables()
                command.ParseFromString(any_message.value)
                return (
                    command.catalog if command.HasField("catalog") else None,
                    command.db_schema_filter_pattern
                    if command.HasField("db_schema_filter_pattern")
                    else None,
                    command.table_name_filter_pattern
                    if command.HasField("table_name_filter_pattern")
                    else None,
                    list(command.table_types),
                    command.include_schema,
                )
            # Parse as Any message first
            any_message = parse_any_command(command_bytes)
            if any_message:
                command = CommandGetTables()
                command.ParseFromString(any_message.value)
                return (
                    command.catalog if command.HasField("catalog") else None,
                    command.db_schema_filter_pattern
                    if command.HasField("db_schema_filter_pattern")
                    else None,
                    command.table_name_filter_pattern
                    if command.HasField("table_name_filter_pattern")
                    else None,
                    list(command.table_types),
                    command.include_schema,
                )

            # Fallback: try to parse directly as protobuf
            try:
                command = CommandGetTables()
                command.ParseFromString(command_bytes)
                return (
                    command.catalog if command.HasField("catalog") else None,
                    command.db_schema_filter_pattern
                    if command.HasField("db_schema_filter_pattern")
                    else None,
                    command.table_name_filter_pattern
                    if command.HasField("table_name_filter_pattern")
                    else None,
                    list(command.table_types),
                    command.include_schema,
                )
            except Exception:
                # For invalid data, return default tuple
                return (None, None, None, [], False)
        except Exception as e:
            protobuf_logger.debug(f"Failed to parse command get tables: {e}")
            # Return default tuple for invalid data
            return (None, None, None, [], False)

    @staticmethod
    def parse_command_statement_query(command_bytes):
        """Parse CommandStatementQuery from command bytes."""
        try:
            # Handle both Any message and direct bytes
            if isinstance(command_bytes, any_pb2.Any):
                any_message = command_bytes
                command = CommandStatementQuery()
                command.ParseFromString(any_message.value)
                return command.query if hasattr(command, "query") else ""
            # Parse as Any message first
            any_message = parse_any_command(command_bytes)
            if any_message:
                command = CommandStatementQuery()
                command.ParseFromString(any_message.value)
                return command.query if hasattr(command, "query") else ""

            # Fallback: try to parse directly as protobuf
            try:
                command = CommandStatementQuery()
                command.ParseFromString(command_bytes)
                return command.query if hasattr(command, "query") else ""
            except Exception:
                # Last fallback: if it looks like raw SQL, return it as string
                try:
                    decoded = command_bytes.decode("utf-8")
                    # Simple heuristic: if it contains SQL keywords, treat as SQL
                    if any(
                        keyword.upper() in decoded.upper()
                        for keyword in ["SELECT", "UPDATE", "INSERT", "DELETE"]
                    ):
                        return decoded
                except Exception:
                    pass
                return None
        except Exception as e:
            protobuf_logger.debug(f"Failed to parse command statement query: {e}")
            return None

    @staticmethod
    def parse_command_statement_update(command_bytes):
        """Parse CommandStatementUpdate from command bytes."""
        try:
            # Handle both Any message and direct bytes
            if isinstance(command_bytes, any_pb2.Any):
                any_message = command_bytes
                command = CommandStatementUpdate()
                command.ParseFromString(any_message.value)
                return command.query if hasattr(command, "query") else ""
            # Parse as Any message first
            any_message = parse_any_command(command_bytes)
            if any_message:
                command = CommandStatementUpdate()
                command.ParseFromString(any_message.value)
                return command.query if hasattr(command, "query") else ""

            # Fallback: try to parse directly as protobuf
            try:
                command = CommandStatementUpdate()
                command.ParseFromString(command_bytes)
                return command.query if hasattr(command, "query") else ""
            except Exception:
                # Last fallback: if it looks like raw SQL, return it as string
                try:
                    decoded = command_bytes.decode("utf-8")
                    # Simple heuristic: if it contains SQL keywords, treat as SQL
                    if any(
                        keyword.upper() in decoded.upper()
                        for keyword in ["SELECT", "UPDATE", "INSERT", "DELETE"]
                    ):
                        return decoded
                except Exception:
                    pass
                return None
        except Exception as e:
            protobuf_logger.debug(f"Failed to parse command statement update: {e}")
            return None

    @staticmethod
    def parse_command_prepared_statement_query(command_bytes):
        """Parse CommandPreparedStatementQuery from command bytes."""
        try:
            # Handle both Any message and direct bytes
            if isinstance(command_bytes, any_pb2.Any):
                any_message = command_bytes
                command = CommandPreparedStatementQuery()
                command.ParseFromString(any_message.value)
                return command
            # Parse as Any message first
            any_message = parse_any_command(command_bytes)
            if any_message:
                command = CommandPreparedStatementQuery()
                command.ParseFromString(any_message.value)
                return command

            # Fallback: try to parse directly as protobuf
            try:
                command = CommandPreparedStatementQuery()
                command.ParseFromString(command_bytes)
                return command
            except Exception:
                # For invalid data, return None
                return None
        except Exception as e:
            protobuf_logger.debug(
                f"Failed to parse command prepared statement query: {e}"
            )
            return None

    @staticmethod
    def parse_command_update(command_bytes):
        """Parse CommandStatementUpdate from command bytes (alias)."""
        return FlightSQLProtobuf.parse_command_statement_update(command_bytes)

    # Additional parsing methods that tests expect
    @staticmethod
    def parse_create_prepared_statement_request(command_bytes):
        """Parse ActionCreatePreparedStatementRequest from command bytes."""
        try:
            request = ActionCreatePreparedStatementRequest()
            request.ParseFromString(command_bytes)
            return request
        except Exception as e:
            protobuf_logger.debug(
                f"Failed to parse create prepared statement request: {e}"
            )
            return None

    @staticmethod
    def parse_close_prepared_statement_request(command_bytes):
        """Parse ActionClosePreparedStatementRequest from command bytes."""
        try:
            request = ActionClosePreparedStatementRequest()
            request.ParseFromString(command_bytes)
            return request
        except Exception as e:
            protobuf_logger.debug(
                f"Failed to parse close prepared statement request: {e}"
            )
            return None


# Utility functions
def parse_action_create_prepared_statement_request(
    action_body: bytes,
):
    """Parse ActionCreatePreparedStatementRequest using generated protobuf."""
    try:
        request = ActionCreatePreparedStatementRequest()
        request.ParseFromString(action_body)
        protobuf_logger.info(
            "Parsed ActionCreatePreparedStatementRequest", query=request.query
        )
        return request
    except Exception as e:
        protobuf_logger.error(f"Parsing failed: {e}")
        raise Exception(f"Parsing failed: {e}") from e


def parse_command_from_any(any_message: any_pb2.Any):
    """Parse a command from an Any message using generated protobuf classes."""
    return FlightSQLProtobuf.parse_command_from_any(any_message)


# Legacy aliases for backward compatibility
parse_command_prepared_statement_query = FlightSQLProtobuf.parse_command_from_any
parse_command_statement_query = FlightSQLProtobuf.parse_command_from_any

# Create aliases for backward compatibility
PreparedStatementQuery = CommandPreparedStatementQuery

# Export specific classes that may be needed
__all__ = [
    "FlightSQLProtobuf",
    "parse_any_command",
    "CommandStatementQuery",
    "CommandStatementUpdate",
    "CommandPreparedStatementQuery",
    "PreparedStatementQuery",  # alias
    "CommandGetCatalogs",
    "CommandGetDbSchemas",
    "CommandGetSqlInfo",
    "CommandGetTables",
    "CommandGetTableTypes",
    "ActionCreatePreparedStatementRequest",
    "ActionClosePreparedStatementRequest",
    "ActionBeginTransactionRequest",
    "ActionEndTransactionRequest",
    "CommandStatementQuery",
    "CommandStatementUpdate",
    "CommandPreparedStatementQuery",
    "CommandPreparedStatementUpdate",
    "CommandGetCatalogs",
    "CommandGetColumns",
    "CommandGetDbSchemas",
    "DoPutUpdateResult",
    "parse_any_command",
]


# Alias for compatibility with minimal.py - maintains original API exactly
def parse_any_command(command_bytes):
    """Parse command bytes into a protobuf Any message - original API compatibility."""
    if isinstance(command_bytes, bytes):
        # Convert bytes to Any message first - exact same logic as original
        try:
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
    else:
        # Already an Any message
        return command_bytes

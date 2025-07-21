"""
FlightSQL protobuf message definitions and handling.

This module implements the protobuf message formats expected by FlightSQL clients,
based on the Apache Arrow FlightSQL specification.
"""

import logging
import struct
import uuid
from typing import Optional, Tuple

from google.protobuf import any_pb2
import pyarrow as pa

from mpzsql.logfire_config import get_protobuf_logger

logger = logging.getLogger(__name__)

# Initialize logfire logger for protobuf operations
protobuf_logger = get_protobuf_logger()

# Keep legacy file logging for backward compatibility
# Set up protobuf logger
protobuf_log = logging.getLogger("server_protobuf")
protobuf_log.setLevel(logging.DEBUG)

# Create a file handler for the protobuf logger
protobuf_fh = logging.FileHandler("server_protobuf.log", mode='w')
protobuf_fh.setLevel(logging.DEBUG)

# Create a formatter and set it for the handler
protobuf_formatter = logging.Formatter('%(asctime)s - %(message)s')
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
        protobuf_log.info(f"parse_any_command called with {len(command_bytes)} bytes: {command_bytes.hex()}")
        protobuf_logger.info("Parsing protobuf Any command", 
                           bytes_length=len(command_bytes), 
                           bytes_hex=command_bytes.hex())
        any_message = any_pb2.Any()
        any_message.ParseFromString(command_bytes)
        protobuf_log.info(f"Successfully parsed Any message with type_url: {any_message.type_url}")
        protobuf_logger.info("Successfully parsed Any message", type_url=any_message.type_url)
        return any_message
    except Exception as e:
        protobuf_log.error(f"Could not parse command as protobuf Any: {e}")
        protobuf_logger.error("Failed to parse protobuf Any command", error=str(e))
        logger.debug(f"Could not parse command as protobuf Any: {e}")
        return None


def _parse_varint(data: bytes, offset: int) -> Tuple[int, int]:
    """Parse a varint from the data starting at the given offset."""
    result = 0
    shift = 0
    while True:
        byte = data[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return result, offset
        shift += 7


class ActionCreatePreparedStatementRequest:
    """
    Custom class to handle parsing for ActionCreatePreparedStatementRequest.
    The `query` attribute will be populated with the SQL query string.
    """

    def __init__(self):
        self.query = ""

    def ParseFromString(self, data: bytes):
        """
        Parse the protobuf data to extract the query using robust varint parsing.
        This handles the Any protobuf wrapper format where:
        - Field 1 contains the type URL
        - Field 2 contains the actual message data
        """
        try:
            logger.info(f"ActionCreatePreparedStatementRequest: parsing {len(data)} bytes: {data.hex()}")
            
            # Use robust varint parsing for the query string
            offset = 0
            while offset < len(data):
                # Read field tag and wire type
                tag_and_type, offset = _parse_varint(data, offset)
                field_number = tag_and_type >> 3
                wire_type = tag_and_type & 0x07
                
                logger.info(f"ActionCreatePreparedStatementRequest: field {field_number}, wire type {wire_type}")
                
                if field_number == 2 and wire_type == 2:  # Field 2 (value), length-delimited
                    # Read message length
                    length, offset = _parse_varint(data, offset)
                    
                    # Read the actual ActionCreatePreparedStatementRequest message
                    if offset + length <= len(data):
                        message_data = data[offset:offset + length]
                        logger.info(f"Found message data in field 2: {message_data.hex()}")
                        
                        # Parse the nested message to find the query (field 1)
                        msg_offset = 0
                        while msg_offset < len(message_data):
                            msg_tag_and_type, msg_offset = _parse_varint(message_data, msg_offset)
                            msg_field_number = msg_tag_and_type >> 3
                            msg_wire_type = msg_tag_and_type & 0x07
                            
                            if msg_field_number == 1 and msg_wire_type == 2:  # Query field
                                query_length, msg_offset = _parse_varint(message_data, msg_offset)
                                if msg_offset + query_length <= len(message_data):
                                    query_bytes = message_data[msg_offset:msg_offset + query_length]
                                    self.query = query_bytes.decode('utf-8')
                                    logger.info(f"Successfully parsed ActionCreatePreparedStatementRequest query: '{self.query}' from bytes: {query_bytes.hex()}")
                                    return
                                else:
                                    logger.error(f"Invalid query length {query_length} at offset {msg_offset}")
                                    break
                            else:
                                # Skip other fields in the nested message
                                if msg_wire_type == 0:  # Varint
                                    _, msg_offset = _parse_varint(message_data, msg_offset)
                                elif msg_wire_type == 1:  # 64-bit
                                    msg_offset += 8
                                elif msg_wire_type == 2:  # Length-delimited
                                    skip_length, msg_offset = _parse_varint(message_data, msg_offset)
                                    msg_offset += skip_length
                                elif msg_wire_type == 5:  # 32-bit
                                    msg_offset += 4
                                else:
                                    logger.error(f"Unknown nested wire type {msg_wire_type}")
                                    break
                        return
                    else:
                        logger.error(f"Invalid message length {length} at offset {offset}")
                        break
                elif field_number == 1 and wire_type == 2:  # Field 1 (type_url), skip it
                    length, offset = _parse_varint(data, offset)
                    type_url = data[offset:offset + length].decode('utf-8')
                    logger.info(f"Skipping type URL: {type_url}")
                    offset += length
                else:
                    # Skip unknown fields
                    if wire_type == 0:  # Varint
                        _, offset = _parse_varint(data, offset)
                    elif wire_type == 1:  # 64-bit
                        offset += 8
                    elif wire_type == 2:  # Length-delimited
                        length, offset = _parse_varint(data, offset)
                        skipped_data = data[offset:offset + length]
                        logger.info(f"Skipping field {field_number} with {length} bytes: {skipped_data.hex()} (decoded: {skipped_data.decode('utf-8', errors='ignore')})")
                        offset += length
                    elif wire_type == 5:  # 32-bit
                        offset += 4
                    else:
                        logger.error(f"Unknown wire type {wire_type}")
                        break
            
            logger.warning("Could not find query field in ActionCreatePreparedStatementRequest")
            self.query = ""
        except Exception as e:
            logger.error(f"Error parsing ActionCreatePreparedStatementRequest: {e}")
            self.query = ""


class ActionClosePreparedStatementRequest:
    """
    Custom class to handle parsing for ActionClosePreparedStatementRequest.
    The `prepared_statement_handle` attribute will be populated with the handle bytes.
    """

    def __init__(self):
        self.prepared_statement_handle = b""

    def ParseFromString(self, data: bytes):
        """
        Parse the protobuf data to extract the prepared statement handle.
        """
        try:
            # Use robust varint parsing for the handle
            offset = 0
            while offset < len(data):
                # Read field tag and wire type
                tag_and_type, offset = _parse_varint(data, offset)
                field_number = tag_and_type >> 3
                wire_type = tag_and_type & 0x07
                
                if field_number == 1 and wire_type == 2:  # Field 1, length-delimited
                    # Read handle length
                    length, offset = _parse_varint(data, offset)
                    
                    # Read handle data
                    if offset + length <= len(data):
                        self.prepared_statement_handle = data[offset:offset + length]
                        logger.info(f"Successfully parsed ActionClosePreparedStatementRequest handle: {self.prepared_statement_handle.hex()}")
                        return
                    else:
                        logger.error(f"Invalid handle length {length} at offset {offset}")
                        break
                else:
                    # Skip unknown fields
                    if wire_type == 0:  # Varint
                        _, offset = _parse_varint(data, offset)
                    elif wire_type == 1:  # 64-bit
                        offset += 8
                    elif wire_type == 2:  # Length-delimited
                        length, offset = _parse_varint(data, offset)
                        offset += length
                    elif wire_type == 5:  # 32-bit
                        offset += 4
                    else:
                        logger.error(f"Unknown wire type {wire_type}")
                        break
            
            logger.warning("Could not find handle field in ActionClosePreparedStatementRequest")
            self.prepared_statement_handle = b""
        except Exception as e:
            logger.error(f"Error parsing ActionClosePreparedStatementRequest: {e}")
            self.prepared_statement_handle = b""


class ActionBeginTransactionRequest:
    """Request to begin a transaction."""
    def __init__(self):
        pass

    def ParseFromString(self, data: bytes):
        pass

class ActionEndTransactionRequest:
    """Request to end a transaction."""
    def __init__(self, transaction_id: bytes = b"", action: int = 0):
        self.transaction_id = transaction_id
        self.action = action  # 0 for COMMIT, 1 for ROLLBACK

    def ParseFromString(self, data: bytes):
        # This is a placeholder. A real implementation would parse the protobuf.
        pass


class DoPutUpdateResult:
    """Represents a DoPutUpdateResult."""

    def __init__(self, record_count=0):
        self.record_count = record_count

    def SerializeToString(self) -> bytes:
        # Basic serialization, field 1 is the record count (int64)
        # Tag for field 1, wire type 0 (varint) is 0x08
        tag = 0x08
        # Varint encoding for record_count
        value = self.record_count
        if value == 0:
            return bytes([tag, 0])

        encoded_value = bytearray()
        while value > 0:
            byte = value & 0x7F
            value >>= 7
            if value > 0:
                byte |= 0x80
            encoded_value.append(byte)
        return bytes([tag]) + encoded_value


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
    """Represents a CommandStatementQuery."""
    def __init__(self):
        self.query = ""

    def ParseFromString(self, data: bytes):
        if data and data[0] == 0x0a:
            length = data[1]
            if len(data) >= 2 + length:
                self.query = data[2:2+length].decode('utf-8')

class CommandStatementUpdate:
    """Represents a CommandStatementUpdate."""
    def __init__(self):
        self.query = ""

    def ParseFromString(self, data: bytes):
        if data and data[0] == 0x0a:
            length = data[1]
            if len(data) >= 2 + length:
                self.query = data[2:2+length].decode('utf-8')

    def Unpack(self, any_command):
        """Custom Unpack method to parse from Any protobuf message."""
        try:
            # Use robust varint parsing for the query string
            data = any_command.value
            offset = 0
            while offset < len(data):
                # Read field tag and wire type
                tag_and_type, offset = _parse_varint(data, offset)
                field_number = tag_and_type >> 3
                wire_type = tag_and_type & 0x07
                
                if field_number == 1 and wire_type == 2:  # Field 1, length-delimited
                    # Read string length
                    length, offset = _parse_varint(data, offset)
                    
                    # Read string data
                    if offset + length <= len(data):
                        self.query = data[offset:offset + length].decode('utf-8')
                        logger.info(f"Successfully parsed CommandStatementUpdate query: {self.query}")
                        return
                    else:
                        logger.error(f"Invalid string length {length} at offset {offset}")
                        break
                else:
                    # Skip unknown fields
                    if wire_type == 0:  # Varint
                        _, offset = _parse_varint(data, offset)
                    elif wire_type == 1:  # 64-bit
                        offset += 8
                    elif wire_type == 2:  # Length-delimited
                        length, offset = _parse_varint(data, offset)
                        offset += length
                    elif wire_type == 5:  # 32-bit
                        offset += 4
                    else:
                        logger.error(f"Unknown wire type {wire_type}")
                        break
            
            logger.warning("Could not find query field in CommandStatementUpdate")
            self.query = ""
        except Exception as e:
            logger.error(f"Error parsing CommandStatementUpdate: {e}")
            self.query = ""


class CommandPreparedStatementQuery:
    """Represents a CommandPreparedStatementQuery.
    
    This is an alias for PreparedStatementQuery to match the expected import name.
    """
    def __init__(self):
        self.prepared_statement_handle = b""

    def ParseFromString(self, data: bytes):
        if data and data[0] == 0x0a:
            length = data[1]
            if len(data) >= 2 + length:
                self.prepared_statement_handle = data[2:2+length]

    def Unpack(self, any_message):
        """Parse the handle from the CommandPreparedStatementQuery protobuf message."""
        self.ParseFromString(any_message.value)


class CommandPreparedStatementUpdate:
    """Represents a CommandPreparedStatementUpdate."""
    def __init__(self):
        self.prepared_statement_handle = b""

    def ParseFromString(self, data: bytes):
        if data and data[0] == 0x0a:
            length = data[1]
            if len(data) >= 2 + length:
                self.prepared_statement_handle = data[2:2+length]

    def Unpack(self, any_message):
        """Parse the handle from the CommandPreparedStatementUpdate protobuf message."""
        self.ParseFromString(any_message.value)


class PreparedStatementQuery:
    """Represents a PreparedStatementQuery."""
    def __init__(self):
        self.prepared_statement_handle = b""

    def ParseFromString(self, data: bytes):
        if data and data[0] == 0x0a:
            length = data[1]
            if len(data) >= 2 + length:
                self.prepared_statement_handle = data[2:2+length]

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

        The inner message structure should be:
        - bytes prepared_statement_handle = 1;
        - bytes dataset_schema = 2; (optional)
        - bytes parameter_schema = 3; (optional)
        """
        try:
            # Create the inner ActionCreatePreparedStatementResult message
            def encode_varint(value):
                result = []
                while value > 127:
                    result.append((value & 127) | 128)
                    value >>= 7
                result.append(value & 127)
                return bytes(result)

            inner_message = b""

            # Field 1: prepared_statement_handle (bytes, field number 1, wire type 2)
            if prepared_statement_handle:
                field1_tag = (1 << 3) | 2  # field 1, wire type 2 (length-delimited)
                handle_length = len(prepared_statement_handle)
                inner_message += (
                    bytes([field1_tag])
                    + encode_varint(handle_length)
                    + prepared_statement_handle
                )

            # Field 2: dataset_schema (bytes, field number 2, wire type 2) - optional
            if dataset_schema:
                field2_tag = (2 << 3) | 2  # field 2, wire type 2 (length-delimited)
                schema_length = len(dataset_schema)
                inner_message += (
                    bytes([field2_tag]) + encode_varint(schema_length) + dataset_schema
                )

            # Field 3: parameter_schema (bytes, field number 3, wire type 2) - optional
            if parameter_schema:
                field3_tag = (3 << 3) | 2  # field 3, wire type 2 (length-delimited)
                param_length = len(parameter_schema)
                inner_message += (
                    bytes([field3_tag]) + encode_varint(param_length) + parameter_schema
                )

            # Wrap in protobuf Any message
            any_message = any_pb2.Any()
            any_message.type_url = (
                FlightSQLProtobuf.ACTION_CREATE_PREPARED_STATEMENT_RESULT_TYPE_URL
            )
            any_message.value = inner_message

            serialized = any_message.SerializeToString()
            logger.debug(
                f"Created ActionCreatePreparedStatementResult: {serialized.hex()}"
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

        This handles protobuf format that contains the prepared statement handle.
        """
        try:
            # Try parsing as protobuf Any message first
            try:
                any_message = any_pb2.Any()
                any_message.ParseFromString(command_bytes)

                if (
                    any_message.type_url
                    == FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_QUERY_TYPE_URL
                ):
                    # Extract the prepared statement handle from the value
                    handle_bytes = any_message.value

                    # The handle is typically in field 1 of the protobuf message
                    # Field 1: prepared_statement_handle (bytes, field number 1, wire type 2)
                    if (
                        len(handle_bytes) >= 3
                    ):  # At minimum: tag + length + 1 byte of data
                        # Skip field tag and length encoding to get to the actual handle
                        field_tag = handle_bytes[0]
                        if field_tag == (1 << 3) | 2:  # field 1, wire type 2
                            # Next byte(s) are varint length
                            length_start = 1
                            length = 0
                            shift = 0
                            while length_start < len(handle_bytes):
                                byte = handle_bytes[length_start]
                                length |= (byte & 0x7F) << shift
                                length_start += 1
                                if (byte & 0x80) == 0:
                                    break
                                shift += 7

                            # Extract the handle
                            handle_start = length_start
                            handle_end = handle_start + length
                            if handle_end <= len(handle_bytes):
                                handle = handle_bytes[handle_start:handle_end].decode(
                                    "utf-8"
                                )
                                logger.debug(
                                    f"Extracted prepared statement handle: {handle}"
                                )
                                return handle

            except Exception as e:
                logger.debug(f"Not a PreparedStatementQuery protobuf message: {e}")
                pass

            # Fallback: try direct decode but validate it's actually a prepared statement handle
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

        This handles both protobuf format and simple string format.
        """
        try:
            protobuf_log.info(f"parse_command_statement_query called with {len(command_bytes)} bytes: {command_bytes.hex()}")
            
            # Try parsing as protobuf Any message first
            try:
                any_message = any_pb2.Any()
                any_message.ParseFromString(command_bytes)
                protobuf_log.info(f"Parsed as Any message with type_url: {any_message.type_url}")

                if (
                    any_message.type_url
                    == FlightSQLProtobuf.COMMAND_STATEMENT_QUERY_TYPE_URL
                ):
                    # Extract the SQL from the value
                    sql_bytes = any_message.value
                    protobuf_log.info(f"SQL bytes: {sql_bytes.hex()}")

                    # Method 1: Direct decode
                    try:
                        sql = sql_bytes.decode("utf-8")
                        if sql and len(sql.strip()) > 0:
                            protobuf_log.info(f"Successfully decoded SQL (method 1): {sql}")
                            return sql.strip()
                    except UnicodeDecodeError:
                        protobuf_log.info("Direct decode failed, trying other methods")
                        pass

                    # Method 2: Skip initial bytes (might be length prefix)
                    # First, try to handle single-byte varint length prefix
                    if len(sql_bytes) > 1:
                        first_byte = sql_bytes[0]
                        # Check if first byte is a reasonable length prefix
                        if first_byte < 128 and first_byte > 0:  # Single-byte varint
                            expected_length = first_byte
                            if len(sql_bytes) >= expected_length + 1:
                                sql_candidate = sql_bytes[1 : expected_length + 1].decode("utf-8", errors="ignore")
                                if (
                                    sql_candidate.strip()
                                    and len(sql_candidate.strip()) > 2
                                    and sql_candidate.isprintable()
                                    and not sql_candidate.startswith("\x00")
                                ):
                                    protobuf_log.info(f"Successfully decoded SQL (method 2): {sql_candidate}")
                                    return sql_candidate.strip()

                    # Fallback to original method
                    for skip in [1, 2, 4, 8]:
                        try:
                            if len(sql_bytes) > skip:
                                sql_candidate = sql_bytes[skip:].decode("utf-8")
                                if sql_candidate and len(sql_candidate.strip()) > 2:
                                    protobuf_log.info(f"Successfully decoded SQL (skip {skip}): {sql_candidate}")
                                    return sql_candidate.strip()
                        except Exception:
                            continue

                    # Method 3: Look for any printable text after skipping binary prefix
                    decoded = sql_bytes.decode("utf-8", errors="ignore")
                    if decoded and len(decoded) > 1:
                        for i in range(min(4, len(decoded))):
                            candidate = decoded[i:].strip()
                            if (
                                candidate
                                and len(candidate) > 2
                                and candidate.isprintable()
                                and not candidate.startswith("\x00")
                                and (" " in candidate or len(candidate) > 3)
                            ):
                                # Clean up any null bytes or control characters
                                sql = "".join(
                                    char
                                    for char in candidate
                                    if ord(char) >= 32 or char in "\t\n\r"
                                )
                                if len(sql) > 2:
                                    protobuf_log.info(f"Successfully decoded SQL (method 3): {sql}")
                                    return sql

            except Exception as e:
                protobuf_log.info(f"Not a protobuf Any message: {e}")
                logger.debug(f"Not a protobuf Any message: {e}")
                pass

            # Fallback: try direct decode if it looks like SQL
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
                        protobuf_log.info(f"Successfully decoded SQL (direct decode): {sql_stripped}")
                        return sql_stripped
            except UnicodeDecodeError:
                pass

            # Final fallback: scan for SQL in binary data
            try:
                decoded = command_bytes.decode("utf-8", errors="ignore")

                # Handle simple varint length prefix (common case)
                if len(command_bytes) > 1:
                    first_byte = command_bytes[0]
                    if first_byte < 128 and first_byte > 0:  # Single-byte varint
                        expected_length = first_byte
                        if len(command_bytes) >= expected_length + 1:
                            sql_candidate = command_bytes[
                                1 : expected_length + 1
                            ].decode("utf-8", errors="ignore")
                            # Check if this looks like valid text (generic approach)
                            if (
                                sql_candidate.strip()
                                and len(sql_candidate.strip()) > 2
                                and sql_candidate.isprintable()
                                and not sql_candidate.startswith("\x00")
                                and (
                                    " " in sql_candidate
                                    or len(sql_candidate.strip()) > 3
                                )
                            ):
                                protobuf_log.info(f"Successfully decoded SQL (varint prefix): {sql_candidate}")
                                return sql_candidate.strip()

                # Handle the specific case where there's a field tag + length prefix
                # Pattern: \n + length_byte + SQL
                if len(decoded) >= 3 and decoded[0] == "\n":
                    # Skip the field tag (\n) and length byte to get to SQL
                    sql_candidate = decoded[2:]  # Skip \n and length byte

                    # Check if this looks like valid text (generic approach)
                    if (
                        sql_candidate.strip()
                        and len(sql_candidate.strip()) > 2
                        and sql_candidate.isprintable()
                        and not sql_candidate.startswith("\x00")
                    ):
                        # Clean up any null bytes or control characters
                        sql = "".join(
                            char
                            for char in sql_candidate
                            if ord(char) >= 32 or char in "\t\n\r"
                        )
                        sql = sql.strip()
                        if len(sql) > 2:
                            protobuf_log.info(f"Successfully decoded SQL (field tag): {sql}")
                            return sql

                # Original fallback logic - look for any printable text after skipping binary prefix
                if decoded and len(decoded) > 1:
                    for i in range(min(4, len(decoded))):
                        candidate = decoded[i:].strip()
                        if (
                            candidate
                            and len(candidate) > 2
                            and candidate.isprintable()
                            and not candidate.startswith("\x00")
                            and (" " in candidate or len(candidate) > 3)
                        ):
                            # Clean up any null bytes or control characters
                            sql = "".join(
                                char
                                for char in candidate
                                if ord(char) >= 32 or char in "\t\n\r"
                            )
                            if len(sql) > 2:
                                protobuf_log.info(f"Successfully decoded SQL (fallback): {sql}")
                                return sql
            except Exception:
                pass

            protobuf_log.warning(f"Could not extract SQL from {len(command_bytes)} bytes")
            logger.warning(f"Could not extract SQL from {len(command_bytes)} bytes")
            return None

        except Exception as e:
            protobuf_log.error(f"Error parsing CommandStatementQuery: {e}")
            logger.error(f"Error parsing CommandStatementQuery: {e}")
            return None

    @staticmethod
    def parse_command_get_db_schemas(command_bytes: bytes) -> Tuple[Optional[str], Optional[str]]:
        """
        Parse CommandGetDbSchemas protobuf message to extract catalog and schema filter.
        
        Returns:
            Tuple of (catalog, db_schema_filter_pattern)
        """
        try:
            protobuf_log.info(f"parse_command_get_db_schemas called with {len(command_bytes)} bytes: {command_bytes.hex()}")
            
            # The command_bytes are already the extracted command bytes, not an Any message
            # Parse the protobuf fields directly
            catalog = None
            db_schema_filter_pattern = None
            
            # Parse the protobuf fields
            pos = 0
            while pos < len(command_bytes):
                if pos >= len(command_bytes):
                    break
                    
                # Read field tag (varint)
                tag_byte = command_bytes[pos]
                pos += 1
                
                # Extract field number and wire type
                field_number = tag_byte >> 3
                wire_type = tag_byte & 0x07
                
                if field_number == 1 and wire_type == 2:  # catalog field, string type
                    # Read length (varint)
                    length = 0
                    shift = 0
                    while pos < len(command_bytes):
                        byte = command_bytes[pos]
                        pos += 1
                        length |= (byte & 0x7F) << shift
                        if (byte & 0x80) == 0:
                            break
                        shift += 7
                    
                    # Read the string data
                    if pos + length <= len(command_bytes):
                        catalog_bytes = command_bytes[pos:pos + length]
                        catalog = catalog_bytes.decode("utf-8")
                        pos += length
                        protobuf_log.info(f"Extracted catalog: {catalog}")
                        
                elif field_number == 2 and wire_type == 2:  # db_schema_filter_pattern field, string type
                    # Read length (varint)
                    length = 0
                    shift = 0
                    while pos < len(command_bytes):
                        byte = command_bytes[pos]
                        pos += 1
                        length |= (byte & 0x7F) << shift
                        if (byte & 0x80) == 0:
                            break
                        shift += 7
                    
                    # Read the string data
                    if pos + length <= len(command_bytes):
                        pattern_bytes = command_bytes[pos:pos + length]
                        db_schema_filter_pattern = pattern_bytes.decode("utf-8")
                        pos += length
                        protobuf_log.info(f"Extracted db_schema_filter_pattern: {db_schema_filter_pattern}")
                else:
                    # Skip unknown fields
                    if wire_type == 0:  # varint
                        while pos < len(command_bytes) and (command_bytes[pos] & 0x80) != 0:
                            pos += 1
                        if pos < len(command_bytes):
                            pos += 1
                    elif wire_type == 2:  # length-delimited
                        # Read length and skip that many bytes
                        length = 0
                        shift = 0
                        while pos < len(command_bytes):
                            byte = command_bytes[pos]
                            pos += 1
                            length |= (byte & 0x7F) << shift
                            if (byte & 0x80) == 0:
                                break
                            shift += 7
                        pos += length
                    else:
                        protobuf_log.warning(f"Skipping unknown wire type {wire_type} for field {field_number}")
                        break
            
            protobuf_log.info(f"Parsed GetDbSchemas: catalog={catalog}, db_schema_filter_pattern={db_schema_filter_pattern}")
            return catalog, db_schema_filter_pattern
            
        except Exception as e:
            protobuf_log.error(f"Error parsing CommandGetDbSchemas: {e}")
            return None, None

    @staticmethod
    def parse_command_get_tables(command_bytes: bytes) -> Tuple[Optional[str], Optional[str], Optional[str], list, bool]:
        """
        Parse CommandGetTables protobuf message to extract parameters.
        
        Returns:
            Tuple of (catalog, db_schema_filter_pattern, table_name_filter_pattern, table_types, include_schema)
        """
        try:
            protobuf_log.info(f"parse_command_get_tables called with {len(command_bytes)} bytes: {command_bytes.hex()}")
            
            # Try parsing as protobuf Any message first
            try:
                any_message = any_pb2.Any()
                any_message.ParseFromString(command_bytes)
                
                if any_message.type_url == FlightSQLProtobuf.COMMAND_GET_TABLES_TYPE_URL:
                    # Extract the command from the value
                    command_bytes = any_message.value
                    protobuf_log.info(f"Extracted command bytes: {command_bytes.hex()}")
                    
                    # Parse the protobuf fields from the extracted command bytes
                    catalog = None
                    db_schema_filter_pattern = None
                    table_name_filter_pattern = None
                    table_types = []
                    include_schema = False
                    
                    pos = 0
                    while pos < len(command_bytes):
                        if pos >= len(command_bytes):
                            break
                            
                        # Read field tag (varint)
                        tag_byte = command_bytes[pos]
                        pos += 1
                        
                        # Extract field number and wire type
                        field_number = tag_byte >> 3
                        wire_type = tag_byte & 0x07
                        
                        if field_number == 1 and wire_type == 2:  # catalog field, string type
                            # Read length (varint)
                            length = 0
                            shift = 0
                            while pos < len(command_bytes):
                                byte = command_bytes[pos]
                                pos += 1
                                length |= (byte & 0x7F) << shift
                                if (byte & 0x80) == 0:
                                    break
                                shift += 7
                            
                            # Read the string data
                            if pos + length <= len(command_bytes):
                                catalog_bytes = command_bytes[pos:pos + length]
                                catalog = catalog_bytes.decode("utf-8")
                                pos += length
                                protobuf_log.info(f"Extracted catalog: {catalog}")
                                
                        elif field_number == 2 and wire_type == 2:  # db_schema_filter_pattern field, string type
                            # Read length (varint)
                            length = 0
                            shift = 0
                            while pos < len(command_bytes):
                                byte = command_bytes[pos]
                                pos += 1
                                length |= (byte & 0x7F) << shift
                                if (byte & 0x80) == 0:
                                    break
                                shift += 7
                            
                            # Read the string data
                            if pos + length <= len(command_bytes):
                                pattern_bytes = command_bytes[pos:pos + length]
                                db_schema_filter_pattern = pattern_bytes.decode("utf-8")
                                pos += length
                                protobuf_log.info(f"Extracted db_schema_filter_pattern: {db_schema_filter_pattern}")
                                
                        elif field_number == 3 and wire_type == 2:  # table_name_filter_pattern field, string type
                            # Read length (varint)
                            length = 0
                            shift = 0
                            while pos < len(command_bytes):
                                byte = command_bytes[pos]
                                pos += 1
                                length |= (byte & 0x7F) << shift
                                if (byte & 0x80) == 0:
                                    break
                                shift += 7
                            
                            # Read the string data
                            if pos + length <= len(command_bytes):
                                pattern_bytes = command_bytes[pos:pos + length]
                                table_name_filter_pattern = pattern_bytes.decode("utf-8")
                                pos += length
                                protobuf_log.info(f"Extracted table_name_filter_pattern: {table_name_filter_pattern}")
                                
                        elif field_number == 4 and wire_type == 2:  # table_types field, repeated string type
                            # Read length (varint)
                            length = 0
                            shift = 0
                            while pos < len(command_bytes):
                                byte = command_bytes[pos]
                                pos += 1
                                length |= (byte & 0x7F) << shift
                                if (byte & 0x80) == 0:
                                    break
                                shift += 7
                            
                            # Read the string data
                            if pos + length <= len(command_bytes):
                                table_type_bytes = command_bytes[pos:pos + length]
                                table_type = table_type_bytes.decode("utf-8")
                                table_types.append(table_type)
                                pos += length
                                protobuf_log.info(f"Extracted table_type: {table_type}")
                                
                        elif field_number == 5 and wire_type == 0:  # include_schema field, bool type
                            # Read varint
                            value = 0
                            shift = 0
                            while pos < len(command_bytes):
                                byte = command_bytes[pos]
                                pos += 1
                                value |= (byte & 0x7F) << shift
                                if (byte & 0x80) == 0:
                                    break
                                shift += 7
                            include_schema = bool(value)
                            protobuf_log.info(f"Extracted include_schema: {include_schema}")
                            
                        else:
                            # Skip unknown fields
                            if wire_type == 0:  # varint
                                while pos < len(command_bytes) and (command_bytes[pos] & 0x80) != 0:
                                    pos += 1
                                if pos < len(command_bytes):
                                    pos += 1
                            elif wire_type == 2:  # length-delimited
                                # Read length and skip that many bytes
                                length = 0
                                shift = 0
                                while pos < len(command_bytes):
                                    byte = command_bytes[pos]
                                    pos += 1
                                    length |= (byte & 0x7F) << shift
                                    if (byte & 0x80) == 0:
                                        break
                                    shift += 7
                                pos += length
                            else:
                                protobuf_log.warning(f"Skipping unknown wire type {wire_type} for field {field_number}")
                                break
                    
                    protobuf_log.info(f"Parsed GetTables: catalog={catalog}, db_schema_filter_pattern={db_schema_filter_pattern}, table_name_filter_pattern={table_name_filter_pattern}, table_types={table_types}, include_schema={include_schema}")
                    return catalog, db_schema_filter_pattern, table_name_filter_pattern, table_types, include_schema
                    
            except Exception as e:
                protobuf_log.debug(f"Not a protobuf Any message: {e}")
                
            # Try parsing directly as command bytes (without Any wrapper)
            catalog = None
            db_schema_filter_pattern = None
            table_name_filter_pattern = None
            table_types = []
            include_schema = False
            
            pos = 0
            while pos < len(command_bytes):
                if pos >= len(command_bytes):
                    break
                    
                # Read field tag (varint)
                tag_byte = command_bytes[pos]
                pos += 1
                
                # Extract field number and wire type
                field_number = tag_byte >> 3
                wire_type = tag_byte & 0x07
                
                if field_number == 1 and wire_type == 2:  # catalog field, string type
                    # Read length (varint)
                    length = 0
                    shift = 0
                    while pos < len(command_bytes):
                        byte = command_bytes[pos]
                        pos += 1
                        length |= (byte & 0x7F) << shift
                        if (byte & 0x80) == 0:
                            break
                        shift += 7
                    
                    # Read the string data
                    if pos + length <= len(command_bytes):
                        catalog_bytes = command_bytes[pos:pos + length]
                        catalog = catalog_bytes.decode("utf-8")
                        pos += length
                        protobuf_log.info(f"Extracted catalog (direct): {catalog}")
                        
                elif field_number == 2 and wire_type == 2:  # db_schema_filter_pattern field, string type
                    # Read length (varint)
                    length = 0
                    shift = 0
                    while pos < len(command_bytes):
                        byte = command_bytes[pos]
                        pos += 1
                        length |= (byte & 0x7F) << shift
                        if (byte & 0x80) == 0:
                            break
                        shift += 7
                    
                    # Read the string data
                    if pos + length <= len(command_bytes):
                        pattern_bytes = command_bytes[pos:pos + length]
                        db_schema_filter_pattern = pattern_bytes.decode("utf-8")
                        pos += length
                        protobuf_log.info(f"Extracted db_schema_filter_pattern (direct): {db_schema_filter_pattern}")
                        
                elif field_number == 3 and wire_type == 2:  # table_name_filter_pattern field, string type
                    # Read length (varint)
                    length = 0
                    shift = 0
                    while pos < len(command_bytes):
                        byte = command_bytes[pos]
                        pos += 1
                        length |= (byte & 0x7F) << shift
                        if (byte & 0x80) == 0:
                            break
                        shift += 7
                    
                    # Read the string data
                    if pos + length <= len(command_bytes):
                        pattern_bytes = command_bytes[pos:pos + length]
                        table_name_filter_pattern = pattern_bytes.decode("utf-8")
                        pos += length
                        protobuf_log.info(f"Extracted table_name_filter_pattern (direct): {table_name_filter_pattern}")
                        
                elif field_number == 4 and wire_type == 2:  # table_types field, repeated string type
                    # Read length (varint)
                    length = 0
                    shift = 0
                    while pos < len(command_bytes):
                        byte = command_bytes[pos]
                        pos += 1
                        length |= (byte & 0x7F) << shift
                        if (byte & 0x80) == 0:
                            break
                        shift += 7
                    
                    # Read the string data
                    if pos + length <= len(command_bytes):
                        table_type_bytes = command_bytes[pos:pos + length]
                        table_type = table_type_bytes.decode("utf-8")
                        table_types.append(table_type)
                        pos += length
                        protobuf_log.info(f"Extracted table_type (direct): {table_type}")
                        
                elif field_number == 5 and wire_type == 0:  # include_schema field, bool type
                    # Read varint
                    value = 0
                    shift = 0
                    while pos < len(command_bytes):
                        byte = command_bytes[pos]
                        pos += 1
                        value |= (byte & 0x7F) << shift
                        if (byte & 0x80) == 0:
                            break
                        shift += 7
                    include_schema = bool(value)
                    protobuf_log.info(f"Extracted include_schema (direct): {include_schema}")
                    
                else:
                    # Skip unknown fields
                    if wire_type == 0:  # varint
                        while pos < len(command_bytes) and (command_bytes[pos] & 0x80) != 0:
                            pos += 1
                        if pos < len(command_bytes):
                            pos += 1
                    elif wire_type == 2:  # length-delimited
                        # Read length and skip that many bytes
                        length = 0
                        shift = 0
                        while pos < len(command_bytes):
                            byte = command_bytes[pos]
                            pos += 1
                            length |= (byte & 0x7F) << shift
                            if (byte & 0x80) == 0:
                                break
                            shift += 7
                        pos += length
                    else:
                        protobuf_log.warning(f"Skipping unknown wire type {wire_type} for field {field_number}")
                        break
            
            if catalog is not None or db_schema_filter_pattern is not None or table_name_filter_pattern is not None or table_types or include_schema:
                protobuf_log.info(f"Parsed GetTables (direct): catalog={catalog}, db_schema_filter_pattern={db_schema_filter_pattern}, table_name_filter_pattern={table_name_filter_pattern}, table_types={table_types}, include_schema={include_schema}")
                return catalog, db_schema_filter_pattern, table_name_filter_pattern, table_types, include_schema
                
            protobuf_log.warning(f"Could not parse GetTables from {len(command_bytes)} bytes")
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

        This matches the Examples server's approach of extracting request.query from the protobuf.
        The structure is:
        - Any message with type_url and value
        - value contains ActionCreatePreparedStatementRequest with query field
        """
        try:
            # Parse as protobuf Any message
            any_message = any_pb2.Any()
            any_message.ParseFromString(action_body)

            # Extract the ActionCreatePreparedStatementRequest from the Any message value
            inner_message_bytes = any_message.value

            # Parse the inner ActionCreatePreparedStatementRequest protobuf
            # Structure: field 1 (query) as string
            # Wire format: tag + length + string_data

            # Parse the protobuf manually to extract the query field
            pos = 0
            while pos < len(inner_message_bytes):
                # Read field tag (varint)
                if pos >= len(inner_message_bytes):
                    break

                tag_byte = inner_message_bytes[pos]
                pos += 1

                # Extract field number and wire type
                field_number = tag_byte >> 3
                wire_type = tag_byte & 0x07

                if field_number == 1 and wire_type == 2:  # query field, string type
                    # Read length (varint)
                    length = 0
                    shift = 0
                    while pos < len(inner_message_bytes):
                        byte = inner_message_bytes[pos]
                        pos += 1
                        length |= (byte & 0x7F) << shift
                        if (byte & 0x80) == 0:
                            break

                    # Read the string data
                    if pos + length <= len(inner_message_bytes):
                        query_bytes = inner_message_bytes[pos : pos + length]
                        query = query_bytes.decode("utf-8", errors="ignore")
                        logger.info(f"Extracted query from ActionCreatePreparedStatementRequest: {query}")
                        return query
                    else:
                        logger.error("Invalid length for query in ActionCreatePreparedStatementRequest")

                # Skip unknown fields
                elif wire_type == 0:  # varint
                    # Fast forward to next byte, varint fields are always 1 byte in this context
                    pos += 1
                elif wire_type == 2:  # length-delimited
                    # Read length (varint)
                    length = 0
                    shift = 0
                    while pos < len(inner_message_bytes):
                        byte = inner_message_bytes[pos]
                        pos += 1
                        length |= (byte & 0x7F) << shift
                        if (byte & 0x80) == 0:
                            break

                    # Skip the length-delimited field
                    pos += length
                else:
                    logger.warning(f"Skipping unknown wire type {wire_type} for field {field_number}")

            logger.warning("Query not found in ActionCreatePreparedStatementRequest")
            return None

        except Exception as e:
            logger.error(f"Error parsing CreatePreparedStatement request: {e}")
            return None

    @staticmethod
    def parse_close_prepared_statement_request(action_body: bytes) -> Optional[bytes]:
        """
        Parse ClosePreparedStatement request to extract prepared statement handle.

        This matches the Examples server's approach of extracting request.prepared_statement_handle from the protobuf.
        The structure is:
        - Any message with type_url and value
        - value contains ActionClosePreparedStatementRequest with prepared_statement_handle field
        """
        try:
            # Parse as protobuf Any message
            any_message = any_pb2.Any()
            any_message.ParseFromString(action_body)

            # Extract the ActionClosePreparedStatementRequest from the Any message value
            inner_message_bytes = any_message.value

            # Parse the inner ActionClosePreparedStatementRequest protobuf
            # Structure: field 1 (prepared_statement_handle) as bytes
            # Wire format: tag + length + bytes_data

            # Parse the protobuf manually to extract the prepared_statement_handle field
            pos = 0
            while pos < len(inner_message_bytes):
                # Read field tag (varint)
                if pos >= len(inner_message_bytes):
                    break

                tag_byte = inner_message_bytes[pos]
                pos += 1

                # Extract field number and wire type
                field_number = tag_byte >> 3
                wire_type = tag_byte & 0x07

                if field_number == 1 and wire_type == 2:  # prepared_statement_handle field, bytes type
                    # Read length (varint)
                    length = 0
                    shift = 0
                    while pos < len(inner_message_bytes):
                        byte = inner_message_bytes[pos]
                        pos += 1
                        length |= (byte & 0x7F) << shift
                        if (byte & 0x80) == 0:
                            break

                    # Read the bytes data
                    if pos + length <= len(inner_message_bytes):
                        handle_bytes = inner_message_bytes[pos : pos + length]
                        logger.info(f"Extracted prepared statement handle from ActionClosePreparedStatementRequest: {handle_bytes.hex()}")
                        return handle_bytes
                    else:
                        logger.error("Invalid length for prepared_statement_handle in ActionClosePreparedStatementRequest")

                # Skip unknown fields
                elif wire_type == 0:  # varint
                    # Fast forward to next byte, varint fields are always 1 byte in this context
                    pos += 1
                elif wire_type == 2:  # length-delimited
                    # Read length (varint)
                    length = 0
                    shift = 0
                    while pos < len(inner_message_bytes):
                        byte = inner_message_bytes[pos]
                        pos += 1
                        length |= (byte & 0x7F) << shift
                        if (byte & 0x80) == 0:
                            break

                    # Skip the length-delimited field
                    pos += length
                else:
                    logger.warning(f"Skipping unknown wire type {wire_type} for field {field_number}")

            logger.warning("Prepared statement handle not found in ActionClosePreparedStatementRequest")
            return None

        except Exception as e:
            logger.error(f"Error parsing ClosePreparedStatement request: {e}")
            return None

    @staticmethod
    def parse_command_update(command_bytes: bytes) -> Optional[bytes]:
        """
        Parse CommandPreparedStatementUpdate protobuf message to extract prepared statement handle.

        This handles protobuf format that contains the prepared statement handle.
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
                    # Extract the prepared statement handle from the value
                    handle_bytes = any_message.value

                    # The handle is typically in field 1 of the protobuf message
                    # Field 1: prepared_statement_handle (bytes, field number 1, wire type 2)
                    if (
                        len(handle_bytes) >= 3
                    ):  # At minimum: tag + length + 1 byte of data
                        # Skip field tag and length encoding to get to the actual handle
                        field_tag = handle_bytes[0]
                        if field_tag == (1 << 3) | 2:  # field 1, wire type 2
                            # Next byte(s) are varint length
                            length_start = 1
                            length = 0
                            shift = 0
                            while length_start < len(handle_bytes):
                                byte = handle_bytes[length_start]
                                length |= (byte & 0x7F) << shift
                                length_start += 1
                                if (byte & 0x80) == 0:
                                    break
                                shift += 7

                            # Extract the handle
                            handle_start = length_start
                            handle_end = handle_start + length
                            if handle_end <= len(handle_bytes):
                                handle = handle_bytes[handle_start:handle_end]
                                logger.debug(
                                    f"Extracted prepared statement handle: {handle.hex()}"
                                )
                                return handle

            except Exception as e:
                logger.debug(f"Not a PreparedStatementUpdate protobuf message: {e}")
                pass

            # Fallback: try direct decode but validate it's actually a prepared statement handle
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
            logger.error(f"Error parsing CommandPreparedStatementUpdate: {e}")

        logger.debug(f"Could not extract handle from {len(command_bytes)} bytes")
        return None

    @staticmethod
    def parse_command_statement_update(command_bytes: bytes) -> Optional[str]:
        """
        Parse CommandPreparedStatementUpdate protobuf message to extract SQL.

        This handles both protobuf format and simple string format.
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
                    # Extract the SQL from the value
                    sql_bytes = any_message.value

                    # Method 1: Direct decode
                    try:
                        sql = sql_bytes.decode("utf-8")
                        if sql and len(sql.strip()) > 0:
                            return sql.strip()
                    except UnicodeDecodeError:
                        pass

                    # Method 2: Skip initial bytes (might be length prefix)
                    # First, try to handle single-byte varint length prefix
                    if len(sql_bytes) > 1:
                        first_byte = sql_bytes[0]
                        # Check if first byte is a reasonable length prefix
                        if first_byte < 128 and first_byte > 0:  # Single-byte varint
                            expected_length = first_byte
                            if len(sql_bytes) >= expected_length + 1:
                                sql_candidate = sql_bytes[
                                    1 : expected_length + 1
                                ].decode("utf-8", errors="ignore")
                                # Check if this looks like valid text (not specific keywords)
                                if (
                                    sql_candidate.strip()
                                    and len(sql_candidate.strip()) > 2
                                    and sql_candidate.isprintable()
                                    and not sql_candidate.startswith("\x00")
                                ):
                                    return sql_candidate.strip()

                    # Fallback to original method
                    for skip in [1, 2, 4, 8]:
                        try:
                            if len(sql_bytes) > skip:
                                sql = sql_bytes[skip:].decode("utf-8", errors="ignore")
                                if sql and len(sql.strip()) > 5:
                                    return sql.strip()
                        except Exception:
                            continue

                    # Method 3: Look for any printable text after skipping binary prefix
                    decoded = sql_bytes.decode("utf-8", errors="ignore")
                    if decoded and len(decoded) > 1:
                        for i in range(min(4, len(decoded))):
                            candidate = decoded[i:].strip()
                            if (
                                candidate
                                and len(candidate) > 2
                                and candidate.isprintable()
                                and not candidate.startswith("\x00")
                                and (" " in candidate or len(candidate) > 3)
                            ):
                                # Clean up any null bytes or control characters
                                sql = "".join(
                                    char
                                    for char in candidate
                                    if ord(char) >= 32 or char in "\t\n\r"
                                )
                                if len(sql) > 2:
                                    return sql

            except Exception as e:
                logger.debug(f"Not a protobuf Any message: {e}")
                pass

            # Fallback: try direct decode if it looks like SQL
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

            # Final fallback: scan for SQL in binary data
            try:
                decoded = command_bytes.decode("utf-8", errors="ignore")

                # Handle simple varint length prefix (common case)
                if len(command_bytes) > 1:
                    first_byte = command_bytes[0]
                    if first_byte < 128 and first_byte > 0:  # Single-byte varint
                        expected_length = first_byte
                        if len(command_bytes) >= expected_length + 1:
                            sql_candidate = command_bytes[
                                1 : expected_length + 1
                            ].decode("utf-8", errors="ignore")
                            # Check if this looks like valid text (generic approach)
                            if (
                                sql_candidate.strip()
                                and len(sql_candidate.strip()) > 2
                                and sql_candidate.isprintable()
                                and not sql_candidate.startswith("\x00")
                                and (
                                    " " in sql_candidate
                                    or len(sql_candidate.strip()) > 3
                                )
                            ):
                                return sql_candidate.strip()

                # Handle the specific case where there's a field tag + length prefix
                # Pattern: \n + length_byte + SQL
                if len(decoded) >= 3 and decoded[0] == "\n":
                    # Skip the field tag (\n) and length byte to get to SQL
                    sql_candidate = decoded[2:]  # Skip \n and length byte

                    # Check if this looks like valid text (generic approach)
                    if (
                        sql_candidate.strip()
                        and len(sql_candidate.strip()) > 2
                        and sql_candidate.isprintable()
                        and not sql_candidate.startswith("\x00")
                    ):
                        # Clean up any null bytes or control characters
                        sql = "".join(
                            char
                            for char in sql_candidate
                            if ord(char) >= 32 or char in "\t\n\r"
                        )
                        sql = sql.strip()
                        if len(sql) > 2:
                            return sql

                # Original fallback logic - look for any printable text after skipping binary prefix
                if decoded and len(decoded) > 1:
                    for i in range(min(4, len(decoded))):
                        candidate = decoded[i:].strip()
                        if (
                            candidate
                            and len(candidate) > 2
                            and candidate.isprintable()
                            and not candidate.startswith("\x00")
                            and (" " in candidate or len(candidate) > 3)
                        ):
                            # Clean up any null bytes or control characters
                            sql = "".join(
                                char
                                for char in candidate
                                if ord(char) >= 32 or char in "\t\n\r"
                            )
                            if len(sql) > 2:
                                return sql
            except Exception:
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
        return pa.schema([
            ("catalog_name", pa.string()),
            ("db_schema_name", pa.string()),
            ("table_name", pa.string()),
            ("table_type", pa.string()),
            ("table_remarks", pa.string()),
        ])

    @staticmethod
    def get_tables_schema_minimal():
        """Get the minimal Flight SQL schema for GetTables command without table_schema.
        
        This is the minimal schema according to the Flight SQL specification,
        but most JDBC drivers expect the table_schema column.
        """
        return pa.schema([
            ("catalog_name", pa.string()),
            ("db_schema_name", pa.string()),
            ("table_name", pa.string()),
            ("table_type", pa.string()),
        ])

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
        return pa.schema([
            ("catalog_name", pa.string()),
            ("db_schema_name", pa.string()),
            ("table_name", pa.string()),
            ("table_type", pa.string()),
            ("table_remarks", pa.string()),  # Standard Flight SQL column for comments/remarks
            ("table_schema", pa.binary()),  # This contains the Arrow schema as bytes
        ])

    @staticmethod
    def get_sql_info_schema():
        """Get the standard Flight SQL schema for GetSqlInfo command.
        
        The schema for SQL info responses should contain:
        - info_name: uint32 NOT NULL (the SQL info code)
        - value: string (simplified - we'll use string values for all info)
        
        Based on the Arrow Flight SQL specification, the proper schema would use
        a dense_union for the value field, but we're simplifying to strings for now.
        """
        return pa.schema([
            ("info_name", pa.uint32()),
            ("value", pa.string()),
        ])

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
            pa.field("int32_to_int32_list_map_value", pa.map_(pa.int32(), pa.list_(pa.int32()))),
        ]
        
        # Create dense union type
        union_type = pa.union(union_fields, mode="dense")
        
        return pa.schema([
            ("info_name", pa.uint32()),
            ("value", union_type),
        ])

    @staticmethod
    def get_primary_keys_schema():
        """Get the standard Flight SQL schema for GetPrimaryKeys command."""
        # Match Examples server: lowercase field names
        return pa.schema([
            ("catalog_name", pa.string()),
            ("schema_name", pa.string()),
            ("table_name", pa.string()),
            ("column_name", pa.string()),
            ("key_sequence", pa.int32()),
            ("key_name", pa.string()),
        ])

    @staticmethod
    def get_imported_keys_schema():
        """Get the standard Flight SQL schema for GetImportedKeys command."""
        return pa.schema([
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
        ])

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
        return pa.schema([
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
        ])

    @staticmethod
    def create_action_begin_transaction_result(transaction_id: str) -> bytes:
        """Create ActionBeginTransactionResult protobuf message."""
        try:
            def encode_varint(value):
                result = []
                while value > 127:
                    result.append((value & 127) | 128)
                    value >>= 7
                result.append(value & 127)
                return bytes(result)

            # Field 1: transaction_id (string)
            field1_tag = (1 << 3) | 2  # field 1, wire type 2
            id_bytes = transaction_id.encode('utf-8')
            inner_message = (
                bytes([field1_tag]) + 
                encode_varint(len(id_bytes)) + 
                id_bytes
            )

            # Wrap in Any message
            any_message = any_pb2.Any()
            any_message.type_url = FlightSQLProtobuf.ACTION_BEGIN_TRANSACTION_RESULT_TYPE_URL
            any_message.value = inner_message
            
            return any_message.SerializeToString()
        except Exception as e:
            logger.error(f"Error creating ActionBeginTransactionResult: {e}")
            return transaction_id.encode('utf-8')

    @staticmethod
    def get_type_mapping():
        """Get mapping from database types to Arrow types, matching Examples implementation."""
        return {
            # Numeric types
            'INTEGER': pa.int32(),
            'BIGINT': pa.int64(),
            'SMALLINT': pa.int16(),
            'TINYINT': pa.int8(),
            'HUGEINT': pa.decimal128(38, 0),
            'DECIMAL': pa.decimal128(38, 10),  # Default precision/scale
            'FLOAT': pa.float32(),
            'REAL': pa.float32(),
            'DOUBLE': pa.float64(),
            
            # String types
            'VARCHAR': pa.string(),
            'CHAR': pa.string(),
            'TEXT': pa.string(),
            'STRING': pa.string(),
            'BLOB': pa.binary(),
            
            # Boolean
            'BOOLEAN': pa.bool_(),
            'BOOL': pa.bool_(),
            
            # Date/Time types
            'DATE': pa.date32(),
            'TIME': pa.time64('us'),
            'TIMESTAMP': pa.timestamp('us'),
            'TIMESTAMP_MS': pa.timestamp('ms'),
            'TIMESTAMP_NS': pa.timestamp('ns'),
            'TIMESTAMP_S': pa.timestamp('s'),
            'INTERVAL': pa.duration('us'),
            
            # Unsigned types
            'UINTEGER': pa.uint32(),
            'UBIGINT': pa.uint64(),
            'USMALLINT': pa.uint16(),
            'UTINYINT': pa.uint8(),
            
            # Special types
            'UUID': pa.string(),  # UUID as string
            'JSON': pa.string(),  # JSON as string
            
            # Default
            'UNKNOWN': pa.null(),
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
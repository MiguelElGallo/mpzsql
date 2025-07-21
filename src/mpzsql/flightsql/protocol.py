"""
FlightSQL protocol support for MPZSQL server.

This module implements FlightSQL protocol handling and protobuf message parsing
to support JDBC clients and other FlightSQL-compatible clients.
"""

import logging
from typing import Optional, Dict, Any, Tuple

import pyarrow as pa
import pyarrow.flight as pf

logger = logging.getLogger(__name__)


class FlightSQLCommands:
    """FlightSQL command type constants."""

    COMMAND_STATEMENT_QUERY = "CommandStatementQuery"
    COMMAND_STATEMENT_UPDATE = "CommandStatementUpdate"
    COMMAND_PREPARED_STATEMENT_QUERY = "CommandPreparedStatementQuery"
    COMMAND_PREPARED_STATEMENT_UPDATE = "CommandPreparedStatementUpdate"
    CREATE_PREPARED_STATEMENT = "CreatePreparedStatement"
    CLOSE_PREPARED_STATEMENT = "ClosePreparedStatement"
    COMMAND_GET_CATALOGS = "CommandGetCatalogs"
    COMMAND_GET_SCHEMAS = "CommandGetSchemas"
    COMMAND_GET_TABLES = "CommandGetTables"
    COMMAND_GET_TABLE_TYPES = "CommandGetTableTypes"
    COMMAND_GET_SQL_INFO = "CommandGetSqlInfo"
    COMMAND_GET_PRIMARY_KEYS = "CommandGetPrimaryKeys"
    COMMAND_GET_EXPORTED_KEYS = "CommandGetExportedKeys"
    COMMAND_GET_IMPORTED_KEYS = "CommandGetImportedKeys"
    COMMAND_GET_CROSS_REFERENCE = "CommandGetCrossReference"
    COMMAND_GET_TYPE_INFO = "CommandGetXdbcTypeInfo"
    
    # Actions
    ACTION_CREATE_PREPARED_STATEMENT = "CreatePreparedStatement"
    ACTION_CLOSE_PREPARED_STATEMENT = "ClosePreparedStatement"
    ACTION_BEGIN_TRANSACTION = "BeginTransaction"
    ACTION_END_TRANSACTION = "EndTransaction"


class FlightSQLSchemas:
    """Standard FlightSQL schemas matching C++ implementation."""
    
    @staticmethod
    def get_catalogs_schema() -> pa.Schema:
        """Schema for GetCatalogs command."""
        return pa.schema([
            pa.field("catalog_name", pa.utf8(), nullable=False)
        ])
    
    @staticmethod
    def get_db_schemas_schema() -> pa.Schema:
        """Schema for GetDbSchemas command."""
        return pa.schema([
            pa.field("catalog_name", pa.utf8()),
            pa.field("db_schema_name", pa.utf8(), nullable=False)
        ])
    
    @staticmethod
    def get_tables_schema() -> pa.Schema:
        """Schema for GetTables command without schema."""
        return pa.schema([
            pa.field("catalog_name", pa.utf8()),
            pa.field("db_schema_name", pa.utf8()),
            pa.field("table_name", pa.utf8(), nullable=False),
            pa.field("table_type", pa.utf8(), nullable=False)
        ])
    
    @staticmethod
    def get_tables_schema_with_included_schema() -> pa.Schema:
        """Schema for GetTables command with included schema."""
        return pa.schema([
            pa.field("catalog_name", pa.utf8()),
            pa.field("db_schema_name", pa.utf8()),
            pa.field("table_name", pa.utf8(), nullable=False),
            pa.field("table_type", pa.utf8(), nullable=False),
            pa.field("table_schema", pa.binary(), nullable=False)
        ])
    
    @staticmethod
    def get_table_types_schema() -> pa.Schema:
        """Schema for GetTableTypes command."""
        return pa.schema([
            pa.field("table_type", pa.utf8(), nullable=False)
        ])
    
    @staticmethod
    def get_primary_keys_schema() -> pa.Schema:
        """Schema for GetPrimaryKeys command."""
        return pa.schema([
            pa.field("catalog_name", pa.utf8()),
            pa.field("db_schema_name", pa.utf8()),
            pa.field("table_name", pa.utf8(), nullable=False),
            pa.field("column_name", pa.utf8(), nullable=False),
            pa.field("key_sequence", pa.int32(), nullable=False),
            pa.field("key_name", pa.utf8())
        ])
    
    @staticmethod
    def get_imported_keys_schema() -> pa.Schema:
        """Schema for GetImportedKeys command."""
        return pa.schema([
            pa.field("pk_catalog_name", pa.utf8()),
            pa.field("pk_db_schema_name", pa.utf8()),
            pa.field("pk_table_name", pa.utf8(), nullable=False),
            pa.field("pk_column_name", pa.utf8(), nullable=False),
            pa.field("fk_catalog_name", pa.utf8()),
            pa.field("fk_db_schema_name", pa.utf8()),
            pa.field("fk_table_name", pa.utf8(), nullable=False),
            pa.field("fk_column_name", pa.utf8(), nullable=False),
            pa.field("key_sequence", pa.int32(), nullable=False),
            pa.field("fk_key_name", pa.utf8()),
            pa.field("pk_key_name", pa.utf8()),
            pa.field("update_rule", pa.uint8(), nullable=False),
            pa.field("delete_rule", pa.uint8(), nullable=False)
        ])
    
    @staticmethod
    def get_exported_keys_schema() -> pa.Schema:
        """Schema for GetExportedKeys command."""
        # Same as imported keys
        return FlightSQLSchemas.get_imported_keys_schema()
    
    @staticmethod
    def get_cross_reference_schema() -> pa.Schema:
        """Schema for GetCrossReference command."""
        # Same as imported keys
        return FlightSQLSchemas.get_imported_keys_schema()
    
    @staticmethod
    def get_xdbc_type_info_schema() -> pa.Schema:
        """Schema for GetXdbcTypeInfo command."""
        return pa.schema([
            pa.field("type_name", pa.utf8(), nullable=False),
            pa.field("data_type", pa.int32(), nullable=False),
            pa.field("column_size", pa.int32()),
            pa.field("literal_prefix", pa.utf8()),
            pa.field("literal_suffix", pa.utf8()),
            pa.field("create_params", pa.list_(pa.utf8())),
            pa.field("nullable", pa.int32(), nullable=False),
            pa.field("case_sensitive", pa.bool_(), nullable=False),
            pa.field("searchable", pa.int32(), nullable=False),
            pa.field("unsigned_attribute", pa.bool_()),
            pa.field("fixed_prec_scale", pa.bool_(), nullable=False),
            pa.field("auto_increment", pa.bool_()),
            pa.field("local_type_name", pa.utf8()),
            pa.field("minimum_scale", pa.int32()),
            pa.field("maximum_scale", pa.int32()),
            pa.field("sql_data_type", pa.int32(), nullable=False),
            pa.field("datetime_subcode", pa.int32()),
            pa.field("num_prec_radix", pa.int32()),
            pa.field("interval_precision", pa.int32())
        ])


class FlightSQLMessageHandler:
    """Handles FlightSQL protobuf message parsing and creation."""

    @staticmethod
    def parse_command_statement_query(command_bytes: bytes) -> Optional[str]:
        """
        Parse a CommandStatementQuery message and extract the SQL query.
        
        This matches the C++ implementation's handling of statement queries.
        """
        try:
            # Handle protobuf encoding
            if len(command_bytes) > 2 and command_bytes[0] == 0x0A:
                # This is a protobuf message with field 1 (string)
                length = command_bytes[1]
                if len(command_bytes) >= 2 + length:
                    sql = command_bytes[2:2+length].decode("utf-8")
                    logger.debug(f"Parsed CommandStatementQuery SQL: {sql}")
                    return sql
            
            # Try direct UTF-8 decode as fallback
            sql = command_bytes.decode("utf-8")
            logger.debug(f"Parsed CommandStatementQuery SQL (direct): {sql}")
            return sql
        except (UnicodeDecodeError, IndexError) as e:
            logger.warning(f"Could not parse CommandStatementQuery: {e}")
            return None

    @staticmethod
    def encode_transaction_query(query: str, transaction_id: str = "") -> bytes:
        """
        Encode a query with transaction ID, matching C++ implementation.
        """
        if transaction_id:
            return f"{transaction_id}:{query}".encode("utf-8")
        return query.encode("utf-8")
    
    @staticmethod
    def decode_transaction_query(ticket: bytes) -> Tuple[str, str]:
        """
        Decode a query with transaction ID, matching C++ implementation.
        """
        ticket_str = ticket.decode("utf-8")
        divider = ticket_str.find(":")
        if divider != -1:
            transaction_id = ticket_str[:divider]
            query = ticket_str[divider+1:]
            return query, transaction_id
        return ticket_str, ""

    @staticmethod
    def create_flight_info_for_query(
        query: str, schema: pa.Schema, location: pf.Location, 
        transaction_id: str = ""
    ) -> pf.FlightInfo:
        """Create FlightInfo for a SQL query with optional transaction."""
        # Encode query with transaction ID
        ticket_data = FlightSQLMessageHandler.encode_transaction_query(
            query, transaction_id
        )
        ticket = pf.Ticket(ticket_data)

        # Create endpoint
        endpoint = pf.FlightEndpoint(ticket=ticket, locations=[location])

        # Create flight descriptor for the query
        descriptor = pf.FlightDescriptor.for_command(query.encode("utf-8"))

        return pf.FlightInfo(
            schema=schema,
            descriptor=descriptor,
            endpoints=[endpoint],
            total_records=-1,  # Unknown
            total_bytes=-1,  # Unknown
        )


class FlightSQLServer:
    """FlightSQL protocol support matching C++ implementation."""

    def __init__(self, backend, config):
        """Initialize FlightSQL support."""
        self.backend = backend
        self.config = config
        self.message_handler = FlightSQLMessageHandler()
        self.prepared_statements: Dict[str, Any] = {}
        self.open_transactions: Dict[str, Any] = {}

    def prepare_query_for_get_tables(self, command) -> str:
        """
        Prepare SQL query for GetTables command, matching C++ implementation.
        """
        parts = ["SELECT 'main' as catalog_name, null as db_schema_name, name as table_name, type as table_type FROM sqlite_master where 1=1"]
        
        if hasattr(command, 'catalog') and command.catalog:
            parts.append(f" and catalog_name='{command.catalog}'")
        
        if hasattr(command, 'db_schema_filter_pattern') and command.db_schema_filter_pattern:
            parts.append(f" and db_schema_name LIKE '{command.db_schema_filter_pattern}'")
        
        if hasattr(command, 'table_name_filter_pattern') and command.table_name_filter_pattern:
            parts.append(f" and table_name LIKE '{command.table_name_filter_pattern}'")
        
        if hasattr(command, 'table_types') and command.table_types:
            types_str = ",".join([f"'{t}'" for t in command.table_types])
            parts.append(f" and table_type IN ({types_str})")
        
        parts.append(" order by table_name")
        return "".join(parts)

    def prepare_query_for_get_imported_or_exported_keys(self, filter_clause: str) -> str:
        """
        Prepare SQL query for imported/exported keys, matching C++ implementation.
        """
        return f"""SELECT * FROM (SELECT NULL AS pk_catalog_name,
    NULL AS pk_db_schema_name,
    p."table" AS pk_table_name,
    p."to" AS pk_column_name,
    NULL AS fk_catalog_name,
    NULL AS fk_db_schema_name,
    m.name AS fk_table_name,
    p."from" AS fk_column_name,
    p.seq AS key_sequence,
    NULL AS pk_key_name,
    NULL AS fk_key_name,
    CASE
        WHEN p.on_update = 'CASCADE' THEN 0
        WHEN p.on_update = 'RESTRICT' THEN 1
        WHEN p.on_update = 'SET NULL' THEN 2
        WHEN p.on_update = 'NO ACTION' THEN 3
        WHEN p.on_update = 'SET DEFAULT' THEN 4
    END AS update_rule,
    CASE
        WHEN p.on_delete = 'CASCADE' THEN 0
        WHEN p.on_delete = 'RESTRICT' THEN 1
        WHEN p.on_delete = 'SET NULL' THEN 2
        WHEN p.on_delete = 'NO ACTION' THEN 3
        WHEN p.on_delete = 'SET DEFAULT' THEN 4
    END AS delete_rule
  FROM sqlite_master m
  JOIN pragma_foreign_key_list(m.name) p ON m.name != p."table"
  WHERE m.type = 'table') WHERE {filter_clause} ORDER BY
  pk_catalog_name, pk_db_schema_name, pk_table_name, pk_key_name, key_sequence"""

    def handle_flightsql_action(
        self, action_type: str, action_body: bytes
    ) -> pf.Result:
        """Handle FlightSQL-specific actions."""
        logger.debug(f"Handling FlightSQL action: {action_type}")

        # Match C++ implementation action handling
        if action_type == FlightSQLCommands.ACTION_CREATE_PREPARED_STATEMENT:
            return self._handle_create_prepared_statement(action_body)
        elif action_type == FlightSQLCommands.ACTION_CLOSE_PREPARED_STATEMENT:
            return self._handle_close_prepared_statement(action_body)
        elif action_type == FlightSQLCommands.ACTION_BEGIN_TRANSACTION:
            return self._handle_begin_transaction(action_body)
        elif action_type == FlightSQLCommands.ACTION_END_TRANSACTION:
            return self._handle_end_transaction(action_body)
        
        # Legacy command handling
        if action_type == FlightSQLCommands.COMMAND_GET_CATALOGS:
            return self._handle_get_catalogs_action()
        elif action_type == FlightSQLCommands.COMMAND_GET_SCHEMAS:
            return self._handle_get_schemas_action(action_body)
        elif action_type == FlightSQLCommands.COMMAND_GET_TABLES:
            return self._handle_get_tables_action(action_body)
        elif action_type == FlightSQLCommands.COMMAND_GET_TABLE_TYPES:
            return self._handle_get_table_types_action()
        else:
            logger.warning(f"Unsupported FlightSQL action: {action_type}")
            return pf.Result(pa.py_buffer(b""))

    def _handle_create_prepared_statement(self, action_body: bytes) -> pf.Result:
        """Handle CreatePreparedStatement action."""
        try:
            # Parse request (simplified - full implementation would use protobuf)
            query = action_body.decode("utf-8")
            
            # Generate random handle like C++ implementation
            import random
            import string
            handle = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
            
            # Store prepared statement
            self.prepared_statements[handle] = {
                'query': query,
                'parameters': []
            }
            
            # Return handle
            return pf.Result(pa.py_buffer(handle.encode("utf-8")))
        except Exception as e:
            logger.error(f"Error creating prepared statement: {e}")
            return pf.Result(pa.py_buffer(b""))

    def _handle_close_prepared_statement(self, action_body: bytes) -> pf.Result:
        """Handle ClosePreparedStatement action."""
        try:
            handle = action_body.decode("utf-8")
            if handle in self.prepared_statements:
                del self.prepared_statements[handle]
            return pf.Result(pa.py_buffer(b"OK"))
        except Exception as e:
            logger.error(f"Error closing prepared statement: {e}")
            return pf.Result(pa.py_buffer(b""))

    def _handle_begin_transaction(self, action_body: bytes) -> pf.Result:
        """Handle BeginTransaction action."""
        try:
            # Generate transaction ID like C++ implementation
            import random
            import string
            transaction_id = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
            
            # Store transaction
            self.open_transactions[transaction_id] = {
                'started': True
            }
            
            return pf.Result(pa.py_buffer(transaction_id.encode("utf-8")))
        except Exception as e:
            logger.error(f"Error beginning transaction: {e}")
            return pf.Result(pa.py_buffer(b""))

    def _handle_end_transaction(self, action_body: bytes) -> pf.Result:
        """Handle EndTransaction action."""
        try:
            # Parse request to get transaction ID and action
            # Simplified - full implementation would use protobuf
            parts = action_body.decode("utf-8").split(":")
            if len(parts) >= 2:
                transaction_id = parts[0]
                # action = parts[1]  # "COMMIT" or "ROLLBACK" - not used currently
                
                if transaction_id in self.open_transactions:
                    del self.open_transactions[transaction_id]
                    
            return pf.Result(pa.py_buffer(b"OK"))
        except Exception as e:
            logger.error(f"Error ending transaction: {e}")
            return pf.Result(pa.py_buffer(b""))

    def _handle_get_catalogs_action(self) -> pf.Result:
        """Handle CommandGetCatalogs action matching C++ implementation."""
        try:
            # Match C++ implementation - return only "main"
            catalog_data = pa.table({
                "catalog_name": ["main"]
            })

            # Serialize to IPC format
            import io
            buffer = io.BytesIO()
            with pa.ipc.new_stream(buffer, catalog_data.schema) as writer:
                writer.write_table(catalog_data)

            return pf.Result(pa.py_buffer(buffer.getvalue()))
        except Exception as e:
            logger.error(f"Error in get_catalogs: {e}")
            return pf.Result(pa.py_buffer(b""))

    def _handle_get_schemas_action(self, action_body: bytes) -> pf.Result:
        """Handle CommandGetSchemas action matching C++ implementation."""
        try:
            # SQLite doesn't support schemas, return single unnamed schema like C++
            schema_data = pa.table({
                "catalog_name": ["main"],
                "db_schema_name": [None]
            })

            # Serialize to IPC format
            import io
            buffer = io.BytesIO()
            with pa.ipc.new_stream(buffer, schema_data.schema) as writer:
                writer.write_table(schema_data)

            return pf.Result(pa.py_buffer(buffer.getvalue()))
        except Exception as e:
            logger.error(f"Error in get_schemas: {e}")
            return pf.Result(pa.py_buffer(b""))

    def _handle_get_tables_action(self, action_body: bytes) -> pf.Result:
        """Handle CommandGetTables action."""
        try:
            # Get table information from backend
            tables = []
            if hasattr(self.backend, "get_tables"):
                table_info = self.backend.get_tables()
                for table in table_info:
                    if isinstance(table, tuple) and len(table) >= 4:
                        tables.append(
                            {
                                "catalog_name": table[0] or "main",
                                "schema_name": table[1] or "main",
                                "table_name": table[2],
                                "table_type": table[3] or "TABLE",
                            }
                        )

            if not tables:
                # Default empty response
                tables = []

            # Create Arrow table
            if tables:
                table_data = pa.table(
                    {
                        "catalog_name": [t["catalog_name"] for t in tables],
                        "schema_name": [t["schema_name"] for t in tables],
                        "table_name": [t["table_name"] for t in tables],
                        "table_type": [t["table_type"] for t in tables],
                    }
                )
            else:
                # Empty table with correct schema
                table_data = pa.table(
                    {
                        "catalog_name": pa.array([], type=pa.string()),
                        "schema_name": pa.array([], type=pa.string()),
                        "table_name": pa.array([], type=pa.string()),
                        "table_type": pa.array([], type=pa.string()),
                    }
                )

            # Serialize to IPC format
            import io

            buffer = io.BytesIO()
            with pa.ipc.new_stream(buffer, table_data.schema) as writer:
                writer.write_table(table_data)

            return pf.Result(pa.py_buffer(buffer.getvalue()))
        except Exception as e:
            logger.error(f"Error in get_tables: {e}")
            return pf.Result(pa.py_buffer(b""))

    def _handle_get_table_types_action(self) -> pf.Result:
        """Handle CommandGetTableTypes action."""
        try:
            # Standard table types
            table_types = ["TABLE", "VIEW", "SYSTEM TABLE"]

            # Create Arrow table
            table_data = pa.table({"table_type": table_types})

            # Serialize to IPC format
            import io

            buffer = io.BytesIO()
            with pa.ipc.new_stream(buffer, table_data.schema) as writer:
                writer.write_table(table_data)

            return pf.Result(pa.py_buffer(buffer.getvalue()))
        except Exception as e:
            logger.error(f"Error in get_table_types: {e}")
            return pf.Result(pa.py_buffer(b""))


# Command classes matching C++ protobuf definitions
class CommandGetCatalogs:
    def Unpack(self, any_message):
        pass


class CommandGetDbSchemas:
    def __init__(self):
        self.catalog = None
        self.db_schema_filter_pattern = None

    def Unpack(self, any_message):
        pass


class CommandGetTables:
    def __init__(self):
        self.catalog = None
        self.db_schema_filter_pattern = None
        self.table_name_filter_pattern = None
        self.table_types = []
        self.include_schema = False

    def Unpack(self, any_message):
        pass


class CommandGetTableTypes:
    def Unpack(self, any_message):
        pass


class CommandGetSqlInfo:
    def __init__(self):
        self.info = []

    def Unpack(self, any_message):
        pass


class CommandStatementQuery:
    def __init__(self):
        self.query = ""
        self.transaction_id = ""

    def Unpack(self, any_message):
        value = any_message.value
        if value and len(value) > 2:
            # Handle protobuf encoding
            if value[0] == 0x0A:  # Field 1, string type
                length = value[1]
                if len(value) >= 2 + length:
                    self.query = value[2:2+length].decode("utf-8")
            
            # Check for transaction_id field (field 2)
            pos = 2 + (value[1] if value[0] == 0x0A else 0)
            if pos < len(value) and value[pos] == 0x12:  # Field 2, string type
                length = value[pos + 1]
                if len(value) >= pos + 2 + length:
                    self.transaction_id = value[pos+2:pos+2+length].decode("utf-8")


class CommandStatementUpdate:
    def __init__(self):
        self.query = ""
        self.transaction_id = ""

    def Unpack(self, any_message):
        # Similar to CommandStatementQuery
        value = any_message.value
        if value and len(value) > 2:
            if value[0] == 0x0A:
                length = value[1]
                if len(value) >= 2 + length:
                    self.query = value[2:2+length].decode("utf-8")


class PreparedStatementQuery:
    def __init__(self):
        self.prepared_statement_handle = b""

    def Unpack(self, any_message):
        value = any_message.value
        if value and len(value) > 2:
            if value[0] == 0x0A:  # Field 1, bytes type
                length = value[1]
                if len(value) >= 2 + length:
                    self.prepared_statement_handle = value[2:2+length]


class PreparedStatementUpdate:
    def __init__(self):
        self.prepared_statement_handle = b""

    def Unpack(self, any_message):
        # Similar to PreparedStatementQuery
        value = any_message.value
        if value and len(value) > 2:
            if value[0] == 0x0A:
                length = value[1]
                if len(value) >= 2 + length:
                    self.prepared_statement_handle = value[2:2+length]


class ActionCreatePreparedStatementRequest:
    def __init__(self):
        self.query = ""
        self.transaction_id = ""

    def Unpack(self, any_message):
        # Similar parsing to CommandStatementQuery
        pass


class ActionClosePreparedStatementRequest:
    def __init__(self):
        self.prepared_statement_handle = ""

    def Unpack(self, any_message):
        pass


class ActionBeginTransactionRequest:
    def Unpack(self, any_message):
        pass


class ActionEndTransactionRequest:
    def __init__(self):
        self.transaction_id = ""
        self.action = 0  # 0 = UNSPECIFIED, 1 = COMMIT, 2 = ROLLBACK

    def Unpack(self, any_message):
        pass

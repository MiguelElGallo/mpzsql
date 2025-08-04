"""
Minimal working FlightSQL server implementation.

This implements the absolute minimum needed to support JDBC clients
by providing proper FlightSQL method implementations.

**THIS IS THE ACTIVE IMPLEMENTATION** used by MPZSQLServer in server.py.
"""

# Remove the incorrect import
# import pyarrow.flight.sql as flight_sql
import logging
import threading
import time
import traceback
import uuid
from typing import Any, Dict, Iterator, List, Optional

import pyarrow as pa
import pyarrow.flight as pf  # keep original alias for pf.<...>

from .protobuf import (
    ActionBeginTransactionRequest,
    ActionClosePreparedStatementRequest,
    ActionCreatePreparedStatementRequest,
    ActionEndTransactionRequest,
    CommandGetCatalogs,
    CommandGetColumns,
    CommandGetDbSchemas,
    CommandGetSqlInfo,
    CommandGetTables,
    CommandGetTableTypes,
    CommandPreparedStatementQuery,
    CommandPreparedStatementUpdate,
    CommandStatementQuery,
    CommandStatementUpdate,
    DoPutUpdateResult,
    FlightSQLProtobuf,
    parse_any_command,
)
from ..logfire_config import get_actions_logger, get_routing_logger

# We now have both aliases available
from ..security import (
    BearerAuthServerMiddlewareFactory,
    HeaderAuthServerMiddlewareFactory,
    NoOpAuthHandler,
    TLSCertificateLoader,
)

# Initialize logfire loggers
actions_logger = get_actions_logger()
routing_logger = get_routing_logger()

# Keep legacy file logging for backward compatibility
# Configure detailed actions logger
actions_log = logging.getLogger("actions")
actions_log.setLevel(logging.INFO)
actions_handler = logging.FileHandler("actions.log", mode="w")
actions_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
actions_handler.setLevel(logging.INFO)
actions_log.addHandler(actions_handler)
actions_log.propagate = False  # Prevent propagation to root logger

# Configure routing logger
routing_log = logging.getLogger("server_routing")
routing_log.setLevel(logging.DEBUG)
routing_fh = logging.FileHandler("server_routing.log", mode="w")
routing_fh.setLevel(logging.DEBUG)
routing_formatter = logging.Formatter("%(asctime)s - %(message)s")
routing_fh.setFormatter(routing_formatter)
routing_log.addHandler(routing_fh)
routing_log.propagate = False

# Test both logger systems
actions_logger.info("Actions logfire logger initialized")
routing_logger.info("Routing logfire logger initialized")
actions_log.info("Actions logger initialized")
actions_handler.flush()  # Force flush
routing_log.info("Routing logger initialized")

# Debug FlightSQLProtobuf import
actions_logger.info(
    "FlightSQLProtobuf import debug",
    imported=str(FlightSQLProtobuf),
    methods=[m for m in dir(FlightSQLProtobuf) if not m.startswith("_")],
    has_parse_command_get_db_schemas=hasattr(
        FlightSQLProtobuf, "parse_command_get_db_schemas"
    ),
)
actions_log.info(f"FlightSQLProtobuf imported: {FlightSQLProtobuf}")
actions_log.info(
    f"FlightSQLProtobuf methods: {[m for m in dir(FlightSQLProtobuf) if not m.startswith('_')]}"
)
actions_log.info(
    f"Has parse_command_get_db_schemas: {hasattr(FlightSQLProtobuf, 'parse_command_get_db_schemas')}"
)


# SQL Info enums (matching Examples implementation)
class SqlInfo:
    FLIGHT_SQL_SERVER_NAME = 0
    FLIGHT_SQL_SERVER_VERSION = 1
    FLIGHT_SQL_SERVER_ARROW_VERSION = 2
    FLIGHT_SQL_SERVER_READ_ONLY = 3
    FLIGHT_SQL_SERVER_SQL = 4
    FLIGHT_SQL_SERVER_SUBSTRAIT = 5
    FLIGHT_SQL_SERVER_TRANSACTION = 6
    FLIGHT_SQL_SERVER_CANCEL = 7
    SQL_DDL_CATALOG = 500
    SQL_DDL_SCHEMA = 501
    SQL_DDL_TABLE = 502
    SQL_IDENTIFIER_CASE = 503
    SQL_IDENTIFIER_QUOTE_CHAR = 504
    SQL_QUOTED_IDENTIFIER_CASE = 505
    SQL_ALL_TABLES_ARE_SELECTABLE = 506
    SQL_NULL_ORDERING = 507


class SqlSupportedTransaction:
    SQL_SUPPORTED_TRANSACTION_NONE = 0
    SQL_SUPPORTED_TRANSACTION_TRANSACTION = 1
    SQL_SUPPORTED_TRANSACTION_SAVEPOINT = 2


class SqlSupportedCaseSensitivity:
    SQL_CASE_SENSITIVITY_UNKNOWN = 0
    SQL_CASE_SENSITIVITY_CASE_INSENSITIVE = 1
    SQL_CASE_SENSITIVITY_UPPERCASE = 2
    SQL_CASE_SENSITIVITY_LOWERCASE = 3


class SqlNullOrdering:
    SQL_NULLS_SORTED_HIGH = 0
    SQL_NULLS_SORTED_LOW = 1
    SQL_NULLS_SORTED_AT_START = 2
    SQL_NULLS_SORTED_AT_END = 3


# Set up routing logger
routing_log = logging.getLogger("server_routing")
routing_log.setLevel(logging.DEBUG)

# Create a file handler for the routing logger
routing_fh = logging.FileHandler("server_routing.log", mode="w")
routing_fh.setLevel(logging.DEBUG)

# Create a formatter and set it for the handler
routing_formatter = logging.Formatter("%(asctime)s - %(message)s")
routing_fh.setFormatter(routing_formatter)

# Add the handler to the logger
routing_log.addHandler(routing_fh)

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

logger = logging.getLogger(__name__)


class MinimalFlightSQLServer(pf.FlightServerBase):
    """
    Minimal FlightSQL server that inherits from FlightServerBase
    and implements the required methods for JDBC compatibility.
    """

    def __init__(
        self,
        backend,
        config,
        location: pf.Location,
        advertised_location: pf.Location = None,
        **kwargs,
    ):
        """Initialize the minimal FlightSQL server."""
        # Setup authentication using Examples server pattern: NoOpAuthHandler + middleware
        auth_handler = NoOpAuthHandler()
        middleware = {}

        if config.is_auth_enabled:
            # Create middleware factories following Examples implementation pattern
            header_middleware = HeaderAuthServerMiddlewareFactory(
                config.username, config.password, config.secret_key
            )
            bearer_middleware = BearerAuthServerMiddlewareFactory(config.secret_key)

            # Add middleware in the same order as Examples server
            middleware = {
                "header-auth-server": header_middleware,
                "bearer-auth-server": bearer_middleware,
            }

            logger.info(f"Authentication enabled for user: {config.username}")
        else:
            logger.info("Authentication disabled - server is open to all")

        # Configure TLS options if enabled (following Examples server pattern)
        tls_certificates = None
        root_certificates = None
        verify_client = False

        if config.is_tls_enabled or config.is_mtls_enabled:
            try:
                tls_certificates, root_certificates, verify_client = (
                    TLSCertificateLoader.configure_tls_options(config)
                )
            except Exception as e:
                logger.error(f"TLS configuration failed: {e}")
                raise ValueError(f"TLS configuration failed: {e}")

        # Pass auth_handler, middleware, and TLS options to parent constructor
        # PyArrow Flight server expects TLS to be configured via specific parameters
        if tls_certificates or root_certificates or verify_client:
            super().__init__(
                location,
                auth_handler=auth_handler,
                middleware=middleware,
                tls_certificates=tls_certificates,
                root_certificates=root_certificates,
                verify_client=verify_client,
                **kwargs,
            )
        else:
            super().__init__(
                location, auth_handler=auth_handler, middleware=middleware, **kwargs
            )

        self.location = location
        self.advertised_location = advertised_location or location
        self.backend = backend
        self.config = config
        self.prepared_statements: Dict[str, Dict[str, Any]] = {}
        # Add transaction and session management like Examples implementation
        self.open_transactions: Dict[str, str] = {}  # transaction_id -> connection_id
        self.open_sessions: Dict[str, Any] = {}  # session_id -> connection
        self._mutex = threading.Lock()  # Similar to Examples mutex
        self._transaction_counter = 0

        # Test actions log
        actions_log.info("MinimalFlightSQLServer initialized")
        print("DEBUG: actions_log test message sent")

    def list_actions(self, context: pf.ServerCallContext) -> Iterator[pf.ActionType]:
        """List available FlightSQL actions."""
        actions = [
            pf.ActionType("CreatePreparedStatement", "Create a prepared statement"),
            pf.ActionType("ClosePreparedStatement", "Close a prepared statement"),
            # Add transaction actions like Examples implementation
            pf.ActionType("BeginTransaction", "Begin a transaction"),
            pf.ActionType("EndTransaction", "End a transaction"),
            # Add session management actions (FlightSQL standard)
            pf.ActionType("CloseSession", "Close and invalidate the current session context"),
        ]
        return iter(actions)

    def do_action(
        self, context: pf.ServerCallContext, action: pf.Action
    ) -> Iterator[pf.Result]:
        """Execute FlightSQL actions."""
        # Add comprehensive debug logging
        actions_log.info(f"=== do_action ENTRY === timestamp: {time.time()}")
        actions_log.info(f"do_action called: {action.type}")
        actions_handler.flush()

        action_type = action.type
        action_body = action.body.to_pybytes() if action.body else b""
        logger.info(f"do_action: {action_type} ({len(action_body)} bytes)")
        print(f"SERVER: do_action called: {action_type} ({len(action_body)} bytes)")

        # Add debug logging to routing log
        routing_log.info(f"do_action called: {action_type} ({len(action_body)} bytes)")

        if action_type == "CreatePreparedStatement":
            actions_log.info("1. Receiving command: Create Prepared Statement")
            actions_handler.flush()
            routing_log.info("Creating prepared statement")
            yield self._create_prepared_statement(action_body)
        elif action_type == "ClosePreparedStatement":
            actions_log.info("1. Receiving command: Close Prepared Statement")
            actions_handler.flush()
            routing_log.info("Closing prepared statement")
            yield self._close_prepared_statement(action_body)
        elif action_type == "BeginTransaction":
            actions_log.info("1. Receiving command: Begin Transaction")
            actions_handler.flush()
            yield self._begin_transaction(action_body)
        elif action_type == "EndTransaction":
            actions_log.info("1. Receiving command: End Transaction")
            actions_handler.flush()
            yield self._end_transaction(action_body)
        elif action_type == "CloseSession":
            actions_log.info("1. Receiving command: Close Session")
            actions_handler.flush()
            yield self._close_session(action_body)
        else:
            actions_log.info(f"1. Receiving command: Unknown Action - {action_type}")
            actions_handler.flush()
            raise NotImplementedError(f"Action {action_type} not implemented.")

    def _begin_transaction(self, action_body: bytes) -> pf.Result:
        """Handle BeginTransaction action (matching Examples implementation)."""
        try:
            request = ActionBeginTransactionRequest()
            request.ParseFromString(action_body)

            with self._mutex:
                self._transaction_counter += 1
                transaction_id = f"txn_{self._transaction_counter}"

                # In Examples, they create a new connection for the transaction
                # Here we'll track the transaction state
                self.open_transactions[transaction_id] = "active"

                logger.info(f"Beginning transaction: {transaction_id}")
                print(f"SERVER: Beginning transaction: {transaction_id}")

            # Return transaction ID as result
            response_bytes = transaction_id.encode("utf-8")
            return pf.Result(pa.py_buffer(response_bytes))

        except Exception as e:
            logger.error(f"Error beginning transaction: {e}", exc_info=True)
            raise

    def _end_transaction(self, action_body: bytes) -> pf.Result:
        """Handle EndTransaction action (matching Examples implementation)."""
        try:
            request = ActionEndTransactionRequest()
            request.ParseFromString(action_body)

            transaction_id = request.transaction_id
            action = request.action  # COMMIT or ROLLBACK

            with self._mutex:
                if transaction_id not in self.open_transactions:
                    raise ValueError(f"Unknown transaction ID: {transaction_id}")

                # Execute commit or rollback
                if action == ActionEndTransactionRequest.COMMIT:
                    logger.info(f"Committing transaction: {transaction_id}")
                    print(f"SERVER: Committing transaction: {transaction_id}")
                    # Here you would execute COMMIT on the backend
                else:
                    logger.info(f"Rolling back transaction: {transaction_id}")
                    print(f"SERVER: Rolling back transaction: {transaction_id}")
                    # Here you would execute ROLLBACK on the backend

                del self.open_transactions[transaction_id]

            return pf.Result(pa.py_buffer(b""))

        except Exception as e:
            logger.error(f"Error ending transaction: {e}", exc_info=True)
            raise

    def _close_session(self, action_body: bytes) -> pf.Result:
        """Handle CloseSession action (FlightSQL standard session management)."""
        try:
            # CloseSession typically receives no parameters (0 bytes as seen in logs)
            # This is a session cleanup action as per FlightSQL specification
            
            logger.info("Closing session")
            print("SERVER: Closing session")
            
            # Log session closure for actions.log
            actions_log.info("2. Command arguments: (none - session cleanup)")
            actions_log.info("3. Command sent to backend: session cleanup")
            
            with self._mutex:
                # Clean up any session-specific state
                # For a stateless server, this is mostly a no-op, but we can:
                # 1. Clean up any remaining prepared statements (defensive cleanup)
                # 2. Clean up any open transactions (defensive cleanup)
                # 3. Clean up session-specific resources
                
                session_cleanup_count = 0
                
                # Clean up any orphaned prepared statements
                if self.prepared_statements:
                    session_cleanup_count += len(self.prepared_statements)
                    self.prepared_statements.clear()
                    logger.info(f"Cleaned up {session_cleanup_count} prepared statements during session close")
                
                # Clean up any orphaned transactions  
                if self.open_transactions:
                    transaction_cleanup_count = len(self.open_transactions)
                    self.open_transactions.clear()
                    logger.info(f"Cleaned up {transaction_cleanup_count} transactions during session close")
                    session_cleanup_count += transaction_cleanup_count
                
                # Clean up any session-specific data
                if self.open_sessions:
                    session_count = len(self.open_sessions)
                    self.open_sessions.clear()
                    logger.info(f"Cleaned up {session_count} session entries during session close")
                    session_cleanup_count += session_count
                
            actions_log.info(f"4. Reply by backend: Session closed, cleaned up {session_cleanup_count} resources")
            actions_log.info("5. Reply sent back: CloseSession completed successfully")
            
            logger.info("Session closed successfully")
            print("SERVER: Session closed successfully")
            
            # Return empty result (standard for CloseSession)
            return pf.Result(pa.py_buffer(b""))
            
        except Exception as e:
            logger.error(f"Error closing session: {e}", exc_info=True)
            actions_log.info(f"4. Reply by backend: ERROR - {e}")
            actions_log.info("5. Reply sent back: CloseSession failed")
            raise

    def get_flight_info(
        self, context: pf.ServerCallContext, descriptor: pf.FlightDescriptor
    ) -> pf.FlightInfo:
        """Get flight info for queries."""
        routing_log.info(
            f"GetFlightInfo called with descriptor_type: {descriptor.descriptor_type}"
        )
        routing_log.info(
            f"Command bytes length: {len(descriptor.command) if descriptor.command else 0}"
        )

        logger.info(
            f"GetFlightInfo called with descriptor_type: {descriptor.descriptor_type}"
        )
        print(
            "SERVER: GetFlightInfo called with descriptor_type: "
            f"{descriptor.descriptor_type}"
        )

        # Handle both CMD (FlightSQL) and PATH (raw Flight) descriptors
        if descriptor.descriptor_type == pf.DescriptorType.CMD:
            # Existing FlightSQL command handling
            return self._handle_flightsql_get_flight_info(context, descriptor)
        elif descriptor.descriptor_type == pf.DescriptorType.PATH:
            # New: Handle raw Flight path descriptors for table info
            return self._handle_path_get_flight_info(context, descriptor)
        else:
            raise NotImplementedError(f"Unsupported descriptor type: {descriptor.descriptor_type}")

    def _handle_flightsql_get_flight_info(self, context: pf.ServerCallContext, descriptor: pf.FlightDescriptor) -> pf.FlightInfo:
        """Handle FlightSQL get_flight_info - EXISTING FUNCTIONALITY UNCHANGED"""
        command_bytes = descriptor.command
        logger.info(f"GetFlightInfo command length: {len(command_bytes)} bytes")
        print(f"SERVER: GetFlightInfo command length: {len(command_bytes)} bytes")

        routing_log.info(f"Command bytes: {command_bytes.hex()}")

        any_command = parse_any_command(command_bytes)
        if not any_command:
            raise ValueError("Failed to parse command from descriptor.")

        command_type_url = any_command.type_url
        routing_log.info(f"Command type URL: {command_type_url}")
        protobuf_log.info(f"Parsing command with type_url: {command_type_url}")
        protobuf_log.info(f"Command value bytes: {any_command.value.hex()}")
        logger.info(f"Successfully parsed command with type URL: {command_type_url}")
        print(f"SERVER: Successfully parsed command with type URL: {command_type_url}")
        print("SERVER: DEBUG - About to handle command type")

        # Add immediate debugging for the crash
        try:
            print("SERVER: DEBUG - Inside try block for command type handling")
            print(f"SERVER: DEBUG - Command type URL is: {repr(command_type_url)}")

            # Check for prepared statement query specifically to prevent crash
            if "CommandPreparedStatementQuery" in command_type_url:
                print("SERVER: DEBUG - Detected CommandPreparedStatementQuery")
                # Handle the prepared statement query with defensive programming
                try:
                    command = self._parse_prepared_statement_query(any_command)
                    return self._get_flight_info_prepared_statement(descriptor, command)
                except Exception as ps_e:
                    print(
                        f"SERVER: ERROR - Exception in prepared statement handling: {ps_e}"
                    )

                    traceback.print_exc()
                    # Return error schema instead of crashing
                    error_schema = pa.schema([pa.field("error", pa.string())])
                    return self._get_flight_info_for_command(descriptor, error_schema)

        except Exception as debug_e:
            print(f"SERVER: CRITICAL - Exception in debug code: {debug_e}")

            traceback.print_exc()
            # Return error schema to prevent complete crash
            error_schema = pa.schema([pa.field("error", pa.string())])
            return self._get_flight_info_for_command(descriptor, error_schema)

        if command_type_url == FlightSQLProtobuf.COMMAND_STATEMENT_QUERY_TYPE_URL:
            print("SERVER: DEBUG - Handling COMMAND_STATEMENT_QUERY")
            command = self._parse_statement_query(any_command)
            return self._get_flight_info_statement(descriptor, command)
        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_CATALOGS_TYPE_URL:
            print("SERVER: DEBUG - Handling COMMAND_GET_CATALOGS")
            command = CommandGetCatalogs()
            return self._get_flight_info_catalogs(descriptor, command)
        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_DB_SCHEMAS_TYPE_URL:
            print("SERVER: DEBUG - Handling COMMAND_GET_DB_SCHEMAS")
            command = self._parse_get_db_schemas(any_command)
            return self._get_flight_info_schemas(descriptor, command)
        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_TABLES_TYPE_URL:
            print("SERVER: DEBUG - Handling COMMAND_GET_TABLES")
            command = self._parse_get_tables(any_command)
            return self._get_flight_info_tables(descriptor, command)
        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_TABLE_TYPES_TYPE_URL:
            command = CommandGetTableTypes()
            return self._get_flight_info_table_types(descriptor, command)
        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_COLUMNS_TYPE_URL:
            print("SERVER: DEBUG - Handling COMMAND_GET_COLUMNS")
            command = self._parse_get_columns(any_command)
            return self._get_flight_info_columns(descriptor, command)
        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_SQL_INFO_TYPE_URL:
            command = self._parse_get_sql_info(any_command)
            return self._get_flight_info_sql_info(descriptor, command)
        elif (
            command_type_url
            == FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_QUERY_TYPE_URL
        ):
            print(
                "SERVER: DEBUG - Handling COMMAND_PREPARED_STATEMENT_QUERY in get_flight_info"
            )
            try:
                print("SERVER: DEBUG - About to parse prepared statement query")
                command = self._parse_prepared_statement_query(any_command)
                print("SERVER: DEBUG - Successfully parsed prepared statement query")
                print("SERVER: DEBUG - About to get flight info for prepared statement")
                result = self._get_flight_info_prepared_statement(descriptor, command)
                print(
                    "SERVER: DEBUG - Successfully got flight info for prepared statement"
                )
                return result
            except Exception as e:
                print(
                    f"SERVER: ERROR - Exception in get_flight_info for prepared statement: {e}"
                )
                actions_log.info(
                    f"DEBUG get_flight_info: Exception in prepared statement: {e}"
                )
                actions_handler.flush()

                traceback.print_exc()
                # Return a safe fallback response instead of crashing
                try:
                    schema = pa.schema([pa.field("error", pa.string())])
                    safe_ticket = f"ERROR: {str(e)}".encode("utf-8")
                    # Use the advertised location for the endpoint
                    endpoint = pf.FlightEndpoint(
                        ticket=pf.Ticket(safe_ticket),
                        locations=[self.advertised_location],
                    )
                    return pf.FlightInfo(
                        schema=schema,
                        descriptor=descriptor,
                        endpoints=[endpoint],
                        total_records=0,
                        total_bytes=0,
                    )
                except Exception as fallback_error:
                    print(
                        f"SERVER: CRITICAL ERROR - Even fallback failed: {fallback_error}"
                    )
                    raise e  # Re-raise the original exception
        else:
            raise NotImplementedError(f"Unsupported command type: {command_type_url}")

    def _handle_path_get_flight_info(self, context: pf.ServerCallContext, descriptor: pf.FlightDescriptor) -> pf.FlightInfo:
        """Handle raw Flight path descriptors for table info retrieval"""
        # Extract table name from path (same logic as in do_put)
        raw_table_name = descriptor.path[0] if descriptor.path else b"unknown_table"
        if isinstance(raw_table_name, bytes):
            raw_table_name = raw_table_name.decode('utf-8')
        raw_table_name = raw_table_name.strip('/')
        
        # Apply same table naming logic as in do_put
        if '.' not in raw_table_name:
            table_name = f"my_ducklake.main.{raw_table_name}"
        elif raw_table_name.startswith('my_ducklake.'):
            table_name = raw_table_name
        else:
            parts = raw_table_name.split('.')
            table_name = f"my_ducklake.main.{parts[-1]}"
        
        print(f"SERVER: PATH get_flight_info: '{raw_table_name}' → '{table_name}'")
        
        try:
            # Get the schema of the existing table
            schema = self.backend.get_table_schema(table_name)
            
            # Create a simple ticket with the table name
            ticket_bytes = table_name.encode('utf-8')
            endpoint = pf.FlightEndpoint(
                ticket=pf.Ticket(ticket_bytes),
                locations=[self.advertised_location]
            )
            
            # Get table row count for metadata
            try:
                row_count = self.backend.get_table_row_count(table_name)
            except Exception:
                row_count = -1  # Unknown
            
            return pf.FlightInfo(
                schema=schema,
                descriptor=descriptor,
                endpoints=[endpoint],
                total_records=row_count,
                total_bytes=-1  # Unknown
            )
        except Exception as e:
            print(f"SERVER: Error getting table info for {table_name}: {e}")
            # Return error schema
            error_schema = pa.schema([pa.field("error", pa.string())])
            ticket_bytes = f"ERROR: {str(e)}".encode('utf-8')
            endpoint = pf.FlightEndpoint(
                ticket=pf.Ticket(ticket_bytes),
                locations=[self.advertised_location]
            )
            return pf.FlightInfo(
                schema=error_schema,
                descriptor=descriptor,
                endpoints=[endpoint],
                total_records=0,
                total_bytes=0
            )

        command_bytes = descriptor.command
        logger.info(f"GetFlightInfo command length: {len(command_bytes)} bytes")
        print(f"SERVER: GetFlightInfo command length: {len(command_bytes)} bytes")

        routing_log.info(f"Command bytes: {command_bytes.hex()}")

        any_command = parse_any_command(command_bytes)
        if not any_command:
            raise ValueError("Failed to parse command from descriptor.")

        command_type_url = any_command.type_url
        routing_log.info(f"Command type URL: {command_type_url}")
        protobuf_log.info(f"Parsing command with type_url: {command_type_url}")
        protobuf_log.info(f"Command value bytes: {any_command.value.hex()}")
        logger.info(f"Successfully parsed command with type URL: {command_type_url}")
        print(f"SERVER: Successfully parsed command with type URL: {command_type_url}")
        print("SERVER: DEBUG - About to handle command type")

        # Add immediate debugging for the crash
        try:
            print("SERVER: DEBUG - Inside try block for command type handling")
            print(f"SERVER: DEBUG - Command type URL is: {repr(command_type_url)}")

            # Check for prepared statement query specifically to prevent crash
            if "CommandPreparedStatementQuery" in command_type_url:
                print("SERVER: DEBUG - Detected CommandPreparedStatementQuery")
                # Handle the prepared statement query with defensive programming
                try:
                    command = self._parse_prepared_statement_query(any_command)
                    return self._get_flight_info_prepared_statement(descriptor, command)
                except Exception as ps_e:
                    print(
                        f"SERVER: ERROR - Exception in prepared statement handling: {ps_e}"
                    )
                    import traceback

                    traceback.print_exc()
                    # Return error schema instead of crashing
                    error_schema = pa.schema([pa.field("error", pa.string())])
                    return self._get_flight_info_for_command(descriptor, error_schema)

        except Exception as debug_e:
            print(f"SERVER: CRITICAL - Exception in debug code: {debug_e}")
            import traceback

            traceback.print_exc()
            # Return error schema to prevent complete crash
            error_schema = pa.schema([pa.field("error", pa.string())])
            return self._get_flight_info_for_command(descriptor, error_schema)

        if command_type_url == FlightSQLProtobuf.COMMAND_STATEMENT_QUERY_TYPE_URL:
            print("SERVER: DEBUG - Handling COMMAND_STATEMENT_QUERY")
            command = self._parse_statement_query(any_command)
            return self._get_flight_info_statement(descriptor, command)
        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_CATALOGS_TYPE_URL:
            print("SERVER: DEBUG - Handling COMMAND_GET_CATALOGS")
            command = CommandGetCatalogs()
            return self._get_flight_info_catalogs(descriptor, command)
        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_DB_SCHEMAS_TYPE_URL:
            print("SERVER: DEBUG - Handling COMMAND_GET_DB_SCHEMAS")
            command = self._parse_get_db_schemas(any_command)
            return self._get_flight_info_schemas(descriptor, command)
        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_TABLES_TYPE_URL:
            print("SERVER: DEBUG - Handling COMMAND_GET_TABLES")
            command = self._parse_get_tables(any_command)
            return self._get_flight_info_tables(descriptor, command)
        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_TABLE_TYPES_TYPE_URL:
            command = CommandGetTableTypes()
            return self._get_flight_info_table_types(descriptor, command)
        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_COLUMNS_TYPE_URL:
            print("SERVER: DEBUG - Handling COMMAND_GET_COLUMNS")
            command = self._parse_get_columns(any_command)
            return self._get_flight_info_columns(descriptor, command)
        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_SQL_INFO_TYPE_URL:
            command = self._parse_get_sql_info(any_command)
            return self._get_flight_info_sql_info(descriptor, command)
        elif (
            command_type_url
            == FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_QUERY_TYPE_URL
        ):
            print(
                "SERVER: DEBUG - Handling COMMAND_PREPARED_STATEMENT_QUERY in get_flight_info"
            )
            try:
                print("SERVER: DEBUG - About to parse prepared statement query")
                command = self._parse_prepared_statement_query(any_command)
                print("SERVER: DEBUG - Successfully parsed prepared statement query")
                print("SERVER: DEBUG - About to get flight info for prepared statement")
                result = self._get_flight_info_prepared_statement(descriptor, command)
                print(
                    "SERVER: DEBUG - Successfully got flight info for prepared statement"
                )
                return result
            except Exception as e:
                print(
                    f"SERVER: ERROR - Exception in get_flight_info for prepared statement: {e}"
                )
                actions_log.info(
                    f"DEBUG get_flight_info: Exception in prepared statement: {e}"
                )
                actions_handler.flush()
                import traceback

                traceback.print_exc()
                # Return a safe fallback response instead of crashing
                try:
                    schema = pa.schema([pa.field("error", pa.string())])
                    safe_ticket = f"ERROR: {str(e)}".encode("utf-8")
                    # Use the advertised location for the endpoint
                    endpoint = pf.FlightEndpoint(
                        ticket=pf.Ticket(safe_ticket),
                        locations=[self.advertised_location],
                    )
                    return pf.FlightInfo(
                        schema=schema,
                        descriptor=descriptor,
                        endpoints=[endpoint],
                        total_records=0,
                        total_bytes=0,
                    )
                except Exception as fallback_error:
                    print(
                        f"SERVER: CRITICAL ERROR - Even fallback failed: {fallback_error}"
                    )
                    raise e  # Re-raise the original exception
        else:
            raise NotImplementedError(f"Unsupported command type: {command_type_url}")

    def do_get(
        self, context: pf.ServerCallContext, ticket: pf.Ticket
    ) -> pf.FlightDataStream:
        """Execute a query and return the results."""
        # Force immediate logging to debug missing logs
        actions_log.info(f"=== do_get ENTRY === timestamp: {time.time()}")
        actions_log.info(f"do_get called with ticket: {ticket.ticket.hex()}")
        actions_handler.flush()

        routing_log.info(f"do_get called with ticket: {ticket.ticket.hex()}")

        # Add debug logging
        actions_log.info(f"DEBUG do_get: Starting with ticket: {ticket.ticket.hex()}")
        actions_handler.flush()

        logger.info(f"DoGet called with ticket: {ticket.ticket}")
        print(f"SERVER: DoGet called with ticket: {ticket.ticket}")
        print("SERVER: DEBUG - do_get method was reached successfully")

        # Extract raw bytes from the ticket
        raw_ticket: bytes = (
            ticket.ticket.to_pybytes()
            if hasattr(ticket.ticket, "to_pybytes")
            else ticket.ticket
        )

        # ---------------------------------------------
        # 1) Try normal protobuf-based command tickets
        # ---------------------------------------------
        any_command = parse_any_command(raw_ticket)
        if any_command:
            command_type_url = any_command.type_url
            routing_log.info(f"do_get command type: {command_type_url}")
            protobuf_log.info(
                f"do_get parsing command with type_url: {command_type_url}"
            )
            protobuf_log.info(f"do_get command value bytes: {any_command.value.hex()}")

            # Add more debug logging
            actions_log.info(f"DEBUG do_get: Parsed command type: {command_type_url}")
            actions_handler.flush()

            # Route based on command type
            if command_type_url == FlightSQLProtobuf.COMMAND_STATEMENT_QUERY_TYPE_URL:
                routing_log.info("do_get routing to StatementQuery")
                query = FlightSQLProtobuf.parse_command_statement_query(
                    any_command.value
                )
                protobuf_log.info(f"Parsed StatementQuery: {query}")
                command = CommandStatementQuery()
                command.query = query or ""
                actions_log.info(f"DEBUG do_get: StatementQuery - {query}")
                actions_handler.flush()
                return self._do_get_statement(command)
            elif command_type_url == FlightSQLProtobuf.COMMAND_GET_CATALOGS_TYPE_URL:
                command = CommandGetCatalogs()
                return self._do_get_catalogs(command)
            elif command_type_url == FlightSQLProtobuf.COMMAND_GET_DB_SCHEMAS_TYPE_URL:
                command = self._parse_get_db_schemas(any_command)
                return self._do_get_schemas(command)
            elif command_type_url == FlightSQLProtobuf.COMMAND_GET_TABLES_TYPE_URL:
                command = self._parse_get_tables(any_command)
                return self._do_get_tables(command)
            elif command_type_url == FlightSQLProtobuf.COMMAND_GET_TABLE_TYPES_TYPE_URL:
                command = CommandGetTableTypes()
                return self._do_get_table_types(command)
            elif command_type_url == FlightSQLProtobuf.COMMAND_GET_COLUMNS_TYPE_URL:
                command = self._parse_get_columns(any_command)
                return self._do_get_columns(command)
            elif command_type_url == FlightSQLProtobuf.COMMAND_GET_SQL_INFO_TYPE_URL:
                command = self._parse_get_sql_info(any_command)
                return self._do_get_sql_info(command)
            elif (
                command_type_url
                == FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_QUERY_TYPE_URL
            ):
                # This is the 'DoGetPreparedStatement' execution path.
                # It's called by JDBC when a SELECT prepared statement is executed.
                print("SERVER: do_get: Handling COMMAND_PREPARED_STATEMENT_QUERY")
                actions_log.info(
                    "DEBUG do_get: Handling COMMAND_PREPARED_STATEMENT_QUERY"
                )
                actions_handler.flush()

                try:
                    print(
                        "SERVER: do_get: About to call _parse_prepared_statement_query"
                    )
                    command = self._parse_prepared_statement_query(any_command)
                    print(
                        "SERVER: do_get: Successfully parsed prepared statement command"
                    )

                    # Ensure handle is a string for dictionary lookup
                    handle_raw = command.prepared_statement_handle
                    if isinstance(handle_raw, bytes):
                        # Convert bytes to hex string for dictionary key
                        handle = handle_raw.hex()
                        print(
                            f"SERVER: do_get: Converted bytes handle to hex string: {handle}"
                        )
                    else:
                        handle = str(handle_raw)
                        print(f"SERVER: do_get: Using string handle: {handle}")

                    actions_log.info(
                        f"DEBUG do_get: Looking up prepared statement handle: {handle}"
                    )
                    actions_handler.flush()

                    if handle not in self.prepared_statements:
                        print(
                            f"SERVER: do_get: LOOKUP FAILED - handle '{handle}' not found"
                        )
                        print(
                            f"SERVER: do_get: Available handles: {list(self.prepared_statements.keys())}"
                        )
                        print(
                            f"SERVER: do_get: Raw handle bytes: {handle_raw.hex() if isinstance(handle_raw, bytes) else str(handle_raw)}"
                        )
                        print(
                            f"SERVER: do_get: Total prepared statements: {len(self.prepared_statements)}"
                        )
                        # Show detailed comparison
                        for stored_handle in self.prepared_statements.keys():
                            print(
                                f"SERVER: do_get: Stored handle: '{stored_handle}' (type: {type(stored_handle)})"
                            )
                        raise ValueError(
                            f"Prepared statement handle not found: {handle}"
                        )

                    query = self.prepared_statements[handle]["sql"]
                    print(
                        f"SERVER: do_get: LOOKUP SUCCESS - Found query: '{query}' for handle: '{handle}'"
                    )

                    # Log for debugging
                    actions_log.info(
                        f"DEBUG: About to execute prepared statement query: {query}"
                    )
                    actions_handler.flush()

                    # Retrieve stored parameters for this prepared statement
                    stored_params = self.prepared_statements[handle].get("parameters", [])
                    if stored_params:
                        # Convert parameter batches to Python list format for DuckDB
                        params = self._convert_parameter_batches_to_list(stored_params)
                        logger.info(f"Retrieved stored parameters for prepared statement: {params}")
                        print(f"SERVER: Retrieved stored parameters: {params}")
                    else:
                        params = None
                        logger.info("No parameters stored for this prepared statement")
                        print("SERVER: No parameters found for prepared statement")

                    # Execute the query with parameters
                    return self._do_get_statement_from_query(query, params)
                except Exception as e:
                    print(
                        f"SERVER: ERROR - Exception in do_get for prepared statement: {e}"
                    )
                    actions_log.info(
                        f"DEBUG do_get: Exception in prepared statement: {e}"
                    )
                    actions_handler.flush()
                    import traceback

                    traceback.print_exc()
                    # Return a safe error response instead of crashing
                    fallback_schema = pa.schema([pa.field("error", pa.string())])
                    fallback_table = pa.table(
                        {"error": pa.array([f"Prepared statement error: {str(e)}"])},
                        schema=fallback_schema,
                    )
                    return pf.RecordBatchStream(fallback_table)
            else:
                routing_log.error(f"Unknown command type: {command_type_url}")
                raise NotImplementedError(
                    f"Unsupported command type: {command_type_url}"
                )
        else:
            # Fallback for non-protobuf tickets
            ticket_str = ticket.ticket.decode("utf-8", errors="ignore")
            routing_log.warning(f"Non-protobuf ticket received: {ticket_str}")
            raise NotImplementedError("Unsupported ticket format")

    def do_put(
        self,
        context: pf.ServerCallContext,
        descriptor: pf.FlightDescriptor,
        reader: pf.FlightStreamReader,
        writer: pf.FlightMetadataWriter,
    ):
        """Handle DoPut for both FlightSQL commands and raw Flight path uploads."""
        # Add comprehensive debug logging
        actions_log.info(f"=== do_put ENTRY === timestamp: {time.time()}")
        actions_log.info(
            f"do_put called with descriptor type: {descriptor.descriptor_type}"
        )
        actions_handler.flush()

        logger.info(f"do_put called with descriptor type: {descriptor.descriptor_type}")
        print(
            f"SERVER: do_put called with descriptor type: {descriptor.descriptor_type}"
        )

        # Route based on descriptor type
        if descriptor.descriptor_type == pf.DescriptorType.CMD:
            # EXISTING: All current FlightSQL functionality stays exactly the same
            return self._handle_flightsql_do_put(context, descriptor, reader, writer)
        elif descriptor.descriptor_type == pf.DescriptorType.PATH:
            # NEW: Handle raw Flight file upload functionality
            return self._handle_file_upload_do_put(context, descriptor, reader, writer)
        else:
            raise NotImplementedError(f"Unsupported descriptor type: {descriptor.descriptor_type}")

    def _handle_flightsql_do_put(
        self,
        context: pf.ServerCallContext,
        descriptor: pf.FlightDescriptor,
        reader: pf.FlightStreamReader,
        writer: pf.FlightMetadataWriter,
    ):
        """Handle FlightSQL DoPut commands - EXISTING FUNCTIONALITY UNCHANGED."""
        command_bytes = descriptor.command
        any_command = parse_any_command(command_bytes)
        if not any_command:
            raise ValueError("Failed to parse command from descriptor.")

        command_type_url = any_command.type_url
        actions_log.info(
            f"do_put: Successfully parsed command with type URL: {command_type_url}"
        )
        actions_handler.flush()

        logger.info(
            f"do_put: Successfully parsed command with type URL: {command_type_url}"
        )
        print(
            f"SERVER: do_put: Successfully parsed command with type URL: {command_type_url}"
        )

        if command_type_url == FlightSQLProtobuf.COMMAND_STATEMENT_UPDATE_TYPE_URL:
            command = CommandStatementUpdate()
            command.Unpack(any_command)
            actions_log.info("1. Receiving command: SQL Update")
            actions_log.info(f"2. Command arguments: {command.query}")
            actions_log.info(f"3. Command sent to DuckDB: {command.query}")
            actions_handler.flush()

            print(f"SERVER: do_put: Executing statement update: {command.query}")
            record_count = self._do_put_update(command)

            actions_log.info(f"4. Reply by DuckDB: {record_count} records affected")
            actions_log.info(
                f"5. Reply sent back: DoPutUpdateResult with {record_count} records"
            )
            actions_handler.flush()

            result = DoPutUpdateResult(record_count=record_count)
            writer.write(pa.py_buffer(result.SerializeToString()))

        elif (
            command_type_url
            == FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_UPDATE_TYPE_URL
        ):
            actions_log.info("1. Receiving command: Prepared Statement Update")
            actions_handler.flush()

            print("SERVER: do_put: Handling prepared statement update")
            try:
                print(
                    f"SERVER: do_put: Raw any_command.value: {any_command.value.hex()}"
                )
                update_command = CommandPreparedStatementUpdate()
                update_command.Unpack(any_command)
                handle = update_command.prepared_statement_handle
                handle_key = handle.hex()  # Convert to hex for dictionary lookup

                print(f"SERVER: do_put: Parsed handle: {handle.hex()}")

                if handle_key not in self.prepared_statements:
                    raise ValueError(
                        f"Prepared statement handle not found: {handle.hex()}"
                    )

                # Read parameter bindings from the reader (matching Examples implementation)
                parameter_batches = []
                while True:
                    try:
                        batch = reader.read_chunk()
                        if batch.data is None:
                            break
                        parameter_batches.append(batch.data)
                    except StopIteration:
                        break

                # Store parameters for later use
                if parameter_batches:
                    self.prepared_statements[handle_key]["parameters"] = (
                        parameter_batches
                    )
                    logger.info(
                        f"Stored {len(parameter_batches)} parameter batches for prepared statement"
                    )

                query = self.prepared_statements[handle_key]["sql"]
                print(f"SERVER: do_put: Retrieved query for handle: '{query}'")

                # Add logging for prepared statement details
                actions_log.info(f"2. Command arguments: {query}")
                actions_log.info(f"3. Command sent to DuckDB: {query}")
                actions_handler.flush()

                # Execute the update with parameters if available
                params = None
                if parameter_batches:
                    params = self._extract_parameters_from_batches(parameter_batches)
                    actions_log.info(f"Extracted parameters: {params}")
                    
                record_count = self._do_put_update_from_query(query, params)

                result = DoPutUpdateResult(record_count=record_count)
                writer.write(pa.py_buffer(result.SerializeToString()))

            except Exception as e:
                logger.error(
                    f"Error handling prepared statement update: {e}", exc_info=True
                )
                raise
        elif (
            command_type_url
            == FlightSQLProtobuf.COMMAND_PREPARED_STATEMENT_QUERY_TYPE_URL
        ):
            # This is DoPutPreparedStatementQuery - for parameter binding
            print(
                "SERVER: do_put: Handling prepared statement query (parameter binding)"
            )
            try:
                query_command = CommandPreparedStatementQuery()
                query_command.Unpack(any_command)
                handle = query_command.prepared_statement_handle
                handle_key = handle.hex()

                if handle_key not in self.prepared_statements:
                    raise ValueError(
                        f"Prepared statement handle not found: {handle.hex()}"
                    )

                # Read and store parameter bindings
                parameter_batches = []
                while True:
                    try:
                        batch = reader.read_chunk()
                        if batch.data is None:
                            break
                        parameter_batches.append(batch.data)
                    except StopIteration:
                        break

                self.prepared_statements[handle_key]["parameters"] = parameter_batches
                logger.info(
                    f"Stored {len(parameter_batches)} parameter batches for prepared statement query"
                )

                # Don't execute here - execution happens in do_get
                # Just acknowledge the parameter binding
                writer.write(pa.py_buffer(b""))

            except Exception as e:
                logger.error(
                    f"Error handling prepared statement query parameters: {e}",
                    exc_info=True,
                )
                raise
        else:
            raise NotImplementedError(
                f"Unsupported command type for DoPut: {command_type_url}"
            )

    def _handle_file_upload_do_put(
        self,
        context: pf.ServerCallContext,
        descriptor: pf.FlightDescriptor,
        reader: pf.FlightStreamReader,
        writer: pf.FlightMetadataWriter,
    ):
        """Handle raw Flight file upload via do_put with path descriptor - creates DuckDB tables directly (no files!)"""
        
        # EXTENSIVE LOGGING SETUP
        from mpzsql.logfire_config import get_duckdb_logger
        
        duckdb_logger = get_duckdb_logger()
        
        # 1. TABLE NAME: Use the path directly as the table name, but ensure it's in my_ducklake.main schema
        #    Examples:
        #    - FlightDescriptor.for_path("users") → table name: "my_ducklake.main.users" (default schema)
        #    - FlightDescriptor.for_path("simple_table") → table name: "my_ducklake.main.simple_table"
        #    - FlightDescriptor.for_path("my_ducklake.main.customers") → keep as-is if already qualified
        raw_table_name = descriptor.path[0] if descriptor.path else b"unknown_table"
        # Decode bytes to string (Arrow Flight paths are bytes)
        if isinstance(raw_table_name, bytes):
            raw_table_name = raw_table_name.decode('utf-8')
        raw_table_name = raw_table_name.strip('/')  # Remove any leading/trailing slashes
        
        # Ensure table is always created in my_ducklake.main schema
        if '.' not in raw_table_name:
            # Simple table name -> add my_ducklake.main prefix
            table_name = f"my_ducklake.main.{raw_table_name}"
        elif raw_table_name.startswith('my_ducklake.'):
            # Already has my_ducklake prefix -> keep as-is
            table_name = raw_table_name
        else:
            # Has some other prefix -> replace with my_ducklake.main
            # e.g., "public.customers" -> "my_ducklake.main.customers"
            # e.g., "analytics.public.employees" -> "my_ducklake.main.employees"
            parts = raw_table_name.split('.')
            table_name = f"my_ducklake.main.{parts[-1]}"  # Use just the table name part
        
        # DuckDB will handle database/schema creation automatically when we create the table!
        # No need for manual parsing or schema creation - DuckDB is smart enough to handle it
        
        # Log the raw Flight do_put request with table name transformation
        print(f"SERVER: Raw Flight do_put: '{raw_table_name}' → '{table_name}'")
        duckdb_logger.info("Raw Flight do_put request received", 
                          descriptor_type="PATH",
                          raw_table_name=raw_table_name,
                          final_table_name=table_name,
                          path=descriptor.path)
        
        actions_log.info(f"RAW_FLIGHT_DO_PUT: raw_name={raw_table_name} -> final_table={table_name}, path={descriptor.path}")
        routing_logger.info(f"ROUTE: do_put(PATH) -> file_upload_handler(table={table_name})")
        
        # 2. CHOOSE PROCESSING MODE: Batch vs Streaming
        if self._should_use_streaming(reader, table_name):
            routing_logger.info(f"ROUTE_MODE: streaming_upload(table={table_name})")
            self._handle_streaming_upload(table_name, reader, writer)
        else:
            routing_logger.info(f"ROUTE_MODE: batch_upload(table={table_name})")
            self._handle_batch_upload(table_name, reader, writer)

    def _should_use_streaming(self, reader, table_name):
        """Determine if we should use streaming based on table name or configuration"""
        # You can implement logic here to decide when to stream
        # Examples:
        # - Large table indicators: table names ending with "_large", "_stream", "_big"
        # - Configuration: self.config.get('force_streaming', False)
        # - Memory constraints: check available memory
        
        return (table_name.endswith(('_large', '_stream', '_big')) or 
                getattr(self.config, 'force_streaming', False))

    def _handle_batch_upload(self, table_name, reader, writer):
        """Handle upload by reading all data at once - creates DuckDB table directly"""
        
        # TRANSFORMATION: FlightStreamReader → PyArrow Table
        arrow_table = reader.read_all()  # ← ONE LINE TRANSFORMATION!
        
        # EXTENSIVE LOGGING to all log files
        from mpzsql.logfire_config import get_duckdb_logger
        duckdb_logger = get_duckdb_logger()
        
        # Log to logfire
        duckdb_logger.info("Raw Flight do_put batch upload started", 
                          table_name=table_name, 
                          rows=len(arrow_table),
                          columns=arrow_table.num_columns,
                          schema=str(arrow_table.schema))
        
        # Log to actions.log
        actions_log.info(f"RAW_FLIGHT_BATCH_UPLOAD: table={table_name}, rows={len(arrow_table)}, cols={arrow_table.num_columns}")
        
        # Log to server_routing.log
        routing_logger.info(f"ROUTE: raw_flight_do_put -> batch_upload(table={table_name})")
        
        # DIRECT DUCKDB TABLE CREATION (no file writing!)
        # This is exactly what you want: duckdb.sql("CREATE TABLE my_table AS SELECT * FROM my_arrow")
        self.backend.create_table_from_arrow(table_name, arrow_table)
        
        duckdb_logger.info("Raw Flight batch upload completed successfully", 
                          table_name=table_name, 
                          final_rows=len(arrow_table))
        
        # Acknowledge the upload
        response_msg = f"Created table '{table_name}' with {len(arrow_table)} rows (batch mode)"
        writer.write(pa.py_buffer(response_msg.encode()))

    def _handle_streaming_upload(self, table_name, reader, writer):
        """Handle upload by streaming data chunk by chunk - creates DuckDB table directly"""
        
        total_rows = 0
        first_chunk = True
        
        # EXTENSIVE LOGGING to all log files
        from mpzsql.logfire_config import get_duckdb_logger
        duckdb_logger = get_duckdb_logger()
        
        # Log to logfire
        duckdb_logger.info("Raw Flight do_put streaming upload started", 
                          table_name=table_name)
        
        # Log to actions.log
        actions_log.info(f"RAW_FLIGHT_STREAMING_UPLOAD: table={table_name} - starting")
        
        # Log to server_routing.log
        routing_logger.info(f"ROUTE: raw_flight_do_put -> streaming_upload(table={table_name})")
        
        # STREAMING APPROACH: Process each chunk as it arrives
        for chunk_num, chunk in enumerate(reader, 1):  # ← STREAMING: reader is iterable!
            batch = chunk.data  # chunk.data is pa.RecordBatch
            
            if first_chunk:
                # Create table with schema from first chunk (no file, just DuckDB table!)
                self.backend.create_table_from_schema(table_name, batch.schema)
                first_chunk = False
                
                duckdb_logger.info("Created table schema for streaming upload",
                                  table_name=table_name,
                                  schema=str(batch.schema))
            
            # Convert RecordBatch to Table and append directly to DuckDB
            chunk_table = pa.Table.from_batches([batch])
            self.backend.append_table_from_arrow(table_name, chunk_table)
            
            total_rows += batch.num_rows
            
            # Log each chunk
            duckdb_logger.debug("Processed streaming chunk",
                               table_name=table_name,
                               chunk_number=chunk_num,
                               chunk_rows=batch.num_rows,
                               total_rows=total_rows)
            
            actions_log.info(f"RAW_FLIGHT_CHUNK: table={table_name}, chunk={chunk_num}, rows={batch.num_rows}, total={total_rows}")
        
        duckdb_logger.info("Raw Flight streaming upload completed successfully", 
                          table_name=table_name, 
                          total_chunks=chunk_num,
                          final_rows=total_rows)
        
        # Acknowledge the upload
        response_msg = f"Created table '{table_name}' with {total_rows} rows (streaming mode, {chunk_num} chunks)"
        writer.write(pa.py_buffer(response_msg.encode()))

    def _create_prepared_statement(self, action_body: bytes) -> pf.Result:
        """Handle CreatePreparedStatement action (matching Examples implementation)."""
        try:
            actions_log.info("2. Command arguments: Creating prepared statement")
            actions_handler.flush()

            routing_log.info(
                f"_create_prepared_statement called with {len(action_body)} bytes"
            )
            request = ActionCreatePreparedStatementRequest()
            request.ParseFromString(action_body)
            query = request.query
            transaction_id = getattr(request, "transaction_id", "")

            actions_log.info(
                f"3. Command sent to DuckDB: Preparing statement - {query}"
            )
            actions_handler.flush()

            routing_log.info(f"Creating prepared statement for query: '{query}'")
            logger.info(f"Creating prepared statement for query: {query}")
            print(f"SERVER: Creating prepared statement for query: '{query}'")

            # Generate handle as bytes (matching Examples GenerateRandomString converted to bytes)
            handle_bytes = uuid.uuid4().bytes
            handle_key = (
                handle_bytes.hex()
            )  # Use hex string as dictionary key for consistency

            routing_log.info(f"Generated handle bytes: {handle_bytes.hex()}")
            print(f"SERVER: Generated handle bytes: {handle_bytes.hex()}")

            # Determine if this is a SELECT query (matching Examples logic)
            query_upper = query.strip().upper()
            is_select_query = query_upper.startswith(
                "SELECT "
            ) or query_upper.startswith("SHOW ")

            actions_log.info(
                f"4. Reply by DuckDB: Prepared statement created, is_select_query={is_select_query}"
            )
            actions_handler.flush()

            routing_log.info(f"Query classification: is_select_query={is_select_query}")

            schema = None
            parameter_schema = pa.schema([])  # Empty parameter schema for now

            if is_select_query:
                actions_log.info(
                    "5. Reply sent back: SELECT query prepared - will use do_get for execution"
                )
                actions_handler.flush()
                try:
                    print(f"SERVER: DEBUG - About to get schema for query: {query}")
                    schema = self.backend.get_statement_schema(query)
                    print(f"SERVER: DEBUG - Schema obtained: {schema}")
                    routing_log.info(f"Schema determined for SELECT query: {schema}")
                except Exception as e:
                    print(f"SERVER: DEBUG - Schema detection failed: {e}")
                    logger.warning(
                        f"Could not get schema for SELECT query '{query}': {e}"
                    )
                    routing_log.warning(
                        f"Could not get schema for SELECT query '{query}': {e}"
                    )
                    schema = pa.schema([])  # fallback to empty schema
            else:
                actions_log.info(
                    "5. Reply sent back: UPDATE query prepared - will use do_put for execution"
                )
                actions_handler.flush()

            # Store prepared statement (matching Examples prepared_statements_ map)
            self.prepared_statements[handle_key] = {
                "sql": query,
                "schema": schema,
                "transaction_id": transaction_id,
                "parameters": None,
            }

            routing_log.info(
                f"STORED prepared statement with handle_key: '{handle_key}'"
            )
            print(f"SERVER: STORED prepared statement with handle_key: '{handle_key}'")

            # CRITICAL: Match Examples behavior for dataset_schema inclusion
            # For SELECT queries: include dataset_schema → JDBC calls DoGetPreparedStatement (do_get)
            # For UPDATE/INSERT/DELETE: exclude dataset_schema → JDBC calls DoPutPreparedStatementUpdate (do_put)
            if is_select_query:
                if schema and len(schema) > 0:
                    dataset_schema_bytes = schema.serialize().to_pybytes()
                else:
                    dataset_schema_bytes = None
            else:
                dataset_schema_bytes = None

            parameter_schema_bytes = parameter_schema.serialize().to_pybytes()

            response_bytes = (
                FlightSQLProtobuf.create_action_create_prepared_statement_result(
                    prepared_statement_handle=handle_bytes,
                    dataset_schema=dataset_schema_bytes,
                    parameter_schema=parameter_schema_bytes,
                )
            )
            return pf.Result(pa.py_buffer(response_bytes))

        except Exception as e:
            logger.error(f"Error creating prepared statement: {e}", exc_info=True)
            raise

    def _close_prepared_statement(self, action_body: bytes) -> pf.Result:
        """Handle ClosePreparedStatement action."""
        try:
            request = ActionClosePreparedStatementRequest()
            request.ParseFromString(action_body)
            handle = request.prepared_statement_handle
            handle_key = handle.hex()

            logger.info(f"Closing prepared statement with handle: {handle_key}")
            print(f"SERVER: Closing prepared statement with handle: {handle_key}")

            if handle_key in self.prepared_statements:
                del self.prepared_statements[handle_key]
                print(f"SERVER: Successfully closed prepared statement {handle_key}")
            else:
                logger.warning(
                    f"Attempted to close non-existent prepared statement: {handle_key}"
                )

            return pf.Result(pa.py_buffer(b""))
        except Exception as e:
            logger.error(f"Error closing prepared statement: {e}", exc_info=True)
            raise

    def _get_flight_info_for_command(
        self, descriptor: pf.FlightDescriptor, schema: pa.Schema
    ) -> pf.FlightInfo:
        ticket_bytes = descriptor.command
        endpoint = pf.FlightEndpoint(
            ticket=pf.Ticket(ticket_bytes), locations=[self.advertised_location]
        )
        return pf.FlightInfo(
            schema=schema,
            descriptor=descriptor,
            endpoints=[endpoint],
            total_records=-1,
            total_bytes=-1,
        )

    def _get_flight_info_statement(
        self, descriptor: pf.FlightDescriptor, command: CommandStatementQuery
    ) -> pf.FlightInfo:
        query = command.query
        schema = self.backend.get_statement_schema(query)
        return self._get_flight_info_for_command(descriptor, schema)

    def _get_flight_info_catalogs(
        self, descriptor: pf.FlightDescriptor, command: CommandGetCatalogs
    ) -> pf.FlightInfo:
        schema = FlightSQLProtobuf.get_catalogs_schema()
        return self._get_flight_info_for_command(descriptor, schema)

    def _get_flight_info_schemas(
        self, descriptor: pf.FlightDescriptor, command: CommandGetDbSchemas
    ) -> pf.FlightInfo:
        schema = FlightSQLProtobuf.get_db_schemas_schema()
        return self._get_flight_info_for_command(descriptor, schema)

    def _get_flight_info_tables(
        self, descriptor: pf.FlightDescriptor, command: CommandGetTables
    ) -> pf.FlightInfo:
        if command.include_schema:
            schema = FlightSQLProtobuf.get_tables_schema_with_included_schema()
        else:
            schema = FlightSQLProtobuf.get_tables_schema()
        return self._get_flight_info_for_command(descriptor, schema)

    def _get_flight_info_table_types(
        self, descriptor: pf.FlightDescriptor, command: CommandGetTableTypes
    ) -> pf.FlightInfo:
        schema = FlightSQLProtobuf.get_table_types_schema()
        return self._get_flight_info_for_command(descriptor, schema)

    def _get_flight_info_columns(
        self, descriptor: pf.FlightDescriptor, command: CommandGetColumns
    ) -> pf.FlightInfo:
        schema = FlightSQLProtobuf.get_columns_schema()
        return self._get_flight_info_for_command(descriptor, schema)

    def _get_flight_info_sql_info(
        self, descriptor: pf.FlightDescriptor, command: CommandGetSqlInfo
    ) -> pf.FlightInfo:
        schema = FlightSQLProtobuf.get_sql_info_schema()
        return self._get_flight_info_for_command(descriptor, schema)

    def _get_flight_info_prepared_statement(
        self, descriptor: pf.FlightDescriptor, command: CommandPreparedStatementQuery
    ) -> pf.FlightInfo:
        handle_bytes = command.prepared_statement_handle
        handle_key = handle_bytes.hex()

        if handle_key not in self.prepared_statements:
            raise ValueError(f"Prepared statement handle not found: {handle_key}")

        statement_info = self.prepared_statements[handle_key]
        schema = statement_info.get("schema")

        if not schema:
            # Fallback if schema wasn't determined at creation
            query = statement_info["sql"]
            schema = self.backend.get_statement_schema(query)

        return self._get_flight_info_for_command(descriptor, schema)

    def _do_get_statement(self, command: CommandStatementQuery) -> pf.FlightDataStream:
        query = command.query
        return self._do_get_statement_from_query(query)

    def _do_get_statement_from_query(self, query: str, params: Optional[List] = None) -> pf.FlightDataStream:
        logger.info(f"Executing query: {query}")
        print(f"SERVER: Executing query: {query}")
        if params:
            logger.info(f"With parameters: {params}")
            print(f"SERVER: With parameters: {params}")

        # Log command details for actions.log
        actions_log.info("1. Receiving command: SQL Query")
        actions_log.info(f"2. Command arguments: {query}")
        if params:
            actions_log.info(f"3. Command sent to DuckDB: {query} with parameters {params}")
        else:
            actions_log.info(f"3. Command sent to DuckDB: {query}")
        actions_handler.flush()

        try:
            if params:
                result = self.backend.execute_query(query, params)
            else:
                result = self.backend.execute_query(query)
            actions_log.info(f"4. Reply by DuckDB: {result}")
            actions_log.info(
                f"5. Reply sent back: FlightDataStream with {len(result)} rows"
            )
            actions_handler.flush()
            return pf.RecordBatchStream(result)
        except Exception as e:
            logger.error(f"Error executing query: {e}", exc_info=True)
            actions_log.info(f"4. Reply by DuckDB: ERROR - {e}")
            actions_log.info("5. Reply sent back: Error response")
            actions_handler.flush()
            # Return an error response
            error_schema = pa.schema([pa.field("error", pa.string())])
            error_table = pa.table({"error": pa.array([str(e)])}, schema=error_schema)
            return pf.RecordBatchStream(error_table)

    def _convert_parameter_batches_to_list(self, parameter_batches: List[pa.RecordBatch]) -> List:
        """
        Convert PyArrow parameter batches to a simple Python list for DuckDB.
        
        The client sends parameters as PyArrow record batches, but DuckDB expects 
        a simple Python list of values like [19] for a single parameter.
        """
        if not parameter_batches:
            return []
        
        try:
            params = []
            
            # Iterate through all parameter batches
            for batch in parameter_batches:
                logger.info(f"Processing parameter batch with {batch.num_columns} columns and {batch.num_rows} rows")
                
                # For each row in the batch (each row represents one execution)
                for row_idx in range(batch.num_rows):
                    row_params = []
                    
                    # For each column in the batch (each column is a parameter)
                    for col_idx in range(batch.num_columns):
                        column = batch.column(col_idx)
                        value = column[row_idx].as_py()  # Convert Arrow scalar to Python value
                        row_params.append(value)
                        logger.info(f"Parameter {col_idx}: {value} (type: {type(value)})")
                    
                    # For prepared statements, we typically expect one row of parameters
                    # If there are multiple rows, we take the first one
                    if row_idx == 0:
                        params.extend(row_params)
                    
            logger.info(f"Converted parameter batches to: {params}")
            return params
            
        except Exception as e:
            logger.error(f"Error converting parameter batches: {e}", exc_info=True)
            return []

    def _do_get_catalogs(self, command: CommandGetCatalogs) -> pf.FlightDataStream:
        actions_log.info("1. Receiving command: API - GetCatalogs")
        actions_log.info("2. Command arguments: (none)")
        actions_log.info("3. Command sent to DuckDB: get_catalogs() backend method")

        result = self.backend.get_catalogs()
        actions_log.info(f"4. Reply by DuckDB: {result}")
        actions_log.info(
            f"5. Reply sent back: FlightDataStream with {len(result)} rows"
        )
        return pf.RecordBatchStream(result)

    def _do_get_schemas(self, command: CommandGetDbSchemas) -> pf.FlightDataStream:
        actions_log.info("1. Receiving command: API - GetDbSchemas")
        actions_log.info(
            f"2. Command arguments: catalog={command.catalog}, db_schema_filter_pattern={command.db_schema_filter_pattern}"
        )
        actions_log.info("3. Command sent to DuckDB: get_db_schemas() backend method")

        result = self.backend.get_db_schemas(
            catalog=command.catalog,
            db_schema_filter_pattern=command.db_schema_filter_pattern,
        )
        actions_log.info(f"4. Reply by DuckDB: {result}")
        actions_log.info(
            f"5. Reply sent back: FlightDataStream with {len(result)} rows"
        )
        return pf.RecordBatchStream(result)

    def _do_get_tables(self, command: CommandGetTables) -> pf.FlightDataStream:
        # Log command details for actions.log
        actions_log.info("1. Receiving command: API - GetTables")
        actions_log.info(
            f"2. Command arguments: catalog={command.catalog}, db_schema_filter_pattern={command.db_schema_filter_pattern}, table_name_filter_pattern={command.table_name_filter_pattern}, table_types={command.table_types}, include_schema={command.include_schema}"
        )
        actions_log.info("3. Command sent to DuckDB: get_tables() backend method")

        result = self.backend.get_tables(
            catalog=command.catalog,
            db_schema_filter_pattern=command.db_schema_filter_pattern,
            table_name_filter_pattern=command.table_name_filter_pattern,
            table_types=command.table_types,
            include_schema=command.include_schema,
        )
        actions_log.info(f"4. Reply by DuckDB: {result}")
        actions_log.info(
            f"5. Reply sent back: FlightDataStream with {len(result)} rows"
        )
        return pf.RecordBatchStream(result)

    def _do_get_table_types(self, command: CommandGetTableTypes) -> pf.FlightDataStream:
        actions_log.info("1. Receiving command: API - GetTableTypes")
        actions_log.info("2. Command arguments: (none)")
        actions_log.info("3. Command sent to DuckDB: get_table_types() backend method")

        result = self.backend.get_table_types()
        actions_log.info(f"4. Reply by DuckDB: {result}")
        actions_log.info(
            f"5. Reply sent back: FlightDataStream with {len(result)} rows"
        )
        return pf.RecordBatchStream(result)

    def _do_get_columns(self, command: CommandGetColumns) -> pf.FlightDataStream:
        actions_log.info("1. Receiving command: API - GetColumns")
        actions_log.info(
            f"2. Command arguments: catalog={command.catalog}, db_schema_filter_pattern={command.db_schema_filter_pattern}, table_name_filter_pattern={command.table_name_filter_pattern}, column_name_filter_pattern={command.column_name_filter_pattern}"
        )
        actions_log.info("3. Command sent to DuckDB: get_columns() backend method")

        result = self.backend.get_columns(
            catalog=command.catalog,
            db_schema_filter_pattern=command.db_schema_filter_pattern,
            table_name_filter_pattern=command.table_name_filter_pattern,
            column_name_filter_pattern=command.column_name_filter_pattern,
        )
        actions_log.info(f"4. Reply by DuckDB: {result}")
        actions_log.info(
            f"5. Reply sent back: FlightDataStream with {len(result)} rows"
        )
        return pf.RecordBatchStream(result)

    def _do_get_sql_info(self, command: CommandGetSqlInfo) -> pf.FlightDataStream:
        actions_log.info("1. Receiving command: API - GetSqlInfo")
        actions_log.info(f"2. Command arguments: info={command.info}")
        actions_log.info("3. Command sent to DuckDB: get_sql_info() backend method")

        result = self.backend.get_sql_info(command.info)
        actions_log.info(f"4. Reply by DuckDB: {result}")
        actions_log.info(
            f"5. Reply sent back: FlightDataStream with {len(result)} rows"
        )
        return pf.RecordBatchStream(result)

    def _do_put_update(self, command: CommandStatementUpdate) -> int:
        query = command.query
        return self._do_put_update_from_query(query)

    def _do_put_update_from_query(self, query: str, params: Optional[List] = None) -> int:
        actions_log.info("1. Receiving command: SQL Update")
        actions_log.info(f"2. Command arguments: {query}")
        actions_log.info(f"3. Command sent to DuckDB: {query}")

        try:
            if params:
                result = self.backend.execute_update(query, params)
            else:
                result = self.backend.execute_update(query)
            actions_log.info(f"4. Reply by DuckDB: {result} rows affected")
            actions_log.info(f"5. Reply sent back: {result} rows affected")
            return result
        except Exception as e:
            actions_log.info(f"4. Reply by DuckDB: ERROR - {e}")
            actions_log.info("5. Reply sent back: Error")
            raise e

    def _extract_parameters_from_batches(self, parameter_batches: List[pa.RecordBatch]) -> List:
        """Extract parameter values from PyArrow record batches into a flat list."""
        params = []
        for batch in parameter_batches:
            # For each row in the batch
            for row_index in range(batch.num_rows):
                # For each column in the batch
                for col_index in range(batch.num_columns):
                    column = batch.column(col_index)
                    value = column[row_index].as_py()
                    params.append(value)
        return params

    def _parse_statement_query(self, any_command) -> CommandStatementQuery:
        """Parse CommandStatementQuery from Any message."""
        query = FlightSQLProtobuf.parse_command_statement_query(any_command.value)
        command = CommandStatementQuery()
        command.query = query or ""
        return command

    def _parse_prepared_statement_query(
        self, any_command
    ) -> CommandPreparedStatementQuery:
        """Parse CommandPreparedStatementQuery from Any message."""
        command = CommandPreparedStatementQuery()
        command.Unpack(any_command)
        return command

    def _parse_get_tables(self, any_command):
        """Parse GetTables command from Any protobuf message."""
        command = CommandGetTables()

        try:
            actions_log.info("_parse_get_tables: Starting to parse command")
            actions_log.info(
                f"_parse_get_tables: Command value bytes: {any_command.value.hex()}"
            )

            # Use the new protobuf parsing function to extract parameters
            (
                catalog,
                db_schema_filter_pattern,
                table_name_filter_pattern,
                table_types,
                include_schema,
            ) = FlightSQLProtobuf.parse_command_get_tables(any_command.value)

            command.catalog = catalog
            command.db_schema_filter_pattern = db_schema_filter_pattern
            command.table_name_filter_pattern = table_name_filter_pattern
            command.table_types = table_types
            command.include_schema = include_schema

            actions_log.info(
                f"Parsed GetTables: catalog={command.catalog}, "
                f"db_schema_filter_pattern={command.db_schema_filter_pattern}, "
                f"table_name_filter_pattern={command.table_name_filter_pattern}, "
                f"table_types={command.table_types}, "
                f"include_schema={command.include_schema}"
            )

        except Exception as e:
            actions_log.warning(f"Error parsing GetTables command: {e}")
            actions_log.warning(f"Exception type: {type(e)}")
            import traceback

            actions_log.warning(f"Traceback: {traceback.format_exc()}")
            # Set default values if parsing fails
            command.catalog = None
            command.db_schema_filter_pattern = None
            command.table_name_filter_pattern = None
            command.table_types = []
            command.include_schema = False
            actions_log.info(
                "_parse_get_tables: Set default values after parsing error"
            )

        return command

    def _parse_get_db_schemas(self, any_command):
        """Parse GetDbSchemas command from Any protobuf message."""
        command = CommandGetDbSchemas()

        try:
            actions_log.info("_parse_get_db_schemas: Starting to parse command")
            actions_log.info(
                f"_parse_get_db_schemas: FlightSQLProtobuf class: {FlightSQLProtobuf}"
            )
            actions_log.info(
                f"_parse_get_db_schemas: Available methods: {[m for m in dir(FlightSQLProtobuf) if 'parse' in m.lower()]}"
            )

            # Check if the method exists
            if hasattr(FlightSQLProtobuf, "parse_command_get_db_schemas"):
                actions_log.info("_parse_get_db_schemas: Method exists, calling it")
                # Parse the catalog and schema filter from the protobuf message
                catalog, db_schema_filter_pattern = (
                    FlightSQLProtobuf.parse_command_get_db_schemas(any_command.value)
                )
                command.catalog = catalog
                command.db_schema_filter_pattern = db_schema_filter_pattern

                actions_log.info(
                    f"Parsed GetDbSchemas: catalog={catalog}, db_schema_filter_pattern={db_schema_filter_pattern}"
                )
            else:
                actions_log.error(
                    "_parse_get_db_schemas: Method parse_command_get_db_schemas NOT FOUND on FlightSQLProtobuf"
                )
                command.catalog = None
                command.db_schema_filter_pattern = None

        except Exception as e:
            actions_log.warning(f"Error parsing GetDbSchemas command: {e}")
            actions_log.warning(f"Exception type: {type(e)}")
            import traceback

            actions_log.warning(f"Traceback: {traceback.format_exc()}")
            # Set default values if parsing fails
            command.catalog = None
            command.db_schema_filter_pattern = None

        return command

    def _parse_get_sql_info(self, any_command):
        """Parse GetSqlInfo command from Any protobuf message."""
        command = CommandGetSqlInfo()

        try:
            actions_log.info("_parse_get_sql_info: Starting to parse command")
            actions_log.info(
                f"_parse_get_sql_info: Command value bytes: {any_command.value.hex()}"
            )

            # Parse the protobuf message
            command.ParseFromString(any_command.value)

            actions_log.info(f"_parse_get_sql_info: Parsed info IDs: {command.info}")

        except Exception as e:
            actions_log.error(f"_parse_get_sql_info: Error parsing command: {e}")
            # Set default empty info list if parsing fails
            command.info = []

        return command

    def _parse_get_columns(self, any_command):
        """Parse GetColumns command from Any protobuf message."""
        command = CommandGetColumns()

        try:
            actions_log.info("_parse_get_columns: Starting to parse command")

            # Check if the method exists
            if hasattr(FlightSQLProtobuf, "parse_command_get_columns"):
                actions_log.info("_parse_get_columns: Method exists, calling it")
                # Parse the parameters from the protobuf message
                (
                    catalog,
                    db_schema_filter_pattern,
                    table_name_filter_pattern,
                    column_name_filter_pattern,
                ) = FlightSQLProtobuf.parse_command_get_columns(any_command.value)
                command.catalog = catalog
                command.db_schema_filter_pattern = db_schema_filter_pattern
                command.table_name_filter_pattern = table_name_filter_pattern
                command.column_name_filter_pattern = column_name_filter_pattern

                actions_log.info(
                    f"Parsed GetColumns: catalog={catalog}, db_schema_filter_pattern={db_schema_filter_pattern}, table_name_filter_pattern={table_name_filter_pattern}, column_name_filter_pattern={column_name_filter_pattern}"
                )
            else:
                actions_log.error(
                    "_parse_get_columns: Method parse_command_get_columns NOT FOUND on FlightSQLProtobuf"
                )
                # Set default values for now
                command.catalog = None
                command.db_schema_filter_pattern = None
                command.table_name_filter_pattern = None
                command.column_name_filter_pattern = None
        except Exception as e:
            actions_log.error(f"_parse_get_columns: Error parsing command: {e}")
            # Fallback to default values
            command.catalog = None
            command.db_schema_filter_pattern = None
            command.table_name_filter_pattern = None
            command.column_name_filter_pattern = None

        return command

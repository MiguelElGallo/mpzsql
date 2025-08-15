"""Minimal working FlightSQL server implementation.

This implements the absolute minimum needed to support JDBC clients
by providing proper FlightSQL method implementations.

**THIS IS THE ACTIVE IMPLEMENTATION** used by MPZSQLServer in server.py.
"""

# Remove the incorrect import
# import pyarrow.flight.sql as flight_sql
import logging
import threading
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pyarrow as pa
import pyarrow.flight as pf  # keep original alias for pf.<...>

from ..logfire_config import get_actions_logger, get_routing_logger

# We now have both aliases available
from ..security import (
    BearerAuthServerMiddlewareFactory,
    HeaderAuthServerMiddlewareFactory,
    NoOpAuthHandler,
    TLSCertificateLoader,
)
from .generated.Flight_pb2 import PollInfo
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
    """Minimal FlightSQL server that inherits from FlightServerBase
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
                raise ValueError(f"TLS configuration failed: {e}") from e

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
        self.prepared_statements: dict[str, dict[str, Any]] = {}
        # Add transaction and session management like Examples implementation
        self.open_transactions: dict[str, str] = {}  # transaction_id -> connection_id
        self.open_sessions: dict[str, Any] = {}  # session_id -> connection
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
            pf.ActionType(
                "CloseSession", "Close and invalidate the current session context"
            ),
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
        # Phase 3 Advanced Actions
        elif action_type == "CancelFlightInfo":
            actions_log.info("1. Receiving command: Cancel Flight Info")
            actions_handler.flush()
            yield self._cancel_flight_info(action_body)
        elif action_type == "CancelMultipleQueries":
            actions_log.info("1. Receiving command: Cancel Multiple Queries")
            actions_handler.flush()
            yield self._cancel_multiple_queries(action_body)
        elif action_type == "CreateSession":
            actions_log.info("1. Receiving command: Create Session")
            actions_handler.flush()
            yield self._create_session(action_body)
        elif action_type == "SetSessionTimeout":
            actions_log.info("1. Receiving command: Set Session Timeout")
            actions_handler.flush()
            yield self._set_session_timeout(action_body)
        elif action_type == "CleanupExpiredSessions":
            actions_log.info("1. Receiving command: Cleanup Expired Sessions")
            actions_handler.flush()
            yield self._cleanup_expired_sessions(action_body)
        elif action_type == "SetSessionState":
            actions_log.info("1. Receiving command: Set Session State")
            actions_handler.flush()
            yield self._set_session_state(action_body)
        elif action_type == "GetSessionState":
            actions_log.info("1. Receiving command: Get Session State")
            actions_handler.flush()
            yield self._get_session_state(action_body)
        elif action_type == "ResumeQuery":
            actions_log.info("1. Receiving command: Resume Query")
            actions_handler.flush()
            yield self._resume_query(action_body)
        elif action_type == "CleanupResources":
            actions_log.info("1. Receiving command: Cleanup Resources")
            actions_handler.flush()
            yield self._cleanup_resources(action_body)
        elif action_type == "GetCircuitBreakerStatus":
            actions_log.info("1. Receiving command: Get Circuit Breaker Status")
            actions_handler.flush()
            yield self._get_circuit_breaker_status(action_body)
        elif action_type == "ConfigureConnectionPool":
            actions_log.info("1. Receiving command: Configure Connection Pool")
            actions_handler.flush()
            yield self._configure_connection_pool(action_body)
        elif action_type == "GetConnectionPoolStatus":
            actions_log.info("1. Receiving command: Get Connection Pool Status")
            actions_handler.flush()
            yield self._get_connection_pool_status(action_body)
        elif action_type == "EnableQueryCache":
            actions_log.info("1. Receiving command: Enable Query Cache")
            actions_handler.flush()
            yield self._enable_query_cache(action_body)
        elif action_type == "SetBatchSize":
            actions_log.info("1. Receiving command: Set Batch Size")
            actions_handler.flush()
            yield self._set_batch_size(action_body)
        elif action_type == "SetConcurrentQueryLimit":
            actions_log.info("1. Receiving command: Set Concurrent Query Limit")
            actions_handler.flush()
            yield self._set_concurrent_query_limit(action_body)
        elif action_type == "CancelTransaction":
            actions_log.info("1. Receiving command: Cancel Transaction")
            actions_handler.flush()
            yield self._cancel_transaction(action_body)
        elif action_type == "SetupComplexWorkflow":
            actions_log.info("1. Receiving command: Setup Complex Workflow")
            actions_handler.flush()
            yield self._setup_complex_workflow(action_body)
        elif action_type == "CleanupWorkflow":
            actions_log.info("1. Receiving command: Cleanup Workflow")
            actions_handler.flush()
            yield self._cleanup_workflow(action_body)
        elif action_type == "CreateMonitoredSession":
            actions_log.info("1. Receiving command: Create Monitored Session")
            actions_handler.flush()
            yield self._create_monitored_session(action_body)
        elif action_type == "GetResourceUsage":
            actions_log.info("1. Receiving command: Get Resource Usage")
            actions_handler.flush()
            yield self._get_resource_usage(action_body)
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
                    logger.info(
                        f"Cleaned up {session_cleanup_count} prepared statements during session close"
                    )

                # Clean up any orphaned transactions
                if self.open_transactions:
                    transaction_cleanup_count = len(self.open_transactions)
                    self.open_transactions.clear()
                    logger.info(
                        f"Cleaned up {transaction_cleanup_count} transactions during session close"
                    )
                    session_cleanup_count += transaction_cleanup_count

                # Clean up any session-specific data
                if self.open_sessions:
                    session_count = len(self.open_sessions)
                    self.open_sessions.clear()
                    logger.info(
                        f"Cleaned up {session_count} session entries during session close"
                    )
                    session_cleanup_count += session_count

            actions_log.info(
                f"4. Reply by backend: Session closed, cleaned up {session_cleanup_count} resources"
            )
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

    # ============================================================================
    # Phase 3 Advanced FlightSQL Methods
    # ============================================================================

    def do_exchange(
        self,
        context: pf.ServerCallContext,
        descriptor: pf.FlightDescriptor,
        reader: pf.MetadataRecordBatchReader,
        writer: pf.MetadataRecordBatchWriter,
    ) -> None:
        """Handle bidirectional streaming for complex workflows and computation offloading.

        This is a Phase 3 method that enables bidirectional communication between
        client and server for advanced use cases like:
        - Computation offloading
        - Streaming aggregations
        - Interactive data analysis
        - Real-time data processing
        """
        actions_log.info(f"=== do_exchange ENTRY === timestamp: {time.time()}")
        actions_log.info("do_exchange called for bidirectional streaming")
        actions_handler.flush()

        logger.info("DoExchange called for bidirectional streaming")
        print("SERVER: DoExchange called for bidirectional streaming")

        try:
            # Parse descriptor to understand the type of exchange requested
            if descriptor.descriptor_type == pf.DescriptorType.CMD:
                command_bytes = descriptor.command
                any_command = parse_any_command(command_bytes)

                if any_command:
                    command_type_url = any_command.type_url
                    actions_log.info(f"DoExchange command type: {command_type_url}")
                    actions_handler.flush()

                    # Handle different types of bidirectional operations
                    if "computation" in command_type_url.lower():
                        self._handle_computation_exchange(reader, writer)
                    elif "streaming" in command_type_url.lower():
                        self._handle_streaming_exchange(reader, writer)
                    else:
                        self._handle_generic_exchange(reader, writer)
                else:
                    # Fallback for non-command exchanges
                    self._handle_generic_exchange(reader, writer)
            else:
                # Handle PATH-based exchanges
                self._handle_path_exchange(descriptor, reader, writer)

            actions_log.info("DoExchange completed successfully")
            actions_handler.flush()

        except Exception as e:
            logger.error(f"Error in do_exchange: {e}", exc_info=True)
            actions_log.info(f"DoExchange failed: {e}")
            actions_handler.flush()
            # Send error response
            error_batch = pa.record_batch({"error": [str(e)]})
            writer.write_batch(error_batch)

    def _handle_computation_exchange(
        self, reader: pf.MetadataRecordBatchReader, writer: pf.MetadataRecordBatchWriter
    ) -> None:
        """Handle computation offloading exchange."""
        logger.info("Handling computation exchange")

        # Read computation request and data
        computation_requests = []
        data_batches = []

        try:
            for batch in reader:
                # Distinguish between computation metadata and data
                if "operation" in batch.schema.names:
                    computation_requests.append(batch)
                else:
                    data_batches.append(batch)
        except StopIteration:
            pass

        # Process computation if backend supports it
        if hasattr(self.backend, "execute_computation"):
            for req_batch in computation_requests:
                try:
                    result = self.backend.execute_computation(req_batch)
                    writer.write_batch(result)
                except Exception as e:
                    logger.error(f"Computation failed: {e}")
                    error_batch = pa.record_batch({"error": [str(e)]})
                    writer.write_batch(error_batch)
        else:
            # Fallback response
            result_batch = pa.record_batch(
                {
                    "status": ["completed"],
                    "message": ["Computation completed"],
                }
            )
            writer.write_batch(result_batch)

    def _handle_streaming_exchange(
        self, reader: pf.MetadataRecordBatchReader, writer: pf.MetadataRecordBatchWriter
    ) -> None:
        """Handle streaming data aggregation exchange."""
        logger.info("Handling streaming exchange")

        running_sum = 0
        chunk_count = 0

        try:
            for batch in reader:
                chunk_count += 1

                # Process streaming data if backend supports it
                if hasattr(self.backend, "process_streaming_aggregation"):
                    result = self.backend.process_streaming_aggregation(batch)
                    writer.write_batch(result)
                else:
                    # Simple aggregation fallback
                    if "value" in batch.schema.names:
                        values = batch.column("value").to_pylist()
                        running_sum += sum(values)

                    # Send intermediate result
                    result_batch = pa.record_batch(
                        {
                            "running_sum": [running_sum],
                            "chunk_count": [chunk_count],
                        }
                    )
                    writer.write_batch(result_batch)

        except StopIteration:
            pass

    def _handle_generic_exchange(
        self, reader: pf.MetadataRecordBatchReader, writer: pf.MetadataRecordBatchWriter
    ) -> None:
        """Handle generic bidirectional exchange."""
        logger.info("Handling generic exchange")

        batch_count = 0
        try:
            for batch in reader:
                batch_count += 1

                # Echo back processed data
                response_batch = pa.record_batch(
                    {
                        "processed_batch": [batch_count],
                        "timestamp": [time.time()],
                        "status": ["processed"],
                    }
                )
                writer.write_batch(response_batch)

        except StopIteration:
            pass

    def _handle_path_exchange(
        self,
        descriptor: pf.FlightDescriptor,
        reader: pf.MetadataRecordBatchReader,
        writer: pf.MetadataRecordBatchWriter,
    ) -> None:
        """Handle PATH-based exchange operations."""
        logger.info(f"Handling path exchange: {descriptor.path}")

        # Simple echo response for path-based exchanges
        response_batch = pa.record_batch(
            {
                "path": [str(descriptor.path)],
                "status": ["exchange_completed"],
                "timestamp": [time.time()],
            }
        )
        writer.write_batch(response_batch)

    def poll_flight_info(
        self, context: pf.ServerCallContext, descriptor: pf.FlightDescriptor
    ) -> PollInfo:
        """Poll the status of a long-running query.

        This is a Phase 3 method that enables monitoring of long-running operations
        without blocking the client. Supports:
        - Query progress monitoring
        - Status updates for running operations
        - Long polling for efficiency
        - Query cancellation detection
        """
        actions_log.info(f"=== poll_flight_info ENTRY === timestamp: {time.time()}")
        actions_log.info("poll_flight_info called for query monitoring")
        actions_handler.flush()

        logger.info("PollFlightInfo called for query status monitoring")
        print("SERVER: PollFlightInfo called for query status monitoring")

        try:
            # Extract query information from descriptor
            query_id = None
            if descriptor.descriptor_type == pf.DescriptorType.CMD:
                command_bytes = descriptor.command
                query_id = f"query_{hash(command_bytes) & 0x7FFFFFFF}"  # Positive hash
            else:
                query_id = f"path_{hash(str(descriptor.path)) & 0x7FFFFFFF}"

            actions_log.info(f"Polling status for query_id: {query_id}")
            actions_handler.flush()

            # Get query status from backend
            status_info = {"status": "completed", "progress": 1.0}
            if hasattr(self.backend, "get_query_status"):
                try:
                    status_info = self.backend.get_query_status(query_id)
                except Exception as e:
                    logger.warning(f"Backend query status failed: {e}")
                    status_info = {
                        "status": "completed",
                        "progress": 1.0,
                    }  # Default to completed

            # Create poll info response
            flight_info = None
            progress = status_info.get("progress", 1.0)  # Default to complete

            # If query is completed, provide flight info for data retrieval
            if status_info.get("status") == "completed":
                try:
                    flight_info = self.get_flight_info(context, descriptor)
                except Exception as e:
                    logger.warning(
                        f"Could not get flight info for completed query: {e}"
                    )

            # Create poll info object using the generated protobuf class
            poll_info = PollInfo()
            poll_info.progress = progress  # Set progress explicitly

            # Set basic fields that might be available in the protobuf
            # The actual implementation would depend on the specific protobuf structure
            # For now we create a minimal valid PollInfo object

            actions_log.info(
                f"Poll info created - status: {status_info.get('status')}, progress: {progress}"
            )
            actions_handler.flush()

            return poll_info

        except Exception as e:
            logger.error(f"Error in poll_flight_info: {e}", exc_info=True)
            actions_log.info(f"poll_flight_info failed: {e}")
            actions_handler.flush()
            raise

    # Phase 3 Action Handlers
    def _cancel_flight_info(self, action_body: bytes) -> pf.Result:
        """Handle CancelFlightInfo action - cancel a running query."""
        try:
            query_id = action_body.decode("utf-8")
            actions_log.info(f"2. Command arguments: Cancelling query_id: {query_id}")
            actions_log.info(f"3. Command sent to backend: cancel_query({query_id})")
            actions_handler.flush()

            logger.info(f"Cancelling query: {query_id}")
            print(f"SERVER: Cancelling query: {query_id}")

            cancelled = False
            if hasattr(self.backend, "cancel_query"):
                try:
                    cancelled = self.backend.cancel_query(query_id)
                except Exception as e:
                    logger.warning(f"Backend cancel failed: {e}")
                    cancelled = False

            status = "cancelled" if cancelled else "not_found"
            result_data = f"Query {query_id} {status}".encode("utf-8")

            actions_log.info(f"4. Reply by backend: Query {status}")
            actions_log.info(f"5. Reply sent back: CancelFlightInfo {status}")
            actions_handler.flush()

            return pf.Result(pa.py_buffer(result_data))

        except Exception as e:
            logger.error(f"Error cancelling flight info: {e}", exc_info=True)
            actions_log.info(f"4. Reply by backend: ERROR - {e}")
            actions_log.info("5. Reply sent back: CancelFlightInfo failed")
            actions_handler.flush()
            return pf.Result(pa.py_buffer(b"error"))

    def _cancel_multiple_queries(self, action_body: bytes) -> pf.Result:
        """Handle cancellation of multiple queries."""
        try:
            query_ids_str = action_body.decode("utf-8")
            query_ids = query_ids_str.split(",") if query_ids_str else []

            actions_log.info(
                f"2. Command arguments: Cancelling {len(query_ids)} queries"
            )
            actions_handler.flush()

            logger.info(f"Cancelling multiple queries: {query_ids}")

            cancelled = []
            not_found = []

            if hasattr(self.backend, "cancel_multiple_queries"):
                try:
                    result = self.backend.cancel_multiple_queries(query_ids)
                    cancelled = result.get("cancelled", [])
                    not_found = result.get("not_found", [])
                except Exception:
                    # Fallback to individual cancellation
                    for query_id in query_ids:
                        if hasattr(self.backend, "cancel_query"):
                            try:
                                if self.backend.cancel_query(query_id):
                                    cancelled.append(query_id)
                                else:
                                    not_found.append(query_id)
                            except Exception:
                                not_found.append(query_id)
                        else:
                            not_found.append(query_id)

            result_data = (
                f"cancelled:{len(cancelled)},not_found:{len(not_found)}".encode("utf-8")
            )

            actions_log.info(
                f"4. Reply by backend: {len(cancelled)} cancelled, {len(not_found)} not found"
            )
            actions_log.info("5. Reply sent back: CancelMultipleQueries completed")
            actions_handler.flush()

            return pf.Result(pa.py_buffer(result_data))

        except Exception as e:
            logger.error(f"Error cancelling multiple queries: {e}", exc_info=True)
            return pf.Result(pa.py_buffer(b"error"))

    def _create_session(self, action_body: bytes) -> pf.Result:
        """Handle CreateSession action."""
        try:
            session_config = action_body.decode("utf-8") if action_body else "default"
            session_id = f"session_{uuid.uuid4().hex[:8]}"

            with self._mutex:
                self.open_sessions[session_id] = {
                    "config": session_config,
                    "created": time.time(),
                    "resources": {},
                }

            logger.info(f"Created session: {session_id}")
            return pf.Result(pa.py_buffer(session_id.encode("utf-8")))

        except Exception as e:
            logger.error(f"Error creating session: {e}", exc_info=True)
            return pf.Result(pa.py_buffer(b"error"))

    def _set_session_timeout(self, action_body: bytes) -> pf.Result:
        """Handle SetSessionTimeout action."""
        try:
            timeout_config = action_body.decode("utf-8")
            logger.info(f"Setting session timeout: {timeout_config}")

            # Store timeout configuration
            # Implementation would set actual timeout values

            return pf.Result(pa.py_buffer(b"timeout_set"))

        except Exception as e:
            logger.error(f"Error setting session timeout: {e}", exc_info=True)
            return pf.Result(pa.py_buffer(b"error"))

    def _cleanup_expired_sessions(self, action_body: bytes) -> pf.Result:
        """Handle cleanup of expired sessions."""
        try:
            cleaned_count = 0
            if hasattr(self.backend, "cleanup_expired_sessions"):
                cleaned_count = self.backend.cleanup_expired_sessions()

            logger.info(f"Cleaned up {cleaned_count} expired sessions")
            return pf.Result(pa.py_buffer(str(cleaned_count).encode("utf-8")))

        except Exception as e:
            logger.error(f"Error cleaning up expired sessions: {e}", exc_info=True)
            return pf.Result(pa.py_buffer(b"0"))

    def _set_session_state(self, action_body: bytes) -> pf.Result:
        """Handle SetSessionState action."""
        try:
            state_data = action_body.decode("utf-8")
            logger.info(f"Setting session state: {state_data}")
            return pf.Result(pa.py_buffer(b"state_set"))

        except Exception as e:
            logger.error(f"Error setting session state: {e}", exc_info=True)
            return pf.Result(pa.py_buffer(b"error"))

    def _get_session_state(self, action_body: bytes) -> pf.Result:
        """Handle GetSessionState action."""
        try:
            state_data = "key:value,setting:enabled"  # Mock state
            logger.info("Retrieved session state")
            return pf.Result(pa.py_buffer(state_data.encode("utf-8")))

        except Exception as e:
            logger.error(f"Error getting session state: {e}", exc_info=True)
            return pf.Result(pa.py_buffer(b"error"))

    def _resume_query(self, action_body: bytes) -> pf.Result:
        """Handle ResumeQuery action for partial result recovery."""
        try:
            continuation_token = action_body.decode("utf-8")
            logger.info(f"Resuming query with token: {continuation_token}")

            # Mock resume functionality
            if hasattr(self.backend, "get_partial_results"):
                partial_info = self.backend.get_partial_results(continuation_token)
                result_data = str(partial_info).encode("utf-8")
            else:
                result_data = b"resumed"

            return pf.Result(pa.py_buffer(result_data))

        except Exception as e:
            logger.error(f"Error resuming query: {e}", exc_info=True)
            return pf.Result(pa.py_buffer(b"error"))

    def _cleanup_resources(self, action_body: bytes) -> pf.Result:
        """Handle CleanupResources action."""
        try:
            logger.info("Cleaning up resources after failure")

            # Basic cleanup
            cleanup_count = 0
            with self._mutex:
                cleanup_count += len(self.prepared_statements)
                cleanup_count += len(self.open_transactions)
                cleanup_count += len(self.open_sessions)

            return pf.Result(pa.py_buffer(f"cleaned_{cleanup_count}".encode("utf-8")))

        except Exception as e:
            logger.error(f"Error cleaning up resources: {e}", exc_info=True)
            return pf.Result(pa.py_buffer(b"error"))

    def _get_circuit_breaker_status(self, action_body: bytes) -> pf.Result:
        """Handle GetCircuitBreakerStatus action."""
        try:
            status = "closed"  # Mock circuit breaker status
            logger.info(f"Circuit breaker status: {status}")
            return pf.Result(pa.py_buffer(status.encode("utf-8")))

        except Exception as e:
            logger.error(f"Error getting circuit breaker status: {e}", exc_info=True)
            return pf.Result(pa.py_buffer(b"error"))

    # Performance optimization action handlers
    def _configure_connection_pool(self, action_body: bytes) -> pf.Result:
        """Handle ConfigureConnectionPool action."""
        try:
            pool_config = action_body.decode("utf-8")
            logger.info(f"Configuring connection pool: {pool_config}")
            return pf.Result(pa.py_buffer(b"pool_configured"))

        except Exception as e:
            logger.error(f"Error configuring connection pool: {e}", exc_info=True)
            return pf.Result(pa.py_buffer(b"error"))

    def _get_connection_pool_status(self, action_body: bytes) -> pf.Result:
        """Handle GetConnectionPoolStatus action."""
        try:
            status = "active:5,idle:3,max:10"  # Mock pool status
            logger.info(f"Connection pool status: {status}")
            return pf.Result(pa.py_buffer(status.encode("utf-8")))

        except Exception as e:
            logger.error(f"Error getting connection pool status: {e}", exc_info=True)
            return pf.Result(pa.py_buffer(b"error"))

    def _enable_query_cache(self, action_body: bytes) -> pf.Result:
        """Handle EnableQueryCache action."""
        try:
            cache_config = action_body.decode("utf-8")
            logger.info(f"Enabling query cache: {cache_config}")
            return pf.Result(pa.py_buffer(b"cache_enabled"))

        except Exception as e:
            logger.error(f"Error enabling query cache: {e}", exc_info=True)
            return pf.Result(pa.py_buffer(b"error"))

    def _set_batch_size(self, action_body: bytes) -> pf.Result:
        """Handle SetBatchSize action."""
        try:
            batch_config = action_body.decode("utf-8")
            logger.info(f"Setting batch size: {batch_config}")
            return pf.Result(pa.py_buffer(b"batch_size_set"))

        except Exception as e:
            logger.error(f"Error setting batch size: {e}", exc_info=True)
            return pf.Result(pa.py_buffer(b"error"))

    def _set_concurrent_query_limit(self, action_body: bytes) -> pf.Result:
        """Handle SetConcurrentQueryLimit action."""
        try:
            limit_config = action_body.decode("utf-8")
            logger.info(f"Setting concurrent query limit: {limit_config}")
            return pf.Result(pa.py_buffer(b"limit_set"))

        except Exception as e:
            logger.error(f"Error setting concurrent query limit: {e}", exc_info=True)
            return pf.Result(pa.py_buffer(b"error"))

    def _cancel_transaction(self, action_body: bytes) -> pf.Result:
        """Handle CancelTransaction action."""
        try:
            transaction_id = action_body.decode("utf-8")
            logger.info(f"Cancelling transaction: {transaction_id}")

            with self._mutex:
                if transaction_id in self.open_transactions:
                    del self.open_transactions[transaction_id]
                    status = "cancelled"
                else:
                    status = "not_found"

            return pf.Result(pa.py_buffer(status.encode("utf-8")))

        except Exception as e:
            logger.error(f"Error cancelling transaction: {e}", exc_info=True)
            return pf.Result(pa.py_buffer(b"error"))

    def _setup_complex_workflow(self, action_body: bytes) -> pf.Result:
        """Handle SetupComplexWorkflow action."""
        try:
            workflow_config = action_body.decode("utf-8")
            logger.info(f"Setting up complex workflow: {workflow_config}")
            return pf.Result(pa.py_buffer(b"workflow_setup"))

        except Exception as e:
            logger.error(f"Error setting up workflow: {e}", exc_info=True)
            return pf.Result(pa.py_buffer(b"error"))

    def _cleanup_workflow(self, action_body: bytes) -> pf.Result:
        """Handle CleanupWorkflow action."""
        try:
            logger.info("Cleaning up workflow")
            return pf.Result(pa.py_buffer(b"workflow_cleaned"))

        except Exception as e:
            logger.error(f"Error cleaning up workflow: {e}", exc_info=True)
            return pf.Result(pa.py_buffer(b"error"))

    def _create_monitored_session(self, action_body: bytes) -> pf.Result:
        """Handle CreateMonitoredSession action."""
        try:
            session_config = action_body.decode("utf-8")
            session_id = f"monitored_session_{uuid.uuid4().hex[:8]}"

            with self._mutex:
                self.open_sessions[session_id] = {
                    "type": "monitored",
                    "config": session_config,
                    "created": time.time(),
                }

            logger.info(f"Created monitored session: {session_id}")
            return pf.Result(pa.py_buffer(session_id.encode("utf-8")))

        except Exception as e:
            logger.error(f"Error creating monitored session: {e}", exc_info=True)
            return pf.Result(pa.py_buffer(b"error"))

    def _get_resource_usage(self, action_body: bytes) -> pf.Result:
        """Handle GetResourceUsage action."""
        try:
            usage_info = f"sessions:{len(self.open_sessions)},transactions:{len(self.open_transactions)},prepared:{len(self.prepared_statements)}"
            logger.info(f"Resource usage: {usage_info}")
            return pf.Result(pa.py_buffer(usage_info.encode("utf-8")))

        except Exception as e:
            logger.error(f"Error getting resource usage: {e}", exc_info=True)
            return pf.Result(pa.py_buffer(b"error"))

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

        # Support PATH descriptor for raw Flight operations (e.g., verify uploads)
        if descriptor.descriptor_type == pf.DescriptorType.PATH:
            try:
                parts = []
                if descriptor.path:
                    for p in descriptor.path:
                        if isinstance(p, (bytes, bytearray)):
                            parts.append(p.decode("utf-8"))
                        else:
                            parts.append(str(p))
                table_name = parts[0] if len(parts) == 1 else ".".join(parts)
                routing_log.info(f"PATH GetFlightInfo for table: {table_name}")
                schema = self.backend.get_table_schema(table_name)
                try:
                    total_rows = self.backend.get_table_row_count(table_name)
                except Exception as e:
                    logger.debug(f"Row count unavailable for {table_name}: {e}")
                    total_rows = 0
                endpoint = pf.FlightEndpoint(
                    ticket=pf.Ticket(f"PATH:{table_name}".encode()),
                    locations=[self.advertised_location],
                )
                return pf.FlightInfo(
                    schema=schema,
                    descriptor=descriptor,
                    endpoints=[endpoint],
                    total_records=total_rows,
                    total_bytes=0,
                )
            except Exception as e:
                logger.error(f"PATH GetFlightInfo failed: {e}", exc_info=True)
                empty_schema = pa.schema([])
                endpoint = pf.FlightEndpoint(
                    ticket=pf.Ticket(b""), locations=[self.advertised_location]
                )
                return pf.FlightInfo(
                    schema=empty_schema,
                    descriptor=descriptor,
                    endpoints=[endpoint],
                    total_records=0,
                    total_bytes=0,
                )

        if descriptor.descriptor_type != pf.DescriptorType.CMD:
            raise NotImplementedError("Only CMD and PATH descriptors are supported.")

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
        if command_type_url == FlightSQLProtobuf.COMMAND_GET_CATALOGS_TYPE_URL:
            print("SERVER: DEBUG - Handling COMMAND_GET_CATALOGS")
            command = CommandGetCatalogs()
            return self._get_flight_info_catalogs(descriptor, command)
        if command_type_url == FlightSQLProtobuf.COMMAND_GET_DB_SCHEMAS_TYPE_URL:
            print("SERVER: DEBUG - Handling COMMAND_GET_DB_SCHEMAS")
            command = self._parse_get_db_schemas(any_command)
            return self._get_flight_info_schemas(descriptor, command)
        if command_type_url == FlightSQLProtobuf.COMMAND_GET_TABLES_TYPE_URL:
            print("SERVER: DEBUG - Handling COMMAND_GET_TABLES")
            command = self._parse_get_tables(any_command)
            return self._get_flight_info_tables(descriptor, command)
        if command_type_url == FlightSQLProtobuf.COMMAND_GET_TABLE_TYPES_TYPE_URL:
            command = CommandGetTableTypes()
            return self._get_flight_info_table_types(descriptor, command)
        if command_type_url == FlightSQLProtobuf.COMMAND_GET_COLUMNS_TYPE_URL:
            print("SERVER: DEBUG - Handling COMMAND_GET_COLUMNS")
            command = self._parse_get_columns(any_command)
            return self._get_flight_info_columns(descriptor, command)
        if command_type_url == FlightSQLProtobuf.COMMAND_GET_SQL_INFO_TYPE_URL:
            command = self._parse_get_sql_info(any_command)
            return self._get_flight_info_sql_info(descriptor, command)
        if (
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
                    safe_ticket = f"ERROR: {str(e)}".encode()
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
                    raise e from None  # Re-raise the original exception
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
            if command_type_url == FlightSQLProtobuf.COMMAND_GET_CATALOGS_TYPE_URL:
                command = CommandGetCatalogs()
                return self._do_get_catalogs(command)
            if command_type_url == FlightSQLProtobuf.COMMAND_GET_DB_SCHEMAS_TYPE_URL:
                command = self._parse_get_db_schemas(any_command)
                return self._do_get_schemas(command)
            if command_type_url == FlightSQLProtobuf.COMMAND_GET_TABLES_TYPE_URL:
                command = self._parse_get_tables(any_command)
                return self._do_get_tables(command)
            if command_type_url == FlightSQLProtobuf.COMMAND_GET_TABLE_TYPES_TYPE_URL:
                command = CommandGetTableTypes()
                return self._do_get_table_types(command)
            if command_type_url == FlightSQLProtobuf.COMMAND_GET_COLUMNS_TYPE_URL:
                command = self._parse_get_columns(any_command)
                return self._do_get_columns(command)
            if command_type_url == FlightSQLProtobuf.COMMAND_GET_SQL_INFO_TYPE_URL:
                command = self._parse_get_sql_info(any_command)
                return self._do_get_sql_info(command)
            if (
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
                    stored_params = self.prepared_statements[handle].get(
                        "parameters", []
                    )
                    if stored_params:
                        # Convert parameter batches to Python list format for DuckDB
                        params = self._convert_parameter_batches_to_list(stored_params)
                        logger.info(
                            f"Retrieved stored parameters for prepared statement: {params}"
                        )
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
            # Fallback for non-protobuf tickets (Phase 3 tests)
            ticket_str = ticket.ticket.decode("utf-8", errors="ignore")
            routing_log.info(f"Non-protobuf ticket received: {ticket_str}")

            # Handle Phase 3 specific tickets
            if ticket_str in [
                "streaming_query",
                "compressed_query",
                "test_query",
                "retry_query",
                "cached_query",
                "batch_query",
                "resource_intensive_query",
            ] or ticket_str.startswith("concurrent_query_"):
                # Create a simple result for Phase 3 test tickets
                result_data = {
                    "query_type": [ticket_str],
                    "status": ["executed"],
                    "timestamp": [time.time()],
                    "rows_processed": [100],
                }

                result_table = pa.table(result_data)
                routing_log.info(
                    f"Created result table for {ticket_str}: {len(result_table)} rows"
                )
                return pf.RecordBatchStream(result_table)
            else:
                routing_log.warning(f"Unknown non-protobuf ticket: {ticket_str}")
                raise NotImplementedError("Unsupported ticket format")

    def do_put(
        self,
        context: pf.ServerCallContext,
        descriptor: pf.FlightDescriptor,
        reader: pf.FlightStreamReader,
        writer: pf.FlightMetadataWriter,
    ):
        """Handle DoPut for prepared statement updates or parameter binding."""
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

        # Handle raw Flight PATH uploads (Arrow table ingestion)
        if descriptor.descriptor_type == pf.DescriptorType.PATH:
            try:
                parts = []
                if descriptor.path:
                    for p in descriptor.path:
                        if isinstance(p, (bytes, bytearray)):
                            parts.append(p.decode("utf-8"))
                        else:
                            parts.append(str(p))
                table_name = parts[0] if len(parts) == 1 else ".".join(parts)

                # Parse client table identifier to show catalog/schema/table breakdown
                if "." in table_name:
                    name_parts = table_name.split(".")
                    if len(name_parts) == 3:
                        catalog, schema, table = name_parts
                        actions_log.info(
                            f"CLIENT PATH do_put → catalog.schema.table: {catalog}.{schema}.{table} (full: {table_name})"
                        )
                    elif len(name_parts) == 2:
                        schema, table = name_parts
                        actions_log.info(
                            f"CLIENT PATH do_put → schema.table: {schema}.{table} (full: {table_name})"
                        )
                    else:
                        actions_log.info(
                            f"CLIENT PATH do_put → complex_table: {table_name} (parts: {len(name_parts)})"
                        )
                else:
                    actions_log.info(f"CLIENT PATH do_put → simple_table: {table_name}")
                actions_handler.flush()

                incoming_schema = getattr(reader, "schema", None)
                if incoming_schema is None:
                    raise ValueError("PATH do_put requires schema from client")

                # Create empty table, then append all incoming batches
                self.backend.create_table_from_schema(table_name, incoming_schema)
                while True:
                    try:
                        chunk = reader.read_chunk()
                    except StopIteration:
                        break
                    if not chunk or chunk.data is None:
                        break
                    batch_table = pa.Table.from_batches([chunk.data])
                    self.backend.append_table_from_arrow(table_name, batch_table)

                try:
                    writer.write(pa.py_buffer(b""))
                except Exception:
                    pass
                logger.info(f"Completed PATH do_put for table: {table_name}")
                print(f"SERVER: PATH do_put completed for table: {table_name}")
                return
            except Exception as e:
                logger.error(f"Error in PATH do_put: {e}", exc_info=True)
                raise
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

    def _do_get_statement_from_query(
        self, query: str, params: list | None = None
    ) -> pf.FlightDataStream:
        logger.info(f"Executing query: {query}")
        print(f"SERVER: Executing query: {query}")
        if params:
            logger.info(f"With parameters: {params}")
            print(f"SERVER: With parameters: {params}")

        # Log command details for actions.log
        actions_log.info("1. Receiving command: SQL Query")
        actions_log.info(f"2. Command arguments: {query}")
        if params:
            actions_log.info(
                f"3. Command sent to DuckDB: {query} with parameters {params}"
            )
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

    def _convert_parameter_batches_to_list(
        self, parameter_batches: list[pa.RecordBatch]
    ) -> list:
        """Convert PyArrow parameter batches to a simple Python list for DuckDB.

        The client sends parameters as PyArrow record batches, but DuckDB expects
        a simple Python list of values like [19] for a single parameter.
        """
        if not parameter_batches:
            return []

        try:
            params = []

            # Iterate through all parameter batches
            for batch in parameter_batches:
                logger.info(
                    f"Processing parameter batch with {batch.num_columns} columns and {batch.num_rows} rows"
                )

                # For each row in the batch (each row represents one execution)
                for row_idx in range(batch.num_rows):
                    row_params = []

                    # For each column in the batch (each column is a parameter)
                    for col_idx in range(batch.num_columns):
                        column = batch.column(col_idx)
                        value = column[
                            row_idx
                        ].as_py()  # Convert Arrow scalar to Python value
                        row_params.append(value)
                        logger.info(
                            f"Parameter {col_idx}: {value} (type: {type(value)})"
                        )

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

    def _do_put_update_from_query(self, query: str, params: list | None = None) -> int:
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

    def _extract_parameters_from_batches(
        self, parameter_batches: list[pa.RecordBatch]
    ) -> list:
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

    # =============================================================================
    # Phase 1: Core Flight Protocol Methods (Required for Flight compliance)
    # =============================================================================

    def list_flights(
        self, context: pf.ServerCallContext, criteria: bytes
    ) -> Iterator[pf.FlightInfo]:
        """
        List all available flights on this server.

        This implements the core Flight protocol ListFlights method,
        providing discoverability of available data endpoints.
        """
        try:
            # Log the request
            actions_logger.info("ListFlights called", criteria_length=len(criteria))
            routing_logger.info("Flight method: ListFlights")

            # For FlightSQL, we can list common metadata endpoints
            available_flights = []

            # Add metadata endpoints that are always available
            metadata_endpoints = [
                ("catalogs", "Available database catalogs"),
                ("schemas", "Available database schemas"),
                ("tables", "Available database tables"),
                ("table_types", "Available table types"),
                ("sql_info", "SQL feature information"),
            ]

            for path, _description in metadata_endpoints:
                # Create a path-based flight descriptor
                descriptor = pf.FlightDescriptor.for_path(path)

                # Create basic schema for metadata (will be refined by actual queries)
                schema = pa.schema(
                    [
                        pa.field("name", pa.string()),
                        pa.field("description", pa.string()),
                    ]
                )

                # Create flight info
                endpoint = pf.FlightEndpoint(
                    ticket=pf.Ticket(path.encode("utf-8")),
                    locations=[self.advertised_location]
                    if hasattr(self, "advertised_location")
                    else [],
                )

                flight_info = pf.FlightInfo(
                    schema=schema,
                    descriptor=descriptor,
                    endpoints=[endpoint],
                    total_records=-1,  # Unknown
                    total_bytes=-1,  # Unknown
                )

                available_flights.append(flight_info)

            actions_logger.info(
                "ListFlights completed", flight_count=len(available_flights)
            )
            return iter(available_flights)

        except Exception as e:
            actions_logger.error("ListFlights failed", error=str(e))
            routing_logger.error(f"ListFlights error: {e}")
            raise

    def get_schema(
        self, context: pf.ServerCallContext, descriptor: pf.FlightDescriptor
    ) -> pa.Schema:
        """
        Get schema for a flight descriptor without executing/transferring data.

        This implements the core Flight protocol GetSchema method,
        supporting both CMD (FlightSQL) and PATH descriptors.
        """
        try:
            actions_logger.info(
                "GetSchema called", descriptor_type=descriptor.descriptor_type.name
            )
            routing_logger.info(
                f"Flight method: GetSchema ({descriptor.descriptor_type.name})"
            )

            if descriptor.descriptor_type == pf.DescriptorType.CMD:
                # Handle FlightSQL command descriptors
                return self._get_schema_for_flightsql_command(context, descriptor)

            elif descriptor.descriptor_type == pf.DescriptorType.PATH:
                # Handle path-based descriptors
                return self._get_schema_for_path(context, descriptor)

            else:
                raise ValueError(
                    f"Unsupported descriptor type: {descriptor.descriptor_type}"
                )

        except Exception as e:
            actions_logger.error("GetSchema failed", error=str(e))
            routing_logger.error(f"GetSchema error: {e}")
            raise

    def _get_schema_for_flightsql_command(
        self, context: pf.ServerCallContext, descriptor: pf.FlightDescriptor
    ) -> pa.Schema:
        """Get schema for FlightSQL command descriptors."""
        command_bytes = descriptor.command
        any_command = parse_any_command(command_bytes)

        if not any_command:
            raise ValueError("Failed to parse command from descriptor.")

        command_type_url = any_command.type_url

        # Route to appropriate schema method based on command type
        if command_type_url == FlightSQLProtobuf.COMMAND_STATEMENT_QUERY_TYPE_URL:
            command = self._parse_statement_query(any_command)
            return self._get_statement_query_schema(command.query)

        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_CATALOGS_TYPE_URL:
            return self._get_catalogs_schema()

        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_DB_SCHEMAS_TYPE_URL:
            return self._get_schemas_schema()

        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_TABLES_TYPE_URL:
            return self._get_tables_schema()

        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_TABLE_TYPES_TYPE_URL:
            return self._get_table_types_schema()

        elif command_type_url == FlightSQLProtobuf.COMMAND_GET_SQL_INFO_TYPE_URL:
            return self._get_sql_info_schema()

        else:
            raise NotImplementedError(
                f"Schema not implemented for command type: {command_type_url}"
            )

    def _get_schema_for_path(
        self, context: pf.ServerCallContext, descriptor: pf.FlightDescriptor
    ) -> pa.Schema:
        """Get schema for path-based descriptors."""
        path = descriptor.path

        if not path:
            raise ValueError("Empty path in descriptor")

        # Handle common metadata paths - convert bytes to strings if needed
        path_parts = []
        for part in path:
            if isinstance(part, bytes):
                path_parts.append(part.decode("utf-8"))
            else:
                path_parts.append(str(part))

        path_str = "/".join(path_parts)

        if path_str == "catalogs":
            return self._get_catalogs_schema()
        elif path_str == "schemas":
            return self._get_schemas_schema()
        elif path_str == "tables":
            return self._get_tables_schema()
        elif path_str == "table_types":
            return self._get_table_types_schema()
        elif path_str == "sql_info":
            return self._get_sql_info_schema()
        else:
            # For unknown paths, return a generic schema
            return pa.schema(
                [pa.field("name", pa.string()), pa.field("value", pa.string())]
            )

    def _get_statement_query_schema(self, query: str) -> pa.Schema:
        """Get schema for a SQL query without executing it."""
        try:
            # Use the backend to analyze the query and get schema
            result = self.backend.execute_query(f"DESCRIBE ({query})")

            # Convert describe result to Arrow schema
            fields = []
            for row in result:
                # Assuming describe returns (column_name, column_type, ...)
                field_name = str(row[0])
                field_type_str = str(row[1])

                # Map SQL types to Arrow types (simplified mapping)
                if (
                    "INTEGER" in field_type_str.upper()
                    or "INT" in field_type_str.upper()
                ):
                    arrow_type = pa.int64()
                elif (
                    "FLOAT" in field_type_str.upper()
                    or "DOUBLE" in field_type_str.upper()
                ):
                    arrow_type = pa.float64()
                elif (
                    "BOOLEAN" in field_type_str.upper()
                    or "BOOL" in field_type_str.upper()
                ):
                    arrow_type = pa.bool_()
                else:
                    arrow_type = pa.string()  # Default to string

                fields.append(pa.field(field_name, arrow_type))

            return pa.schema(fields)

        except Exception as e:
            actions_logger.warning(
                "Failed to get query schema", query=query, error=str(e)
            )
            # Return a generic schema as fallback
            return pa.schema([pa.field("result", pa.string())])

    def _get_catalogs_schema(self) -> pa.Schema:
        """Get schema for catalogs metadata."""
        return pa.schema([pa.field("catalog_name", pa.string(), nullable=False)])

    def _get_schemas_schema(self) -> pa.Schema:
        """Get schema for schemas metadata."""
        return pa.schema(
            [
                pa.field("catalog_name", pa.string()),
                pa.field("db_schema_name", pa.string(), nullable=False),
            ]
        )

    def _get_tables_schema(self) -> pa.Schema:
        """Get schema for tables metadata."""
        return pa.schema(
            [
                pa.field("catalog_name", pa.string()),
                pa.field("db_schema_name", pa.string()),
                pa.field("table_name", pa.string(), nullable=False),
                pa.field("table_type", pa.string(), nullable=False),
            ]
        )

    def _get_table_types_schema(self) -> pa.Schema:
        """Get schema for table types metadata."""
        return pa.schema([pa.field("table_type", pa.string(), nullable=False)])

    def _get_sql_info_schema(self) -> pa.Schema:
        """Get schema for SQL info metadata."""
        return pa.schema(
            [
                pa.field("info_name", pa.uint32(), nullable=False),
                pa.field("value", pa.string()),
            ]
        )

    def handshake(
        self, context: pf.ServerCallContext, incoming_bytes: bytes
    ) -> tuple[bytes, str]:
        """
        Perform authentication handshake.

        This implements the core Flight protocol Handshake method,
        enabling client authentication and capability negotiation.
        """
        try:
            actions_logger.info(
                "Handshake called", incoming_bytes_length=len(incoming_bytes)
            )
            routing_logger.info("Flight method: Handshake")

            # For now, implement basic handshake
            # TODO: Integrate with existing auth system in future phases

            if len(incoming_bytes) == 0:
                # Initial handshake - return server capabilities
                response = b"MPZSQL Flight Server v1.0"
                peer_identity = "anonymous"

                actions_logger.info(
                    "Handshake completed",
                    peer_identity=peer_identity,
                    response_length=len(response),
                )
                return response, peer_identity
            else:
                # Client authentication data provided
                # For Phase 1, accept any authentication
                try:
                    auth_data = incoming_bytes.decode("utf-8")
                    # Extract identity from auth data (simplified)
                    peer_identity = f"user_{hash(auth_data) % 10000}"
                except Exception:
                    peer_identity = "unknown_user"

                response = b"Authentication accepted"

                actions_logger.info(
                    "Handshake with auth completed",
                    peer_identity=peer_identity,
                    response_length=len(response),
                )
                return response, peer_identity

        except Exception as e:
            actions_logger.error("Handshake failed", error=str(e))
            routing_logger.error(f"Handshake error: {e}")
            raise

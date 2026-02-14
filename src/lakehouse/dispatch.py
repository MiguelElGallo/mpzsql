"""Flight SQL protobuf command dispatch layer.

Since PyArrow exposes only ``FlightServerBase`` (not ``FlightSqlServerBase``),
this module manually unpacks Flight SQL protobuf commands and routes
them to the appropriate handler methods.

The design mirrors the C++ ``arrow::flight::sql::FlightSqlServerBase``:

* ``get_flight_info`` unpacks the command from the descriptor and
  dispatches to a ``get_flight_info_*`` handler.
* ``do_get`` unpacks the ticket and dispatches to a ``do_get_*`` handler.
* ``do_put`` unpacks the command and dispatches to a ``do_put_*`` handler.
* ``do_action`` routes by the action-type string and unpacks the body.

Subclasses override the handler methods they need (the default raises
``NotImplementedError`` which maps to gRPC ``UNIMPLEMENTED``).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.flight as flight

from lakehouse.proto import fs, pack_any, unpack_any

if TYPE_CHECKING:
    from collections.abc import Iterator

    from google.protobuf.message import Message

logger = logging.getLogger(__name__)

__all__ = [
    "ACTION_BEGIN_SAVEPOINT",
    "ACTION_BEGIN_TRANSACTION",
    "ACTION_CANCEL_QUERY",
    "ACTION_CLOSE_PREPARED_STATEMENT",
    "ACTION_CREATE_PREPARED_STATEMENT",
    "ACTION_END_SAVEPOINT",
    "ACTION_END_TRANSACTION",
    "FlightSqlServer",
]

# ---------------------------------------------------------------------------
# Flight SQL action-type string constants (per the specification)
# ---------------------------------------------------------------------------
ACTION_CREATE_PREPARED_STATEMENT = "CreatePreparedStatement"
ACTION_CLOSE_PREPARED_STATEMENT = "ClosePreparedStatement"
ACTION_BEGIN_TRANSACTION = "BeginTransaction"
ACTION_END_TRANSACTION = "EndTransaction"
ACTION_BEGIN_SAVEPOINT = "BeginSavepoint"
ACTION_END_SAVEPOINT = "EndSavepoint"
ACTION_CANCEL_QUERY = "CancelQuery"

_ALL_ACTIONS: list[tuple[str, str]] = [
    (ACTION_CREATE_PREPARED_STATEMENT, "Create a new prepared statement."),
    (ACTION_CLOSE_PREPARED_STATEMENT, "Close a prepared statement."),
    (ACTION_BEGIN_TRANSACTION, "Begin a new transaction."),
    (ACTION_END_TRANSACTION, "End a transaction (commit or rollback)."),
    (ACTION_BEGIN_SAVEPOINT, "Create a savepoint within a transaction."),
    (ACTION_END_SAVEPOINT, "Release or rollback to a savepoint."),
    (ACTION_CANCEL_QUERY, "Cancel a running query."),
]

# ---------------------------------------------------------------------------
# Dispatch tables: protobuf class → handler method name
# ---------------------------------------------------------------------------
# NOTE: CommandStatementSubstraitPlan is intentionally omitted — Substrait
# support is deferred to a later phase.
_GET_FLIGHT_INFO_DISPATCH: dict[type[Message], str] = {
    fs.CommandStatementQuery: "get_flight_info_statement",
    fs.CommandPreparedStatementQuery: "get_flight_info_prepared_statement",
    fs.CommandGetCatalogs: "get_flight_info_catalogs",
    fs.CommandGetDbSchemas: "get_flight_info_db_schemas",
    fs.CommandGetTables: "get_flight_info_tables",
    fs.CommandGetTableTypes: "get_flight_info_table_types",
    fs.CommandGetXdbcTypeInfo: "get_flight_info_xdbc_type_info",
    fs.CommandGetSqlInfo: "get_flight_info_sql_info",
    fs.CommandGetPrimaryKeys: "get_flight_info_primary_keys",
    fs.CommandGetImportedKeys: "get_flight_info_imported_keys",
    fs.CommandGetExportedKeys: "get_flight_info_exported_keys",
    fs.CommandGetCrossReference: "get_flight_info_cross_reference",
}

_DO_GET_DISPATCH: dict[type[Message], str] = {
    fs.TicketStatementQuery: "do_get_statement",
    fs.CommandPreparedStatementQuery: "do_get_prepared_statement",
    fs.CommandGetCatalogs: "do_get_catalogs",
    fs.CommandGetDbSchemas: "do_get_db_schemas",
    fs.CommandGetTables: "do_get_tables",
    fs.CommandGetTableTypes: "do_get_table_types",
    fs.CommandGetXdbcTypeInfo: "do_get_xdbc_type_info",
    fs.CommandGetSqlInfo: "do_get_sql_info",
    fs.CommandGetPrimaryKeys: "do_get_primary_keys",
    fs.CommandGetImportedKeys: "do_get_imported_keys",
    fs.CommandGetExportedKeys: "do_get_exported_keys",
    fs.CommandGetCrossReference: "do_get_cross_reference",
}

_DO_PUT_DISPATCH: dict[type[Message], str] = {
    fs.CommandStatementUpdate: "do_put_statement_update",
    fs.CommandPreparedStatementUpdate: "do_put_prepared_statement_update",
    fs.CommandPreparedStatementQuery: "do_put_prepared_statement_query",
    fs.CommandStatementIngest: "do_put_statement_ingest",
}

_DO_ACTION_DISPATCH: dict[str, tuple[str, type[Message]]] = {
    ACTION_CREATE_PREPARED_STATEMENT: (
        "create_prepared_statement",
        fs.ActionCreatePreparedStatementRequest,
    ),
    ACTION_CLOSE_PREPARED_STATEMENT: (
        "close_prepared_statement",
        fs.ActionClosePreparedStatementRequest,
    ),
    ACTION_BEGIN_TRANSACTION: (
        "begin_transaction",
        fs.ActionBeginTransactionRequest,
    ),
    ACTION_END_TRANSACTION: (
        "end_transaction",
        fs.ActionEndTransactionRequest,
    ),
    ACTION_BEGIN_SAVEPOINT: (
        "begin_savepoint",
        fs.ActionBeginSavepointRequest,
    ),
    ACTION_END_SAVEPOINT: (
        "end_savepoint",
        fs.ActionEndSavepointRequest,
    ),
    ACTION_CANCEL_QUERY: (
        "cancel_query",
        fs.ActionCancelQueryRequest,
    ),
}


# ---------------------------------------------------------------------------
# FlightSqlServer
# ---------------------------------------------------------------------------
class FlightSqlServer(flight.FlightServerBase):
    """Abstract base that replicates ``FlightSqlServerBase`` for Python.

    Override the ``get_flight_info_*``, ``do_get_*``, ``do_put_*``, and
    action handler methods in your concrete subclass.  The default
    implementation of each handler raises ``NotImplementedError``.
    """

    # ── Utility helpers ──────────────────────────────────────────

    @staticmethod
    def make_flight_info(
        descriptor: flight.FlightDescriptor,
        schema: pa.Schema,
    ) -> flight.FlightInfo:
        """Build a ``FlightInfo`` with a single endpoint using *descriptor.command* as the ticket.

        This mirrors the C++ ``GetFlightInfoForCommand`` helper used throughout
         for metadata commands.

        Args:
            descriptor: The original ``FlightDescriptor`` from the client.
            schema: The Arrow schema of the result set.

        Returns:
            A ``FlightInfo`` with one endpoint, ``total_records=-1``,
            ``total_bytes=-1``.
        """
        endpoint = flight.FlightEndpoint(flight.Ticket(descriptor.command), [])
        return flight.FlightInfo(schema, descriptor, [endpoint], -1, -1)

    @staticmethod
    def create_ticket(command: Message) -> flight.Ticket:
        """Serialize a protobuf *command* into a ``Ticket``.

        The command is packed as ``google.protobuf.Any`` and serialized so
        that ``do_get`` can later unpack it.

        Args:
            command: Any concrete Flight SQL protobuf message.

        Returns:
            A ``Ticket`` whose bytes are the serialized ``Any``.
        """
        return flight.Ticket(pack_any(command).SerializeToString())

    # ── Flight protocol overrides (dispatch layer) ───────────────

    def get_flight_info(
        self,
        context: flight.ServerCallContext,
        descriptor: flight.FlightDescriptor,
    ) -> flight.FlightInfo:
        """Unpack the Flight SQL command and dispatch to the typed handler.

        Args:
            context: The server call context.
            descriptor: Flight descriptor whose ``command`` bytes contain
                a serialized ``google.protobuf.Any`` wrapping a Flight SQL
                command message.

        Returns:
            ``FlightInfo`` describing the result set.

        Raises:
            NotImplementedError: If the command type is not recognised.
        """
        command = unpack_any(descriptor.command)
        handler_name = _GET_FLIGHT_INFO_DISPATCH.get(type(command))
        if handler_name is None:
            msg = f"Unsupported Flight SQL command for get_flight_info: {type(command).__name__}"
            raise NotImplementedError(msg)
        logger.debug("get_flight_info → %s", handler_name)
        return getattr(self, handler_name)(context, command, descriptor)

    def do_get(
        self,
        context: flight.ServerCallContext,
        ticket: flight.Ticket,
    ) -> flight.FlightDataStream:
        """Unpack the Flight SQL ticket and dispatch to the typed handler.

        Args:
            context: The server call context.
            ticket: Flight ticket whose bytes contain a serialized
                ``google.protobuf.Any`` wrapping a Flight SQL command or
                ``TicketStatementQuery``.

        Returns:
            A ``FlightDataStream`` (typically a ``RecordBatchStream``).

        Raises:
            NotImplementedError: If the ticket type is not recognised.
        """
        command = unpack_any(ticket.ticket)
        handler_name = _DO_GET_DISPATCH.get(type(command))
        if handler_name is None:
            msg = f"Unsupported Flight SQL ticket type for do_get: {type(command).__name__}"
            raise NotImplementedError(msg)
        logger.debug("do_get → %s", handler_name)
        return getattr(self, handler_name)(context, command)

    def do_put(
        self,
        context: flight.ServerCallContext,
        descriptor: flight.FlightDescriptor,
        reader: flight.MetadataRecordBatchReader,
        writer: flight.FlightMetadataWriter,
    ) -> None:
        """Unpack the Flight SQL command and dispatch to the typed handler.

        Args:
            context: The server call context.
            descriptor: Flight descriptor whose ``command`` bytes contain
                the serialized protobuf command.
            reader: Stream of record batches from the client.
            writer: Writer for sending metadata back to the client.

        Raises:
            NotImplementedError: If the command type is not recognised.
        """
        command = unpack_any(descriptor.command)
        handler_name = _DO_PUT_DISPATCH.get(type(command))
        if handler_name is None:
            msg = f"Unsupported Flight SQL command for do_put: {type(command).__name__}"
            raise NotImplementedError(msg)
        logger.debug("do_put → %s", handler_name)
        getattr(self, handler_name)(context, command, reader, writer)

    def do_action(
        self,
        context: flight.ServerCallContext,
        action: flight.Action,
    ) -> Iterator[flight.Result]:
        """Route Flight SQL actions by ``action.type`` string.

        The action body is unpacked as ``google.protobuf.Any`` → concrete
        request message, and the handler is called.  If the handler returns
        a protobuf message it is packed as ``Any`` and yielded as a
        ``Result``; if it returns ``None`` no result is yielded.

        Args:
            context: The server call context.
            action: The Flight action containing type and body.

        Yields:
            ``flight.Result`` containing the serialized response (if any).

        Raises:
            NotImplementedError: If the action type is not supported.
        """
        entry = _DO_ACTION_DISPATCH.get(action.type)
        if entry is None:
            msg = f"Unsupported Flight SQL action: {action.type!r}"
            raise NotImplementedError(msg)

        handler_name, request_cls = entry

        body_buf = action.body
        body_bytes = body_buf.to_pybytes() if body_buf is not None else b""

        request = unpack_any(body_bytes, request_cls)
        logger.debug("do_action %r → %s", action.type, handler_name)
        result = getattr(self, handler_name)(context, request)

        if result is not None:
            yield flight.Result(pack_any(result).SerializeToString())

    def list_actions(
        self,
        context: flight.ServerCallContext,
    ) -> list[flight.ActionType]:
        """Return all supported Flight SQL action types.

        Args:
            context: The server call context.

        Returns:
            List of ``ActionType`` descriptors.
        """
        return [flight.ActionType(t, d) for t, d in _ALL_ACTIONS]

    # ── get_flight_info handlers (override in subclass) ──────────

    def get_flight_info_statement(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandStatementQuery,
        descriptor: flight.FlightDescriptor,
    ) -> flight.FlightInfo:
        """Handle ``CommandStatementQuery`` in ``get_flight_info``."""
        raise NotImplementedError

    def get_flight_info_prepared_statement(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandPreparedStatementQuery,
        descriptor: flight.FlightDescriptor,
    ) -> flight.FlightInfo:
        """Handle ``CommandPreparedStatementQuery`` in ``get_flight_info``."""
        raise NotImplementedError

    def get_flight_info_catalogs(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetCatalogs,
        descriptor: flight.FlightDescriptor,
    ) -> flight.FlightInfo:
        """Handle ``CommandGetCatalogs`` in ``get_flight_info``."""
        raise NotImplementedError

    def get_flight_info_db_schemas(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetDbSchemas,
        descriptor: flight.FlightDescriptor,
    ) -> flight.FlightInfo:
        """Handle ``CommandGetDbSchemas`` in ``get_flight_info``."""
        raise NotImplementedError

    def get_flight_info_tables(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetTables,
        descriptor: flight.FlightDescriptor,
    ) -> flight.FlightInfo:
        """Handle ``CommandGetTables`` in ``get_flight_info``."""
        raise NotImplementedError

    def get_flight_info_table_types(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetTableTypes,
        descriptor: flight.FlightDescriptor,
    ) -> flight.FlightInfo:
        """Handle ``CommandGetTableTypes`` in ``get_flight_info``."""
        raise NotImplementedError

    def get_flight_info_xdbc_type_info(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetXdbcTypeInfo,
        descriptor: flight.FlightDescriptor,
    ) -> flight.FlightInfo:
        """Handle ``CommandGetXdbcTypeInfo`` in ``get_flight_info``."""
        raise NotImplementedError

    def get_flight_info_sql_info(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetSqlInfo,
        descriptor: flight.FlightDescriptor,
    ) -> flight.FlightInfo:
        """Handle ``CommandGetSqlInfo`` in ``get_flight_info``."""
        raise NotImplementedError

    def get_flight_info_primary_keys(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetPrimaryKeys,
        descriptor: flight.FlightDescriptor,
    ) -> flight.FlightInfo:
        """Handle ``CommandGetPrimaryKeys`` in ``get_flight_info``."""
        raise NotImplementedError

    def get_flight_info_imported_keys(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetImportedKeys,
        descriptor: flight.FlightDescriptor,
    ) -> flight.FlightInfo:
        """Handle ``CommandGetImportedKeys`` in ``get_flight_info``."""
        raise NotImplementedError

    def get_flight_info_exported_keys(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetExportedKeys,
        descriptor: flight.FlightDescriptor,
    ) -> flight.FlightInfo:
        """Handle ``CommandGetExportedKeys`` in ``get_flight_info``."""
        raise NotImplementedError

    def get_flight_info_cross_reference(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetCrossReference,
        descriptor: flight.FlightDescriptor,
    ) -> flight.FlightInfo:
        """Handle ``CommandGetCrossReference`` in ``get_flight_info``."""
        raise NotImplementedError

    # ── do_get handlers (override in subclass) ───────────────────

    def do_get_statement(
        self,
        context: flight.ServerCallContext,
        command: fs.TicketStatementQuery,
    ) -> flight.FlightDataStream:
        """Handle ``TicketStatementQuery`` in ``do_get``."""
        raise NotImplementedError

    def do_get_prepared_statement(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandPreparedStatementQuery,
    ) -> flight.FlightDataStream:
        """Handle ``CommandPreparedStatementQuery`` in ``do_get``."""
        raise NotImplementedError

    def do_get_catalogs(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetCatalogs,
    ) -> flight.FlightDataStream:
        """Handle ``CommandGetCatalogs`` in ``do_get``."""
        raise NotImplementedError

    def do_get_db_schemas(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetDbSchemas,
    ) -> flight.FlightDataStream:
        """Handle ``CommandGetDbSchemas`` in ``do_get``."""
        raise NotImplementedError

    def do_get_tables(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetTables,
    ) -> flight.FlightDataStream:
        """Handle ``CommandGetTables`` in ``do_get``."""
        raise NotImplementedError

    def do_get_table_types(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetTableTypes,
    ) -> flight.FlightDataStream:
        """Handle ``CommandGetTableTypes`` in ``do_get``."""
        raise NotImplementedError

    def do_get_xdbc_type_info(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetXdbcTypeInfo,
    ) -> flight.FlightDataStream:
        """Handle ``CommandGetXdbcTypeInfo`` in ``do_get``."""
        raise NotImplementedError

    def do_get_sql_info(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetSqlInfo,
    ) -> flight.FlightDataStream:
        """Handle ``CommandGetSqlInfo`` in ``do_get``."""
        raise NotImplementedError

    def do_get_primary_keys(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetPrimaryKeys,
    ) -> flight.FlightDataStream:
        """Handle ``CommandGetPrimaryKeys`` in ``do_get``."""
        raise NotImplementedError

    def do_get_imported_keys(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetImportedKeys,
    ) -> flight.FlightDataStream:
        """Handle ``CommandGetImportedKeys`` in ``do_get``."""
        raise NotImplementedError

    def do_get_exported_keys(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetExportedKeys,
    ) -> flight.FlightDataStream:
        """Handle ``CommandGetExportedKeys`` in ``do_get``."""
        raise NotImplementedError

    def do_get_cross_reference(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetCrossReference,
    ) -> flight.FlightDataStream:
        """Handle ``CommandGetCrossReference`` in ``do_get``."""
        raise NotImplementedError

    # ── do_put handlers (override in subclass) ───────────────────

    def do_put_statement_update(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandStatementUpdate,
        reader: flight.MetadataRecordBatchReader,
        writer: flight.FlightMetadataWriter,
    ) -> None:
        """Handle ``CommandStatementUpdate`` in ``do_put``."""
        raise NotImplementedError

    def do_put_prepared_statement_update(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandPreparedStatementUpdate,
        reader: flight.MetadataRecordBatchReader,
        writer: flight.FlightMetadataWriter,
    ) -> None:
        """Handle ``CommandPreparedStatementUpdate`` in ``do_put``."""
        raise NotImplementedError

    def do_put_prepared_statement_query(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandPreparedStatementQuery,
        reader: flight.MetadataRecordBatchReader,
        writer: flight.FlightMetadataWriter,
    ) -> None:
        """Handle ``CommandPreparedStatementQuery`` in ``do_put`` (parameter binding)."""
        raise NotImplementedError

    def do_put_statement_ingest(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandStatementIngest,
        reader: flight.MetadataRecordBatchReader,
        writer: flight.FlightMetadataWriter,
    ) -> None:
        """Handle ``CommandStatementIngest`` in ``do_put``."""
        raise NotImplementedError

    # ── do_action handlers (override in subclass) ────────────────

    def create_prepared_statement(
        self,
        context: flight.ServerCallContext,
        request: fs.ActionCreatePreparedStatementRequest,
    ) -> fs.ActionCreatePreparedStatementResult:
        """Handle ``CreatePreparedStatement`` action.

        Args:
            context: The server call context.
            request: The parsed request containing the SQL query.

        Returns:
            Result with the prepared-statement handle and schema.
        """
        raise NotImplementedError

    def close_prepared_statement(
        self,
        context: flight.ServerCallContext,
        request: fs.ActionClosePreparedStatementRequest,
    ) -> None:
        """Handle ``ClosePreparedStatement`` action.

        Args:
            context: The server call context.
            request: The parsed request containing the statement handle.
        """
        raise NotImplementedError

    def begin_transaction(
        self,
        context: flight.ServerCallContext,
        request: fs.ActionBeginTransactionRequest,
    ) -> fs.ActionBeginTransactionResult:
        """Handle ``BeginTransaction`` action.

        Args:
            context: The server call context.
            request: The parsed begin-transaction request.

        Returns:
            Result with the transaction identifier.
        """
        raise NotImplementedError

    def end_transaction(
        self,
        context: flight.ServerCallContext,
        request: fs.ActionEndTransactionRequest,
    ) -> None:
        """Handle ``EndTransaction`` action (commit or rollback).

        Args:
            context: The server call context.
            request: The parsed end-transaction request.
        """
        raise NotImplementedError

    def begin_savepoint(
        self,
        context: flight.ServerCallContext,
        request: fs.ActionBeginSavepointRequest,
    ) -> fs.ActionBeginSavepointResult:
        """Handle ``BeginSavepoint`` action.

        Args:
            context: The server call context.
            request: The parsed begin-savepoint request.

        Returns:
            Result with the savepoint identifier.
        """
        raise NotImplementedError

    def end_savepoint(
        self,
        context: flight.ServerCallContext,
        request: fs.ActionEndSavepointRequest,
    ) -> None:
        """Handle ``EndSavepoint`` action (release or rollback).

        Args:
            context: The server call context.
            request: The parsed end-savepoint request.
        """
        raise NotImplementedError

    def cancel_query(
        self,
        context: flight.ServerCallContext,
        request: fs.ActionCancelQueryRequest,
    ) -> fs.ActionCancelQueryResult:
        """Handle ``CancelQuery`` action.

        Args:
            context: The server call context.
            request: The parsed cancel-query request.

        Returns:
            Result indicating the cancellation outcome.
        """
        raise NotImplementedError

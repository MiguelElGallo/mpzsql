"""Tests for lakehouse.dispatch — Flight SQL command dispatch layer."""

from __future__ import annotations

from unittest.mock import MagicMock

import pyarrow as pa
import pyarrow.flight as flight
import pytest

from lakehouse.dispatch import (
    ACTION_BEGIN_SAVEPOINT,
    ACTION_BEGIN_TRANSACTION,
    ACTION_CANCEL_QUERY,
    ACTION_CLOSE_PREPARED_STATEMENT,
    ACTION_CREATE_PREPARED_STATEMENT,
    ACTION_END_SAVEPOINT,
    ACTION_END_TRANSACTION,
    FlightSqlServer,
)
from lakehouse.proto import fs, pack_any, unpack_any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_descriptor(msg):
    """Build a CMD FlightDescriptor from a protobuf message."""
    any_bytes = pack_any(msg).SerializeToString()
    return flight.FlightDescriptor.for_command(any_bytes)


def _make_ticket(msg):
    """Build a Ticket from a protobuf message."""
    any_bytes = pack_any(msg).SerializeToString()
    return flight.Ticket(any_bytes)


def _make_action(action_type, request_msg):
    """Build a Flight Action from a type string and request protobuf."""
    body = pack_any(request_msg).SerializeToString()
    return flight.Action(action_type, body)


# ---------------------------------------------------------------------------
# Concrete subclass for testing (overrides all needed handlers)
# ---------------------------------------------------------------------------
class StubFlightSqlServer(FlightSqlServer):
    """Minimal concrete subclass that records which handler was called."""

    def __init__(self):
        self.last_handler = None
        self.last_command = None

    def _record(self, name, command=None):
        self.last_handler = name
        self.last_command = command


# ---------------------------------------------------------------------------
# Test: FlightSqlServer.make_flight_info
# ---------------------------------------------------------------------------
class TestMakeFlightInfo:
    def test_returns_flight_info_with_correct_schema(self):
        schema = pa.schema([("col1", pa.int32())])
        descriptor = _make_descriptor(fs.CommandGetCatalogs())
        info = FlightSqlServer.make_flight_info(descriptor, schema)

        assert isinstance(info, flight.FlightInfo)
        assert info.schema == schema
        assert info.total_records == -1
        assert info.total_bytes == -1

    def test_endpoint_ticket_matches_descriptor_cmd(self):
        descriptor = _make_descriptor(fs.CommandGetTableTypes())
        schema = pa.schema([("table_type", pa.utf8())])
        info = FlightSqlServer.make_flight_info(descriptor, schema)

        endpoints = list(info.endpoints)
        assert len(endpoints) == 1
        assert endpoints[0].ticket.ticket == descriptor.command

    def test_roundtrip_unpack_ticket(self):
        """Ticket from make_flight_info can be unpacked back to the command."""
        cmd = fs.CommandGetCatalogs()
        descriptor = _make_descriptor(cmd)
        schema = pa.schema([("catalog_name", pa.utf8())])
        info = FlightSqlServer.make_flight_info(descriptor, schema)

        ticket_bytes = next(iter(info.endpoints)).ticket.ticket
        roundtripped = unpack_any(ticket_bytes, fs.CommandGetCatalogs)
        assert isinstance(roundtripped, fs.CommandGetCatalogs)


# ---------------------------------------------------------------------------
# Test: FlightSqlServer.create_ticket
# ---------------------------------------------------------------------------
class TestCreateTicket:
    def test_ticket_is_flight_ticket(self):
        cmd = fs.TicketStatementQuery(statement_handle=b"abc")
        ticket = FlightSqlServer.create_ticket(cmd)
        assert isinstance(ticket, flight.Ticket)

    def test_ticket_roundtrip(self):
        cmd = fs.TicketStatementQuery(statement_handle=b"handle-123")
        ticket = FlightSqlServer.create_ticket(cmd)
        restored = unpack_any(ticket.ticket, fs.TicketStatementQuery)
        assert restored.statement_handle == b"handle-123"


# ---------------------------------------------------------------------------
# Test: get_flight_info dispatch
# ---------------------------------------------------------------------------
class TestGetFlightInfoDispatch:
    """Verify get_flight_info unpacks the command and dispatches correctly."""

    @pytest.fixture()
    def server(self):
        return StubFlightSqlServer()

    def _dispatch(self, server, cmd, handler_name, return_value=None):
        """Patch the handler on server, call get_flight_info, verify dispatch."""
        mock_handler = MagicMock(return_value=return_value)
        setattr(server, handler_name, mock_handler)
        descriptor = _make_descriptor(cmd)
        result = server.get_flight_info(MagicMock(), descriptor)
        mock_handler.assert_called_once()
        # First arg is context, second is the unpacked command, third is descriptor
        call_args = mock_handler.call_args
        assert isinstance(call_args[0][1], type(cmd))
        return result

    def test_statement_query(self, server):
        info = MagicMock(spec=flight.FlightInfo)
        cmd = fs.CommandStatementQuery(query="SELECT 1")
        self._dispatch(server, cmd, "get_flight_info_statement", info)

    def test_prepared_statement_query(self, server):
        info = MagicMock(spec=flight.FlightInfo)
        cmd = fs.CommandPreparedStatementQuery(prepared_statement_handle=b"h")
        self._dispatch(server, cmd, "get_flight_info_prepared_statement", info)

    def test_catalogs(self, server):
        info = MagicMock(spec=flight.FlightInfo)
        self._dispatch(server, fs.CommandGetCatalogs(), "get_flight_info_catalogs", info)

    def test_db_schemas(self, server):
        info = MagicMock(spec=flight.FlightInfo)
        self._dispatch(server, fs.CommandGetDbSchemas(), "get_flight_info_db_schemas", info)

    def test_tables(self, server):
        info = MagicMock(spec=flight.FlightInfo)
        self._dispatch(server, fs.CommandGetTables(), "get_flight_info_tables", info)

    def test_table_types(self, server):
        info = MagicMock(spec=flight.FlightInfo)
        self._dispatch(server, fs.CommandGetTableTypes(), "get_flight_info_table_types", info)

    def test_xdbc_type_info(self, server):
        info = MagicMock(spec=flight.FlightInfo)
        self._dispatch(server, fs.CommandGetXdbcTypeInfo(), "get_flight_info_xdbc_type_info", info)

    def test_sql_info(self, server):
        info = MagicMock(spec=flight.FlightInfo)
        self._dispatch(server, fs.CommandGetSqlInfo(), "get_flight_info_sql_info", info)

    def test_primary_keys(self, server):
        info = MagicMock(spec=flight.FlightInfo)
        cmd = fs.CommandGetPrimaryKeys(table="t")
        self._dispatch(server, cmd, "get_flight_info_primary_keys", info)

    def test_imported_keys(self, server):
        info = MagicMock(spec=flight.FlightInfo)
        cmd = fs.CommandGetImportedKeys(table="t")
        self._dispatch(server, cmd, "get_flight_info_imported_keys", info)

    def test_exported_keys(self, server):
        info = MagicMock(spec=flight.FlightInfo)
        cmd = fs.CommandGetExportedKeys(table="t")
        self._dispatch(server, cmd, "get_flight_info_exported_keys", info)

    def test_cross_reference(self, server):
        info = MagicMock(spec=flight.FlightInfo)
        cmd = fs.CommandGetCrossReference(pk_table="pk", fk_table="fk")
        self._dispatch(server, cmd, "get_flight_info_cross_reference", info)

    def test_unknown_command_raises(self, server):
        """An unrecognised command type should raise NotImplementedError."""
        # Use DoPutUpdateResult as a message NOT in the get_flight_info dispatch
        descriptor = _make_descriptor(fs.DoPutUpdateResult(record_count=0))
        with pytest.raises(NotImplementedError, match="Unsupported"):
            server.get_flight_info(MagicMock(), descriptor)


# ---------------------------------------------------------------------------
# Test: do_get dispatch
# ---------------------------------------------------------------------------
class TestDoGetDispatch:
    @pytest.fixture()
    def server(self):
        return StubFlightSqlServer()

    def _dispatch(self, server, cmd, handler_name, return_value=None):
        mock_handler = MagicMock(return_value=return_value)
        setattr(server, handler_name, mock_handler)
        ticket = _make_ticket(cmd)
        result = server.do_get(MagicMock(), ticket)
        mock_handler.assert_called_once()
        return result

    def test_ticket_statement_query(self, server):
        cmd = fs.TicketStatementQuery(statement_handle=b"h")
        self._dispatch(server, cmd, "do_get_statement")

    def test_prepared_statement(self, server):
        cmd = fs.CommandPreparedStatementQuery(prepared_statement_handle=b"h")
        self._dispatch(server, cmd, "do_get_prepared_statement")

    def test_catalogs(self, server):
        self._dispatch(server, fs.CommandGetCatalogs(), "do_get_catalogs")

    def test_db_schemas(self, server):
        self._dispatch(server, fs.CommandGetDbSchemas(), "do_get_db_schemas")

    def test_tables(self, server):
        self._dispatch(server, fs.CommandGetTables(), "do_get_tables")

    def test_table_types(self, server):
        self._dispatch(server, fs.CommandGetTableTypes(), "do_get_table_types")

    def test_xdbc_type_info(self, server):
        self._dispatch(server, fs.CommandGetXdbcTypeInfo(), "do_get_xdbc_type_info")

    def test_sql_info(self, server):
        self._dispatch(server, fs.CommandGetSqlInfo(), "do_get_sql_info")

    def test_primary_keys(self, server):
        self._dispatch(server, fs.CommandGetPrimaryKeys(table="t"), "do_get_primary_keys")

    def test_imported_keys(self, server):
        self._dispatch(server, fs.CommandGetImportedKeys(table="t"), "do_get_imported_keys")

    def test_exported_keys(self, server):
        self._dispatch(server, fs.CommandGetExportedKeys(table="t"), "do_get_exported_keys")

    def test_cross_reference(self, server):
        cmd = fs.CommandGetCrossReference(pk_table="pk", fk_table="fk")
        self._dispatch(server, cmd, "do_get_cross_reference")

    def test_unknown_ticket_raises(self, server):
        ticket = _make_ticket(fs.DoPutUpdateResult(record_count=0))
        with pytest.raises(NotImplementedError, match="Unsupported"):
            server.do_get(MagicMock(), ticket)


# ---------------------------------------------------------------------------
# Test: do_put dispatch
# ---------------------------------------------------------------------------
class TestDoPutDispatch:
    @pytest.fixture()
    def server(self):
        return StubFlightSqlServer()

    def _dispatch(self, server, cmd, handler_name):
        mock_handler = MagicMock()
        setattr(server, handler_name, mock_handler)
        descriptor = _make_descriptor(cmd)
        reader = MagicMock()
        writer = MagicMock()
        server.do_put(MagicMock(), descriptor, reader, writer)
        mock_handler.assert_called_once()
        # Verify reader and writer are passed through
        call_args = mock_handler.call_args[0]
        assert call_args[2] is reader
        assert call_args[3] is writer

    def test_statement_update(self, server):
        cmd = fs.CommandStatementUpdate(query="INSERT INTO t VALUES (1)")
        self._dispatch(server, cmd, "do_put_statement_update")

    def test_prepared_statement_update(self, server):
        cmd = fs.CommandPreparedStatementUpdate(prepared_statement_handle=b"h")
        self._dispatch(server, cmd, "do_put_prepared_statement_update")

    def test_prepared_statement_query(self, server):
        cmd = fs.CommandPreparedStatementQuery(prepared_statement_handle=b"h")
        self._dispatch(server, cmd, "do_put_prepared_statement_query")

    def test_statement_ingest(self, server):
        cmd = fs.CommandStatementIngest(table="t")
        self._dispatch(server, cmd, "do_put_statement_ingest")

    def test_unknown_command_raises(self, server):
        descriptor = _make_descriptor(fs.DoPutUpdateResult(record_count=0))
        with pytest.raises(NotImplementedError, match="Unsupported"):
            server.do_put(MagicMock(), descriptor, MagicMock(), MagicMock())


# ---------------------------------------------------------------------------
# Test: do_action dispatch
# ---------------------------------------------------------------------------
class TestDoActionDispatch:
    @pytest.fixture()
    def server(self):
        return StubFlightSqlServer()

    def test_create_prepared_statement(self, server):
        request = fs.ActionCreatePreparedStatementRequest(query="SELECT 1")
        result_msg = fs.ActionCreatePreparedStatementResult(prepared_statement_handle=b"h")
        server.create_prepared_statement = MagicMock(return_value=result_msg)

        action = _make_action(ACTION_CREATE_PREPARED_STATEMENT, request)
        results = list(server.do_action(MagicMock(), action))

        server.create_prepared_statement.assert_called_once()
        assert len(results) == 1
        # Verify the result can be unpacked
        restored = unpack_any(
            results[0].body.to_pybytes(),
            fs.ActionCreatePreparedStatementResult,
        )
        assert restored.prepared_statement_handle == b"h"

    def test_close_prepared_statement_no_result(self, server):
        """ClosePreparedStatement returns None → no Result yielded."""
        request = fs.ActionClosePreparedStatementRequest(prepared_statement_handle=b"h")
        server.close_prepared_statement = MagicMock(return_value=None)

        action = _make_action(ACTION_CLOSE_PREPARED_STATEMENT, request)
        results = list(server.do_action(MagicMock(), action))

        server.close_prepared_statement.assert_called_once()
        assert len(results) == 0

    def test_begin_transaction(self, server):
        request = fs.ActionBeginTransactionRequest()
        result_msg = fs.ActionBeginTransactionResult(transaction_id=b"txn-1")
        server.begin_transaction = MagicMock(return_value=result_msg)

        action = _make_action(ACTION_BEGIN_TRANSACTION, request)
        results = list(server.do_action(MagicMock(), action))

        assert len(results) == 1
        restored = unpack_any(
            results[0].body.to_pybytes(),
            fs.ActionBeginTransactionResult,
        )
        assert restored.transaction_id == b"txn-1"

    def test_end_transaction_no_result(self, server):
        request = fs.ActionEndTransactionRequest(
            transaction_id=b"txn-1",
            action=fs.ActionEndTransactionRequest.END_TRANSACTION_COMMIT,
        )
        server.end_transaction = MagicMock(return_value=None)

        action = _make_action(ACTION_END_TRANSACTION, request)
        results = list(server.do_action(MagicMock(), action))
        assert len(results) == 0

    def test_begin_savepoint(self, server):
        request = fs.ActionBeginSavepointRequest(transaction_id=b"txn-1", name="sp1")
        result_msg = fs.ActionBeginSavepointResult(savepoint_id=b"sp-1")
        server.begin_savepoint = MagicMock(return_value=result_msg)

        action = _make_action(ACTION_BEGIN_SAVEPOINT, request)
        results = list(server.do_action(MagicMock(), action))

        assert len(results) == 1

    def test_end_savepoint_no_result(self, server):
        request = fs.ActionEndSavepointRequest(
            savepoint_id=b"sp-1",
            action=fs.ActionEndSavepointRequest.END_SAVEPOINT_RELEASE,
        )
        server.end_savepoint = MagicMock(return_value=None)

        action = _make_action(ACTION_END_SAVEPOINT, request)
        results = list(server.do_action(MagicMock(), action))
        assert len(results) == 0

    def test_cancel_query(self, server):
        request = fs.ActionCancelQueryRequest()
        result_msg = fs.ActionCancelQueryResult(
            result=fs.ActionCancelQueryResult.CANCEL_RESULT_CANCELLED,
        )
        server.cancel_query = MagicMock(return_value=result_msg)

        action = _make_action(ACTION_CANCEL_QUERY, request)
        results = list(server.do_action(MagicMock(), action))

        assert len(results) == 1

    def test_unknown_action_raises(self, server):
        action = flight.Action("UnknownAction", b"")
        with pytest.raises(NotImplementedError, match="Unsupported"):
            list(server.do_action(MagicMock(), action))

    def test_empty_body_raises(self, server):
        """An action with no body should raise ValueError from unpack_any."""
        action = flight.Action(ACTION_CREATE_PREPARED_STATEMENT, b"")
        with pytest.raises(ValueError, match="empty bytes"):
            list(server.do_action(MagicMock(), action))


# ---------------------------------------------------------------------------
# Test: list_actions
# ---------------------------------------------------------------------------
class TestListActions:
    def test_returns_all_action_types(self):
        server = StubFlightSqlServer()
        actions = server.list_actions(MagicMock())
        action_types = {a.type for a in actions}

        assert ACTION_CREATE_PREPARED_STATEMENT in action_types
        assert ACTION_CLOSE_PREPARED_STATEMENT in action_types
        assert ACTION_BEGIN_TRANSACTION in action_types
        assert ACTION_END_TRANSACTION in action_types
        assert ACTION_BEGIN_SAVEPOINT in action_types
        assert ACTION_END_SAVEPOINT in action_types
        assert ACTION_CANCEL_QUERY in action_types

    def test_all_have_descriptions(self):
        server = StubFlightSqlServer()
        actions = server.list_actions(MagicMock())
        for action in actions:
            assert action.description, f"Action {action.type} has no description"


# ---------------------------------------------------------------------------
# Test: handler stubs raise NotImplementedError
# ---------------------------------------------------------------------------
class TestHandlerStubsRaiseNotImplemented:
    """Every default handler should raise NotImplementedError."""

    @pytest.fixture()
    def server(self):
        return StubFlightSqlServer()

    # -- get_flight_info handlers --

    @pytest.mark.parametrize(
        "method",
        [
            "get_flight_info_statement",
            "get_flight_info_prepared_statement",
            "get_flight_info_catalogs",
            "get_flight_info_db_schemas",
            "get_flight_info_tables",
            "get_flight_info_table_types",
            "get_flight_info_xdbc_type_info",
            "get_flight_info_sql_info",
            "get_flight_info_primary_keys",
            "get_flight_info_imported_keys",
            "get_flight_info_exported_keys",
            "get_flight_info_cross_reference",
        ],
    )
    def test_get_flight_info_stubs(self, server, method):
        with pytest.raises(NotImplementedError):
            getattr(server, method)(MagicMock(), MagicMock(), MagicMock())

    # -- do_get handlers --

    @pytest.mark.parametrize(
        "method",
        [
            "do_get_statement",
            "do_get_prepared_statement",
            "do_get_catalogs",
            "do_get_db_schemas",
            "do_get_tables",
            "do_get_table_types",
            "do_get_xdbc_type_info",
            "do_get_sql_info",
            "do_get_primary_keys",
            "do_get_imported_keys",
            "do_get_exported_keys",
            "do_get_cross_reference",
        ],
    )
    def test_do_get_stubs(self, server, method):
        with pytest.raises(NotImplementedError):
            getattr(server, method)(MagicMock(), MagicMock())

    # -- do_put handlers --

    @pytest.mark.parametrize(
        "method",
        [
            "do_put_statement_update",
            "do_put_prepared_statement_update",
            "do_put_prepared_statement_query",
            "do_put_statement_ingest",
        ],
    )
    def test_do_put_stubs(self, server, method):
        with pytest.raises(NotImplementedError):
            getattr(server, method)(MagicMock(), MagicMock(), MagicMock(), MagicMock())

    # -- do_action handlers --

    @pytest.mark.parametrize(
        "method",
        [
            "create_prepared_statement",
            "close_prepared_statement",
            "begin_transaction",
            "end_transaction",
            "begin_savepoint",
            "end_savepoint",
            "cancel_query",
        ],
    )
    def test_action_stubs(self, server, method):
        with pytest.raises(NotImplementedError):
            getattr(server, method)(MagicMock(), MagicMock())


# ---------------------------------------------------------------------------
# Test: dispatch table completeness
# ---------------------------------------------------------------------------
class TestDispatchTableCompleteness:
    """Verify dispatch tables have matching handler methods."""

    def test_get_flight_info_handlers_exist(self):
        from lakehouse.dispatch import _GET_FLIGHT_INFO_DISPATCH

        server = FlightSqlServer.__new__(FlightSqlServer)
        for handler_name in _GET_FLIGHT_INFO_DISPATCH.values():
            assert hasattr(server, handler_name), f"Missing handler: {handler_name}"

    def test_do_get_handlers_exist(self):
        from lakehouse.dispatch import _DO_GET_DISPATCH

        server = FlightSqlServer.__new__(FlightSqlServer)
        for handler_name in _DO_GET_DISPATCH.values():
            assert hasattr(server, handler_name), f"Missing handler: {handler_name}"

    def test_do_put_handlers_exist(self):
        from lakehouse.dispatch import _DO_PUT_DISPATCH

        server = FlightSqlServer.__new__(FlightSqlServer)
        for handler_name in _DO_PUT_DISPATCH.values():
            assert hasattr(server, handler_name), f"Missing handler: {handler_name}"

    def test_do_action_handlers_exist(self):
        from lakehouse.dispatch import _DO_ACTION_DISPATCH

        server = FlightSqlServer.__new__(FlightSqlServer)
        for handler_name, _ in _DO_ACTION_DISPATCH.values():
            assert hasattr(server, handler_name), f"Missing handler: {handler_name}"

    def test_dispatch_table_sizes(self):
        from lakehouse.dispatch import (
            _DO_ACTION_DISPATCH,
            _DO_GET_DISPATCH,
            _DO_PUT_DISPATCH,
            _GET_FLIGHT_INFO_DISPATCH,
        )

        assert len(_GET_FLIGHT_INFO_DISPATCH) == 12
        assert len(_DO_GET_DISPATCH) == 12
        assert len(_DO_PUT_DISPATCH) == 4
        assert len(_DO_ACTION_DISPATCH) == 7  # includes CancelQuery

"""DuckDB session management — connection pooling and query execution.

This module mirrors the C++ ``ClientSession`` / session-map pattern found in
.  Each client gets its own DuckDB
connection (created from the shared ``DuckDB`` instance) so that prepared
statements, transactions, and session-level state remain isolated.

Key design decisions carried over from the C++ original:

* **One connection per session** — ``duckdb.DuckDBPyConnection.cursor()``
  creates a lightweight child cursor that shares the underlying catalog but
  has its own transaction context.
* **Global + per-session locking** — a global :class:`threading.Lock` guards
  the session map; each :class:`ClientSession` has its own lock for internal
  mutations (prepared statements, transactions).  DuckDB I/O is performed
  outside the global lock to avoid blocking unrelated sessions.
* **Prepared statements stored at session level** — in the C++ code they
  live in the ``Impl`` class next to the session map.  Here we co-locate
  them inside :class:`ClientSession` for cleaner ownership.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import duckdb

logger = logging.getLogger(__name__)

__all__ = ["ClientSession", "SessionManager"]


# ---------------------------------------------------------------------------
# ClientSession
# ---------------------------------------------------------------------------
@dataclass
class ClientSession:
    """Per-client session state.

    Each session owns a DuckDB cursor derived from the shared database
    instance, plus bookkeeping for prepared statements and transactions.



    Attributes:
        session_id: Unique identifier (UUID string), set by auth middleware.
        username: Authenticated username from bearer auth.
        connection: DuckDB cursor for this session.
        created_at: UTC timestamp when the session was created.
        prepared_statements: Map of handle → DuckDB prepared statement.
        open_transactions: Set of active transaction handles for this session.
    """

    session_id: str
    username: str
    connection: duckdb.DuckDBPyConnection
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    prepared_statements: dict[str, duckdb.DuckDBPyConnection] = field(default_factory=dict)
    open_transactions: set[str] = field(default_factory=set)
    _lock: threading.Lock = field(
        init=False, default_factory=threading.Lock, repr=False, compare=False
    )

    def close(self) -> None:
        """Release all resources held by this session.

        Closes prepared-statement cursors, rolls back open transactions, and
        closes the underlying DuckDB cursor.
        """
        with self._lock:
            # Close prepared statements first (they may hold refs to connection)
            stmt_count = len(self.prepared_statements)
            for cursor in self.prepared_statements.values():
                with contextlib.suppress(duckdb.Error):
                    cursor.close()
            self.prepared_statements.clear()

            # Roll back any open transactions
            txn_count = len(self.open_transactions)
            if txn_count > 0:
                try:
                    self.connection.rollback()
                except duckdb.Error:
                    logger.debug(
                        "Rollback during session close failed (session=%s)",
                        self.session_id,
                    )
            self.open_transactions.clear()

            # Close the cursor
            try:
                self.connection.close()
            except duckdb.Error:
                logger.debug(
                    "Connection close failed (session=%s)",
                    self.session_id,
                )

        if stmt_count or txn_count:
            logger.debug(
                "Session %s closed: released %d prepared statement(s), %d transaction(s)",
                self.session_id,
                stmt_count,
                txn_count,
            )


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------
class SessionManager:
    """Thread-safe store for :class:`ClientSession` objects.

    Mirrors the session portion of ``DuckDBFlightSqlServer::Impl`` in the C++
    code, which uses ``unordered_map<string, shared_ptr<ClientSession>>``
    guarded by a ``shared_mutex``.

    Args:
        db: The parent DuckDB connection from which per-session cursors are
            derived via ``db.cursor()``.
    """

    def __init__(
        self,
        db: duckdb.DuckDBPyConnection,
        *,
        ducklake_alias: str = "",
    ) -> None:
        """Initialise the session manager with a parent DuckDB connection.

        Args:
            db: The parent DuckDB connection from which per-session cursors
                are derived via ``db.cursor()``.
            ducklake_alias: When non-empty, every new cursor will execute
                ``USE <alias>`` to set the DuckLake catalog as default.
        """
        self._db = db
        self._ducklake_alias = ducklake_alias
        self._sessions: dict[str, ClientSession] = {}
        self._lock = threading.Lock()

    # -- public API ---------------------------------------------------------

    def get_or_create(
        self,
        session_id: str,
        username: str = "",
    ) -> ClientSession:
        """Return an existing session or create a new one.

        This mirrors the C++ ``GetClientSession`` double-check pattern:
        first try to find the session, then create if absent — both under
        lock to prevent races.

        Args:
            session_id: Unique session identifier (typically from auth middleware).
            username: Authenticated username.

        Returns:
            The existing or newly created :class:`ClientSession`.

        Note:
            The returned session is a live reference.  Callers must not use
            a session after it has been closed by another thread.
        """
        with self._lock:
            existing = self._sessions.get(session_id)
            if existing is not None:
                return existing

            cursor = self._db.cursor()
            # ATTACH is catalog-level (visible to all cursors), but USE is
            # connection-level — new cursors default to 'memory' unless we
            # explicitly point them at the DuckLake database.
            if self._ducklake_alias:
                cursor.execute(f"USE {self._ducklake_alias}")
            # DuckDB cursors don't inherit GLOBAL settings from the parent
            # connection; force the curl transport so the Azure C++ SDK can
            # find the CA certificate bundle on Linux containers.
            with contextlib.suppress(Exception):
                cursor.execute("SET azure_transport_option_type = 'curl'")
            session = ClientSession(
                session_id=session_id,
                username=username,
                connection=cursor,
            )
            self._sessions[session_id] = session
            logger.debug(
                "Created session %s for user=%s",
                session_id,
                username,
            )
            return session

    def get(self, session_id: str) -> ClientSession | None:
        """Look up an existing session without creating one.

        Args:
            session_id: Session identifier.

        Returns:
            The session if it exists, otherwise ``None``.
        """
        with self._lock:
            return self._sessions.get(session_id)

    def close_session(self, session_id: str) -> bool:
        """Close and remove a session.

        Mirrors C++ ``CloseSession`` which erases the session from the map
        and lets the shared_ptr destructor release the DuckDB connection.

        Args:
            session_id: Session to close.

        Returns:
            ``True`` if the session existed and was closed, ``False`` if not found.
        """
        with self._lock:
            session = self._sessions.pop(session_id, None)

        if session is None:
            return False

        # Close outside the lock to avoid holding it during I/O
        session.close()
        logger.info("Session %s closed", session_id)
        return True

    def close_all(self) -> int:
        """Close every active session and return the count.

        Mirrors C++ ``ReleaseAllSessions`` which clears both the prepared
        statement map and the session map under their respective locks.

        Returns:
            Number of sessions that were closed.
        """
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()

        for session in sessions:
            session.close()

        count = len(sessions)
        if count:
            logger.info("Released %d active session(s)", count)
        return count

    @property
    def active_count(self) -> int:
        """Return the number of currently active sessions."""
        with self._lock:
            return len(self._sessions)

    def session_ids(self) -> list[str]:
        """Return a snapshot of all active session IDs.

        Returns:
            A list (not a view) of session ID strings.
        """
        with self._lock:
            return list(self._sessions.keys())

    # -- prepared statement helpers -----------------------------------------

    def add_prepared_statement(
        self,
        session_id: str,
        handle: str | None = None,
    ) -> tuple[str, duckdb.DuckDBPyConnection]:
        """Create a prepared-statement cursor within the given session.

        Each prepared statement gets its own child cursor so that parameter
        binding and execution don't interfere with other statements.

        Args:
            session_id: The owning session.
            handle: Optional explicit handle (UUID string).  If ``None``, one
                    is generated automatically.

        Returns:
            A ``(handle, cursor)`` tuple.

        Raises:
            KeyError: If *session_id* does not exist.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"Session not found: {session_id}")

        with session._lock:
            if handle is None:
                handle = str(uuid.uuid4())

            cursor = session.connection.cursor()
            # DuckDB cursors don't inherit settings; force curl transport
            # for Azure blob SSL CA cert resolution in containers.
            with contextlib.suppress(Exception):
                cursor.execute("SET azure_transport_option_type = 'curl'")
            session.prepared_statements[handle] = cursor

        logger.debug(
            "Prepared statement %s created in session %s",
            handle,
            session_id,
        )
        return handle, cursor

    def get_prepared_statement(
        self,
        session_id: str,
        handle: str,
    ) -> duckdb.DuckDBPyConnection:
        """Retrieve a prepared-statement cursor by handle.

        Args:
            session_id: The owning session.
            handle: The statement handle returned by
                    :meth:`add_prepared_statement`.

        Returns:
            The DuckDB cursor for the prepared statement.

        Raises:
            KeyError: If either *session_id* or *handle* is not found.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"Session not found: {session_id}")

        with session._lock:
            cursor = session.prepared_statements.get(handle)
            if cursor is None:
                raise KeyError(f"Prepared statement not found: {handle}")
            return cursor

    def close_prepared_statement(
        self,
        session_id: str,
        handle: str,
    ) -> bool:
        """Remove a prepared statement.

        Mirrors C++ ``ClosePreparedStatement`` which erases the handle from
        the ``prepared_statements_`` map.

        Args:
            session_id: The owning session.
            handle: The statement handle.

        Returns:
            ``True`` if the statement was found and removed.

        Raises:
            KeyError: If *session_id* does not exist.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"Session not found: {session_id}")

        with session._lock:
            cursor = session.prepared_statements.pop(handle, None)

        if cursor is None:
            return False

        with contextlib.suppress(duckdb.Error):
            cursor.close()
        logger.debug(
            "Prepared statement %s closed in session %s",
            handle,
            session_id,
        )
        return True

    # -- transaction helpers ------------------------------------------------

    def begin_transaction(self, session_id: str) -> str:
        """Begin a transaction and return its handle.

        Mirrors C++ ``BeginTransaction`` which generates a UUID handle, stores
        it in ``open_transactions_``, and executes ``BEGIN TRANSACTION``.

        DuckDB supports only one active transaction per connection; calling
        this while a transaction is already open raises :class:`ValueError`.

        Args:
            session_id: The owning session.

        Returns:
            A UUID transaction handle.

        Raises:
            KeyError: If *session_id* does not exist.
            ValueError: If the session already has an active transaction.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"Session not found: {session_id}")

        with session._lock:
            if session.open_transactions:
                raise ValueError(f"Session {session_id} already has an active transaction")

            handle = str(uuid.uuid4())
            session.connection.begin()
            session.open_transactions.add(handle)

        logger.debug(
            "Transaction %s started in session %s",
            handle,
            session_id,
        )
        return handle

    def end_transaction(
        self,
        session_id: str,
        handle: str,
        *,
        commit: bool = True,
    ) -> None:
        """Commit or rollback a transaction.

        Mirrors C++ ``EndTransaction`` which either commits or rolls back,
        then erases the handle from ``open_transactions_``.

        The handle is always removed, even if the commit/rollback fails, to
        avoid leaving stale entries.

        Args:
            session_id: The owning session.
            handle: The transaction handle from :meth:`begin_transaction`.
            commit: If ``True``, commit; otherwise rollback.

        Raises:
            KeyError: If *session_id* or *handle* is not found.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"Session not found: {session_id}")

        with session._lock:
            if handle not in session.open_transactions:
                raise KeyError(f"Transaction not found: {handle}")

            try:
                if commit:
                    session.connection.commit()
                else:
                    session.connection.rollback()
            finally:
                session.open_transactions.discard(handle)

        action = "committed" if commit else "rolled back"
        logger.debug(
            "Transaction %s %s in session %s",
            handle,
            action,
            session_id,
        )

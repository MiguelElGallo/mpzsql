"""Tests for lakehouse.session — DuckDB session management."""

from __future__ import annotations

import threading
from datetime import UTC

import duckdb
import pytest

from lakehouse.session import ClientSession, SessionManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def db():
    """In-memory DuckDB connection shared across a test."""
    conn = duckdb.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def mgr(db):
    """SessionManager backed by the in-memory DuckDB instance."""
    return SessionManager(db)


# ═══════════════════════════════════════════════════════════════════════════
#  ClientSession
# ═══════════════════════════════════════════════════════════════════════════
class TestClientSession:
    """Unit tests for the ClientSession dataclass."""

    def test_construction_defaults(self, db):
        cursor = db.cursor()
        session = ClientSession(session_id="s1", username="alice", connection=cursor)

        assert session.session_id == "s1"
        assert session.username == "alice"
        assert session.connection is cursor
        assert session.prepared_statements == {}
        assert session.open_transactions == set()

    def test_created_at_is_utc(self, db):
        session = ClientSession(session_id="s1", username="u", connection=db.cursor())
        assert session.created_at.tzinfo is UTC

    def test_close_releases_resources(self, db):
        cursor = db.cursor()
        session = ClientSession(session_id="s1", username="u", connection=cursor)

        # Add a child cursor as a prepared statement
        child = cursor.cursor()
        session.prepared_statements["h1"] = child

        # Mark an open transaction (simulate)
        session.open_transactions.add("txn1")

        session.close()

        assert session.prepared_statements == {}
        assert session.open_transactions == set()

    def test_close_idempotent(self, db):
        """Calling close twice should not raise."""
        session = ClientSession(session_id="s1", username="u", connection=db.cursor())
        session.close()
        # Second close on an already-closed cursor should be suppressed
        session.close()

    def test_close_rolls_back_open_transaction(self, db):
        cursor = db.cursor()
        # Create a table and begin a transaction
        cursor.execute("CREATE TABLE t (x INT)")
        cursor.begin()
        cursor.execute("INSERT INTO t VALUES (1)")

        session = ClientSession(session_id="s1", username="u", connection=cursor)
        session.open_transactions.add("txn1")
        session.close()

        # The insert should have been rolled back
        result = db.execute("SELECT COUNT(*) FROM t").fetchone()
        assert result[0] == 0


# ═══════════════════════════════════════════════════════════════════════════
#  SessionManager — session lifecycle
# ═══════════════════════════════════════════════════════════════════════════
class TestSessionLifecycle:
    """Tests for session creation, lookup, and teardown."""

    def test_get_or_create_new_session(self, mgr):
        session = mgr.get_or_create("s1", "alice")

        assert session.session_id == "s1"
        assert session.username == "alice"
        assert isinstance(session.connection, duckdb.DuckDBPyConnection)
        assert mgr.active_count == 1

    def test_get_or_create_returns_existing(self, mgr):
        s1 = mgr.get_or_create("s1", "alice")
        s2 = mgr.get_or_create("s1", "alice")

        assert s1 is s2
        assert mgr.active_count == 1

    def test_get_or_create_different_ids(self, mgr):
        mgr.get_or_create("s1", "alice")
        mgr.get_or_create("s2", "bob")

        assert mgr.active_count == 2

    def test_get_existing(self, mgr):
        created = mgr.get_or_create("s1", "alice")
        found = mgr.get("s1")

        assert found is created

    def test_get_missing_returns_none(self, mgr):
        assert mgr.get("nonexistent") is None

    def test_close_session_existing(self, mgr):
        mgr.get_or_create("s1", "alice")
        assert mgr.close_session("s1") is True
        assert mgr.active_count == 0
        assert mgr.get("s1") is None

    def test_close_session_missing(self, mgr):
        assert mgr.close_session("nonexistent") is False

    def test_close_all(self, mgr):
        mgr.get_or_create("s1", "alice")
        mgr.get_or_create("s2", "bob")
        mgr.get_or_create("s3", "charlie")

        count = mgr.close_all()
        assert count == 3
        assert mgr.active_count == 0

    def test_close_all_empty(self, mgr):
        assert mgr.close_all() == 0

    def test_session_ids_snapshot(self, mgr):
        mgr.get_or_create("s1", "alice")
        mgr.get_or_create("s2", "bob")

        ids = mgr.session_ids()
        assert sorted(ids) == ["s1", "s2"]
        # Returned list should be independent of internal state
        mgr.close_session("s1")
        assert sorted(ids) == ["s1", "s2"]  # snapshot unchanged

    def test_active_count(self, mgr):
        assert mgr.active_count == 0
        mgr.get_or_create("s1")
        assert mgr.active_count == 1
        mgr.get_or_create("s2")
        assert mgr.active_count == 2
        mgr.close_session("s1")
        assert mgr.active_count == 1


# ═══════════════════════════════════════════════════════════════════════════
#  SessionManager — prepared statements
# ═══════════════════════════════════════════════════════════════════════════
class TestPreparedStatements:
    """Tests for prepared statement CRUD operations."""

    def test_add_auto_handle(self, mgr):
        mgr.get_or_create("s1", "alice")
        handle, cursor = mgr.add_prepared_statement("s1")

        assert isinstance(handle, str)
        assert len(handle) == 36  # UUID format
        assert isinstance(cursor, duckdb.DuckDBPyConnection)

    def test_add_explicit_handle(self, mgr):
        mgr.get_or_create("s1", "alice")
        handle, cursor = mgr.add_prepared_statement("s1", handle="my-handle")

        assert handle == "my-handle"
        assert isinstance(cursor, duckdb.DuckDBPyConnection)

    def test_get_existing(self, mgr):
        mgr.get_or_create("s1", "alice")
        handle, added_cursor = mgr.add_prepared_statement("s1")

        fetched = mgr.get_prepared_statement("s1", handle)
        assert fetched is added_cursor

    def test_get_missing_handle(self, mgr):
        mgr.get_or_create("s1", "alice")
        with pytest.raises(KeyError, match="Prepared statement not found"):
            mgr.get_prepared_statement("s1", "no-such-handle")

    def test_get_missing_session(self, mgr):
        with pytest.raises(KeyError, match="Session not found"):
            mgr.get_prepared_statement("no-session", "no-handle")

    def test_close_existing(self, mgr):
        mgr.get_or_create("s1", "alice")
        handle, _ = mgr.add_prepared_statement("s1")

        assert mgr.close_prepared_statement("s1", handle) is True
        # Should no longer be retrievable
        with pytest.raises(KeyError, match="Prepared statement not found"):
            mgr.get_prepared_statement("s1", handle)

    def test_close_missing_handle(self, mgr):
        mgr.get_or_create("s1", "alice")
        assert mgr.close_prepared_statement("s1", "no-such-handle") is False

    def test_close_missing_session(self, mgr):
        with pytest.raises(KeyError, match="Session not found"):
            mgr.close_prepared_statement("no-session", "handle")

    def test_add_missing_session(self, mgr):
        with pytest.raises(KeyError, match="Session not found"):
            mgr.add_prepared_statement("no-session")

    def test_multiple_statements_per_session(self, mgr):
        mgr.get_or_create("s1", "alice")
        h1, c1 = mgr.add_prepared_statement("s1")
        h2, c2 = mgr.add_prepared_statement("s1")

        assert h1 != h2
        assert c1 is not c2
        assert mgr.get_prepared_statement("s1", h1) is c1
        assert mgr.get_prepared_statement("s1", h2) is c2

    def test_prepared_stmt_executes_query(self, mgr):
        """Prepared statement cursors can actually execute queries."""
        mgr.get_or_create("s1", "alice")
        _, cursor = mgr.add_prepared_statement("s1")

        cursor.execute("SELECT 42 AS answer")
        result = cursor.fetchone()
        assert result[0] == 42


# ═══════════════════════════════════════════════════════════════════════════
#  SessionManager — transactions
# ═══════════════════════════════════════════════════════════════════════════
class TestTransactions:
    """Tests for transaction begin/end lifecycle."""

    def test_begin_returns_handle(self, mgr):
        mgr.get_or_create("s1", "alice")
        handle = mgr.begin_transaction("s1")

        assert isinstance(handle, str)
        assert len(handle) == 36  # UUID

    def test_commit_transaction(self, mgr, db):
        mgr.get_or_create("s1", "alice")
        session = mgr.get("s1")
        session.connection.execute("CREATE TABLE t (x INT)")

        handle = mgr.begin_transaction("s1")
        session.connection.execute("INSERT INTO t VALUES (42)")
        mgr.end_transaction("s1", handle, commit=True)

        # Data should be visible from parent connection
        result = db.execute("SELECT x FROM t").fetchone()
        assert result[0] == 42

    def test_rollback_transaction(self, mgr, db):
        mgr.get_or_create("s1", "alice")
        session = mgr.get("s1")
        session.connection.execute("CREATE TABLE t (x INT)")

        handle = mgr.begin_transaction("s1")
        session.connection.execute("INSERT INTO t VALUES (99)")
        mgr.end_transaction("s1", handle, commit=False)

        # Data should NOT be visible (rolled back)
        result = db.execute("SELECT COUNT(*) FROM t").fetchone()
        assert result[0] == 0

    def test_begin_missing_session(self, mgr):
        with pytest.raises(KeyError, match="Session not found"):
            mgr.begin_transaction("no-session")

    def test_end_missing_session(self, mgr):
        with pytest.raises(KeyError, match="Session not found"):
            mgr.end_transaction("no-session", "handle")

    def test_end_missing_handle(self, mgr):
        mgr.get_or_create("s1", "alice")
        with pytest.raises(KeyError, match="Transaction not found"):
            mgr.end_transaction("s1", "no-such-handle")

    def test_double_begin_raises_value_error(self, mgr):
        mgr.get_or_create("s1", "alice")
        mgr.begin_transaction("s1")

        with pytest.raises(ValueError, match="already has an active transaction"):
            mgr.begin_transaction("s1")

    def test_end_clears_handle(self, mgr):
        mgr.get_or_create("s1", "alice")
        handle = mgr.begin_transaction("s1")
        mgr.end_transaction("s1", handle, commit=True)

        # Handle should be gone
        with pytest.raises(KeyError, match="Transaction not found"):
            mgr.end_transaction("s1", handle)

    def test_end_allows_new_begin(self, mgr):
        """After ending a transaction, a new one can be started."""
        mgr.get_or_create("s1", "alice")

        h1 = mgr.begin_transaction("s1")
        mgr.end_transaction("s1", h1, commit=True)

        h2 = mgr.begin_transaction("s1")
        assert h2 != h1
        mgr.end_transaction("s1", h2, commit=True)


# ═══════════════════════════════════════════════════════════════════════════
#  SessionManager — close_session cleans up resources
# ═══════════════════════════════════════════════════════════════════════════
class TestCloseSessionCleanup:
    """Verify that closing a session releases all sub-resources."""

    def test_close_cleans_prepared_statements(self, mgr):
        mgr.get_or_create("s1", "alice")
        mgr.add_prepared_statement("s1")
        mgr.add_prepared_statement("s1")

        mgr.close_session("s1")
        # Session gone — methods should raise KeyError
        with pytest.raises(KeyError, match="Session not found"):
            mgr.add_prepared_statement("s1")

    def test_close_cleans_transactions(self, mgr):
        mgr.get_or_create("s1", "alice")
        mgr.begin_transaction("s1")

        mgr.close_session("s1")
        with pytest.raises(KeyError, match="Session not found"):
            mgr.begin_transaction("s1")

    def test_close_all_cleans_everything(self, mgr):
        for i in range(3):
            sid = f"s{i}"
            mgr.get_or_create(sid, f"user{i}")
            mgr.add_prepared_statement(sid)

        count = mgr.close_all()
        assert count == 3
        assert mgr.active_count == 0


# ═══════════════════════════════════════════════════════════════════════════
#  Thread safety
# ═══════════════════════════════════════════════════════════════════════════
class TestThreadSafety:
    """Basic concurrency smoke tests."""

    def test_concurrent_session_creation(self, mgr):
        """Multiple threads creating different sessions should not race."""
        results: dict[str, ClientSession] = {}
        errors: list[Exception] = []

        def create(sid):
            try:
                results[sid] = mgr.get_or_create(sid, f"user-{sid}")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=create, args=(f"s{i}",)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert mgr.active_count == 20

    def test_concurrent_get_or_create_same_id(self, mgr):
        """Multiple threads calling get_or_create with the same ID get the same session."""
        results: list[ClientSession] = []
        lock = threading.Lock()

        def get_same():
            session = mgr.get_or_create("shared", "user")
            with lock:
                results.append(session)

        threads = [threading.Thread(target=get_same) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should be the exact same object
        assert len(results) == 10
        assert all(r is results[0] for r in results)
        assert mgr.active_count == 1


# ═══════════════════════════════════════════════════════════════════════════
#  Broken cursor on close
# ═══════════════════════════════════════════════════════════════════════════
class TestBrokenCursorClose:
    """Verify that closing a session with an already-closed cursor does not raise."""

    def test_close_handles_broken_cursor(self, mgr):
        """Close a session whose underlying DuckDB cursor is already closed."""
        mgr.get_or_create("broken", "user")
        session = mgr.get("broken")
        # Manually break the cursor
        session.connection.close()
        # Closing the session should not propagate an error
        mgr.close_session("broken")
        assert mgr.active_count == 0


# ═══════════════════════════════════════════════════════════════════════════
#  DuckLake alias — USE on new cursors (D.3)
# ═══════════════════════════════════════════════════════════════════════════
class TestDuckLakeAlias:
    """Tests for SessionManager with ducklake_alias."""

    def test_no_alias_does_not_use(self, db):
        """When ducklake_alias is empty, no USE is executed."""
        mgr = SessionManager(db, ducklake_alias="")
        session = mgr.get_or_create("s1", "user")
        # Default database should be 'memory'
        result = session.connection.execute("SELECT current_database()").fetchone()
        assert result[0] == "memory"

    def test_alias_sets_default_database(self, db):
        """When ducklake_alias is set, new cursors USE that database."""
        # Create a schema/database to USE
        db.execute("ATTACH ':memory:' AS testdb")
        mgr = SessionManager(db, ducklake_alias="testdb")
        session = mgr.get_or_create("s1", "user")
        result = session.connection.execute("SELECT current_database()").fetchone()
        assert result[0] == "testdb"

    def test_alias_applies_to_each_new_session(self, db):
        """Each new session's cursor gets USE applied independently."""
        db.execute("ATTACH ':memory:' AS testdb")
        mgr = SessionManager(db, ducklake_alias="testdb")
        s1 = mgr.get_or_create("s1", "user1")
        s2 = mgr.get_or_create("s2", "user2")
        for session in [s1, s2]:
            result = session.connection.execute("SELECT current_database()").fetchone()
            assert result[0] == "testdb"

    def test_alias_does_not_affect_existing_sessions(self, db):
        """Returning an existing session does not re-execute USE."""
        db.execute("ATTACH ':memory:' AS testdb")
        mgr = SessionManager(db, ducklake_alias="testdb")
        s1 = mgr.get_or_create("s1", "user")
        # Manually switch the cursor to a different database
        s1.connection.execute("USE memory")
        # get_or_create should return the same session without re-USEing
        s1_again = mgr.get_or_create("s1", "user")
        assert s1_again is s1
        result = s1_again.connection.execute("SELECT current_database()").fetchone()
        # Should still be 'memory' since USE was not re-executed
        assert result[0] == "memory"

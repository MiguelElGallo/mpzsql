"""
Tests for transaction management module.
Tests for mpzsql.transaction module providing transaction handling.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest

from mpzsql.transaction import Transaction, TransactionManager, TransactionState


class TestTransactionState:
    """Test cases for TransactionState enum."""

    def test_transaction_states(self) -> None:
        """Test that all expected transaction states exist."""
        assert TransactionState.ACTIVE.value == "ACTIVE"
        assert TransactionState.COMMITTED.value == "COMMITTED"
        assert TransactionState.ROLLED_BACK.value == "ROLLED_BACK"

    def test_transaction_state_values(self) -> None:
        """Test transaction state values are correct."""
        states = [state.value for state in TransactionState]
        expected_states = ["ACTIVE", "COMMITTED", "ROLLED_BACK"]
        assert set(states) == set(expected_states)


class TestTransaction:
    """Test cases for Transaction class."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.transaction_id = "txn_test123"
        self.session_id = "session_456"
        self.mock_connection = Mock()

        self.transaction = Transaction(
            transaction_id=self.transaction_id,
            session_id=self.session_id,
            connection=self.mock_connection,
        )

    def test_initialization(self) -> None:
        """Test Transaction initialization."""
        assert self.transaction.transaction_id == self.transaction_id
        assert self.transaction.session_id == self.session_id
        assert self.transaction.connection == self.mock_connection
        assert self.transaction.state == TransactionState.ACTIVE
        assert isinstance(self.transaction.created_at, datetime)
        assert self.transaction.statements == []

    def test_add_statement(self) -> None:
        """Test adding statements to transaction."""
        statement1 = "SELECT * FROM users"
        statement2 = "INSERT INTO logs VALUES (1, 'test')"

        self.transaction.add_statement(statement1)
        self.transaction.add_statement(statement2)

        assert len(self.transaction.statements) == 2
        assert self.transaction.statements[0]["statement"] == statement1
        assert self.transaction.statements[1]["statement"] == statement2

        # Verify timestamps are added
        assert "timestamp" in self.transaction.statements[0]
        assert "timestamp" in self.transaction.statements[1]
        assert isinstance(self.transaction.statements[0]["timestamp"], datetime)

    def test_commit_success(self) -> None:
        """Test successful transaction commit."""
        self.transaction.commit()

        self.mock_connection.commit.assert_called_once()
        assert self.transaction.state == TransactionState.COMMITTED

    def test_commit_already_committed(self) -> None:
        """Test committing an already committed transaction."""
        self.transaction.state = TransactionState.COMMITTED

        with pytest.raises(
            ValueError,
            match="Cannot commit transaction in state TransactionState.COMMITTED",
        ):
            self.transaction.commit()

        self.mock_connection.commit.assert_not_called()

    def test_commit_already_rolled_back(self) -> None:
        """Test committing a rolled back transaction."""
        self.transaction.state = TransactionState.ROLLED_BACK

        with pytest.raises(
            ValueError,
            match="Cannot commit transaction in state TransactionState.ROLLED_BACK",
        ):
            self.transaction.commit()

        self.mock_connection.commit.assert_not_called()

    def test_commit_connection_error(self) -> None:
        """Test commit with connection error."""
        self.mock_connection.commit.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            self.transaction.commit()

        # State should remain ACTIVE after failed commit
        assert self.transaction.state == TransactionState.ACTIVE

    def test_rollback_success(self) -> None:
        """Test successful transaction rollback."""
        self.transaction.rollback()

        self.mock_connection.rollback.assert_called_once()
        assert self.transaction.state == TransactionState.ROLLED_BACK

    def test_rollback_already_committed(self) -> None:
        """Test rolling back a committed transaction."""
        self.transaction.state = TransactionState.COMMITTED

        with pytest.raises(
            ValueError,
            match="Cannot rollback transaction in state TransactionState.COMMITTED",
        ):
            self.transaction.rollback()

        self.mock_connection.rollback.assert_not_called()

    def test_rollback_already_rolled_back(self) -> None:
        """Test rolling back an already rolled back transaction."""
        self.transaction.state = TransactionState.ROLLED_BACK

        with pytest.raises(
            ValueError,
            match="Cannot rollback transaction in state TransactionState.ROLLED_BACK",
        ):
            self.transaction.rollback()

        self.mock_connection.rollback.assert_not_called()

    def test_rollback_connection_error(self) -> None:
        """Test rollback with connection error."""
        self.mock_connection.rollback.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            self.transaction.rollback()

        # State should remain ACTIVE after failed rollback
        assert self.transaction.state == TransactionState.ACTIVE

    def test_transaction_with_statements(self) -> None:
        """Test transaction with multiple statements."""
        statements = [
            "BEGIN",
            "SELECT * FROM users WHERE id = 1",
            "UPDATE users SET last_login = NOW() WHERE id = 1",
            "INSERT INTO user_sessions (user_id, session_id) VALUES (1, 'abc123')",
        ]

        for stmt in statements:
            self.transaction.add_statement(stmt)

        assert len(self.transaction.statements) == 4

        # Verify all statements are recorded with timestamps
        for i, stmt in enumerate(statements):
            assert self.transaction.statements[i]["statement"] == stmt
            assert isinstance(self.transaction.statements[i]["timestamp"], datetime)

    def test_created_at_timestamp(self) -> None:
        """Test that created_at timestamp is recent."""
        creation_time = datetime.now(timezone.utc)
        transaction = Transaction("txn_test", "session_test", Mock())

        # Should be created within last few seconds
        time_diff = abs((transaction.created_at - creation_time).total_seconds())
        assert time_diff < 5  # Within 5 seconds


class TestTransactionManager:
    """Test cases for TransactionManager class."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.manager = TransactionManager()
        self.mock_connection = Mock()
        self.session_id = "test_session_123"

    def test_initialization(self) -> None:
        """Test TransactionManager initialization."""
        assert isinstance(self.manager.transactions, dict)
        assert len(self.manager.transactions) == 0

    def test_begin_transaction(self) -> None:
        """Test beginning a new transaction."""
        transaction_id = self.manager.begin_transaction(
            self.session_id, self.mock_connection
        )

        assert transaction_id.startswith("txn_")
        assert len(transaction_id) == 20  # "txn_" + 16 hex chars

        # Verify connection.begin() was called
        self.mock_connection.begin.assert_called_once()

        # Verify transaction was stored
        assert transaction_id in self.manager.transactions
        transaction = self.manager.transactions[transaction_id]
        assert transaction.transaction_id == transaction_id
        assert transaction.session_id == self.session_id
        assert transaction.connection == self.mock_connection
        assert transaction.state == TransactionState.ACTIVE

    def test_begin_multiple_transactions(self) -> None:
        """Test beginning multiple transactions."""
        session1 = "session_1"
        session2 = "session_2"
        connection1 = Mock()
        connection2 = Mock()

        txn_id1 = self.manager.begin_transaction(session1, connection1)
        txn_id2 = self.manager.begin_transaction(session2, connection2)

        assert txn_id1 != txn_id2
        assert len(self.manager.transactions) == 2

        assert self.manager.transactions[txn_id1].session_id == session1
        assert self.manager.transactions[txn_id2].session_id == session2

    def test_get_transaction_exists(self) -> None:
        """Test getting an existing transaction."""
        transaction_id = self.manager.begin_transaction(
            self.session_id, self.mock_connection
        )

        retrieved = self.manager.get_transaction(transaction_id)

        assert retrieved is not None
        assert retrieved.transaction_id == transaction_id
        assert retrieved.session_id == self.session_id

    def test_get_transaction_not_exists(self) -> None:
        """Test getting a non-existent transaction."""
        fake_id = "txn_nonexistent123"

        retrieved = self.manager.get_transaction(fake_id)

        assert retrieved is None

    def test_end_transaction_commit(self) -> None:
        """Test ending transaction with commit action."""
        transaction_id = self.manager.begin_transaction(
            self.session_id, self.mock_connection
        )

        # Action 1 = COMMIT
        result = self.manager.end_transaction(transaction_id, 1)

        assert result is True
        self.mock_connection.commit.assert_called_once()

        # Transaction should be removed from active transactions
        assert transaction_id not in self.manager.transactions

    def test_end_transaction_rollback(self) -> None:
        """Test ending transaction with rollback action."""
        transaction_id = self.manager.begin_transaction(
            self.session_id, self.mock_connection
        )

        # Action 2 = ROLLBACK
        result = self.manager.end_transaction(transaction_id, 2)

        assert result is True
        self.mock_connection.rollback.assert_called_once()

        # Transaction should be removed from active transactions
        assert transaction_id not in self.manager.transactions

    def test_end_transaction_unknown_action(self) -> None:
        """Test ending transaction with unknown action."""
        transaction_id = self.manager.begin_transaction(
            self.session_id, self.mock_connection
        )

        # Action 99 = Unknown
        result = self.manager.end_transaction(transaction_id, 99)

        assert result is False

        # Transaction should still exist since operation failed
        assert transaction_id in self.manager.transactions

    def test_end_transaction_not_exists(self) -> None:
        """Test ending a non-existent transaction."""
        fake_id = "txn_nonexistent123"

        result = self.manager.end_transaction(fake_id, 1)

        assert result is False

    def test_end_transaction_commit_error(self) -> None:
        """Test ending transaction when commit fails."""
        transaction_id = self.manager.begin_transaction(
            self.session_id, self.mock_connection
        )
        self.mock_connection.commit.side_effect = Exception("Commit failed")

        result = self.manager.end_transaction(transaction_id, 1)

        assert result is False

        # Transaction should still exist since operation failed
        assert transaction_id in self.manager.transactions

    def test_end_transaction_rollback_error(self) -> None:
        """Test ending transaction when rollback fails."""
        transaction_id = self.manager.begin_transaction(
            self.session_id, self.mock_connection
        )
        self.mock_connection.rollback.side_effect = Exception("Rollback failed")

        result = self.manager.end_transaction(transaction_id, 2)

        assert result is False

        # Transaction should still exist since operation failed
        assert transaction_id in self.manager.transactions

    def test_cleanup_abandoned_transactions_none_abandoned(self) -> None:
        """Test cleanup when no transactions are abandoned."""
        transaction_id = self.manager.begin_transaction(
            self.session_id, self.mock_connection
        )

        # Clean up with default 30 minute timeout
        self.manager.cleanup_abandoned_transactions()

        # Recent transaction should not be cleaned up
        assert transaction_id in self.manager.transactions

    def test_cleanup_abandoned_transactions_with_abandoned(self) -> None:
        """Test cleanup with abandoned transactions."""
        transaction_id = self.manager.begin_transaction(
            self.session_id, self.mock_connection
        )

        # Manually set transaction creation time to be old
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        self.manager.transactions[transaction_id].created_at = old_time

        # Clean up with 1 hour timeout
        self.manager.cleanup_abandoned_transactions(timeout_minutes=60)

        # Old transaction should be cleaned up (rolled back)
        assert transaction_id not in self.manager.transactions
        self.mock_connection.rollback.assert_called()

    def test_cleanup_abandoned_transactions_custom_timeout(self) -> None:
        """Test cleanup with custom timeout."""
        transaction_id = self.manager.begin_transaction(
            self.session_id, self.mock_connection
        )

        # Set transaction to be 45 minutes old
        old_time = datetime.now(timezone.utc) - timedelta(minutes=45)
        self.manager.transactions[transaction_id].created_at = old_time

        # Clean up with 30 minute timeout (should clean up)
        self.manager.cleanup_abandoned_transactions(timeout_minutes=30)
        assert transaction_id not in self.manager.transactions

        # Create another transaction and set it to be 15 minutes old
        transaction_id2 = self.manager.begin_transaction(
            self.session_id, self.mock_connection
        )
        recent_time = datetime.now(timezone.utc) - timedelta(minutes=15)
        self.manager.transactions[transaction_id2].created_at = recent_time

        # Clean up with 30 minute timeout (should NOT clean up)
        self.manager.cleanup_abandoned_transactions(timeout_minutes=30)
        assert transaction_id2 in self.manager.transactions

    def test_cleanup_abandoned_transactions_multiple(self) -> None:
        """Test cleanup with multiple transactions, some abandoned."""
        # Create multiple transactions with different ages
        txn1 = self.manager.begin_transaction("session1", Mock())
        txn2 = self.manager.begin_transaction("session2", Mock())
        txn3 = self.manager.begin_transaction("session3", Mock())

        # Make txn1 and txn3 old (abandoned), keep txn2 recent
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        recent_time = datetime.now(timezone.utc) - timedelta(minutes=5)

        self.manager.transactions[txn1].created_at = old_time
        self.manager.transactions[txn2].created_at = recent_time
        self.manager.transactions[txn3].created_at = old_time

        # Cleanup
        self.manager.cleanup_abandoned_transactions(timeout_minutes=60)

        # Only txn2 should remain
        assert txn1 not in self.manager.transactions
        assert txn2 in self.manager.transactions
        assert txn3 not in self.manager.transactions

    def test_cleanup_abandoned_transactions_empty(self) -> None:
        """Test cleanup with no transactions."""
        # Should not raise any errors
        self.manager.cleanup_abandoned_transactions()
        assert len(self.manager.transactions) == 0

    @patch("mpzsql.transaction.logger")
    def test_logging_integration(self, mock_logger):
        """Test that appropriate logging occurs during operations."""
        # Test begin transaction logging
        transaction_id = self.manager.begin_transaction(
            self.session_id, self.mock_connection
        )
        mock_logger.info.assert_called_with(
            f"Started transaction {transaction_id} for session {self.session_id}"
        )

        # Test end transaction logging
        mock_logger.reset_mock()
        self.manager.end_transaction(transaction_id, 1)  # Commit

        # Should log the commit operation (done in Transaction.commit())
        # and not error on end_transaction since it succeeds

    @patch("mpzsql.transaction.logger")
    def test_error_logging(self, mock_logger):
        """Test error logging for various failure scenarios."""
        # Test end transaction with non-existent transaction
        fake_id = "txn_fake123"
        self.manager.end_transaction(fake_id, 1)

        mock_logger.error.assert_called_with(f"Transaction {fake_id} not found")

        # Test end transaction with unknown action
        mock_logger.reset_mock()
        transaction_id = self.manager.begin_transaction(
            self.session_id, self.mock_connection
        )
        self.manager.end_transaction(transaction_id, 99)

        mock_logger.error.assert_called_with("Unknown transaction action: 99")

    def test_transaction_id_uniqueness(self) -> None:
        """Test that transaction IDs are unique."""
        transaction_ids = set()

        # Create many transactions to test uniqueness
        for i in range(100):
            session_id = f"session_{i}"
            connection = Mock()
            txn_id = self.manager.begin_transaction(session_id, connection)

            assert txn_id not in transaction_ids, f"Duplicate transaction ID: {txn_id}"
            transaction_ids.add(txn_id)

        assert len(transaction_ids) == 100
        assert len(self.manager.transactions) == 100


class TestTransactionIntegration:
    """Integration tests for transaction management."""

    def test_complete_transaction_lifecycle_commit(self) -> None:
        """Test complete transaction lifecycle with commit."""
        manager = TransactionManager()
        connection = Mock()
        session_id = "integration_session"

        # Begin transaction
        txn_id = manager.begin_transaction(session_id, connection)
        assert txn_id in manager.transactions

        # Get transaction and add some statements
        txn = manager.get_transaction(txn_id)
        txn.add_statement("SELECT * FROM users")
        txn.add_statement("UPDATE users SET last_seen = NOW()")

        # Commit transaction
        result = manager.end_transaction(txn_id, 1)  # COMMIT

        assert result is True
        assert txn_id not in manager.transactions
        connection.begin.assert_called_once()
        connection.commit.assert_called_once()

    def test_complete_transaction_lifecycle_rollback(self) -> None:
        """Test complete transaction lifecycle with rollback."""
        manager = TransactionManager()
        connection = Mock()
        session_id = "integration_session"

        # Begin transaction
        txn_id = manager.begin_transaction(session_id, connection)

        # Get transaction and add some statements
        txn = manager.get_transaction(txn_id)
        txn.add_statement("INSERT INTO logs VALUES (1, 'test')")
        txn.add_statement("DELETE FROM temp_table")

        # Rollback transaction
        result = manager.end_transaction(txn_id, 2)  # ROLLBACK

        assert result is True
        assert txn_id not in manager.transactions
        connection.begin.assert_called_once()
        connection.rollback.assert_called_once()

    def test_multiple_concurrent_transactions(self) -> None:
        """Test handling multiple concurrent transactions."""
        manager = TransactionManager()

        # Create multiple transactions for different sessions
        transactions = {}
        for i in range(5):
            session_id = f"session_{i}"
            connection = Mock()
            txn_id = manager.begin_transaction(session_id, connection)
            transactions[session_id] = (txn_id, connection)

        assert len(manager.transactions) == 5

        # Add statements to each transaction
        for session_id, (txn_id, _) in transactions.items():
            txn = manager.get_transaction(txn_id)
            txn.add_statement(f"INSERT INTO logs VALUES ({session_id}, 'test')")

        # Commit some, rollback others
        sessions_to_commit = ["session_0", "session_2", "session_4"]
        sessions_to_rollback = ["session_1", "session_3"]

        for session_id in sessions_to_commit:
            txn_id, connection = transactions[session_id]
            result = manager.end_transaction(txn_id, 1)  # COMMIT
            assert result is True
            connection.commit.assert_called_once()

        for session_id in sessions_to_rollback:
            txn_id, connection = transactions[session_id]
            result = manager.end_transaction(txn_id, 2)  # ROLLBACK
            assert result is True
            connection.rollback.assert_called_once()

        # All transactions should be completed
        assert len(manager.transactions) == 0

    def test_transaction_error_handling(self) -> None:
        """Test transaction error handling scenarios."""
        manager = TransactionManager()
        connection = Mock()

        # Test commit failure
        connection.commit.side_effect = Exception("Database connection lost")
        txn_id = manager.begin_transaction("session1", connection)

        result = manager.end_transaction(txn_id, 1)  # COMMIT
        assert result is False
        assert txn_id in manager.transactions  # Transaction still exists

        # Reset connection and try rollback
        connection.reset_mock()
        connection.rollback.side_effect = None  # Remove the side effect

        result = manager.end_transaction(txn_id, 2)  # ROLLBACK
        assert result is True
        assert txn_id not in manager.transactions

    def test_abandoned_transaction_cleanup_integration(self) -> None:
        """Test complete abandoned transaction cleanup workflow."""
        manager = TransactionManager()

        # Create some transactions
        active_connection = Mock()
        abandoned_connection1 = Mock()
        abandoned_connection2 = Mock()

        active_txn = manager.begin_transaction("active_session", active_connection)
        abandoned_txn1 = manager.begin_transaction(
            "abandoned_session1", abandoned_connection1
        )
        abandoned_txn2 = manager.begin_transaction(
            "abandoned_session2", abandoned_connection2
        )

        # Make some transactions old
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        manager.transactions[abandoned_txn1].created_at = old_time
        manager.transactions[abandoned_txn2].created_at = old_time

        # Add statements to transactions
        for txn_id in [active_txn, abandoned_txn1, abandoned_txn2]:
            txn = manager.get_transaction(txn_id)
            txn.add_statement("SELECT 1")

        assert len(manager.transactions) == 3

        # Run cleanup
        manager.cleanup_abandoned_transactions(timeout_minutes=60)

        # Only active transaction should remain
        assert len(manager.transactions) == 1
        assert active_txn in manager.transactions
        assert abandoned_txn1 not in manager.transactions
        assert abandoned_txn2 not in manager.transactions

        # Verify rollback was called on abandoned transactions
        abandoned_connection1.rollback.assert_called_once()
        abandoned_connection2.rollback.assert_called_once()
        active_connection.rollback.assert_not_called()

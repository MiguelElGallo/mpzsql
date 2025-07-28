"""
Comprehensive test suite for transaction management.

This module tests the transaction management functionality including:
- Transaction class lifecycle
- TransactionManager operations 
- Transaction state management
- Error handling and cleanup scenarios
"""

import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import logging

from mpzsql.transaction import (
    Transaction,
    TransactionManager,
    TransactionState
)


class TestTransactionState:
    """Test TransactionState enum."""
    
    def test_transaction_state_values(self):
        """Test that transaction state enum has correct values."""
        assert TransactionState.ACTIVE.value == "ACTIVE"
        assert TransactionState.COMMITTED.value == "COMMITTED"
        assert TransactionState.ROLLED_BACK.value == "ROLLED_BACK"


class TestTransaction:
    """Test Transaction class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_connection = Mock()
        self.transaction_id = "test_txn_123"
        self.session_id = "test_session_456"
        self.transaction = Transaction(
            self.transaction_id,
            self.session_id,
            self.mock_connection
        )
    
    def test_transaction_initialization(self):
        """Test transaction initialization."""
        assert self.transaction.transaction_id == self.transaction_id
        assert self.transaction.session_id == self.session_id
        assert self.transaction.connection == self.mock_connection
        assert self.transaction.state == TransactionState.ACTIVE
        assert isinstance(self.transaction.created_at, datetime)
        assert self.transaction.statements == []
    
    def test_add_statement(self):
        """Test adding statements to transaction."""
        statement1 = "SELECT * FROM users"
        statement2 = "UPDATE users SET name = 'test'"
        
        self.transaction.add_statement(statement1)
        self.transaction.add_statement(statement2)
        
        assert len(self.transaction.statements) == 2
        assert self.transaction.statements[0]['statement'] == statement1
        assert self.transaction.statements[1]['statement'] == statement2
        assert isinstance(self.transaction.statements[0]['timestamp'], datetime)
        assert isinstance(self.transaction.statements[1]['timestamp'], datetime)
    
    def test_commit_success(self):
        """Test successful transaction commit."""
        self.transaction.commit()
        
        self.mock_connection.commit.assert_called_once()
        assert self.transaction.state == TransactionState.COMMITTED
    
    def test_commit_already_committed(self):
        """Test commit on already committed transaction."""
        self.transaction.state = TransactionState.COMMITTED
        
        with pytest.raises(ValueError, match="Cannot commit transaction in state"):
            self.transaction.commit()
        
        self.mock_connection.commit.assert_not_called()
    
    def test_commit_already_rolled_back(self):
        """Test commit on already rolled back transaction."""
        self.transaction.state = TransactionState.ROLLED_BACK
        
        with pytest.raises(ValueError, match="Cannot commit transaction in state"):
            self.transaction.commit()
        
        self.mock_connection.commit.assert_not_called()
    
    def test_commit_connection_error(self):
        """Test commit with connection error."""
        self.mock_connection.commit.side_effect = Exception("Connection failed")
        
        with pytest.raises(Exception, match="Connection failed"):
            self.transaction.commit()
        
        self.mock_connection.commit.assert_called_once()
        assert self.transaction.state == TransactionState.ACTIVE  # State unchanged on error
    
    def test_rollback_success(self):
        """Test successful transaction rollback."""
        self.transaction.rollback()
        
        self.mock_connection.rollback.assert_called_once()
        assert self.transaction.state == TransactionState.ROLLED_BACK
    
    def test_rollback_already_committed(self):
        """Test rollback on already committed transaction."""
        self.transaction.state = TransactionState.COMMITTED
        
        with pytest.raises(ValueError, match="Cannot rollback transaction in state"):
            self.transaction.rollback()
        
        self.mock_connection.rollback.assert_not_called()
    
    def test_rollback_already_rolled_back(self):
        """Test rollback on already rolled back transaction."""
        self.transaction.state = TransactionState.ROLLED_BACK
        
        with pytest.raises(ValueError, match="Cannot rollback transaction in state"):
            self.transaction.rollback()
        
        self.mock_connection.rollback.assert_not_called()
    
    def test_rollback_connection_error(self):
        """Test rollback with connection error."""
        self.mock_connection.rollback.side_effect = Exception("Rollback failed")
        
        with pytest.raises(Exception, match="Rollback failed"):
            self.transaction.rollback()
        
        self.mock_connection.rollback.assert_called_once()
        assert self.transaction.state == TransactionState.ACTIVE  # State unchanged on error


class TestTransactionManager:
    """Test TransactionManager class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.manager = TransactionManager()
        self.mock_connection = Mock()
        self.session_id = "test_session_789"
    
    def test_transaction_manager_initialization(self):
        """Test transaction manager initialization."""
        assert self.manager.transactions == {}
    
    @patch('mpzsql.transaction.uuid.uuid4')
    def test_begin_transaction(self, mock_uuid):
        """Test beginning a new transaction."""
        mock_uuid.return_value = Mock(hex="abcdef1234567890")
        
        transaction_id = self.manager.begin_transaction(self.session_id, self.mock_connection)
        
        expected_id = "txn_abcdef1234567890"
        assert transaction_id == expected_id
        assert transaction_id in self.manager.transactions
        
        transaction = self.manager.transactions[transaction_id]
        assert transaction.transaction_id == expected_id
        assert transaction.session_id == self.session_id
        assert transaction.connection == self.mock_connection
        assert transaction.state == TransactionState.ACTIVE
        
        self.mock_connection.begin.assert_called_once()
    
    def test_get_transaction_exists(self):
        """Test getting an existing transaction."""
        # Create a transaction first
        transaction_id = self.manager.begin_transaction(self.session_id, self.mock_connection)
        
        # Retrieve it
        transaction = self.manager.get_transaction(transaction_id)
        
        assert transaction is not None
        assert transaction.transaction_id == transaction_id
        assert transaction.session_id == self.session_id
    
    def test_get_transaction_not_exists(self):
        """Test getting a non-existent transaction."""
        transaction = self.manager.get_transaction("non_existent_id")
        assert transaction is None
    
    def test_end_transaction_commit(self):
        """Test ending transaction with commit."""
        transaction_id = self.manager.begin_transaction(self.session_id, self.mock_connection)
        
        result = self.manager.end_transaction(transaction_id, 1)  # COMMIT
        
        assert result is True
        assert transaction_id not in self.manager.transactions
        self.mock_connection.commit.assert_called_once()
    
    def test_end_transaction_rollback(self):
        """Test ending transaction with rollback."""
        transaction_id = self.manager.begin_transaction(self.session_id, self.mock_connection)
        
        result = self.manager.end_transaction(transaction_id, 2)  # ROLLBACK
        
        assert result is True
        assert transaction_id not in self.manager.transactions
        self.mock_connection.rollback.assert_called_once()
    
    def test_end_transaction_unknown_action(self):
        """Test ending transaction with unknown action."""
        transaction_id = self.manager.begin_transaction(self.session_id, self.mock_connection)
        
        with patch('mpzsql.transaction.logger') as mock_logger:
            result = self.manager.end_transaction(transaction_id, 999)  # Unknown action
        
        assert result is False
        assert transaction_id in self.manager.transactions  # Transaction still exists
        mock_logger.error.assert_called_with("Unknown transaction action: 999")
    
    def test_end_transaction_not_found(self):
        """Test ending a non-existent transaction."""
        with patch('mpzsql.transaction.logger') as mock_logger:
            result = self.manager.end_transaction("non_existent_id", 1)
        
        assert result is False
        mock_logger.error.assert_called_with("Transaction non_existent_id not found")
    
    def test_end_transaction_commit_error(self):
        """Test ending transaction with commit error."""
        transaction_id = self.manager.begin_transaction(self.session_id, self.mock_connection)
        self.mock_connection.commit.side_effect = Exception("Commit failed")
        
        with patch('mpzsql.transaction.logger') as mock_logger:
            result = self.manager.end_transaction(transaction_id, 1)
        
        assert result is False
        assert transaction_id in self.manager.transactions  # Transaction still exists
        mock_logger.error.assert_called_with(f"Failed to end transaction {transaction_id}: Commit failed")
    
    def test_end_transaction_rollback_error(self):
        """Test ending transaction with rollback error."""
        transaction_id = self.manager.begin_transaction(self.session_id, self.mock_connection)
        self.mock_connection.rollback.side_effect = Exception("Rollback failed")
        
        with patch('mpzsql.transaction.logger') as mock_logger:
            result = self.manager.end_transaction(transaction_id, 2)
        
        assert result is False
        assert transaction_id in self.manager.transactions  # Transaction still exists
        mock_logger.error.assert_called_with(f"Failed to end transaction {transaction_id}: Rollback failed")
    
    @patch('mpzsql.transaction.datetime')
    def test_cleanup_abandoned_transactions(self, mock_datetime):
        """Test cleanup of abandoned transactions."""
        # Setup current time
        current_time = datetime(2023, 1, 1, 12, 0, 0)
        mock_datetime.utcnow.return_value = current_time
        
        # Create some transactions with different ages
        transaction_id1 = self.manager.begin_transaction(self.session_id, Mock())
        transaction_id2 = self.manager.begin_transaction(self.session_id, Mock())
        transaction_id3 = self.manager.begin_transaction(self.session_id, Mock())
        
        # Make some transactions old
        old_time = current_time - timedelta(minutes=35)  # Older than 30 minutes
        recent_time = current_time - timedelta(minutes=15)  # Recent
        
        self.manager.transactions[transaction_id1].created_at = old_time
        self.manager.transactions[transaction_id2].created_at = recent_time
        self.manager.transactions[transaction_id3].created_at = old_time
        
        with patch('mpzsql.transaction.logger') as mock_logger:
            self.manager.cleanup_abandoned_transactions(timeout_minutes=30)
        
        # Check that old transactions were removed
        assert transaction_id1 not in self.manager.transactions
        assert transaction_id3 not in self.manager.transactions
        assert transaction_id2 in self.manager.transactions  # Recent one should remain
        
        # Check logging
        assert mock_logger.warning.call_count == 2
    
    def test_cleanup_abandoned_transactions_default_timeout(self):
        """Test cleanup with default timeout."""
        # Create a transaction
        transaction_id = self.manager.begin_transaction(self.session_id, Mock())
        
        # Make it very old (more than 30 minutes)
        old_time = datetime.utcnow() - timedelta(minutes=35)
        self.manager.transactions[transaction_id].created_at = old_time
        
        with patch('mpzsql.transaction.logger'):
            self.manager.cleanup_abandoned_transactions()
        
        assert transaction_id not in self.manager.transactions
    
    def test_cleanup_abandoned_transactions_no_abandoned(self):
        """Test cleanup when no transactions are abandoned."""
        # Create a recent transaction
        transaction_id = self.manager.begin_transaction(self.session_id, Mock())
        
        with patch('mpzsql.transaction.logger') as mock_logger:
            self.manager.cleanup_abandoned_transactions()
        
        assert transaction_id in self.manager.transactions
        mock_logger.warning.assert_not_called()


class TestTransactionManagerIntegration:
    """Integration tests for transaction manager."""
    
    def test_full_transaction_lifecycle(self):
        """Test complete transaction lifecycle."""
        manager = TransactionManager()
        mock_connection = Mock()
        session_id = "integration_session"
        
        # Begin transaction
        transaction_id = manager.begin_transaction(session_id, mock_connection)
        assert transaction_id in manager.transactions
        
        # Get and use transaction
        transaction = manager.get_transaction(transaction_id)
        assert transaction is not None
        
        transaction.add_statement("SELECT * FROM test")
        transaction.add_statement("UPDATE test SET value = 1")
        
        assert len(transaction.statements) == 2
        
        # End transaction with commit
        result = manager.end_transaction(transaction_id, 1)
        assert result is True
        assert transaction_id not in manager.transactions
        
        mock_connection.begin.assert_called_once()
        mock_connection.commit.assert_called_once()
        mock_connection.rollback.assert_not_called()
    
    def test_multiple_transactions(self):
        """Test managing multiple transactions."""
        manager = TransactionManager()
        
        # Create multiple transactions
        connections = [Mock() for _ in range(3)]
        session_ids = [f"session_{i}" for i in range(3)]
        
        transaction_ids = []
        for i in range(3):
            txn_id = manager.begin_transaction(session_ids[i], connections[i])
            transaction_ids.append(txn_id)
        
        assert len(manager.transactions) == 3
        
        # Commit first, rollback second, leave third active
        manager.end_transaction(transaction_ids[0], 1)  # COMMIT
        manager.end_transaction(transaction_ids[1], 2)  # ROLLBACK
        
        assert len(manager.transactions) == 1
        assert transaction_ids[2] in manager.transactions
        
        connections[0].commit.assert_called_once()
        connections[1].rollback.assert_called_once()
        connections[2].commit.assert_not_called()
        connections[2].rollback.assert_not_called()


class TestLogging:
    """Test logging functionality."""
    
    def test_transaction_logging_import(self):
        """Test that logging is properly imported and configured."""
        from mpzsql.transaction import logger, transaction_logger
        
        assert logger is not None
        assert logger.name == "mpzsql.transaction"
        assert transaction_logger is not None


class TestErrorHandling:
    """Test error handling scenarios."""
    
    def test_transaction_with_none_connection(self):
        """Test transaction creation with None connection."""
        transaction = Transaction("test_id", "test_session", None)
        
        # Should still initialize properly
        assert transaction.transaction_id == "test_id"
        assert transaction.session_id == "test_session"
        assert transaction.connection is None
        assert transaction.state == TransactionState.ACTIVE
    
    def test_manager_with_connection_errors(self):
        """Test manager behavior with connection errors."""
        manager = TransactionManager()
        mock_connection = Mock()
        mock_connection.begin.side_effect = Exception("Connection error")
        
        with pytest.raises(Exception, match="Connection error"):
            manager.begin_transaction("test_session", mock_connection)
    
    def test_empty_statements_list(self):
        """Test transaction with no statements."""
        transaction = Transaction("test_id", "test_session", Mock())
        
        assert transaction.statements == []
        
        # Should still be able to commit/rollback
        transaction.commit()
        assert transaction.state == TransactionState.COMMITTED
"""Transaction management for FlightSQL server.
Implements transaction handling similar to the Examples server.
"""

import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from mpzsql.logfire_config import get_transaction_logger

logger = logging.getLogger(__name__)
transaction_logger = get_transaction_logger()  # type: ignore


class TransactionState(Enum):
    """Transaction states."""

    ACTIVE = "ACTIVE"
    COMMITTED = "COMMITTED"
    ROLLED_BACK = "ROLLED_BACK"


class Transaction:
    """Represents a database transaction."""

    def __init__(self, transaction_id: str, session_id: str, connection: Any):
        self.transaction_id = transaction_id
        self.session_id = session_id
        self.connection = connection
        self.state = TransactionState.ACTIVE
        self.created_at = datetime.now(timezone.utc)
        self.statements: list[dict[str, Any]] = []

    def add_statement(self, statement: str) -> None:
        """Add a statement to the transaction log."""
        self.statements.append(
            {"statement": statement, "timestamp": datetime.now(timezone.utc)}
        )

    def commit(self) -> None:
        """Commit the transaction."""
        if self.state != TransactionState.ACTIVE:
            raise ValueError(f"Cannot commit transaction in state {self.state}")

        try:
            self.connection.commit()
            self.state = TransactionState.COMMITTED
            logger.info(f"Transaction {self.transaction_id} committed")
        except Exception as e:
            logger.error(f"Failed to commit transaction {self.transaction_id}: {e}")
            raise

    def rollback(self) -> None:
        """Rollback the transaction."""
        if self.state != TransactionState.ACTIVE:
            raise ValueError(f"Cannot rollback transaction in state {self.state}")

        try:
            self.connection.rollback()
            self.state = TransactionState.ROLLED_BACK
            logger.info(f"Transaction {self.transaction_id} rolled back")
        except Exception as e:
            logger.error(f"Failed to rollback transaction {self.transaction_id}: {e}")
            raise


class TransactionManager:
    """Manages database transactions."""

    def __init__(self) -> None:
        self.transactions: dict[str, Transaction] = {}

    def begin_transaction(self, session_id: str, connection: Any) -> str:
        """Begin a new transaction."""
        transaction_id = f"txn_{uuid.uuid4().hex[:16]}"

        # Start transaction on the connection
        connection.begin()

        transaction = Transaction(transaction_id, session_id, connection)
        self.transactions[transaction_id] = transaction

        logger.info(f"Started transaction {transaction_id} for session {session_id}")
        return transaction_id

    def get_transaction(self, transaction_id: str) -> Transaction | None:
        """Get a transaction by ID."""
        return self.transactions.get(transaction_id)

    def end_transaction(self, transaction_id: str, action: int) -> bool:
        """End a transaction with the specified action.
        Action: 1 = COMMIT, 2 = ROLLBACK
        """
        transaction = self.transactions.get(transaction_id)
        if not transaction:
            logger.error(f"Transaction {transaction_id} not found")
            return False

        try:
            if action == 1:  # COMMIT
                transaction.commit()
            elif action == 2:  # ROLLBACK
                transaction.rollback()
            else:
                logger.error(f"Unknown transaction action: {action}")
                return False

            # Remove from active transactions
            del self.transactions[transaction_id]
            return True

        except Exception as e:
            logger.error(f"Failed to end transaction {transaction_id}: {e}")
            return False

    def cleanup_abandoned_transactions(self, timeout_minutes: int = 30) -> None:
        """Clean up transactions that have been abandoned."""
        current_time = datetime.now(timezone.utc)
        abandoned = []

        for txn_id, transaction in self.transactions.items():
            if (current_time - transaction.created_at).seconds > timeout_minutes * 60:
                abandoned.append(txn_id)

        for txn_id in abandoned:
            logger.warning(f"Rolling back abandoned transaction {txn_id}")
            self.end_transaction(txn_id, 2)  # ROLLBACK

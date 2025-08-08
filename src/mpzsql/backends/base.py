"""
Base database backend interface.

This module defines the abstract interface that all database backends
must implement for the MPZSQL server.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

import pyarrow as pa

from src.mpzsql.config import ServerConfig


class DatabaseBackend(ABC):
    """Abstract base class for database backends."""

    def __init__(self, config: ServerConfig):
        """Initialize the backend with configuration."""
        self.config = config

    @abstractmethod
    def execute_sql(self, sql: str) -> None:
        """Execute SQL commands without returning results."""
        pass

    @abstractmethod
    def execute_query(self, query: str, params: Optional[List] = None) -> pa.Table:
        """Execute a query and return an Arrow Table."""
        pass

    @abstractmethod
    def execute_update(self, query: str, params: Optional[List] = None) -> int:
        """Execute an UPDATE, INSERT or DELETE statement and return the number of affected rows."""
        pass

    @abstractmethod
    def get_statement_schema(self, query: str) -> pa.Schema:
        """Get the schema for a SQL statement without executing it."""
        pass

    @abstractmethod
    def get_catalogs(self) -> pa.Table:
        """Get available catalogs as an Arrow table."""
        pass

    @abstractmethod
    def get_schemas(self, catalog: Optional[str] = None) -> List[Tuple[str, str]]:
        """Get available schemas for a catalog, returns (catalog, schema) tuples."""
        pass

    @abstractmethod
    def get_tables(
        self,
        catalog: Optional[str] = None,
        db_schema_filter_pattern: Optional[str] = None,
        table_name_filter_pattern: Optional[str] = None,
        table_types: Optional[List[str]] = None,
        include_schema: bool = False,
    ) -> pa.Table:
        """Get available tables with their metadata as an Arrow table."""
        pass

    @abstractmethod
    def get_sql_info(self, info_codes: List[int]) -> pa.Table:
        """Get SQL info for the given info codes as an Arrow table."""
        pass

    @abstractmethod
    def get_db_schemas(
        self,
        catalog: Optional[str] = None,
        db_schema_filter_pattern: Optional[str] = None,
    ) -> pa.Table:
        """Get available schemas for a catalog as an Arrow table."""
        pass

    @abstractmethod
    def get_columns(
        self,
        catalog: Optional[str] = None,
        db_schema_filter_pattern: Optional[str] = None,
        table_name_filter_pattern: Optional[str] = None,
        column_name_filter_pattern: Optional[str] = None,
    ) -> pa.Table:
        """Get columns for a table as an Arrow table."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the backend and cleanup resources."""
        pass

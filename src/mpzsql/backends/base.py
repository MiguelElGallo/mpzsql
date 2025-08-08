"""Base database backend interface.

This module defines the abstract interface that all database backends
must implement for the MPZSQL server.
"""

from abc import ABC, abstractmethod

import pyarrow as pa

from mpzsql.config import ServerConfig


class DatabaseBackend(ABC):
    """Abstract base class for database backends."""

    def __init__(self, config: ServerConfig):
        """Initialize the backend with configuration."""
        self.config = config

    @abstractmethod
    def execute_sql(self, sql: str) -> None:
        """Execute SQL commands without returning results."""

    @abstractmethod
    def execute_query(self, query: str, params: list | None = None) -> pa.Table:
        """Execute a query and return an Arrow Table."""

    @abstractmethod
    def execute_update(self, query: str, params: list | None = None) -> int:
        """Execute an UPDATE, INSERT or DELETE statement and return the number of affected rows."""

    @abstractmethod
    def get_statement_schema(self, query: str) -> pa.Schema:
        """Get the schema for a SQL statement without executing it."""

    @abstractmethod
    def get_catalogs(self) -> pa.Table:
        """Get available catalogs as an Arrow table."""

    @abstractmethod
    def get_schemas(self, catalog: str | None = None) -> list[tuple[str, str]]:
        """Get available schemas for a catalog, returns (catalog, schema) tuples."""

    @abstractmethod
    def get_tables(
        self,
        catalog: str | None = None,
        db_schema_filter_pattern: str | None = None,
        table_name_filter_pattern: str | None = None,
        table_types: list[str] | None = None,
        include_schema: bool = False,
    ) -> pa.Table:
        """Get available tables with their metadata as an Arrow table."""

    @abstractmethod
    def get_sql_info(self, info_codes: list[int]) -> pa.Table:
        """Get SQL info for the given info codes as an Arrow table."""

    @abstractmethod
    def get_db_schemas(
        self,
        catalog: str | None = None,
        db_schema_filter_pattern: str | None = None,
    ) -> pa.Table:
        """Get available schemas for a catalog as an Arrow table."""

    @abstractmethod
    def get_columns(
        self,
        catalog: str | None = None,
        db_schema_filter_pattern: str | None = None,
        table_name_filter_pattern: str | None = None,
        column_name_filter_pattern: str | None = None,
    ) -> pa.Table:
        """Get columns for a table as an Arrow table."""

    @abstractmethod
    def close(self) -> None:
        """Close the backend and cleanup resources."""

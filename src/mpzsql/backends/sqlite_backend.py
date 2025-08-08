"""
SQLite backend implementation for MPZSQL.

This module provides the SQLite-specific implementation of the database backend,
including query execution, schema introspection, and metadata operations.
"""

import logging
import sqlite3
import threading
from typing import List, Optional, Tuple

import pyarrow as pa

from mpzsql.backends.base import DatabaseBackend
from mpzsql.config import ServerConfig
from mpzsql.logfire_config import get_sqlite_logger

logger = logging.getLogger(__name__)
sqlite_logger = get_sqlite_logger()


class SQLiteBackend(DatabaseBackend):
    """SQLite backend implementation."""

    def __init__(self, config: ServerConfig):
        """Initialize SQLite backend."""
        super().__init__(config)

        # Add thread lock for concurrent access safety
        self._lock = threading.Lock()

        if not config.database:
            raise ValueError("SQLite backend requires a database file")

        try:
            # Create SQLite connection
            connection_params = {
                "check_same_thread": False,  # Allow multi-threaded access
                "isolation_level": None,  # Autocommit mode
            }

            if config.read_only:
                # Open in read-only mode
                self.connection = sqlite3.connect(
                    f"file:{config.database}?mode=ro", uri=True, **connection_params
                )
            else:
                self.connection = sqlite3.connect(config.database, **connection_params)

            # Configure connection
            self.connection.row_factory = sqlite3.Row  # Enable column access by name

            logger.info(f"Connected to SQLite database: {config.database}")

        except Exception as e:
            logger.error(f"Failed to connect to SQLite: {e}")
            raise

    def execute_sql(self, sql: str) -> None:
        """Execute SQL commands without returning results."""
        with self._lock:  # Ensure thread-safe access
            try:
                cursor = self.connection.cursor()
                # Execute potentially multiple statements
                cursor.executescript(sql)
                cursor.close()
                logger.debug(f"Executed SQL: {sql[:100]}...")
            except Exception as e:
                logger.error(f"SQL execution failed: {e}")
                raise

    def execute_query(self, query: str, params: Optional[List] = None) -> pa.Table:
        """Execute a query and return an Arrow Table."""
        with self._lock:  # Ensure thread-safe access
            try:
                cursor = self.connection.cursor()
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)

                # Get column information
                columns = [desc[0] for desc in cursor.description]

                # Fetch all rows (for simplicity - in production, this should be chunked)
                rows = cursor.fetchall()
                cursor.close()

                if not rows:
                    # Empty result
                    schema = self._infer_schema_from_cursor_description(
                        cursor.description
                    )
                    empty_batch = pa.record_batch(
                        [pa.array([], type=field.type) for field in schema],
                        schema=schema,
                    )
                    return pa.Table.from_batches([empty_batch])

                # Convert to Arrow format
                # First, we need to infer types from the data
                arrow_arrays = []
                schema_fields = []

                for i, column_name in enumerate(columns):
                    # Extract column values
                    column_values = [row[i] for row in rows]

                    # Infer Arrow type and create array
                    arrow_type = self._infer_arrow_type(column_values)
                    arrow_array = pa.array(column_values, type=arrow_type)

                    arrow_arrays.append(arrow_array)
                    schema_fields.append(pa.field(column_name, arrow_type))

                # Create schema and record batch
                schema = pa.schema(schema_fields)
                batch = pa.record_batch(arrow_arrays, schema=schema)

                # Return as Table
                return pa.Table.from_batches([batch])

            except Exception as e:
                logger.error(f"Query execution failed: {e}")
                raise

    def get_statement_schema(self, query: str) -> pa.Schema:
        """Get the schema for a SQL statement without executing it."""
        with self._lock:  # Ensure thread-safe access
            try:
                # Use EXPLAIN QUERY PLAN to understand the query structure
                cursor = self.connection.cursor()

                # For SQLite, we'll execute with LIMIT 0 to get schema
                limited_query = f"SELECT * FROM ({query}) LIMIT 0"
                cursor.execute(limited_query)

                schema = self._infer_schema_from_cursor_description(cursor.description)
                cursor.close()

                return schema

            except Exception as e:
                logger.error(f"Schema analysis failed: {e}")
                # Fallback: try PRAGMA table_info if it's a simple table query
                try:
                    # Very basic parsing to extract table name
                    query_upper = query.strip().upper()
                    if query_upper.startswith("SELECT") and "FROM" in query_upper:
                        # This is a very simplified approach
                        # In production, you'd want a proper SQL parser
                        pass

                    # For now, return a generic schema
                    return pa.schema([pa.field("result", pa.string())])

                except Exception:
                    raise e

    def execute_update(self, query: str, params: Optional[List] = None) -> int:
        """Execute an UPDATE, INSERT or DELETE statement and return the number of affected rows."""
        with self._lock:  # Ensure thread-safe access
            try:
                cursor = self.connection.cursor()
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                affected_rows = cursor.rowcount
                cursor.close()
                logger.debug(f"Update query affected {affected_rows} rows")
                return affected_rows
            except Exception as e:
                logger.error(f"Update query execution failed: {e}")
                raise

    def get_catalogs(self) -> pa.Table:
        """Get available catalogs as an Arrow table."""
        # SQLite has a single catalog (main database)
        with self._lock:  # Ensure thread-safe access
            try:
                cursor = self.connection.cursor()
                cursor.execute("PRAGMA database_list")
                databases = cursor.fetchall()
                cursor.close()

                catalog_names = [
                    db[1] for db in databases
                ]  # database name is in column 1

                # Return as Arrow table
                return pa.table({"catalog_name": catalog_names})
            except Exception as e:
                logger.warning(f"Could not get catalogs: {e}")
                return pa.table({"catalog_name": ["main"]})

    def get_schemas(self, catalog: Optional[str] = None) -> List[Tuple[str, str]]:
        """Get available schemas for a catalog, returns (catalog, schema) tuples."""
        # SQLite doesn't have schemas in the traditional sense
        # Everything is in the main schema
        catalog_name = catalog or "main"
        return [(catalog_name, "")]  # Empty string represents the default schema

    def get_tables(
        self,
        catalog: Optional[str] = None,
        db_schema_filter_pattern: Optional[str] = None,
        table_name_filter_pattern: Optional[str] = None,
        table_types: Optional[List[str]] = None,
        include_schema: bool = False,
    ) -> pa.Table:
        """Get available tables with their metadata as an Arrow table."""
        with self._lock:  # Ensure thread-safe access
            try:
                cursor = self.connection.cursor()

                # Get all tables and views
                query = """
                SELECT name, type FROM sqlite_master 
                WHERE type IN ('table', 'view')
                """

                params = []

                if table_name_filter_pattern:
                    query += " AND name LIKE ?"
                    params.append(table_name_filter_pattern)

                if table_types:
                    # Convert to SQLite types
                    sqlite_types = []
                    for t in table_types:
                        if t.upper() in ["BASE TABLE", "TABLE"]:
                            sqlite_types.append("table")
                        elif t.upper() == "VIEW":
                            sqlite_types.append("view")

                    if sqlite_types:
                        placeholders = ",".join("?" * len(sqlite_types))
                        query += f" AND type IN ({placeholders})"
                        params.extend(sqlite_types)

                query += " ORDER BY name"

                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)

                results = cursor.fetchall()
                cursor.close()

                # Convert to expected format
                catalog_name = catalog or "main"
                schema_name = ""  # SQLite doesn't have schemas

                catalog_names = []
                schema_names = []
                table_names = []
                table_types_list = []

                for row in results:
                    table_name = row[0]
                    table_type = "BASE TABLE" if row[1] == "table" else "VIEW"
                    catalog_names.append(catalog_name)
                    schema_names.append(schema_name)
                    table_names.append(table_name)
                    table_types_list.append(table_type)

                return pa.table(
                    {
                        "catalog_name": catalog_names,
                        "db_schema_name": schema_names,
                        "table_name": table_names,
                        "table_type": table_types_list,
                    }
                )

            except Exception as e:
                logger.error(f"Could not get tables: {e}")
                return pa.table(
                    {
                        "catalog_name": [],
                        "db_schema_name": [],
                        "table_name": [],
                        "table_type": [],
                    }
                )

    def get_sql_info(self, info_codes: List[int]) -> pa.Table:
        """Get SQL info for the given info codes as an Arrow table."""
        # Basic implementation for SQLite
        info_names = []
        info_values = []

        for code in info_codes:
            if code == 500:  # SQL_DBMS_NAME
                info_names.append("SQL_DBMS_NAME")
                info_values.append("SQLite")
            elif code == 501:  # SQL_DBMS_VER
                info_names.append("SQL_DBMS_VER")
                info_values.append(sqlite3.sqlite_version)
            else:
                info_names.append(f"SQL_INFO_{code}")
                info_values.append("Unknown")

        return pa.table({"info_name": info_names, "info_value": info_values})

    def get_db_schemas(
        self,
        catalog: Optional[str] = None,
        db_schema_filter_pattern: Optional[str] = None,
    ) -> pa.Table:
        """Get available schemas for a catalog as an Arrow table."""
        # SQLite doesn't have schemas in the traditional sense
        catalog_name = catalog or "main"

        return pa.table({"catalog_name": [catalog_name], "db_schema_name": [""]})

    def get_columns(
        self,
        catalog: Optional[str] = None,
        db_schema_filter_pattern: Optional[str] = None,
        table_name_filter_pattern: Optional[str] = None,
        column_name_filter_pattern: Optional[str] = None,
    ) -> pa.Table:
        """Get columns for tables as an Arrow table."""
        with self._lock:  # Ensure thread-safe access
            try:
                cursor = self.connection.cursor()

                # Get all tables first
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = cursor.fetchall()

                catalog_names = []
                schema_names = []
                table_names = []
                column_names = []
                data_types = []

                for table_row in tables:
                    table_name = table_row[0]

                    # Filter tables if pattern provided
                    if (
                        table_name_filter_pattern
                        and table_name_filter_pattern not in table_name
                    ):
                        continue

                    # Get column info for this table
                    cursor.execute(f"PRAGMA table_info({table_name})")
                    columns = cursor.fetchall()

                    for col in columns:
                        column_name = col[1]
                        column_type = col[2] or "TEXT"

                        # Filter columns if pattern provided
                        if (
                            column_name_filter_pattern
                            and column_name_filter_pattern not in column_name
                        ):
                            continue

                        catalog_names.append(catalog or "main")
                        schema_names.append("")
                        table_names.append(table_name)
                        column_names.append(column_name)
                        data_types.append(column_type)

                cursor.close()

                return pa.table(
                    {
                        "catalog_name": catalog_names,
                        "db_schema_name": schema_names,
                        "table_name": table_names,
                        "column_name": column_names,
                        "data_type": data_types,
                    }
                )

            except Exception as e:
                logger.error(f"Could not get columns: {e}")
                return pa.table(
                    {
                        "catalog_name": [],
                        "db_schema_name": [],
                        "table_name": [],
                        "column_name": [],
                        "data_type": [],
                    }
                )

    def get_catalogs_old(self) -> List[str]:
        """Get available catalogs (deprecated method for backward compatibility)."""
        catalogs_table = self.get_catalogs()
        return catalogs_table.column("catalog_name").to_pylist()

    def get_schemas_old(self, catalog: Optional[str] = None) -> List[str]:
        """Get available schemas for a catalog (deprecated method for backward compatibility)."""
        # SQLite doesn't have schemas in the traditional sense
        # Everything is in the main schema
        return [""]  # Empty string represents the default schema

    def get_tables_old(
        self,
        catalog: Optional[str] = None,
        db_schema_filter: Optional[str] = None,
        table_filter: Optional[str] = None,
        table_types: Optional[List[str]] = None,
    ) -> List[Tuple[str, str, str, str]]:
        """Get available tables with their metadata (deprecated method for backward compatibility)."""
        tables_table = self.get_tables(
            catalog, db_schema_filter, table_filter, table_types
        )

        # Convert table to list of tuples
        results = []
        for i in range(len(tables_table)):
            catalog_name = tables_table.column("catalog_name")[i].as_py()
            schema_name = tables_table.column("db_schema_name")[i].as_py()
            table_name = tables_table.column("table_name")[i].as_py()
            table_type = tables_table.column("table_type")[i].as_py()
            results.append((catalog_name, schema_name, table_name, table_type))

        return results

    def _infer_schema_from_cursor_description(self, description) -> pa.Schema:
        """Infer Arrow schema from SQLite cursor description."""
        fields = []

        for col_desc in description:
            column_name = col_desc[0]
            # SQLite cursor description doesn't provide reliable type info
            # Default to string, will be refined when we see actual data
            fields.append(pa.field(column_name, pa.string()))

        return pa.schema(fields)

    def _infer_arrow_type(self, values: List) -> pa.DataType:
        """Infer Arrow type from a list of values."""
        if not values:
            return pa.string()

        # Filter out None values for type inference
        non_null_values = [v for v in values if v is not None]

        if not non_null_values:
            return pa.string()

        # Check if all non-null values are of the same type
        first_type = type(non_null_values[0])
        if not all(isinstance(v, first_type) for v in non_null_values):
            # Mixed types - default to string
            return pa.string()

        # Check the type of the first non-null value
        sample_value = non_null_values[0]

        if isinstance(sample_value, bool):
            return pa.bool_()
        elif isinstance(sample_value, int):
            # Check if all values fit in different int types
            min_val = min(non_null_values)
            max_val = max(non_null_values)

            if -128 <= min_val and max_val <= 127:
                return pa.int8()
            elif -32768 <= min_val and max_val <= 32767:
                return pa.int16()
            elif -2147483648 <= min_val and max_val <= 2147483647:
                return pa.int32()
            else:
                return pa.int64()
        elif isinstance(sample_value, float):
            return pa.float64()
        elif isinstance(sample_value, str):
            return pa.string()
        elif isinstance(sample_value, bytes):
            return pa.binary()
        else:
            # Default to string for unknown types
            return pa.string()

    def close(self) -> None:
        """Close the SQLite connection."""
        try:
            if self.connection:
                self.connection.close()
                logger.info("SQLite connection closed")
        except Exception as e:
            logger.error(f"Error closing SQLite connection: {e}")

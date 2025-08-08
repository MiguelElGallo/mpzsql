"""
DuckDB backend implementation for MPZSQL.

This module provides the DuckDB-specific implementation of the database backend,
including query execution, schema introspection, and metadata operations.
"""

import logging
import os
import uuid
from typing import List, Optional, Tuple

import duckdb
import pyarrow as pa
import pyarrow.compute as pc

from mpzsql.backends.base import DatabaseBackend
from mpzsql.config import ServerConfig
from mpzsql.logfire_config import get_duckdb_logger

logger = logging.getLogger(__name__)

# Initialize logfire logger for DuckDB operations
duckdb_logger = get_duckdb_logger()

# Keep legacy file logging for now for backward compatibility
# Create a file handler for the duckdb logger with absolute path
log_path = os.path.join(os.getcwd(), "server_duckdb.log")
fh = logging.FileHandler(log_path, mode="w")
fh.setLevel(logging.DEBUG)

# Create a formatter and set it for the handler
formatter = logging.Formatter("%(asctime)s - %(message)s")
fh.setFormatter(formatter)

# Create legacy logger for file output (keep existing for compatibility)
duckdb_log = logging.getLogger("duckdb_queries")
duckdb_log.setLevel(logging.DEBUG)
duckdb_log.addHandler(fh)
duckdb_log.propagate = False  # Prevent propagation to root logger

# Test both loggers
duckdb_logger.info(
    f"DuckDB logfire logger initialized - also writing legacy log to {log_path}"
)
duckdb_log.info(f"DuckDB logger initialized - writing to {log_path}")
fh.flush()  # Force flush


class DuckDBBackend(DatabaseBackend):
    """DuckDB backend implementation."""

    def __init__(self, config: ServerConfig, existing_connection=None):
        """Initialize DuckDB backend."""
        super().__init__(config)

        # Use existing connection if provided, otherwise create new one
        if existing_connection:
            self.connection = existing_connection
            logger.info("Using existing DuckDB connection")
            # Still need to call setup if we have an existing connection
            # Use a simple check to avoid duplicate setup
            try:
                # Try to check if setup was already done by testing a known extension
                self.connection.execute(
                    "SELECT * FROM pragma_database_list();"
                ).fetchall()
                logger.info("Existing connection appears to be configured")
            except Exception:
                # If there's any issue, just run setup
                self._setup_duckdb()
        else:
            # Create DuckDB connection
            try:
                connection_params = {}
                if config.read_only:
                    connection_params["read_only"] = True

                if config.database:
                    self.connection = duckdb.connect(
                        config.database, **connection_params
                    )
                    logger.info(f"Connected to DuckDB database: {config.database}")
                else:
                    self.connection = duckdb.connect(":memory:", **connection_params)
                    logger.info("Connected to in-memory DuckDB database")

                # Set up any DuckDB-specific configuration
                self._setup_duckdb()

            except Exception as e:
                logger.error(f"Failed to connect to DuckDB: {e}")
                raise

    def _setup_duckdb(self):
        """Set up DuckDB-specific configuration."""
        try:
            # Try to install and load common extensions, but don't fail if they're not available
            extensions = ["httpfs", "parquet", "json"]
            for ext in extensions:
                try:
                    # Check if extension is already installed
                    result = self.connection.execute(
                        "SELECT extension_name FROM duckdb_extensions() WHERE installed = true"
                    ).fetchall()
                    installed_extensions = [row[0] for row in result]

                    if ext not in installed_extensions:
                        self.connection.execute(f"INSTALL {ext}")

                    self.connection.execute(f"LOAD {ext}")
                    logger.debug(f"Loaded DuckDB extension: {ext}")
                except Exception as e:
                    logger.debug(f"Could not load DuckDB extension {ext}: {e}")
                    # Continue without this extension

            # Configure Arrow format for better integration
            self.connection.execute("SET arrow_large_buffer_size = true")

        except Exception as e:
            logger.debug(f"DuckDB setup completed with some warnings: {e}")

    def execute_sql(self, sql: str) -> None:
        """Execute SQL commands without returning results."""
        try:
            self.connection.execute(sql)
            logger.debug(f"Executed SQL: {sql[:100]}...")
        except Exception as e:
            logger.error(f"SQL execution failed: {e}")
            raise

    def execute_query(self, query: str, params: Optional[List] = None) -> pa.Table:
        """Execute a SQL query using DuckDB and return the results as a PyArrow Table."""
        try:
            duckdb_log.info(f"Executing query: {query}")
            duckdb_logger.info("Executing DuckDB query", query=query)
            if params:
                duckdb_log.info(f"With parameters: {params}")
                duckdb_logger.info("Query parameters provided", params=params)
            fh.flush()  # Force flush before execution
            result = self.connection.execute(query, params).fetch_arrow_table()
            duckdb_log.info(f"Query result:\n{result}")
            duckdb_logger.info(
                "Query executed successfully",
                rows=len(result),
                columns=len(result.schema),
            )
            fh.flush()  # Force flush after execution
            return result
        except Exception as e:
            duckdb_log.error(f"Error executing query: {query}\n{e}")
            duckdb_logger.error("Query execution failed", query=query, error=str(e))
            fh.flush()  # Force flush on error
            raise

    def execute_update(self, query: str, params: Optional[List] = None) -> int:
        """Execute an UPDATE, INSERT or DELETE statement and return the number of affected rows."""
        try:
            duckdb_log.info(f"Executing update query: {query}")
            duckdb_logger.info("Executing DuckDB update query", query=query)
            if params:
                duckdb_log.info(f"With parameters: {params}")
                duckdb_logger.info("Update query parameters provided", params=params)
            fh.flush()  # Force flush before execution

            # Execute the query and get the result
            result = self.connection.execute(query, params).fetch_arrow_table()

            duckdb_log.info(f"Update query result:\n{result}")
            duckdb_logger.info(
                "Update query executed",
                result_rows=result.num_rows,
                result_columns=result.num_columns,
            )
            fh.flush()  # Force flush after execution

            # For DML statements, DuckDB returns a single BIGINT value with the number of
            # affected rows. This is represented as a Table with one row and one column.
            if result.num_rows == 1 and result.num_columns == 1:
                # Get the scalar value from the first column, first row
                column = result.column(0)
                if len(column) > 0:
                    scalar_value = column[0].as_py()
                    if scalar_value is not None:
                        affected_rows = int(scalar_value)
                        duckdb_log.info(f"Affected rows: {affected_rows}")
                        duckdb_logger.info(
                            "Update affected rows", affected_rows=affected_rows
                        )
                        fh.flush()
                        return affected_rows

            # Fallback to previous behavior for other cases
            affected_rows = result.num_rows
            duckdb_log.info(f"Affected rows (fallback): {affected_rows}")
            duckdb_logger.info(
                "Update affected rows (fallback)", affected_rows=affected_rows
            )
            fh.flush()
            return affected_rows

        except Exception as e:
            duckdb_log.error(f"Error executing update query: {query}\n{e}")
            duckdb_logger.error(
                "Update query execution failed", query=query, error=str(e)
            )
            fh.flush()  # Force flush on error
            raise

    def _convert_large_utf8_to_utf8(self, table: pa.Table) -> pa.Table:
        """Convert LargeUtf8 columns to Utf8 and handle other JDBC compatibility issues."""
        try:
            # Check if any columns need conversion
            needs_conversion = False
            new_fields = []

            for field in table.schema:
                if field.type == pa.large_utf8():
                    new_fields.append(pa.field(field.name, pa.utf8(), field.nullable))
                    needs_conversion = True
                elif pa.types.is_large_binary(field.type):
                    # Convert large binary to regular binary
                    new_fields.append(pa.field(field.name, pa.binary(), field.nullable))
                    needs_conversion = True
                elif pa.types.is_large_list(field.type):
                    # Convert large list to regular list
                    value_type = field.type.value_type
                    new_fields.append(
                        pa.field(field.name, pa.list_(value_type), field.nullable)
                    )
                    needs_conversion = True
                elif pa.types.is_decimal256(field.type):
                    # Convert decimal256 to decimal128 for better compatibility
                    precision, scale = field.type.precision, field.type.scale
                    if precision <= 38:  # decimal128 max precision
                        new_fields.append(
                            pa.field(
                                field.name,
                                pa.decimal128(precision, scale),
                                field.nullable,
                            )
                        )
                        needs_conversion = True
                    else:
                        # Fall back to string representation for very large decimals
                        new_fields.append(
                            pa.field(field.name, pa.utf8(), field.nullable)
                        )
                        needs_conversion = True
                else:
                    new_fields.append(field)

            if not needs_conversion:
                return table

            # Convert the table
            new_schema = pa.schema(new_fields)
            new_columns = []

            for i, column in enumerate(table.columns):
                original_type = table.schema.field(i).type
                if original_type == pa.large_utf8():
                    # Convert LargeUtf8 to Utf8
                    new_column = pc.cast(column, pa.utf8())
                    new_columns.append(new_column)
                elif pa.types.is_large_binary(original_type):
                    # Convert large binary to regular binary
                    new_column = pc.cast(column, pa.binary())
                    new_columns.append(new_column)
                elif pa.types.is_large_list(original_type):
                    # Convert large list to regular list
                    value_type = original_type.value_type
                    new_column = pc.cast(column, pa.list_(value_type))
                    new_columns.append(new_column)
                elif pa.types.is_decimal256(original_type):
                    # Convert decimal256 to decimal128 or string
                    precision, scale = original_type.precision, original_type.scale
                    if precision <= 38:
                        new_column = pc.cast(column, pa.decimal128(precision, scale))
                        new_columns.append(new_column)
                    else:
                        # Convert to string for very large decimals
                        new_column = pc.cast(column, pa.utf8())
                        new_columns.append(new_column)
                else:
                    new_columns.append(column)

            return pa.table(new_columns, schema=new_schema)

        except Exception as e:
            logger.warning(
                f"Failed to convert data types for JDBC compatibility: {e}, returning original table"
            )
            return table

    def get_statement_schema(self, query: str) -> pa.Schema:
        """Get the schema for a SQL statement without executing it."""
        # Handle non-SELECT statements that don't have a schema
        query_upper = query.strip().upper()
        if (
            query_upper.startswith("USE ")
            or query_upper.startswith("SET ")
            or query_upper.startswith("CREATE ")
            or query_upper.startswith("DROP ")
            or query_upper.startswith("ALTER ")
            or query_upper.startswith("INSERT ")
            or query_upper.startswith("UPDATE ")
            or query_upper.startswith("DELETE ")
            or query_upper.startswith("ATTACH ")
            or query_upper.startswith("DETACH ")
        ):
            # These statements don't return data, so return empty schema
            return pa.schema([])

        # Handle SHOW DATABASES specifically
        if query_upper.startswith("SHOW DATABASES"):
            # Return the expected schema for SHOW DATABASES (single column "Database")
            return pa.schema([pa.field("Database", pa.string())])

        try:
            # For SELECT statements and other queries that return data,
            # use DuckDB's PREPARE to get the schema

            duckdb_log.info(f"Getting schema for query: {query}")

            # Special handling for parameterized queries (contains ?)
            if "?" in query:
                duckdb_log.info("Query contains parameters, using special handling")
                # For parameterized queries, try to get schema by executing a LIMIT 0 version
                # This approach works better than PREPARE with unbound parameters
                try:
                    # Create a version of the query with LIMIT 0 to get just the schema
                    # Replace parameters with reasonable dummy values
                    schema_query = query

                    # Simple parameter replacement strategy
                    # For most common cases, replace ? with 1 (works for numeric, string comparisons)
                    param_count = query.count("?")
                    duckdb_log.info(f"Found {param_count} parameters in query")

                    # Replace each ? with a dummy value that should work for schema detection
                    for i in range(param_count):
                        schema_query = schema_query.replace(
                            "?", "1", 1
                        )  # Use 1 as a generic dummy value

                    # Add LIMIT 0 to avoid actually executing the query with data
                    if "LIMIT" not in schema_query.upper():
                        schema_query = f"({schema_query}) LIMIT 0"

                    duckdb_log.info(f"Schema detection query: {schema_query}")

                    # Execute the query to get the schema
                    result = self.connection.execute(schema_query).fetch_arrow_table()
                    schema = result.schema
                    duckdb_log.info(f"Created schema from query execution: {schema}")
                    return schema

                except Exception as param_error:
                    duckdb_log.error(
                        f"Query-based schema detection failed: {param_error}"
                    )
                    # Try the PREPARE approach as fallback
                    try:
                        # Replace parameters with NULL for PREPARE
                        schema_query = query
                        param_count = query.count("?")
                        for i in range(param_count):
                            schema_query = schema_query.replace("?", "NULL", 1)

                        duckdb_log.info(
                            f"Fallback PREPARE schema detection query: {schema_query}"
                        )
                        prepare_query = f"PREPARE stmt AS {schema_query}"
                        self.connection.execute(prepare_query)

                        # Get the prepared statement info
                        describe_result = self.connection.execute(
                            "DESCRIBE stmt"
                        ).fetchall()
                        duckdb_log.info(f"DESCRIBE result: {describe_result}")

                        # Clean up the prepared statement
                        self.connection.execute("DEALLOCATE stmt")

                        fields = []
                        for row in describe_result:
                            col_name = row[0]
                            col_type = row[1]
                            # Convert DuckDB types to Arrow types
                            arrow_type = self._duckdb_type_to_arrow(col_type)
                            fields.append(pa.field(col_name, arrow_type))

                        schema = pa.schema(fields)
                        duckdb_log.info(f"Created schema from PREPARE: {schema}")
                        return schema
                    except Exception as prepare_error:
                        duckdb_log.error(
                            f"PREPARE fallback also failed: {prepare_error}"
                        )
                        # Last resort: return empty schema
                        return pa.schema([])

            duckdb_log.info("Using standard PREPARE approach")
            prepare_query = f"PREPARE stmt AS {query}"
            self.connection.execute(prepare_query)

            # Get the prepared statement info
            describe_result = self.connection.execute("DESCRIBE stmt").fetchall()

            # Clean up the prepared statement
            self.connection.execute("DEALLOCATE stmt")

            fields = []
            for row in describe_result:
                col_name = row[0]
                col_type = row[1]
                # Convert DuckDB types to Arrow types
                arrow_type = self._duckdb_type_to_arrow(col_type)
                fields.append(pa.field(col_name, arrow_type))

            return pa.schema(fields)

        except Exception as e:
            logger.error(f"Schema analysis with PREPARE failed: {e}")
            # Fallback: try to use LIMIT 0 approach for SELECT statements
            try:
                if query_upper.startswith("SELECT "):
                    limited_query = f"SELECT * FROM ({query}) LIMIT 0"
                    result = self.connection.execute(limited_query).arrow()

                    if isinstance(result, pa.Table):
                        return result.schema
                    else:
                        return result.schema
                else:
                    # For non-SELECT statements, return empty schema
                    return pa.schema([])

            except Exception as e2:
                logger.error(f"Schema fallback failed: {e2}")
                # Last resort: return empty schema
                return pa.schema([])

    def _duckdb_type_to_arrow(self, duckdb_type: str) -> pa.DataType:
        """Convert DuckDB type string to PyArrow DataType."""
        # Handle common DuckDB types and convert to appropriate Arrow types
        duckdb_type = duckdb_type.upper()

        # Handle parameterized types (e.g., VARCHAR(50), DECIMAL(10,2))
        base_type = duckdb_type.split("(")[0].strip()

        type_mapping = {
            # Integer types
            "TINYINT": pa.int8(),
            "SMALLINT": pa.int16(),
            "INTEGER": pa.int32(),
            "INT": pa.int32(),
            "BIGINT": pa.int64(),
            "UTINYINT": pa.uint8(),
            "USMALLINT": pa.uint16(),
            "UINTEGER": pa.uint32(),
            "UBIGINT": pa.uint64(),
            # Floating point types
            "REAL": pa.float32(),
            "FLOAT": pa.float32(),
            "DOUBLE": pa.float64(),
            # String types
            "VARCHAR": pa.string(),
            "TEXT": pa.string(),
            "STRING": pa.string(),
            "CHAR": pa.string(),
            # Boolean
            "BOOLEAN": pa.bool_(),
            "BOOL": pa.bool_(),
            # Date/Time types
            "DATE": pa.date32(),
            "TIME": pa.time64("us"),
            "TIMESTAMP": pa.timestamp("us"),
            "TIMESTAMPTZ": pa.timestamp("us", tz="UTC"),
            "INTERVAL": pa.duration("us"),
            # Binary types
            "BLOB": pa.binary(),
            "BYTEA": pa.binary(),
            # UUID
            "UUID": pa.string(),  # Arrow doesn't have native UUID, use string
        }

        # Handle DECIMAL types specially
        if base_type == "DECIMAL" or base_type == "NUMERIC":
            # Extract precision and scale if present
            if "(" in duckdb_type:
                try:
                    params = duckdb_type.split("(")[1].split(")")[0]
                    if "," in params:
                        precision, scale = map(int, params.split(","))
                        return pa.decimal128(precision, scale)
                    else:
                        precision = int(params)
                        return pa.decimal128(precision, 0)
                except (ValueError, IndexError):
                    pass
            return pa.decimal128(18, 3)  # Default precision and scale

        # Handle LIST types
        if base_type == "LIST" or duckdb_type.endswith("[]"):
            # For now, return a generic list of strings
            # This could be enhanced to parse the inner type
            return pa.list_(pa.string())

        # Handle STRUCT types
        if base_type == "STRUCT":
            # For now, return a generic struct
            # This could be enhanced to parse the field types
            return pa.struct([pa.field("field", pa.string())])

        # Handle MAP types
        if base_type == "MAP":
            # For now, return a generic map
            return pa.map_(pa.string(), pa.string())

        # Return mapped type or default to string
        return type_mapping.get(base_type, pa.string())

    def get_catalogs(self) -> pa.Table:
        """Get available catalogs as an Arrow table."""
        try:
            # Use the same query as Examples implementation
            query = "SELECT DISTINCT catalog_name FROM information_schema.schemata ORDER BY catalog_name"
            duckdb_log.info(f"get_catalogs() - Executing query: {query}")
            fh.flush()
            result = self.connection.execute(query).fetchall()
            catalogs = [row[0] for row in result]
            duckdb_log.info(
                f"get_catalogs() - Query returned {len(catalogs)} catalogs: {catalogs}"
            )

            # If no catalogs found, fall back to SHOW DATABASES
            if not catalogs:
                query = "SHOW DATABASES"
                duckdb_log.info(f"get_catalogs() - Fallback query: {query}")
                fh.flush()
                result = self.connection.execute(query).fetchall()
                catalogs = [row[0] for row in result]
                duckdb_log.info(
                    f"get_catalogs() - Fallback query returned {len(catalogs)} catalogs: {catalogs}"
                )

            # Return as Arrow table with proper schema
            schema = pa.schema([("catalog_name", pa.string())])
            table = pa.table({"catalog_name": catalogs}, schema=schema)
            # Convert to compatible types for JDBC driver
            table = self._convert_large_utf8_to_utf8(table)
            duckdb_log.info(f"get_catalogs() - Returning table with {len(table)} rows")
            fh.flush()
            return table
        except Exception as e:
            duckdb_log.error(f"get_catalogs() - Error: {e}")
            fh.flush()
            logger.warning(f"Could not get catalogs: {e}")
            # Return default catalog as Arrow table
            schema = pa.schema([("catalog_name", pa.string())])
            table = pa.table({"catalog_name": ["main"]}, schema=schema)
            # Convert to compatible types for JDBC driver
            table = self._convert_large_utf8_to_utf8(table)
            duckdb_log.info(
                f"get_catalogs() - Returning default table with {len(table)} rows"
            )
            fh.flush()
            return table

    def get_schemas(self, catalog: Optional[str] = None) -> List[Tuple[str, str]]:
        """Get available schemas for a catalog, returns (catalog, schema) tuples."""
        try:
            # Use the same query structure as Examples implementation
            query = """
            SELECT catalog_name, schema_name AS db_schema_name 
            FROM information_schema.schemata 
            WHERE 1 = 1
            """

            params = []

            # Match Examples server behavior: use CURRENT_DATABASE() when catalog is None
            if catalog is not None:
                query += " AND catalog_name = ?"
                params.append(catalog)
            else:
                query += " AND catalog_name = CURRENT_DATABASE()"

            query += " ORDER BY catalog_name, db_schema_name"

            # Execute with parameters
            if params:
                result = self.connection.execute(query, params).fetchall()
            else:
                result = self.connection.execute(query).fetchall()

            return [(row[0], row[1]) for row in result]
        except Exception as e:
            logger.warning(f"Could not get schemas: {e}")
            # Fallback to basic approach
            try:
                if catalog is None:
                    catalogs_table = self.get_catalogs()
                    catalogs = catalogs_table.to_pydict()["catalog_name"]
                else:
                    catalogs = [catalog]
                result_schemas = []

                for cat in catalogs:
                    if cat != "main":
                        self.connection.execute(f"USE {cat}")

                    try:
                        result = self.connection.execute("SHOW SCHEMAS").fetchall()
                        schemas = [row[0] for row in result]

                        for schema in schemas:
                            result_schemas.append((cat, schema))
                    except Exception:
                        result_schemas.extend(
                            [(cat, "main"), (cat, "information_schema")]
                        )

                    if cat != "main":
                        self.connection.execute("USE main")

                return result_schemas
            except Exception as e2:
                logger.error(f"Schema fallback failed: {e2}")
                return [
                    ("main", "main"),
                    ("main", "information_schema"),
                ]  # Default schemas

    def get_tables(
        self,
        catalog: Optional[str] = None,
        db_schema_filter_pattern: Optional[str] = None,
        table_name_filter_pattern: Optional[str] = None,
        table_types: Optional[List[str]] = None,
        include_schema: bool = False,
    ) -> pa.Table:
        """Get available tables with their metadata as an Arrow table."""
        # Correctly handle LIKE patterns
        db_schema_filter_pattern = (
            db_schema_filter_pattern.replace("*", "%")
            if db_schema_filter_pattern
            else None
        )
        table_name_filter_pattern = (
            table_name_filter_pattern.replace("*", "%")
            if table_name_filter_pattern
            else None
        )

        query = """
            SELECT 
                table_catalog as catalog_name,
                table_schema as db_schema_name, 
                table_name,
                table_type
            FROM information_schema.tables
            WHERE 1=1
        """

        params = []
        # Match Examples server behavior: use CURRENT_DATABASE() when catalog is None
        # This is correct for FlightSQL protocol - JDBC GUIs should call getTables(catalogName) for each catalog
        if catalog is not None:
            query += " AND table_catalog = ?"
            params.append(catalog)
            duckdb_log.info(f"get_tables() - Filtering by catalog: {catalog}")
        else:
            query += " AND table_catalog = CURRENT_DATABASE()"
            duckdb_log.info(
                "get_tables() - No catalog specified, using CURRENT_DATABASE() filter"
            )
        if db_schema_filter_pattern:
            query += " AND table_schema LIKE ?"
            params.append(db_schema_filter_pattern)
        if table_name_filter_pattern:
            query += " AND table_name LIKE ?"
            params.append(table_name_filter_pattern)
        if table_types:
            placeholders = ",".join("?" * len(table_types))
            query += f" AND table_type IN ({placeholders})"
            params.extend(table_types)

        query += " ORDER BY table_name"
        duckdb_log.info(f"get_tables() - Executing query: {query} with params {params}")

        try:
            result_table = self.connection.execute(query, params).arrow()
            duckdb_log.info(
                f"get_tables() - Query returned {result_table.num_rows} tables"
            )

            # Log the results to track catalog-schema-table relationships
            if result_table.num_rows > 0:
                catalogs = result_table.column("catalog_name").to_pylist()
                schemas = result_table.column("db_schema_name").to_pylist()
                tables = result_table.column("table_name").to_pylist()
                table_types = result_table.column("table_type").to_pylist()
                duckdb_log.info("get_tables() - Catalog-Schema-Table relationships:")
                for i, (cat, schema, table, ttype) in enumerate(
                    zip(catalogs, schemas, tables, table_types)
                ):
                    duckdb_log.info(f"  {i + 1}. {cat}.{schema}.{table} ({ttype})")
            else:
                duckdb_log.warning("get_tables() - No tables found!")

            # Convert to compatible types for JDBC driver
            result_table = self._convert_large_utf8_to_utf8(result_table)

            # Define the base schema, which is always returned.
            base_fields = [
                pa.field("catalog_name", pa.string()),
                pa.field("db_schema_name", pa.string()),
                pa.field("table_name", pa.string()),
                pa.field("table_type", pa.string()),
            ]

            if include_schema:
                duckdb_log.info("get_tables() - Including schema as requested.")
                table_schemas_bytes = []
                for table_row in result_table.to_pylist():
                    table_name = table_row["table_name"]
                    catalog_name = table_row["catalog_name"]
                    schema_name = table_row["db_schema_name"]

                    try:
                        # Use proper qualified table name with catalog and schema
                        qualified_table = (
                            f'"{catalog_name}"."{schema_name}"."{table_name}"'
                        )
                        schema_query = f"SELECT * FROM {qualified_table} WHERE 1 = 0"
                        duckdb_log.info(
                            f"Executing schema query for {table_name}: {schema_query}"
                        )

                        schema_result = self.connection.execute(schema_query).arrow()

                        # Get the schema from the empty result
                        arrow_schema = schema_result.schema
                        duckdb_log.info(
                            f"Got Arrow schema for {table_name}: {arrow_schema}"
                        )

                        # Serialize the schema to bytes as required by Flight SQL
                        import io

                        import pyarrow.ipc as ipc

                        # Write schema to a buffer
                        buffer = io.BytesIO()
                        with ipc.new_stream(buffer, arrow_schema) as _:
                            pass  # Just creating the stream writes the schema
                        schema_bytes = buffer.getvalue()
                        table_schemas_bytes.append(schema_bytes)

                        duckdb_log.info(
                            f"Successfully serialized schema for table {table_name} ({len(schema_bytes)} bytes)"
                        )
                    except Exception as e:
                        duckdb_log.error(
                            f"Failed to get schema for table {table_name}: {e}"
                        )
                        table_schemas_bytes.append(None)

                duckdb_log.info(f"Collected {len(table_schemas_bytes)} table schemas")

                # Add the serialized schema as a new column
                schema_col = pa.array(table_schemas_bytes, type=pa.binary())
                result_table = result_table.append_column("table_schema", schema_col)

                # Update the schema to include the new column
                final_schema = pa.schema(
                    base_fields + [pa.field("table_schema", pa.binary())]
                )
                result_table = result_table.cast(final_schema)
                duckdb_log.info(
                    f"get_tables() - Successfully added 'table_schema' column. Final table has {result_table.num_rows} rows and {result_table.num_columns} columns"
                )

            return result_table

        except Exception as e:
            duckdb_log.error(f"get_tables() - An error occurred: {e}", exc_info=True)
            # On error, return an empty table with the correct schema
            if include_schema:
                schema = pa.schema(
                    [
                        pa.field("catalog_name", pa.string()),
                        pa.field("db_schema_name", pa.string()),
                        pa.field("table_name", pa.string()),
                        pa.field("table_type", pa.string()),
                        pa.field("table_schema", pa.binary()),
                    ]
                )
            else:
                schema = pa.schema(
                    [
                        pa.field("catalog_name", pa.string()),
                        pa.field("db_schema_name", pa.string()),
                        pa.field("table_name", pa.string()),
                        pa.field("table_type", pa.string()),
                    ]
                )
            empty_table = schema.empty_table()
            return self._convert_large_utf8_to_utf8(empty_table)

    def get_table_types(self) -> pa.Table:
        """Get available table types as an Arrow table."""
        # DuckDB supports these standard table types
        table_types = ["BASE TABLE", "VIEW", "LOCAL TEMPORARY", "SYSTEM TABLE"]

        # Create Arrow table with proper schema for FlightSQL
        schema = pa.schema([("table_type", pa.string())])
        table = pa.table({"table_type": table_types}, schema=schema)
        # Convert to compatible types for JDBC driver
        return self._convert_large_utf8_to_utf8(table)

    def get_columns(
        self,
        catalog: Optional[str] = None,
        db_schema_filter_pattern: Optional[str] = None,
        table_name_filter_pattern: Optional[str] = None,
        column_name_filter_pattern: Optional[str] = None,
    ) -> pa.Table:
        """Get columns for a table as an Arrow table."""
        try:
            # Base query to get column metadata from DuckDB
            query = """
            SELECT
                table_catalog AS catalog_name,
                table_schema AS db_schema_name,
                table_name,
                column_name,
                data_type,
                ordinal_position AS "DECIMAL_DIGITS", 
                'YES' as "IS_NULLABLE",
                0 as "NUM_PREC_RADIX"
            FROM information_schema.columns
            WHERE 1=1
            """

            conditions = []
            # For JDBC metadata queries, when catalog is None, return ALL columns from ALL catalogs
            # This matches the expected JDBC behavior where getColumns() returns all columns
            if catalog is not None:
                conditions.append(f"table_catalog = '{catalog}'")
            if db_schema_filter_pattern:
                conditions.append(
                    f"table_schema LIKE '{db_schema_filter_pattern.replace('*', '%')}'"
                )
            if table_name_filter_pattern:
                conditions.append(
                    f"table_name LIKE '{table_name_filter_pattern.replace('*', '%')}'"
                )
            if column_name_filter_pattern:
                conditions.append(
                    f"column_name LIKE '{column_name_filter_pattern.replace('*', '%')}'"
                )

            if conditions:
                query += " AND " + " AND ".join(conditions)

            query += (
                " ORDER BY table_catalog, table_schema, table_name, ordinal_position"
            )

            duckdb_log.info(f"Executing get_columns query: {query}")
            result_table = self.connection.execute(query).arrow()
            duckdb_log.info(f"get_columns query returned {result_table.num_rows} rows.")

            # Ensure the table has the correct schema expected by Flight SQL's GetColumns.
            # The schema is defined in FlightSQLProtobuf.get_columns_schema()

            # Create a list of columns that match the expected schema.
            # We will create new columns for the fields that are not directly available from the query.

            num_rows = len(result_table)

            # Helper to create a column, filling with nulls if it doesn't exist in the source table.
            def get_column_or_null(table, name, type):
                if name in table.schema.names:
                    return table.column(name).cast(type)
                else:
                    return pa.nulls(num_rows, type=type)

            # A simple mapping from DuckDB types to SQL type codes (INTEGER for now)
            # This should be expanded for correctness.
            # For now, we will use a placeholder.
            # This is a major source of errors if not correct.
            # Let's try to map some common types.
            type_name_col = result_table.column("data_type").cast(pa.string())

            # A very basic type mapping. This needs to be more robust.
            # Ref: java.sql.Types
            sql_type_map = {
                "BIGINT": -5,
                "BOOLEAN": 16,
                "BLOB": 2004,
                "DATE": 91,
                "DOUBLE": 8,
                "INTEGER": 4,
                "FLOAT": 6,
                "REAL": 7,
                "SMALLINT": 5,
                "TIME": 92,
                "TIMESTAMP": 93,
                "TINYINT": -6,
                "VARCHAR": 12,
                "UUID": -11,
                "INTERVAL": -10,
                "DECIMAL": 3,
                "LIST": 2003,
                "STRUCT": 2002,
                "MAP": 2000,
            }

            def map_type_name_to_sql_type(type_name):
                if not type_name:
                    return 0  # java.sql.Types.NULL
                # take the base type
                base_type = type_name.split("(")[0].upper()
                return sql_type_map.get(base_type, 12)  # Default to VARCHAR

            data_type_values = [
                map_type_name_to_sql_type(s.as_py()) for s in type_name_col
            ]
            data_type_col = pa.array(data_type_values, type=pa.int32())

            # is_nullable to int32
            is_nullable_col_str = result_table.column("IS_NULLABLE")
            nullable_values = [
                1 if s and s.as_py() == "YES" else 0 for s in is_nullable_col_str
            ]
            nullable_col = pa.array(nullable_values, type=pa.int32())

            # Construct the final table
            final_table = pa.table(
                [
                    result_table.column("catalog_name"),
                    result_table.column("db_schema_name"),
                    result_table.column("table_name"),
                    result_table.column("column_name"),
                    data_type_col,
                    type_name_col,
                    pa.nulls(num_rows, pa.int32()),  # column_size
                    pa.nulls(num_rows, pa.int32()),  # buffer_length
                    result_table.column("DECIMAL_DIGITS").cast(pa.int32()),
                    result_table.column("NUM_PREC_RADIX").cast(pa.int32()),
                    nullable_col,  # nullable
                    pa.nulls(num_rows, pa.string()),  # remarks
                    pa.nulls(num_rows, pa.string()),  # column_def
                    data_type_col,  # sql_data_type
                    pa.nulls(num_rows, pa.int32()),  # sql_datetime_sub
                    pa.nulls(num_rows, pa.int32()),  # char_octet_length
                    result_table.column("ordinal_position").cast(pa.int32()),
                    result_table.column("IS_NULLABLE"),
                    pa.nulls(num_rows, pa.string()),  # is_autoincrement
                    pa.nulls(num_rows, pa.string()),  # is_generatedcolumn
                ],
                names=[
                    "catalog_name",
                    "db_schema_name",
                    "table_name",
                    "column_name",
                    "data_type",
                    "type_name",
                    "column_size",
                    "buffer_length",
                    "decimal_digits",
                    "num_prec_radix",
                    "nullable",
                    "remarks",
                    "column_def",
                    "sql_data_type",
                    "sql_datetime_sub",
                    "char_octet_length",
                    "ordinal_position",
                    "is_nullable",
                    "is_autoincrement",
                    "is_generatedcolumn",
                ],
            )

            # Convert to compatible types for JDBC driver
            final_table = self._convert_large_utf8_to_utf8(final_table)
            return final_table

        except Exception as e:
            duckdb_log.error(f"Error in get_columns: {e}", exc_info=True)
            # Return empty table with correct schema on error
            schema = pa.schema(
                [
                    pa.field("catalog_name", pa.string()),
                    pa.field("db_schema_name", pa.string()),
                    pa.field("table_name", pa.string()),
                    pa.field("column_name", pa.string()),
                    pa.field("data_type", pa.int32()),
                    pa.field("type_name", pa.string()),
                    pa.field("column_size", pa.int32()),
                    pa.field("buffer_length", pa.int32()),
                    pa.field("decimal_digits", pa.int32()),
                    pa.field("num_prec_radix", pa.int32()),
                    pa.field("nullable", pa.int32()),
                    pa.field("remarks", pa.string()),
                    pa.field("column_def", pa.string()),
                    pa.field("sql_data_type", pa.int32()),
                    pa.field("sql_datetime_sub", pa.int32()),
                    pa.field("char_octet_length", pa.int32()),
                    pa.field("ordinal_position", pa.int32()),
                    pa.field("is_nullable", pa.string()),
                    pa.field("is_autoincrement", pa.string()),
                    pa.field("is_generatedcolumn", pa.string()),
                ]
            )
            empty_table = schema.empty_table()
            return self._convert_large_utf8_to_utf8(empty_table)

    def get_tables_filtered(self, filters: dict) -> pa.Table:
        """Get tables with proper filtering support"""
        try:
            # Build the query based on filters
            base_query = """
            SELECT 
                current_database() as catalog_name,
                schema_name,
                table_name,
                table_type
            FROM information_schema.tables 
            WHERE 1=1
            """

            conditions = []

            # Catalog filter
            if filters.get("catalog"):
                conditions.append(f"catalog_name = '{filters['catalog']}'")

            # Schema pattern filter
            if filters.get("schema_pattern"):
                if "%" in filters["schema_pattern"]:
                    conditions.append(f"schema_name LIKE '{filters['schema_pattern']}'")
                else:
                    conditions.append(f"schema_name = '{filters['schema_pattern']}'")

            # Table name pattern filter
            if filters.get("table_name_pattern"):
                pattern = filters["table_name_pattern"]
                if "%" in pattern:
                    conditions.append(f"table_name LIKE '{pattern}'")
                else:
                    conditions.append(f"table_name = '{pattern}'")

            # Table types filter
            if filters.get("table_types"):
                types_str = "', '".join(filters["table_types"])
                conditions.append(f"table_type IN ('{types_str}')")

            # Add all conditions
            if conditions:
                base_query += " AND " + " AND ".join(conditions)

            base_query += " ORDER BY catalog_name, schema_name, table_name"

            logger.info(f"Executing filtered GetTables query: {base_query}")

            # Execute the query
            result = self.conn.execute(base_query).arrow()

            logger.info(f"GetTables filtered result: {result.num_rows} rows")

            # If no results and we're looking for PostgreSQL system tables, return empty properly
            if result.num_rows == 0 and filters.get(
                "table_name_pattern", ""
            ).startswith("pg_"):
                logger.info(
                    f"No PostgreSQL system table found: {filters['table_name_pattern']}"
                )

            return result

        except Exception as e:
            logger.error(f"Error in get_tables_filtered: {e}")
            # Return empty result with correct schema
            schema = pa.schema(
                [
                    pa.field("catalog_name", pa.string()),
                    pa.field("schema_name", pa.string()),
                    pa.field("table_name", pa.string()),
                    pa.field("table_type", pa.string()),
                ]
            )
            return pa.Table.from_arrays(
                [
                    pa.array([], type=pa.string()),
                    pa.array([], type=pa.string()),
                    pa.array([], type=pa.string()),
                    pa.array([], type=pa.string()),
                ],
                schema=schema,
            )

    def close(self) -> None:
        """Close the DuckDB connection."""
        try:
            if self.connection:
                self.connection.close()
                logger.info("DuckDB connection closed")
        except Exception as e:
            logger.error(f"Error closing DuckDB connection: {e}")

    def get_sql_info(self, info_codes: List[int]) -> pa.Table:
        """Get SQL info for the given info codes as an Arrow table."""
        # This is a placeholder implementation.
        # It should be updated to return correct values based on the info_codes.
        info_name_array = pa.array(info_codes, type=pa.int32())
        value_array = pa.array(
            [f"value_{code}" for code in info_codes], type=pa.string()
        )

        schema = pa.schema(
            [pa.field("info_name", pa.int32()), pa.field("value", pa.string())]
        )

        return pa.Table.from_arrays([info_name_array, value_array], schema=schema)

    def get_db_schemas(
        self,
        catalog: Optional[str] = None,
        db_schema_filter_pattern: Optional[str] = None,
    ) -> pa.Table:
        """Get available schemas for a catalog as an Arrow table."""
        try:
            query = """
            SELECT catalog_name, schema_name AS db_schema_name 
            FROM information_schema.schemata 
            WHERE 1 = 1
            """

            params = []

            # Match Examples server behavior: use CURRENT_DATABASE() when catalog is None
            # This is correct for FlightSQL protocol - JDBC GUIs should call getSchemas(catalogName) for each catalog
            if catalog is not None:
                query += " AND catalog_name = ?"
                params.append(catalog)
                duckdb_log.info(f"get_db_schemas() - Filtering by catalog: {catalog}")
            else:
                query += " AND catalog_name = CURRENT_DATABASE()"
                duckdb_log.info(
                    "get_db_schemas() - No catalog specified, using CURRENT_DATABASE() filter"
                )

            if db_schema_filter_pattern:
                query += " AND schema_name LIKE ?"
                params.append(db_schema_filter_pattern.replace("*", "%"))

            query += " ORDER BY catalog_name, db_schema_name"

            duckdb_log.info(f"get_db_schemas() - Final query: {query}")
            duckdb_log.info(f"get_db_schemas() - Query params: {params}")

            # Execute with parameters
            if params:
                result = self.connection.execute(query, params).arrow()
            else:
                result = self.connection.execute(query).arrow()

            # Log the results to track catalog-schema relationships
            duckdb_log.info(f"get_db_schemas() - Query returned {result.num_rows} rows")
            if result.num_rows > 0:
                catalogs = result.column("catalog_name").to_pylist()
                schemas = result.column("db_schema_name").to_pylist()
                duckdb_log.info("get_db_schemas() - Catalog-Schema relationships:")
                for i, (cat, schema) in enumerate(zip(catalogs, schemas)):
                    duckdb_log.info(f"  {i + 1}. {cat} -> {schema}")
            else:
                duckdb_log.warning("get_db_schemas() - No schemas found!")

            # Convert to compatible types for JDBC driver
            result = self._convert_large_utf8_to_utf8(result)
            return result

        except Exception as e:
            logger.error(f"Error in get_db_schemas: {e}")
            # Return empty table with correct schema
            schema = pa.schema(
                [
                    pa.field("catalog_name", pa.string()),
                    pa.field("db_schema_name", pa.string()),
                ]
            )
            table = pa.table({"catalog_name": [], "db_schema_name": []}, schema=schema)
            return self._convert_large_utf8_to_utf8(table)

    # ===== RAW FLIGHT DO_PUT SUPPORT METHODS =====
    # Added for raw Flight do_put functionality to create DuckDB tables directly from Arrow data

    def _table_exists(self, table_name: str) -> bool:
        """Check if a table exists using DuckDB's recommended approach.

        Uses a simple SELECT to test table existence, which works with fully qualified names
        and avoids complex information_schema parsing.
        """
        try:
            # Try to query the table with LIMIT 0 - if it succeeds, table exists
            self.connection.execute(f"SELECT 1 FROM {table_name} LIMIT 0")
            return True
        except Exception:
            # If query fails, table doesn't exist
            return False

    def _ensure_catalog_exists(self, table_name: str) -> None:
        """Ensure that the catalog exists for a qualified table name.

        For table names like 'my_ducklake.main.table_name', ensure the 'my_ducklake' catalog exists.
        If it doesn't exist, create it as an in-memory catalog for testing.
        """
        if "." in table_name:
            parts = table_name.split(".")
            if len(parts) >= 3:  # catalog.schema.table format
                catalog_name = parts[0]

                try:
                    # Check if catalog exists by trying to query it
                    self.connection.execute(
                        f"SELECT * FROM {catalog_name}.information_schema.schemata LIMIT 0"
                    )
                    duckdb_log.info(
                        f"_ensure_catalog_exists: Catalog '{catalog_name}' already exists"
                    )
                except Exception:
                    # Catalog doesn't exist, create it as in-memory
                    try:
                        self.connection.execute(f"CREATE DATABASE {catalog_name}")
                        duckdb_log.info(
                            f"_ensure_catalog_exists: Created in-memory catalog '{catalog_name}'"
                        )
                        duckdb_logger.info(
                            "Created in-memory catalog for testing",
                            catalog_name=catalog_name,
                        )
                    except Exception as e:
                        # If CREATE DATABASE fails, try ATTACH as in-memory
                        try:
                            self.connection.execute(
                                f"ATTACH ':memory:' AS {catalog_name}"
                            )
                            duckdb_log.info(
                                f"_ensure_catalog_exists: Attached in-memory catalog '{catalog_name}'"
                            )
                            duckdb_logger.info(
                                "Attached in-memory catalog for testing",
                                catalog_name=catalog_name,
                            )
                        except Exception as e2:
                            duckdb_log.warning(
                                f"_ensure_catalog_exists: Could not create catalog '{catalog_name}': {e}, {e2}"
                            )
                            # Continue anyway - DuckDB might handle it automatically

    def _ensure_catalog_exists(self, table_name: str) -> None:
        """Ensure that the catalog exists for a qualified table name.

        For table names like 'my_ducklake.main.table_name', ensure the 'my_ducklake' catalog exists.
        If it doesn't exist, create it as an in-memory catalog for testing.
        """
        if "." in table_name:
            parts = table_name.split(".")
            if len(parts) >= 3:  # catalog.schema.table format
                catalog_name = parts[0]

                try:
                    # Check if catalog exists by trying to query it
                    self.connection.execute(
                        f"SELECT * FROM {catalog_name}.information_schema.schemata LIMIT 0"
                    )
                    duckdb_log.info(
                        f"_ensure_catalog_exists: Catalog '{catalog_name}' already exists"
                    )
                except Exception:
                    # Catalog doesn't exist, create it as in-memory
                    try:
                        self.connection.execute(f"CREATE DATABASE {catalog_name}")
                        duckdb_log.info(
                            f"_ensure_catalog_exists: Created in-memory catalog '{catalog_name}'"
                        )
                        duckdb_logger.info(
                            "Created in-memory catalog for testing",
                            catalog_name=catalog_name,
                        )
                    except Exception as e:
                        # If CREATE DATABASE fails, try ATTACH as in-memory
                        try:
                            self.connection.execute(
                                f"ATTACH ':memory:' AS {catalog_name}"
                            )
                            duckdb_log.info(
                                f"_ensure_catalog_exists: Attached in-memory catalog '{catalog_name}'"
                            )
                            duckdb_logger.info(
                                "Attached in-memory catalog for testing",
                                catalog_name=catalog_name,
                            )
                        except Exception as e2:
                            duckdb_log.warning(
                                f"_ensure_catalog_exists: Could not create catalog '{catalog_name}': {e}, {e2}"
                            )
                            # Continue anyway - DuckDB might handle it automatically

    def create_table_from_arrow(self, table_name: str, arrow_table: pa.Table) -> None:
        """Create a DuckDB table directly from PyArrow Table data (batch mode)

        DuckDB will automatically handle fully qualified names like:
        - "my_table" → main.main.my_table (default database.schema.table)
        - "public.customers" → main.public.customers (database.schema.table)
        - "analytics.hr.employees" → analytics.hr.employees (database.schema.table)

        DuckDB automatically creates databases and schemas as needed!
        """

        # EXTENSIVE LOGGING
        duckdb_logger.info(
            "Creating DuckDB table from Arrow data (batch mode)",
            table_name=table_name,
            rows=len(arrow_table),
            columns=arrow_table.num_columns,
            schema=str(arrow_table.schema),
        )

        duckdb_log.info(
            f"create_table_from_arrow: table={table_name}, rows={len(arrow_table)}, cols={arrow_table.num_columns}"
        )

        try:
            # Ensure catalog exists if table name is qualified with a catalog
            self._ensure_catalog_exists(table_name)

            # DIRECT ARROW → DUCKDB TABLE CREATION!
            # DuckDB can directly create tables from PyArrow tables using register()
            # Step 1: Register the Arrow table as a temporary view with unique name
            temp_table_name = f"temp_arrow_table_{uuid.uuid4().hex[:8]}"
            self.connection.register(temp_table_name, arrow_table)

            # Step 2: Create or append based on table existence (DuckDB documented pattern)
            # Per DuckDB docs: CREATE TABLE AS for new tables, INSERT INTO for existing
            if self._table_exists(table_name):
                # Table exists - append data using INSERT INTO pattern
                duckdb_log.info(
                    f"create_table_from_arrow: Table {table_name} exists, appending data"
                )
                self.connection.execute(
                    f"INSERT INTO {table_name} SELECT * FROM {temp_table_name}"
                )
            else:
                # Table doesn't exist - create using CREATE TABLE AS pattern
                duckdb_log.info(
                    f"create_table_from_arrow: Table {table_name} doesn't exist, creating new table"
                )
                self.connection.execute(
                    f"CREATE TABLE {table_name} AS SELECT * FROM {temp_table_name}"
                )

            # Step 3: Unregister the temporary view to clean up
            self.connection.unregister(temp_table_name)

            # Step 4: Verify the table was created successfully
            row_count = self.connection.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone()[0]

            duckdb_logger.info(
                "Successfully created DuckDB table from Arrow data",
                table_name=table_name,
                final_rows=row_count,
            )

            duckdb_log.info(
                f"create_table_from_arrow: SUCCESS - table={table_name} created with {len(arrow_table)} rows"
            )

        except Exception as e:
            duckdb_logger.error(
                "Failed to create DuckDB table from Arrow data",
                table_name=table_name,
                error=str(e),
            )

            duckdb_log.error(
                f"create_table_from_arrow: ERROR - table={table_name}, error={e}"
            )
            raise

    def create_table_from_schema(
        self, table_name: str, arrow_schema: pa.Schema
    ) -> None:
        """Create an empty DuckDB table from PyArrow Schema (streaming mode - first chunk)

        DuckDB will automatically handle fully qualified names and create databases/schemas as needed.
        """

        # EXTENSIVE LOGGING
        duckdb_logger.info(
            "Creating empty DuckDB table from Arrow schema (streaming mode)",
            table_name=table_name,
            schema=str(arrow_schema),
        )

        duckdb_log.info(
            f"create_table_from_schema: table={table_name}, schema={arrow_schema}"
        )

        try:
            # Ensure catalog exists if table name is qualified with a catalog
            self._ensure_catalog_exists(table_name)

            # Create empty table with schema from Arrow Schema
            # Step 1: Create an empty Arrow table with the correct schema
            # Build empty column data for each field in the schema
            empty_columns = {}
            for field in arrow_schema:
                # Create empty array of the correct type
                empty_array = pa.array([], type=field.type)
                empty_columns[field.name] = empty_array

            empty_table = pa.table(empty_columns, schema=arrow_schema)

            # Step 2: Register and create table using same pattern as batch mode
            temp_table_name = f"temp_schema_table_{uuid.uuid4().hex[:8]}"
            self.connection.register(temp_table_name, empty_table)
            self.connection.execute(
                f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM {temp_table_name}"
            )
            self.connection.unregister(temp_table_name)

            duckdb_logger.info(
                "Successfully created empty DuckDB table from schema",
                table_name=table_name,
            )

            duckdb_log.info(
                f"create_table_from_schema: SUCCESS - empty table={table_name} created"
            )

        except Exception as e:
            duckdb_logger.error(
                "Failed to create empty DuckDB table from schema",
                table_name=table_name,
                error=str(e),
            )

            duckdb_log.error(
                f"create_table_from_schema: ERROR - table={table_name}, error={e}"
            )
            raise

    def append_table_from_arrow(self, table_name: str, arrow_table: pa.Table) -> None:
        """Append Arrow data to existing DuckDB table (streaming mode - subsequent chunks)

        Used in streaming mode to append each chunk to the existing table.
        """

        # EXTENSIVE LOGGING
        duckdb_logger.debug(
            "Appending Arrow data to existing DuckDB table",
            table_name=table_name,
            rows=len(arrow_table),
            columns=arrow_table.num_columns,
        )

        duckdb_log.info(
            f"append_table_from_arrow: table={table_name}, rows={len(arrow_table)}"
        )

        try:
            # Ensure catalog exists if table name is qualified with a catalog
            self._ensure_catalog_exists(table_name)

            # INSERT INTO existing table FROM Arrow data
            # Step 1: Register the Arrow table temporarily with unique name
            temp_table_name = f"temp_append_table_{uuid.uuid4().hex[:8]}"
            self.connection.register(temp_table_name, arrow_table)

            # Step 2: Insert from the registered table
            self.connection.execute(
                f"INSERT INTO {table_name} SELECT * FROM {temp_table_name}"
            )

            # Step 3: Clean up the temporary registration
            self.connection.unregister(temp_table_name)

            duckdb_logger.debug(
                "Successfully appended Arrow data to DuckDB table",
                table_name=table_name,
                appended_rows=len(arrow_table),
            )

            duckdb_log.info(
                f"append_table_from_arrow: SUCCESS - appended {len(arrow_table)} rows to table={table_name}"
            )

        except Exception as e:
            duckdb_logger.error(
                "Failed to append Arrow data to DuckDB table",
                table_name=table_name,
                error=str(e),
            )

            duckdb_log.error(
                f"append_table_from_arrow: ERROR - table={table_name}, error={e}"
            )
            raise

    def get_table_schema(self, table_name: str) -> pa.Schema:
        """Get the PyArrow schema for the specified table."""
        try:
            # Ensure catalog exists for qualified table names
            self._ensure_catalog_exists(table_name)

            # Query the table to get its schema
            result = self.connection.execute(
                f"SELECT * FROM {table_name} LIMIT 0"
            ).arrow()

            duckdb_logger.debug(
                "Successfully retrieved table schema",
                table_name=table_name,
                schema_fields=len(result.schema),
            )

            duckdb_log.info(
                f"get_table_schema: SUCCESS - table={table_name}, fields={len(result.schema)}"
            )

            return result.schema

        except Exception as e:
            duckdb_logger.error(
                "Failed to get table schema", table_name=table_name, error=str(e)
            )

            duckdb_log.error(f"get_table_schema: ERROR - table={table_name}, error={e}")
            raise

    def get_table_row_count(self, table_name: str) -> int:
        """Get the number of rows in the specified table."""
        try:
            # Ensure catalog exists for qualified table names
            self._ensure_catalog_exists(table_name)

            result = self.connection.execute(
                f"SELECT COUNT(*) as row_count FROM {table_name}"
            ).fetchone()
            row_count = result[0] if result else 0

            duckdb_logger.debug(
                "Successfully retrieved table row count",
                table_name=table_name,
                row_count=row_count,
            )

            duckdb_log.info(
                f"get_table_row_count: SUCCESS - table={table_name}, rows={row_count}"
            )

            return row_count

        except Exception as e:
            duckdb_logger.error(
                "Failed to get table row count", table_name=table_name, error=str(e)
            )

            duckdb_log.error(
                f"get_table_row_count: ERROR - table={table_name}, error={e}"
            )
            raise

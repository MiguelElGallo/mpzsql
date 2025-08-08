# Raw Flight do_put Implementation Plan for MPZSQL

## ✅ CORRECTED CONCEPT: Direct DuckDB Table Creation (No File I/O!)

**What this implementation does:**
1. **Client uploads Arrow data** via `FlightDescriptor.for_path("my_table")`
2. **Server receives Arrow data** in the `do_put` method
3. **Server creates DuckDB table directly** using `duckdb.sql("CREATE TABLE my_table AS SELECT * FROM my_arrow")`
4. **No files involved** - just in-memory Arrow → DuckDB table transformation
5. **Extensive logging** to `actions.log`, `server_duckdb.log`, `server_routing.log`, etc.

**Key Examples:**
- `FlightDescriptor.for_path("users")` → Creates DuckDB table named `"users"` (in default schema)
- `FlightDescriptor.for_path("sales_data")` → Creates DuckDB table named `"sales_data"` (in default schema)
- `FlightDescriptor.for_path("products_stream")` → Creates DuckDB table named `"products_stream"` (using streaming mode)
- `FlightDescriptor.for_path("analytics.public.customers")` → Creates DuckDB table `"analytics.public.customers"` (fully qualified - DuckDB handles it natively)
- `FlightDescriptor.for_path("warehouse.staging.orders")` → Creates DuckDB table `"warehouse.staging.orders"` (DuckDB will create database/schema as needed)

**The Table Creation Process:**
```python
# Client uploads with fully qualified table name
data_table = pa.table({"name": ["Alice", "Bob"], "age": [25, 30]})
descriptor = pf.FlightDescriptor.for_path("analytics.hr.employees")  # ← Fully qualified table name
writer, _ = client.do_put(descriptor, data_table.schema, options=options)
writer.write_table(data_table)

# Server processes
def _handle_batch_upload(self, table_name, reader, writer):
    arrow_table = reader.read_all()  # ← Get the Arrow data

    # Direct DuckDB table creation with full qualification - DuckDB handles database/schema creation!
    self.backend.create_table_from_arrow(table_name, arrow_table)  # ← DuckDB: CREATE TABLE analytics.hr.employees AS SELECT * FROM arrow_table

# Result: DuckDB table "analytics.hr.employees" ready for SQL queries!
# DuckDB automatically creates the "analytics" database and "hr" schema as needed!
```

## Current State ✅

Your MPZSQL server already has a working `do_put` implementation that supports:

1. **FlightSQL CommandStatementUpdate** - SQL INSERT/UPDATE/DELETE operations
2. **FlightSQL CommandPreparedStatementUpdate** - Prepared statement updates with parameters
3. **FlightSQL CommandPreparedStatementQuery** - Parameter binding for queries

This works perfectly with ADBC FlightSQL clients and handles the FlightSQL protocol correctly.

## What You Want to Add 🎯

You want to support **raw PyArrow Flight do_put** for file uploads, like this:

```python
import pyarrow as pa
import pyarrow.flight as pf

client = pf.FlightClient("grpc+tls://localhost:8080")
token_pair = client.authenticate_basic_token(b'user', b'password')
options = pf.FlightCallOptions(headers=[token_pair])

# Upload a dataset to a path
data_table = pa.table([["Mario", "Luigi", "Peach"]], names=["Character"])
upload_descriptor = pf.FlightDescriptor.for_path("uploaded.parquet")
writer, _ = client.do_put(upload_descriptor, data_table.schema, options=options)
writer.write_table(data_table)
writer.close()
```

## Preserving Existing FlightSQL Functionality ✅

**Important**: All existing FlightSQL functionality will remain completely unchanged! The implementation uses a clean separation based on descriptor types:

```python
def do_put(self, context, descriptor, reader, writer):
    if descriptor.descriptor_type == pf.DescriptorType.COMMAND:
        # EXISTING: All current FlightSQL functionality stays exactly the same
        # - CommandStatementUpdate (SQL INSERT/UPDATE/DELETE)
        # - CommandPreparedStatementUpdate (prepared statements)
        # - CommandPreparedStatementQuery (parameter binding)
        return self._handle_flightsql_do_put(context, descriptor, reader, writer)

    elif descriptor.descriptor_type == pf.DescriptorType.PATH:
        # NEW: File upload functionality with streaming support
        return self._handle_file_upload_do_put(context, descriptor, reader, writer)

    else:
        raise NotImplementedError(f"Unsupported descriptor type: {descriptor.descriptor_type}")

def _handle_flightsql_do_put(self, context, descriptor, reader, writer):
    """Existing FlightSQL do_put logic - UNCHANGED"""
    # Move all your current do_put logic here
    # This preserves 100% compatibility with:
    # - ADBC FlightSQL clients
    # - Prepared statements
    # - Parameter binding
    # - All existing functionality

    command_bytes = descriptor.command
    any_command = parse_any_command(command_bytes)
    # ... rest of existing do_put logic
```

**No Breaking Changes**:
- Your existing `client_test.py` will continue to work perfectly
- All ADBC FlightSQL functionality is preserved
- Prepared statements work exactly as before
- All existing tests pass unchanged

## Implementation Plan 📋

### 1. Modify the `do_put` method in MinimalFlightSQLServer

Currently, your `do_put` method in `/src/mpzsql/flightsql/minimal.py` only handles command descriptors:

```python
def do_put(self, context, descriptor, reader, writer):
    # Current: Only handles descriptor.command (FlightSQL commands)
    command_bytes = descriptor.command
    # ... FlightSQL processing
```

**Add support for path descriptors:**

```python
def do_put(self, context, descriptor, reader, writer):
    if descriptor.descriptor_type == pf.DescriptorType.COMMAND:
        # Existing FlightSQL command handling
        self._handle_flightsql_do_put(context, descriptor, reader, writer)
    elif descriptor.descriptor_type == pf.DescriptorType.PATH:
        # New: Handle file upload
        self._handle_file_upload_do_put(context, descriptor, reader, writer)
    else:
        raise NotImplementedError(f"Unsupported descriptor type: {descriptor.descriptor_type}")
```

### 2. Implement File Upload Handler (with Streaming Support)

Create a new method to handle file uploads with both regular and streaming approaches:

```python
def _handle_file_upload_do_put(self, context, descriptor, reader, writer):
    """Handle file upload via do_put with path descriptor - creates DuckDB tables directly (no files!)"""

    # EXTENSIVE LOGGING SETUP
    import logging
    from mpzsql.logfire_config import get_duckdb_logger

    duckdb_logger = get_duckdb_logger()
    actions_logger = logging.getLogger("actions")
    routing_logger = logging.getLogger("routing")

    # 1. TABLE NAME: Use the path directly as the table name (DuckDB handles fully qualified names natively)
    #    Examples:
    #    - FlightDescriptor.for_path("my_table") → table name: "my_table" (default schema)
    #    - FlightDescriptor.for_path("users")    → table name: "users" (default schema)
    #    - FlightDescriptor.for_path("public.customers") → table name: "public.customers" (schema.table)
    #    - FlightDescriptor.for_path("analytics.public.customers") → table name: "analytics.public.customers" (database.schema.table)
    #    - FlightDescriptor.for_path("warehouse.staging.orders") → table name: "warehouse.staging.orders" (database.schema.table)
    table_name = descriptor.path[0] if descriptor.path else "unknown_table"
    table_name = table_name.strip('/')  # Remove any leading/trailing slashes

    # DuckDB will handle database/schema creation automatically when we create the table!
    # No need for manual parsing or schema creation - DuckDB is smart enough to handle it

    # Log the raw Flight do_put request
    duckdb_logger.info("Raw Flight do_put request received",
                      descriptor_type="PATH",
                      table_name=table_name,
                      path=descriptor.path)

    actions_logger.info(f"RAW_FLIGHT_DO_PUT: table={table_name}, path={descriptor.path}")
    routing_logger.info(f"ROUTE: do_put(PATH) -> file_upload_handler(table={table_name})")

    # 2. CHOOSE PROCESSING MODE: Batch vs Streaming
    if self._should_use_streaming(reader, table_name):
        routing_logger.info(f"ROUTE_MODE: streaming_upload(table={table_name})")
        self._handle_streaming_upload(table_name, reader, writer)
    else:
        routing_logger.info(f"ROUTE_MODE: batch_upload(table={table_name})")
        self._handle_batch_upload(table_name, reader, writer)

def _should_use_streaming(self, reader, table_name):
    """Determine if we should use streaming based on table name or configuration"""
    # You can implement logic here to decide when to stream
    # Examples:
    # - Large table indicators: table names ending with "_large", "_stream", "_big"
    # - Configuration: self.config.get('force_streaming', False)
    # - Memory constraints: check available memory

    return (table_name.endswith(('_large', '_stream', '_big')) or
            self.config.get('force_streaming', False))

def _handle_batch_upload(self, path, reader, writer):
    """Handle upload by reading all data at once - creates DuckDB table directly"""

    # TRANSFORMATION: FlightStreamReader → PyArrow Table
    arrow_table = reader.read_all()  # ← ONE LINE TRANSFORMATION!

    # TABLE NAME: Use the path directly as table name (client specifies it)
    table_name = path.strip('/')  # Remove leading/trailing slashes

    # EXTENSIVE LOGGING to all log files
    from mpzsql.logfire_config import get_duckdb_logger
    duckdb_logger = get_duckdb_logger()

    # Log to logfire
    duckdb_logger.info("Raw Flight do_put batch upload started",
                      table_name=table_name,
                      rows=len(arrow_table),
                      columns=arrow_table.num_columns,
                      schema=str(arrow_table.schema))

    # Log to actions.log
    actions_logger = logging.getLogger("actions")
    actions_logger.info(f"RAW_FLIGHT_BATCH_UPLOAD: table={table_name}, rows={len(arrow_table)}, cols={arrow_table.num_columns}")

    # Log to server_routing.log
    routing_logger = logging.getLogger("routing")
    routing_logger.info(f"ROUTE: raw_flight_do_put -> batch_upload(table={table_name})")

    # DIRECT DUCKDB TABLE CREATION (no file writing!)
    # This is exactly what you want: duckdb.sql("CREATE TABLE my_table AS SELECT * FROM my_arrow")
    self.backend.create_table_from_arrow(table_name, arrow_table)

    duckdb_logger.info("Raw Flight batch upload completed successfully",
                      table_name=table_name,
                      final_rows=len(arrow_table))

    # Acknowledge the upload
    response_msg = f"Created table '{table_name}' with {len(arrow_table)} rows (batch mode)"
    writer.write(pa.py_buffer(response_msg.encode()))

def _handle_streaming_upload(self, path, reader, writer):
    """Handle upload by streaming data chunk by chunk - creates DuckDB table directly"""

    # TABLE NAME: Use the path directly as table name (client specifies it)
    table_name = path.strip('/')  # Remove leading/trailing slashes
    total_rows = 0
    first_chunk = True

    # EXTENSIVE LOGGING to all log files
    from mpzsql.logfire_config import get_duckdb_logger
    duckdb_logger = get_duckdb_logger()

    # Log to logfire
    duckdb_logger.info("Raw Flight do_put streaming upload started",
                      table_name=table_name)

    # Log to actions.log
    actions_logger = logging.getLogger("actions")
    actions_logger.info(f"RAW_FLIGHT_STREAMING_UPLOAD: table={table_name} - starting")

    # Log to server_routing.log
    routing_logger = logging.getLogger("routing")
    routing_logger.info(f"ROUTE: raw_flight_do_put -> streaming_upload(table={table_name})")

    # STREAMING APPROACH: Process each chunk as it arrives
    for chunk_num, chunk in enumerate(reader, 1):  # ← STREAMING: reader is iterable!
        batch = chunk.data  # chunk.data is pa.RecordBatch

        if first_chunk:
            # Create table with schema from first chunk (no file, just DuckDB table!)
            self.backend.create_table_from_schema(table_name, batch.schema)
            first_chunk = False

            duckdb_logger.info("Created table schema for streaming upload",
                              table_name=table_name,
                              schema=str(batch.schema))

        # Convert RecordBatch to Table and append directly to DuckDB
        chunk_table = pa.Table.from_batches([batch])
        self.backend.append_table_from_arrow(table_name, chunk_table)

        total_rows += batch.num_rows

        # Log each chunk
        duckdb_logger.debug("Processed streaming chunk",
                           table_name=table_name,
                           chunk_number=chunk_num,
                           chunk_rows=batch.num_rows,
                           total_rows=total_rows)

        actions_logger.info(f"RAW_FLIGHT_CHUNK: table={table_name}, chunk={chunk_num}, rows={batch.num_rows}, total={total_rows}")

    duckdb_logger.info("Raw Flight streaming upload completed successfully",
                      table_name=table_name,
                      total_chunks=chunk_num,
                      final_rows=total_rows)

    # Acknowledge the upload
    response_msg = f"Created table '{table_name}' with {total_rows} rows (streaming mode, {chunk_num} chunks)"
    writer.write(pa.py_buffer(response_msg.encode()))
```

**Key Streaming Insight**: The `reader` is iterable! You can use `for chunk in reader:` to process data as it arrives, which is perfect for large datasets that don't fit in memory.

### 3. Update get_flight_info for Path Descriptors

Currently, `get_flight_info` only handles FlightSQL commands. Add path support:

```python
def get_flight_info(self, context, descriptor):
    if descriptor.descriptor_type == pf.DescriptorType.COMMAND:
        # Existing FlightSQL command handling
        return self._get_flightsql_flight_info(context, descriptor)
    elif descriptor.descriptor_type == pf.DescriptorType.PATH:
        # New: Handle file info requests
        return self._get_file_flight_info(context, descriptor)
    else:
        raise NotImplementedError(f"Unsupported descriptor type: {descriptor.descriptor_type}")
```

### 4. Implement File Retrieval (with Streaming Support)

Add support in `do_get` for retrieving uploaded files with streaming:

```python
def do_get(self, context, ticket):
    # Parse ticket to determine if it's FlightSQL or file retrieval
    if self._is_flightsql_ticket(ticket):
        # Existing FlightSQL handling (KEEP UNCHANGED)
        return self._handle_flightsql_do_get(context, ticket)
    else:
        # New: Handle file retrieval with streaming support
        return self._handle_file_do_get(context, ticket)

def _handle_file_do_get(self, context, ticket):
    """Handle file retrieval with optional streaming"""

    # Decode the file path from ticket
    file_path = ticket.ticket.decode('utf-8')
    table_name = f"uploaded_{file_path.replace('.', '_').replace('/', '_')}"

    # Check if table exists
    if not self.backend.table_exists(table_name):
        raise ValueError(f"File not found: {file_path}")

    # Choose streaming approach based on table size
    if self._should_stream_download(table_name):
        return self._stream_table_download(table_name)
    else:
        return self._batch_table_download(table_name)

def _batch_table_download(self, table_name):
    """Download entire table at once (current approach)"""
    arrow_table = self.backend.get_table_as_arrow(table_name)
    return pf.RecordBatchStream(arrow_table)

def _stream_table_download(self, table_name):
    """Stream table data in chunks (new streaming approach)"""

    # Get table schema first
    schema = self.backend.get_table_schema(table_name)

    # Create a generator that yields record batches
    def batch_generator():
        batch_size = 10000  # Configurable chunk size
        offset = 0

        while True:
            # Get next batch from DuckDB
            query = f"SELECT * FROM {table_name} LIMIT {batch_size} OFFSET {offset}"
            batch_table = self.backend.execute_query(query)

            if len(batch_table) == 0:
                break

            # Convert to RecordBatch and yield
            for batch in batch_table.to_batches():
                yield batch

            offset += batch_size

            # Break if we got less than batch_size (end of data)
            if len(batch_table) < batch_size:
                break

    # Use GeneratorStream for efficient streaming
    return pf.GeneratorStream(schema, batch_generator())

def _should_stream_download(self, table_name):
    """Determine if we should stream the download"""
    # Get table row count
    row_count = self.backend.get_table_row_count(table_name)
    return row_count > 100000  # Stream if more than 100k rows
```

**Streaming Benefits**:
- `GeneratorStream` allows handling large datasets without loading everything into memory
- Data is streamed efficiently from DuckDB to client
- Maintains good performance for both small and large datasets

### 5. Backend Support (with Streaming Methods)

Add methods to your DuckDB backend to support both regular and streaming file operations:

```python
# In /src/mpzsql/backends/duckdb_backend.py

def create_table_from_arrow(self, table_name: str, arrow_table: pa.Table):
    """Create a DuckDB table from an Arrow table - DuckDB handles database/schema creation automatically!"""

    # EXTENSIVE LOGGING
    from mpzsql.logfire_config import get_duckdb_logger
    import logging

    duckdb_logger = get_duckdb_logger()
    duckdb_log = logging.getLogger("duckdb_queries")  # File logger
    actions_logger = logging.getLogger("actions")

    # Log the operation
    duckdb_logger.info("Creating DuckDB table from Arrow data",
                      table_name=table_name,
                      rows=len(arrow_table),
                      columns=arrow_table.num_columns,
                      schema=str(arrow_table.schema))

    duckdb_log.info(f"CREATE_TABLE_FROM_ARROW: {table_name} ({len(arrow_table)} rows, {arrow_table.num_columns} cols)")
    actions_logger.info(f"DUCKDB_CREATE: table={table_name}, source=arrow_table")

    try:
        # THIS IS THE KEY: Direct DuckDB table creation from Arrow table
        # DuckDB automatically creates databases and schemas as needed for fully qualified names!
        # Examples:
        # - "users" → creates table in default schema
        # - "public.customers" → creates "public" schema if needed, then creates table
        # - "analytics.sales.revenue" → creates "analytics" database and "sales" schema if needed, then creates table
        self.connection.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM arrow_table")

        # Verify creation
        row_count = self.connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]

        duckdb_logger.info("Successfully created DuckDB table",
                          table_name=table_name,
                          verified_rows=row_count)

        duckdb_log.info(f"CREATE_TABLE_SUCCESS: {table_name} - verified {row_count} rows")
        actions_logger.info(f"DUCKDB_CREATE_SUCCESS: table={table_name}, rows={row_count}")

    except Exception as e:
        duckdb_logger.error("Failed to create DuckDB table from Arrow data",
                           table_name=table_name,
                           error=str(e))

        duckdb_log.error(f"CREATE_TABLE_ERROR: {table_name} - {str(e)}")
        actions_logger.error(f"DUCKDB_CREATE_ERROR: table={table_name}, error={str(e)}")
        raise

def get_table_as_arrow(self, table_name: str) -> pa.Table:
    """Retrieve a DuckDB table as Arrow table (existing method)"""
    return self.connection.execute(f"SELECT * FROM {table_name}").fetch_arrow_table()

# NEW STREAMING METHODS:

def create_table_from_schema(self, table_name: str, schema: pa.Schema):
    """Create an empty DuckDB table with the given Arrow schema - DuckDB handles database/schema creation automatically"""

    # EXTENSIVE LOGGING
    from mpzsql.logfire_config import get_duckdb_logger
    import logging

    duckdb_logger = get_duckdb_logger()
    duckdb_log = logging.getLogger("duckdb_queries")
    actions_logger = logging.getLogger("actions")

    duckdb_logger.info("Creating empty DuckDB table from Arrow schema",
                      table_name=table_name,
                      schema=str(schema))

    duckdb_log.info(f"CREATE_TABLE_FROM_SCHEMA: {table_name} - {len(schema)} columns")
    actions_logger.info(f"DUCKDB_CREATE_SCHEMA: table={table_name}, cols={len(schema)}")

    try:
        # Convert Arrow schema to DuckDB CREATE TABLE statement
        columns = []
        for field in schema:
            duck_type = self._arrow_to_duckdb_type(field.type)
            columns.append(f"{field.name} {duck_type}")

        columns_sql = ", ".join(columns)
        # DuckDB will automatically create database/schema for fully qualified table names!
        create_sql = f"CREATE OR REPLACE TABLE {table_name} ({columns_sql})"

        duckdb_log.info(f"CREATE_SQL: {create_sql}")

        self.connection.execute(create_sql)

        duckdb_logger.info("Successfully created empty DuckDB table",
                          table_name=table_name,
                          columns=len(schema))

        duckdb_log.info(f"CREATE_SCHEMA_SUCCESS: {table_name}")
        actions_logger.info(f"DUCKDB_CREATE_SCHEMA_SUCCESS: table={table_name}")

    except Exception as e:
        duckdb_logger.error("Failed to create table from schema",
                           table_name=table_name,
                           error=str(e))

        duckdb_log.error(f"CREATE_SCHEMA_ERROR: {table_name} - {str(e)}")
        actions_logger.error(f"DUCKDB_CREATE_SCHEMA_ERROR: table={table_name}, error={str(e)}")
        raise

def append_table_from_arrow(self, table_name: str, arrow_table: pa.Table):
    """Append data from Arrow table to existing DuckDB table - for streaming uploads"""

    # EXTENSIVE LOGGING
    from mpzsql.logfire_config import get_duckdb_logger
    import logging

    duckdb_logger = get_duckdb_logger()
    duckdb_log = logging.getLogger("duckdb_queries")
    actions_logger = logging.getLogger("actions")

    duckdb_logger.debug("Appending Arrow data to DuckDB table",
                       table_name=table_name,
                       rows=len(arrow_table))

    duckdb_log.info(f"APPEND_TABLE: {table_name} + {len(arrow_table)} rows")
    actions_logger.info(f"DUCKDB_APPEND: table={table_name}, rows={len(arrow_table)}")

    try:
        # Register the Arrow table temporarily and insert
        self.connection.register("temp_append_table", arrow_table)
        insert_sql = f"INSERT INTO {table_name} SELECT * FROM temp_append_table"

        duckdb_log.info(f"APPEND_SQL: {insert_sql}")

        self.connection.execute(insert_sql)
        self.connection.unregister("temp_append_table")

        duckdb_logger.debug("Successfully appended data to DuckDB table",
                           table_name=table_name,
                           appended_rows=len(arrow_table))

        actions_logger.info(f"DUCKDB_APPEND_SUCCESS: table={table_name}, rows={len(arrow_table)}")

    except Exception as e:
        duckdb_logger.error("Failed to append data to DuckDB table",
                           table_name=table_name,
                           error=str(e))

        duckdb_log.error(f"APPEND_ERROR: {table_name} - {str(e)}")
        actions_logger.error(f"DUCKDB_APPEND_ERROR: table={table_name}, error={str(e)}")

        # Clean up temporary table if it exists
        try:
            self.connection.unregister("temp_append_table")
        except:
            pass

        raise

def table_exists(self, table_name: str) -> bool:
    """Check if a table exists in DuckDB"""
    result = self.connection.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
        [table_name]
    ).fetchone()
    return result[0] > 0

def get_table_schema(self, table_name: str) -> pa.Schema:
    """Get the Arrow schema of a DuckDB table"""
    # Get a single row to extract schema
    result = self.connection.execute(f"SELECT * FROM {table_name} LIMIT 1").fetch_arrow_table()
    return result.schema

def get_table_row_count(self, table_name: str) -> int:
    """Get the number of rows in a table"""
    result = self.connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
    return result[0]

def _arrow_to_duckdb_type(self, arrow_type):
    """Convert Arrow type to DuckDB type string"""
    type_mapping = {
        pa.string(): "VARCHAR",
        pa.int32(): "INTEGER",
        pa.int64(): "BIGINT",
        pa.float32(): "REAL",
        pa.float64(): "DOUBLE",
        pa.bool_(): "BOOLEAN",
        pa.date32(): "DATE",
        pa.timestamp('us'): "TIMESTAMP",
    }

    return type_mapping.get(arrow_type, "VARCHAR")  # Default to VARCHAR
```

**Streaming Backend Features**:
- `create_table_from_schema()` - Create empty tables for streaming inserts
- `append_table_from_arrow()` - Append chunks during streaming upload
- Helper methods for table existence, schema, and row counts

## Testing Your Implementation 🧪

Once implemented, you can test both batch and streaming approaches:

### Test 1: Basic Table Upload (Small Dataset)
```python
import pyarrow as pa
import pyarrow.flight as pf

# Connect and authenticate
client = pf.FlightClient("grpc+tls://localhost:8080")
token_pair = client.authenticate_basic_token(b'user', b'password')
options = pf.FlightCallOptions(headers=[token_pair])

# Upload small dataset to create a table called "characters"
data_table = pa.table({
    "Character": ["Mario", "Luigi", "Peach"],
    "Game": ["Super Mario Bros", "Luigi's Mansion", "Super Princess Peach"],
    "Score": [10000, 8500, 9200]
})

# TABLE NAME: "characters" (no .parquet extension - it's not a file!)
upload_descriptor = pf.FlightDescriptor.for_path("characters")
writer, _ = client.do_put(upload_descriptor, data_table.schema, options=options)
writer.write_table(data_table)  # All data sent at once
writer.close()

# Now you have a DuckDB table called "characters" that you can query with SQL!
print("Created table 'characters' in DuckDB - query it with SQL!")

# Retrieve data
flight_info = client.get_flight_info(upload_descriptor, options=options)
reader = client.do_get(flight_info.endpoints[0].ticket, options=options)
result = reader.read_all()
print(result)
```

### Test 4: Fully Qualified Table Names (Database.Schema.Table)
```python
# Test creating tables with fully qualified names
import pyarrow as pa
import pyarrow.flight as pf

# Connect and authenticate
client = pf.FlightClient("grpc+tls://localhost:8080")
token_pair = client.authenticate_basic_token(b'user', b'password')
options = pf.FlightCallOptions(headers=[token_pair])

# Test 1: Create table in specific database and schema
sales_data = pa.table({
    "product_id": [1, 2, 3],
    "quantity": [100, 200, 150],
    "revenue": [1000.0, 2500.0, 750.0]
})

# This will create database "analytics", schema "sales", and table "monthly_revenue" automatically!
upload_descriptor = pf.FlightDescriptor.for_path("analytics.sales.monthly_revenue")
writer, _ = client.do_put(upload_descriptor, sales_data.schema, options=options)
writer.write_table(sales_data)
writer.close()

print("Created table: analytics.sales.monthly_revenue (DuckDB created database/schema automatically)")

# Test 2: Create table with just schema qualification
user_data = pa.table({
    "user_id": [1001, 1002, 1003],
    "username": ["alice", "bob", "charlie"],
    "email": ["alice@example.com", "bob@example.com", "charlie@example.com"]
})

# This will create schema "public" if needed, then create table "users"
upload_descriptor = pf.FlightDescriptor.for_path("public.users")
writer, _ = client.do_put(upload_descriptor, user_data.schema, options=options)
writer.write_table(user_data)
writer.close()

print("Created table: public.users (DuckDB created schema automatically)")

# Test 3: Create table with simple name (default database/schema)
products_data = pa.table({
    "product_name": ["Widget A", "Widget B", "Widget C"],
    "price": [19.99, 29.99, 39.99]
})

# This will create table "products" in the default schema
upload_descriptor = pf.FlightDescriptor.for_path("products")
writer, _ = client.do_put(upload_descriptor, products_data.schema, options=options)
writer.write_table(products_data)
writer.close()

print("Created table: products (in default schema)")

# Now you can query these tables with their full names:
# SELECT * FROM analytics.sales.monthly_revenue  -- DuckDB created database.schema automatically
# SELECT * FROM public.users                     -- DuckDB created schema automatically
# SELECT * FROM products                          -- Default schema
```

### Test 5: Verify FlightSQL Still Works
```

### Test 2: Streaming Upload (Large Dataset)
```python
# Upload large dataset to create a table called "large_dataset" (streaming mode)
NUM_BATCHES = 1000
ROWS_PER_BATCH = 5000

# TABLE NAME: "large_dataset_stream" (triggers streaming mode due to "_stream" suffix)
upload_descriptor = pf.FlightDescriptor.for_path("large_dataset_stream")
batch = pa.record_batch([
    pa.array(range(ROWS_PER_BATCH)),
    pa.array([f"name_{i}" for i in range(ROWS_PER_BATCH)])
], names=["id", "name"])

writer, _ = client.do_put(upload_descriptor, batch.schema, options=options)
with writer:
    for i in range(NUM_BATCHES):
        writer.write_batch(batch)  # Streaming: one batch at a time
        print(f"Sent batch {i+1}/{NUM_BATCHES}")

print(f"Created table 'large_dataset_stream' with {NUM_BATCHES * ROWS_PER_BATCH} rows via streaming")

# Now you can query this table with SQL:
# SELECT COUNT(*) FROM large_dataset_stream
# SELECT * FROM large_dataset_stream WHERE id < 100
```

### Test 3: Streaming Download (Large Dataset)
```python
# Download large dataset with streaming from the "large_dataset_stream" table
flight_info = client.get_flight_info(upload_descriptor, options=options)
reader = client.do_get(flight_info.endpoints[0].ticket, options=options)

total_rows = 0
for chunk in reader:  # Streaming: process each chunk as it arrives
    total_rows += chunk.data.num_rows
    print(f"Received chunk with {chunk.data.num_rows} rows")

print(f"Downloaded {total_rows} rows via streaming from table 'large_dataset_stream'")
```

### Test 4: Verify FlightSQL Still Works
```python
# Test that existing FlightSQL functionality is unchanged
from adbc_driver_flightsql import dbapi as mpzsql, DatabaseOptions

db_kwargs = {
    "username": "user",
    "password": "password",
    DatabaseOptions.TLS_SKIP_VERIFY.value: "true"
}

with mpzsql.connect(uri="grpc+tls://localhost:8080", db_kwargs=db_kwargs) as conn:
    with conn.cursor() as cur:
        # This should still work exactly as before
        cur.execute("CREATE TABLE test_flightsql (id INTEGER, name VARCHAR)")
        cur.execute("INSERT INTO test_flightsql VALUES (1, 'FlightSQL Works!')")
        cur.execute("SELECT * FROM test_flightsql")
        result = cur.fetch_arrow_table()
        print("FlightSQL test:", result)
```

## Files to Modify 📁

1. `/src/mpzsql/flightsql/minimal.py` - Main implementation
2. `/src/mpzsql/backends/duckdb_backend.py` - Backend support
3. Add tests in `/tests/` to verify functionality

## Benefits 🎉

After implementation, your server will support both:
- **FlightSQL protocol** (SQL queries, prepared statements) via ADBC
- **Raw Flight protocol** (file uploads/downloads) via PyArrow Flight

This gives you the best of both worlds - SQL capabilities AND file transfer capabilities!

# MPZSQL - Apache Arrow FlightSQL Server

[![Tests](https://github.com/MiguelElGallo/mpzsql/actions/workflows/test.yml/badge.svg)](https://github.com/MiguelElGallo/mpzsql/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/MiguelElGallo/mpzsql/branch/main/graph/badge.svg?token=FFX8G2S7X9)](https://codecov.io/gh/MiguelElGallo/mpzsql)

MPZSQL is a Python implementation of an Apache Arrow FlightSQL server that supports DuckLake.

See these resources for more understanding:

- [My initial idea](https://www.linkedin.com/pulse/thinking-ducklake-architecture-miguel-peredo-z%25C3%25BCrcher-lt5ff/?trackingId=2dHjs0mPQGi8Y3YKEIshhw%3D%3D)
- A [demo of what you can achieve](https://www.youtube.com/watch?v=-Dx_qz7s-Ds) if you make it run.

***Update 12-Sep-2025*** The Azure deploment repo can be found here: https://github.com/MiguelElGallo/mpzsql_azinfra


## Warning!

This software is in experimental state. I have not tested the security features yet. The software it uses like [DuckLake](https://github.com/duckdb/ducklake) is also in experimental state. (As of July 2025)

***Do NOT use in production!***

## Minimum Configuration for Starting in DuckLake Mode

### Azure Login

Make sure you are authenticated with Azure CLI:

```bash
az login
```

The server relies on Azure Identity's [DefaultAzureCredential](https://learn.microsoft.com/en-us/python/api/overview/azure/identity-readme?view=azure-python#defaultazurecredential), so it will automatically pick up the credentials produced by `az login` when it runs.
The Azure account you use (or you log in with) **must have data-plane permissions on the storage account** that hosts your DuckLake files:

1. Storage Blob Data **Contributor** (if you need write access)

You can grant those roles at the storage-account or container scope.
See Microsoft's documentation for details:

* Assign data-plane roles –
  https://learn.microsoft.com/azure/storage/common/storage-auth-aad-rbac-portal
* Role definitions –
  https://learn.microsoft.com/azure/role-based-access-control/built-in-roles#storage-blob-data-roles

Without the correct data-plane privileges, the server will fail when it tries to list, read, or write blobs.

### Running the Server

Set all the environment variables like: POSTGRESQL_SERVER, POSTGRESQL_USER, etc. and then run the following command:

```shell
uv run python -m mpzsql.cli \
  --database "localconf.duckdb" \
  --print-queries \
  --secret-key "test-secret-key" \
  --postgresql-server "$POSTGRESQL_SERVER" \
  --postgresql-port "$POSTGRESQL_PORT" \
  --postgresql-user "$POSTGRESQL_USER" \
  --postgresql-password "$POSTGRESQL_PASSWORD" \
  --postgresql-catalogdb "$POSTGRESQL_CATALOGDB" \
  --azure-storage-account "$AZURE_STORAGE_ACCOUNT" \
  --azure-storage-container "$AZURE_STORAGE_CONTAINER"
```

The PostgreSQL database must exist, as [mentioned](https://ducklake.select/docs/stable/duckdb/usage/choosing_a_catalog_database#postgresql).

The server is verbose and creates 5 log files, check the root folder.

### Testing with a Client

The server will run on localhost port 8080. You can use any JDBC client to connect, with a connection string like:
`jdbc:arrow-flight-sql://localhost:8080?useEncryption=false&disableCertificateVerification=true`

I have tested with DBeaver, and I found this [guide](https://github.com/voltrondata/setup-arrow-jdbc-driver-in-dbeaver).

### Notes about Logfire

The server can send logs to [Logfire](https://logfire.pydantic.dev/docs/why/). Just set the environment variable `LOGFIRE_WRITE_TOKEN`.

## Features

- Apache Arrow FlightSQL interface
- JDBC interface

## FlightSQL Implementation Status

### ✅ Implemented FlightSQL Actions

- **CreatePreparedStatement** - Create prepared statements for efficient query execution
- **ClosePreparedStatement** - Clean up prepared statements
- **BeginTransaction** - Start database transactions
- **EndTransaction** - Commit or rollback transactions
- **CloseSession** - Clean up session resources and state

### ✅ Implemented FlightSQL Commands

- **CommandStatementQuery** - Execute SQL queries
- **CommandGetCatalogs** - List database catalogs
- **CommandGetDbSchemas** - List database schemas
- **CommandGetTables** - List tables with metadata
- **CommandGetTableTypes** - List available table types
- **CommandGetColumns** - List column metadata
- **CommandGetSqlInfo** - SQL capability information
- **CommandPreparedStatementQuery** - Execute prepared statements
- **CommandStatementUpdate** - Execute INSERT/UPDATE/DELETE statements
- **CommandPreparedStatementUpdate** - Execute prepared statement updates

### ❌ Not Implemented Yet

The following FlightSQL commands are not yet implemented but could be added for enhanced JDBC compatibility:

#### Priority 1: Essential Metadata Commands
- **GetXdbcTypeInfo** - JDBC/ODBC type information
- **GetPrimaryKeys** - Primary key metadata

#### Priority 2: Advanced Metadata Commands
- **GetImportedKeys** - Foreign key information (imported)
- **GetExportedKeys** - Foreign key information (exported)
- **GetCrossReference** - Cross-reference between tables

**Current Compatibility**: ~85% FlightSQL compatible
**With Priority 1**: ~95% FlightSQL compatible
**With full implementation**: 100% FlightSQL compatible

## FlightSQL → DuckDB backend mapping

This document maps FlightSQL operations to their DuckDB backend implementations and the SQL each method executes.

- Flight SQL: the FlightSQL command/action.
- Backend method: method in src/mpzsql/backends/duckdb_backend.py.
- SQL / Behavior: the actual SQL executed (or behavior when no direct SQL).

| Flight SQL                          | Backend method              | SQL / Behavior |
|-------------------------------------|-----------------------------|----------------|
| CommandGetCatalogs                  | get_catalogs                | SELECT DISTINCT catalog_name FROM information_schema.schemata ORDER BY catalog_name; Fallback: SHOW DATABASES |
| CommandGetDbSchemas                 | get_db_schemas              | Base: SELECT catalog_name, schema_name AS db_schema_name FROM information_schema.schemata WHERE 1 = 1 [AND catalog_name = ? or AND catalog_name = CURRENT_DATABASE()] [AND schema_name LIKE ?] ORDER BY catalog_name, db_schema_name |
| CommandGetTables                    | get_tables                  | Base: SELECT table_catalog AS catalog_name, table_schema AS db_schema_name, table_name, table_type FROM information_schema.tables WHERE 1=1 [AND table_catalog = ? or AND table_catalog = CURRENT_DATABASE()] [AND table_schema LIKE ?] [AND table_name LIKE ?] [AND table_type IN (?, ...)] ORDER BY table_name |
| CommandGetTableTypes                | get_table_types             | No direct SQL; returns a static Arrow table: ["BASE TABLE","VIEW","LOCAL TEMPORARY","SYSTEM TABLE"] |
| CommandGetColumns                   | get_columns                 | Base: SELECT table_catalog AS catalog_name, table_schema AS db_schema_name, table_name, column_name, data_type, ordinal_position AS "DECIMAL_DIGITS", 'YES' AS "IS_NULLABLE", 0 AS "NUM_PREC_RADIX" FROM information_schema.columns WHERE 1=1 [AND table_catalog = '...'] [AND table_schema LIKE '...'] [AND table_name LIKE '...'] [AND column_name LIKE '...'] ORDER BY table_catalog, table_schema, table_name, ordinal_position; Then reshapes to FlightSQL GetColumns schema (adds/mapps data_type codes, etc.) |
| CommandGetSqlInfo                   | get_sql_info                | No direct SQL; returns a placeholder Arrow table from provided info codes |
| CommandStatementQuery               | execute_query               | Executes client-provided SELECT/SQL and returns Arrow table (varies per client query) |
| CommandStatementUpdate              | execute_update              | Executes client-provided DML (INSERT/UPDATE/DELETE); returns affected rows (DuckDB returns BIGINT count) |
| CommandPreparedStatementQuery       | get_statement_schema (prepare phase) / execute_query (execution) | Prepare phase (schema inference): typically PREPARE stmt AS {query}; DESCRIBE stmt; DEALLOCATE stmt. For parameterized queries: attempts a LIMIT 0 variant replacing ? with 1; fallback to PREPARE with NULLs. Execution: same as CommandStatementQuery with parameters |
| CommandPreparedStatementUpdate      | execute_update              | Executes client-provided DML with bound parameters; returns affected rows |
| Action: CreatePreparedStatement     | get_statement_schema        | Same schema inference logic as above: PREPARE/ DESCRIBE/ DEALLOCATE; for parameterized queries, tries LIMIT 0 with dummy values, fallback PREPARE with NULLs |
| Action: ClosePreparedStatement      | —                           | No backend SQL; server clears cached handle |
| Action: BeginTransaction / EndTransaction | —                      | No backend SQL in current DuckDB backend; transaction state tracked in server layer |
| Action: CloseSession                | —                           | No backend SQL; server/session cleanup only |

Notes:
- Patterns: Incoming FlightSQL patterns use * and are converted to SQL LIKE % in backend methods.
- CURRENT_DATABASE(): When catalog is not provided for GetTables/GetDbSchemas, backend uses CURRENT_DATABASE() to match FlightSQL metadata behavior.
- Errors/Empty results: On errors, backend returns empty Arrow tables with correct schemas where appropriate.

## Arrow Flight → DuckDB backend mapping

This document maps core Arrow Flight methods implemented in [`MinimalFlightSQLServer`](src/mpzsql/flightsql/minimal.py) to DuckDB backend behavior in [`DuckDBBackend`](src/mpzsql/backends/duckdb_backend.py), including the SQL they execute (when applicable).

Reference: https://arrow.apache.org/docs/python/api/flight.html

| Arrow Flight API | Server method | Backend method(s) | DuckDB SQL / Behavior |
| --- | --- | --- | --- |
| Handshake | [`MinimalFlightSQLServer.handshake`](src/mpzsql/flightsql/minimal.py) | — | Authentication handshake; no SQL. Returns capability/auth messages. |
| ListFlights | [`MinimalFlightSQLServer.list_flights`](src/mpzsql/flightsql/minimal.py) | — | Advertises a few metadata endpoints as PATH descriptors; no SQL. |
| GetSchema (DescriptorType.PATH) | [`MinimalFlightSQLServer._get_schema_for_path`](src/mpzsql/flightsql/minimal.py) | — | Static schemas for “catalogs”, “schemas”, “tables”, “table_types”, “sql_info”. Unknown paths return a generic schema; no SQL. |
| GetFlightInfo (DescriptorType.PATH: “<table_name>”) | [`MinimalFlightSQLServer.get_flight_info`](src/mpzsql/flightsql/minimal.py) | [`DuckDBBackend.get_table_schema`](src/mpzsql/backends/duckdb_backend.py), [`DuckDBBackend.get_table_row_count`](src/mpzsql/backends/duckdb_backend.py) | Schema: inferred via a lightweight select (typically `SELECT * FROM {table_name} LIMIT 1`) to get Arrow schema. Row count: `SELECT COUNT(*) FROM {table_name}`. Ticket returned: `PATH:{table_name}`. |
| DoGet (Ticket produced by PATH GetFlightInfo) | [`MinimalFlightSQLServer.do_get`](src/mpzsql/flightsql/minimal.py) | — | MISSING: current implementation does
## Configuration Options

MPZSQL can be configured using command-line switches or environment variables. Environment variables take precedence over CLI defaults but CLI switches take precedence over environment variables (except for MPZSQL_PORT which always takes precedence).

### Backend Options

| Switch | Environment Variable | Description | Type | Default |
|--------|---------------------|-------------|------|---------|
| `--backend` | - | Database backend (duckdb) | string | duckdb |
| `--database` | - | Database filename (defaults to in-memory for DuckDB) | string | None |

### Network Options

| Switch | Environment Variable | Description | Type | Default |
|--------|---------------------|-------------|------|---------|
| `--hostname` | `MPZSQL_HOSTNAME` | Server hostname to listen on | string | localhost |
| `--advertised-hostname` | `MPZSQL_ADVERTISED_HOSTNAME` or `WEBSITE_HOSTNAME` | Hostname to advertise to clients (defaults to hostname) | string | None |
| `--port` | `MPZSQL_PORT` | Server port (MPZSQL_PORT env var takes precedence over CLI) | int (1-65535) | 8080 |

### Authentication Options

| Switch | Environment Variable | Description | Type | Default |
|--------|---------------------|-------------|------|---------|
| `--username` | `MPZSQL_USERNAME` | Authentication username | string | None |
| `--password` | `MPZSQL_PASSWORD` | Authentication password | string | None |
| `--secret-key` | `SECRET_KEY` | JWT secret key (random if not provided) | string | None |

### TLS Options

| Switch | Environment Variable | Description | Type | Default |
|--------|---------------------|-------------|------|---------|
| `--tls-cert` | - | TLS certificate file path | string | None |
| `--tls-key` | - | TLS private key file path | string | None |
| `--mtls-ca` | `MPZSQL_MTLS_CA` | mTLS CA certificate for client verification | string | None |

### SQL Initialization Options

| Switch | Environment Variable | Description | Type | Default |
|--------|---------------------|-------------|------|---------|
| `--init-sql` | `MPZSQL_INIT_SQL` | SQL commands to run on startup | string | None |
| `--init-sql-file` | `MPZSQL_INIT_SQL_FILE` | File containing SQL commands to run on startup | string | None |

### Server Behavior Options

| Switch | Environment Variable | Description | Type | Default |
|--------|---------------------|-------------|------|---------|
| `--print-queries` | - | Print executed queries to console | bool | False |
| `--read-only` | - | Enable read-only mode | bool | False |

### PostgreSQL Connection Options

| Switch | Environment Variable | Description | Type | Default |
|--------|---------------------|-------------|------|---------|
| `--postgresql-server` | `POSTGRESQL_SERVER` | PostgreSQL server hostname | string | None |
| `--postgresql-port` | `POSTGRESQL_PORT` | PostgreSQL server port | int | 5432 |
| `--postgresql-user` | `POSTGRESQL_USER` | PostgreSQL username | string | None |
| `--postgresql-password` | `POSTGRESQL_PASSWORD` | PostgreSQL password (use "AZURE" for Azure AD auth) | string | None |
| `--postgresql-catalogdb` | `POSTGRESQL_CATALOGDB` | PostgreSQL catalog database name | string | None |

### Azure Storage Connection Options

| Switch | Environment Variable | Description | Type | Default |
|--------|---------------------|-------------|------|---------|
| `--azure-storage-account` | `AZURE_STORAGE_ACCOUNT` | Azure Storage account name | string | None |
| `--azure-storage-container` | `AZURE_STORAGE_CONTAINER` | Azure Storage container name | string | None |

### Other Options

| Switch | Environment Variable | Description | Type | Default |
|--------|---------------------|-------------|------|---------|
| `--version` | - | Show version and exit | bool | False |

### Notes

- Both `--tls-cert` and `--tls-key` must be provided together
- The `MPZSQL_PORT` environment variable takes precedence over the `--port` CLI option
- For Azure AD authentication with PostgreSQL, set `--postgresql-password AZURE`
- The `WEBSITE_HOSTNAME` environment variable is automatically set by Azure Web Apps

## Starting the Server

Check the help with:
```shell
uv run python -m mpzsql.cli --help
```

## Development

### Running Tests

Tests can be run locally using:

```bash
uv run pytest tests/ -v
```

For coverage reporting:

```bash
uv run coverage run -m pytest tests/
uv run coverage report
uv run coverage xml
```

### Setting up Codecov (Optional)

If you want to enable code coverage reporting to Codecov in GitHub Actions, you need to:

1. Create a free account at [codecov.io](https://codecov.io)
2. Add your repository to Codecov
3. Get your repository's upload token from Codecov
4. Add the token as a repository secret named `CODECOV_TOKEN` in your GitHub repository settings

Without this token, the Codecov upload step will be skipped in the CI pipeline, but all tests will still run successfully.

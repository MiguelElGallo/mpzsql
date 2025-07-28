# MPZSQL - Apache Arrow FlightSQL Server

[![Tests](https://github.com/MiguelElGallo/mpzsql/actions/workflows/test.yml/badge.svg)](https://github.com/MiguelElGallo/mpzsql/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/MiguelElGallo/mpzsql/branch/main/graph/badge.svg?token=FFX8G2S7X9)](https://codecov.io/gh/MiguelElGallo/mpzsql)

MPZSQL is a Python implementation of an Apache Arrow FlightSQL server that supports DuckLake.

See these resources for more understanding:

- [My initial idea](https://www.linkedin.com/pulse/thinking-ducklake-architecture-miguel-peredo-z%25C3%25BCrcher-lt5ff/?trackingId=2dHjs0mPQGi8Y3YKEIshhw%3D%3D)
- A [demo of what you can achieve](https://www.youtube.com/watch?v=-Dx_qz7s-Ds) if you make it run. 

***Note*** The azure part showed in the video is not part of this repository, that you will need to figure by yourself, at least for now.


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

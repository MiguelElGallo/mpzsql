# MPZSQL - Apache Arrow FlightSQL Server

MPZSQL is a Python implementation of an Apache Arrow FlightSQL server that supports DuckLake

## Features

- Apache Arrow FlightSQL interface
- JDBC interface



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
- SQLite backend requires the `--database` option
- The `MPZSQL_PORT` environment variable takes precedence over the `--port` CLI option
- For Azure AD authentication with PostgreSQL, set `--postgresql-password AZURE`
- The `WEBSITE_HOSTNAME` environment variable is automatically set by Azure Web Apps

## Starting the server 

Check the with:
```shell
uv run python -m mpzsql.cli --help
```

## Minimum configuration for starting in ducklake mode

### Azure login 

Make sure you have already authenticated with Azure CLI:

```bash
az login
```

The server relies on Azure Identity’s `DefaultAzureCredential`, so it will automatically pick up the credentials produced by `az login` when it runs.  
The Azure account you use **must have data-plane permissions on the storage account** that hosts your DuckLake files:


1. Storage Blob Data **Contributor** (if you need write access)

You can grant those roles at the storage-account or container scope.  
See Microsoft’s documentation for details:

* Assign data-plane roles –  
  https://learn.microsoft.com/azure/storage/common/storage-auth-aad-rbac-portal  
* Role definitions –  
  https://learn.microsoft.com/azure/role-based-access-control/built-in-roles#storage-blob-data-roles

Without the correct data-plane privileges the server will fail when it tries to list, read or write blobs.


### Running the server 
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

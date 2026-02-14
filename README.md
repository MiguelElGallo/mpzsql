# Lakehouse

**High-Performance SQL Server for the Cloud — Arrow Flight SQL + DuckDB**

Query DuckDB over the network using any Flight SQL or ADBC client.
Deploy to Azure in one command. Connect with JDBC or Python.

---

## Features

- **Full Flight SQL protocol** — 35 handlers covering queries, prepared statements, metadata, transactions, and catalog introspection
- **DuckDB + DuckLake** — analytical SQL with PostgreSQL catalog and Azure Blob Storage, plus native Arrow export
- **Authentication** — Basic auth with HMAC-hashed passwords, JWT bearer tokens (HS256/RS256)
- **TLS / mTLS** — encrypted transport with optional client certificate verification
- **Health checking** — standalone gRPC health service (Kubernetes-ready) with background DuckDB probes
- **One-command Azure deploy** — `azd up` provisions storage, PostgreSQL, Container Apps, and managed identity

---

## Deploy to Azure

Go from zero to a running Lakehouse server on Azure Container Apps.

### Prerequisites

| Tool | Install |
|------|---------|
| Azure CLI | `brew install azure-cli` or [aka.ms/installazurecli](https://aka.ms/installazurecli) |
| Azure Developer CLI | `brew install azd` or [learn.microsoft.com/azure/developer/azure-developer-cli/install-azd](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) |
| PostgreSQL client | `brew install libpq` or `apt install postgresql-client` |
| Git | `brew install git` |

Log in to Azure:

```bash
az login
azd auth login
```

### Step 1 — Clone and configure

```bash
git clone https://github.com/MiguelElGallo/lakehouse.git
cd lakehouse

azd env new lakehouse-dev
azd env set AZURE_SUBSCRIPTION_ID "<your-subscription-id>"
azd env set AZURE_RESOURCE_GROUP "rg-lakehouse2026"
azd env set AZURE_LOCATION "centralus"
azd env set POSTGRES_ADMIN_PASSWORD "<strong-password>"
azd env set POSTGRES_ENTRA_ADMIN_OBJECT_ID "<your-entra-object-id>"
azd env set POSTGRES_ENTRA_ADMIN_PRINCIPAL_NAME "<your-entra-upn>"
azd env set POSTGRES_ENTRA_ADMIN_PRINCIPAL_TYPE "User"
azd env set DUCKLAKE_DATA_PATH "az://lakehouse/data/"
```

> **Tip:** Find your Entra Object ID with `az ad signed-in-user show --query id -o tsv`
> and your UPN with `az ad signed-in-user show --query userPrincipalName -o tsv`.

### Step 2 — Deploy

```bash
azd up
```

This single command provisions all Azure infrastructure (storage, PostgreSQL, Container Apps, managed identity), builds the Docker image remotely in Azure Container Registry (no local Docker or Podman required), and configures PostgreSQL grants.

### Step 3 — Verify it's running

```bash
az containerapp show \
  -g "$(azd env get-value AZURE_RESOURCE_GROUP)" \
  -n "$(azd env get-value CONTAINER_APP_NAME)" \
  --query properties.configuration.ingress.fqdn -o tsv
```

You should see an FQDN like:

```text
ca-lakehouse-xxxxx.centralus.azurecontainerapps.io
```

Done. Your Lakehouse server is live.

---

## Connect to Your Server

Now connect to the deployed server and run queries. Pick your client:

### Option A — JDBC (Java)

Grab the endpoint and password from Azure, then run the built-in demo:

```bash
ENDPOINT="$(az containerapp show \
  -g "$(azd env get-value AZURE_RESOURCE_GROUP)" \
  -n "$(azd env get-value CONTAINER_APP_NAME)" \
  --query properties.configuration.ingress.fqdn -o tsv):443"

PASSWORD="$(az keyvault secret show \
  --vault-name "$(azd env get-value KEY_VAULT_NAME)" \
  --name lakehouse-password \
  --query value -o tsv)"
```

Run the Azure Demo:

```bash
cd tests/jdbc
MAVEN_OPTS="--add-opens=java.base/java.nio=ALL-UNNAMED" \
mvn -q \
  -Dexec.mainClass=lakehouse.AzureDemo \
  -Dexec.args="$ENDPOINT $PASSWORD lakehouse" \
  test-compile exec:java
```

> **Note:** The `MAVEN_OPTS` flag is required for Apache Arrow on Java 17+.

You should see:

```text
Connecting to ca-lakehouse-xxxxx.centralus.azurecontainerapps.io:443 ...

=== CATALOGS ===
  lakehouse
  system
  temp

=== SCHEMAS ===
  lakehouse.ducklake_meta
  lakehouse.main
  ...

✓  Created table 'lakehouse.main.whatever'
✓  Inserted 5 rows

── SELECT * FROM lakehouse.main.whatever ORDER BY id ──
ID   NAME         DESCRIPTION        VALUE  CREATED_AT
----------------------------------------------------------------------
1    Widget A     First widget        19.99  2026-02-12 10:00:00.0
2    Widget B     Second widget       29.99  2026-02-12 10:05:00.0
...

Done.
```

The demo discovers catalogs and schemas, creates a table in DuckLake, inserts rows, and queries them — all through the Flight SQL protocol over TLS.

> **Tip:** You can also set environment variables instead of passing args:
>
> ```bash
> export LAKEHOUSE_DEMO_ENDPOINT="$ENDPOINT"
> export LAKEHOUSE_DEMO_PASSWORD="$PASSWORD"
> export LAKEHOUSE_DEMO_USER="lakehouse"
> MAVEN_OPTS="--add-opens=java.base/java.nio=ALL-UNNAMED" \
> mvn -q -Dexec.mainClass=lakehouse.AzureDemo test-compile exec:java
> ```

### Option B — ADBC (Python)

Install the ADBC Flight SQL driver:

```bash
pip install adbc-driver-flightsql
```

Connect to your Azure deployment:

```python
import base64
import adbc_driver_flightsql.dbapi as flight_sql
from adbc_driver_flightsql import DatabaseOptions

# Use the ENDPOINT and PASSWORD from above
endpoint = "grpc+tls://ca-lakehouse-xxxxx.centralus.azurecontainerapps.io:443"
token = base64.b64encode(b"lakehouse:<your-password>").decode()

conn = flight_sql.connect(
    endpoint,
    db_kwargs={DatabaseOptions.AUTHORIZATION_HEADER.value: f"Basic {token}"},
)

cursor = conn.cursor()
cursor.execute("SELECT * FROM lakehouse.main.whatever ORDER BY id")
print(cursor.fetchall())
```

You should see the 5 rows inserted by the JDBC demo (or an empty result if you haven't run it yet).

---

## What Just Happened?

```text
┌──────────────────────────┐
│  Your Client             │
│  (JDBC / ADBC / Python)  │
└───────────┬──────────────┘
            │ gRPC + TLS (Flight SQL)
            ▼
┌──────────────────────────┐     ┌────────────────────────┐
│  Lakehouse Server        │     │  Azure Blob Storage    │
│  (Container Apps)        │────▶│  (Parquet data files)  │
│                          │     └────────────────────────┘
│  DuckDB + DuckLake ext   │
│                          │     ┌────────────────────────┐
│                          │────▶│  Azure PostgreSQL      │
└──────────────────────────┘     │  (DuckLake catalog)    │
                                 └────────────────────────┘
```

Lakehouse runs DuckDB in-memory and attaches [DuckLake](https://ducklake.select/), which stores its **catalog** (table definitions, snapshots) in PostgreSQL and its **data** (Parquet files) in Azure Blob Storage. Authentication to both services uses Microsoft Entra ID managed identity — no secrets stored in the container.

---

## Reference

Everything below is reference material: local development, configuration, architecture details, and Azure infrastructure specifics.

---

## Local Development

### Install requirements

- Python 3.12+
- [UV](https://docs.astral.sh/uv/) (package manager)

### Install and run locally

```bash
git clone https://github.com/MiguelElGallo/lakehouse.git
cd lakehouse
uv sync
```

```bash
# In-memory database, no auth
uv run lakehouse serve

# With authentication
uv run lakehouse serve --password mysecret

# Persistent database
uv run lakehouse serve --database /path/to/data.duckdb --password mysecret

# Custom port and startup SQL
uv run lakehouse serve --port 8815 --init-sql "CREATE TABLE t AS SELECT 1 AS id"
```

### Connect locally with ADBC (Python)

```python
import adbc_driver_flightsql.dbapi as flight_sql

# No auth
conn = flight_sql.connect("grpc://localhost:31337")

# With Basic auth
import base64
from adbc_driver_flightsql import DatabaseOptions
token = base64.b64encode(b"lakehouse:mysecret").decode()
conn = flight_sql.connect(
    "grpc://localhost:31337",
    db_kwargs={DatabaseOptions.AUTHORIZATION_HEADER.value: f"Basic {token}"},
)

cursor = conn.cursor()
cursor.execute("SELECT 42 AS answer")
print(cursor.fetchall())  # [(42,)]

# Arrow-native fetch
cursor.execute("SELECT * FROM range(1000000) t(id)")
table = cursor.fetch_arrow_table()
print(table.num_rows)  # 1000000
```

### Tests

```bash
uv sync --group dev

# Full suite (578 tests)
uv run pytest

# Quick run
uv run pytest -q --no-header

# Specific module
uv run pytest tests/test_server.py -v

# Integration tests only
uv run pytest tests/test_e2e.py -v
```

### Lint, format, type-check

```bash
# Lint
uv run ruff check src/ tests/

# Auto-fix
uv run ruff check --fix src/ tests/

# Format
uv run ruff format src/ tests/

# Type check
uv run ty check src/lakehouse/
```

---

## Configuration Reference

Most settings can be set via both CLI flags and `LAKEHOUSE_*` environment variables.
A few settings are environment-only (`.env` also works).

| Setting | CLI Flag | Env Variable | Default | Availability | Description |
|---------|----------|-------------|---------|--------------|-------------|
| Host | `--host` | `LAKEHOUSE_HOST` | `0.0.0.0` | CLI + Env | Bind address |
| Port | `--port` | `LAKEHOUSE_PORT` | `31337` | CLI + Env | Flight SQL (gRPC) port |
| Database | `--database` | `LAKEHOUSE_DATABASE` | `:memory:` | CLI + Env | DuckDB database path |
| Username | `--username` | `LAKEHOUSE_USERNAME` | `lakehouse` | CLI + Env | Auth username |
| Password | `--password` | `LAKEHOUSE_PASSWORD` | *(empty)* | CLI + Env | Auth password (empty disables auth) |
| Secret Key | `--secret-key` | `LAKEHOUSE_SECRET_KEY` | *(auto-generated)* | CLI + Env | HMAC / JWT signing key |
| Health Port | `--health-check-port` | `LAKEHOUSE_HEALTH_CHECK_PORT` | `8081` | CLI + Env | gRPC health service port |
| Health Enabled | `--health-check-enabled` | `LAKEHOUSE_HEALTH_CHECK_ENABLED` | `true` | CLI + Env | Enable health check server |
| Log Level | `--log-level` | `LAKEHOUSE_LOG_LEVEL` | `INFO` | CLI + Env | Python log level |
| Print Queries | `--print-queries` | `LAKEHOUSE_PRINT_QUERIES` | `false` | CLI + Env | Log client SQL queries |
| Init SQL | `--init-sql` | `LAKEHOUSE_INIT_SQL` | *(empty)* | CLI + Env | Startup SQL (semicolon-separated) |
| Azure Storage Account | `--azure-storage-account` | `LAKEHOUSE_AZURE_STORAGE_ACCOUNT` | *(empty)* | CLI + Env | DuckLake Azure Storage account |
| DuckLake Data Path | `--ducklake-data-path` | `LAKEHOUSE_DUCKLAKE_DATA_PATH` | *(empty)* | CLI + Env | DuckLake `DATA_PATH` (must end with `/`) |
| PostgreSQL Host | `--pg-host` | `LAKEHOUSE_PG_HOST` | *(empty)* | CLI + Env | DuckLake PostgreSQL host |
| PostgreSQL Port | `--pg-port` | `LAKEHOUSE_PG_PORT` | `5432` | CLI + Env | DuckLake PostgreSQL port |
| PostgreSQL Database | `--pg-database` | `LAKEHOUSE_PG_DATABASE` | *(empty)* | CLI + Env | DuckLake PostgreSQL DB |
| PostgreSQL User | `--pg-user` | `LAKEHOUSE_PG_USER` | *(empty)* | CLI + Env | DuckLake PostgreSQL user |
| DuckLake Alias | `--ducklake-alias` | `LAKEHOUSE_DUCKLAKE_ALIAS` | `lakehouse` | CLI + Env | Attached DuckLake alias |
| PG Token Refresh Minutes | `--pg-token-refresh-minutes` | `LAKEHOUSE_PG_TOKEN_REFRESH_MINUTES` | `5.0` | CLI + Env | Entra token refresh margin |
| Init SQL File | — | `LAKEHOUSE_INIT_SQL_FILE` | *(empty)* | Env only | Path to startup `.sql` file |
| TLS Cert | — | `LAKEHOUSE_TLS_CERT_FILE` | *(empty)* | Env only | PEM certificate for TLS |
| TLS Key | — | `LAKEHOUSE_TLS_KEY_FILE` | *(empty)* | Env only | PEM private key for TLS |
| mTLS CA | — | `LAKEHOUSE_MTLS_CA_CERT_FILE` | *(empty)* | Env only | CA certificate for client verification |
| Read Only | — | `LAKEHOUSE_READ_ONLY` | `false` | Env only | Open DuckDB in read-only mode |
| JWT Issuer | — | `LAKEHOUSE_JWT_ISSUER` | `lakehouse` | Env only | JWT `iss` claim |
| Health Poll Interval | — | `LAKEHOUSE_HEALTH_POLL_INTERVAL` | `5.0` | Env only | Seconds between health probes |

---

## Docker

```bash
# Build
docker build -t lakehouse .

# Run
docker run -p 31337:31337 -p 8081:8081 lakehouse serve --password mysecret

# With persistent storage
docker run -p 31337:31337 -v ./data:/data lakehouse serve \
  --database /data/warehouse.duckdb --password mysecret
```

---

## Architecture

```text
┌──────────────────────────────────────────────────────────┐
│  Client (ADBC / Flight SQL)                              │
└────────────────────┬─────────────────────────────────────┘
                     │ gRPC (Flight SQL protocol)
                     ▼
┌──────────────────────────────────────────────────────────┐
│  Middleware Stack                                         │
│  ┌─────────────┐ ┌──────────────┐ ┌───────────────────┐ │
│  │ Access Log   │ │ Basic Auth   │ │ Bearer Auth (JWT) │ │
│  └─────────────┘ └──────────────┘ └───────────────────┘ │
└────────────────────┬─────────────────────────────────────┘
                     ▼
┌──────────────────────────────────────────────────────────┐
│  FlightSqlDispatchMixin (dispatch.py)                    │
│  Parses protobuf Any → routes to 35 handler methods      │
└────────────────────┬─────────────────────────────────────┘
                     ▼
┌──────────────────────────────────────────────────────────┐
│  DuckDBFlightSqlServer (server.py)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │ Session Mgr  │  │ Prepared Stmt│  │ Catalog / Meta │ │
│  └──────────────┘  └──────────────┘  └────────────────┘ │
└────────────────────┬─────────────────────────────────────┘
                     ▼
┌──────────────────────────────────────────────────────────┐
│  DuckDB Engine                                           │
│  In-memory or persistent · Extensions · Native Arrow     │
└──────────────────────────────────────────────────────────┘

┌──────────────────┐
│ gRPC Health Svc  │ Port 8081 (Kubernetes probes)
│ + DuckDB Poller  │
└──────────────────┘
```

### Module Overview

| Module | Description |
|--------|-------------|
| `dispatch.py` | Protobuf `Any` → Flight SQL command dispatch mixin (~680 lines) |
| `server.py` | `DuckDBFlightSqlServer` — 35 Flight SQL handler implementations |
| `session.py` | Per-client DuckDB session isolation and lifecycle |
| `auth.py` | Basic & Bearer auth middleware factories |
| `security.py` | HMAC password hashing, JWT encode/decode |
| `health.py` | gRPC health server with background DuckDB health polling |
| `config.py` | `ServerConfig` — Pydantic Settings model for CLI/env configuration |
| `__main__.py` | Typer CLI entry point + `build_server` factory |
| `logging.py` | Access log middleware |

---

## Flight SQL Protocol Support

Lakehouse implements all standard Flight SQL RPCs:

| Category | Supported Operations |
|----------|---------------------|
| **Queries** | `CommandStatementQuery`, `CommandStatementUpdate`, `CommandStatementSubstraitPlan` |
| **Prepared Statements** | `ActionCreatePreparedStatementRequest`, `ActionClosePreparedStatementRequest`, `CommandPreparedStatementQuery`, `CommandPreparedStatementUpdate` |
| **Catalog Metadata** | `CommandGetCatalogs`, `CommandGetDbSchemas`, `CommandGetTables`, `CommandGetTableTypes`, `CommandGetPrimaryKeys`, `CommandGetExportedKeys`, `CommandGetImportedKeys`, `CommandGetCrossReference` |
| **SQL Info** | `CommandGetSqlInfo`, `CommandGetXdbcTypeInfo` |
| **Transactions** | `ActionBeginTransactionRequest`, `ActionEndTransactionRequest`, `ActionBeginSavepointRequest`, `ActionEndSavepointRequest` |

---

## Azure Infrastructure Details

`azd up` provisions the following into your resource group:

- **Azure Storage Account** — hierarchical namespace enabled (ADLS Gen2) for Parquet data files
- **Azure Database for PostgreSQL** — Flexible Server for the DuckLake catalog
- **Azure Container Apps** — runs the Lakehouse Docker image
- **User-assigned managed identity** — attached to the Container App, with `Storage Blob Data Contributor` RBAC
- **Azure Key Vault** — stores the Lakehouse password

A `postprovision` hook runs automatically to configure PostgreSQL Entra auth grants for the managed identity.

### What `azd up` does step by step

1. **`azd provision`** — deploys infrastructure from `infra/main.bicep`, saves outputs to `.env`, runs `hooks/postprovision.sh` for PostgreSQL grants
2. **`azd deploy`** — uploads source to ACR, builds the Docker image remotely via ACR Tasks (no local Docker/Podman needed), updates the Container App revision

> **Note:** The Bicep default image is a placeholder. If you only run `azd provision`, the app container is not deployed yet.

### Required permissions

- Deploying resources: `Contributor`
- Creating role assignments at storage scope: `Owner` or `User Access Administrator`
- PostgreSQL Entra admin principal must be valid in your tenant

### Validation commands

Verify HNS on storage account:

```bash
az storage account show \
  -n "$(azd env get-value STORAGE_ACCOUNT_NAME)" \
  -g "$(azd env get-value AZURE_RESOURCE_GROUP)" \
  --query isHnsEnabled -o tsv
```

Verify Container App identity:

```bash
az identity show \
  -g "$(azd env get-value AZURE_RESOURCE_GROUP)" \
  -n "$(azd env get-value CONTAINER_APP_IDENTITY_NAME)" \
  --query "{clientId:clientId,principalId:principalId}" -o json
```

Verify PostgreSQL Entra auth:

```bash
az postgres flexible-server show \
  -g "$(azd env get-value AZURE_RESOURCE_GROUP)" \
  -n "$(azd env get-value POSTGRES_SERVER_NAME)" \
  --query "authConfig" -o json
```

### Troubleshooting

- If `azd provision` fails on role assignment, your principal likely lacks `roleAssignments/write`.
- PostgreSQL grants are idempotent — re-run safely with `azd hooks run postprovision`.
- `hooks/postprovision.sh` detects your public IP via `https://api.ipify.org` to create a temporary firewall rule. In restricted networks, set `CURRENT_IP` explicitly:

  ```bash
  CURRENT_IP="<your-public-ip>" azd hooks run postprovision
  ```
- PostgreSQL is pinned to a low-cost profile (`Burstable`, `Standard_B1ms`, 1 vCore / 2 GiB, 128 GiB storage).
- `centralus` is configured and tested. Some subscriptions are restricted for PostgreSQL in `eastus` / `eastus2`.

---

## License

MIT

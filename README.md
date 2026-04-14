# Lakehouse

## Arrow Flight SQL + DuckDB on Azure

Query DuckLake over the network using Flight SQL.
Deploy to Azure with `azd up`. Run the JDBC demo in a few commands.

> Experimental: until DuckLake reaches 1.0, this project should be treated as experimental.

## Start Here

If your goal is to get something running quickly:

1. Install Azure CLI, Azure Developer CLI, Java 17+, and Maven.
2. Run `azd up`.
3. Run the built-in Arrow Flight SQL JDBC demo.

Everything after the quickstart is reference.

---

## Features

- **Full Flight SQL protocol** — 35 handlers covering queries, prepared statements, metadata, transactions, and catalog introspection
- **DuckDB + DuckLake** — analytical SQL with PostgreSQL catalog and Azure Blob Storage, plus native Arrow export
- **Authentication** — Basic auth with HMAC-hashed passwords, JWT bearer tokens (HS256/RS256)
- **TLS / mTLS** — encrypted transport with optional client certificate verification
- **Health checking** — standalone gRPC health service (Kubernetes-ready) with background DuckDB probes
- **One-command Azure deploy** — `azd up` provisions storage, PostgreSQL, Container Apps, and managed identity

---

## Azure Quickstart

This is the shortest path from a fresh clone to a live Azure deployment and a working JDBC demo.

### 1. Install the few things you need

| Tool | Install |
| ------ | ------- |
| Azure CLI | `brew install azure-cli` or [aka.ms/installazurecli](https://aka.ms/installazurecli) |
| Azure Developer CLI | `brew install azd` or [learn.microsoft.com/azure/developer/azure-developer-cli/install-azd](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) |
| Java 17+ | any OpenJDK distribution |
| Maven | `brew install maven` |
| Git | `brew install git` |

Sign in once:

```bash
az login
azd auth login
```

### 2. Copy, paste, and set the required values

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
azd env set LAKEHOUSE_SECRET_KEY "$(openssl rand -base64 32)"
```

Find the Entra values if you need them:

```bash
az ad signed-in-user show --query id -o tsv
az ad signed-in-user show --query userPrincipalName -o tsv
```

If you prefer one compact block, this is the whole setup:

```bash
git clone https://github.com/MiguelElGallo/lakehouse.git
cd lakehouse

az login
azd auth login

azd env new lakehouse-dev
azd env set AZURE_SUBSCRIPTION_ID "<your-subscription-id>"
azd env set AZURE_RESOURCE_GROUP "rg-lakehouse2026"
azd env set AZURE_LOCATION "centralus"
azd env set POSTGRES_ADMIN_PASSWORD "<strong-password>"
azd env set POSTGRES_ENTRA_ADMIN_OBJECT_ID "<your-entra-object-id>"
azd env set POSTGRES_ENTRA_ADMIN_PRINCIPAL_NAME "<your-entra-upn>"
azd env set POSTGRES_ENTRA_ADMIN_PRINCIPAL_TYPE "User"
azd env set DUCKLAKE_DATA_PATH "az://lakehouse/data/"
azd env set LAKEHOUSE_SECRET_KEY "$(openssl rand -base64 32)"

azd up
```

### 3. Deploy to Azure

```bash
azd up
```

That single command provisions the infrastructure, builds the image remotely, deploys Container Apps, and runs the PostgreSQL grant hook.

### 4. Run the live JDBC demo

Get the endpoint and password:

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

Run the Arrow Flight SQL JDBC demo:

```bash
cd tests/jdbc
export LAKEHOUSE_DEMO_ENDPOINT="$ENDPOINT"
export LAKEHOUSE_DEMO_PASSWORD="$PASSWORD"
export LAKEHOUSE_DEMO_USER="lakehouse"
MAVEN_OPTS="--add-opens=java.base/java.nio=ALL-UNNAMED" \
mvn -q -Dexec.mainClass=lakehouse.AzureDemo test-compile exec:java
```

The `MAVEN_OPTS` flag is required for Apache Arrow on Java 17+.

### Run the live backend tests

The live backend pytest is opt-in because it queries the deployed Azure Container App and reads the `lakehouse-password` secret from Key Vault:

```bash
LAKEHOUSE_LIVE_BACKEND=1 uv run pytest -q tests/test_live_azure_backend.py
```

That default path uses PyArrow to perform the Basic-token handshake, then gives the returned Bearer token to ADBC for the query. It verifies the deployed endpoint, TLS, Key Vault password, and Bearer auth path.

There is also a separate opt-in check for ADBC's direct Basic-auth path:

```bash
LAKEHOUSE_LIVE_BACKEND=1 LAKEHOUSE_LIVE_BACKEND_ADBC_BASIC=1 \
  uv run pytest -q tests/test_live_azure_backend.py
```

The ADBC Basic check is marked `xfail` because that is the known client path currently failing against the deployed Container App. A result such as `1 passed, 1 xfailed` means the supported bearer smoke test passed and the tracked ADBC Basic issue reproduced as expected. If that changes to `1 passed, 1 xpassed`, the ADBC Basic path has started working and the `xfail` marker should be removed.

If you want one copy/paste block for the demo itself:

```bash
ENDPOINT="$(az containerapp show \
  -g "$(azd env get-value AZURE_RESOURCE_GROUP)" \
  -n "$(azd env get-value CONTAINER_APP_NAME)" \
  --query properties.configuration.ingress.fqdn -o tsv):443"

PASSWORD="$(az keyvault secret show \
  --vault-name "$(azd env get-value KEY_VAULT_NAME)" \
  --name lakehouse-password \
  --query value -o tsv)"

cd tests/jdbc
export LAKEHOUSE_DEMO_ENDPOINT="$ENDPOINT"
export LAKEHOUSE_DEMO_PASSWORD="$PASSWORD"
export LAKEHOUSE_DEMO_USER="lakehouse"
MAVEN_OPTS="--add-opens=java.base/java.nio=ALL-UNNAMED" \
mvn -q -Dexec.mainClass=lakehouse.AzureDemo test-compile exec:java
```

### 5. What success looks like

```text
Connecting to ca-lakehouse-xxxxx.centralus.azurecontainerapps.io:443 ...

=== CATALOGS ===
  lakehouse
  system
  temp

=== SCHEMAS ===
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

At that point, the Azure deployment is working end to end through Arrow Flight SQL and JDBC.

---

## After Quickstart

Use this section only after the fast path above is already working.

### What `azd up` gives you

Lakehouse runs on Azure Container Apps and attaches DuckLake using:

- Azure Blob Storage for data files
- Azure Database for PostgreSQL Flexible Server for the catalog
- Key Vault for the demo password
- a managed identity for Azure access from the container

### Verify the deployed endpoint

```bash
az containerapp show \
  -g "$(azd env get-value AZURE_RESOURCE_GROUP)" \
  -n "$(azd env get-value CONTAINER_APP_NAME)" \
  --query properties.configuration.ingress.fqdn -o tsv
```

### Other client options

#### JDBC notes

`AzureDemo` also accepts `endpoint password [username]` as positional args, but the environment-variable form is more reliable with `mvn exec:java`.

#### ADBC (Python)

Install the ADBC Flight SQL driver:

```bash
pip install adbc-driver-flightsql
```

Connect to your Azure deployment:

```python
import base64
import adbc_driver_flightsql.dbapi as flight_sql
from adbc_driver_flightsql import DatabaseOptions

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

You should see the rows inserted by the JDBC demo, or an empty result if you have not run it yet.

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
| ------- | -------- | ------------ | ------- | ------------ | ----------- |
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
| ------ | ----------- |
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
| -------- | -------------------- |
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
- **PostgreSQL Entra admin principal** — granted `Storage Blob Data Contributor` RBAC for local DuckLake validation
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

## Release Notes

### April 13, 2026 dependency refresh

Updated the `uv` lockfile to current compatible package versions and validated the Azure deployment flow. Notable upgrades include `duckdb` 1.5.2, `grpcio` 1.80.0, `grpcio-health-checking` 1.80.0, `azure-identity` 1.25.3, `azure-core` 1.39.0, `pydantic` 2.13.0, `pyjwt` 2.12.1, `rich` 15.0.0, `ruff` 0.15.10, `ty` 0.0.29, `pytest` 9.0.3, and `adbc-driver-flightsql` 1.11.0.

---

## License

MIT

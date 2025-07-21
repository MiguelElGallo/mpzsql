"""
CLI interface for MPZSQL server using typer.

This module implements the command-line argument parsing and main entrypoint
for the MPZSQL server, supporting all options from the original Examples implementation.
"""

import asyncio
import logging
import os
import secrets
from pathlib import Path
from typing import Optional, Tuple

import duckdb
import fsspec
import typer
from azure.identity.aio import DefaultAzureCredential
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from mpzsql import __version__
from mpzsql.config import ServerConfig
from mpzsql.server import MPZSQLServer
from mpzsql.logfire_config import LogfireManager, get_main_logger

# Create typer app and rich console
app = typer.Typer(
    name="mpzsql-server",
    help="Apache Arrow FlightSQL Server with DuckLake and Azure integration",
    add_completion=False,
)
console = Console()


def validate_postgresql_connection(config: ServerConfig) -> bool:
    """Test PostgreSQL connection using provided configuration."""
    logger = get_main_logger()
    
    if not config.is_postgresql_enabled:
        return True  # Skip test if not configured

    try:
        import subprocess

        import psycopg2

        console.print(
            f"[blue]🔍 Testing PostgreSQL connection to {config.postgresql_server}:{config.postgresql_port}...[/blue]"
        )
        logger.info("Testing PostgreSQL connection", 
                   server=config.postgresql_server, 
                   port=config.postgresql_port)

        # Handle Azure authentication
        password = config.postgresql_password
        if password == "AZURE":
            console.print("[blue]🔑 Getting Azure access token...[/blue]")
            try:
                result = subprocess.run(
                    [
                        "az",
                        "account",
                        "get-access-token",
                        "--resource",
                        "https://ossrdbms-aad.database.windows.net",
                        "--query",
                        "accessToken",
                        "--output",
                        "tsv",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                password = result.stdout.strip()
                console.print("[green]✅ Azure access token obtained[/green]")
                logger.info("Azure access token obtained for PostgreSQL")
            except subprocess.CalledProcessError as e:
                console.print(f"[red]❌ Failed to get Azure access token: {e}[/red]")
                logger.error("Failed to get Azure access token", error=str(e))
                return False
            except FileNotFoundError:
                console.print(
                    "[red]❌ Azure CLI not found. Please install Azure CLI[/red]"
                )
                logger.error("Azure CLI not found")
                return False

        # Build connection string
        conn_params = {
            "host": config.postgresql_server,
            "port": config.postgresql_port,
            "user": config.postgresql_user,
            "password": password,
            "connect_timeout": 10,
        }

        if config.postgresql_catalogdb:
            conn_params["database"] = config.postgresql_catalogdb

        # Test connection
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        cursor.close()
        conn.close()

        console.print("[green]✅ PostgreSQL connection successful[/green]")
        console.print(
            f"[dim]   Server: {config.postgresql_server}:{config.postgresql_port}[/dim]"
        )
        console.print(f"[dim]   User: {config.postgresql_user}[/dim]")
        if config.postgresql_catalogdb:
            console.print(f"[dim]   Database: {config.postgresql_catalogdb}[/dim]")
        console.print(f"[dim]   Version: {version.split(',')[0]}[/dim]")
        
        logger.info("PostgreSQL connection successful", 
                   server=config.postgresql_server,
                   port=config.postgresql_port,
                   user=config.postgresql_user,
                   database=config.postgresql_catalogdb,
                   version=version.split(',')[0])
        return True

    except ImportError:
        console.print(
            "[red]❌ PostgreSQL connection failed: psycopg2-binary not installed[/red]"
        )
        logger.error("PostgreSQL connection failed: psycopg2-binary not installed")
        return False
    except Exception as e:
        console.print(f"[red]❌ PostgreSQL connection failed: {e}[/red]")
        console.print(
            f"[dim]   Server: {config.postgresql_server}:{config.postgresql_port}[/dim]"
        )
        console.print(f"[dim]   User: {config.postgresql_user}[/dim]")
        if config.postgresql_catalogdb:
            console.print(f"[dim]   Database: {config.postgresql_catalogdb}[/dim]")
        logger.error("PostgreSQL connection failed", 
                    error=str(e),
                    server=config.postgresql_server,
                    port=config.postgresql_port,
                    user=config.postgresql_user,
                    database=config.postgresql_catalogdb)
        return False


def validate_azure_storage_connection(config: ServerConfig) -> bool:
    """Test Azure Storage connection using default credentials."""
    logger = get_main_logger()
    
    if not config.is_azure_storage_enabled:
        return True  # Skip test if not configured

    try:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient

        console.print(
            f"[blue]🔍 Testing Azure Storage connection to {config.azure_storage_account}...[/blue]"
        )
        logger.info("Testing Azure Storage connection", 
                   account=config.azure_storage_account,
                   container=config.azure_storage_container)

        # Use default credentials
        credential = DefaultAzureCredential()
        account_url = f"https://{config.azure_storage_account}.blob.core.windows.net"

        # Test connection
        blob_service_client = BlobServiceClient(
            account_url=account_url, credential=credential
        )
        container_client = blob_service_client.get_container_client(
            config.azure_storage_container
        )

        # Try to get container properties to test connection
        properties = container_client.get_container_properties()

        console.print("[green]✅ Azure Storage connection successful[/green]")
        console.print(f"[dim]   Account: {config.azure_storage_account}[/dim]")
        console.print(f"[dim]   Container: {config.azure_storage_container}[/dim]")
        console.print(f"[dim]   Last Modified: {properties.last_modified}[/dim]")
        
        logger.info("Azure Storage connection successful",
                   account=config.azure_storage_account,
                   container=config.azure_storage_container,
                   last_modified=str(properties.last_modified))
        return True

    except ImportError:
        console.print(
            "[red]❌ Azure Storage connection failed: azure-storage-blob or azure-identity not installed[/red]"
        )
        logger.error("Azure Storage connection failed: missing dependencies")
        return False
    except Exception as e:
        console.print(f"[red]❌ Azure Storage connection failed: {e}[/red]")
        console.print(f"[dim]   Account: {config.azure_storage_account}[/dim]")
        console.print(f"[dim]   Container: {config.azure_storage_container}[/dim]")
        logger.error("Azure Storage connection failed",
                    error=str(e),
                    account=config.azure_storage_account,
                    container=config.azure_storage_container)
        return False


def validate_backend(value: str) -> str:
    """Validate backend option."""
    if value not in ["duckdb", "sqlite"]:
        raise typer.BadParameter("Backend must be 'duckdb' or 'sqlite'")
    return value


def validate_tls_files(
    cert_file: Optional[str], key_file: Optional[str]
) -> Tuple[Optional[str], Optional[str]]:
    """Validate TLS certificate and key files."""
    if cert_file and key_file:
        if not Path(cert_file).exists():
            raise typer.BadParameter(f"TLS certificate file not found: {cert_file}")
        if not Path(key_file).exists():
            raise typer.BadParameter(f"TLS key file not found: {key_file}")
    elif cert_file or key_file:
        raise typer.BadParameter(
            "Both --tls-cert and --tls-key must be provided together"
        )
    return cert_file, key_file


def load_init_sql(
    init_sql: Optional[str], init_sql_file: Optional[str]
) -> Optional[str]:
    """Load initialization SQL from inline command or file."""
    if init_sql_file:
        try:
            return Path(init_sql_file).read_text()
        except FileNotFoundError:
            raise typer.BadParameter(f"Init SQL file not found: {init_sql_file}")
        except Exception as e:
            raise typer.BadParameter(f"Error reading init SQL file: {e}")
    return init_sql


@app.command()
def main(
    # Backend options
    backend: str = typer.Option(
        "duckdb",
        "--backend",
        help="Database backend (duckdb, sqlite)",
        callback=lambda _, value: validate_backend(value) if value else "duckdb",
    ),
    database: Optional[str] = typer.Option(
        None,
        "--database",
        help="Database filename (defaults to in-memory for DuckDB, required for SQLite)",
    ),
    # Network options
    hostname: Optional[str] = typer.Option(
        None,
        "--hostname",
        help="Server hostname to listen on (default: localhost, env: MPZSQL_HOSTNAME)",
    ),
    advertised_hostname: Optional[str] = typer.Option(
        None,
        "--advertised-hostname",
        help="Hostname to advertise to clients (defaults to hostname, env: MPZSQL_ADVERTISED_HOSTNAME or WEBSITE_HOSTNAME)",
    ),
    port: int = typer.Option(
        8080,
        "--port",
        help="Server port (default: 8080, env: MPZSQL_PORT takes precedence)",
        min=1,
        max=65535,
    ),
    # Authentication options
    username: Optional[str] = typer.Option(
        None,
        "--username",
        help="Authentication username (env: MPZSQL_USERNAME)",
    ),
    password: Optional[str] = typer.Option(
        None,
        "--password",
        help="Authentication password (env: MPZSQL_PASSWORD)",
    ),
    secret_key: Optional[str] = typer.Option(
        None,
        "--secret-key",
        help="JWT secret key (env: SECRET_KEY, random if not provided)",
    ),
    # TLS options
    tls_cert: Optional[str] = typer.Option(
        None,
        "--tls-cert",
        help="TLS certificate file path",
    ),
    tls_key: Optional[str] = typer.Option(
        None,
        "--tls-key",
        help="TLS private key file path",
    ),
    mtls_ca: Optional[str] = typer.Option(
        None,
        "--mtls-ca",
        help="mTLS CA certificate for client verification (env: MPZSQL_MTLS_CA)",
    ),
    # SQL initialization options
    init_sql: Optional[str] = typer.Option(
        None,
        "--init-sql",
        help="SQL commands to run on startup (env: MPZSQL_INIT_SQL)",
    ),
    init_sql_file: Optional[str] = typer.Option(
        None,
        "--init-sql-file",
        help="File containing SQL commands to run on startup (env: MPZSQL_INIT_SQL_FILE)",
    ),
    # Server behavior options
    print_queries: bool = typer.Option(
        False,
        "--print-queries",
        help="Print executed queries to console",
    ),
    read_only: bool = typer.Option(
        False,
        "--read-only",
        help="Enable read-only mode",
    ),
    # PostgreSQL connection options
    postgresql_server: Optional[str] = typer.Option(
        None,
        "--postgresql-server",
        help="PostgreSQL server hostname (env: POSTGRESQL_SERVER)",
    ),
    postgresql_port: Optional[int] = typer.Option(
        5432,
        "--postgresql-port",
        help="PostgreSQL server port (env: POSTGRESQL_PORT)",
    ),
    postgresql_user: Optional[str] = typer.Option(
        None,
        "--postgresql-user",
        help="PostgreSQL username (env: POSTGRESQL_USER)",
    ),
    postgresql_password: Optional[str] = typer.Option(
        None,
        "--postgresql-password",
        help="PostgreSQL password (env: POSTGRESQL_PASSWORD)",
    ),
    postgresql_catalogdb: Optional[str] = typer.Option(
        None,
        "--postgresql-catalogdb",
        help="PostgreSQL catalog database name (env: POSTGRESQL_CATALOGDB)",
    ),
    # Azure Storage connection options
    azure_storage_account: Optional[str] = typer.Option(
        None,
        "--azure-storage-account",
        help="Azure Storage account name (env: AZURE_STORAGE_ACCOUNT)",
    ),
    azure_storage_container: Optional[str] = typer.Option(
        None,
        "--azure-storage-container",
        help="Azure Storage container name (env: AZURE_STORAGE_CONTAINER)",
    ),
    # Version option
    version: bool = typer.Option(
        False,
        "--version",
        help="Show version and exit",
    ),
) -> None:
    """Start the MPZSQL Apache Arrow FlightSQL server."""

    # Initialize logfire
    LogfireManager.initialize()
    logger = get_main_logger()
    
    # Setup legacy logging for backward compatibility (but logfire is now primary)
    log_file = os.getenv("MPZSQL_LOG_FILE", "mpzsql.log")
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        filename=log_file,
        filemode="w",  # Overwrite log on each start
    )
    # Add a handler to also print to console
    logging.getLogger().addHandler(logging.StreamHandler())

    logger.info("MPZSQL Server starting", version=__version__)


    if version:
        console.print(f"MPZSQL Server version {__version__}")
        raise typer.Exit()

    # Validate TLS configuration
    tls_cert, tls_key = validate_tls_files(tls_cert, tls_key)

    # Environment variable fallbacks
    hostname = hostname or os.getenv("MPZSQL_HOSTNAME", "localhost")
    
    # Advertised hostname with Azure Web Apps support
    # Priority: CLI option > MPZSQL_ADVERTISED_HOSTNAME > WEBSITE_HOSTNAME > hostname
    if advertised_hostname is None:
        advertised_hostname = (
            os.getenv("MPZSQL_ADVERTISED_HOSTNAME") or
            os.getenv("WEBSITE_HOSTNAME")  # Azure Web Apps hostname
        )
    
    # Handle MPZSQL_PORT environment variable with precedence over CLI port
    env_port = os.getenv("MPZSQL_PORT")
    if env_port:
        try:
            port = int(env_port)
            if port < 1 or port > 65535:
                console.print(f"[red]Error:[/red] Invalid port in MPZSQL_PORT environment variable: {env_port} (must be 1-65535)")
                raise typer.Exit(1)
        except ValueError:
            console.print(f"[red]Error:[/red] Invalid port in MPZSQL_PORT environment variable: {env_port} (must be a number)")
            raise typer.Exit(1)
    
    username = username or os.getenv("MPZSQL_USERNAME")
    password = password or os.getenv("MPZSQL_PASSWORD")
    secret_key = secret_key or os.getenv("SECRET_KEY")
    mtls_ca = mtls_ca or os.getenv("MPZSQL_MTLS_CA")
    init_sql = init_sql or os.getenv("MPZSQL_INIT_SQL")
    init_sql_file = init_sql_file or os.getenv("MPZSQL_INIT_SQL_FILE")

    # PostgreSQL environment variable fallbacks
    postgresql_server = postgresql_server or os.getenv("POSTGRESQL_SERVER")
    postgresql_user = postgresql_user or os.getenv("POSTGRESQL_USER")
    postgresql_password = postgresql_password or os.getenv("POSTGRESQL_PASSWORD")
    postgresql_catalogdb = postgresql_catalogdb or os.getenv("POSTGRESQL_CATALOGDB")

    # Azure Storage environment variable fallbacks
    azure_storage_account = azure_storage_account or os.getenv("AZURE_STORAGE_ACCOUNT")
    azure_storage_container = azure_storage_container or os.getenv(
        "AZURE_STORAGE_CONTAINER"
    )

    # Generate random secret key if not provided
    if not secret_key:
        secret_key = secrets.token_urlsafe(32)
        console.print(
            "[yellow]Warning:[/yellow] No secret key provided, generated random key for this session"
        )

    # Load initialization SQL
    try:
        init_sql_content = load_init_sql(init_sql, init_sql_file)
    except typer.BadParameter as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Validate SQLite requires database file
    if backend == "sqlite" and not database:
        console.print("[red]Error:[/red] SQLite backend requires --database option")
        raise typer.Exit(1)

    # Validate mTLS CA file if provided
    if mtls_ca and not Path(mtls_ca).exists():
        console.print(f"[red]Error:[/red] mTLS CA file not found: {mtls_ca}")
        raise typer.Exit(1)

    # Create server configuration
    try:
        config = ServerConfig(
            backend=backend,
            database=database,
            hostname=hostname,
            advertised_hostname=advertised_hostname,
            port=port,
            username=username,
            password=password,
            secret_key=secret_key,
            tls_cert=tls_cert,
            tls_key=tls_key,
            mtls_ca=mtls_ca,
            init_sql=init_sql_content,
            print_queries=print_queries,
            read_only=read_only,
            postgresql_server=postgresql_server,
            postgresql_port=postgresql_port,
            postgresql_user=postgresql_user,
            postgresql_password=postgresql_password,
            postgresql_catalogdb=postgresql_catalogdb,
            azure_storage_account=azure_storage_account,
            azure_storage_container=azure_storage_container,
        )
    except Exception as e:
        console.print(f"[red]Error:[/red] Invalid configuration: {e}")
        raise typer.Exit(1)

    # Test external connections if configured
    connection_checks_passed = True

    if config.is_postgresql_enabled:
        if not validate_postgresql_connection(config):
            connection_checks_passed = False

    if config.is_azure_storage_enabled:
        if not validate_azure_storage_connection(config):
            connection_checks_passed = False

    # Stop server if any connection checks failed
    if not connection_checks_passed:
        console.print(
            "\n[red]❌ Server startup aborted due to connection failures[/red]"
        )
        raise typer.Exit(1)

    # Initialize DuckDB with or without Azure integration
    duckdb_con = None
    if config.backend == "duckdb":
        if config.is_azure_storage_enabled:
            duckdb_con = asyncio.run(initialize_duckdb_with_azure(config))
        else:
            duckdb_con = initialize_duckdb_basic(config)

    # Print startup banner
    print_startup_banner(config)

    # Create and start server
    try:
        server = MPZSQLServer(config, duckdb_con)
        server.start()
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped by user[/yellow]")
        if duckdb_con:
            duckdb_con.close()
        raise typer.Exit(0)
    except Exception as e:
        console.print(f"[red]Server error:[/red] {e}")
        if duckdb_con:
            duckdb_con.close()
        raise typer.Exit(1)


async def setup_azure_filesystem(account_name: str, credential):
    """Creates the fsspec filesystem for Azure."""
    console.print(f"\n🔐 Setting up Azure filesystem for account: {account_name}")
    try:
        az_fs = fsspec.filesystem(
            "abfs", account_name=account_name, credential=credential
        )
        console.print("✅ Azure filesystem created successfully!")
        return az_fs
    except Exception as e:
        console.print(f"❌ Failed to setup Azure filesystem: {e}")
        raise


def setup_duckdb_connection(az_fs, config: ServerConfig) -> duckdb.DuckDBPyConnection:
    """Creates a DuckDB connection and registers the Azure filesystem."""
    console.print("\n🦆 Setting up DuckDB connection with Azure filesystem...")
    try:
        # The `allow_unsigned_extensions` setting may be needed if the httpfs extension is not signed.
        connection_config = {"allow_unsigned_extensions": "true"}

        if config.database:
            console.print(f"   Using database file: {config.database}")
            con = duckdb.connect(config.database, config=connection_config)
        else:
            console.print("   Using in-memory database")
            con = duckdb.connect(":memory:", config=connection_config)

        con.register_filesystem(az_fs)
        console.print("✅ Azure filesystem registered with DuckDB!")
        return con
    except Exception as e:
        console.print(f"❌ Failed to setup DuckDB connection: {e}")
        raise


async def initialize_duckdb_with_azure(
    config: ServerConfig,
) -> Optional[duckdb.DuckDBPyConnection]:
    """Initialize DuckDB with Azure integration and run setup commands."""
    if not config.is_azure_storage_enabled:
        console.print(
            "\n[yellow]⚠️  Azure Storage not configured, falling back to basic DuckDB initialization[/yellow]"
        )
        return initialize_duckdb_basic(config)

    console.print("\n" + "=" * 60)
    console.print("🚀 INITIALIZING DUCKDB WITH AZURE INTEGRATION")
    console.print("=" * 60)

    try:
        # Setup Azure filesystem
        async with DefaultAzureCredential() as credential:
            az_fs = await setup_azure_filesystem(
                config.azure_storage_account, credential
            )
            con = setup_duckdb_connection(az_fs, config)

            # Install required extensions
            console.print("\n📦 Installing DuckDB extensions...")

            console.print("Installing ducklake extension...")
            try:
                result = con.execute("INSTALL ducklake;").fetchall()
                console.print("✅ ducklake extension installed successfully")
                console.print(f"   Result: {result}")
            except Exception as e:
                console.print(f"❌ Failed to install ducklake extension: {e}")
                raise

            console.print("Installing postgres extension...")
            try:
                result = con.execute("INSTALL postgres;").fetchall()
                console.print("✅ postgres extension installed successfully")
                console.print(f"   Result: {result}")
            except Exception as e:
                console.print(f"❌ Failed to install postgres extension: {e}")
                raise

            # Create PostgreSQL secret if configured
            if config.is_postgresql_enabled:
                console.print("\n🔐 Creating PostgreSQL secret...")
                try:
                    # Handle special case for Azure authentication
                    if config.postgresql_password == "AZURE":
                        console.print("Using Azure authentication for PostgreSQL...")
                        import subprocess

                        result = subprocess.run(
                            [
                                "az",
                                "account",
                                "get-access-token",
                                "--resource",
                                "https://ossrdbms-aad.database.windows.net",
                                "--query",
                                "accessToken",
                                "--output",
                                "tsv",
                            ],
                            capture_output=True,
                            text=True,
                            check=True,
                        )
                        pg_password = result.stdout.strip()
                        console.print("✅ Azure access token obtained for PostgreSQL")
                    else:
                        pg_password = config.postgresql_password

                    pg_secret_sql = f"""
                    CREATE SECRET (
                        TYPE postgres,
                        HOST '{config.postgresql_server}',
                        PORT {config.postgresql_port},
                        DATABASE {config.postgresql_catalogdb or "postgres"},
                        USER '{config.postgresql_user}',
                        PASSWORD '{pg_password}'
                    );
                    """
                    result = con.execute(pg_secret_sql).fetchall()
                    console.print("✅ PostgreSQL secret created successfully")
                    console.print(f"   Result: {result}")
                except Exception as e:
                    console.print(f"❌ Failed to create PostgreSQL secret: {e}")
                    raise

            # Create Azure secret
            console.print("\n🔐 Creating Azure secret...")
            try:
                azure_secret_sql = f"""
                CREATE OR REPLACE SECRET secr_azure_lake1 (
                    TYPE azure,
                    PROVIDER CREDENTIAL_CHAIN,
                    ACCOUNT_NAME '{config.azure_storage_account}'
                );
                """
                result = con.execute(azure_secret_sql).fetchall()
                console.print("✅ Azure secret created successfully")
                console.print(f"   Result: {result}")
            except Exception as e:
                console.print(f"❌ Failed to create Azure secret: {e}")
                raise

            # Attach ducklake catalog if PostgreSQL is configured
            if config.is_postgresql_enabled:
                console.print("\n🔗 Attaching ducklake catalog...")
                try:
                    attach_sql = f"""
                    ATTACH 'ducklake:postgres:dbname=ducklake_catalog host={config.postgresql_server}' AS my_ducklake
                        (DATA_PATH 'abfs://{config.azure_storage_container}');
                    """
                    result = con.execute(attach_sql).fetchall()
                    console.print("✅ ducklake catalog attached successfully")
                    console.print(f"   Result: {result}")

                    # Switch to the ducklake database
                    #result = con.execute("USE my_ducklake;").fetchall()
                    #console.print("✅ Switched to ducklake database")
                    #console.print(f"   Result: {result}")

                    # Show available databases for verification
                    console.print("\n📋 Verifying available databases...")
                    databases_result = con.execute("SHOW DATABASES;").fetchall()
                    console.print("✅ Available databases:")
                    for db in databases_result:
                        console.print(f"   - {db[0]}")

                    # Show current database
                    current_db_result = con.execute(
                        "SELECT current_database();"
                    ).fetchall()
                    console.print(f"✅ Current database: {current_db_result[0][0]}")
                except Exception as e:
                    console.print(f"❌ Failed to attach ducklake catalog: {e}")
                    raise

            console.print(
                "\n🎉 DuckDB with Azure integration initialized successfully!"
            )
            return con

    except Exception as e:
        console.print(f"\n❌ Failed to initialize DuckDB with Azure: {e}")
        console.print("\n🔄 Falling back to basic DuckDB initialization...")
        try:
            return initialize_duckdb_basic(config)
        except Exception as basic_e:
            console.print(f"\n❌ Basic DuckDB initialization also failed: {basic_e}")
            return None


def initialize_duckdb_basic(config: ServerConfig) -> duckdb.DuckDBPyConnection:
    """Initialize DuckDB without Azure integration."""
    console.print("\n🦆 Initializing DuckDB connection...")
    try:
        connection_config = {"allow_unsigned_extensions": "true"}

        if config.database:
            console.print(f"   Using database file: {config.database}")
            con = duckdb.connect(config.database, config=connection_config)
        else:
            console.print("   Using in-memory database")
            con = duckdb.connect(":memory:", config=connection_config)

        console.print("✅ DuckDB connection initialized successfully!")
        return con
    except Exception as e:
        console.print(f"❌ Failed to initialize DuckDB connection: {e}")
        raise


def print_startup_banner(config: ServerConfig) -> None:
    """Print server startup banner with configuration details."""

    # Server info
    server_info = Text()
    server_info.append("MPZSQL Server ", style="bold blue")
    server_info.append(f"v{__version__}", style="dim")
    server_info.append("\nApache Arrow FlightSQL Server")

    # Configuration summary
    config_lines = [
        f"Backend: {config.backend}",
        f"Database: {config.database or 'in-memory' if config.backend == 'duckdb' else 'N/A'}",
        f"Listen Address: {config.hostname}:{config.port}",
        f"Advertised Address: {config.effective_advertised_hostname}:{config.port}",
        f"TLS: {'enabled' if config.tls_cert else 'disabled'}",
        f"mTLS: {'enabled' if config.mtls_ca else 'disabled'}",
        f"Auth: {'enabled' if config.username else 'disabled'}",
        f"Read-only: {'yes' if config.read_only else 'no'}",
        f"Print queries: {'yes' if config.print_queries else 'no'}",
    ]

    # Add PostgreSQL info
    if config.is_postgresql_enabled:
        config_lines.append(
            f"PostgreSQL: {config.postgresql_server}:{config.postgresql_port} (user: {config.postgresql_user})"
        )
    else:
        config_lines.append("PostgreSQL: not configured")

    # Add Azure Storage info
    if config.is_azure_storage_enabled:
        config_lines.append(
            f"Azure Storage: {config.azure_storage_account}/{config.azure_storage_container}"
        )
    else:
        config_lines.append("Azure Storage: not configured")

    if config.init_sql:
        config_lines.append("Init SQL: provided")

    config_text = "\n".join(config_lines)

    # Create panels
    console.print(Panel(server_info, title="Server Starting", border_style="blue"))
    console.print(Panel(config_text, title="Configuration", border_style="green"))

    # Security warnings
    warnings = []
    if not config.tls_cert:
        warnings.append("⚠️  TLS disabled - connection is not encrypted")
    if not config.username:
        warnings.append("⚠️  Authentication disabled - server is open to all")
    if config.database and config.backend == "sqlite":
        if not Path(config.database).parent.exists():
            warnings.append(
                f"⚠️  Database directory doesn't exist: {Path(config.database).parent}"
            )

    if warnings:
        warning_text = "\n".join(warnings)
        console.print(
            Panel(warning_text, title="Security Warnings", border_style="yellow")
        )

    console.print(
        f"\n[green]Starting server on {config.hostname}:{config.port}...[/green]"
    )
    
    # Show advertised address if different from listen address
    if config.effective_advertised_hostname != config.hostname:
        console.print(
            f"[blue]Clients will connect to: {config.effective_advertised_hostname}:{config.port}[/blue]"
        )


if __name__ == "__main__":
    app()
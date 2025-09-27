"""CLI interface for MPZSQL server using typer.

This module implements the command-line argument parsing and main entrypoint
for the MPZSQL server, supporting all options from the original Examples implementation.
"""

import asyncio
import logging
import os
import secrets
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import fsspec
import psycopg2
import psycopg2.errors
import typer
from azure.identity import DefaultAzureCredential
from azure.identity.aio import DefaultAzureCredential as DefaultAzureCredentialAsync
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Import psutil for memory monitoring (optional)
try:
    import psutil  # noqa: F401

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from mpzsql import __version__
from mpzsql.config import ServerConfig
from mpzsql.logfire_config import LogfireManager, get_main_logger
from mpzsql.server import MPZSQLServer

# Create typer app and rich console
app = typer.Typer(
    name="mpzsql-server",
    help="Apache Arrow FlightSQL Server with DuckLake and Azure integration",
    add_completion=False,
)
console = Console()


class AzureCredentialManager:
    """
    Manages Azure credentials for PostgreSQL authentication using DefaultAzureCredential.

    This class provides:
    - Token caching to avoid repeated credential requests
    - Automatic token refresh when tokens expire
    - Proper error handling with fallback to subprocess calls
    - Thread-safe credential management
    - DuckDB secret refresh for expired tokens
    """

    def __init__(self):
        self._credential = None
        self._cached_token = None
        self._token_expires_at = None
        self._postgresql_scope = "https://ossrdbms-aad.database.windows.net/.default"
        self._duckdb_connection = None
        self._server_config = None

    def set_duckdb_connection(self, connection, config):
        """
        Set the DuckDB connection and server config for automatic secret refresh.

        Args:
            connection: DuckDB connection object
            config: ServerConfig object with PostgreSQL settings
        """
        self._duckdb_connection = connection
        self._server_config = config

    def get_postgresql_token(self, force_refresh: bool = False) -> str:
        """
        Get a valid PostgreSQL access token using DefaultAzureCredential.

        Args:
            force_refresh: If True, bypass cache and get a fresh token

        Returns:
            str: A valid access token for PostgreSQL

        Raises:
            Exception: If token acquisition fails
        """
        # Check if we have a cached token that's still valid (with 5-minute buffer)
        now = datetime.now()
        if (
            not force_refresh
            and self._cached_token
            and self._token_expires_at
            and self._token_expires_at > now + timedelta(minutes=5)
        ):
            return self._cached_token

        # Initialize credential if not already done
        if not self._credential:
            console.print(
                "[blue]🔑 Initializing Azure DefaultAzureCredential...[/blue]"
            )
            self._credential = DefaultAzureCredential()

        try:
            console.print(
                "[blue]🔑 Getting Azure access token for PostgreSQL...[/blue]"
            )

            # Get token from DefaultAzureCredential
            token_result = self._credential.get_token(self._postgresql_scope)

            # Cache the token and its expiration
            old_token = self._cached_token
            self._cached_token = token_result.token
            self._token_expires_at = datetime.fromtimestamp(token_result.expires_on)

            console.print(
                f"[green]✅ Azure token obtained, expires at {self._token_expires_at}[/green]"
            )

            # Validate token format
            if not validate_azure_token_format(self._cached_token):
                console.print(
                    "[yellow]⚠️  Token validation warnings detected - connection may fail[/yellow]"
                )

            # Debug: Log token info (first/last 10 characters for security)
            if len(self._cached_token) > 20:
                token_preview = (
                    f"{self._cached_token[:10]}...{self._cached_token[-10:]}"
                )
                console.print(
                    f"[dim]Token preview: {token_preview} (length: {len(self._cached_token)})[/dim]"
                )

                # Warn about very long tokens
                if len(self._cached_token) > 2000:
                    console.print(
                        f"[yellow]⚠️  Token is very long ({len(self._cached_token)} chars) - this might cause issues[/yellow]"
                    )

            # If token changed and we have a DuckDB connection, refresh the secret
            if (
                old_token != self._cached_token
                and self._duckdb_connection
                and self._server_config
            ):
                self._refresh_duckdb_secret()

            return self._cached_token

        except Exception as e:
            console.print(f"[yellow]⚠️  DefaultAzureCredential failed: {e}[/yellow]")
            console.print("[yellow]Falling back to az CLI...[/yellow]")

            # Fallback to subprocess call (existing behavior)
            return self._get_token_via_subprocess()

    def _refresh_duckdb_secret(self):
        """
        Refresh the PostgreSQL secret in DuckDB with the new token.
        """
        if not self._duckdb_connection or not self._server_config:
            return

        try:
            console.print("[blue]🔄 Refreshing PostgreSQL secret in DuckDB...[/blue]")

            # Drop any existing PostgreSQL secrets (both named and anonymous)
            # Try to drop named secret first, then anonymous
            try:
                drop_named_secret_sql = "DROP SECRET IF EXISTS postgres_secret;"
                self._duckdb_connection.execute(drop_named_secret_sql)
            except Exception:
                pass  # Ignore errors for named secret cleanup

            try:
                drop_anonymous_secret_sql = "DROP SECRET (TYPE postgres);"
                self._duckdb_connection.execute(drop_anonymous_secret_sql)
            except Exception:
                pass  # Ignore errors for anonymous secret cleanup

            # Create the new secret with the fresh token
            create_secret_sql = create_duckdb_postgresql_secret_sql(
                host=self._server_config.postgresql_server,
                port=self._server_config.postgresql_port,
                database=self._server_config.postgresql_catalogdb,
                user=self._server_config.postgresql_user,
                password=self._cached_token,
            )
            console.print(
                f"[dim]Creating DuckDB secret with USER: '{self._server_config.postgresql_user}' (length: {len(self._server_config.postgresql_user)})[/dim]"
            )

            # Check for potential username truncation issues
            if len(self._server_config.postgresql_user) > 63:
                console.print(
                    f"[yellow]⚠️  Username is very long ({len(self._server_config.postgresql_user)} chars) - some PostgreSQL drivers truncate usernames at 63 characters[/yellow]"
                )

            try:
                # Debug: Show the SQL without the password
                debug_sql = create_duckdb_postgresql_secret_debug_sql(
                    host=self._server_config.postgresql_server,
                    port=self._server_config.postgresql_port,
                    database=self._server_config.postgresql_catalogdb,
                    user=self._server_config.postgresql_user,
                )
                console.print(f"[dim]Secret SQL: {debug_sql.strip()}[/dim]")

                self._duckdb_connection.execute(create_secret_sql).fetchall()
                console.print("[green]✅ PostgreSQL secret refreshed in DuckDB[/green]")
            except Exception as e:
                console.print(
                    f"[yellow]⚠️  Failed to refresh DuckDB secret: {e}[/yellow]"
                )
                console.print(f"[dim]SQL that failed: {debug_sql.strip()}[/dim]")
                # Try without SSLMODE as fallback
                try:
                    console.print(
                        "[blue]🔄 Retrying without SSLMODE parameter...[/blue]"
                    )
                    fallback_sql = create_duckdb_postgresql_secret_sql(
                        host=self._server_config.postgresql_server,
                        port=self._server_config.postgresql_port,
                        database=self._server_config.postgresql_catalogdb,
                        user=self._server_config.postgresql_user,
                        password=self._cached_token,
                    )
                    self._duckdb_connection.execute(fallback_sql).fetchall()
                    console.print(
                        "[green]✅ PostgreSQL secret refreshed in DuckDB (without SSLMODE)[/green]"
                    )
                    console.print(
                        "[yellow]⚠️  SSL may not be enforced - this could cause connection issues with Azure PostgreSQL[/yellow]"
                    )
                except Exception as fallback_e:
                    console.print(f"[red]❌ Fallback also failed: {fallback_e}[/red]")
                    # Don't raise - this is a background operation

        except Exception as e:
            console.print(f"[yellow]⚠️  Failed to refresh DuckDB secret: {e}[/yellow]")
            # Don't raise - this is a background operation

    def _get_token_via_subprocess(self) -> str:
        """
        Fallback method to get token using az CLI subprocess call.

        Returns:
            str: Access token from az CLI

        Raises:
            Exception: If subprocess call fails
        """
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
            token = result.stdout.strip()
            console.print("[green]✅ Azure token obtained via az CLI[/green]")

            # Validate token format
            if not validate_azure_token_format(token):
                console.print(
                    "[yellow]⚠️  Token validation warnings detected - connection may fail[/yellow]"
                )

            # Debug: Log token info (first/last 10 characters for security)
            if len(token) > 20:
                token_preview = f"{token[:10]}...{token[-10:]}"
                console.print(
                    f"[dim]Token preview: {token_preview} (length: {len(token)})[/dim]"
                )

                # Warn about very long tokens
                if len(token) > 2000:
                    console.print(
                        f"[yellow]⚠️  Token is very long ({len(token)} chars) - this might cause issues[/yellow]"
                    )

            # Update cache with subprocess token (no expiration info available)
            old_token = self._cached_token
            self._cached_token = token
            self._token_expires_at = None  # Unknown expiration from CLI

            # Refresh DuckDB secret if token changed
            if (
                old_token != self._cached_token
                and self._duckdb_connection
                and self._server_config
            ):
                self._refresh_duckdb_secret()

            return token

        except subprocess.CalledProcessError as e:
            error_msg = (
                f"az CLI failed with exit code {e.returncode}: {e.stderr.strip()}"
            )
            console.print(f"[red]❌ {error_msg}[/red]")
            raise Exception(error_msg) from e
        except FileNotFoundError as e:
            error_msg = "az CLI not found - please install Azure CLI"
            console.print(f"[red]❌ {error_msg}[/red]")
            raise Exception(error_msg) from e

    def invalidate_cache(self):
        """Invalidate the cached token to force refresh on next request."""
        self._cached_token = None
        self._token_expires_at = None
        console.print("[yellow]🔄 Azure token cache invalidated[/yellow]")

    def schedule_token_refresh(self):
        """
        Schedule automatic token refresh before expiration.
        This could be extended to use background threads or async tasks.
        """
        if not self._token_expires_at:
            return

        # Calculate time until refresh needed (5 minutes before expiration)
        refresh_time = self._token_expires_at - timedelta(minutes=5)
        time_until_refresh = refresh_time - datetime.now()

        if time_until_refresh.total_seconds() > 0:
            console.print(f"[dim]Next token refresh scheduled for {refresh_time}[/dim]")


# Global instance of the credential manager
_azure_credential_manager = AzureCredentialManager()

# DuckDB PostgreSQL Secret Configuration
# IMPORTANT: These are the ONLY supported parameters for DuckDB PostgreSQL secrets
DUCKDB_POSTGRESQL_SECRET_SUPPORTED_PARAMETERS = [
    "TYPE",  # must be 'postgres'
    "HOST",  # PostgreSQL server hostname
    "PORT",  # PostgreSQL server port
    "DATABASE",  # PostgreSQL database name
    "USER",  # PostgreSQL username
    "PASSWORD",  # PostgreSQL password
]
# DO NOT add SSLMODE, SSLCERT, SSLKEY, or any other parameters - they are not supported!


def get_azure_postgresql_token() -> str:
    """
    Get a PostgreSQL access token using Azure authentication.

    This function provides a centralized way to get Azure tokens for PostgreSQL
    across the entire application, with proper caching and error handling.

    Returns:
        str: A valid PostgreSQL access token

    Raises:
        Exception: If token acquisition fails
    """
    return _azure_credential_manager.get_postgresql_token()


def refresh_azure_postgresql_token() -> str:
    """
    Force refresh of the PostgreSQL access token, bypassing cache.

    This is useful when you know the token might be expired or invalid.

    Returns:
        str: A fresh PostgreSQL access token

    Raises:
        Exception: If token acquisition fails
    """
    return _azure_credential_manager.get_postgresql_token(force_refresh=True)


def escape_sql_string(value: str) -> str:
    """
    Escape a string value for safe use in SQL statements.

    Args:
        value: The string to escape

    Returns:
        str: The escaped string safe for SQL insertion
    """
    if not value:
        return ""

    # Escape single quotes by doubling them (SQL standard)
    # This handles usernames with special characters like @, #, etc.
    return value.replace("'", "''")


def create_duckdb_postgresql_secret_sql(
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
    secret_name: str = "postgres_secret",
) -> str:
    """
    Create the SQL statement for a DuckDB PostgreSQL secret.

    CRITICAL: DuckDB only supports the parameters listed in DUCKDB_POSTGRESQL_SECRET_SUPPORTED_PARAMETERS.

    Supported parameters:
    - TYPE: must be 'postgres'
    - HOST: PostgreSQL server hostname
    - PORT: PostgreSQL server port
    - DATABASE: PostgreSQL database name
    - USER: PostgreSQL username
    - PASSWORD: PostgreSQL password

    UNSUPPORTED parameters (will cause errors):
    - SSLMODE, SSLCERT, SSLKEY, SSLROOTCERT, or any other SSL/TLS parameters
    - Any authentication parameters beyond USER/PASSWORD
    - Any connection parameters beyond HOST/PORT/DATABASE

    Args:
        host: PostgreSQL server hostname
        port: PostgreSQL server port
        database: PostgreSQL database name
        user: PostgreSQL username
        password: PostgreSQL password
        secret_name: Name for the DuckDB secret (default: postgres_secret)

    Returns:
        str: Complete CREATE SECRET SQL statement with ONLY the supported parameters
    """
    # Use anonymous secret (like the old working version) to ensure DuckLake can find it
    # Do not escape the password as Azure tokens should not be escaped
    return f"""CREATE SECRET (
        TYPE postgres,
        HOST '{escape_sql_string(host)}',
        PORT {port},
        DATABASE '{escape_sql_string(database or "postgres")}',
        USER '{escape_sql_string(user)}',
        PASSWORD '{password}'
    );"""


def create_duckdb_postgresql_secret_debug_sql(
    host: str, port: int, database: str, user: str, secret_name: str = "postgres_secret"
) -> str:
    """
    Create a debug version of the PostgreSQL secret SQL with password redacted.

    Args:
        host: PostgreSQL server hostname
        port: PostgreSQL server port
        database: PostgreSQL database name
        user: PostgreSQL username
        secret_name: Name for the DuckDB secret (default: postgres_secret)

    Returns:
        str: CREATE SECRET SQL statement with password redacted
    """
    # Use anonymous secret (like the old working version) to ensure DuckLake can find it
    return f"""CREATE SECRET (
        TYPE postgres,
        HOST '{escape_sql_string(host)}',
        PORT {port},
        DATABASE '{escape_sql_string(database or "postgres")}',
        USER '{escape_sql_string(user)}',
        PASSWORD '***REDACTED***'
    );"""


def validate_azure_token_format(token: str) -> bool:
    """
    Validate that an Azure access token has the expected format.

    Args:
        token: The access token to validate

    Returns:
        bool: True if token appears valid, False otherwise
    """
    if not token:
        return False

    # Basic validation - Azure tokens are usually JWT format
    # They should be base64-encoded strings with dots separating parts
    parts = token.split(".")
    if len(parts) != 3:
        console.print(
            f"[yellow]⚠️  Token doesn't appear to be JWT format (has {len(parts)} parts, expected 3)[/yellow]"
        )
        return False

    # Check for reasonable length (Azure tokens are typically 1000+ characters)
    if len(token) < 100:
        console.print(
            f"[yellow]⚠️  Token seems too short ({len(token)} chars) for Azure token[/yellow]"
        )
        return False

    # Check for non-printable characters that might cause issues
    if not all(32 <= ord(c) <= 126 or c in "\t\n\r" for c in token):
        console.print(
            "[yellow]⚠️  Token contains non-printable characters that might cause issues[/yellow]"
        )
        return False

    return True


def get_memory_info():
    """Get basic memory information using system commands."""
    try:
        if PSUTIL_AVAILABLE:
            import psutil

            process = psutil.Process()
            memory_info = process.memory_info()
            return {
                "rss_mb": memory_info.rss / 1024 / 1024,
                "vms_mb": memory_info.vms / 1024 / 1024,
                "percent": process.memory_percent(),
            }
        else:
            # Fallback to basic info
            return {"rss_mb": 0, "vms_mb": 0, "percent": 0}
    except Exception:
        return {"rss_mb": 0, "vms_mb": 0, "percent": 0}


def log_memory_usage(logger, operation: str = ""):
    """Log current memory usage."""
    try:
        memory = get_memory_info()
        if memory["rss_mb"] > 0:
            logger.info(
                f"Memory {operation}: RSS={memory['rss_mb']:.1f}MB, VMS={memory['vms_mb']:.1f}MB, CPU%={memory['percent']:.1f}%"
            )
            console.print(
                f"[dim]Memory {operation}: RSS={memory['rss_mb']:.1f}MB[/dim]"
            )

            # Warning for high memory usage
            if memory["rss_mb"] > 1000:
                console.print(
                    f"[yellow]⚠️  HIGH MEMORY: {memory['rss_mb']:.1f}MB RSS[/yellow]"
                )
                logger.warning(f"High memory usage: {memory['rss_mb']:.1f}MB RSS")
    except Exception as e:
        logger.debug(f"Failed to log memory usage: {e}")


def validate_postgresql_connection(config: ServerConfig) -> bool:
    """Test PostgreSQL connection using provided configuration."""
    logger = get_main_logger()

    if not config.is_postgresql_enabled:
        return True  # Skip test if not configured

    try:
        import psycopg2

        console.print(
            f"[blue]🔍 Testing PostgreSQL connection to {config.postgresql_server}:{config.postgresql_port}...[/blue]"
        )
        logger.info(
            "Testing PostgreSQL connection",
            server=config.postgresql_server,
            port=config.postgresql_port,
        )

        # Handle Azure authentication
        password = config.postgresql_password
        if password == "AZURE":
            try:
                password = get_azure_postgresql_token()
                logger.info("Azure access token obtained for PostgreSQL")
            except Exception as e:
                console.print(f"[red]❌ Failed to get Azure access token: {e}[/red]")
                logger.error("Failed to get Azure access token", error=str(e))
                return False

        # Build connection string
        conn_params = {
            "host": config.postgresql_server,
            "port": config.postgresql_port,
            "user": config.postgresql_user,
            "password": password,
            "connect_timeout": 10,
            "sslmode": "require",  # Required for Azure Database for PostgreSQL
            "sslcert": None,  # Client certificate not needed for token auth
            "sslkey": None,  # Client key not needed for token auth
            "sslrootcert": None,  # Use system CA store
        }

        if config.postgresql_catalogdb:
            conn_params["database"] = config.postgresql_catalogdb

        # Debug: Log connection attempt details (without password)
        debug_params = {k: v for k, v in conn_params.items() if k != "password"}
        debug_params["password"] = (
            "***Azure Token***" if password != config.postgresql_password else "***"
        )
        console.print(f"[dim]Connection parameters: {debug_params}[/dim]")

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

        logger.info(
            "PostgreSQL connection successful",
            server=config.postgresql_server,
            port=config.postgresql_port,
            user=config.postgresql_user,
            database=config.postgresql_catalogdb,
            version=version.split(",")[0],
        )
        return True

    except ImportError:
        console.print(
            "[red]❌ PostgreSQL connection failed: psycopg2-binary not installed[/red]"
        )
        logger.error("PostgreSQL connection failed: psycopg2-binary not installed")
        return False
    except Exception as e:
        error_msg = str(e).lower()
        console.print(f"[red]❌ PostgreSQL connection failed: {e}[/red]")
        console.print(
            f"[dim]   Server: {config.postgresql_server}:{config.postgresql_port}[/dim]"
        )
        console.print(f"[dim]   User: {config.postgresql_user}[/dim]")
        if config.postgresql_catalogdb:
            console.print(f"[dim]   Database: {config.postgresql_catalogdb}[/dim]")

        # Provide specific guidance for common Azure authentication issues
        if (
            "invalid format" in error_msg
            and password == config.postgresql_password
            and config.postgresql_password == "AZURE"
        ):
            console.print(
                "\n[yellow]💡 Azure Token Issues - Troubleshooting Steps:[/yellow]"
            )
            console.print(
                "[yellow]   1. Ensure you're logged in with 'az login'[/yellow]"
            )
            console.print(
                "[yellow]   2. Check your Azure account has access to the PostgreSQL server[/yellow]"
            )
            console.print(
                "[yellow]   3. Try refreshing token with 'az account get-access-token --resource https://ossrdbms-aad.database.windows.net'[/yellow]"
            )
        elif "no encryption" in error_msg or "ssl" in error_msg:
            console.print("\n[yellow]💡 SSL/TLS Issues - Check:[/yellow]")
            console.print(
                "[yellow]   1. Azure Database for PostgreSQL requires SSL connections[/yellow]"
            )
            console.print(
                "[yellow]   2. Firewall rules might be blocking the connection[/yellow]"
            )
        elif "no pg_hba.conf entry" in error_msg:
            console.print("\n[yellow]💡 Access Control Issues - Check:[/yellow]")
            console.print(
                "[yellow]   1. Azure Database firewall rules allow your IP address[/yellow]"
            )
            console.print(
                "[yellow]   2. User exists and has proper permissions[/yellow]"
            )
            console.print(
                "[yellow]   3. Azure AD authentication is properly configured[/yellow]"
            )

        logger.error(
            "PostgreSQL connection failed",
            error=str(e),
            server=config.postgresql_server,
            port=config.postgresql_port,
            user=config.postgresql_user,
            database=config.postgresql_catalogdb,
        )
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
        logger.info(
            "Testing Azure Storage connection",
            account=config.azure_storage_account,
            container=config.azure_storage_container,
        )

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

        logger.info(
            "Azure Storage connection successful",
            account=config.azure_storage_account,
            container=config.azure_storage_container,
            last_modified=str(properties.last_modified),
        )
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
        logger.error(
            "Azure Storage connection failed",
            error=str(e),
            account=config.azure_storage_account,
            container=config.azure_storage_container,
        )
        return False


def validate_backend(value: str) -> str:
    """Validate backend option."""
    if value not in ["duckdb", "sqlite"]:
        raise typer.BadParameter("Backend must be 'duckdb' or 'sqlite'")
    return value


def validate_tls_files(
    cert_file: str | None, key_file: str | None
) -> tuple[str | None, str | None]:
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


def load_init_sql(init_sql: str | None, init_sql_file: str | None) -> str | None:
    """Load initialization SQL from inline command or file."""
    if init_sql_file:
        try:
            return Path(init_sql_file).read_text()
        except FileNotFoundError as e:
            raise typer.BadParameter(f"Init SQL file not found: {init_sql_file}") from e
        except Exception as e:
            raise typer.BadParameter(f"Error reading init SQL file: {e}") from e
    return init_sql


def ensure_postgresql_database(config: ServerConfig) -> bool:
    """Ensure PostgreSQL catalog database exists, creating it if necessary."""
    logger = get_main_logger()

    if not config.is_postgresql_enabled or not config.postgresql_catalogdb:
        return True  # Skip if not configured or no specific database needed

    try:
        console.print(
            f"[blue]🔧 Ensuring PostgreSQL database '{config.postgresql_catalogdb}' exists...[/blue]"
        )
        logger.info(
            "Ensuring PostgreSQL database exists",
            database=config.postgresql_catalogdb,
            server=config.postgresql_server,
        )

        # Handle Azure authentication
        password = config.postgresql_password
        if password == "AZURE":
            try:
                password = get_azure_postgresql_token()
            except Exception as e:
                console.print(f"[red]❌ Failed to get Azure access token: {e}[/red]")
                logger.error(
                    "Failed to get Azure access token for database creation",
                    error=str(e),
                )
                return False

        # Connect to default postgres database to check/create target database
        conn_params = {
            "host": config.postgresql_server,
            "port": config.postgresql_port,
            "user": config.postgresql_user,
            "password": password,
            "database": "postgres",  # Connect to default database
            "connect_timeout": 10,
            "sslmode": "require",  # Required for Azure Database for PostgreSQL
            "sslcert": None,  # Client certificate not needed for token auth
            "sslkey": None,  # Client key not needed for token auth
            "sslrootcert": None,  # Use system CA store
        }

        # Debug: Log connection attempt details (without password)
        debug_params = {k: v for k, v in conn_params.items() if k != "password"}
        debug_params["password"] = (
            "***Azure Token***" if password != config.postgresql_password else "***"
        )
        console.print(
            f"[dim]Database creation connection parameters: {debug_params}[/dim]"
        )

        conn = psycopg2.connect(**conn_params)
        conn.autocommit = True  # Required for CREATE DATABASE
        cursor = conn.cursor()

        # Check if database exists
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s;",
            (config.postgresql_catalogdb,),
        )
        exists = cursor.fetchone()

        if exists:
            console.print(
                f"[green]✅ Database '{config.postgresql_catalogdb}' already exists[/green]"
            )
            logger.info(
                "PostgreSQL database already exists",
                database=config.postgresql_catalogdb,
            )
        else:
            # Create the database with error handling for race conditions
            try:
                cursor.execute(f'CREATE DATABASE "{config.postgresql_catalogdb}";')
                console.print(
                    f"[green]✅ Database '{config.postgresql_catalogdb}' created successfully[/green]"
                )
                logger.info(
                    "PostgreSQL database created", database=config.postgresql_catalogdb
                )
            except psycopg2.errors.DuplicateDatabase:
                # Database was created by another process between our check and creation attempt
                console.print(
                    f"[green]✅ Database '{config.postgresql_catalogdb}' already exists (created concurrently)[/green]"
                )
                logger.info(
                    "PostgreSQL database already exists (created concurrently)",
                    database=config.postgresql_catalogdb,
                )

        cursor.close()
        conn.close()
        return True

    except ImportError:
        console.print(
            "[red]❌ Database creation failed: psycopg2-binary not installed[/red]"
        )
        logger.error("Database creation failed: psycopg2-binary not installed")
        return False
    except Exception as e:
        error_msg = str(e).lower()
        console.print(f"[red]❌ Database creation failed: {e}[/red]")

        # Provide specific guidance for common Azure authentication issues
        if "invalid format" in error_msg and password != config.postgresql_password:
            console.print(
                "\n[yellow]💡 Azure Token Issues - Troubleshooting Steps:[/yellow]"
            )
            console.print(
                "[yellow]   1. Ensure you're logged in with 'az login'[/yellow]"
            )
            console.print(
                "[yellow]   2. Check your Azure account has access to the PostgreSQL server[/yellow]"
            )
            console.print(
                "[yellow]   3. Try refreshing token with 'az account get-access-token --resource https://ossrdbms-aad.database.windows.net'[/yellow]"
            )
        elif "no encryption" in error_msg or "ssl" in error_msg:
            console.print("\n[yellow]💡 SSL/TLS Issues - Check:[/yellow]")
            console.print(
                "[yellow]   1. Azure Database for PostgreSQL requires SSL connections[/yellow]"
            )
            console.print(
                "[yellow]   2. Firewall rules might be blocking the connection[/yellow]"
            )
        elif "no pg_hba.conf entry" in error_msg:
            console.print("\n[yellow]💡 Access Control Issues - Check:[/yellow]")
            console.print(
                "[yellow]   1. Azure Database firewall rules allow your IP address[/yellow]"
            )
            console.print(
                "[yellow]   2. User exists and has proper permissions[/yellow]"
            )
            console.print(
                "[yellow]   3. Azure AD authentication is properly configured[/yellow]"
            )

        logger.error(
            "Database creation failed",
            error=str(e),
            database=config.postgresql_catalogdb,
            server=config.postgresql_server,
        )
        return False


@app.command()
def main(
    # Backend options
    backend: str = typer.Option(
        "duckdb",
        "--backend",
        help="Database backend (duckdb, sqlite)",
        callback=lambda _, value: validate_backend(value) if value else "duckdb",
    ),
    database: str | None = typer.Option(
        None,
        "--database",
        help="Database filename (defaults to in-memory for DuckDB, required for SQLite)",
    ),
    # Network options
    hostname: str | None = typer.Option(
        None,
        "--hostname",
        help="Server hostname to listen on (default: localhost, env: MPZSQL_HOSTNAME)",
    ),
    advertised_hostname: str | None = typer.Option(
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
    username: str | None = typer.Option(
        None,
        "--username",
        help="Authentication username (env: MPZSQL_USERNAME)",
    ),
    password: str | None = typer.Option(
        None,
        "--password",
        help="Authentication password (env: MPZSQL_PASSWORD)",
    ),
    secret_key: str | None = typer.Option(
        None,
        "--secret-key",
        help="JWT secret key (env: SECRET_KEY, random if not provided)",
    ),
    # TLS options
    tls_cert: str | None = typer.Option(
        None,
        "--tls-cert",
        help="TLS certificate file path",
    ),
    tls_key: str | None = typer.Option(
        None,
        "--tls-key",
        help="TLS private key file path",
    ),
    mtls_ca: str | None = typer.Option(
        None,
        "--mtls-ca",
        help="mTLS CA certificate for client verification (env: MPZSQL_MTLS_CA)",
    ),
    # SQL initialization options
    init_sql: str | None = typer.Option(
        None,
        "--init-sql",
        help="SQL commands to run on startup (env: MPZSQL_INIT_SQL)",
    ),
    init_sql_file: str | None = typer.Option(
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
    postgresql_server: str | None = typer.Option(
        None,
        "--postgresql-server",
        help="PostgreSQL server hostname (env: POSTGRESQL_SERVER)",
    ),
    postgresql_port: int | None = typer.Option(
        5432,
        "--postgresql-port",
        help="PostgreSQL server port (env: POSTGRESQL_PORT)",
    ),
    postgresql_user: str | None = typer.Option(
        None,
        "--postgresql-user",
        help="PostgreSQL username (env: POSTGRESQL_USER)",
    ),
    postgresql_password: str | None = typer.Option(
        None,
        "--postgresql-password",
        help="PostgreSQL password (env: POSTGRESQL_PASSWORD)",
    ),
    postgresql_catalogdb: str | None = typer.Option(
        None,
        "--postgresql-catalogdb",
        help="PostgreSQL catalog database name (env: POSTGRESQL_CATALOGDB)",
    ),
    # Azure Storage connection options
    azure_storage_account: str | None = typer.Option(
        None,
        "--azure-storage-account",
        help="Azure Storage account name (env: AZURE_STORAGE_ACCOUNT)",
    ),
    azure_storage_container: str | None = typer.Option(
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
    # Handle version request first, before any initialization
    if version:
        console.print(f"MPZSQL Server version {__version__}")
        raise typer.Exit()

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

    # Log initial memory usage
    log_memory_usage(logger, "SERVER_START")

    # Validate TLS configuration
    tls_cert, tls_key = validate_tls_files(tls_cert, tls_key)

    # Environment variable fallbacks
    hostname = hostname or os.getenv("MPZSQL_HOSTNAME", "localhost")

    # Advertised hostname with Azure Web Apps support
    # Priority: CLI option > MPZSQL_ADVERTISED_HOSTNAME > WEBSITE_HOSTNAME > hostname
    if advertised_hostname is None:
        advertised_hostname = (
            os.getenv("MPZSQL_ADVERTISED_HOSTNAME")
            or os.getenv("WEBSITE_HOSTNAME")  # Azure Web Apps hostname
        )

    # Handle MPZSQL_PORT environment variable with precedence over CLI port
    env_port = os.getenv("MPZSQL_PORT")
    if env_port:
        try:
            port = int(env_port)
            if port < 1 or port > 65535:
                console.print(
                    f"[red]Error:[/red] Invalid port in MPZSQL_PORT environment variable: {env_port} (must be 1-65535)"
                )
                raise typer.Exit(1)
        except ValueError as e:
            console.print(
                f"[red]Error:[/red] Invalid port in MPZSQL_PORT environment variable: {env_port} (must be a number)"
            )
            raise typer.Exit(1) from e

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
        raise typer.Exit(1) from e

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
        raise typer.Exit(1) from e

    # Test external connections if configured
    connection_checks_passed = True

    if config.is_postgresql_enabled:
        # Ensure PostgreSQL database exists before validating connection
        if not ensure_postgresql_database(config) or not validate_postgresql_connection(
            config
        ):
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
            console.print(
                "[blue]🦆 Initializing DuckDB with Azure integration...[/blue]"
            )
            log_memory_usage(logger, "PRE_DUCKDB_AZURE")
            duckdb_con = asyncio.run(initialize_duckdb_with_azure(config))
            log_memory_usage(logger, "POST_DUCKDB_AZURE")
        else:
            console.print("[blue]🦆 Initializing DuckDB in basic mode...[/blue]")
            log_memory_usage(logger, "PRE_DUCKDB_BASIC")
            duckdb_con = initialize_duckdb_basic(config)
            log_memory_usage(logger, "POST_DUCKDB_BASIC")

    # Print startup banner
    print_startup_banner(config)

    # Create and start server
    try:
        console.print("[green]🚀 Starting MPZSQL server...[/green]")
        log_memory_usage(logger, "PRE_SERVER_START")

        server = MPZSQLServer(config, duckdb_con)

        log_memory_usage(logger, "POST_SERVER_INIT")
        console.print("[green]✅ Server initialized successfully[/green]")

        server.start()
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped by user[/yellow]")
        log_memory_usage(logger, "SERVER_SHUTDOWN")
        if duckdb_con:
            duckdb_con.close()
        raise typer.Exit(0) from None
    except Exception as e:
        console.print(f"[red]Server error:[/red] {e}")
        log_memory_usage(logger, "SERVER_ERROR")
        if duckdb_con:
            duckdb_con.close()
        raise typer.Exit(1) from e


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
) -> duckdb.DuckDBPyConnection | None:
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
        async with DefaultAzureCredentialAsync() as credential:
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
                # Ensure the PostgreSQL database exists
                if not ensure_postgresql_database(config):
                    console.print(
                        "[red]❌ Failed to ensure PostgreSQL database exists[/red]"
                    )
                    raise Exception("PostgreSQL database creation failed")

                console.print("\n🔐 Creating PostgreSQL secret...")
                try:
                    # Handle special case for Azure authentication
                    if config.postgresql_password == "AZURE":
                        console.print("Using Azure authentication for PostgreSQL...")
                        pg_password = get_azure_postgresql_token()
                        console.print("✅ Azure access token obtained for PostgreSQL")

                        # Register DuckDB connection with credential manager for automatic refresh
                        _azure_credential_manager.set_duckdb_connection(con, config)
                    else:
                        pg_password = config.postgresql_password

                    pg_secret_sql = create_duckdb_postgresql_secret_sql(
                        host=config.postgresql_server,
                        port=config.postgresql_port,
                        database=config.postgresql_catalogdb,
                        user=config.postgresql_user,
                        password=pg_password,
                    )

                    console.print(
                        f"[dim]Creating DuckDB secret with USER: '{config.postgresql_user}' (length: {len(config.postgresql_user)})[/dim]"
                    )

                    # Check for potential username truncation issues
                    if len(config.postgresql_user) > 63:
                        console.print(
                            f"[yellow]⚠️  Username is very long ({len(config.postgresql_user)} chars) - some PostgreSQL drivers truncate usernames at 63 characters[/yellow]"
                        )

                    # Debug: Show the SQL without the password
                    debug_sql = create_duckdb_postgresql_secret_debug_sql(
                        host=config.postgresql_server,
                        port=config.postgresql_port,
                        database=config.postgresql_catalogdb,
                        user=config.postgresql_user,
                    )
                    console.print(f"[dim]Secret SQL: {debug_sql.strip()}[/dim]")

                    try:
                        result = con.execute(pg_secret_sql).fetchall()
                        console.print("✅ PostgreSQL secret created successfully")
                        console.print(f"   Result: {result}")
                    except Exception as e:
                        console.print(
                            f"[yellow]⚠️  Failed to create PostgreSQL secret with SSLMODE: {e}[/yellow]"
                        )
                        # Try without SSLMODE as fallback
                        console.print(
                            "[blue]🔄 Retrying without SSLMODE parameter...[/blue]"
                        )
                        fallback_sql = create_duckdb_postgresql_secret_sql(
                            host=config.postgresql_server,
                            port=config.postgresql_port,
                            database=config.postgresql_catalogdb,
                            user=config.postgresql_user,
                            password=pg_password,
                        )
                        result = con.execute(fallback_sql).fetchall()
                        console.print(
                            "✅ PostgreSQL secret created successfully (without SSLMODE)"
                        )
                        console.print(f"   Result: {result}")
                        console.print(
                            "[yellow]⚠️  SSL may not be enforced - this could cause connection issues with Azure PostgreSQL[/yellow]"
                        )
                except Exception as e:
                    console.print(f"❌ Failed to create PostgreSQL secret: {e}")
                    raise

            # Attach ducklake catalog if PostgreSQL is configured
            if config.is_postgresql_enabled:
                # Create Azure secret (required for DuckLake storage)
                console.print("\n🔐 Creating Azure secret for DuckLake...")
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

                # Now both secrets are ready, attach DuckLake catalog
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
                    # result = con.execute("USE my_ducklake;").fetchall()
                    # console.print("✅ Switched to ducklake database")
                    # console.print(f"   Result: {result}")

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

                    # Verify Azure container access with CSV read test
                    console.print("\n🔍 Verifying Azure container access...")
                    try:
                        csv_uri = f"abfs://{config.azure_storage_account}.dfs.core.windows.net/{config.azure_storage_container}/dummy.csv"
                        console.print(f"   Testing access to: {csv_uri}")

                        verification_sql = f"""
                        SELECT
                            *
                        FROM
                            '{csv_uri}' AS server
                        LIMIT 5;
                        """

                        result = con.execute(verification_sql).fetchall()
                        console.print("✅ Azure container access verified successfully")
                        console.print(
                            f"   Retrieved {len(result)} sample rows from dummy.csv"
                        )

                    except Exception as e:
                        console.print(
                            f"❌ FATAL: Azure container access verification failed: {e}"
                        )
                        console.print(f"   Could not read from: {csv_uri}")
                        console.print(
                            "   This is a fatal error - DuckLake integration requires Azure access"
                        )
                        console.print(
                            "   🛑 SERVER STARTUP ABORTED - Fix Azure configuration and try again"
                        )
                        # Use a specific exception type to prevent fallback
                        raise SystemExit(
                            f"FATAL: Azure container verification failed: {e}"
                        ) from e

                except Exception as e:
                    console.print(f"❌ Failed to attach ducklake catalog: {e}")
                    # Check if this is our fatal Azure error
                    if "Azure container verification failed" in str(e):
                        # Re-raise as SystemExit to prevent fallback
                        raise SystemExit(str(e)) from e
                    else:
                        # Other errors can still fallback
                        raise

            console.print(
                "\n🎉 DuckDB with Azure integration initialized successfully!"
            )
            return con

    except SystemExit:
        # Don't catch SystemExit - let it propagate to stop the server
        raise
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

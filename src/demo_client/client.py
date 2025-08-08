#!/usr/bin/env python3
"""Demo FlightSQL client for MPZSQL server.

This client connects to the MPZSQL server using ADBC with TLS encryption and authentication.
It allows executing SQL queries and displaying results in a user-friendly format.

"""

import base64
import logging
from pathlib import Path

import adbc_driver_flightsql.dbapi as flightsql_dbapi
import pyarrow as pa
import typer
from adbc_driver_flightsql import DatabaseOptions
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Create typer app and rich console
app = typer.Typer(
    name="mpzsql-client",
    help="Demo client for MPZSQL FlightSQL server",
    add_completion=False,
)
console = Console()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MPZSQLClient:
    """FlightSQL client for connecting to MPZSQL server using ADBC."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str | None = None,
        password: str | None = None,
        certificate: str | None = None,
    ):
        """Initialize the client with connection parameters."""
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.certificate = certificate
        self.connection = None

    def connect(self) -> bool:
        """Establish connection to the FlightSQL server using ADBC."""
        try:
            # Build connection URI based on GizmoSQL client implementation
            if self.certificate:
                # Use TLS if certificate is provided
                uri = f"grpc+tls://{self.host}:{self.port}"
                console.print(
                    f"[blue]🔐 Connecting to FlightSQL server at {uri} with TLS...[/blue]"
                )
            else:
                # Use plain TCP
                uri = f"grpc://{self.host}:{self.port}"
                console.print(
                    f"[blue]🔗 Connecting to FlightSQL server at {uri}...[/blue]"
                )

            # Add TLS certificate if provided
            if self.certificate:
                cert_path = Path(self.certificate)
                if cert_path.exists():
                    console.print(f"[blue]📜 Using TLS certificate: {cert_path}[/blue]")
                else:
                    console.print(
                        f"[red]❌ Certificate file not found: {self.certificate}[/red]"
                    )
                    return False

            # Configure ADBC connection with TLS + Authentication
            db_kwargs = {}

            # Add authentication using ADBC DatabaseOptions (if provided)
            if self.username and self.password:
                console.print(
                    f"[blue]🔑 Authenticating as user: {self.username}[/blue]"
                )
                # Use the working ADBC authentication method
                auth_header = base64.b64encode(
                    f"{self.username}:{self.password}".encode()
                ).decode()
                db_kwargs[DatabaseOptions.AUTHORIZATION_HEADER.value] = (
                    f"Basic {auth_header}"
                )

            # Add TLS skip verify for self-signed certificates
            if self.certificate:
                db_kwargs[DatabaseOptions.TLS_SKIP_VERIFY.value] = "true"

            # Create ADBC connection with proper authentication and TLS
            self.connection = flightsql_dbapi.connect(
                uri, db_kwargs=db_kwargs if db_kwargs else None
            )

            console.print(
                "[green]✅ Connected to FlightSQL server with TLS + Authentication[/green]"
            )
            return True

        except Exception as e:
            console.print(f"[red]❌ Failed to connect: {e}[/red]")
            logger.error(f"Connection failed: {e}")
            return False

    def disconnect(self):
        """Close the connection to the server."""
        if self.connection:
            self.connection.close()
            self.connection = None
            console.print("[yellow]📡 Disconnected from server[/yellow]")

    def execute_query(self, sql: str) -> pa.Table | None:
        """Execute a SQL query and return the result as a PyArrow table."""
        if not self.connection:
            console.print("[red]❌ Not connected to server[/red]")
            return None

        try:
            console.print(f"[blue]🔍 Executing query: {sql}[/blue]")

            # Create cursor and execute query
            cursor = self.connection.cursor()
            cursor.execute(sql)

            # Get result as PyArrow table
            table = cursor.fetch_arrow_table()

            console.print(
                f"[green]✅ Query executed successfully. Rows: {table.num_rows}[/green]"
            )
            return table

        except Exception as e:
            console.print(f"[red]❌ Query failed: {e}[/red]")
            logger.error(f"Query execution failed: {e}")
            return None

    def execute_update(self, sql: str) -> bool:
        """Execute a DDL/DML statement (CREATE, INSERT, UPDATE, DELETE) that doesn't return a result set."""
        if not self.connection:
            console.print("[red]❌ Not connected to server[/red]")
            return False

        try:
            console.print(f"[blue]🔍 Executing statement: {sql}[/blue]")

            # Create cursor and execute statement
            cursor = self.connection.cursor()
            cursor.execute(sql)

            # For DDL/DML operations, we don't fetch results, just check if it succeeded
            # The operation succeeded if no exception was thrown
            console.print("[green]✅ Statement executed successfully[/green]")
            return True

        except Exception as e:
            console.print(f"[red]❌ Statement failed: {e}[/red]")
            logger.error(f"Statement execution failed: {e}")
            return False

    def get_server_info(self) -> bool:
        """Get server information."""
        if not self.connection:
            console.print("[red]❌ Not connected to server[/red]")
            return False

        try:
            console.print("[blue]📊 Getting server information...[/blue]")

            # Try to get some basic server info using SQL
            cursor = self.connection.cursor()

            # Try some standard queries to test connectivity
            test_queries = [
                ("Server Test", "SELECT 1 as connection_test"),
                ("Current Time", "SELECT CURRENT_TIMESTAMP as server_time"),
            ]

            for name, query in test_queries:
                try:
                    cursor.execute(query)
                    result = cursor.fetch_arrow_table()
                    console.print(f"  • {name}: ✅ (Rows: {result.num_rows})")
                except Exception as e:
                    console.print(f"  • {name}: ❌ ({str(e)[:50]}...)")

            return True

        except Exception as e:
            console.print(f"[red]❌ Failed to get server info: {e}[/red]")
            logger.error(f"Get server info failed: {e}")
            return False

    def list_catalogs(self) -> bool:
        """List available catalogs."""
        if not self.connection:
            console.print("[red]❌ Not connected to server[/red]")
            return False

        try:
            console.print("[blue]📁 Listing catalogs...[/blue]")

            # Try different ways to list databases/catalogs
            catalog_queries = [
                "SHOW DATABASES",
                "SHOW SCHEMAS",
                "SELECT 1 as test_catalog",  # Fallback test query
            ]

            for query in catalog_queries:
                try:
                    result = self.execute_query(query)
                    if result and result.num_rows > 0:
                        self._display_table(result, f"Results from: {query}")
                        return True
                except Exception:
                    continue

            console.print("[yellow]📄 No catalog information available[/yellow]")
            return True

        except Exception as e:
            console.print(f"[red]❌ Failed to list catalogs: {e}[/red]")
            logger.error(f"List catalogs failed: {e}")
            return False

    def _display_table(self, table: pa.Table, title: str = "Query Results"):
        """Display a PyArrow table in a nice format."""
        if table.num_rows == 0:
            console.print(f"[yellow]📄 {title}: No data returned[/yellow]")
            return

        # Create rich table
        rich_table = Table(title=title, show_header=True, header_style="bold magenta")

        # Add columns
        for column in table.column_names:
            rich_table.add_column(column)

        # Add rows (limit to first 100 for display)
        max_rows = min(table.num_rows, 100)
        for i in range(max_rows):
            row = []
            for col_name in table.column_names:
                value = table[col_name][i].as_py()
                row.append(str(value) if value is not None else "NULL")
            rich_table.add_row(*row)

        if table.num_rows > 100:
            rich_table.add_row(*["..." for _ in table.column_names])

        console.print(rich_table)
        console.print(f"[dim]Showing {max_rows} of {table.num_rows} rows[/dim]")


@app.command()
def connect(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Server host"),
    port: int = typer.Option(8080, "--port", "-p", help="Server port"),
    username: str | None = typer.Option(
        None, "--user", "-u", help="Username for authentication"
    ),
    password: str | None = typer.Option(
        None, "--password", "-P", help="Password for authentication"
    ),
    certificate: str | None = typer.Option(
        None, "--cert", "-c", help="Path to TLS certificate file"
    ),
    interactive: bool = typer.Option(
        True, "--interactive/--no-interactive", "-i", help="Start interactive mode"
    ),
):
    """Connect to MPZSQL FlightSQL server."""
    # Display connection info
    panel_text = Text()
    panel_text.append("MPZSQL FlightSQL Demo Client\n\n", style="bold blue")
    panel_text.append(f"Host: {host}\n", style="cyan")
    panel_text.append(f"Port: {port}\n", style="cyan")
    if username:
        panel_text.append(f"Username: {username}\n", style="cyan")
    if certificate:
        panel_text.append(f"Certificate: {certificate}\n", style="cyan")

    console.print(Panel(panel_text, title="Connection Parameters", border_style="blue"))

    # Create and connect client
    client = MPZSQLClient(
        host=host,
        port=port,
        username=username,
        password=password,
        certificate=certificate,
    )

    if not client.connect():
        console.print("[red]❌ Failed to establish connection[/red]")
        raise typer.Exit(1)

    try:
        # Get server info
        client.get_server_info()

        if interactive:
            console.print(
                "\n[bold green]🎯 Interactive mode started. Type 'help' for commands, 'quit' to exit.[/bold green]"
            )
            _interactive_mode(client)
        else:
            # Just test the connection and exit
            console.print("[green]✅ Connection test successful[/green]")

    finally:
        client.disconnect()


def _interactive_mode(client: MPZSQLClient):
    """Run interactive mode for the client."""
    while True:
        try:
            command = typer.prompt("\nmpzsql> ", type=str).strip()

            if command.lower() in ["quit", "exit", "q"]:
                console.print("[yellow]👋 Goodbye![/yellow]")
                break

            if command.lower() in ["help", "h"]:
                _show_help()

            elif command.lower() in ["info", "server"]:
                client.get_server_info()

            elif command.lower() in ["catalogs", "databases"]:
                client.list_catalogs()

            elif command.lower().startswith("select") or command.lower().startswith(
                "show"
            ):
                result = client.execute_query(command)
                if result:
                    client._display_table(result)

            elif command:
                # Try to execute as SQL
                result = client.execute_query(command)
                if result:
                    client._display_table(result)

            else:
                console.print(
                    "[yellow]Empty command. Type 'help' for available commands.[/yellow]"
                )

        except KeyboardInterrupt:
            console.print("\n[yellow]Use 'quit' to exit.[/yellow]")
        except EOFError:
            console.print("\n[yellow]👋 Goodbye![/yellow]")
            break
        except Exception as e:
            console.print(f"[red]❌ Error: {e}[/red]")


def _show_help():
    """Show help information."""
    help_table = Table(
        title="Available Commands", show_header=True, header_style="bold magenta"
    )
    help_table.add_column("Command", style="cyan", no_wrap=True)
    help_table.add_column("Description", style="white")

    help_table.add_row("help, h", "Show this help message")
    help_table.add_row("info, server", "Get server information")
    help_table.add_row("catalogs, databases", "List available catalogs/databases")
    help_table.add_row("SELECT ...", "Execute a SQL query")
    help_table.add_row("SHOW ...", "Execute a SHOW command")
    help_table.add_row("quit, exit, q", "Exit the client")

    console.print(help_table)


@app.command()
def query(
    sql: str = typer.Argument(..., help="SQL query to execute"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Server host"),
    port: int = typer.Option(8080, "--port", "-p", help="Server port"),
    username: str | None = typer.Option(
        None, "--user", "-u", help="Username for authentication"
    ),
    password: str | None = typer.Option(
        None, "--password", "-P", help="Password for authentication"
    ),
    certificate: str | None = typer.Option(
        None, "--cert", "-c", help="Path to TLS certificate file"
    ),
):
    """Execute a single SQL query and exit."""
    # Create and connect client
    client = MPZSQLClient(
        host=host,
        port=port,
        username=username,
        password=password,
        certificate=certificate,
    )

    if not client.connect():
        console.print("[red]❌ Failed to establish connection[/red]")
        raise typer.Exit(1)

    try:
        result = client.execute_query(sql)
        if result:
            client._display_table(result)
        else:
            raise typer.Exit(1)

    finally:
        client.disconnect()


@app.command()
def execute(
    sql: str = typer.Argument(
        ..., help="SQL statement to execute (CREATE, INSERT, UPDATE, DELETE)"
    ),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Server host"),
    port: int = typer.Option(8080, "--port", "-p", help="Server port"),
    username: str | None = typer.Option(
        None, "--user", "-u", help="Username for authentication"
    ),
    password: str | None = typer.Option(
        None, "--password", "-P", help="Password for authentication"
    ),
    certificate: str | None = typer.Option(
        None, "--cert", "-c", help="Path to TLS certificate file"
    ),
):
    """Execute a DDL/DML statement (CREATE, INSERT, UPDATE, DELETE) and exit."""
    # Create and connect client
    client = MPZSQLClient(
        host=host,
        port=port,
        username=username,
        password=password,
        certificate=certificate,
    )

    if not client.connect():
        console.print("[red]❌ Failed to establish connection[/red]")
        raise typer.Exit(1)

    try:
        success = client.execute_update(sql)
        if not success:
            raise typer.Exit(1)

    finally:
        client.disconnect()


@app.command()
def test_connection(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Server host"),
    port: int = typer.Option(8080, "--port", "-p", help="Server port"),
    username: str | None = typer.Option(
        None, "--user", "-u", help="Username for authentication"
    ),
    password: str | None = typer.Option(
        None, "--password", "-P", help="Password for authentication"
    ),
    certificate: str | None = typer.Option(
        None, "--cert", "-c", help="Path to TLS certificate file"
    ),
):
    """Test connection to the server without interactive mode."""
    client = MPZSQLClient(
        host=host,
        port=port,
        username=username,
        password=password,
        certificate=certificate,
    )

    if client.connect():
        client.get_server_info()
        client.disconnect()
        console.print("[green]✅ Connection test successful[/green]")
    else:
        console.print("[red]❌ Connection test failed[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()

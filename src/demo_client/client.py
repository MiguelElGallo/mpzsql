#!/usr/bin/env python3
"""
Arrow Flight Client with TLS and Authentication Support

This client connects to an Arrow Flight server using:
- ADBC FlightSQL driver for reliable connections
- TLS encryption with certificates
- Basic authentication with username/password
- Support for various Flight SQL operations

Configuration is loaded from the environment variables set by test_postgresql_config.sh
"""

import argparse
import base64
import logging
import os
import sys
from pathlib import Path

import pandas as pd
from adbc_driver_flightsql import DatabaseOptions
from adbc_driver_flightsql import dbapi as flightsql_dbapi


class ServerConfig:
    """Configuration holder for server connection details."""

    def __init__(self):
        self.host: str = "127.0.0.1"
        self.port: int = 8080
        self.username: str = ""
        self.password: str = ""
        self.tls_cert_path: str = ""
        self.tls_key_path: str = ""


def read_server_config() -> ServerConfig:
    """
    Read server configuration from environment variables.

    Expected environment variables (set by test_postgresql_config.sh):
    - MPZSQL_USERNAME: Username for authentication
    - MPZSQL_PASSWORD: Password for authentication
    - MPZSQL_TLS_CERT_PATH: Path to TLS certificate file
    - MPZSQL_TLS_KEY_PATH: Path to TLS private key file

    Returns:
        ServerConfig: Configuration object with connection details

    Raises:
        ValueError: If required environment variables are missing or files don't exist
    """
    config = ServerConfig()

    # Get authentication credentials
    config.username = os.getenv("MPZSQL_USERNAME", "")
    config.password = os.getenv("MPZSQL_PASSWORD", "")

    # Get TLS certificate paths
    config.tls_cert_path = os.getenv("MPZSQL_TLS_CERT_PATH", "")
    config.tls_key_path = os.getenv("MPZSQL_TLS_KEY_PATH", "")

    # Validate required configuration
    if not config.username:
        raise ValueError("MPZSQL_USERNAME environment variable is required")
    if not config.password:
        raise ValueError("MPZSQL_PASSWORD environment variable is required")
    if not config.tls_cert_path:
        raise ValueError("MPZSQL_TLS_CERT_PATH environment variable is required")
    if not config.tls_key_path:
        raise ValueError("MPZSQL_TLS_KEY_PATH environment variable is required")

    # Validate certificate files exist
    if not Path(config.tls_cert_path).exists():
        raise ValueError(f"TLS certificate file not found: {config.tls_cert_path}")
    if not Path(config.tls_key_path).exists():
        raise ValueError(f"TLS private key file not found: {config.tls_key_path}")

    logging.info("Configuration loaded:")
    logging.info(f"  Server: {config.host}:{config.port}")
    logging.info(f"  Username: {config.username}")
    logging.info(f"  TLS Certificate: {config.tls_cert_path}")
    logging.info(f"  TLS Key: {config.tls_key_path}")

    return config


class MPZSQLFlightClient:
    """
    Arrow Flight client for connecting to MPZSQL server using ADBC with TLS and authentication.
    """

    def __init__(self, config: ServerConfig):
        """Initialize client with server configuration."""
        self.config = config
        self.connection = None
        self.cursor = None

    def connect(self) -> None:
        """Establish secure connection with TLS and authentication using ADBC."""
        try:
            # Create connection URL for TLS
            connection_url = f"grpc+tls://{self.config.host}:{self.config.port}"

            logging.info(
                f"Connecting to {connection_url} with TLS and authentication..."
            )

            # Configure ADBC connection parameters
            db_kwargs = {}

            # Add authentication using Base64 Basic authentication
            if self.config.username and self.config.password:
                auth_header = base64.b64encode(
                    f"{self.config.username}:{self.config.password}".encode()
                ).decode()
                db_kwargs[DatabaseOptions.AUTHORIZATION_HEADER.value] = (
                    f"Basic {auth_header}"
                )
                logging.info(f"Added authentication for user: {self.config.username}")

            # Skip TLS verification for self-signed certificates
            db_kwargs[DatabaseOptions.TLS_SKIP_VERIFY.value] = "true"

            # Create ADBC connection
            self.connection = flightsql_dbapi.connect(
                uri=connection_url, db_kwargs=db_kwargs
            )

            # Create cursor for operations
            self.cursor = self.connection.cursor()

            logging.info("Client connected and authenticated successfully using ADBC")

        except Exception as e:
            logging.error(f"Failed to connect: {e}")
            raise

    def disconnect(self) -> None:
        """Close the connection to the server."""
        try:
            if self.cursor:
                self.cursor.close()
                self.cursor = None
            if self.connection:
                self.connection.close()
                self.connection = None
            logging.info("Disconnected from server")
        except Exception as e:
            logging.warning(f"Error during disconnect: {e}")

    def execute_query(self, sql: str, limit: int = 10) -> None:
        """
        Execute a SQL query and display results.

        Args:
            sql: SQL query to execute
            limit: Maximum number of rows to display
        """
        if not self.cursor:
            raise RuntimeError("Not connected - call connect() first")

        try:
            print(f"Executing query: {sql}")
            print("-" * 50)

            # Execute the query
            self.cursor.execute(sql)

            # Get column names
            columns = (
                [desc[0] for desc in self.cursor.description]
                if self.cursor.description
                else []
            )

            if not columns:
                print("Query executed successfully (no results returned)")
                return

            # Fetch results
            rows = self.cursor.fetchall()

            if not rows:
                print("No rows returned")
                return

            print(f"Query returned {len(rows)} rows")

            # Convert to pandas DataFrame for nice display
            df = pd.DataFrame(rows, columns=columns)

            print("\nSchema:")
            for col in df.columns:
                dtype = str(df[col].dtype)
                print(f"  {col}: {dtype}")

            print(f"\nFirst {min(limit, len(df))} rows:")
            print(df.head(limit).to_string(index=False))

        except Exception as e:
            logging.error(f"Failed to execute query: {e}")
            raise

    def get_server_info(self) -> None:
        """Get basic server information."""
        if not self.cursor:
            raise RuntimeError("Not connected - call connect() first")

        try:
            print("Server Information:")
            print("-" * 50)

            # Try some basic queries to test the connection
            test_queries = [
                ("Server Version", "SELECT version() as version"),
                ("Current Time", "SELECT CURRENT_TIMESTAMP as current_time"),
                ("Test Query", "SELECT 1 as test_value, 'Hello MPZSQL' as message"),
            ]

            for name, query in test_queries:
                try:
                    self.cursor.execute(query)
                    result = self.cursor.fetchone()
                    if result:
                        print(f"{name}: {result[0]}")
                    else:
                        print(f"{name}: No result")
                except Exception as e:
                    print(f"{name}: Error - {e}")

        except Exception as e:
            logging.error(f"Failed to get server info: {e}")
            raise

    def list_tables(self) -> None:
        """List available tables."""
        if not self.cursor:
            raise RuntimeError("Not connected - call connect() first")

        try:
            print("Available Tables:")
            print("-" * 50)

            # Try different approaches to list tables
            table_queries = [
                "SHOW TABLES",
                "SELECT table_name FROM information_schema.tables WHERE table_type = 'BASE TABLE'",
                "PRAGMA show_tables",  # DuckDB specific
            ]

            success = False
            for query in table_queries:
                try:
                    self.cursor.execute(query)
                    rows = self.cursor.fetchall()

                    if rows:
                        print(f"Tables found using: {query}")
                        for i, row in enumerate(rows, 1):
                            table_name = row[0] if row else "Unknown"
                            print(f"  {i}. {table_name}")
                        success = True
                        break

                except Exception as e:
                    logging.debug(f"Query '{query}' failed: {e}")
                    continue

            if not success:
                print("No tables found or unable to list tables")
                print("Try executing a custom query with --query option")

        except Exception as e:
            logging.error(f"Failed to list tables: {e}")
            raise

    def show_databases(self) -> None:
        """Show available databases."""
        if not self.cursor:
            raise RuntimeError("Not connected - call connect() first")

        try:
            print("Available Databases:")
            print("-" * 50)

            database_queries = [
                "SHOW DATABASES",
                "PRAGMA show_databases",  # DuckDB specific
                "SELECT datname FROM pg_database",  # PostgreSQL style
            ]

            success = False
            for query in database_queries:
                try:
                    self.cursor.execute(query)
                    rows = self.cursor.fetchall()

                    if rows:
                        print(f"Databases found using: {query}")
                        for i, row in enumerate(rows, 1):
                            db_name = row[0] if row else "Unknown"
                            print(f"  {i}. {db_name}")
                        success = True
                        break

                except Exception as e:
                    logging.debug(f"Query '{query}' failed: {e}")
                    continue

            if not success:
                print("No databases found or unable to list databases")

        except Exception as e:
            logging.error(f"Failed to show databases: {e}")
            raise


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Arrow Flight Client for MPZSQL Server with TLS and Authentication (ADBC)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --info                           # Show server information
  %(prog)s --list-tables                    # List available tables
  %(prog)s --list-databases                 # List available databases
  %(prog)s --query "SHOW TABLES"            # Execute a SQL query
  %(prog)s --query "SELECT * FROM my_table LIMIT 5"  # Query data
  
Environment variables (set by test_postgresql_config.sh):
  MPZSQL_USERNAME        - Username for authentication
  MPZSQL_PASSWORD        - Password for authentication  
  MPZSQL_TLS_CERT_PATH   - Path to TLS certificate file
  MPZSQL_TLS_KEY_PATH    - Path to TLS private key file
        """,
    )

    # Connection options
    parser.add_argument(
        "--host", default="127.0.0.1", help="Server hostname (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Server port (default: 8080)"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    # Operations
    parser.add_argument("--info", action="store_true", help="Show server information")
    parser.add_argument(
        "--list-tables", action="store_true", help="List available tables"
    )
    parser.add_argument(
        "--list-databases", action="store_true", help="List available databases"
    )
    parser.add_argument("--query", metavar="SQL", help="Execute SQL query")
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Limit rows in query results (default: 10)",
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.INFO if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    try:
        # Load configuration
        config = read_server_config()
        config.host = args.host
        config.port = args.port

        # Create and connect client
        client = MPZSQLFlightClient(config)
        client.connect()

        # Execute requested operations
        if args.info:
            client.get_server_info()
        elif args.list_tables:
            client.list_tables()
        elif args.list_databases:
            client.show_databases()
        elif args.query:
            client.execute_query(args.query, args.limit)
        else:
            # Default: show basic server info
            print("Connected successfully to MPZSQL Flight Server!")
            print(f"Server: {config.host}:{config.port}")
            print(f"Username: {config.username}")
            print("\nUse --help to see available operations")
            print("\nTesting connection...")
            client.get_server_info()

    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        if args.verbose:
            logging.exception("Operation failed")
        else:
            print(f"Error: {e}")
        sys.exit(1)
    finally:
        # Clean up
        try:
            if "client" in locals():
                client.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    main()

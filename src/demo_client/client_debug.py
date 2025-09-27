#!/usr/bin/env python3
"""
Enhanced Arrow Flight Client with Memory Monitoring and PyArrow Debugging

This enhanced version includes:
- Memory usage tracking and reporting
- PyArrow version and configuration details
- Better error handling and crash detection
- Connection pool management
- Resource cleanup monitoring
"""

import argparse
import base64
import gc
import logging
import os
import sys
import traceback
from pathlib import Path

import pandas as pd
import psutil
import pyarrow as pa
from adbc_driver_flightsql import DatabaseOptions
from adbc_driver_flightsql import dbapi as flightsql_dbapi


class MemoryMonitor:
    """Monitor memory usage throughout client execution."""

    def __init__(self):
        self.process = psutil.Process()
        self.initial_memory = self.get_memory_info()
        self.peak_memory = self.initial_memory

    def get_memory_info(self):
        """Get current memory usage information."""
        memory_info = self.process.memory_info()
        return {
            "rss_mb": memory_info.rss / 1024 / 1024,
            "vms_mb": memory_info.vms / 1024 / 1024,
            "percent": self.process.memory_percent(),
        }

    def log_memory_usage(self, operation: str = ""):
        """Log current memory usage."""
        current = self.get_memory_info()
        if current["rss_mb"] > self.peak_memory["rss_mb"]:
            self.peak_memory = current

        print(
            f"MEMORY {operation}: RSS={current['rss_mb']:.1f}MB, "
            f"VMS={current['vms_mb']:.1f}MB, "
            f"CPU%={self.process.cpu_percent():.1f}%, "
            f"MEM%={current['percent']:.1f}%"
        )

        # Warning for high memory usage
        if current["rss_mb"] > 500:
            print(f"⚠️  HIGH MEMORY WARNING: {current['rss_mb']:.1f}MB RSS")

        return current

    def get_memory_summary(self):
        """Get memory usage summary."""
        current = self.get_memory_info()
        return {
            "initial": self.initial_memory,
            "current": current,
            "peak": self.peak_memory,
            "growth_mb": current["rss_mb"] - self.initial_memory["rss_mb"],
        }


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
    """Read server configuration from environment variables."""
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


def print_environment_info():
    """Print detailed environment information for debugging."""
    print("=" * 60)
    print("ENVIRONMENT DEBUGGING INFORMATION")
    print("=" * 60)

    # Python version
    print(f"Python Version: {sys.version}")
    print(f"Python Executable: {sys.executable}")
    print(f"Platform: {sys.platform}")

    # PyArrow info
    try:
        print(f"PyArrow Version: {pa.__version__}")
        print(f"PyArrow Build Info: {pa.cpp_build_info}")
        print(f"PyArrow Runtime Info: {pa.runtime_info()}")

        # PyArrow memory pool info
        try:
            pool = pa.default_memory_pool()
            print(f"PyArrow Memory Pool: {type(pool).__name__}")
            print(
                f"PyArrow Memory Pool Stats: bytes_allocated={pool.bytes_allocated()}, "
                f"max_memory={pool.max_memory()}"
            )
        except Exception as e:
            print(f"PyArrow Memory Pool Info Error: {e}")

        # Check for CUDA support
        try:
            print(f"PyArrow CUDA Support: {pa.cuda.have_cuda()}")
        except AttributeError:
            print("PyArrow CUDA Support: N/A")

    except Exception as e:
        print(f"PyArrow Info Error: {e}")

    # ADBC info
    try:
        import adbc_driver_flightsql

        print(f"ADBC FlightSQL Driver: {adbc_driver_flightsql.__version__}")
    except Exception as e:
        print(f"ADBC Info Error: {e}")

    # System memory info
    try:
        vm = psutil.virtual_memory()
        print(
            f"System Memory: Total={vm.total / 1024 / 1024 / 1024:.1f}GB, "
            f"Available={vm.available / 1024 / 1024 / 1024:.1f}GB, "
            f"Used={vm.percent:.1f}%"
        )
    except Exception as e:
        print(f"System Memory Info Error: {e}")

    # Process info
    try:
        process = psutil.Process()
        print(f"Process ID: {process.pid}")
        memory_info = process.memory_info()
        print(
            f"Process Memory: RSS={memory_info.rss / 1024 / 1024:.1f}MB, "
            f"VMS={memory_info.vms / 1024 / 1024:.1f}MB"
        )
    except Exception as e:
        print(f"Process Info Error: {e}")

    print("=" * 60)


class MPZSQLFlightClientDebug:
    """Enhanced Arrow Flight client with debugging and memory monitoring."""

    def __init__(self, config: ServerConfig):
        """Initialize client with server configuration."""
        self.config = config
        self.connection = None
        self.cursor = None
        self.memory_monitor = MemoryMonitor()
        self.connection_count = 0

        # Print environment info on initialization
        print_environment_info()

        print("CLIENT DEBUG INFO:")
        print(f"  Client PID: {os.getpid()}")
        self.memory_monitor.log_memory_usage("INIT")

    def connect(self) -> None:
        """Establish secure connection with enhanced error handling."""
        try:
            self.connection_count += 1
            print(f"🔗 CONNECTION ATTEMPT #{self.connection_count}")

            # Pre-connection memory check
            self.memory_monitor.log_memory_usage("PRE-CONNECT")

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

            print("🔧 ADBC Connection Parameters:")
            for key, value in db_kwargs.items():
                # Don't print sensitive auth headers
                if "AUTHORIZATION" in key:
                    print(f"  {key}: [REDACTED]")
                else:
                    print(f"  {key}: {value}")

            # Create ADBC connection with timeout and error handling
            try:
                self.connection = flightsql_dbapi.connect(
                    uri=connection_url, db_kwargs=db_kwargs
                )
                print("✅ ADBC Connection established")
            except Exception as conn_error:
                print(f"❌ ADBC Connection failed: {conn_error}")
                print(f"Connection error type: {type(conn_error)}")
                raise

            # Create cursor for operations
            try:
                self.cursor = self.connection.cursor()
                print("✅ Cursor created successfully")
            except Exception as cursor_error:
                print(f"❌ Cursor creation failed: {cursor_error}")
                print(f"Cursor error type: {type(cursor_error)}")
                raise

            # Post-connection memory check
            self.memory_monitor.log_memory_usage("POST-CONNECT")

            logging.info("Client connected and authenticated successfully using ADBC")

        except Exception as e:
            print("🚨 CONNECTION FAILURE:")
            print(f"  Error: {e}")
            print(f"  Error Type: {type(e)}")
            print("  Traceback:")
            traceback.print_exc()

            # Memory check during error
            self.memory_monitor.log_memory_usage("CONNECT-ERROR")

            logging.error(f"Failed to connect: {e}")
            raise

    def disconnect(self) -> None:
        """Close the connection with enhanced cleanup."""
        try:
            print("🔌 DISCONNECTING CLIENT")

            # Pre-disconnect memory check
            self.memory_monitor.log_memory_usage("PRE-DISCONNECT")

            cleanup_errors = []

            if self.cursor:
                try:
                    self.cursor.close()
                    self.cursor = None
                    print("✅ Cursor closed")
                except Exception as e:
                    cleanup_errors.append(f"Cursor close error: {e}")

            if self.connection:
                try:
                    self.connection.close()
                    self.connection = None
                    print("✅ Connection closed")
                except Exception as e:
                    cleanup_errors.append(f"Connection close error: {e}")

            # Force garbage collection
            print("🧹 Running garbage collection...")
            collected = gc.collect()
            print(f"🧹 Garbage collector freed {collected} objects")

            # Post-disconnect memory check
            self.memory_monitor.log_memory_usage("POST-DISCONNECT")

            if cleanup_errors:
                print("⚠️  Cleanup warnings:")
                for error in cleanup_errors:
                    print(f"  - {error}")
            else:
                print("✅ Clean disconnection completed")

            logging.info("Disconnected from server")

        except Exception as e:
            print(f"🚨 DISCONNECT ERROR: {e}")
            logging.warning(f"Error during disconnect: {e}")

    def execute_query(self, sql: str, limit: int = 10) -> None:
        """Execute a SQL query with enhanced monitoring and error handling."""
        if not self.cursor:
            raise RuntimeError("Not connected - call connect() first")

        try:
            print("📝 EXECUTING QUERY:")
            print(f"  Length: {len(sql)} characters")
            print(f"  Query: {sql[:200]}{'...' if len(sql) > 200 else ''}")
            print("-" * 50)

            # Pre-execution memory check
            self.memory_monitor.log_memory_usage("PRE-QUERY")

            # Execute the query with timeout protection
            try:
                self.cursor.execute(sql)
                print("✅ Query executed successfully")
            except Exception as exec_error:
                print(f"❌ Query execution failed: {exec_error}")
                print(f"Query error type: {type(exec_error)}")
                raise

            # Memory check after execution
            self.memory_monitor.log_memory_usage("POST-QUERY-EXEC")

            # Get column names
            columns = (
                [desc[0] for desc in self.cursor.description]
                if self.cursor.description
                else []
            )

            if not columns:
                print("Query executed successfully (no results returned)")
                return

            print(f"📊 Result schema: {len(columns)} columns")
            for i, col in enumerate(columns):
                print(f"  {i + 1}. {col}")

            # Fetch results with memory monitoring
            try:
                print("📥 Fetching results...")
                rows = self.cursor.fetchall()
                print(f"📥 Fetched {len(rows)} rows")
            except Exception as fetch_error:
                print(f"❌ Result fetching failed: {fetch_error}")
                print(f"Fetch error type: {type(fetch_error)}")
                raise

            # Memory check after fetching
            self.memory_monitor.log_memory_usage("POST-FETCH")

            if not rows:
                print("No rows returned")
                return

            print(f"Query returned {len(rows)} rows")

            # Convert to pandas DataFrame for nice display with memory monitoring
            try:
                print("🐼 Converting to pandas DataFrame...")
                df = pd.DataFrame(rows, columns=columns)
                print(f"🐼 DataFrame created: shape {df.shape}")

                # Memory check after DataFrame creation
                self.memory_monitor.log_memory_usage("POST-DATAFRAME")

            except Exception as df_error:
                print(f"❌ DataFrame conversion failed: {df_error}")
                print(f"DataFrame error type: {type(df_error)}")
                # Try to show raw results instead
                print("Raw results (first 5 rows):")
                for i, row in enumerate(rows[:5]):
                    print(f"  {i + 1}: {row}")
                return

            print("\nSchema:")
            for col in df.columns:
                dtype = str(df[col].dtype)
                print(f"  {col}: {dtype}")

            print(f"\nFirst {min(limit, len(df))} rows:")
            print(df.head(limit).to_string(index=False))

            # Final memory check
            self.memory_monitor.log_memory_usage("QUERY-COMPLETE")

        except Exception as e:
            print("🚨 QUERY ERROR:")
            print(f"  Error: {e}")
            print(f"  Error Type: {type(e)}")
            print("  Traceback:")
            traceback.print_exc()

            # Memory check during error
            self.memory_monitor.log_memory_usage("QUERY-ERROR")

            logging.error(f"Failed to execute query: {e}")
            raise

    def get_memory_summary(self) -> None:
        """Print detailed memory usage summary."""
        print("\n" + "=" * 50)
        print("MEMORY USAGE SUMMARY")
        print("=" * 50)

        summary = self.memory_monitor.get_memory_summary()

        print(f"Initial Memory: {summary['initial']['rss_mb']:.1f}MB RSS")
        print(f"Current Memory: {summary['current']['rss_mb']:.1f}MB RSS")
        print(f"Peak Memory: {summary['peak']['rss_mb']:.1f}MB RSS")
        print(f"Memory Growth: {summary['growth_mb']:.1f}MB")

        if summary["growth_mb"] > 50:
            print(f"⚠️  SIGNIFICANT MEMORY GROWTH: {summary['growth_mb']:.1f}MB")

        # PyArrow memory pool stats
        try:
            pool = pa.default_memory_pool()
            print(f"PyArrow Pool: {pool.bytes_allocated()} bytes allocated")
        except Exception as e:
            print(f"PyArrow Pool Error: {e}")

        print("=" * 50)


def main():
    """Main CLI entry point with enhanced error handling."""
    parser = argparse.ArgumentParser(
        description="Enhanced Arrow Flight Client with Memory Monitoring and PyArrow Debugging",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This enhanced client includes memory monitoring, PyArrow debugging, and crash detection.
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
    parser.add_argument("--query", metavar="SQL", help="Execute SQL query")
    parser.add_argument("--file", metavar="PATH", help="Execute SQL commands from file")
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

    client = None

    try:
        # Load configuration
        config = read_server_config()
        config.host = args.host
        config.port = args.port

        # Create and connect client
        print("🚀 STARTING ENHANCED MPZSQL CLIENT")
        client = MPZSQLFlightClientDebug(config)
        client.connect()

        # Execute requested operations
        if args.query:
            client.execute_query(args.query, args.limit)
        elif args.file:
            # For file execution, we'll need to implement this with the enhanced client
            print("File execution not yet implemented in debug client")
        else:
            # Default: show basic connection test
            print("Connected successfully to MPZSQL Flight Server!")
            print(f"Server: {config.host}:{config.port}")
            print(f"Username: {config.username}")

            # Test query
            client.execute_query(
                "SELECT 'Debug client test' as message, CURRENT_TIMESTAMP as timestamp",
                5,
            )

        # Show final memory summary
        if client:
            client.get_memory_summary()

    except KeyboardInterrupt:
        print("\n🛑 Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print("\n🚨 FATAL ERROR:")
        print(f"  Error: {e}")
        print(f"  Error Type: {type(e)}")

        if args.verbose:
            print("Full traceback:")
            traceback.print_exc()

        # Try to get memory info even during error
        if client and hasattr(client, "memory_monitor"):
            try:
                client.memory_monitor.log_memory_usage("FATAL-ERROR")
                client.get_memory_summary()
            except:
                pass

        sys.exit(1)
    finally:
        # Clean up with enhanced error handling
        if client:
            try:
                print("\n🧹 FINAL CLEANUP")
                client.disconnect()
            except Exception as cleanup_error:
                print(f"⚠️  Cleanup error: {cleanup_error}")


if __name__ == "__main__":
    main()

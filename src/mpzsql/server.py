"""
MPZSQL FlightSQL server implementation.

This module implements the core FlightSQL server using Apache Arrow Flight
with support for DuckDB and SQLite backends.

**IMPORTANT**: The main server implementation is MinimalFlightSQLServer.
The MPZSQLFlightServer class below is NOT currently used by the main entry point.
The actual implementation path is:
  MPZSQLServer -> MinimalFlightSQLServer (in minimal_flightsql.py)

This has been kept for reference but should be cleaned up in the future.
"""

import logging
import signal
import threading
from typing import Optional

import pyarrow.flight as pf
from rich.console import Console

from mpzsql.logfire_config import get_main_logger

from mpzsql.backends.base import DatabaseBackend
from mpzsql.backends.duckdb_backend import DuckDBBackend
from mpzsql.backends.sqlite_backend import SQLiteBackend
from mpzsql.config import ServerConfig

from mpzsql.flightsql.minimal import MinimalFlightSQLServer

console = Console()
logger = logging.getLogger(__name__)
server_logger = get_main_logger()




class MPZSQLServer:
    """Main server class that manages the FlightSQL server lifecycle."""

    def __init__(self, config: ServerConfig, duckdb_connection=None):
        """Initialize the server."""
        self.config = config
        self.duckdb_connection = duckdb_connection
        self.flight_service: Optional[pf.FlightServerBase] = None
        self._shutdown_event = threading.Event()

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        console.print(f"\n[yellow]Received signal {signum}, shutting down...[/yellow]")
        self._shutdown_event.set()

    def _create_backend(self) -> DatabaseBackend:
        """Create the appropriate database backend."""
        if self.config.backend == "duckdb":
            return DuckDBBackend(self.config, self.duckdb_connection)
        elif self.config.backend == "sqlite":
            return SQLiteBackend(self.config)
        else:
            raise ValueError(f"Unknown backend: {self.config.backend}")

    def start(self):
        """Start the server."""
        try:
            # Create listen location object (where the server actually listens)
            if self.config.is_tls_enabled:
                listen_location = pf.Location.for_grpc_tls(
                    self.config.hostname, self.config.port
                )
            else:
                listen_location = pf.Location.for_grpc_tcp(
                    self.config.hostname, self.config.port
                )

            # Create advertised location object (what clients should connect to)
            if self.config.is_tls_enabled:
                advertised_location = pf.Location.for_grpc_tls(
                    self.config.effective_advertised_hostname, self.config.port
                )
            else:
                advertised_location = pf.Location.for_grpc_tcp(
                    self.config.effective_advertised_hostname, self.config.port
                )

            # Create backend
            backend = self._create_backend()

            # Create the appropriate flight service
            # Use MinimalFlightSQLServer - this is the ACTIVE implementation that provides
            # proper JDBC compatibility with correct FlightSQL protocol handling.
            # (MPZSQLFlightServer in this file is legacy and not used)
            
            # Pass both listen and advertised locations to the FlightSQL server
            # Note: This assumes MinimalFlightSQLServer supports the advertised_location parameter.
            # If it doesn't, we may need to modify that class as well.
            try:
                # Try new signature with advertised location support
                self.flight_service = MinimalFlightSQLServer(
                    backend, self.config, listen_location, advertised_location
                )
            except TypeError:
                # Fallback to old signature for backward compatibility
                console.print("[yellow]Warning: MinimalFlightSQLServer doesn't support advertised location yet, using listen location[/yellow]")
                self.flight_service = MinimalFlightSQLServer(backend, self.config, listen_location)

            console.print(
                f"[green]✓[/green] Server started on {self.config.hostname}:{self.config.port}"
            )
            if self.config.effective_advertised_hostname != self.config.hostname:
                console.print(
                    f"[blue]✓[/blue] Server advertising {self.config.effective_advertised_hostname}:{self.config.port} to clients"
                )
            console.print("[dim]Press Ctrl+C to stop the server[/dim]")

            # Start the Flight server - this is blocking
            self.flight_service.serve()

        except Exception as e:
            logger.error(f"Server startup failed: {e}")
            raise
        finally:
            self.stop()

    def stop(self):
        """Stop the server."""
        if self.flight_service:
            try:
                self.flight_service.shutdown()
                console.print("[green]✓[/green] Server stopped")
            except Exception as e:
                logger.error(f"Error stopping server: {e}")

        if self.flight_service:
            try:
                # Close any backend connections
                if hasattr(self.flight_service, "backend") and hasattr(
                    self.flight_service.backend, "close"
                ):
                    self.flight_service.backend.close()
            except Exception as e:
                logger.error(f"Error closing flight service: {e}")
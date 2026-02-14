"""gRPC Health Checking service (grpc.health.v1).

Runs a **separate** lightweight gRPC server that implements the standard
``grpc.health.v1.Health/Check`` and ``Watch`` RPCs.  PyArrow Flight manages
its own gRPC server internally, so we cannot register additional services on
it — hence the need for a dedicated health port (matching
design where health runs on a plaintext ``--health-check-port``).

The :class:`BackgroundHealthPoller` periodically probes DuckDB to ensure
the database is healthy and updates the health servicer status accordingly.
"""

from __future__ import annotations

import logging
import threading
from concurrent import futures
from typing import TYPE_CHECKING

import grpc

if TYPE_CHECKING:
    import duckdb
from grpc_health.v1.health import HealthServicer
from grpc_health.v1.health_pb2 import HealthCheckResponse
from grpc_health.v1.health_pb2_grpc import add_HealthServicer_to_server

logger = logging.getLogger(__name__)

__all__ = ["BackgroundHealthPoller", "HealthServer"]

# Service name used in health checks (empty string = overall server health)
_OVERALL = ""
_SERVICE_NAME = "lakehouse.FlightSql"


class HealthServer:
    """A standalone gRPC server dedicated to health checking.

    Runs on a separate port so that Kubernetes probes (``grpc_health_probe``,
    ``livenessProbe.grpc``) can reach it without TLS or auth, even when the
    main Flight SQL port requires both.

    Args:
        port: TCP port to listen on (e.g. ``8081``).
        max_workers: Thread-pool size for the gRPC server.
    """

    def __init__(self, port: int = 8081, max_workers: int = 2) -> None:
        """Initialize with *port* and *max_workers*."""
        self.port = port
        self._servicer = HealthServicer()
        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
        add_HealthServicer_to_server(self._servicer, self._server)
        self._server.add_insecure_port(f"[::]:{port}")

    @property
    def servicer(self) -> HealthServicer:
        """The underlying ``HealthServicer`` — use to set status programmatically."""
        return self._servicer

    def set_serving(self) -> None:
        """Mark both overall and per-service health as ``SERVING``."""
        status = HealthCheckResponse.SERVING
        self._servicer.set(_OVERALL, status)
        self._servicer.set(_SERVICE_NAME, status)
        logger.info("Health status set to SERVING on port %d", self.port)

    def set_not_serving(self) -> None:
        """Mark both overall and per-service health as ``NOT_SERVING``."""
        status = HealthCheckResponse.NOT_SERVING
        self._servicer.set(_OVERALL, status)
        self._servicer.set(_SERVICE_NAME, status)
        logger.info("Health status set to NOT_SERVING on port %d", self.port)

    def start(self) -> None:
        """Start the health gRPC server (non-blocking)."""
        self._server.start()
        self.set_serving()
        logger.info("Health server listening on port %d", self.port)

    def stop(self, grace: float = 5.0) -> None:
        """Gracefully stop the health server.

        Args:
            grace: Seconds to wait for in-flight RPCs before forcefully closing.
        """
        self._servicer.enter_graceful_shutdown()
        self._server.stop(grace)
        logger.info("Health server stopped")

    def wait_for_termination(self, timeout: float | None = None) -> bool:
        """Block until the server terminates.

        Args:
            timeout: Max seconds to wait. ``None`` → wait forever.

        Returns:
            ``True`` on timeout (server still running), ``False`` when terminated.
        """
        event = self._server.wait_for_termination(timeout=timeout)
        return bool(event)


class BackgroundHealthPoller:
    """Periodically probe DuckDB and update the health servicer.

    Runs a background daemon thread that executes ``SELECT 1`` against the
    DuckDB connection every *interval* seconds.  If the query succeeds the
    health status is ``SERVING``; on any exception it flips to
    ``NOT_SERVING``.

    Args:
        health_server: The :class:`HealthServer` whose status to update.
        db: DuckDB connection to probe.
        interval: Polling interval in seconds.
    """

    def __init__(
        self,
        health_server: HealthServer,
        db: duckdb.DuckDBPyConnection,
        interval: float = 5.0,
    ) -> None:
        """Initialize with *health_server*, *db* connection, and poll *interval*."""
        self._health_server = health_server
        self._db = db
        self._interval = interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the background polling thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, name="health-poller", daemon=True)
        self._thread.start()
        logger.info("Health poller started (interval=%.1fs)", self._interval)

    def stop(self) -> None:
        """Signal the polling thread to stop and wait for it to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval * 2)
            self._thread = None
        logger.info("Health poller stopped")

    @property
    def is_running(self) -> bool:
        """Whether the poller thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def _poll_loop(self) -> None:
        """Continuously poll DuckDB health until stopped."""
        while not self._stop_event.is_set():
            try:
                self._db.execute("SELECT 1")
                self._health_server.set_serving()
            except Exception:
                logger.exception("Health check failed — DuckDB unreachable")
                self._health_server.set_not_serving()
            self._stop_event.wait(self._interval)

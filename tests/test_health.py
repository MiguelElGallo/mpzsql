"""Tests for lakehouse.health — gRPC health checking service."""

from __future__ import annotations

import time

import duckdb
import grpc
import pytest
from grpc_health.v1.health_pb2 import HealthCheckRequest, HealthCheckResponse
from grpc_health.v1.health_pb2_grpc import HealthStub

from lakehouse.health import BackgroundHealthPoller, HealthServer


# ═══════════════════════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════════════════════
def _find_free_port():
    """Find an available TCP port."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture
def health_port():
    """Return a free port for the health server."""
    return _find_free_port()


@pytest.fixture
def health_server(health_port):
    """A HealthServer instance that is started and stopped around the test."""
    server = HealthServer(port=health_port)
    server.start()
    yield server
    server.stop(grace=1.0)


@pytest.fixture
def health_channel(health_port, health_server):
    """A gRPC channel connected to the health server."""
    channel = grpc.insecure_channel(f"localhost:{health_port}")
    yield channel
    channel.close()


@pytest.fixture
def health_stub(health_channel):
    """A Health gRPC stub."""
    return HealthStub(health_channel)


@pytest.fixture
def db():
    """In-memory DuckDB connection."""
    conn = duckdb.connect(":memory:")
    yield conn
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════
#  HealthServer
# ═══════════════════════════════════════════════════════════════════════════
class TestHealthServer:
    """Tests for HealthServer lifecycle and status management."""

    def test_serving_on_start(self, health_stub):
        """After start(), health check returns SERVING."""
        resp = health_stub.Check(HealthCheckRequest(service=""))
        assert resp.status == HealthCheckResponse.SERVING

    def test_serving_named_service(self, health_stub):
        """Named service also returns SERVING after start()."""
        resp = health_stub.Check(HealthCheckRequest(service="lakehouse.FlightSql"))
        assert resp.status == HealthCheckResponse.SERVING

    def test_set_not_serving(self, health_server, health_stub):
        """set_not_serving() flips status to NOT_SERVING."""
        health_server.set_not_serving()
        resp = health_stub.Check(HealthCheckRequest(service=""))
        assert resp.status == HealthCheckResponse.NOT_SERVING

    def test_set_serving_after_not_serving(self, health_server, health_stub):
        """Can toggle back to SERVING."""
        health_server.set_not_serving()
        health_server.set_serving()
        resp = health_stub.Check(HealthCheckRequest(service=""))
        assert resp.status == HealthCheckResponse.SERVING

    def test_unknown_service(self, health_stub):
        """Unknown service name raises NOT_FOUND."""
        with pytest.raises(grpc.RpcError) as exc_info:
            health_stub.Check(HealthCheckRequest(service="nonexistent.Service"))
        assert exc_info.value.code() == grpc.StatusCode.NOT_FOUND

    def test_servicer_property(self, health_server):
        """The servicer property exposes the underlying HealthServicer."""
        assert health_server.servicer is not None

    def test_stop_idempotent(self, health_port):
        """Stopping a server that was never started doesn't crash."""
        server = HealthServer(port=health_port + 1)
        server.stop(grace=0.5)  # Should not raise


class TestHealthServerConstruction:
    """Tests for HealthServer construction (no start)."""

    def test_default_port(self):
        server = HealthServer()
        assert server.port == 8081

    def test_custom_port(self):
        server = HealthServer(port=9999)
        assert server.port == 9999


# ═══════════════════════════════════════════════════════════════════════════
#  BackgroundHealthPoller
# ═══════════════════════════════════════════════════════════════════════════
class TestBackgroundHealthPoller:
    """Tests for BackgroundHealthPoller."""

    def test_starts_and_polls(self, health_server, health_stub, db):
        """Poller sets SERVING when DuckDB is healthy."""
        health_server.set_not_serving()
        poller = BackgroundHealthPoller(health_server, db, interval=0.1)
        poller.start()
        try:
            # Wait for at least one poll cycle
            time.sleep(0.3)
            resp = health_stub.Check(HealthCheckRequest(service=""))
            assert resp.status == HealthCheckResponse.SERVING
        finally:
            poller.stop()

    def test_detects_failure(self, health_server, health_stub, db):
        """Poller sets NOT_SERVING when DuckDB connection fails."""
        poller = BackgroundHealthPoller(health_server, db, interval=0.1)
        poller.start()
        try:
            # Wait for initial poll
            time.sleep(0.2)
            assert (
                health_stub.Check(HealthCheckRequest(service="")).status
                == HealthCheckResponse.SERVING
            )

            # Close the DuckDB connection to simulate failure
            db.close()
            time.sleep(0.3)
            resp = health_stub.Check(HealthCheckRequest(service=""))
            assert resp.status == HealthCheckResponse.NOT_SERVING
        finally:
            poller.stop()

    def test_stop_halts_thread(self, health_server, db):
        """Calling stop() terminates the poller thread."""
        poller = BackgroundHealthPoller(health_server, db, interval=0.1)
        poller.start()
        assert poller.is_running
        poller.stop()
        time.sleep(0.1)
        assert not poller.is_running

    def test_is_running_before_start(self, health_server, db):
        """is_running is False before start()."""
        poller = BackgroundHealthPoller(health_server, db, interval=1.0)
        assert not poller.is_running

    def test_stop_without_start(self, health_server, db):
        """Calling stop() without start() doesn't crash."""
        poller = BackgroundHealthPoller(health_server, db, interval=1.0)
        poller.stop()  # Should not raise

    def test_custom_interval(self, health_server, db):
        """Custom interval is respected."""
        poller = BackgroundHealthPoller(health_server, db, interval=10.0)
        assert poller._interval == 10.0

    def test_daemon_thread(self, health_server, db):
        """The poller thread is a daemon so it doesn't block shutdown."""
        poller = BackgroundHealthPoller(health_server, db, interval=0.1)
        poller.start()
        try:
            assert poller._thread is not None
            assert poller._thread.daemon
        finally:
            poller.stop()


# ═══════════════════════════════════════════════════════════════════════════
#  HealthServer.wait_for_termination
# ═══════════════════════════════════════════════════════════════════════════
class TestWaitForTermination:
    """Tests for HealthServer.wait_for_termination()."""

    def test_wait_for_termination_returns_true_on_timeout(self):
        """When the server is running, wait_for_termination with a short timeout returns True."""
        port = _find_free_port()
        server = HealthServer(port=port)
        server.start()
        try:
            result = server.wait_for_termination(timeout=0.2)
            assert result is True
        finally:
            server.stop()

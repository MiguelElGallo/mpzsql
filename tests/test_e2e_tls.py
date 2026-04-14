"""End-to-end TLS tests for the Flight SQL server.

Generates a self-signed CA + server certificate at test time, starts the
server with ``grpc+tls://``, and verifies connectivity from both ADBC
(Python) and JDBC (Java via Maven) over encrypted channels.

No external env vars required — runs entirely in-memory with DuckDB.
"""

from __future__ import annotations

import contextlib
import ipaddress
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import adbc_driver_flightsql
import adbc_driver_flightsql.dbapi as flightsql
import adbc_driver_manager
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from lakehouse.server import DuckDBFlightSqlServer

# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _generate_self_signed_cert(
    tmpdir: str,
) -> tuple[Path, Path, Path]:
    """Generate a CA key/cert and a server key/cert signed by the CA.

    Returns ``(ca_cert_path, server_cert_path, server_key_path)``.
    """
    import datetime

    # ── CA key + cert ────────────────────────────────────────
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.UTC))
        .not_valid_after(datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    # ── Server key + cert (signed by CA) ─────────────────────
    srv_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    srv_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    srv_cert = (
        x509.CertificateBuilder()
        .subject_name(srv_name)
        .issuer_name(ca_name)
        .public_key(srv_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.UTC))
        .not_valid_after(datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    # ── Write to disk ────────────────────────────────────────
    ca_cert_path = Path(tmpdir) / "ca.crt"
    srv_cert_path = Path(tmpdir) / "server.crt"
    srv_key_path = Path(tmpdir) / "server.key"

    ca_cert_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    srv_cert_path.write_bytes(srv_cert.public_bytes(serialization.Encoding.PEM))
    srv_key_path.write_bytes(
        srv_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )

    return ca_cert_path, srv_cert_path, srv_key_path


# ───────────────────────────────────────────────────────────────────────────
# Fixtures
# ───────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def tls_artifacts():
    """Generate TLS certs and persist them for the whole module."""
    tmpdir = tempfile.mkdtemp(prefix="lakehouse_tls_")
    ca, cert, key = _generate_self_signed_cert(tmpdir)
    yield ca, cert, key, tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="module")
def tls_server(tls_artifacts):
    """Start a Flight SQL server with TLS enabled."""
    _ca_cert, srv_cert, srv_key, _tmpdir = tls_artifacts
    port = _free_port()
    location = f"grpc+tls://127.0.0.1:{port}"

    cert_bytes = srv_cert.read_bytes()
    key_bytes = srv_key.read_bytes()

    srv = DuckDBFlightSqlServer(
        location=location,
        db_path=":memory:",
        tls_certificates=[(cert_bytes, key_bytes)],
    )

    # Pre-seed a table so we can verify queries work
    srv._db.execute("CREATE TABLE tls_test (id INT, val TEXT)")
    srv._db.execute("INSERT INTO tls_test VALUES (1, 'encrypted'), (2, 'channel')")

    t = threading.Thread(target=srv.serve, daemon=True)
    t.start()
    time.sleep(0.5)

    yield srv, port

    srv.shutdown()


@pytest.fixture(scope="module")
def tls_conn(tls_server, tls_artifacts):
    """ADBC connection over TLS to the server."""
    ca_cert, _cert, _key, _tmpdir = tls_artifacts
    _srv, port = tls_server

    ca_bytes = ca_cert.read_bytes().decode("utf-8")

    conn = flightsql.connect(
        f"grpc+tls://127.0.0.1:{port}",
        db_kwargs={
            adbc_driver_flightsql.DatabaseOptions.TLS_ROOT_CERTS.value: ca_bytes,
        },
    )
    with contextlib.suppress(adbc_driver_manager.NotSupportedError):
        conn.adbc_connection.set_autocommit(True)
    yield conn
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# ADBC over TLS
# ═══════════════════════════════════════════════════════════════════════════


class TestTlsAdbc:
    """Verify ADBC connectivity over an encrypted gRPC channel."""

    def test_simple_query(self, tls_conn):
        """SELECT over TLS succeeds."""
        cur = tls_conn.execute("SELECT 42 AS answer")
        rows = cur.fetchall()
        assert rows == [(42,)]
        cur.close()

    def test_query_seeded_table(self, tls_conn):
        """Query pre-seeded rows over TLS."""
        cur = tls_conn.execute("SELECT id, val FROM tls_test ORDER BY id")
        rows = cur.fetchall()
        assert rows == [(1, "encrypted"), (2, "channel")]
        cur.close()

    def test_ddl_over_tls(self, tls_conn):
        """CREATE + INSERT + SELECT over TLS roundtrip."""
        tls_conn.execute("CREATE TABLE tls_ddl (x INT)").close()
        tls_conn.execute("INSERT INTO tls_ddl VALUES (99)").close()

        cur = tls_conn.execute("SELECT x FROM tls_ddl")
        assert cur.fetchall() == [(99,)]
        cur.close()

        tls_conn.execute("DROP TABLE tls_ddl").close()

    def test_plaintext_rejected(self, tls_server):
        """A plaintext connection to a TLS server must fail."""
        _srv, port = tls_server
        with pytest.raises(Exception):  # noqa: B017
            conn = flightsql.connect(f"grpc://127.0.0.1:{port}")
            conn.execute("SELECT 1")

    def test_wrong_ca_rejected(self, tls_server):
        """A connection with a different CA cert must fail."""
        _srv, port = tls_server

        # Generate a completely different CA
        tmpdir = tempfile.mkdtemp()
        other_ca, _, _ = _generate_self_signed_cert(tmpdir)
        other_ca_bytes = other_ca.read_bytes().decode("utf-8")

        with pytest.raises(Exception):  # noqa: B017
            conn = flightsql.connect(
                f"grpc+tls://127.0.0.1:{port}",
                db_kwargs={
                    adbc_driver_flightsql.DatabaseOptions.TLS_ROOT_CERTS.value: other_ca_bytes,
                },
            )
            conn.execute("SELECT 1")

        shutil.rmtree(tmpdir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════
# JDBC over TLS
# ═══════════════════════════════════════════════════════════════════════════

_JDBC_DIR = os.path.join(os.path.dirname(__file__), "jdbc")


@pytest.mark.skipif(shutil.which("mvn") is None, reason="Maven (mvn) not found")
def test_jdbc_over_tls(tls_server, tls_artifacts):
    """Run the JDBC TLS test class against our TLS-enabled server."""
    _ca_cert, _cert, _key, _tmpdir = tls_artifacts
    _srv, port = tls_server

    result = subprocess.run(
        [
            "mvn",
            "-q",
            "test",
            f"-Dflight.url=grpc+tls://127.0.0.1:{port}",
            "-Dtest=FlightSqlJdbcTlsTest",
        ],
        cwd=_JDBC_DIR,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        print("=== Maven stdout ===")
        print(result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout)
        print("=== Maven stderr ===")
        print(result.stderr[-3000:] if len(result.stderr) > 3000 else result.stderr)

    assert result.returncode == 0, f"mvn test (TLS) failed (exit {result.returncode})"

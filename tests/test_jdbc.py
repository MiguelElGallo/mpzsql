"""Pytest bridge that runs JDBC integration tests via Maven.

This test starts a DuckLake-enabled Flight SQL server, then shells out
to ``mvn test`` inside ``tests/jdbc/`` passing the server URL as
``-Dflight.url=grpc://127.0.0.1:<port>``.

Skipped when:
* DuckLake env vars are missing (same gate as ``test_e2e_ducklake.py``).
* Maven (``mvn``) is not on ``$PATH``.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import threading
import time

import pytest

# ───────────────────────────────────────────────────────────────────────────
# Skip conditions
# ───────────────────────────────────────────────────────────────────────────

_REQUIRED_ENV = (
    "DUCKLAKE_PG_HOST",
    "DUCKLAKE_PG_DATABASE",
    "DUCKLAKE_PG_USER",
    "DUCKLAKE_AZURE_STORAGE_ACCOUNT",
    "DUCKLAKE_DATA_PATH",
)
_missing = [v for v in _REQUIRED_ENV if not os.environ.get(v)]

pytestmark = [
    pytest.mark.skipif(bool(_missing), reason=f"DuckLake env vars missing: {', '.join(_missing)}"),
    pytest.mark.skipif(shutil.which("mvn") is None, reason="Maven (mvn) not found"),
]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def ducklake_server():  # type: ignore[no-redef]
    from lakehouse.azure_token import PostgresTokenManager
    from lakehouse.config import ServerConfig
    from lakehouse.ducklake import initialize_ducklake
    from lakehouse.server import DuckDBFlightSqlServer

    alias = os.environ.get("DUCKLAKE_ALIAS", "lakehouse")
    port = _free_port()
    location = f"grpc://127.0.0.1:{port}"

    config = ServerConfig(
        port=port,
        database=":memory:",
        azure_storage_account=os.environ["DUCKLAKE_AZURE_STORAGE_ACCOUNT"],
        ducklake_data_path=os.environ["DUCKLAKE_DATA_PATH"],
        pg_host=os.environ["DUCKLAKE_PG_HOST"],
        pg_port=int(os.environ.get("DUCKLAKE_PG_PORT", "5432")),
        pg_database=os.environ["DUCKLAKE_PG_DATABASE"],
        pg_user=os.environ["DUCKLAKE_PG_USER"],
        ducklake_alias=alias,
    )

    srv = DuckDBFlightSqlServer(location=location, db_path=":memory:", ducklake_alias=alias)
    token_mgr = PostgresTokenManager(srv._db, config)
    token = token_mgr.get_initial_token()
    initialize_ducklake(srv._db, config, token=token)

    t = threading.Thread(target=srv.serve, daemon=True)
    t.start()
    time.sleep(0.5)

    yield srv, port

    token_mgr.stop()
    srv.shutdown()


# ───────────────────────────────────────────────────────────────────────────
# JDBC test
# ───────────────────────────────────────────────────────────────────────────

_JDBC_DIR = os.path.join(os.path.dirname(__file__), "jdbc")


def test_jdbc_integration(ducklake_server):
    """Run Maven JDBC tests against the running DuckLake Flight SQL server."""
    _srv, port = ducklake_server
    url = f"grpc://127.0.0.1:{port}"

    result = subprocess.run(
        ["mvn", "-q", "test", f"-Dflight.url={url}", "-Dtest=FlightSqlJdbcTest"],
        cwd=_JDBC_DIR,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        # Print Maven output so the tester can diagnose
        print("=== Maven stdout ===")
        print(result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout)
        print("=== Maven stderr ===")
        print(result.stderr[-3000:] if len(result.stderr) > 3000 else result.stderr)

    assert result.returncode == 0, f"mvn test failed (exit {result.returncode})"

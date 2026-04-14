from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
import time

import duckdb

from lakehouse._azd_env import apply_env_resolution, postgres_firewall_hint, resolve_ducklake_env


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _require_environment() -> None:
    resolution = resolve_ducklake_env()
    apply_env_resolution(resolution)

    if resolution.missing:
        raise SystemExit(resolution.skip_reason("Missing DuckLake environment variables"))

    if shutil.which("mvn") is None:
        raise SystemExit("Maven (mvn) not found on PATH")


def main() -> int:
    _require_environment()

    from lakehouse.azure_token import PostgresTokenManager
    from lakehouse.config import ServerConfig
    from lakehouse.ducklake import initialize_ducklake
    from lakehouse.server import DuckDBFlightSqlServer

    alias = os.environ.get("DUCKLAKE_ALIAS", "lakehouse")
    port = _free_port()
    location = f"grpc://127.0.0.1:{port}"

    config = ServerConfig(
        host="127.0.0.1",
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

    server = DuckDBFlightSqlServer(location=location, db_path=":memory:", ducklake_alias=alias)
    token_manager = PostgresTokenManager(server._db, config)
    token = token_manager.get_initial_token()
    storage_token = token_manager.get_initial_storage_token()
    try:
        initialize_ducklake(server._db, config, token=token, storage_token=storage_token)
    except duckdb.Error as exc:
        message = (
            "Failed to bootstrap the local DuckLake catalog. "
            "Verify the DUCKLAKE_* settings or azd environment outputs. "
            f"{postgres_firewall_hint()}"
        )
        raise SystemExit(f"{message}\nError type: {type(exc).__name__}") from None

    thread = threading.Thread(target=server.serve, daemon=True)
    thread.start()
    time.sleep(0.5)

    script_dir = os.path.dirname(__file__)
    command = ["mvn", "-q", "test", f"-Dflight.url={location}", "-Dtest=FlightSqlJdbcTest"]
    env = os.environ.copy()
    env["MAVEN_OPTS"] = f"{env.get('MAVEN_OPTS', '').strip()} -Duser.timezone=UTC".strip()

    try:
        result = subprocess.run(command, cwd=script_dir, env=env, text=True)
        return result.returncode
    finally:
        token_manager.stop()
        server.shutdown()


if __name__ == "__main__":
    sys.exit(main())

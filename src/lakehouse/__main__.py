"""Entry point for ``python -m lakehouse`` and the ``lakehouse`` console script.

The :func:`build_server` factory wires together all components —
:class:`~lakehouse.server.DuckDBFlightSqlServer`,
:class:`~lakehouse.auth.BasicAuthServerMiddlewareFactory`,
:class:`~lakehouse.auth.BearerAuthServerMiddlewareFactory`,
:class:`~lakehouse.auth.AccessLogMiddlewareFactory`,
:class:`~lakehouse.health.HealthServer`, and
:class:`~lakehouse.health.BackgroundHealthPoller`
— from a single :class:`~lakehouse.config.ServerConfig`.
"""

from __future__ import annotations

import logging
import signal
import sys
from typing import TYPE_CHECKING, Annotated

import typer

if TYPE_CHECKING:
    import duckdb

    from lakehouse.azure_token import PostgresTokenManager

from lakehouse.auth import (
    AccessLogMiddlewareFactory,
    BasicAuthServerMiddlewareFactory,
    BearerAuthServerMiddlewareFactory,
    NoOpAuthHandler,
    RequiredAuthServerMiddlewareFactory,
)
from lakehouse.config import ServerConfig
from lakehouse.health import BackgroundHealthPoller, HealthServer
from lakehouse.security import hash_password
from lakehouse.server import DuckDBFlightSqlServer

logger = logging.getLogger(__name__)

__all__ = ["build_server", "main"]


# ═══════════════════════════════════════════════════════════════════════════
#  Server builder
# ═══════════════════════════════════════════════════════════════════════════


def build_server(config: ServerConfig) -> DuckDBFlightSqlServer:
    """Create a fully-wired :class:`DuckDBFlightSqlServer` from *config*.

    Configures middleware (Basic auth, Bearer auth, access logging),
    TLS certificates, and the DuckDB connection.

    Args:
        config: Server configuration.

    Returns:
        A ready-to-:meth:`serve` ``DuckDBFlightSqlServer``.
    """
    # ── Middleware stack ──────────────────────────────────────
    middleware: dict[str, object] = {}

    # Access logging (always enabled)
    middleware["access-log"] = AccessLogMiddlewareFactory()

    # Authentication middleware (enabled when password is set)
    if config.password:
        pw_hash = hash_password(config.password, config.secret_key)
        middleware["basic-auth"] = BasicAuthServerMiddlewareFactory(
            secret_key=config.secret_key,
            password_hash=pw_hash,
            instance_id="",
        )
        middleware["bearer-auth"] = BearerAuthServerMiddlewareFactory(
            secret_key=config.secret_key,
            issuer=config.jwt_issuer,
        )
        middleware["required-auth"] = RequiredAuthServerMiddlewareFactory()
        logger.info("Authentication enabled (username=%s)", config.username)
    else:
        logger.warning("No password configured — authentication is DISABLED")

    # ── TLS ──────────────────────────────────────────────────
    tls_certificates: list[tuple[bytes, bytes]] | None = None
    if config.tls_enabled:
        assert config.tls_cert_file is not None  # guaranteed by validator
        assert config.tls_key_file is not None
        cert_bytes = config.tls_cert_file.read_bytes()
        key_bytes = config.tls_key_file.read_bytes()
        tls_certificates = [(cert_bytes, key_bytes)]
        logger.info("TLS enabled (cert=%s)", config.tls_cert_file)

    # ── Build server ─────────────────────────────────────────
    # NoOpAuthHandler : the Handshake RPC succeeds (no-op),
    # while actual authentication is enforced by middleware on every call.
    kwargs: dict[str, object] = {"middleware": middleware, "auth_handler": NoOpAuthHandler()}
    if tls_certificates:
        kwargs["tls_certificates"] = tls_certificates
    if config.mtls_enabled:
        assert config.mtls_ca_cert_file is not None
        kwargs["verify_client"] = True
        kwargs["root_certificates"] = config.mtls_ca_cert_file.read_bytes()
        logger.info("mTLS enabled (CA=%s)", config.mtls_ca_cert_file)

    server = DuckDBFlightSqlServer(
        location=config.location,
        db_path=config.database,
        ducklake_alias=config.ducklake_alias if config.ducklake_enabled else "",
        **kwargs,
    )

    return server


def _run_init_sql(db: duckdb.DuckDBPyConnection, config: ServerConfig) -> None:
    """Execute startup SQL from config (inline and/or file).

    Args:
        db: DuckDB connection.
        config: Server configuration.
    """
    if config.init_sql:
        for stmt in config.init_sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                logger.info("init-sql: %s", stmt)
                db.execute(stmt)

    if config.init_sql_file is not None:
        sql = config.init_sql_file.read_text(encoding="utf-8")
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                logger.info("init-sql-file(%s): %s", config.init_sql_file, stmt)
                db.execute(stmt)


# ═══════════════════════════════════════════════════════════════════════════
#  Typer CLI
# ═══════════════════════════════════════════════════════════════════════════

app = typer.Typer(
    name="lakehouse",
    help="Lakehouse — High-Performance Flight SQL Server backed by DuckDB.",
    add_completion=False,
)


@app.command()
def serve(
    host: Annotated[str | None, typer.Option(help="Bind address")] = None,
    port: Annotated[int | None, typer.Option(help="Flight SQL port")] = None,
    database: Annotated[str | None, typer.Option(help="DuckDB database path")] = None,
    username: Annotated[str | None, typer.Option(help="Auth username")] = None,
    password: Annotated[str | None, typer.Option(help="Auth password")] = None,
    secret_key: Annotated[str | None, typer.Option(help="HMAC/JWT secret key")] = None,
    health_check_port: Annotated[int | None, typer.Option(help="Health check port")] = None,
    health_check_enabled: Annotated[
        bool | None,
        typer.Option(
            "--health-check-enabled/--no-health-check-enabled",
            help="Enable health server",
        ),
    ] = None,
    log_level: Annotated[str | None, typer.Option(help="Log level")] = None,
    print_queries: Annotated[
        bool | None,
        typer.Option(
            "--print-queries/--no-print-queries",
            help="Log client SQL queries",
        ),
    ] = None,
    init_sql: Annotated[str | None, typer.Option(help="Startup SQL (semicolon-separated)")] = None,
    # ── DuckLake options ─────────────────────────────────────
    azure_storage_account: Annotated[
        str | None, typer.Option(help="Azure Storage account name for DuckLake data files")
    ] = None,
    ducklake_data_path: Annotated[
        str | None, typer.Option(help="DATA_PATH for DuckLake ATTACH (e.g. az://container/)")
    ] = None,
    pg_host: Annotated[
        str | None, typer.Option(help="PostgreSQL host for DuckLake catalog")
    ] = None,
    pg_port: Annotated[int | None, typer.Option(help="PostgreSQL port")] = None,
    pg_database: Annotated[
        str | None, typer.Option(help="PostgreSQL database for DuckLake catalog")
    ] = None,
    pg_user: Annotated[
        str | None, typer.Option(help="PostgreSQL user (Entra ID principal)")
    ] = None,
    ducklake_alias: Annotated[
        str | None, typer.Option(help="DuckDB alias for the attached DuckLake")
    ] = None,
    pg_token_refresh_minutes: Annotated[
        float | None, typer.Option(help="Minutes before token expiry to refresh")
    ] = None,
) -> None:
    """Start the Lakehouse Flight SQL server."""
    # Only pass explicitly-provided CLI flags to ServerConfig.
    # Omitted flags fall through to LAKEHOUSE_* env vars → .env → field defaults.
    overrides: dict[str, object] = {
        k: v
        for k, v in {
            "host": host,
            "port": port,
            "database": database,
            "username": username,
            "password": password,
            "secret_key": secret_key,
            "health_check_port": health_check_port,
            "health_check_enabled": health_check_enabled,
            "log_level": log_level,
            "print_queries": print_queries,
            "init_sql": init_sql,
            "azure_storage_account": azure_storage_account,
            "ducklake_data_path": ducklake_data_path,
            "pg_host": pg_host,
            "pg_port": pg_port,
            "pg_database": pg_database,
            "pg_user": pg_user,
            "ducklake_alias": ducklake_alias,
            "pg_token_refresh_minutes": pg_token_refresh_minutes,
        }.items()
        if v is not None
    }
    config = ServerConfig(**overrides)  # ty: ignore[invalid-argument-type]

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        stream=sys.stderr,
    )

    logger.info("Starting Lakehouse Flight SQL server")
    logger.info("  Location: %s", config.location)
    logger.info("  Database: %s", config.database)

    # Build and start the Flight server
    server = build_server(config)

    # ── DuckLake initialization ──────────────────────────────
    token_manager: PostgresTokenManager | None = None
    if config.ducklake_enabled:
        from lakehouse.azure_token import PostgresTokenManager
        from lakehouse.ducklake import initialize_ducklake

        token_manager = PostgresTokenManager(server._db, config)
        initial_token = token_manager.get_initial_token()
        storage_token = token_manager.get_initial_storage_token()
        initialize_ducklake(server._db, config, token=initial_token, storage_token=storage_token)
        token_manager.start()

    # Health check
    health_srv: HealthServer | None = None
    poller: BackgroundHealthPoller | None = None
    if config.health_check_enabled:
        health_srv = HealthServer(port=config.health_check_port)
        health_srv.start()
        # Connect a poller to the server's DuckDB instance
        poller = BackgroundHealthPoller(
            health_srv,
            server._db,
            interval=config.health_poll_interval,
        )
        poller.start()

    # Graceful shutdown handler
    def _shutdown(signum: int, frame: object) -> None:
        logger.info("Received signal %d — shutting down", signum)
        if token_manager:
            token_manager.stop()
        if poller:
            poller.stop()
        if health_srv:
            health_srv.stop()
        server.shutdown()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Block until terminated
    logger.info("Server ready — accepting connections on %s", config.location)
    server.serve()


def main() -> None:
    """Launch the Lakehouse Flight SQL server."""
    app()


if __name__ == "__main__":
    main()

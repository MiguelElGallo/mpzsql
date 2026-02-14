"""DuckLake initialization — extensions, secrets, and catalog attach.

This module orchestrates the DuckDB setup required for DuckLake:

1. Install and load required extensions (ducklake, iceberg, httpfs, azure, postgres).
2. Create a PostgreSQL secret with an Entra ID token.
3. Create an Azure storage secret using the credential chain provider.
4. Attach the DuckLake catalog and set it as the default database.

All functions accept a raw :class:`duckdb.DuckDBPyConnection` and the
:class:`~lakehouse.config.ServerConfig` (or individual parameters) so they
can be tested and composed independently.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb

    from lakehouse.config import ServerConfig

logger = logging.getLogger(__name__)

__all__ = [
    "attach_ducklake",
    "create_azure_secret",
    "create_pg_secret",
    "initialize_ducklake",
    "install_extensions",
]

#: DuckDB extensions required for DuckLake with PostgreSQL + Azure Blob.
REQUIRED_EXTENSIONS: tuple[str, ...] = (
    "ducklake",
    "iceberg",
    "httpfs",
    "azure",
    "postgres",
)


def install_extensions(db: duckdb.DuckDBPyConnection) -> None:
    """Install and load all DuckDB extensions required for DuckLake.

    Extensions: ``ducklake``, ``iceberg``, ``httpfs``, ``azure``, ``postgres``.

    Args:
        db: An open DuckDB connection.

    Raises:
        duckdb.Error: If an extension fails to install or load.
    """
    for ext in REQUIRED_EXTENSIONS:
        logger.info("Installing DuckDB extension: %s ...", ext)
        db.execute(f"INSTALL {ext}")
        db.execute(f"LOAD {ext}")
        logger.info("  %s loaded", ext)

    # Use DuckDB's custom curl transport which has proper CA cert
    # fallback logic for Linux (checks common cert bundle paths).
    db.execute("SET azure_transport_option_type = 'curl'")
    logger.info("  azure_transport_option_type set to 'curl'")


def create_pg_secret(
    db: duckdb.DuckDBPyConnection,
    *,
    host: str,
    port: int,
    database: str,
    user: str,
    token: str,
) -> None:
    """Create a DuckDB PostgreSQL secret with an Entra ID token.

    The secret is named ``pg_catalog_secret`` and provides authentication
    for the DuckLake PostgreSQL catalog connection.

    Args:
        db: An open DuckDB connection.
        host: PostgreSQL server hostname.
        port: PostgreSQL server port.
        database: PostgreSQL database name.
        user: PostgreSQL username (Entra ID principal).
        token: Entra ID access token.

    Raises:
        duckdb.Error: If the secret cannot be created.
    """
    logger.info("Creating PostgreSQL secret (pg_catalog_secret) ...")
    # DDL statements do not support parameterized queries in DuckDB,
    # so we use f-strings.  All values except *token* are validated by
    # config.py (no single-quotes, semicolons, or spaces).  The token
    # is a base64url-encoded JWT and therefore injection-safe.
    _safe_token = token.replace("'", "''")
    try:
        db.execute(f"""
            CREATE OR REPLACE SECRET pg_catalog_secret (
                TYPE postgres,
                HOST '{host}',
                PORT {port},
                DATABASE '{database}',
                USER '{user}',
                PASSWORD '{_safe_token}'
            )
        """)
    except Exception:
        logger.exception("Failed to create PostgreSQL secret (token redacted)")
        raise
    logger.info("  PostgreSQL secret created")


def create_azure_secret(
    db: duckdb.DuckDBPyConnection,
    *,
    account_name: str,
    access_token: str = "",
) -> None:
    """Create a DuckDB Azure storage secret.

    When *access_token* is provided, uses the ``access_token`` provider
    with an explicit bearer token obtained from the Python Azure Identity
    SDK (avoids DuckDB's C++ credential chain entirely).

    Otherwise falls back to the ``credential_chain`` provider, which is
    convenient for local development (``az login``).

    Args:
        db: An open DuckDB connection.
        account_name: Azure Storage account name.
        access_token: Optional Azure Storage bearer token.  When empty
            the ``credential_chain`` provider is used.

    Raises:
        duckdb.Error: If the secret cannot be created.
    """
    if access_token:
        logger.info("Creating Azure storage secret (access_token) ...")
        _safe_token = access_token.replace("'", "''")
        db.execute(f"""
            CREATE OR REPLACE SECRET azure_storage_secret (
                TYPE azure,
                PROVIDER access_token,
                ACCESS_TOKEN '{_safe_token}',
                ACCOUNT_NAME '{account_name}'
            )
        """)
    else:
        logger.info("Creating Azure storage secret (credential_chain) ...")
        db.execute(f"""
            CREATE OR REPLACE SECRET azure_storage_secret (
                TYPE azure,
                PROVIDER credential_chain,
                ACCOUNT_NAME '{account_name}'
            )
        """)
    logger.info("  Azure storage secret created")


def attach_ducklake(
    db: duckdb.DuckDBPyConnection,
    *,
    host: str,
    port: int,
    database: str,
    user: str,
    alias: str,
    data_path: str,
) -> None:
    """Attach a DuckLake catalog and set it as the default database.

    Executes:

    .. code-block:: sql

        ATTACH 'ducklake:postgres:dbname=<db> host=<host> port=<port> user=<user>'
            AS <alias>
            (DATA_PATH '<data_path>', META_SECRET 'pg_catalog_secret');
        USE <alias>;

    The ``META_SECRET`` parameter tells DuckLake to pass the named secret
    to the PostgreSQL catalog backend, providing the Entra ID token as the
    password.  Token renewal only requires ``CREATE OR REPLACE SECRET`` —
    no ``DETACH`` / ``ATTACH`` is needed.

    Args:
        db: An open DuckDB connection.
        host: PostgreSQL server hostname.
        port: PostgreSQL server port.
        database: PostgreSQL database name.
        user: PostgreSQL username.
        alias: DuckDB alias for the attached DuckLake catalog.
        data_path: ``DATA_PATH`` for Parquet files (e.g. ``az://container/``).

    Raises:
        duckdb.Error: If the ATTACH or USE fails.
    """
    conn_str = (
        f"ducklake:postgres:dbname={database} host={host} port={port} user={user} sslmode=require"
    )
    logger.info(
        "Attaching DuckLake: catalog=%s@%s, data_path=%s",
        database,
        host,
        data_path,
    )
    db.execute(
        f"ATTACH '{conn_str}' AS {alias}"
        f" (DATA_PATH '{data_path}', META_SECRET 'pg_catalog_secret')"
    )
    logger.info("  DuckLake attached as %r", alias)

    db.execute(f"USE {alias}")
    logger.info("  USE %s", alias)


def initialize_ducklake(
    db: duckdb.DuckDBPyConnection,
    config: ServerConfig,
    *,
    token: str,
    storage_token: str = "",
) -> None:
    """Orchestrate full DuckLake initialization.

    Calls, in order:

    1. :func:`install_extensions`
    2. :func:`create_pg_secret`
    3. :func:`create_azure_secret`
    4. :func:`attach_ducklake`

    Args:
        db: An open DuckDB connection (typically ``:memory:``).
        config: Server configuration with all DuckLake fields populated.
        token: Initial Entra ID access token for PostgreSQL.
        storage_token: Optional Entra ID access token for Azure Storage.
            When provided, uses ``access_token`` provider (bypasses
            DuckDB's C++ credential chain).  When empty, falls back to
            ``credential_chain``.

    Raises:
        duckdb.Error: If any step fails.
    """
    install_extensions(db)
    create_pg_secret(
        db,
        host=config.pg_host,
        port=config.pg_port,
        database=config.pg_database,
        user=config.pg_user,
        token=token,
    )
    create_azure_secret(
        db,
        account_name=config.azure_storage_account,
        access_token=storage_token,
    )
    attach_ducklake(
        db,
        host=config.pg_host,
        port=config.pg_port,
        database=config.pg_database,
        user=config.pg_user,
        alias=config.ducklake_alias,
        data_path=config.ducklake_data_path,
    )
    logger.info("DuckLake initialization complete")

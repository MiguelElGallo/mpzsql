"""Entra ID token management for PostgreSQL catalog authentication.

This module provides :class:`PostgresTokenManager`, a background thread that
automatically renews the Azure Entra ID access token used by the DuckDB
PostgreSQL secret.  When the token is close to expiry the manager:

1. Obtains a fresh token via ``azure.identity.DefaultAzureCredential``.
2. Drops the existing DuckDB secret (``pg_catalog_secret``).
3. Creates a new secret with the refreshed token.

No ``DETACH`` / ``ATTACH`` is required because the ATTACH connection string
does **not** contain the password — it is supplied by the secret.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from azure.identity import DefaultAzureCredential

if TYPE_CHECKING:
    import duckdb

    from lakehouse.config import ServerConfig

logger = logging.getLogger(__name__)

__all__ = [
    "PostgresTokenManager",
    "get_pg_entra_token",
    "get_storage_entra_token",
]

#: OAuth2 scope for Azure Database for PostgreSQL (Entra ID).
PG_TOKEN_SCOPE: str = "https://ossrdbms-aad.database.windows.net/.default"

#: OAuth2 scope for Azure Storage (Entra ID).
STORAGE_TOKEN_SCOPE: str = "https://storage.azure.com/.default"


def get_pg_entra_token(
    credential: DefaultAzureCredential,
) -> tuple[str, float]:
    """Fetch an Entra ID access token for Azure Database for PostgreSQL.

    Args:
        credential: An Azure ``DefaultAzureCredential`` instance.

    Returns:
        A ``(token, expires_on)`` tuple where *token* is the access-token
        string and *expires_on* is the Unix timestamp at which it expires.

    Raises:
        azure.core.exceptions.ClientAuthenticationError: If no credential
            in the chain can authenticate.
    """
    response = credential.get_token(PG_TOKEN_SCOPE)
    return response.token, response.expires_on


def get_storage_entra_token(
    credential: DefaultAzureCredential,
) -> tuple[str, float]:
    """Fetch an Entra ID access token for Azure Storage.

    Args:
        credential: An Azure ``DefaultAzureCredential`` instance.

    Returns:
        A ``(token, expires_on)`` tuple where *token* is the access-token
        string and *expires_on* is the Unix timestamp at which it expires.

    Raises:
        azure.core.exceptions.ClientAuthenticationError: If no credential
            in the chain can authenticate.
    """
    response = credential.get_token(STORAGE_TOKEN_SCOPE)
    return response.token, response.expires_on


class PostgresTokenManager:
    """Background thread that renews Entra ID tokens for PostgreSQL and Azure Storage.

    Refreshes both the DuckDB PostgreSQL secret and (optionally) the Azure
    storage secret when either token is close to expiry.  No ``DETACH`` /
    ``ATTACH`` is required because the ATTACH connection string does not
    contain the password.

    Args:
        db: The DuckDB connection whose secrets are managed.
        config: Server configuration with DuckLake fields populated.
        credential: Azure credential instance (injected for testability).

    Example::

        mgr = PostgresTokenManager(db, config)
        initial_token = mgr.get_initial_token()
        storage_token = mgr.get_initial_storage_token()
        mgr.start()    # background renewal loop
        ...
        mgr.stop()     # graceful shutdown
    """

    def __init__(
        self,
        db: duckdb.DuckDBPyConnection,
        config: ServerConfig,
        credential: DefaultAzureCredential | None = None,
    ) -> None:
        """Initialise the token manager.

        Args:
            db: The DuckDB connection whose secrets are managed.
            config: Server configuration with DuckLake fields populated.
            credential: Azure credential instance (injected for testability).
        """
        self._db = db
        self._config = config
        self._credential = credential or DefaultAzureCredential()
        self._refresh_margin = config.pg_token_refresh_minutes * 60  # seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._pg_expires_on: float = 0.0
        self._storage_expires_on: float = 0.0
        self._manage_storage: bool = False
        self._lock = threading.Lock()

    # ── Public API ───────────────────────────────────────────

    def get_initial_token(self) -> str:
        """Fetch the first PostgreSQL token (called during startup).

        Returns:
            The access-token string.

        Raises:
            azure.core.exceptions.ClientAuthenticationError: If
                authentication fails.
        """
        token, self._pg_expires_on = get_pg_entra_token(self._credential)
        logger.info(
            "Entra ID token obtained (expires in %.0f s)",
            self._pg_expires_on - time.time(),
        )
        return token

    def get_initial_storage_token(self) -> str:
        """Fetch the first Azure Storage token (called during startup).

        Also enables automatic storage token renewal in the background
        thread.

        Returns:
            The access-token string for Azure Storage.

        Raises:
            azure.core.exceptions.ClientAuthenticationError: If
                authentication fails.
        """
        token, self._storage_expires_on = get_storage_entra_token(self._credential)
        self._manage_storage = True
        logger.info(
            "Azure Storage token obtained (expires in %.0f s)",
            self._storage_expires_on - time.time(),
        )
        return token

    def start(self) -> None:
        """Start the background renewal thread (daemon)."""
        self._thread = threading.Thread(
            target=self._renewal_loop,
            name="pg-token-renew",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "PostgreSQL token renewal thread started (refresh %.1f min before expiry)",
            self._config.pg_token_refresh_minutes,
        )

    def stop(self) -> None:
        """Signal the renewal thread to stop and wait for it to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            logger.info("PostgreSQL token renewal thread stopped")

    # ── Internal ─────────────────────────────────────────────

    def _renewal_loop(self) -> None:
        """Sleep until near-expiry, then refresh the secret(s).  Repeats."""
        while not self._stop_event.is_set():
            # Sleep until the earlier of the two expiry times.
            next_expiry = self._pg_expires_on
            if self._manage_storage:
                next_expiry = min(next_expiry, self._storage_expires_on)
            sleep_seconds = max(0.0, next_expiry - time.time() - self._refresh_margin)
            if self._stop_event.wait(timeout=sleep_seconds):
                break  # stop requested

            try:
                self._refresh_pg_secret()
            except Exception:
                logger.exception("Failed to refresh PostgreSQL Entra token — retrying in 30 s")

            if self._manage_storage:
                try:
                    self._refresh_storage_secret()
                except Exception:
                    logger.exception("Failed to refresh Storage Entra token — retrying in 30 s")

            # If either refresh failed, retry in 30 s.
            if self._stop_event.wait(timeout=0):
                break

    def _refresh_pg_secret(self) -> None:
        """Obtain a new token and recreate the DuckDB PostgreSQL secret."""
        token, expires_on = get_pg_entra_token(self._credential)
        _safe_token = token.replace("'", "''")

        with self._lock:
            try:
                self._db.execute(f"""
                    CREATE OR REPLACE SECRET pg_catalog_secret (
                        TYPE postgres,
                        HOST '{self._config.pg_host}',
                        PORT {self._config.pg_port},
                        DATABASE '{self._config.pg_database}',
                        USER '{self._config.pg_user}',
                        PASSWORD '{_safe_token}'
                    )
                """)
            except Exception:
                logger.exception("Failed to refresh PostgreSQL secret (token redacted)")
                raise
            self._pg_expires_on = expires_on

        logger.info("PostgreSQL Entra token refreshed successfully")

    def _refresh_storage_secret(self) -> None:
        """Obtain a new token and recreate the DuckDB Azure storage secret."""
        token, expires_on = get_storage_entra_token(self._credential)
        _safe_token = token.replace("'", "''")

        with self._lock:
            try:
                self._db.execute(f"""
                    CREATE OR REPLACE SECRET azure_storage_secret (
                        TYPE azure,
                        PROVIDER access_token,
                        ACCESS_TOKEN '{_safe_token}',
                        ACCOUNT_NAME '{self._config.azure_storage_account}'
                    )
                """)
            except Exception:
                logger.exception("Failed to refresh Azure storage secret (token redacted)")
                raise
            self._storage_expires_on = expires_on

        logger.info("Azure Storage Entra token refreshed successfully")

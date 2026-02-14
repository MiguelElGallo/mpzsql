"""Tests for lakehouse.azure_token — Entra ID token management."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import duckdb
import pytest

from lakehouse.azure_token import (
    PG_TOKEN_SCOPE,
    STORAGE_TOKEN_SCOPE,
    PostgresTokenManager,
    get_pg_entra_token,
    get_storage_entra_token,
)
from lakehouse.config import ServerConfig


def _make_token_response(token: str = "fake-jwt", expires_on: float | None = None):
    """Build a mock token response matching azure.core.credentials.AccessToken."""
    return SimpleNamespace(
        token=token,
        expires_on=expires_on if expires_on is not None else time.time() + 3600,
    )


def _ducklake_config(**overrides) -> ServerConfig:
    """Return a minimal ServerConfig with DuckLake fields populated."""
    defaults = {
        "azure_storage_account": "stompz1",
        "ducklake_data_path": "az://data/",
        "pg_host": "localhost",
        "pg_port": 5432,
        "pg_database": "testdb",
        "pg_user": "testuser",
    }
    defaults.update(overrides)
    return ServerConfig(**defaults)


# ═══════════════════════════════════════════════════════════════════════════
#  C.1  get_pg_entra_token
# ═══════════════════════════════════════════════════════════════════════════
class TestGetPgEntraToken:
    """Tests for get_pg_entra_token()."""

    def test_returns_token_and_expiry(self):
        """Returns (token_str, expires_on) from the credential."""
        mock_cred = MagicMock()
        expires = time.time() + 3600
        mock_cred.get_token.return_value = _make_token_response("my-token", expires)

        token, exp = get_pg_entra_token(mock_cred)

        assert token == "my-token"
        assert exp == expires
        mock_cred.get_token.assert_called_once_with(PG_TOKEN_SCOPE)

    def test_propagates_auth_error(self):
        """Raises when the credential fails."""
        mock_cred = MagicMock()
        mock_cred.get_token.side_effect = RuntimeError("no credential")

        with pytest.raises(RuntimeError, match="no credential"):
            get_pg_entra_token(mock_cred)


# ═══════════════════════════════════════════════════════════════════════════
#  C.1b  get_storage_entra_token
# ═══════════════════════════════════════════════════════════════════════════
class TestGetStorageEntraToken:
    """Tests for get_storage_entra_token()."""

    def test_returns_token_and_expiry(self):
        """Returns (token_str, expires_on) from the credential."""
        mock_cred = MagicMock()
        expires = time.time() + 3600
        mock_cred.get_token.return_value = _make_token_response("storage-tok", expires)

        token, exp = get_storage_entra_token(mock_cred)

        assert token == "storage-tok"
        assert exp == expires
        mock_cred.get_token.assert_called_once_with(
            STORAGE_TOKEN_SCOPE
        )  # ═══════════════════════════════════════════════════════════════════════════


#  C.2  PostgresTokenManager.__init__ + get_initial_token
# ═══════════════════════════════════════════════════════════════════════════
class TestPostgresTokenManagerInit:
    """Tests for PostgresTokenManager construction and initial token."""

    def test_get_initial_token(self):
        """get_initial_token fetches and returns a token string."""
        db = duckdb.connect(":memory:")
        config = _ducklake_config()
        mock_cred = MagicMock()
        mock_cred.get_token.return_value = _make_token_response("init-tok")

        mgr = PostgresTokenManager(db, config, credential=mock_cred)
        token = mgr.get_initial_token()

        assert token == "init-tok"
        mock_cred.get_token.assert_called_once_with(PG_TOKEN_SCOPE)
        db.close()

    def test_refresh_margin_computed_from_config(self):
        """_refresh_margin is pg_token_refresh_minutes * 60."""
        db = duckdb.connect(":memory:")
        config = _ducklake_config(pg_token_refresh_minutes=10.0)
        mock_cred = MagicMock()

        mgr = PostgresTokenManager(db, config, credential=mock_cred)
        assert mgr._refresh_margin == 600.0
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
#  C.3  _renewal_loop
# ═══════════════════════════════════════════════════════════════════════════
class TestRenewalLoop:
    """Tests for the background renewal loop."""

    def test_renewal_fires_before_expiry(self):
        """The renewal loop refreshes the secret before expiry."""
        db = duckdb.connect(":memory:")
        db.execute("INSTALL postgres; LOAD postgres")
        config = _ducklake_config(pg_token_refresh_minutes=0.0001)  # tiny margin

        mock_cred = MagicMock()
        # Initial token expires almost immediately
        mock_cred.get_token.return_value = _make_token_response("tok-v1", time.time() + 0.1)

        mgr = PostgresTokenManager(db, config, credential=mock_cred)
        mgr.get_initial_token()

        # Second call returns a new token
        mock_cred.get_token.return_value = _make_token_response("tok-v2", time.time() + 3600)

        mgr.start()
        # Wait enough for renewal to fire
        time.sleep(0.5)
        mgr.stop()

        # Should have been called at least twice (initial + renewal)
        assert mock_cred.get_token.call_count >= 2
        db.close()

    def test_stop_interrupts_sleep(self):
        """Calling stop() wakes up the sleeping renewal thread promptly."""
        db = duckdb.connect(":memory:")
        config = _ducklake_config()
        mock_cred = MagicMock()
        mock_cred.get_token.return_value = _make_token_response("tok", time.time() + 9999)

        mgr = PostgresTokenManager(db, config, credential=mock_cred)
        mgr.get_initial_token()
        mgr.start()

        start_t = time.time()
        mgr.stop()
        elapsed = time.time() - start_t

        # Should stop in well under 1 second, not wait for expiry
        assert elapsed < 2.0
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
#  C.4  _refresh_secret
# ═══════════════════════════════════════════════════════════════════════════
class TestRefreshSecret:
    """Tests for _refresh_secret()."""

    def test_refresh_creates_secret(self):
        """_refresh_pg_secret creates a pg_catalog_secret in DuckDB."""
        db = duckdb.connect(":memory:")
        db.execute("INSTALL postgres; LOAD postgres")
        config = _ducklake_config()

        mock_cred = MagicMock()
        mock_cred.get_token.return_value = _make_token_response("refreshed-tok")

        mgr = PostgresTokenManager(db, config, credential=mock_cred)
        mgr._refresh_pg_secret()

        secrets = {row[0] for row in db.execute("SELECT name FROM duckdb_secrets()").fetchall()}
        assert "pg_catalog_secret" in secrets
        db.close()

    def test_refresh_replaces_existing(self):
        """Calling _refresh_secret twice replaces the secret without error."""
        db = duckdb.connect(":memory:")
        db.execute("INSTALL postgres; LOAD postgres")
        config = _ducklake_config()

        mock_cred = MagicMock()
        mock_cred.get_token.return_value = _make_token_response("tok-v1")

        mgr = PostgresTokenManager(db, config, credential=mock_cred)
        mgr._refresh_pg_secret()

        mock_cred.get_token.return_value = _make_token_response("tok-v2")
        mgr._refresh_pg_secret()  # should not raise

        secrets = {row[0] for row in db.execute("SELECT name FROM duckdb_secrets()").fetchall()}
        assert "pg_catalog_secret" in secrets
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
#  C.5  Lifecycle (start / stop)
# ═══════════════════════════════════════════════════════════════════════════
class TestTokenManagerLifecycle:
    """Tests for start() / stop() lifecycle."""

    def test_start_creates_daemon_thread(self):
        """start() spawns a daemon thread named 'pg-token-renew'."""
        db = duckdb.connect(":memory:")
        config = _ducklake_config()
        mock_cred = MagicMock()
        mock_cred.get_token.return_value = _make_token_response("tok", time.time() + 9999)

        mgr = PostgresTokenManager(db, config, credential=mock_cred)
        mgr.get_initial_token()
        mgr.start()

        assert mgr._thread is not None
        assert mgr._thread.is_alive()
        assert mgr._thread.daemon is True
        assert mgr._thread.name == "pg-token-renew"

        mgr.stop()
        assert not mgr._thread.is_alive()
        db.close()

    def test_stop_without_start_is_noop(self):
        """stop() does not raise if start() was never called."""
        db = duckdb.connect(":memory:")
        config = _ducklake_config()
        mock_cred = MagicMock()

        mgr = PostgresTokenManager(db, config, credential=mock_cred)
        mgr.stop()  # should not raise
        db.close()

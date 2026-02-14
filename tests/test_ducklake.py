"""Tests for lakehouse.ducklake — extension install, secret creation, attach."""

from __future__ import annotations

import duckdb
import pytest

from lakehouse.ducklake import (
    REQUIRED_EXTENSIONS,
    attach_ducklake,
    create_azure_secret,
    create_pg_secret,
    initialize_ducklake,
    install_extensions,
)


# ═══════════════════════════════════════════════════════════════════════════
#  B.1  install_extensions
# ═══════════════════════════════════════════════════════════════════════════
class TestInstallExtensions:
    """Tests for install_extensions()."""

    def test_required_extensions_tuple(self):
        """REQUIRED_EXTENSIONS is a non-empty tuple of strings."""
        assert isinstance(REQUIRED_EXTENSIONS, tuple)
        assert len(REQUIRED_EXTENSIONS) > 0
        for ext in REQUIRED_EXTENSIONS:
            assert isinstance(ext, str)

    def test_expected_extensions_present(self):
        """All five expected extensions are listed."""
        expected = {"ducklake", "iceberg", "httpfs", "azure", "postgres"}
        assert set(REQUIRED_EXTENSIONS) == expected

    def test_install_extensions_loads_all(self):
        """install_extensions installs and loads all required extensions."""
        db = duckdb.connect(":memory:")
        try:
            install_extensions(db)
            loaded = {
                row[0]
                for row in db.execute(
                    "SELECT extension_name FROM duckdb_extensions() WHERE loaded = true"
                ).fetchall()
            }
            for ext in REQUIRED_EXTENSIONS:
                # DuckDB registers 'postgres' as 'postgres_scanner' internally.
                name = "postgres_scanner" if ext == "postgres" else ext
                assert name in loaded, f"Extension {ext!r} not loaded"
        finally:
            db.close()

    def test_install_extensions_idempotent(self):
        """Calling install_extensions twice does not raise."""
        db = duckdb.connect(":memory:")
        try:
            install_extensions(db)
            install_extensions(db)  # second call should be a no-op
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════════
#  B.2  create_pg_secret
# ═══════════════════════════════════════════════════════════════════════════
class TestCreatePgSecret:
    """Tests for create_pg_secret()."""

    def _setup_db(self) -> duckdb.DuckDBPyConnection:
        db = duckdb.connect(":memory:")
        db.execute("INSTALL postgres; LOAD postgres")
        return db

    def test_creates_secret(self):
        """A PostgreSQL secret is created with the correct name."""
        db = self._setup_db()
        try:
            create_pg_secret(
                db,
                host="localhost",
                port=5432,
                database="testdb",
                user="testuser",
                token="fake-token-123",
            )
            secrets = db.execute("SELECT name, type FROM duckdb_secrets()").fetchall()
            names = {row[0] for row in secrets}
            assert "pg_catalog_secret" in names
        finally:
            db.close()

    def test_create_or_replace_idempotent(self):
        """Calling create_pg_secret twice replaces the secret without error."""
        db = self._setup_db()
        try:
            for _ in range(2):
                create_pg_secret(
                    db,
                    host="localhost",
                    port=5432,
                    database="testdb",
                    user="testuser",
                    token="token-v1",
                )
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════════
#  B.3  create_azure_secret
# ═══════════════════════════════════════════════════════════════════════════
class TestCreateAzureSecret:
    """Tests for create_azure_secret()."""

    def _setup_db(self) -> duckdb.DuckDBPyConnection:
        db = duckdb.connect(":memory:")
        db.execute("INSTALL azure; LOAD azure")
        return db

    def test_creates_secret(self):
        """An Azure storage secret is created with the correct name."""
        db = self._setup_db()
        try:
            create_azure_secret(db, account_name="stompz1")
            secrets = db.execute("SELECT name, type FROM duckdb_secrets()").fetchall()
            names = {row[0] for row in secrets}
            assert "azure_storage_secret" in names
        finally:
            db.close()

    def test_create_or_replace_idempotent(self):
        """Calling create_azure_secret twice replaces without error."""
        db = self._setup_db()
        try:
            for _ in range(2):
                create_azure_secret(db, account_name="stompz1")
        finally:
            db.close()

    def test_with_managed_identity_client_id(self):
        """When access_token is set, uses access_token provider."""
        db = self._setup_db()
        try:
            create_azure_secret(
                db,
                account_name="stompz1",
                access_token="fake-storage-token",
            )
            raw = db.execute("SELECT secret_string FROM duckdb_secrets()").fetchone()
            assert raw is not None
            secret_str = raw[0]
            assert "provider=access_token" in secret_str
            assert "azure_storage_secret" in secret_str
        finally:
            db.close()

    def test_without_managed_identity_uses_credential_chain(self):
        """Without access_token, credential_chain provider is used."""
        db = self._setup_db()
        try:
            create_azure_secret(db, account_name="stompz1")
            raw = db.execute("SELECT secret_string FROM duckdb_secrets()").fetchone()
            assert raw is not None
            secret_str = raw[0]
            assert "provider=credential_chain" in secret_str
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════════
#  B.4  attach_ducklake  (requires running PostgreSQL — skip if unavailable)
# ═══════════════════════════════════════════════════════════════════════════
class TestAttachDucklake:
    """Tests for attach_ducklake().

    These tests require a running PostgreSQL server, so they are skipped by
    default.  The function's SQL construction is validated via string
    inspection in unit tests below.
    """

    def test_attach_fails_without_pg(self):
        """attach_ducklake raises when no PostgreSQL server is available."""
        db = duckdb.connect(":memory:")
        try:
            install_extensions(db)
            create_pg_secret(
                db,
                host="localhost",
                port=5432,
                database="nonexistent",
                user="nobody",
                token="fake",
            )
            with pytest.raises(duckdb.Error):
                attach_ducklake(
                    db,
                    host="localhost",
                    port=5432,
                    database="nonexistent",
                    user="nobody",
                    alias="test_dl",
                    data_path="az://bucket/",
                )
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════════
#  B.5  initialize_ducklake  (orchestration)
# ═══════════════════════════════════════════════════════════════════════════
class TestInitializeDucklake:
    """Tests for initialize_ducklake() orchestration."""

    def test_initialize_installs_extensions_and_secrets(self):
        """initialize_ducklake installs extensions and creates secrets.

        It will fail at ATTACH (no PG server), but extensions + secrets
        should be set up before that.
        """
        from lakehouse.config import ServerConfig

        config = ServerConfig(
            azure_storage_account="stompz1",
            ducklake_data_path="az://data/",
            pg_host="localhost",
            pg_port=5432,
            pg_database="testdb",
            pg_user="testuser",
            ducklake_alias="test_dl",
        )
        db = duckdb.connect(":memory:")
        try:
            with pytest.raises(duckdb.Error):
                initialize_ducklake(db, config, token="fake-token")

            # Extensions should be loaded (they were installed before ATTACH failed)
            loaded = {
                row[0]
                for row in db.execute(
                    "SELECT extension_name FROM duckdb_extensions() WHERE loaded = true"
                ).fetchall()
            }
            for ext in REQUIRED_EXTENSIONS:
                # DuckDB registers 'postgres' as 'postgres_scanner' internally.
                name = "postgres_scanner" if ext == "postgres" else ext
                assert name in loaded

            # Secrets should exist (created before ATTACH failed)
            secrets = {
                row[0] for row in db.execute("SELECT name FROM duckdb_secrets()").fetchall()
            }
            assert "pg_catalog_secret" in secrets
            assert "azure_storage_secret" in secrets
        finally:
            db.close()

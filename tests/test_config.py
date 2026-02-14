"""Tests for lakehouse.config — ServerConfig Pydantic Settings."""

from __future__ import annotations

from pathlib import Path

import pytest

from lakehouse.config import ServerConfig


# ═══════════════════════════════════════════════════════════════════════════
#  Defaults
# ═══════════════════════════════════════════════════════════════════════════
class TestConfigDefaults:
    """Verify all default values match the documented specification."""

    def test_host(self):
        cfg = ServerConfig()
        assert cfg.host == "0.0.0.0"

    def test_port(self):
        cfg = ServerConfig()
        assert cfg.port == 31337

    def test_database(self):
        cfg = ServerConfig()
        assert cfg.database == ":memory:"

    def test_read_only(self):
        cfg = ServerConfig()
        assert cfg.read_only is False

    def test_username(self):
        cfg = ServerConfig()
        assert cfg.username == "lakehouse"

    def test_password_empty(self):
        cfg = ServerConfig()
        assert cfg.password == ""

    def test_secret_key_auto_generated(self):
        cfg = ServerConfig()
        assert cfg.secret_key.startswith("SECRET-")

    def test_secret_key_unique(self):
        cfg1 = ServerConfig()
        cfg2 = ServerConfig()
        assert cfg1.secret_key != cfg2.secret_key

    def test_jwt_issuer(self):
        cfg = ServerConfig()
        assert cfg.jwt_issuer == "lakehouse"

    def test_tls_disabled(self):
        cfg = ServerConfig()
        assert cfg.tls_cert_file is None
        assert cfg.tls_key_file is None
        assert cfg.tls_enabled is False

    def test_mtls_disabled(self):
        cfg = ServerConfig()
        assert cfg.mtls_ca_cert_file is None
        assert cfg.mtls_enabled is False

    def test_health_check_port(self):
        cfg = ServerConfig()
        assert cfg.health_check_port == 8081

    def test_health_check_enabled(self):
        cfg = ServerConfig()
        assert cfg.health_check_enabled is True

    def test_health_poll_interval(self):
        cfg = ServerConfig()
        assert cfg.health_poll_interval == 5.0

    def test_print_queries(self):
        cfg = ServerConfig()
        assert cfg.print_queries is False

    def test_log_level(self):
        cfg = ServerConfig()
        assert cfg.log_level == "INFO"

    def test_init_sql(self):
        cfg = ServerConfig()
        assert cfg.init_sql == ""

    def test_init_sql_file(self):
        cfg = ServerConfig()
        assert cfg.init_sql_file is None


# ═══════════════════════════════════════════════════════════════════════════
#  Explicit values
# ═══════════════════════════════════════════════════════════════════════════
class TestConfigExplicit:
    """Test passing explicit values."""

    def test_custom_port(self):
        cfg = ServerConfig(port=9090)
        assert cfg.port == 9090

    def test_custom_host(self):
        cfg = ServerConfig(host="127.0.0.1")
        assert cfg.host == "127.0.0.1"

    def test_custom_database(self):
        cfg = ServerConfig(database="/tmp/test.duckdb")
        assert cfg.database == "/tmp/test.duckdb"

    def test_read_only(self):
        cfg = ServerConfig(read_only=True)
        assert cfg.read_only is True

    def test_explicit_secret_key(self):
        cfg = ServerConfig(secret_key="my-key-32-chars-long-at-minimum!")
        assert cfg.secret_key == "my-key-32-chars-long-at-minimum!"

    def test_custom_jwt_issuer(self):
        cfg = ServerConfig(jwt_issuer="my-server")
        assert cfg.jwt_issuer == "my-server"

    def test_print_queries(self):
        cfg = ServerConfig(print_queries=True)
        assert cfg.print_queries is True

    def test_custom_log_level(self):
        cfg = ServerConfig(log_level="DEBUG")
        assert cfg.log_level == "DEBUG"

    def test_init_sql(self):
        cfg = ServerConfig(init_sql="CREATE TABLE t (x INT)")
        assert cfg.init_sql == "CREATE TABLE t (x INT)"


# ═══════════════════════════════════════════════════════════════════════════
#  Environment variable loading
# ═══════════════════════════════════════════════════════════════════════════
class TestConfigFromEnv:
    """Test loading from LAKEHOUSE_ environment variables."""

    def test_port_from_env(self, monkeypatch):
        monkeypatch.setenv("LAKEHOUSE_PORT", "8888")
        cfg = ServerConfig()
        assert cfg.port == 8888

    def test_host_from_env(self, monkeypatch):
        monkeypatch.setenv("LAKEHOUSE_HOST", "192.168.1.1")
        cfg = ServerConfig()
        assert cfg.host == "192.168.1.1"

    def test_database_from_env(self, monkeypatch):
        monkeypatch.setenv("LAKEHOUSE_DATABASE", "/data/mydb.duckdb")
        cfg = ServerConfig()
        assert cfg.database == "/data/mydb.duckdb"

    def test_password_from_env(self, monkeypatch):
        monkeypatch.setenv("LAKEHOUSE_PASSWORD", "s3cret")
        cfg = ServerConfig()
        assert cfg.password == "s3cret"

    def test_log_level_from_env(self, monkeypatch):
        monkeypatch.setenv("LAKEHOUSE_LOG_LEVEL", "debug")
        cfg = ServerConfig()
        assert cfg.log_level == "DEBUG"  # normalised to uppercase

    def test_health_check_enabled_from_env(self, monkeypatch):
        monkeypatch.setenv("LAKEHOUSE_HEALTH_CHECK_ENABLED", "false")
        cfg = ServerConfig()
        assert cfg.health_check_enabled is False

    def test_print_queries_from_env(self, monkeypatch):
        monkeypatch.setenv("LAKEHOUSE_PRINT_QUERIES", "true")
        cfg = ServerConfig()
        assert cfg.print_queries is True


# ═══════════════════════════════════════════════════════════════════════════
#  Validation
# ═══════════════════════════════════════════════════════════════════════════
class TestConfigValidation:
    """Test Pydantic validators."""

    def test_invalid_log_level(self):
        with pytest.raises(ValueError, match="Invalid log level"):
            ServerConfig(log_level="VERBOSE")

    def test_log_level_case_insensitive(self):
        cfg = ServerConfig(log_level="warning")
        assert cfg.log_level == "WARNING"

    def test_tls_cert_without_key(self):
        with pytest.raises(
            ValueError, match="tls_cert_file and tls_key_file must be set together"
        ):
            ServerConfig(tls_cert_file=Path("/cert.pem"))

    def test_tls_key_without_cert(self):
        with pytest.raises(
            ValueError, match="tls_cert_file and tls_key_file must be set together"
        ):
            ServerConfig(tls_key_file=Path("/key.pem"))

    def test_tls_both_set(self):
        cfg = ServerConfig(
            tls_cert_file=Path("/cert.pem"),
            tls_key_file=Path("/key.pem"),
        )
        assert cfg.tls_enabled is True
        assert cfg.mtls_enabled is False

    def test_mtls_enabled(self):
        cfg = ServerConfig(
            tls_cert_file=Path("/cert.pem"),
            tls_key_file=Path("/key.pem"),
            mtls_ca_cert_file=Path("/ca.pem"),
        )
        assert cfg.mtls_enabled is True


# ═══════════════════════════════════════════════════════════════════════════
#  Derived properties
# ═══════════════════════════════════════════════════════════════════════════
class TestConfigProperties:
    """Test computed properties."""

    def test_location_grpc(self):
        cfg = ServerConfig(host="0.0.0.0", port=31337)
        assert cfg.location == "grpc://0.0.0.0:31337"

    def test_location_grpc_tls(self):
        cfg = ServerConfig(
            host="0.0.0.0",
            port=31337,
            tls_cert_file=Path("/cert.pem"),
            tls_key_file=Path("/key.pem"),
        )
        assert cfg.location == "grpc+tls://0.0.0.0:31337"

    def test_tls_enabled_false(self):
        cfg = ServerConfig()
        assert cfg.tls_enabled is False

    def test_tls_enabled_true(self):
        cfg = ServerConfig(
            tls_cert_file=Path("/cert.pem"),
            tls_key_file=Path("/key.pem"),
        )
        assert cfg.tls_enabled is True

    def test_mtls_enabled_without_tls(self):
        """mTLS requires TLS to also be enabled."""
        cfg = ServerConfig(mtls_ca_cert_file=Path("/ca.pem"))
        assert cfg.mtls_enabled is False


# ═══════════════════════════════════════════════════════════════════════════
#  DuckLake defaults
# ═══════════════════════════════════════════════════════════════════════════
class TestDuckLakeDefaults:
    """Verify DuckLake fields default to empty / disabled."""

    def test_azure_storage_account(self):
        cfg = ServerConfig()
        assert cfg.azure_storage_account == ""

    def test_ducklake_data_path(self):
        cfg = ServerConfig()
        assert cfg.ducklake_data_path == ""

    def test_pg_host(self):
        cfg = ServerConfig()
        assert cfg.pg_host == ""

    def test_pg_port(self):
        cfg = ServerConfig()
        assert cfg.pg_port == 5432

    def test_pg_database(self):
        cfg = ServerConfig()
        assert cfg.pg_database == ""

    def test_pg_user(self):
        cfg = ServerConfig()
        assert cfg.pg_user == ""

    def test_ducklake_alias(self):
        cfg = ServerConfig()
        assert cfg.ducklake_alias == "lakehouse"

    def test_pg_token_refresh_minutes(self):
        cfg = ServerConfig()
        assert cfg.pg_token_refresh_minutes == 5.0

    def test_ducklake_enabled_false(self):
        cfg = ServerConfig()
        assert cfg.ducklake_enabled is False


# ═══════════════════════════════════════════════════════════════════════════
#  DuckLake explicit values
# ═══════════════════════════════════════════════════════════════════════════
class TestDuckLakeExplicit:
    """Test passing explicit DuckLake values (all required together)."""

    def _full_ducklake_kwargs(self, **overrides):
        defaults = {
            "azure_storage_account": "stompz1",
            "ducklake_data_path": "az://my-container/",
            "pg_host": "mydb.postgres.database.azure.com",
            "pg_database": "ducklake_catalog",
            "pg_user": "admin@mydb",
        }
        defaults.update(overrides)
        return defaults

    def test_all_ducklake_fields_set(self):
        cfg = ServerConfig(**self._full_ducklake_kwargs())
        assert cfg.azure_storage_account == "stompz1"
        assert cfg.ducklake_data_path == "az://my-container/"
        assert cfg.pg_host == "mydb.postgres.database.azure.com"
        assert cfg.pg_database == "ducklake_catalog"
        assert cfg.pg_user == "admin@mydb"
        assert cfg.ducklake_enabled is True

    def test_custom_pg_port(self):
        cfg = ServerConfig(**self._full_ducklake_kwargs(pg_port=5433))
        assert cfg.pg_port == 5433

    def test_custom_ducklake_alias(self):
        cfg = ServerConfig(**self._full_ducklake_kwargs(ducklake_alias="my_ducklake"))
        assert cfg.ducklake_alias == "my_ducklake"

    def test_custom_token_refresh(self):
        cfg = ServerConfig(**self._full_ducklake_kwargs(pg_token_refresh_minutes=10.0))
        assert cfg.pg_token_refresh_minutes == 10.0


# ═══════════════════════════════════════════════════════════════════════════
#  DuckLake from environment variables
# ═══════════════════════════════════════════════════════════════════════════
class TestDuckLakeFromEnv:
    """Test loading DuckLake fields from LAKEHOUSE_ environment variables."""

    def _set_full_ducklake_env(self, monkeypatch):
        monkeypatch.setenv("LAKEHOUSE_AZURE_STORAGE_ACCOUNT", "stompz1")
        monkeypatch.setenv("LAKEHOUSE_DUCKLAKE_DATA_PATH", "az://data/")
        monkeypatch.setenv("LAKEHOUSE_PG_HOST", "pg.azure.com")
        monkeypatch.setenv("LAKEHOUSE_PG_DATABASE", "ducklake")
        monkeypatch.setenv("LAKEHOUSE_PG_USER", "admin")

    def test_ducklake_from_env(self, monkeypatch):
        self._set_full_ducklake_env(monkeypatch)
        cfg = ServerConfig()
        assert cfg.azure_storage_account == "stompz1"
        assert cfg.ducklake_data_path == "az://data/"
        assert cfg.pg_host == "pg.azure.com"
        assert cfg.pg_database == "ducklake"
        assert cfg.pg_user == "admin"
        assert cfg.ducklake_enabled is True

    def test_pg_port_from_env(self, monkeypatch):
        self._set_full_ducklake_env(monkeypatch)
        monkeypatch.setenv("LAKEHOUSE_PG_PORT", "5433")
        cfg = ServerConfig()
        assert cfg.pg_port == 5433

    def test_ducklake_alias_from_env(self, monkeypatch):
        self._set_full_ducklake_env(monkeypatch)
        monkeypatch.setenv("LAKEHOUSE_DUCKLAKE_ALIAS", "my_lake")
        cfg = ServerConfig()
        assert cfg.ducklake_alias == "my_lake"

    def test_pg_token_refresh_from_env(self, monkeypatch):
        self._set_full_ducklake_env(monkeypatch)
        monkeypatch.setenv("LAKEHOUSE_PG_TOKEN_REFRESH_MINUTES", "10")
        cfg = ServerConfig()
        assert cfg.pg_token_refresh_minutes == 10.0


# ═══════════════════════════════════════════════════════════════════════════
#  DuckLake validation
# ═══════════════════════════════════════════════════════════════════════════
class TestDuckLakeValidation:
    """Test DuckLake-specific validators."""

    def _full_ducklake_kwargs(self, **overrides):
        defaults = {
            "azure_storage_account": "stompz1",
            "ducklake_data_path": "az://my-container/",
            "pg_host": "localhost",
            "pg_database": "ducklake",
            "pg_user": "admin",
        }
        defaults.update(overrides)
        return defaults

    # all-or-nothing
    def test_partial_ducklake_missing_pg_host(self):
        with pytest.raises(ValueError, match="DuckLake configuration is incomplete"):
            ServerConfig(
                azure_storage_account="stompz1",
                ducklake_data_path="az://c/",
                pg_database="db",
                pg_user="u",
            )

    def test_partial_ducklake_missing_data_path(self):
        with pytest.raises(ValueError, match="DuckLake configuration is incomplete"):
            ServerConfig(
                azure_storage_account="stompz1",
                pg_host="localhost",
                pg_database="db",
                pg_user="u",
            )

    def test_partial_ducklake_only_storage_account(self):
        with pytest.raises(ValueError, match="DuckLake configuration is incomplete"):
            ServerConfig(azure_storage_account="stompz1")

    # ducklake_alias
    def test_invalid_alias_starts_with_digit(self):
        with pytest.raises(ValueError, match="valid SQL identifier"):
            ServerConfig(**self._full_ducklake_kwargs(ducklake_alias="1bad"))

    def test_invalid_alias_has_spaces(self):
        with pytest.raises(ValueError, match="valid SQL identifier"):
            ServerConfig(**self._full_ducklake_kwargs(ducklake_alias="my lake"))

    def test_invalid_alias_has_hyphen(self):
        with pytest.raises(ValueError, match="valid SQL identifier"):
            ServerConfig(**self._full_ducklake_kwargs(ducklake_alias="my-lake"))

    def test_valid_alias_underscore(self):
        cfg = ServerConfig(**self._full_ducklake_kwargs(ducklake_alias="_my_lake_2"))
        assert cfg.ducklake_alias == "_my_lake_2"

    def test_empty_alias_allowed_when_no_ducklake(self):
        """Empty alias is fine if DuckLake is not configured."""
        cfg = ServerConfig(ducklake_alias="")
        assert cfg.ducklake_alias == ""

    # ducklake_data_path
    def test_data_path_must_end_with_slash(self):
        with pytest.raises(ValueError, match="must end with '/'"):
            ServerConfig(**self._full_ducklake_kwargs(ducklake_data_path="az://container"))

    def test_data_path_with_subfolder(self):
        cfg = ServerConfig(
            **self._full_ducklake_kwargs(ducklake_data_path="az://container/subfolder/")
        )
        assert cfg.ducklake_data_path == "az://container/subfolder/"

    # pg_port
    def test_pg_port_zero(self):
        with pytest.raises(ValueError, match="pg_port must be between 1 and 65535"):
            ServerConfig(**self._full_ducklake_kwargs(pg_port=0))

    def test_pg_port_too_high(self):
        with pytest.raises(ValueError, match="pg_port must be between 1 and 65535"):
            ServerConfig(**self._full_ducklake_kwargs(pg_port=70000))

    def test_pg_port_max_valid(self):
        cfg = ServerConfig(**self._full_ducklake_kwargs(pg_port=65535))
        assert cfg.pg_port == 65535

    # pg_token_refresh_minutes
    def test_token_refresh_zero(self):
        with pytest.raises(ValueError, match="pg_token_refresh_minutes must be > 0"):
            ServerConfig(**self._full_ducklake_kwargs(pg_token_refresh_minutes=0))

    def test_token_refresh_negative(self):
        with pytest.raises(ValueError, match="pg_token_refresh_minutes must be > 0"):
            ServerConfig(**self._full_ducklake_kwargs(pg_token_refresh_minutes=-1.0))

    # SQL injection safety — pg fields
    def test_pg_host_no_single_quote(self):
        with pytest.raises(ValueError, match="single-quotes, semicolons, or spaces"):
            ServerConfig(**self._full_ducklake_kwargs(pg_host="host'inject"))

    def test_pg_database_no_semicolon(self):
        with pytest.raises(ValueError, match="single-quotes, semicolons, or spaces"):
            ServerConfig(**self._full_ducklake_kwargs(pg_database="db;DROP TABLE"))

    def test_pg_user_no_single_quote(self):
        with pytest.raises(ValueError, match="single-quotes, semicolons, or spaces"):
            ServerConfig(**self._full_ducklake_kwargs(pg_user="user'name"))

    def test_pg_host_no_spaces(self):
        with pytest.raises(ValueError, match="single-quotes, semicolons, or spaces"):
            ServerConfig(**self._full_ducklake_kwargs(pg_host="host inject"))

    # SQL injection safety — data path
    def test_data_path_no_single_quote(self):
        with pytest.raises(ValueError, match="single-quotes or semicolons"):
            ServerConfig(**self._full_ducklake_kwargs(ducklake_data_path="az://c'/"))

    def test_data_path_no_semicolon(self):
        with pytest.raises(ValueError, match="single-quotes or semicolons"):
            ServerConfig(**self._full_ducklake_kwargs(ducklake_data_path="az://c;/"))

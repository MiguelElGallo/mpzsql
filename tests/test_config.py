"""
Tests for config.py module to improve code coverage.

This test suite covers the ServerConfig class and its validation methods,
focusing on edge cases and property methods that might not be fully tested.
"""

import pytest
from pathlib import Path
from pydantic import ValidationError

from mpzsql.config import ServerConfig


class TestServerConfigValidation:
    """Test ServerConfig validation methods."""

    def test_validate_backend_valid(self):
        """Test backend validation with valid backends."""
        config = ServerConfig(secret_key="test_key", backend="duckdb")
        assert config.backend == "duckdb"
        
        config = ServerConfig(secret_key="test_key", backend="sqlite", database="test.db")
        assert config.backend == "sqlite"

    def test_validate_backend_invalid(self):
        """Test backend validation with invalid backend."""
        with pytest.raises(ValidationError) as exc_info:
            ServerConfig(secret_key="test_key", backend="invalid_backend")
        
        assert "Backend must be 'duckdb' or 'sqlite'" in str(exc_info.value)

    def test_validate_tls_cert_nonexistent_file(self):
        """Test TLS cert validation with nonexistent file."""
        with pytest.raises(ValidationError) as exc_info:
            ServerConfig(
                secret_key="test_key",
                tls_cert="/nonexistent/path/cert.pem"
            )
        
        assert "TLS certificate file not found" in str(exc_info.value)

    def test_validate_tls_cert_valid_file(self):
        """Test TLS cert validation with valid file."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.pem', delete=False) as cert_f:
            cert_f.write(b'fake cert content')
            cert_path = cert_f.name
            
        with tempfile.NamedTemporaryFile(suffix='.pem', delete=False) as key_f:
            key_f.write(b'fake key content')
            key_path = key_f.name
        
        try:
            config = ServerConfig(
                secret_key="test_key",
                tls_cert=cert_path,
                tls_key=key_path
            )
            assert config.tls_cert == cert_path
        finally:
            Path(cert_path).unlink()
            Path(key_path).unlink()

    def test_validate_tls_key_nonexistent_file(self):
        """Test TLS key validation with nonexistent file."""
        with pytest.raises(ValidationError) as exc_info:
            ServerConfig(
                secret_key="test_key",
                tls_key="/nonexistent/path/key.pem"
            )
        
        assert "TLS key file not found" in str(exc_info.value)

    def test_validate_tls_key_valid_file(self):
        """Test TLS key validation with valid file."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.pem', delete=False) as cert_f:
            cert_f.write(b'fake cert content')
            cert_path = cert_f.name
            
        with tempfile.NamedTemporaryFile(suffix='.pem', delete=False) as key_f:
            key_f.write(b'fake key content')
            key_path = key_f.name
        
        try:
            config = ServerConfig(
                secret_key="test_key",
                tls_cert=cert_path,
                tls_key=key_path
            )
            assert config.tls_key == key_path
        finally:
            Path(cert_path).unlink()
            Path(key_path).unlink()

    def test_validate_mtls_ca_nonexistent_file(self):
        """Test mTLS CA validation with nonexistent file."""
        with pytest.raises(ValidationError) as exc_info:
            ServerConfig(
                secret_key="test_key",
                mtls_ca="/nonexistent/path/ca.pem"
            )
        
        assert "mTLS CA certificate file not found" in str(exc_info.value)

    def test_validate_mtls_ca_valid_file(self):
        """Test mTLS CA validation with valid file."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.pem', delete=False) as f:
            f.write(b'fake ca content')
            ca_path = f.name
        
        try:
            config = ServerConfig(
                secret_key="test_key",
                mtls_ca=ca_path
            )
            assert config.mtls_ca == ca_path
        finally:
            Path(ca_path).unlink()

    def test_validate_config_sqlite_without_database(self):
        """Test SQLite backend validation without database file."""
        with pytest.raises(ValidationError) as exc_info:
            ServerConfig(
                secret_key="test_key",
                backend="sqlite",
                database=None
            )
        
        assert "SQLite backend requires a database file" in str(exc_info.value)

    def test_validate_config_sqlite_with_database(self):
        """Test SQLite backend validation with database file."""
        config = ServerConfig(
            secret_key="test_key",
            backend="sqlite",
            database="test.db"
        )
        assert config.backend == "sqlite"
        assert config.database == "test.db"

    def test_validate_config_tls_incomplete_cert_only(self):
        """Test TLS validation with only certificate provided."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.pem', delete=False) as f:
            f.write(b'fake cert content')
            cert_path = f.name
        
        try:
            with pytest.raises(ValidationError) as exc_info:
                ServerConfig(
                    secret_key="test_key",
                    tls_cert=cert_path,
                    tls_key=None
                )
            
            assert "Both TLS certificate and key must be provided together" in str(exc_info.value)
        finally:
            Path(cert_path).unlink()

    def test_validate_config_tls_incomplete_key_only(self):
        """Test TLS validation with only key provided."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.pem', delete=False) as f:
            f.write(b'fake key content')
            key_path = f.name
        
        try:
            with pytest.raises(ValidationError) as exc_info:
                ServerConfig(
                    secret_key="test_key",
                    tls_cert=None,
                    tls_key=key_path
                )
            
            assert "Both TLS certificate and key must be provided together" in str(exc_info.value)
        finally:
            Path(key_path).unlink()


class TestServerConfigProperties:
    """Test ServerConfig property methods."""

    def test_is_tls_enabled_false(self):
        """Test is_tls_enabled returns False when no TLS config."""
        config = ServerConfig(secret_key="test_key")
        assert config.is_tls_enabled is False

    def test_is_tls_enabled_true(self):
        """Test is_tls_enabled returns True when TLS is configured."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.pem', delete=False) as cert_f:
            cert_f.write(b'fake cert')
            cert_path = cert_f.name
        
        with tempfile.NamedTemporaryFile(suffix='.pem', delete=False) as key_f:
            key_f.write(b'fake key')
            key_path = key_f.name
        
        try:
            config = ServerConfig(
                secret_key="test_key",
                tls_cert=cert_path,
                tls_key=key_path
            )
            assert config.is_tls_enabled is True
        finally:
            Path(cert_path).unlink()
            Path(key_path).unlink()

    def test_is_mtls_enabled_false(self):
        """Test is_mtls_enabled returns False when no mTLS config."""
        config = ServerConfig(secret_key="test_key")
        assert config.is_mtls_enabled is False

    def test_is_mtls_enabled_true(self):
        """Test is_mtls_enabled returns True when mTLS is configured."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.pem', delete=False) as ca_f:
            ca_f.write(b'fake ca')
            ca_path = ca_f.name
        
        try:
            config = ServerConfig(
                secret_key="test_key",
                mtls_ca=ca_path
            )
            assert config.is_mtls_enabled is True
        finally:
            Path(ca_path).unlink()

    def test_is_auth_enabled_false(self):
        """Test is_auth_enabled returns False when no auth config."""
        config = ServerConfig(secret_key="test_key")
        assert config.is_auth_enabled is False

    def test_is_auth_enabled_true_username_only(self):
        """Test is_auth_enabled with only username fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            ServerConfig(secret_key="test_key", username="testuser")
        
        assert "Password is required when username is provided" in str(exc_info.value)

    def test_is_auth_enabled_true_password_only(self):
        """Test is_auth_enabled returns False with only password."""
        config = ServerConfig(secret_key="test_key", password="testpass")
        assert config.is_auth_enabled is False

    def test_is_auth_enabled_true_both(self):
        """Test is_auth_enabled returns True with both username and password."""
        config = ServerConfig(
            secret_key="test_key", 
            username="testuser", 
            password="testpass"
        )
        assert config.is_auth_enabled is True

    def test_database_url_duckdb_no_database(self):
        """Test database_url for DuckDB without database file."""
        config = ServerConfig(secret_key="test_key", backend="duckdb")
        assert config.database_url == ":memory:"

    def test_database_url_duckdb_with_database(self):
        """Test database_url for DuckDB with database file."""
        config = ServerConfig(
            secret_key="test_key", 
            backend="duckdb", 
            database="test.duckdb"
        )
        assert config.database_url == "test.duckdb"

    def test_database_url_sqlite(self):
        """Test database_url for SQLite."""
        config = ServerConfig(
            secret_key="test_key", 
            backend="sqlite", 
            database="test.db"
        )
        assert config.database_url == "test.db"

    def test_is_postgresql_enabled_false(self):
        """Test is_postgresql_enabled returns False for non-PostgreSQL backends."""
        config = ServerConfig(secret_key="test_key", backend="duckdb")
        assert config.is_postgresql_enabled is False
        
        config = ServerConfig(secret_key="test_key", backend="sqlite", database="test.db")
        assert config.is_postgresql_enabled is False

    def test_is_postgresql_enabled_true(self):
        """Test is_postgresql_enabled returns True when PostgreSQL is configured."""
        config = ServerConfig(
            secret_key="test_key",
            postgresql_server="localhost",
            postgresql_user="testuser", 
            postgresql_password="testpass"
        )
        assert config.is_postgresql_enabled is True

    def test_is_azure_storage_enabled_false(self):
        """Test is_azure_storage_enabled returns False by default."""
        config = ServerConfig(secret_key="test_key")
        assert config.is_azure_storage_enabled is False

    def test_is_azure_storage_enabled_true(self):
        """Test is_azure_storage_enabled returns True when Azure Storage is configured."""
        config = ServerConfig(
            secret_key="test_key",
            azure_storage_account="testaccount",
            azure_storage_container="testcontainer"
        )
        assert config.is_azure_storage_enabled is True

    def test_effective_advertised_hostname_default(self):
        """Test effective_advertised_hostname returns hostname when not set."""
        config = ServerConfig(secret_key="test_key", hostname="test.example.com")
        assert config.effective_advertised_hostname == "test.example.com"

    def test_effective_advertised_hostname_explicit(self):
        """Test effective_advertised_hostname returns advertised_hostname when set."""
        config = ServerConfig(
            secret_key="test_key",
            hostname="internal.example.com",
            advertised_hostname="public.example.com"
        )
        assert config.effective_advertised_hostname == "public.example.com"


class TestServerConfigDefaults:
    """Test ServerConfig default values."""

    def test_default_values(self):
        """Test default configuration values."""
        config = ServerConfig(secret_key="test_key")
        
        assert config.backend == "duckdb"
        assert config.database is None
        assert config.hostname == "localhost"
        assert config.advertised_hostname is None
        assert config.port == 8080
        assert config.username is None
        assert config.password is None
        assert config.secret_key == "test_key"
        assert config.tls_cert is None
        assert config.tls_key is None
        assert config.mtls_ca is None
        assert config.init_sql is None
        assert config.print_queries is False
        assert config.read_only is False
        assert config.postgresql_server is None
        assert config.postgresql_port == 5432
        assert config.postgresql_user is None
        assert config.postgresql_password is None
        assert config.postgresql_catalogdb is None
        assert config.azure_storage_account is None
        assert config.azure_storage_container is None

    def test_required_secret_key(self):
        """Test that secret_key is required."""
        with pytest.raises(ValidationError):
            ServerConfig()

    def test_port_validation_valid(self):
        """Test port validation with valid values."""
        config = ServerConfig(secret_key="test_key", port=1)
        assert config.port == 1
        
        config = ServerConfig(secret_key="test_key", port=65535)
        assert config.port == 65535

    def test_port_validation_invalid_low(self):
        """Test port validation with value too low."""
        with pytest.raises(ValidationError):
            ServerConfig(secret_key="test_key", port=0)

    def test_port_validation_invalid_high(self):
        """Test port validation with value too high."""
        with pytest.raises(ValidationError):
            ServerConfig(secret_key="test_key", port=65536)


if __name__ == "__main__":
    pytest.main(["-v", __file__])
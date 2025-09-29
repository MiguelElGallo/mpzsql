"""
Comprehensive tests for MPZSQL server configuration.

Tests for mpzsql.config module providing ServerConfig validation and properties.
This ensures all configuration validation works correctly and edge cases are handled.
"""

import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from mpzsql.config import ServerConfig


class TestServerConfigDefaults:
    """Test default configuration values."""

    def test_minimal_valid_config(self) -> None:
        """Test minimal valid configuration with required fields only."""
        config = ServerConfig(secret_key="test-secret")
        
        assert config.backend == "duckdb"
        assert config.database is None
        assert config.hostname == "localhost"
        assert config.advertised_hostname is None
        assert config.port == 8080
        assert config.username is None
        assert config.password is None
        assert config.secret_key == "test-secret"
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

    def test_all_fields_specified(self) -> None:
        """Test configuration with all fields specified."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create temporary files for TLS testing
            cert_path = Path(temp_dir) / "cert.pem"
            key_path = Path(temp_dir) / "key.pem"
            ca_path = Path(temp_dir) / "ca.pem"
            
            cert_path.write_text("dummy cert")
            key_path.write_text("dummy key")
            ca_path.write_text("dummy ca")
            
            config = ServerConfig(
                backend="sqlite",
                database="/tmp/test.db",
                hostname="0.0.0.0",
                advertised_hostname="example.com",
                port=9090,
                username="testuser",
                password="testpass",
                secret_key="test-secret-123",
                tls_cert=str(cert_path),
                tls_key=str(key_path),
                mtls_ca=str(ca_path),
                init_sql="CREATE TABLE test (id INTEGER);",
                print_queries=True,
                read_only=True,
                postgresql_server="pg.example.com",
                postgresql_port=5433,
                postgresql_user="pguser",
                postgresql_password="pgpass",
                postgresql_catalogdb="catalog",
                azure_storage_account="testaccount",
                azure_storage_container="testcontainer",
            )
            
            assert config.backend == "sqlite"
            assert config.database == "/tmp/test.db"
            assert config.hostname == "0.0.0.0"
            assert config.advertised_hostname == "example.com"
            assert config.port == 9090
            assert config.username == "testuser"
            assert config.password == "testpass"
            assert config.secret_key == "test-secret-123"
            assert config.tls_cert == str(cert_path)
            assert config.tls_key == str(key_path)
            assert config.mtls_ca == str(ca_path)
            assert config.init_sql == "CREATE TABLE test (id INTEGER);"
            assert config.print_queries is True
            assert config.read_only is True
            assert config.postgresql_server == "pg.example.com"
            assert config.postgresql_port == 5433
            assert config.postgresql_user == "pguser"
            assert config.postgresql_password == "pgpass"
            assert config.postgresql_catalogdb == "catalog"
            assert config.azure_storage_account == "testaccount"
            assert config.azure_storage_container == "testcontainer"


class TestServerConfigFieldValidators:
    """Test individual field validators."""

    def test_backend_validator_valid_values(self) -> None:
        """Test backend validator accepts valid values."""
        # Test duckdb
        config = ServerConfig(backend="duckdb", secret_key="test")
        assert config.backend == "duckdb"
        
        # Test sqlite
        config = ServerConfig(backend="sqlite", database="test.db", secret_key="test")
        assert config.backend == "sqlite"

    def test_backend_validator_invalid_values(self) -> None:
        """Test backend validator rejects invalid values."""
        with pytest.raises(ValidationError) as exc_info:
            ServerConfig(backend="invalid", secret_key="test")
        
        assert "Backend must be 'duckdb' or 'sqlite'" in str(exc_info.value)

    def test_port_validator_valid_range(self) -> None:
        """Test port validator accepts valid port numbers."""
        # Test minimum valid port
        config = ServerConfig(port=1, secret_key="test")
        assert config.port == 1
        
        # Test maximum valid port
        config = ServerConfig(port=65535, secret_key="test")
        assert config.port == 65535
        
        # Test typical port
        config = ServerConfig(port=8080, secret_key="test")
        assert config.port == 8080

    def test_port_validator_invalid_range(self) -> None:
        """Test port validator rejects invalid port numbers."""
        # Test port too low
        with pytest.raises(ValidationError):
            ServerConfig(port=0, secret_key="test")
        
        # Test port too high
        with pytest.raises(ValidationError):
            ServerConfig(port=65536, secret_key="test")
        
        # Test negative port
        with pytest.raises(ValidationError):
            ServerConfig(port=-1, secret_key="test")

    def test_postgresql_port_validator(self) -> None:
        """Test PostgreSQL port validator."""
        # Valid port
        config = ServerConfig(postgresql_port=5432, secret_key="test")
        assert config.postgresql_port == 5432
        
        # Invalid port
        with pytest.raises(ValidationError):
            ServerConfig(postgresql_port=0, secret_key="test")

    def test_tls_cert_validator_existing_file(self) -> None:
        """Test TLS certificate validator with existing file (requires both cert and key)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_path = Path(temp_dir) / "cert.pem"
            key_path = Path(temp_dir) / "key.pem"
            
            cert_path.write_text("dummy cert")
            key_path.write_text("dummy key")
            
            # Both cert and key must be provided together
            config = ServerConfig(
                tls_cert=str(cert_path),
                tls_key=str(key_path),
                secret_key="test"
            )
            assert config.tls_cert == str(cert_path)

    def test_tls_cert_validator_nonexistent_file(self) -> None:
        """Test TLS certificate validator with nonexistent file."""
        with pytest.raises(ValidationError) as exc_info:
            ServerConfig(tls_cert="/nonexistent/cert.pem", secret_key="test")
        
        assert "TLS certificate file not found" in str(exc_info.value)

    def test_tls_key_validator_existing_file(self) -> None:
        """Test TLS key validator with existing file (requires both cert and key)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_path = Path(temp_dir) / "cert.pem"
            key_path = Path(temp_dir) / "key.pem"
            
            cert_path.write_text("dummy cert")
            key_path.write_text("dummy key")
            
            # Both cert and key must be provided together
            config = ServerConfig(
                tls_cert=str(cert_path),
                tls_key=str(key_path),
                secret_key="test"
            )
            assert config.tls_key == str(key_path)

    def test_tls_key_validator_nonexistent_file(self) -> None:
        """Test TLS key validator with nonexistent file."""
        with pytest.raises(ValidationError) as exc_info:
            ServerConfig(tls_key="/nonexistent/key.pem", secret_key="test")
        
        assert "TLS key file not found" in str(exc_info.value)

    def test_mtls_ca_validator_existing_file(self) -> None:
        """Test mTLS CA validator with existing file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            temp_file.write("dummy ca")
            temp_path = temp_file.name
        
        try:
            config = ServerConfig(mtls_ca=temp_path, secret_key="test")
            assert config.mtls_ca == temp_path
        finally:
            Path(temp_path).unlink()

    def test_mtls_ca_validator_nonexistent_file(self) -> None:
        """Test mTLS CA validator with nonexistent file."""
        with pytest.raises(ValidationError) as exc_info:
            ServerConfig(mtls_ca="/nonexistent/ca.pem", secret_key="test")
        
        assert "mTLS CA certificate file not found" in str(exc_info.value)


class TestServerConfigCrossFieldValidation:
    """Test cross-field validation in model_validator."""

    def test_sqlite_requires_database(self) -> None:
        """Test that SQLite backend requires a database file."""
        with pytest.raises(ValidationError) as exc_info:
            ServerConfig(backend="sqlite", secret_key="test")
        
        assert "SQLite backend requires a database file" in str(exc_info.value)

    def test_sqlite_with_database_valid(self) -> None:
        """Test that SQLite backend with database is valid."""
        config = ServerConfig(backend="sqlite", database="test.db", secret_key="test")
        assert config.backend == "sqlite"
        assert config.database == "test.db"

    def test_duckdb_without_database_valid(self) -> None:
        """Test that DuckDB backend without database is valid."""
        config = ServerConfig(backend="duckdb", secret_key="test")
        assert config.backend == "duckdb"
        assert config.database is None

    def test_tls_cert_without_key_invalid(self) -> None:
        """Test that TLS certificate without key is invalid."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            temp_file.write("dummy cert")
            temp_path = temp_file.name
        
        try:
            with pytest.raises(ValidationError) as exc_info:
                ServerConfig(tls_cert=temp_path, secret_key="test")
            
            assert "Both TLS certificate and key must be provided together" in str(exc_info.value)
        finally:
            Path(temp_path).unlink()

    def test_tls_key_without_cert_invalid(self) -> None:
        """Test that TLS key without certificate is invalid."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            temp_file.write("dummy key")
            temp_path = temp_file.name
        
        try:
            with pytest.raises(ValidationError) as exc_info:
                ServerConfig(tls_key=temp_path, secret_key="test")
            
            assert "Both TLS certificate and key must be provided together" in str(exc_info.value)
        finally:
            Path(temp_path).unlink()

    def test_tls_cert_and_key_together_valid(self) -> None:
        """Test that TLS certificate and key together are valid."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_path = Path(temp_dir) / "cert.pem"
            key_path = Path(temp_dir) / "key.pem"
            
            cert_path.write_text("dummy cert")
            key_path.write_text("dummy key")
            
            config = ServerConfig(
                tls_cert=str(cert_path),
                tls_key=str(key_path),
                secret_key="test"
            )
            assert config.tls_cert == str(cert_path)
            assert config.tls_key == str(key_path)

    def test_username_without_password_invalid(self) -> None:
        """Test that username without password is invalid."""
        with pytest.raises(ValidationError) as exc_info:
            ServerConfig(username="testuser", secret_key="test")
        
        assert "Password is required when username is provided" in str(exc_info.value)

    def test_password_without_username_valid(self) -> None:
        """Test that password without username is valid (edge case)."""
        config = ServerConfig(password="testpass", secret_key="test")
        assert config.password == "testpass"
        assert config.username is None

    def test_username_and_password_together_valid(self) -> None:
        """Test that username and password together are valid."""
        config = ServerConfig(username="testuser", password="testpass", secret_key="test")
        assert config.username == "testuser"
        assert config.password == "testpass"


class TestServerConfigComputedProperties:
    """Test computed properties of ServerConfig."""

    def test_is_tls_enabled_with_tls(self) -> None:
        """Test is_tls_enabled returns True when TLS is configured."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_path = Path(temp_dir) / "cert.pem"
            key_path = Path(temp_dir) / "key.pem"
            
            cert_path.write_text("dummy cert")
            key_path.write_text("dummy key")
            
            config = ServerConfig(
                tls_cert=str(cert_path),
                tls_key=str(key_path),
                secret_key="test"
            )
            assert config.is_tls_enabled is True

    def test_is_tls_enabled_without_tls(self) -> None:
        """Test is_tls_enabled returns False when TLS is not configured."""
        config = ServerConfig(secret_key="test")
        assert config.is_tls_enabled is False

    def test_is_mtls_enabled_with_mtls(self) -> None:
        """Test is_mtls_enabled returns True when mTLS is configured."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            temp_file.write("dummy ca")
            temp_path = temp_file.name
        
        try:
            config = ServerConfig(mtls_ca=temp_path, secret_key="test")
            assert config.is_mtls_enabled is True
        finally:
            Path(temp_path).unlink()

    def test_is_mtls_enabled_without_mtls(self) -> None:
        """Test is_mtls_enabled returns False when mTLS is not configured."""
        config = ServerConfig(secret_key="test")
        assert config.is_mtls_enabled is False

    def test_is_auth_enabled_with_auth(self) -> None:
        """Test is_auth_enabled returns True when authentication is configured."""
        config = ServerConfig(username="testuser", password="testpass", secret_key="test")
        assert config.is_auth_enabled is True

    def test_is_auth_enabled_without_auth(self) -> None:
        """Test is_auth_enabled returns False when authentication is not configured."""
        config = ServerConfig(secret_key="test")
        assert config.is_auth_enabled is False

    def test_database_url_duckdb_with_file(self) -> None:
        """Test database_url for DuckDB with file database."""
        config = ServerConfig(backend="duckdb", database="/tmp/test.duckdb", secret_key="test")
        assert config.database_url == "/tmp/test.duckdb"

    def test_database_url_duckdb_memory(self) -> None:
        """Test database_url for DuckDB with in-memory database."""
        config = ServerConfig(backend="duckdb", secret_key="test")
        assert config.database_url == ":memory:"

    def test_database_url_sqlite(self) -> None:
        """Test database_url for SQLite."""
        config = ServerConfig(backend="sqlite", database="/tmp/test.db", secret_key="test")
        assert config.database_url == "/tmp/test.db"

    def test_database_url_unknown_backend(self) -> None:
        """Test database_url raises error for unknown backend."""
        # Create a config with valid backend, then test the property directly
        config = ServerConfig(secret_key="test")
        
        # Mock the backend property to bypass validation
        with pytest.raises(ValueError) as exc_info:
            # Temporarily modify the backend attribute using object.__setattr__
            # to bypass Pydantic validation
            object.__setattr__(config, 'backend', 'unknown')
            _ = config.database_url
        
        assert "Unknown backend: unknown" in str(exc_info.value)

    def test_is_postgresql_enabled_complete_config(self) -> None:
        """Test is_postgresql_enabled with complete PostgreSQL configuration."""
        config = ServerConfig(
            postgresql_server="localhost",
            postgresql_user="user",
            postgresql_password="pass",
            secret_key="test"
        )
        assert config.is_postgresql_enabled is True

    def test_is_postgresql_enabled_incomplete_config(self) -> None:
        """Test is_postgresql_enabled with incomplete PostgreSQL configuration."""
        # Missing server
        config = ServerConfig(
            postgresql_user="user",
            postgresql_password="pass",
            secret_key="test"
        )
        assert config.is_postgresql_enabled is False
        
        # Missing user
        config = ServerConfig(
            postgresql_server="localhost",
            postgresql_password="pass",
            secret_key="test"
        )
        assert config.is_postgresql_enabled is False
        
        # Missing password
        config = ServerConfig(
            postgresql_server="localhost",
            postgresql_user="user",
            secret_key="test"
        )
        assert config.is_postgresql_enabled is False

    def test_is_azure_storage_enabled_complete_config(self) -> None:
        """Test is_azure_storage_enabled with complete Azure configuration."""
        config = ServerConfig(
            azure_storage_account="account",
            azure_storage_container="container",
            secret_key="test"
        )
        assert config.is_azure_storage_enabled is True

    def test_is_azure_storage_enabled_incomplete_config(self) -> None:
        """Test is_azure_storage_enabled with incomplete Azure configuration."""
        # Missing account
        config = ServerConfig(
            azure_storage_container="container",
            secret_key="test"
        )
        assert config.is_azure_storage_enabled is False
        
        # Missing container
        config = ServerConfig(
            azure_storage_account="account",
            secret_key="test"
        )
        assert config.is_azure_storage_enabled is False

    def test_effective_advertised_hostname_with_advertised(self) -> None:
        """Test effective_advertised_hostname when advertised_hostname is set."""
        config = ServerConfig(
            hostname="localhost",
            advertised_hostname="example.com",
            secret_key="test"
        )
        assert config.effective_advertised_hostname == "example.com"

    def test_effective_advertised_hostname_without_advertised(self) -> None:
        """Test effective_advertised_hostname when advertised_hostname is not set."""
        config = ServerConfig(hostname="0.0.0.0", secret_key="test")
        assert config.effective_advertised_hostname == "0.0.0.0"


class TestServerConfigEdgeCases:
    """Test edge cases and error conditions."""

    def test_missing_required_secret_key(self) -> None:
        """Test that missing secret_key raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            ServerConfig()  # Missing required secret_key parameter
        
        assert "secret_key" in str(exc_info.value).lower()

    def test_empty_secret_key(self) -> None:
        """Test that empty secret_key is accepted but not recommended."""
        config = ServerConfig(secret_key="")
        assert config.secret_key == ""

    def test_extra_fields_forbidden(self) -> None:
        """Test that extra fields are forbidden."""
        with pytest.raises(ValidationError) as exc_info:
            ServerConfig(secret_key="test", extra_field="not allowed")  # Invalid extra field
        
        assert "extra" in str(exc_info.value).lower()

    def test_validate_assignment(self) -> None:
        """Test that assignment validation works."""
        config = ServerConfig(secret_key="test")
        
        # Valid assignment
        config.hostname = "example.com"
        assert config.hostname == "example.com"
        
        # Invalid assignment should raise ValidationError
        with pytest.raises(ValidationError):
            config.port = 0  # Invalid port
        
        with pytest.raises(ValidationError):
            config.backend = "invalid"  # Invalid backend

    def test_none_values_handling(self) -> None:
        """Test handling of None values for optional fields."""
        config = ServerConfig(
            database=None,
            advertised_hostname=None,
            username=None,
            password=None,
            tls_cert=None,
            tls_key=None,
            mtls_ca=None,
            init_sql=None,
            postgresql_server=None,
            postgresql_user=None,
            postgresql_password=None,
            postgresql_catalogdb=None,
            azure_storage_account=None,
            azure_storage_container=None,
            secret_key="test"
        )
        
        assert config.database is None
        assert config.advertised_hostname is None
        assert config.username is None
        assert config.password is None
        assert config.tls_cert is None
        assert config.tls_key is None
        assert config.mtls_ca is None
        assert config.init_sql is None
        assert config.postgresql_server is None
        assert config.postgresql_user is None
        assert config.postgresql_password is None
        assert config.postgresql_catalogdb is None
        assert config.azure_storage_account is None
        assert config.azure_storage_container is None


class TestServerConfigIntegration:
    """Test integration scenarios and real-world configurations."""

    def test_production_like_config(self) -> None:
        """Test a production-like configuration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_path = Path(temp_dir) / "cert.pem"
            key_path = Path(temp_dir) / "key.pem"
            ca_path = Path(temp_dir) / "ca.pem"
            
            cert_path.write_text("dummy cert")
            key_path.write_text("dummy key")
            ca_path.write_text("dummy ca")
            
            config = ServerConfig(
                backend="duckdb",
                database="/data/production.duckdb",
                hostname="0.0.0.0",
                advertised_hostname="api.company.com",
                port=443,
                username="admin",
                password="secure-password-123",
                secret_key="super-secret-key-for-jwt",
                tls_cert=str(cert_path),
                tls_key=str(key_path),
                mtls_ca=str(ca_path),
                print_queries=False,
                read_only=False,
                postgresql_server="pg.company.com",
                postgresql_port=5432,
                postgresql_user="app_user",
                postgresql_password="AZURE",
                postgresql_catalogdb="analytics",
                azure_storage_account="companystorage",
                azure_storage_container="datalake",
            )
            
            # Verify all production features are enabled
            assert config.is_tls_enabled is True
            assert config.is_mtls_enabled is True
            assert config.is_auth_enabled is True
            assert config.is_postgresql_enabled is True
            assert config.is_azure_storage_enabled is True
            assert config.effective_advertised_hostname == "api.company.com"
            assert config.database_url == "/data/production.duckdb"

    def test_development_config(self) -> None:
        """Test a development configuration."""
        config = ServerConfig(
            backend="duckdb",
            hostname="localhost",
            port=8080,
            secret_key="dev-secret",
            print_queries=True,
        )
        
        # Verify development settings
        assert config.is_tls_enabled is False
        assert config.is_mtls_enabled is False
        assert config.is_auth_enabled is False
        assert config.is_postgresql_enabled is False
        assert config.is_azure_storage_enabled is False
        assert config.print_queries is True
        assert config.effective_advertised_hostname == "localhost"
        assert config.database_url == ":memory:"

    def test_sqlite_config(self) -> None:
        """Test SQLite-specific configuration."""
        config = ServerConfig(
            backend="sqlite",
            database="/tmp/app.db",
            secret_key="sqlite-secret",
            read_only=True,
        )
        
        assert config.backend == "sqlite"
        assert config.database_url == "/tmp/app.db"
        assert config.read_only is True

    def test_azure_only_config(self) -> None:
        """Test Azure-specific configuration."""
        config = ServerConfig(
            backend="duckdb",
            azure_storage_account="myaccount",
            azure_storage_container="mycontainer",
            secret_key="azure-secret",
        )
        
        assert config.is_azure_storage_enabled is True
        assert config.is_postgresql_enabled is False
        assert config.azure_storage_account == "myaccount"
        assert config.azure_storage_container == "mycontainer"

    def test_postgresql_only_config(self) -> None:
        """Test PostgreSQL-specific configuration."""
        config = ServerConfig(
            backend="duckdb",
            postgresql_server="localhost",
            postgresql_user="postgres",
            postgresql_password="password123",
            postgresql_catalogdb="testdb",
            secret_key="pg-secret",
        )
        
        assert config.is_postgresql_enabled is True
        assert config.is_azure_storage_enabled is False
        assert config.postgresql_server == "localhost"
        assert config.postgresql_user == "postgres"
        assert config.postgresql_password == "password123"
        assert config.postgresql_catalogdb == "testdb"
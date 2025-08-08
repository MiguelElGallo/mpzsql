"""Configuration management for MPZSQL server.

This module defines the server configuration structure using Pydantic,
providing validation and type safety for all server options.
"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ServerConfig(BaseModel):
    """Server configuration with validation."""

    # Backend configuration
    backend: str = Field(
        default="duckdb", description="Database backend (duckdb or sqlite)"
    )
    database: str | None = Field(
        default=None,
        description="Database filename (optional for DuckDB, required for SQLite)",
    )

    # Network configuration
    hostname: str = Field(
        default="localhost", description="Server hostname to listen on"
    )
    advertised_hostname: str | None = Field(
        default=None,
        description="Hostname to advertise to clients (falls back to hostname if not set)",
    )
    port: int = Field(default=8080, ge=1, le=65535, description="Server port")

    # Authentication configuration
    username: str | None = Field(default=None, description="Authentication username")
    password: str | None = Field(default=None, description="Authentication password")
    secret_key: str = Field(description="JWT secret key")

    # TLS configuration
    tls_cert: str | None = Field(default=None, description="TLS certificate file path")
    tls_key: str | None = Field(default=None, description="TLS private key file path")
    mtls_ca: str | None = Field(
        default=None, description="mTLS CA certificate file path"
    )

    # SQL initialization
    init_sql: str | None = Field(
        default=None, description="SQL commands to run on startup"
    )

    # Server behavior
    print_queries: bool = Field(
        default=False, description="Print executed queries to console"
    )
    read_only: bool = Field(default=False, description="Enable read-only mode")

    # PostgreSQL configuration
    postgresql_server: str | None = Field(
        default=None, description="PostgreSQL server hostname"
    )
    postgresql_port: int | None = Field(
        default=5432, ge=1, le=65535, description="PostgreSQL server port"
    )
    postgresql_user: str | None = Field(default=None, description="PostgreSQL username")
    postgresql_password: str | None = Field(
        default=None, description="PostgreSQL password"
    )
    postgresql_catalogdb: str | None = Field(
        default=None, description="PostgreSQL catalog database name"
    )

    # Azure Storage configuration
    azure_storage_account: str | None = Field(
        default=None, description="Azure Storage account name"
    )
    azure_storage_container: str | None = Field(
        default=None, description="Azure Storage container name"
    )

    @field_validator("backend")
    def validate_backend(cls, v):
        """Validate backend option."""
        if v not in ["duckdb", "sqlite"]:
            raise ValueError("Backend must be 'duckdb' or 'sqlite'")
        return v

    @field_validator("tls_cert")
    def validate_tls_cert(cls, v):
        """Validate TLS certificate file exists if provided."""
        if v and not Path(v).exists():
            raise ValueError(f"TLS certificate file not found: {v}")
        return v

    @field_validator("tls_key")
    def validate_tls_key_exists(cls, v):
        """Validate TLS key file exists if provided."""
        if v and not Path(v).exists():
            raise ValueError(f"TLS key file not found: {v}")
        return v

    @field_validator("mtls_ca")
    def validate_mtls_ca(cls, v):
        """Validate mTLS CA certificate file exists if provided."""
        if v and not Path(v).exists():
            raise ValueError(f"mTLS CA certificate file not found: {v}")
        return v

    @model_validator(mode="after")
    def validate_config(self):
        """Validate cross-field configuration."""
        # Validate database configuration based on backend
        if self.backend == "sqlite" and not self.database:
            raise ValueError("SQLite backend requires a database file")

        # Validate TLS certificate and key are provided together
        if bool(self.tls_key) != bool(self.tls_cert):
            raise ValueError("Both TLS certificate and key must be provided together")

        # Validate authentication configuration
        if bool(self.username) != bool(self.password):
            if self.username and not self.password:
                raise ValueError("Password is required when username is provided")

        return self

    @property
    def is_tls_enabled(self) -> bool:
        """Check if TLS is enabled."""
        return bool(self.tls_cert and self.tls_key)

    @property
    def is_mtls_enabled(self) -> bool:
        """Check if mTLS is enabled."""
        return bool(self.mtls_ca)

    @property
    def is_auth_enabled(self) -> bool:
        """Check if authentication is enabled."""
        return bool(self.username and self.password)

    @property
    def database_url(self) -> str:
        """Get the database connection URL/path."""
        if self.backend == "duckdb":
            return self.database or ":memory:"
        if self.backend == "sqlite":
            return self.database or ""
        raise ValueError(f"Unknown backend: {self.backend}")

    @property
    def is_postgresql_enabled(self) -> bool:
        """Check if PostgreSQL connection is configured."""
        return bool(
            self.postgresql_server and self.postgresql_user and self.postgresql_password
        )

    @property
    def is_azure_storage_enabled(self) -> bool:
        """Check if Azure Storage connection is configured."""
        return bool(self.azure_storage_account and self.azure_storage_container)

    @property
    def effective_advertised_hostname(self) -> str:
        """Get the effective advertised hostname (falls back to listening hostname)."""
        return self.advertised_hostname or self.hostname

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

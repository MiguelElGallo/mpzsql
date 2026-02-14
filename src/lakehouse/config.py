"""Server configuration — CLI args, env vars, defaults.

Uses `pydantic-settings <https://docs.pydantic.dev/latest/concepts/pydantic_settings/>`_
so that every field can be set via:

1. An environment variable with the ``LAKEHOUSE_`` prefix (e.g. ``LAKEHOUSE_PORT``).
2. A ``.env`` file in the working directory.
3. Programmatic construction (e.g. in tests).

The fields mirror  / SQLFlite CLI flags where applicable.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path  # noqa: TC003 — Pydantic needs Path at runtime for field validation

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["ServerConfig"]


class ServerConfig(BaseSettings):
    """Complete configuration for the Lakehouse Flight SQL server.

    Attributes:
        host: Network interface to bind to.
        port: TCP port for the Flight SQL (gRPC) endpoint.
        tls_cert_file: Path to the TLS certificate (PEM).  ``None`` disables TLS.
        tls_key_file: Path to the TLS private key (PEM).
        mtls_ca_cert_file: Path to the CA certificate for mutual-TLS client
            verification.  When set, ``verify_client`` is implied.
        username: Default username for Basic auth.
        password: Password for Basic auth.  **Required** unless auth is disabled.
        secret_key: Key for HMAC password hashing and HS256 JWT signing.
            Auto-generated if left empty.
        jwt_issuer: ``iss`` claim in issued JWTs.
        database: DuckDB database file path.  ``":memory:"`` for in-memory.
        read_only: Open the DuckDB database in read-only mode.
        init_sql: Semicolon-separated SQL statements to execute at startup.
        init_sql_file: Path to a ``.sql`` file to execute at startup.
        azure_storage_account: Azure Storage account name for DuckLake data files.
        ducklake_data_path: ``DATA_PATH`` for DuckLake ``ATTACH`` (e.g.
            ``az://my-container/``).
        pg_host: PostgreSQL server hostname for DuckLake catalog.
        pg_port: PostgreSQL server port.
        pg_database: PostgreSQL database name for DuckLake catalog.
        pg_user: PostgreSQL username (Entra ID principal).
        ducklake_alias: DuckDB alias for the attached DuckLake database.
        pg_token_refresh_minutes: Minutes before Entra ID token expiry to
            trigger a refresh.
        health_check_port: TCP port for the gRPC health checking endpoint.
        health_check_enabled: Whether to start the health check server.
        health_poll_interval: Seconds between DuckDB health probes.
        print_queries: Log every SQL query executed by clients.
        log_level: Python logging level (``DEBUG``, ``INFO``, ``WARNING``, etc.).
    """

    model_config = SettingsConfigDict(
        env_prefix="LAKEHOUSE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Network ──────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 31337

    # ── TLS ──────────────────────────────────────────────────
    tls_cert_file: Path | None = None
    tls_key_file: Path | None = None
    mtls_ca_cert_file: Path | None = None

    # ── Auth ─────────────────────────────────────────────────
    username: str = "lakehouse"
    password: str = ""
    secret_key: str = ""
    jwt_issuer: str = "lakehouse"

    # ── DuckDB ───────────────────────────────────────────────
    database: str = ":memory:"
    read_only: bool = False
    init_sql: str = ""
    init_sql_file: Path | None = None

    # ── DuckLake ─────────────────────────────────────────────
    azure_storage_account: str = ""
    ducklake_data_path: str = ""
    pg_host: str = ""
    pg_port: int = 5432
    pg_database: str = ""
    pg_user: str = ""
    ducklake_alias: str = "lakehouse"
    pg_token_refresh_minutes: float = 5.0

    # ── Health ───────────────────────────────────────────────
    health_check_port: int = 8081
    health_check_enabled: bool = True
    health_poll_interval: float = 5.0

    # ── Logging / Debug ──────────────────────────────────────
    print_queries: bool = False
    log_level: str = "INFO"

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        """Normalise to upper-case and reject unknown levels."""
        v = v.upper()
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v not in valid:
            msg = f"Invalid log level {v!r}, expected one of {sorted(valid)}"
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def _auto_generate_secret_key(self) -> ServerConfig:
        """Generate a random secret key if none was provided."""
        if not self.secret_key:
            self.secret_key = f"SECRET-{uuid.uuid4()}"
        return self

    @model_validator(mode="after")
    def _validate_tls_pair(self) -> ServerConfig:
        """Ensure cert and key are provided together."""
        has_cert = self.tls_cert_file is not None
        has_key = self.tls_key_file is not None
        if has_cert != has_key:
            msg = "Both tls_cert_file and tls_key_file must be set together"
            raise ValueError(msg)
        return self

    @field_validator("ducklake_alias")
    @classmethod
    def _validate_ducklake_alias(cls, v: str) -> str:
        """Ensure the DuckLake alias is a valid SQL identifier.

        Allows empty string (DuckLake not configured).
        """
        if v and not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", v):
            msg = (
                f"Invalid ducklake_alias {v!r}: "
                "must be a valid SQL identifier (letters, digits, underscores; "
                "cannot start with a digit)"
            )
            raise ValueError(msg)
        return v

    @field_validator("ducklake_data_path")
    @classmethod
    def _validate_ducklake_data_path(cls, v: str) -> str:
        """Ensure the DuckLake data path ends with ``/`` and contains no SQL-unsafe chars."""
        if v and ("'" in v or ";" in v):
            msg = "ducklake_data_path must not contain single-quotes or semicolons"
            raise ValueError(msg)
        if v and not v.endswith("/"):
            msg = f"ducklake_data_path must end with '/': got {v!r}"
            raise ValueError(msg)
        return v

    @field_validator("pg_port")
    @classmethod
    def _validate_pg_port(cls, v: int) -> int:
        """Ensure the PostgreSQL port is within the valid TCP range."""
        if not 1 <= v <= 65535:
            msg = f"pg_port must be between 1 and 65535: got {v}"
            raise ValueError(msg)
        return v

    @field_validator("pg_token_refresh_minutes")
    @classmethod
    def _validate_pg_token_refresh_minutes(cls, v: float) -> float:
        """Ensure the token refresh interval is positive."""
        if v <= 0:
            msg = f"pg_token_refresh_minutes must be > 0: got {v}"
            raise ValueError(msg)
        return v

    @field_validator("pg_host", "pg_database", "pg_user")
    @classmethod
    def _validate_pg_no_sql_chars(cls, v: str) -> str:
        """Reject single-quotes and semicolons in PostgreSQL connection fields.

        These values are interpolated into SQL strings; embedded ``'`` or ``;``
        would break or inject into the statement.
        """
        if v and ("'" in v or ";" in v or " " in v):
            msg = (
                "PostgreSQL connection fields must not contain "
                "single-quotes, semicolons, or spaces"
            )
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def _validate_ducklake_fields(self) -> ServerConfig:
        """Ensure all DuckLake fields are provided together (all-or-nothing)."""
        ducklake_fields = {
            "azure_storage_account": self.azure_storage_account,
            "ducklake_data_path": self.ducklake_data_path,
            "pg_host": self.pg_host,
            "pg_database": self.pg_database,
            "pg_user": self.pg_user,
        }
        provided = {k for k, v in ducklake_fields.items() if v}
        if provided and provided != set(ducklake_fields.keys()):
            missing = set(ducklake_fields.keys()) - provided
            msg = (
                f"DuckLake configuration is incomplete: "
                f"missing {', '.join(sorted(missing))}. "
                f"All DuckLake fields must be set together."
            )
            raise ValueError(msg)
        return self

    @property
    def ducklake_enabled(self) -> bool:
        """Whether DuckLake integration is configured."""
        return bool(self.pg_host and self.pg_database and self.pg_user)

    @property
    def tls_enabled(self) -> bool:
        """Whether TLS is configured."""
        return self.tls_cert_file is not None and self.tls_key_file is not None

    @property
    def mtls_enabled(self) -> bool:
        """Whether mutual TLS (client certificate verification) is configured."""
        return self.tls_enabled and self.mtls_ca_cert_file is not None

    @property
    def location(self) -> str:
        """The Flight server location URI (``grpc://`` or ``grpc+tls://``)."""
        scheme = "grpc+tls" if self.tls_enabled else "grpc"
        return f"{scheme}://{self.host}:{self.port}"

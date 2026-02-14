"""Lakehouse — High-Performance SQL Server for the Cloud.

Arrow Flight SQL server backed by DuckDB
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = [
    "DuckDBFlightSqlServer",
    "ServerConfig",
    "build_server",
]


def __getattr__(name: str) -> object:
    """Lazy imports to avoid heavy startup cost for simple version checks."""
    if name == "DuckDBFlightSqlServer":
        from lakehouse.server import DuckDBFlightSqlServer

        return DuckDBFlightSqlServer
    if name == "ServerConfig":
        from lakehouse.config import ServerConfig

        return ServerConfig
    if name == "build_server":
        from lakehouse.__main__ import build_server

        return build_server
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)

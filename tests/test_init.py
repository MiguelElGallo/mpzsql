"""Tests for lakehouse.__init__ — lazy imports and module attributes."""

from __future__ import annotations

import pytest


class TestLazyImports:
    """Tests for __getattr__ lazy import behaviour."""

    def test_lazy_import_duckdb_flight_sql_server(self):
        import lakehouse

        cls = lakehouse.DuckDBFlightSqlServer
        from lakehouse.server import DuckDBFlightSqlServer

        assert cls is DuckDBFlightSqlServer

    def test_lazy_import_server_config(self):
        import lakehouse

        cls = lakehouse.ServerConfig
        from lakehouse.config import ServerConfig

        assert cls is ServerConfig

    def test_lazy_import_build_server(self):
        import lakehouse

        func = lakehouse.build_server
        from lakehouse.__main__ import build_server

        assert func is build_server

    def test_unknown_attribute_raises(self):
        import lakehouse

        with pytest.raises(AttributeError, match="no_such_thing"):
            _ = lakehouse.no_such_thing

    def test_version_accessible(self):
        import lakehouse

        assert isinstance(lakehouse.__version__, str)

    def test_all_exports(self):
        import lakehouse

        assert "DuckDBFlightSqlServer" in lakehouse.__all__
        assert "ServerConfig" in lakehouse.__all__
        assert "build_server" in lakehouse.__all__

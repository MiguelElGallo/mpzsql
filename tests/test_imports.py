"""Basic import tests for mpzsql package."""


def test_import_mpzsql():
    """Test that the main package can be imported."""
    import mpzsql

    assert mpzsql is not None


def test_import_cli():
    """Test that the CLI module can be imported."""
    from mpzsql import cli

    assert cli is not None


def test_import_config():
    """Test that the config module can be imported."""
    from mpzsql import config

    assert config is not None


def test_import_backends():
    """Test that backend modules can be imported."""
    from mpzsql.backends import base, duckdb_backend, sqlite_backend

    assert base is not None
    assert duckdb_backend is not None
    assert sqlite_backend is not None


def test_import_flightsql():
    """Test that FlightSQL modules can be imported."""
    from mpzsql.flightsql import protocol, server_base

    assert server_base is not None
    assert protocol is not None

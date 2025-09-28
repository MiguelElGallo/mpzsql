"""
Tests for demo_client/client_fixed.py module to improve code coverage.

This test suite covers the fixed version of the MPZSQLClient class.
"""

import os
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

import pytest
import pyarrow as pa

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from demo_client.client_fixed import MPZSQLClient, app, console, logger


class TestMPZSQLClientFixed:
    """Test the fixed version of MPZSQLClient class."""

    def test_client_initialization_fixed(self):
        """Test client initialization with various parameters in fixed version."""
        # Test with minimal parameters
        client = MPZSQLClient(host="localhost", port=8080)
        assert client.host == "localhost"
        assert client.port == 8080
        assert client.username is None
        assert client.password is None
        assert client.certificate is None
        assert client.connection is None

        # Test with all parameters
        client = MPZSQLClient(
            host="test.example.com",
            port=9090,
            username="testuser",
            password="testpass",
            certificate="test.crt",
        )
        assert client.host == "test.example.com"
        assert client.port == 9090
        assert client.username == "testuser"
        assert client.password == "testpass"
        assert client.certificate == "test.crt"

    @patch("demo_client.client_fixed.console")
    @patch("demo_client.client_fixed.flightsql_dbapi.connect")
    def test_connect_success_fixed(self, mock_connect, mock_console):
        """Test successful connection in fixed version."""
        mock_connection = Mock()
        mock_connect.return_value = mock_connection

        client = MPZSQLClient(host="localhost", port=8080)
        result = client.connect()

        assert result is True
        assert client.connection == mock_connection
        mock_connect.assert_called_once()

    @patch("demo_client.client_fixed.console")
    @patch("demo_client.client_fixed.flightsql_dbapi.connect")
    def test_connect_failure_fixed(self, mock_connect, mock_console):
        """Test connection failure in fixed version."""
        mock_connect.side_effect = Exception("Connection failed")

        client = MPZSQLClient(host="localhost", port=8080)
        result = client.connect()

        assert result is False
        assert client.connection is None

    def test_disconnect_fixed(self):
        """Test disconnect in fixed version."""
        mock_connection = Mock()
        client = MPZSQLClient(host="localhost", port=8080)
        client.connection = mock_connection

        client.disconnect()

        mock_connection.close.assert_called_once()
        assert client.connection is None

    def test_execute_query_no_connection_fixed(self):
        """Test query execution without connection in fixed version."""
        client = MPZSQLClient(host="localhost", port=8080)
        with patch("demo_client.client_fixed.console") as mock_console:
            result = client.execute_query("SELECT 1")

        assert result is None

    def test_execute_query_success_fixed(self):
        """Test successful query execution in fixed version."""
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_table = Mock()
        mock_table.num_rows = 5

        mock_connection.cursor.return_value = mock_cursor
        mock_cursor.fetch_arrow_table.return_value = mock_table

        client = MPZSQLClient(host="localhost", port=8080)
        client.connection = mock_connection

        with patch("demo_client.client_fixed.console"):
            result = client.execute_query("SELECT * FROM test_table")

        assert result == mock_table
        mock_cursor.execute.assert_called_once_with("SELECT * FROM test_table")

    def test_execute_query_methods_fixed(self):
        """Test available query execution methods in fixed version."""
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_connection.cursor.return_value = mock_cursor

        client = MPZSQLClient(host="localhost", port=8080)
        client.connection = mock_connection

        # Test execute_query method exists
        with patch("demo_client.client_fixed.console"):
            mock_cursor.fetch_arrow_table.return_value = Mock(num_rows=1)
            result = client.execute_query("SELECT 1")
            assert result is not None

    def test_get_server_info_fixed(self):
        """Test server info retrieval in fixed version."""
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_table = Mock()
        mock_table.num_rows = 1

        mock_connection.cursor.return_value = mock_cursor
        mock_cursor.fetch_arrow_table.return_value = mock_table

        client = MPZSQLClient(host="localhost", port=8080)
        client.connection = mock_connection

        with patch("demo_client.client_fixed.console"):
            result = client.get_server_info()

        assert result is True

    def test_list_catalogs_fixed(self):
        """Test catalog listing in fixed version."""
        client = MPZSQLClient(host="localhost", port=8080)
        client.connection = Mock()

        with patch("demo_client.client_fixed.console"):
            with patch.object(client, 'execute_query', return_value=Mock(num_rows=1)):
                with patch.object(client, '_display_table'):
                    result = client.list_catalogs()

        assert result is True

    def test_display_table_fixed(self):
        """Test table display in fixed version."""
        table = pa.table({
            "id": [1, 2, 3],
            "name": ["Alice", "Bob", "Charlie"]
        })

        client = MPZSQLClient(host="localhost", port=8080)
        
        with patch("demo_client.client_fixed.console"):
            # Should not raise an error
            client._display_table(table, "Test Results")

    def test_typer_app_fixed(self):
        """Test that the typer app is configured correctly in fixed version."""
        assert app.info.name == "mpzsql-client"
        assert "Demo client for MPZSQL FlightSQL server" in app.info.help


class TestCliCommandsFixed:
    """Test CLI commands in the fixed version."""

    @patch("demo_client.client_fixed.MPZSQLClient")
    @patch("demo_client.client_fixed.console")
    def test_connect_command_basic_fixed(self, mock_console, mock_client_class):
        """Test basic connect command in fixed version."""
        mock_client = Mock()
        mock_client.connect.return_value = True
        mock_client_class.return_value = mock_client

        from typer.testing import CliRunner
        runner = CliRunner()
        
        # Test without interactive mode
        result = runner.invoke(app, ["connect", "--no-interactive"])
        assert result.exit_code == 0
        mock_client.connect.assert_called_once()

    @patch("demo_client.client_fixed.MPZSQLClient")
    @patch("demo_client.client_fixed.console")
    def test_connect_command_with_params_fixed(self, mock_console, mock_client_class):
        """Test connect command with parameters in fixed version."""
        mock_client = Mock()
        mock_client.connect.return_value = True
        mock_client_class.return_value = mock_client

        from typer.testing import CliRunner
        runner = CliRunner()
        
        result = runner.invoke(app, [
            "connect", 
            "--host", "test.com",
            "--port", "9090",
            "--user", "testuser",
            "--no-interactive"
        ])
        assert result.exit_code == 0


if __name__ == "__main__":
    pytest.main(["-v", __file__])
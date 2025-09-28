"""
Comprehensive tests for demo_client module to improve code coverage.

This test suite covers the MPZSQLClient class and demo functionality,
focusing on connection handling, query execution, and error scenarios.
"""

import os
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

import pytest
import pyarrow as pa

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from demo_client.client import MPZSQLClient, app, console, logger
from demo_client.demo import main as demo_main


class TestMPZSQLClient:
    """Test the MPZSQLClient class."""

    def test_client_initialization(self):
        """Test client initialization with various parameters."""
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

    @patch("demo_client.client.console")
    @patch("demo_client.client.flightsql_dbapi.connect")
    def test_connect_success_no_auth(self, mock_connect, mock_console):
        """Test successful connection without authentication."""
        mock_connection = Mock()
        mock_connect.return_value = mock_connection

        client = MPZSQLClient(host="localhost", port=8080)
        result = client.connect()

        assert result is True
        assert client.connection == mock_connection
        mock_connect.assert_called_once()
        mock_console.print.assert_any_call("[green]✅ Connected to FlightSQL server with TLS + Authentication[/green]")

    @patch("demo_client.client.console")
    @patch("demo_client.client.flightsql_dbapi.connect")
    def test_connect_success_with_auth(self, mock_connect, mock_console):
        """Test successful connection with authentication."""
        mock_connection = Mock()
        mock_connect.return_value = mock_connection

        client = MPZSQLClient(
            host="localhost", 
            port=8080,
            username="testuser", 
            password="testpass"
        )
        result = client.connect()

        assert result is True
        assert client.connection == mock_connection
        mock_connect.assert_called_once()

    @patch("demo_client.client.console")
    @patch("demo_client.client.flightsql_dbapi.connect")
    def test_connect_success_with_tls(self, mock_connect, mock_console):
        """Test successful connection with TLS certificate."""
        mock_connection = Mock()
        mock_connect.return_value = mock_connection

        # Create a temporary certificate file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.crt', delete=False) as f:
            f.write("fake certificate")
            cert_path = f.name

        try:
            client = MPZSQLClient(
                host="localhost", 
                port=8080,
                certificate=cert_path
            )
            result = client.connect()

            assert result is True
            assert client.connection == mock_connection
        finally:
            os.unlink(cert_path)

    @patch("demo_client.client.console")
    @patch("demo_client.client.flightsql_dbapi.connect")
    def test_connect_failure(self, mock_connect, mock_console):
        """Test connection failure."""
        mock_connect.side_effect = Exception("Connection failed")

        client = MPZSQLClient(host="localhost", port=8080)
        result = client.connect()

        assert result is False
        assert client.connection is None
        mock_console.print.assert_any_call("[red]❌ Failed to connect: Connection failed[/red]")

    @patch("demo_client.client.console")
    def test_disconnect_with_connection(self, mock_console):
        """Test disconnect when connection exists."""
        mock_connection = Mock()
        client = MPZSQLClient(host="localhost", port=8080)
        client.connection = mock_connection

        client.disconnect()

        mock_connection.close.assert_called_once()
        assert client.connection is None
        mock_console.print.assert_any_call("[yellow]📡 Disconnected from server[/yellow]")

    @patch("demo_client.client.console")
    def test_disconnect_no_connection(self, mock_console):
        """Test disconnect when no connection exists."""
        client = MPZSQLClient(host="localhost", port=8080)
        client.disconnect()  # Should not raise an error

    @patch("demo_client.client.console")
    def test_execute_query_no_connection(self, mock_console):
        """Test query execution without connection."""
        client = MPZSQLClient(host="localhost", port=8080)
        result = client.execute_query("SELECT 1")

        assert result is None
        mock_console.print.assert_any_call("[red]❌ Not connected to server[/red]")

    @patch("demo_client.client.console")
    def test_execute_query_success(self, mock_console):
        """Test successful query execution."""
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_table = Mock()
        mock_table.num_rows = 5

        mock_connection.cursor.return_value = mock_cursor
        mock_cursor.fetch_arrow_table.return_value = mock_table

        client = MPZSQLClient(host="localhost", port=8080)
        client.connection = mock_connection

        result = client.execute_query("SELECT * FROM test_table")

        assert result == mock_table
        mock_cursor.execute.assert_called_once_with("SELECT * FROM test_table")
        mock_console.print.assert_any_call("[green]✅ Query executed successfully. Rows: 5[/green]")

    @patch("demo_client.client.console")
    @patch("demo_client.client.logger")
    def test_execute_query_failure(self, mock_logger, mock_console):
        """Test query execution failure."""
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_connection.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception("Query failed")

        client = MPZSQLClient(host="localhost", port=8080)
        client.connection = mock_connection

        result = client.execute_query("SELECT * FROM nonexistent")

        assert result is None
        mock_console.print.assert_any_call("[red]❌ Query failed: Query failed[/red]")
        mock_logger.error.assert_called_once_with("Query execution failed: Query failed")

    @patch("demo_client.client.console")
    def test_execute_update_no_connection(self, mock_console):
        """Test update execution without connection."""
        client = MPZSQLClient(host="localhost", port=8080)
        result = client.execute_update("CREATE TABLE test (id INTEGER)")

        assert result is False
        mock_console.print.assert_any_call("[red]❌ Not connected to server[/red]")

    @patch("demo_client.client.console")
    def test_execute_update_success(self, mock_console):
        """Test successful update execution."""
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_connection.cursor.return_value = mock_cursor

        client = MPZSQLClient(host="localhost", port=8080)
        client.connection = mock_connection

        result = client.execute_update("INSERT INTO test VALUES (1)")

        assert result is True
        mock_cursor.execute.assert_called_once_with("INSERT INTO test VALUES (1)")
        mock_console.print.assert_any_call("[green]✅ Statement executed successfully[/green]")

    @patch("demo_client.client.console")
    @patch("demo_client.client.logger")
    def test_execute_update_failure(self, mock_logger, mock_console):
        """Test update execution failure."""
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_connection.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception("Update failed")

        client = MPZSQLClient(host="localhost", port=8080)
        client.connection = mock_connection

        result = client.execute_update("INSERT INTO nonexistent VALUES (1)")

        assert result is False
        mock_console.print.assert_any_call("[red]❌ Statement failed: Update failed[/red]")
        mock_logger.error.assert_called_once_with("Statement execution failed: Update failed")

    @patch("demo_client.client.console")
    def test_get_server_info_no_connection(self, mock_console):
        """Test server info retrieval without connection."""
        client = MPZSQLClient(host="localhost", port=8080)
        result = client.get_server_info()

        assert result is False
        mock_console.print.assert_any_call("[red]❌ Not connected to server[/red]")

    @patch("demo_client.client.console")
    def test_get_server_info_success(self, mock_console):
        """Test successful server info retrieval."""
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_table1 = Mock()
        mock_table1.num_rows = 1
        mock_table2 = Mock()
        mock_table2.num_rows = 1

        mock_connection.cursor.return_value = mock_cursor
        mock_cursor.fetch_arrow_table.side_effect = [mock_table1, mock_table2]

        client = MPZSQLClient(host="localhost", port=8080)
        client.connection = mock_connection

        result = client.get_server_info()

        assert result is True
        assert mock_cursor.execute.call_count == 2
        mock_console.print.assert_any_call("  • Server Test: ✅ (Rows: 1)")
        mock_console.print.assert_any_call("  • Current Time: ✅ (Rows: 1)")

    @patch("demo_client.client.console")
    def test_get_server_info_partial_failure(self, mock_console):
        """Test server info retrieval with some queries failing."""
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_table = Mock()
        mock_table.num_rows = 1

        mock_connection.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = [None, Exception("Time query failed")]
        mock_cursor.fetch_arrow_table.side_effect = [mock_table, Exception("Time query failed")]

        client = MPZSQLClient(host="localhost", port=8080)
        client.connection = mock_connection

        result = client.get_server_info()

        assert result is True  # Method still succeeds even if individual queries fail
        mock_console.print.assert_any_call("  • Server Test: ✅ (Rows: 1)")
        # Should show truncated error message
        call_args = mock_console.print.call_args_list
        error_calls = [call for call in call_args if "❌" in str(call)]
        assert len(error_calls) > 0

    @patch("demo_client.client.console")
    def test_list_catalogs_no_connection(self, mock_console):
        """Test catalog listing without connection."""
        client = MPZSQLClient(host="localhost", port=8080)
        result = client.list_catalogs()

        assert result is False
        mock_console.print.assert_any_call("[red]❌ Not connected to server[/red]")

    @patch("demo_client.client.console")
    def test_list_catalogs_success(self, mock_console):
        """Test successful catalog listing."""
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_table = Mock()
        mock_table.num_rows = 2

        mock_connection.cursor.return_value = mock_cursor
        mock_cursor.fetch_arrow_table.return_value = mock_table

        client = MPZSQLClient(host="localhost", port=8080)
        client.connection = mock_connection

        # Mock execute_query to return the mock table
        with patch.object(client, 'execute_query', return_value=mock_table):
            with patch.object(client, '_display_table') as mock_display:
                result = client.list_catalogs()

        assert result is True
        # Should call _display_table with the result
        mock_display.assert_called_once()

    def test_display_table_empty(self):
        """Test table display with empty table."""
        # Create empty Arrow table correctly
        table = pa.table({
            "id": pa.array([], type=pa.int64()),
            "name": pa.array([], type=pa.string())
        })

        client = MPZSQLClient(host="localhost", port=8080)
        
        # Should not raise an error
        with patch("demo_client.client.console") as mock_console:
            client._display_table(table, "Empty Test")
            mock_console.print.assert_called()

    def test_display_table_with_data(self):
        """Test table display with data."""
        # Create Arrow table with data
        table = pa.table({
            "id": [1, 2, 3],
            "name": ["Alice", "Bob", "Charlie"],
            "score": [95.5, 87.2, 92.1]
        })

        client = MPZSQLClient(host="localhost", port=8080)
        
        with patch("demo_client.client.console") as mock_console:
            client._display_table(table, "Test Results")
            mock_console.print.assert_called()

    def test_display_table_large_data(self):
        """Test table display with large data set (should be truncated)."""
        # Create large Arrow table (more than 100 rows to trigger truncation)
        table = pa.table({
            "id": list(range(150)),
            "value": [f"item_{i}" for i in range(150)]
        })

        client = MPZSQLClient(host="localhost", port=8080)
        
        with patch("demo_client.client.console") as mock_console:
            client._display_table(table, "Large Data")
            # Should show showing message for truncated results
            call_args = [str(call) for call in mock_console.print.call_args_list]
            showing_messages = [call for call in call_args if "showing" in call.lower() and "150" in call]
            assert len(showing_messages) > 0


class TestDemoModule:
    """Test the demo.py module."""

    @patch("demo_client.demo.MPZSQLClient")
    def test_demo_main_success(self, mock_client_class):
        """Test successful demo execution."""
        mock_client = Mock()
        mock_client.connect.return_value = True
        mock_client.get_server_info.return_value = True
        
        # Mock query results
        mock_table = Mock()
        mock_client.execute_query.return_value = mock_table
        mock_client._display_table.return_value = None
        
        mock_client_class.return_value = mock_client

        with patch("builtins.print") as mock_print:
            result = demo_main()

        assert result == 0
        mock_client.connect.assert_called_once()
        mock_client.get_server_info.assert_called_once()
        assert mock_client.execute_query.call_count == 3  # Three test queries
        mock_client.disconnect.assert_called_once()

    @patch("demo_client.demo.MPZSQLClient")
    def test_demo_main_connection_failure(self, mock_client_class):
        """Test demo with connection failure."""
        mock_client = Mock()
        mock_client.connect.return_value = False
        mock_client_class.return_value = mock_client

        with patch("builtins.print") as mock_print:
            result = demo_main()

        assert result == 1
        mock_client.connect.assert_called_once()
        mock_client.get_server_info.assert_not_called()

    @patch("demo_client.demo.MPZSQLClient")
    def test_demo_main_keyboard_interrupt(self, mock_client_class):
        """Test demo with keyboard interrupt."""
        mock_client = Mock()
        mock_client.connect.return_value = True
        mock_client.get_server_info.side_effect = KeyboardInterrupt()
        mock_client_class.return_value = mock_client

        with patch("builtins.print") as mock_print:
            result = demo_main()

        assert result == 0  # Keyboard interrupt is handled gracefully
        mock_client.disconnect.assert_called_once()

    @patch("demo_client.demo.MPZSQLClient")
    def test_demo_main_exception(self, mock_client_class):
        """Test demo with unexpected exception."""
        mock_client = Mock()
        mock_client.connect.return_value = True
        mock_client.get_server_info.side_effect = Exception("Unexpected error")
        mock_client_class.return_value = mock_client

        with patch("builtins.print") as mock_print:
            result = demo_main()

        assert result == 1
        mock_client.disconnect.assert_called_once()


class TestClientUtilities:
    """Test utility functions and edge cases."""

    def test_typer_app_configuration(self):
        """Test that the typer app is configured correctly."""
        assert app.info.name == "mpzsql-client"
        assert "Demo client for MPZSQL FlightSQL server" in app.info.help

    def test_console_instance(self):
        """Test that console instance is created."""
        from demo_client.client import console
        assert console is not None

    def test_logger_configuration(self):
        """Test that logger is configured."""
        from demo_client.client import logger
        assert logger.name == "demo_client.client"


if __name__ == "__main__":
    pytest.main(["-v", __file__])
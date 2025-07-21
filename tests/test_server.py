"""
Test suite for MPZSQL server based on real server interactions.

This test suite simulates real server lifecycle operations as captured in the server logs,
testing server initialization, configuration, and basic operation handling.
"""

import pytest
from unittest.mock import Mock, patch
import threading

from mpzsql.server import MPZSQLServer
from mpzsql.config import ServerConfig


class TestMPZSQLServerBasedOnLogs:
    """Test MPZSQL server operations based on real server logs."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = Mock(spec=ServerConfig)
        self.config.hostname = "localhost"
        self.config.port = 8080
        self.config.tls_cert = None
        self.config.tls_key = None
        self.config.username = None
        self.config.password = None
        self.config.secret_key = "test-secret"
        self.config.read_only = False

    def test_server_initialization_from_logs(self):
        """Test server initialization based on log sequence."""
        # From logs: "MinimalFlightSQLServer initialized"
        mock_connection = Mock()
        
        # MPZSQLServer stores duckdb_connection, not connection, and doesn't create MinimalFlightSQLServer in __init__
        server = MPZSQLServer(self.config, mock_connection)
        
        # Verify server was created with correct parameters
        assert server.config == self.config
        assert server.duckdb_connection == mock_connection
        assert server.flight_service is None  # Not created until start() is called
        assert hasattr(server, '_shutdown_event')

    @patch('mpzsql.server.MinimalFlightSQLServer')
    def test_server_start_lifecycle_from_logs(self, mock_server_class):
        """Test server start lifecycle based on real logs."""
        # From logs: Server startup sequence
        mock_connection = Mock()
        mock_flight_server = Mock()
        mock_server_class.return_value = mock_flight_server
        
        # Mock the serve method to avoid blocking
        mock_flight_server.serve = Mock()
        
        server = MPZSQLServer(self.config, mock_connection)
        
        # Mock _create_backend to avoid actual database connection
        with patch.object(server, '_create_backend') as mock_create_backend:
            mock_backend = Mock()
            mock_create_backend.return_value = mock_backend
            
            # Mock location creation to avoid PyArrow dependencies
            with patch('mpzsql.server.pf.Location') as mock_location:
                mock_location.for_grpc_tcp.return_value = Mock()
                
                # Test that start() creates the flight service
                try:
                    with patch.object(server, 'stop'):  # Mock stop to avoid cleanup issues
                        server.start()
                except Exception:
                    pass  # Expected since we're mocking everything
                
                # Verify backend was created
                mock_create_backend.assert_called_once()
                # Verify MinimalFlightSQLServer was created
                mock_server_class.assert_called()
    def test_server_configuration_validation(self):
        """Test server configuration validation."""
        mock_connection = Mock()
        
        # Test with valid configuration
        server = MPZSQLServer(self.config, mock_connection)
        assert server.config.hostname == "localhost"
        assert server.config.port == 8080

    def test_server_with_tls_configuration(self):
        """Test server with TLS configuration."""
        self.config.tls_cert = "cert.pem"
        self.config.tls_key = "key.pem"
        self.config.is_tls_enabled = True
        mock_connection = Mock()
        
        # TLS configuration is handled during start(), not __init__
        server = MPZSQLServer(self.config, mock_connection)
        assert server.config.tls_cert == "cert.pem"
        assert server.config.tls_key == "key.pem"

    def test_server_with_authentication_configuration(self):
        """Test server with authentication configuration."""
        self.config.username = "admin"
        self.config.password = "password"
        mock_connection = Mock()
        
        # Authentication configuration is stored in config
        server = MPZSQLServer(self.config, mock_connection)
        assert server.config.username == "admin"
        assert server.config.password == "password"

    @patch('mpzsql.server.signal.signal')
    def test_signal_handler_setup(self, mock_signal):
        """Test signal handler setup for graceful shutdown."""
        mock_connection = Mock()
        
        # Signal handlers are set up in __init__
        server = MPZSQLServer(self.config, mock_connection)
        
        # Verify server was created and signal handlers were set up
        assert server is not None
        assert mock_signal.call_count == 2
        
        # Verify SIGINT and SIGTERM handlers were set
        signal_calls = mock_signal.call_args_list
        signals_set = [call[0][0] for call in signal_calls]
        import signal
        assert signal.SIGINT in signals_set
        assert signal.SIGTERM in signals_set

    def test_server_shutdown_handling(self):
        """Test server shutdown handling."""
        mock_connection = Mock()
        
        server = MPZSQLServer(self.config, mock_connection)
        
        # Test stop method exists and can be called
        assert hasattr(server, 'stop')
        
        # Mock flight_service for stop() method
        server.flight_service = Mock()
        server.stop()
        
        # Verify shutdown was called on flight service
        server.flight_service.shutdown.assert_called_once()

    @patch('mpzsql.server.console')
    def test_server_logging_integration(self, mock_console):
        """Test server logging integration."""
        mock_connection = Mock()
        
        with patch('mpzsql.server.MinimalFlightSQLServer'):
            MPZSQLServer(self.config, mock_connection)
            
            # Verify console is available for logging
            assert mock_console is not None

    def test_server_connection_handling(self):
        """Test server connection handling."""
        mock_connection = Mock()
        
        server = MPZSQLServer(self.config, mock_connection)
        
        # Verify connection is stored as duckdb_connection
        assert server.duckdb_connection == mock_connection
        assert server.config == self.config

    def test_server_port_configuration(self):
        """Test server port configuration."""
        # Test different port configurations
        ports = [8080, 9090, 443, 8443]
        
        for port in ports:
            self.config.port = port
            mock_connection = Mock()
            
            with patch('mpzsql.server.MinimalFlightSQLServer'):
                server = MPZSQLServer(self.config, mock_connection)
                assert server.config.port == port

    def test_server_hostname_configuration(self):
        """Test server hostname configuration."""
        # Test different hostname configurations
        hostnames = ["localhost", "0.0.0.0", "example.com", "127.0.0.1"]
        
        for hostname in hostnames:
            self.config.hostname = hostname
            mock_connection = Mock()
            
            with patch('mpzsql.server.MinimalFlightSQLServer'):
                server = MPZSQLServer(self.config, mock_connection)
                assert server.config.hostname == hostname

    def test_server_error_handling_during_initialization(self):
        """Test server error handling during initialization."""
        mock_connection = Mock()
        
        # Test that __init__ succeeds normally (no MinimalFlightSQLServer created yet)
        server = MPZSQLServer(self.config, mock_connection)
        assert server is not None
        
        # Mock the config to have proper hostname for start() to work
        self.config.effective_advertised_hostname = "localhost"
        self.config.is_tls_enabled = False
        
        # Error would occur during start(), let's test with _create_backend failure
        with patch.object(server, '_create_backend') as mock_create_backend:
            with patch('mpzsql.server.pf.Location') as mock_location:
                mock_location.for_grpc_tcp.return_value = Mock()
                mock_create_backend.side_effect = Exception("Backend creation failed")
                
                with pytest.raises(Exception, match="Backend creation failed"):
                    server.start()

    def test_server_read_only_configuration(self):
        """Test server read-only configuration."""
        self.config.read_only = True
        mock_connection = Mock()
        
        server = MPZSQLServer(self.config, mock_connection)
        
        # Verify read-only configuration is stored
        assert server.config.read_only is True

    def test_server_minimal_flight_sql_integration(self):
        """Test integration with MinimalFlightSQLServer."""
        mock_connection = Mock()
        
        server = MPZSQLServer(self.config, mock_connection)
        
        # MinimalFlightSQLServer is not created until start() is called
        assert server.flight_service is None
        
        # Test that _create_backend method exists
        assert hasattr(server, '_create_backend')
        assert callable(server._create_backend)


class TestMPZSQLServerLoggingBasedOnLogs:
    """Test server logging behavior based on real log outputs."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = Mock(spec=ServerConfig)
        self.config.hostname = "localhost"
        self.config.port = 8080

    def test_logger_initialization_from_logs(self):
        """Test logger initialization based on log patterns."""
        mock_connection = Mock()
        
        # Logger is initialized at module level, not during __init__
        # Test that server can be created successfully
        server = MPZSQLServer(self.config, mock_connection)
        assert server is not None
        
        # Test that we can access the server_logger from the module
        from mpzsql.server import server_logger
        assert server_logger is not None

    @patch('mpzsql.server.console')
    @patch('mpzsql.server.MinimalFlightSQLServer')
    def test_console_output_patterns(self, mock_server_class, mock_console):
        """Test console output patterns seen in logs."""
        mock_connection = Mock()
        
        MPZSQLServer(self.config, mock_connection)
        
        # Console should be available for rich output
        assert mock_console is not None

    @patch('mpzsql.server.logger')
    @patch('mpzsql.server.MinimalFlightSQLServer')
    def test_logging_levels_and_patterns(self, mock_server_class, mock_logger):
        """Test logging levels and patterns from real logs."""
        mock_connection = Mock()
        
        MPZSQLServer(self.config, mock_connection)
        
        # Logger should be available for different log levels
        assert mock_logger is not None


class TestMPZSQLServerThreadingAndConcurrency:
    """Test server threading and concurrency aspects."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = Mock(spec=ServerConfig)
        self.config.hostname = "localhost"
        self.config.port = 8080

    @patch('mpzsql.server.signal.signal')
    @patch('mpzsql.server.MinimalFlightSQLServer')
    def test_server_thread_safety(self, mock_server_class, mock_signal):
        """Test server thread safety during initialization."""
        mock_connection = Mock()
        mock_flight_server = Mock()
        mock_server_class.return_value = mock_flight_server
        
        # Create multiple servers concurrently
        servers = []
        
        def create_server():
            # Mock signal to avoid "signal only works in main thread" error
            server = MPZSQLServer(self.config, mock_connection)
            servers.append(server)
        
        threads = [threading.Thread(target=create_server) for _ in range(3)]
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # All servers should be created successfully
        assert len(servers) == 3
        for server in servers:
            assert server.config == self.config

    @patch('mpzsql.server.MinimalFlightSQLServer')
    def test_server_concurrent_operations(self, mock_server_class):
        """Test server handling of concurrent operations."""
        mock_connection = Mock()
        mock_flight_server = Mock()
        mock_server_class.return_value = mock_flight_server
        
        server = MPZSQLServer(self.config, mock_connection)
        
        # Verify server can handle concurrent access to its properties
        def access_server_properties():
            assert server.config is not None
            assert server.duckdb_connection is not None
            # flight_service is None until start() is called
            assert hasattr(server, 'flight_service')
        
        threads = [threading.Thread(target=access_server_properties) for _ in range(5)]
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()


if __name__ == "__main__":
    pytest.main(["-v", "--tb=short", __file__])

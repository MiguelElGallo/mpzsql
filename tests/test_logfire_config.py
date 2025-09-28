"""
Comprehensive tests for logfire_config.py module to improve code coverage.

This test suite covers the LogfireManager class and all logging utility functions,
focusing on initialization, fallback handling, and different logging scenarios.
"""

import os
from unittest.mock import Mock, patch, MagicMock
from contextlib import contextmanager

import pytest

from mpzsql.logfire_config import (
    LogfireManager,
    get_main_logger,
    get_duckdb_logger,
    get_protobuf_logger,
    get_actions_logger,
    get_routing_logger,
    get_auth_logger,
    get_transaction_logger,
    get_sqlite_logger,
)


class TestLogfireManager:
    """Test the LogfireManager class."""

    def setup_method(self):
        """Reset LogfireManager state before each test."""
        LogfireManager._initialized = False
        LogfireManager._logfire_instance = None

    def teardown_method(self):
        """Clean up after each test."""
        LogfireManager._initialized = False
        LogfireManager._logfire_instance = None

    @patch("mpzsql.logfire_config.logfire")
    def test_initialize_with_token_parameter(self, mock_logfire):
        """Test initialization with token parameter."""
        mock_logfire.configure = Mock()
        
        LogfireManager.initialize(token="test_token")
        
        assert LogfireManager._initialized is True
        assert LogfireManager._logfire_instance == mock_logfire
        mock_logfire.configure.assert_called_once_with(token="test_token", inspect_arguments=False)

    @patch.dict(os.environ, {"LOGFIRE_WRITE_TOKEN": "env_token"})
    @patch("mpzsql.logfire_config.logfire")
    def test_initialize_with_env_token(self, mock_logfire):
        """Test initialization with environment token."""
        mock_logfire.configure = Mock()
        
        LogfireManager.initialize()
        
        assert LogfireManager._initialized is True
        assert LogfireManager._logfire_instance == mock_logfire
        mock_logfire.configure.assert_called_once_with(token="env_token", inspect_arguments=False)

    @patch("mpzsql.logfire_config.logfire")
    def test_initialize_without_token_success(self, mock_logfire):
        """Test initialization without token - successful configuration."""
        mock_logfire.configure = Mock()
        
        LogfireManager.initialize()
        
        assert LogfireManager._initialized is True
        assert LogfireManager._logfire_instance == mock_logfire
        mock_logfire.configure.assert_called_once_with(inspect_arguments=False)

    @patch("mpzsql.logfire_config.logfire")
    @patch("builtins.print")
    def test_initialize_without_token_fallback(self, mock_print, mock_logfire):
        """Test initialization without token - falls back to fallback logger."""
        mock_logfire.configure.side_effect = Exception("Auth failed")
        
        LogfireManager.initialize()
        
        assert LogfireManager._initialized is True
        assert LogfireManager._logfire_instance is not None
        # Should have printed warning
        mock_print.assert_called()
        call_args = str(mock_print.call_args)
        assert "Warning: Logfire authentication failed" in call_args

    @patch("mpzsql.logfire_config.logfire")
    @patch("builtins.print")
    def test_initialize_with_token_configuration_failure(self, mock_print, mock_logfire):
        """Test initialization with token but configuration fails."""
        mock_logfire.configure.side_effect = Exception("Config failed")
        
        LogfireManager.initialize(token="test_token")
        
        assert LogfireManager._initialized is True
        assert LogfireManager._logfire_instance is not None
        # Should have printed warning
        mock_print.assert_called()
        call_args = str(mock_print.call_args)
        assert "Warning: Logfire configuration failed" in call_args

    def test_initialize_twice_no_effect(self):
        """Test that calling initialize twice has no effect."""
        with patch("mpzsql.logfire_config.logfire") as mock_logfire:
            mock_logfire.configure = Mock()
            
            # First call
            LogfireManager.initialize(token="test_token")
            # Second call
            LogfireManager.initialize(token="different_token")
            
            # Should only be called once
            mock_logfire.configure.assert_called_once()

    def test_create_fallback_logger(self):
        """Test creation of fallback logger."""
        fallback = LogfireManager._create_fallback_logger()
        
        assert fallback is not None
        assert hasattr(fallback, 'info')
        assert hasattr(fallback, 'debug')
        assert hasattr(fallback, 'warning')
        assert hasattr(fallback, 'error')
        assert hasattr(fallback, 'span')

    def test_fallback_logger_methods(self):
        """Test fallback logger methods work correctly."""
        fallback = LogfireManager._create_fallback_logger()
        
        # Test logging methods without raising errors
        fallback.info("Test info message")
        fallback.info("Test info with kwargs", key="value")
        fallback.debug("Test debug message")
        fallback.debug("Test debug with kwargs", key="value")
        fallback.warning("Test warning message")
        fallback.warning("Test warning with kwargs", key="value")
        fallback.error("Test error message")
        fallback.error("Test error with kwargs", key="value")

    def test_fallback_logger_span(self):
        """Test fallback logger span method."""
        fallback = LogfireManager._create_fallback_logger()
        
        # Test span context manager
        with fallback.span("test_span", operation="test"):
            pass  # Should not raise any errors

    @patch("mpzsql.logfire_config.logfire")
    def test_get_logger_auto_initializes(self, mock_logfire):
        """Test that get_logger auto-initializes if not initialized."""
        mock_logfire.configure = Mock()
        
        logger = LogfireManager.get_logger("test")
        
        assert LogfireManager._initialized is True
        assert logger == mock_logfire

    @patch("mpzsql.logfire_config.logfire")
    def test_get_logger_with_name(self, mock_logfire):
        """Test get_logger with name parameter."""
        mock_logfire.configure = Mock()
        
        logger = LogfireManager.get_logger("test_name")
        
        assert logger == mock_logfire

    @patch("mpzsql.logfire_config.logfire")
    def test_span_method(self, mock_logfire):
        """Test LogfireManager span method."""
        mock_logfire.configure = Mock()
        mock_span = Mock()
        mock_logfire.span.return_value = mock_span
        
        result = LogfireManager.span("test_span", operation="test")
        
        assert result == mock_span
        mock_logfire.span.assert_called_once_with("test_span", operation="test")

    @patch("mpzsql.logfire_config.logfire")
    def test_info_method(self, mock_logfire):
        """Test LogfireManager info method."""
        mock_logfire.configure = Mock()
        mock_logfire.info = Mock()
        
        LogfireManager.info("test message", key="value")
        
        mock_logfire.info.assert_called_once_with("test message", key="value")

    @patch("mpzsql.logfire_config.logfire")
    def test_debug_method(self, mock_logfire):
        """Test LogfireManager debug method."""
        mock_logfire.configure = Mock()
        mock_logfire.debug = Mock()
        
        LogfireManager.debug("test message", key="value")
        
        mock_logfire.debug.assert_called_once_with("test message", key="value")

    @patch("mpzsql.logfire_config.logfire")
    def test_warning_method(self, mock_logfire):
        """Test LogfireManager warning method."""
        mock_logfire.configure = Mock()
        mock_logfire.warning = Mock()
        
        LogfireManager.warning("test message", key="value")
        
        mock_logfire.warning.assert_called_once_with("test message", key="value")

    @patch("mpzsql.logfire_config.logfire")
    def test_error_method(self, mock_logfire):
        """Test LogfireManager error method."""
        mock_logfire.configure = Mock()
        mock_logfire.error = Mock()
        
        LogfireManager.error("test message", key="value")
        
        mock_logfire.error.assert_called_once_with("test message", key="value")

    @patch("mpzsql.logfire_config.logfire")
    def test_logging_methods_auto_initialize(self, mock_logfire):
        """Test that logging methods auto-initialize if not initialized."""
        mock_logfire.configure = Mock()
        mock_logfire.info = Mock()
        mock_logfire.debug = Mock()
        mock_logfire.warning = Mock()
        mock_logfire.error = Mock()
        mock_logfire.span = Mock()
        
        # Call each method - should trigger initialization
        LogfireManager.info("test")
        LogfireManager.debug("test")
        LogfireManager.warning("test")
        LogfireManager.error("test")
        LogfireManager.span("test")
        
        # Should have called configure
        mock_logfire.configure.assert_called()


class TestConvenienceFunctions:
    """Test the convenience logger functions."""

    def setup_method(self):
        """Reset LogfireManager state before each test."""
        LogfireManager._initialized = False
        LogfireManager._logfire_instance = None

    def teardown_method(self):
        """Clean up after each test."""
        LogfireManager._initialized = False
        LogfireManager._logfire_instance = None

    @patch("mpzsql.logfire_config.LogfireManager.get_logger")
    def test_get_main_logger(self, mock_get_logger):
        """Test get_main_logger function."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        
        result = get_main_logger()
        
        assert result == mock_logger
        mock_get_logger.assert_called_once_with("mpzsql.main")

    @patch("mpzsql.logfire_config.LogfireManager.get_logger")
    def test_get_duckdb_logger(self, mock_get_logger):
        """Test get_duckdb_logger function."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        
        result = get_duckdb_logger()
        
        assert result == mock_logger
        mock_get_logger.assert_called_once_with("mpzsql.duckdb")

    @patch("mpzsql.logfire_config.LogfireManager.get_logger")
    def test_get_protobuf_logger(self, mock_get_logger):
        """Test get_protobuf_logger function."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        
        result = get_protobuf_logger()
        
        assert result == mock_logger
        mock_get_logger.assert_called_once_with("mpzsql.protobuf")

    @patch("mpzsql.logfire_config.LogfireManager.get_logger")
    def test_get_actions_logger(self, mock_get_logger):
        """Test get_actions_logger function."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        
        result = get_actions_logger()
        
        assert result == mock_logger
        mock_get_logger.assert_called_once_with("mpzsql.actions")

    @patch("mpzsql.logfire_config.LogfireManager.get_logger")
    def test_get_routing_logger(self, mock_get_logger):
        """Test get_routing_logger function."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        
        result = get_routing_logger()
        
        assert result == mock_logger
        mock_get_logger.assert_called_once_with("mpzsql.routing")

    @patch("mpzsql.logfire_config.LogfireManager.get_logger")
    def test_get_auth_logger(self, mock_get_logger):
        """Test get_auth_logger function."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        
        result = get_auth_logger()
        
        assert result == mock_logger
        mock_get_logger.assert_called_once_with("mpzsql.auth")

    @patch("mpzsql.logfire_config.LogfireManager.get_logger")
    def test_get_transaction_logger(self, mock_get_logger):
        """Test get_transaction_logger function."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        
        result = get_transaction_logger()
        
        assert result == mock_logger
        mock_get_logger.assert_called_once_with("mpzsql.transaction")

    @patch("mpzsql.logfire_config.LogfireManager.get_logger")
    def test_get_sqlite_logger(self, mock_get_logger):
        """Test get_sqlite_logger function."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        
        result = get_sqlite_logger()
        
        assert result == mock_logger
        mock_get_logger.assert_called_once_with("mpzsql.sqlite")


class TestIntegrationScenarios:
    """Test integration scenarios with LogfireManager."""

    def setup_method(self):
        """Reset LogfireManager state before each test."""
        LogfireManager._initialized = False
        LogfireManager._logfire_instance = None

    def teardown_method(self):
        """Clean up after each test."""
        LogfireManager._initialized = False
        LogfireManager._logfire_instance = None

    @patch("mpzsql.logfire_config.logfire")
    def test_full_workflow_with_logfire(self, mock_logfire):
        """Test full workflow with successful logfire setup."""
        mock_logfire.configure = Mock()
        mock_logfire.info = Mock()
        mock_logfire.span = Mock()
        
        # Initialize with token
        LogfireManager.initialize(token="test_token")
        
        # Get logger and use it
        logger = LogfireManager.get_logger("test")
        
        # Use logging methods
        LogfireManager.info("Test message")
        LogfireManager.span("test_span")
        
        # Use convenience functions
        main_logger = get_main_logger()
        duckdb_logger = get_duckdb_logger()
        
        # Verify all worked
        assert LogfireManager._initialized is True
        assert logger == mock_logfire
        assert main_logger == mock_logfire
        assert duckdb_logger == mock_logfire
        mock_logfire.info.assert_called_once_with("Test message")

    def test_full_workflow_with_fallback(self):
        """Test full workflow with fallback logger."""
        with patch("mpzsql.logfire_config.logfire") as mock_logfire:
            mock_logfire.configure.side_effect = Exception("Auth failed")
            
            with patch("builtins.print"):
                # Initialize - should create fallback
                LogfireManager.initialize()
                
                # Get logger and use it
                logger = LogfireManager.get_logger("test")
                
                # Use logging methods - should not raise errors
                LogfireManager.info("Test message")
                LogfireManager.debug("Debug message")
                LogfireManager.warning("Warning message")
                LogfireManager.error("Error message")
                
                with LogfireManager.span("test_span"):
                    pass
                
                # Use convenience functions
                main_logger = get_main_logger()
                duckdb_logger = get_duckdb_logger()
                
                # Verify fallback is working
                assert LogfireManager._initialized is True
                assert logger is not None
                assert main_logger is not None
                assert duckdb_logger is not None


if __name__ == "__main__":
    pytest.main(["-v", __file__])
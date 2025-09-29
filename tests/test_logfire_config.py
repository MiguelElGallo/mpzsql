"""
Comprehensive tests for MPZSQL logfire configuration.

Tests for mpzsql.logfire_config module covering LogfireManager initialization,
fallback behavior, and logger convenience functions.
"""

import logging
import os
from contextlib import contextmanager
from unittest.mock import MagicMock, Mock, patch

import pytest

from mpzsql.logfire_config import (
    LogfireManager,
    get_actions_logger,
    get_auth_logger,
    get_duckdb_logger,
    get_main_logger,
    get_protobuf_logger,
    get_routing_logger,
    get_sqlite_logger,
    get_transaction_logger,
)


class TestLogfireManagerInitialization:
    """Test LogfireManager initialization scenarios."""

    def setup_method(self) -> None:
        """Reset LogfireManager state before each test."""
        LogfireManager._initialized = False
        LogfireManager._logfire_instance = None

    def teardown_method(self) -> None:
        """Clean up after each test."""
        LogfireManager._initialized = False
        LogfireManager._logfire_instance = None
        # Clean up environment variables
        if "LOGFIRE_WRITE_TOKEN" in os.environ:
            del os.environ["LOGFIRE_WRITE_TOKEN"]

    def test_initialize_with_token_parameter(self) -> None:
        """Test initialization with explicit token parameter."""
        with patch("mpzsql.logfire_config.logfire") as mock_logfire:
            LogfireManager.initialize(token="test-token-123")
            
            assert LogfireManager._initialized is True
            assert LogfireManager._logfire_instance == mock_logfire
            mock_logfire.configure.assert_called_once_with(
                token="test-token-123",
                inspect_arguments=False
            )

    def test_initialize_with_environment_token(self) -> None:
        """Test initialization with token from environment variable."""
        os.environ["LOGFIRE_WRITE_TOKEN"] = "env-token-456"
        
        with patch("mpzsql.logfire_config.logfire") as mock_logfire:
            LogfireManager.initialize()
            
            assert LogfireManager._initialized is True
            assert LogfireManager._logfire_instance == mock_logfire
            mock_logfire.configure.assert_called_once_with(
                token="env-token-456",
                inspect_arguments=False
            )

    def test_initialize_parameter_overrides_environment(self) -> None:
        """Test that explicit parameter overrides environment variable."""
        os.environ["LOGFIRE_WRITE_TOKEN"] = "env-token"
        
        with patch("mpzsql.logfire_config.logfire") as mock_logfire:
            LogfireManager.initialize(token="param-token")
            
            assert LogfireManager._initialized is True
            mock_logfire.configure.assert_called_once_with(
                token="param-token",
                inspect_arguments=False
            )

    def test_initialize_without_token_success(self) -> None:
        """Test initialization without token that succeeds."""
        with patch("mpzsql.logfire_config.logfire") as mock_logfire:
            LogfireManager.initialize()
            
            assert LogfireManager._initialized is True
            assert LogfireManager._logfire_instance == mock_logfire
            mock_logfire.configure.assert_called_once_with(inspect_arguments=False)

    def test_initialize_without_token_fails_creates_fallback(self) -> None:
        """Test initialization without token that fails and creates fallback."""
        with patch("mpzsql.logfire_config.logfire") as mock_logfire:
            mock_logfire.configure.side_effect = Exception("Auth failed")
            
            with patch("builtins.print") as mock_print:
                LogfireManager.initialize()
            
            assert LogfireManager._initialized is True
            assert LogfireManager._logfire_instance is not None
            # Should be fallback logger, not the mock logfire
            assert LogfireManager._logfire_instance != mock_logfire
            mock_print.assert_called_once()
            assert "Logfire authentication failed" in mock_print.call_args[0][0]

    def test_initialize_with_token_fails_creates_fallback(self) -> None:
        """Test initialization with token that fails and creates fallback."""
        with patch("mpzsql.logfire_config.logfire") as mock_logfire:
            mock_logfire.configure.side_effect = Exception("Config failed")
            
            with patch("builtins.print") as mock_print:
                LogfireManager.initialize(token="test-token")
            
            assert LogfireManager._initialized is True
            assert LogfireManager._logfire_instance is not None
            assert LogfireManager._logfire_instance != mock_logfire
            mock_print.assert_called_once()
            assert "Logfire configuration failed" in mock_print.call_args[0][0]

    def test_initialize_multiple_calls_idempotent(self) -> None:
        """Test that multiple initialization calls are idempotent."""
        with patch("mpzsql.logfire_config.logfire") as mock_logfire:
            LogfireManager.initialize(token="test-token")
            LogfireManager.initialize(token="different-token")  # Should be ignored
            
            assert LogfireManager._initialized is True
            # Should only be called once with the first token
            mock_logfire.configure.assert_called_once_with(
                token="test-token",
                inspect_arguments=False
            )


class TestLogfireManagerFallbackLogger:
    """Test LogfireManager fallback logger functionality."""

    def setup_method(self) -> None:
        """Reset LogfireManager state before each test."""
        LogfireManager._initialized = False
        LogfireManager._logfire_instance = None

    def teardown_method(self) -> None:
        """Clean up after each test."""
        LogfireManager._initialized = False
        LogfireManager._logfire_instance = None

    def test_fallback_logger_creation(self) -> None:
        """Test creation of fallback logger."""
        fallback = LogfireManager._create_fallback_logger()
        
        assert hasattr(fallback, "info")
        assert hasattr(fallback, "debug")
        assert hasattr(fallback, "warning")
        assert hasattr(fallback, "error")
        assert hasattr(fallback, "span")
        assert hasattr(fallback.logger, "info")

    def test_fallback_logger_info_without_kwargs(self) -> None:
        """Test fallback logger info method without kwargs."""
        fallback = LogfireManager._create_fallback_logger()
        
        with patch.object(fallback.logger, "info") as mock_info:
            fallback.info("Test message")
            mock_info.assert_called_once_with("Test message")

    def test_fallback_logger_info_with_kwargs(self) -> None:
        """Test fallback logger info method with kwargs."""
        fallback = LogfireManager._create_fallback_logger()
        
        with patch.object(fallback.logger, "info") as mock_info:
            fallback.info("Test message", key1="value1", key2="value2")
            mock_info.assert_called_once_with("Test message - {'key1': 'value1', 'key2': 'value2'}")

    def test_fallback_logger_debug_methods(self) -> None:
        """Test fallback logger debug method."""
        fallback = LogfireManager._create_fallback_logger()
        
        with patch.object(fallback.logger, "debug") as mock_debug:
            fallback.debug("Debug message")
            mock_debug.assert_called_once_with("Debug message")
            
            mock_debug.reset_mock()
            fallback.debug("Debug with kwargs", user="test")
            mock_debug.assert_called_once_with("Debug with kwargs - {'user': 'test'}")

    def test_fallback_logger_warning_methods(self) -> None:
        """Test fallback logger warning method."""
        fallback = LogfireManager._create_fallback_logger()
        
        with patch.object(fallback.logger, "warning") as mock_warning:
            fallback.warning("Warning message")
            mock_warning.assert_called_once_with("Warning message")
            
            mock_warning.reset_mock()
            fallback.warning("Warning with kwargs", code=404)
            mock_warning.assert_called_once_with("Warning with kwargs - {'code': 404}")

    def test_fallback_logger_error_methods(self) -> None:
        """Test fallback logger error method."""
        fallback = LogfireManager._create_fallback_logger()
        
        with patch.object(fallback.logger, "error") as mock_error:
            fallback.error("Error message")
            mock_error.assert_called_once_with("Error message")
            
            mock_error.reset_mock()
            fallback.error("Error with kwargs", exception="ValueError")
            mock_error.assert_called_once_with("Error with kwargs - {'exception': 'ValueError'}")

    def test_fallback_logger_span_context_manager(self) -> None:
        """Test fallback logger span as context manager."""
        fallback = LogfireManager._create_fallback_logger()
        
        with patch.object(fallback.logger, "debug") as mock_debug:
            with fallback.span("test_operation", operation_id=123):
                pass  # Context manager should work
            
            mock_debug.assert_called_once_with("Span: test_operation - {'operation_id': 123}")

    def test_fallback_logger_span_without_kwargs(self) -> None:
        """Test fallback logger span without kwargs."""
        fallback = LogfireManager._create_fallback_logger()
        
        with patch.object(fallback.logger, "debug") as mock_debug:
            with fallback.span("simple_operation"):
                pass
            
            mock_debug.assert_called_once_with("Span: simple_operation - {}")


class TestLogfireManagerMethods:
    """Test LogfireManager public methods."""

    def setup_method(self) -> None:
        """Reset LogfireManager state before each test."""
        LogfireManager._initialized = False
        LogfireManager._logfire_instance = None

    def teardown_method(self) -> None:
        """Clean up after each test."""
        LogfireManager._initialized = False
        LogfireManager._logfire_instance = None

    def test_get_logger_initializes_if_needed(self) -> None:
        """Test get_logger initializes LogfireManager if not initialized."""
        with patch.object(LogfireManager, "initialize") as mock_init:
            with patch("mpzsql.logfire_config.logfire") as mock_logfire:
                LogfireManager._logfire_instance = mock_logfire
                
                result = LogfireManager.get_logger("test")
                
                mock_init.assert_called_once()
                assert result == mock_logfire

    def test_get_logger_returns_instance_when_initialized(self) -> None:
        """Test get_logger returns instance when already initialized."""
        mock_instance = Mock()
        LogfireManager._initialized = True
        LogfireManager._logfire_instance = mock_instance
        
        result = LogfireManager.get_logger("test")
        assert result == mock_instance

    def test_span_method(self) -> None:
        """Test LogfireManager span method."""
        mock_instance = Mock()
        mock_span = Mock()
        mock_instance.span.return_value = mock_span
        
        LogfireManager._initialized = True
        LogfireManager._logfire_instance = mock_instance
        
        result = LogfireManager.span("test_span", param="value")
        
        mock_instance.span.assert_called_once_with("test_span", param="value")
        assert result == mock_span

    def test_span_initializes_if_needed(self) -> None:
        """Test span method initializes if needed."""
        with patch.object(LogfireManager, "initialize") as mock_init:
            mock_instance = Mock()
            LogfireManager._logfire_instance = mock_instance
            
            LogfireManager.span("test")
            
            mock_init.assert_called_once()
            mock_instance.span.assert_called_once_with("test")

    def test_info_method(self) -> None:
        """Test LogfireManager info method."""
        mock_instance = Mock()
        LogfireManager._initialized = True
        LogfireManager._logfire_instance = mock_instance
        
        LogfireManager.info("test message", key="value")
        
        mock_instance.info.assert_called_once_with("test message", key="value")

    def test_debug_method(self) -> None:
        """Test LogfireManager debug method."""
        mock_instance = Mock()
        LogfireManager._initialized = True
        LogfireManager._logfire_instance = mock_instance
        
        LogfireManager.debug("debug message", debug_key="debug_value")
        
        mock_instance.debug.assert_called_once_with("debug message", debug_key="debug_value")

    def test_warning_method(self) -> None:
        """Test LogfireManager warning method."""
        mock_instance = Mock()
        LogfireManager._initialized = True
        LogfireManager._logfire_instance = mock_instance
        
        LogfireManager.warning("warning message", warn_key="warn_value")
        
        mock_instance.warning.assert_called_once_with("warning message", warn_key="warn_value")

    def test_error_method(self) -> None:
        """Test LogfireManager error method."""
        mock_instance = Mock()
        LogfireManager._initialized = True
        LogfireManager._logfire_instance = mock_instance
        
        LogfireManager.error("error message", error_key="error_value")
        
        mock_instance.error.assert_called_once_with("error message", error_key="error_value")

    def test_logging_methods_initialize_if_needed(self) -> None:
        """Test all logging methods initialize if needed."""
        with patch.object(LogfireManager, "initialize") as mock_init:
            mock_instance = Mock()
            LogfireManager._logfire_instance = mock_instance
            
            LogfireManager.info("test")
            mock_init.assert_called_once()
            
            mock_init.reset_mock()
            LogfireManager.debug("test")
            mock_init.assert_called_once()
            
            mock_init.reset_mock()
            LogfireManager.warning("test")
            mock_init.assert_called_once()
            
            mock_init.reset_mock()
            LogfireManager.error("test")
            mock_init.assert_called_once()


class TestConvenienceFunctions:
    """Test convenience logger functions."""

    def setup_method(self) -> None:
        """Reset LogfireManager state before each test."""
        LogfireManager._initialized = False
        LogfireManager._logfire_instance = None

    def teardown_method(self) -> None:
        """Clean up after each test."""
        LogfireManager._initialized = False
        LogfireManager._logfire_instance = None

    def test_get_main_logger(self) -> None:
        """Test get_main_logger function."""
        with patch.object(LogfireManager, "get_logger") as mock_get_logger:
            get_main_logger()
            mock_get_logger.assert_called_once_with("mpzsql.main")

    def test_get_duckdb_logger(self) -> None:
        """Test get_duckdb_logger function."""
        with patch.object(LogfireManager, "get_logger") as mock_get_logger:
            get_duckdb_logger()
            mock_get_logger.assert_called_once_with("mpzsql.duckdb")

    def test_get_protobuf_logger(self) -> None:
        """Test get_protobuf_logger function."""
        with patch.object(LogfireManager, "get_logger") as mock_get_logger:
            get_protobuf_logger()
            mock_get_logger.assert_called_once_with("mpzsql.protobuf")

    def test_get_actions_logger(self) -> None:
        """Test get_actions_logger function."""
        with patch.object(LogfireManager, "get_logger") as mock_get_logger:
            get_actions_logger()
            mock_get_logger.assert_called_once_with("mpzsql.actions")

    def test_get_routing_logger(self) -> None:
        """Test get_routing_logger function."""
        with patch.object(LogfireManager, "get_logger") as mock_get_logger:
            get_routing_logger()
            mock_get_logger.assert_called_once_with("mpzsql.routing")

    def test_get_auth_logger(self) -> None:
        """Test get_auth_logger function."""
        with patch.object(LogfireManager, "get_logger") as mock_get_logger:
            get_auth_logger()
            mock_get_logger.assert_called_once_with("mpzsql.auth")

    def test_get_transaction_logger(self) -> None:
        """Test get_transaction_logger function."""
        with patch.object(LogfireManager, "get_logger") as mock_get_logger:
            get_transaction_logger()
            mock_get_logger.assert_called_once_with("mpzsql.transaction")

    def test_get_sqlite_logger(self) -> None:
        """Test get_sqlite_logger function."""
        with patch.object(LogfireManager, "get_logger") as mock_get_logger:
            get_sqlite_logger()
            mock_get_logger.assert_called_once_with("mpzsql.sqlite")


class TestLogfireManagerIntegration:
    """Test LogfireManager integration scenarios."""

    def setup_method(self) -> None:
        """Reset LogfireManager state before each test."""
        LogfireManager._initialized = False
        LogfireManager._logfire_instance = None

    def teardown_method(self) -> None:
        """Clean up after each test."""
        LogfireManager._initialized = False
        LogfireManager._logfire_instance = None
        if "LOGFIRE_WRITE_TOKEN" in os.environ:
            del os.environ["LOGFIRE_WRITE_TOKEN"]

    def test_full_workflow_with_token(self) -> None:
        """Test complete workflow with token-based initialization."""
        with patch("mpzsql.logfire_config.logfire") as mock_logfire:
            # Initialize with token
            LogfireManager.initialize(token="production-token")
            
            # Use various logging methods
            LogfireManager.info("Server starting", port=8080)
            LogfireManager.debug("Connection details", host="localhost")
            LogfireManager.warning("High memory usage", memory_mb=512)
            LogfireManager.error("Database error", error_code="DB001")
            
            # Use span
            with LogfireManager.span("database_query", query="SELECT * FROM users"):
                pass
            
            # Get logger instances
            main_logger = get_main_logger()
            duckdb_logger = get_duckdb_logger()
            
            # Verify all calls
            assert LogfireManager._initialized is True
            mock_logfire.configure.assert_called_once_with(
                token="production-token",
                inspect_arguments=False
            )
            mock_logfire.info.assert_called_with("Server starting", port=8080)
            mock_logfire.debug.assert_called_with("Connection details", host="localhost")
            mock_logfire.warning.assert_called_with("High memory usage", memory_mb=512)
            mock_logfire.error.assert_called_with("Database error", error_code="DB001")
            mock_logfire.span.assert_called_with("database_query", query="SELECT * FROM users")
            
            assert main_logger == mock_logfire
            assert duckdb_logger == mock_logfire

    def test_fallback_workflow(self) -> None:
        """Test complete workflow with fallback logger."""
        with patch("mpzsql.logfire_config.logfire") as mock_logfire:
            mock_logfire.configure.side_effect = Exception("Auth failed")
            
            with patch("builtins.print"):
                # Initialize - should create fallback
                LogfireManager.initialize(token="bad-token")
                
                # Use logging methods - should not raise exceptions
                LogfireManager.info("Fallback info", key="value")
                LogfireManager.debug("Fallback debug")
                LogfireManager.warning("Fallback warning")
                LogfireManager.error("Fallback error")
                
                # Use span
                with LogfireManager.span("fallback_operation"):
                    pass
                
                # Get logger
                logger = get_main_logger()
                
                # Verify state
                assert LogfireManager._initialized is True
                assert LogfireManager._logfire_instance is not None
                assert LogfireManager._logfire_instance != mock_logfire
                assert logger == LogfireManager._logfire_instance

    def test_mixed_environment_and_parameter_usage(self) -> None:
        """Test mixed usage with environment variables and parameters."""
        # Set environment variable
        os.environ["LOGFIRE_WRITE_TOKEN"] = "env-token"
        
        with patch("mpzsql.logfire_config.logfire") as mock_logfire:
            # First call uses environment
            logger1 = get_main_logger()
            assert LogfireManager._initialized is True
            mock_logfire.configure.assert_called_with(
                token="env-token",
                inspect_arguments=False
            )
            
            # Second call should not reinitialize
            LogfireManager.initialize(token="new-token")
            # Should still be called only once with env token
            assert mock_logfire.configure.call_count == 1

    def test_concurrent_initialization_behavior(self) -> None:
        """Test behavior with multiple loggers requested simultaneously."""
        with patch("mpzsql.logfire_config.logfire") as mock_logfire:
            # Request multiple loggers - should initialize once
            loggers = [
                get_main_logger(),
                get_duckdb_logger(),
                get_protobuf_logger(),
                get_actions_logger(),
            ]
            
            # All should be the same instance
            assert all(logger == mock_logfire for logger in loggers)
            
            # Should only configure once
            mock_logfire.configure.assert_called_once()

    def test_logger_state_persistence(self) -> None:
        """Test that logger state persists across calls."""
        with patch("mpzsql.logfire_config.logfire") as mock_logfire:
            # Initialize
            LogfireManager.initialize(token="test")
            initial_instance = LogfireManager._logfire_instance
            
            # Get loggers multiple times
            logger1 = get_main_logger()
            logger2 = get_duckdb_logger()
            logger3 = LogfireManager.get_logger("custom")
            
            # All should reference the same instance
            assert logger1 is initial_instance
            assert logger2 is initial_instance
            assert logger3 is initial_instance
            assert LogfireManager._logfire_instance is initial_instance


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def setup_method(self) -> None:
        """Reset LogfireManager state before each test."""
        LogfireManager._initialized = False
        LogfireManager._logfire_instance = None

    def teardown_method(self) -> None:
        """Clean up after each test."""
        LogfireManager._initialized = False
        LogfireManager._logfire_instance = None
        if "LOGFIRE_WRITE_TOKEN" in os.environ:
            del os.environ["LOGFIRE_WRITE_TOKEN"]

    def test_empty_string_token(self) -> None:
        """Test initialization with empty string token."""
        with patch("mpzsql.logfire_config.logfire") as mock_logfire:
            LogfireManager.initialize(token="")
            
            # Empty string is falsy, so should try without token
            mock_logfire.configure.assert_called_once_with(inspect_arguments=False)

    def test_none_token_explicit(self) -> None:
        """Test initialization with explicit None token."""
        with patch("mpzsql.logfire_config.logfire") as mock_logfire:
            LogfireManager.initialize(token=None)
            
            # None should try without token
            mock_logfire.configure.assert_called_once_with(inspect_arguments=False)

    def test_environment_variable_empty_string(self) -> None:
        """Test with empty string environment variable."""
        os.environ["LOGFIRE_WRITE_TOKEN"] = ""
        
        with patch("mpzsql.logfire_config.logfire") as mock_logfire:
            LogfireManager.initialize()
            
            # Empty string is falsy, should configure without token
            mock_logfire.configure.assert_called_once_with(inspect_arguments=False)

    def test_fallback_logger_exception_handling(self) -> None:
        """Test fallback logger propagates logging exceptions."""
        fallback = LogfireManager._create_fallback_logger()
        
        # Mock the logger to raise exceptions
        with patch.object(fallback.logger, "info", side_effect=Exception("Logging failed")):
            # Should raise exception since fallback doesn't handle them
            with pytest.raises(Exception, match="Logging failed"):
                fallback.info("This will raise an exception")

    def test_span_context_manager_exception_in_context(self) -> None:
        """Test fallback span context manager with exception in context."""
        fallback = LogfireManager._create_fallback_logger()
        
        with pytest.raises(ValueError):
            with fallback.span("test_span"):
                raise ValueError("Test exception in span context")
        
        # Span should still complete properly despite exception

    def test_multiple_fallback_creations(self) -> None:
        """Test multiple fallback logger creations are independent wrapper instances."""
        fallback1 = LogfireManager._create_fallback_logger()
        fallback2 = LogfireManager._create_fallback_logger()
        
        # Should be different FallbackLogger instances
        assert fallback1 is not fallback2
        # Both should have the required logging methods
        assert hasattr(fallback1, "info")
        assert hasattr(fallback2, "info")
        assert hasattr(fallback1, "span")
        assert hasattr(fallback2, "span")

    def test_get_logger_with_none_name(self) -> None:
        """Test get_logger with None name parameter."""
        with patch("mpzsql.logfire_config.logfire") as mock_logfire:
            LogfireManager._initialized = True
            LogfireManager._logfire_instance = mock_logfire
            
            result = LogfireManager.get_logger(None)  # type: ignore[arg-type]  # Testing edge case with None name
            
            # Should still return the logfire instance
            assert result == mock_logfire

    def test_get_logger_with_empty_string_name(self) -> None:
        """Test get_logger with empty string name."""
        with patch("mpzsql.logfire_config.logfire") as mock_logfire:
            LogfireManager._initialized = True
            LogfireManager._logfire_instance = mock_logfire
            
            result = LogfireManager.get_logger("")
            
            # Should still return the logfire instance
            assert result == mock_logfire
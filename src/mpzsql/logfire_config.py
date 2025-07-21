"""
Logfire configuration for MPZSQL server.

This module provides centralized logfire setup and logger instances
to replace the standard Python logging throughout the application.
"""

import os
import logfire
from typing import Optional


class LogfireManager:
    """Centralized logfire configuration and logger management."""
    
    _initialized = False
    _logfire_instance = None
    
    @classmethod
    def initialize(cls, token: Optional[str] = None) -> None:
        """Initialize logfire with the provided token or environment variable."""
        if cls._initialized:
            return
            
        # Get token from parameter or environment variable
        logfire_token = token or os.getenv('LOGFIRE_WRITE_TOKEN')
        
        try:
            if logfire_token:
                # Configure logfire with the token
                logfire.configure(token=logfire_token, inspect_arguments=False)
                cls._logfire_instance = logfire
            else:
                # Configure logfire without token - this might fail if no auth setup
                # Try with token parameter first, fall back to local-only mode
                try:
                    logfire.configure(inspect_arguments=False)
                    cls._logfire_instance = logfire
                except Exception as e:
                    # If logfire auth fails, create a minimal logging interface
                    print(f"Warning: Logfire authentication failed ({e}). Using fallback mode.")
                    cls._logfire_instance = cls._create_fallback_logger()
        except Exception as e:
            print(f"Warning: Logfire configuration failed ({e}). Using fallback mode.")
            cls._logfire_instance = cls._create_fallback_logger()
            
        cls._initialized = True
    
    @classmethod
    def _create_fallback_logger(cls):
        """Create a fallback logger that mimics logfire interface."""
        import logging
        
        class FallbackLogger:
            def __init__(self):
                self.logger = logging.getLogger("logfire_fallback")
                
            def info(self, message: str, **kwargs):
                if kwargs:
                    self.logger.info(f"{message} - {kwargs}")
                else:
                    self.logger.info(message)
                    
            def debug(self, message: str, **kwargs):
                if kwargs:
                    self.logger.debug(f"{message} - {kwargs}")
                else:
                    self.logger.debug(message)
                    
            def warning(self, message: str, **kwargs):
                if kwargs:
                    self.logger.warning(f"{message} - {kwargs}")
                else:
                    self.logger.warning(message)
                    
            def error(self, message: str, **kwargs):
                if kwargs:
                    self.logger.error(f"{message} - {kwargs}")
                else:
                    self.logger.error(message)
                    
            def span(self, name: str, **kwargs):
                # Return a context manager that does nothing
                from contextlib import contextmanager
                
                @contextmanager
                def dummy_span():
                    self.logger.debug(f"Span: {name} - {kwargs}")
                    yield
                    
                return dummy_span()
        
        return FallbackLogger()
    
    @classmethod
    def get_logger(cls, name: str = None):
        """Get a logfire logger instance."""
        if not cls._initialized:
            cls.initialize()
        return cls._logfire_instance
    
    @classmethod
    def span(cls, name: str, **kwargs):
        """Create a logfire span."""
        if not cls._initialized:
            cls.initialize()
        return cls._logfire_instance.span(name, **kwargs)
    
    @classmethod
    def info(cls, message: str, **kwargs):
        """Log an info message."""
        if not cls._initialized:
            cls.initialize()
        cls._logfire_instance.info(message, **kwargs)
    
    @classmethod
    def debug(cls, message: str, **kwargs):
        """Log a debug message."""
        if not cls._initialized:
            cls.initialize()
        cls._logfire_instance.debug(message, **kwargs)
    
    @classmethod
    def warning(cls, message: str, **kwargs):
        """Log a warning message."""
        if not cls._initialized:
            cls.initialize()
        cls._logfire_instance.warning(message, **kwargs)
    
    @classmethod
    def error(cls, message: str, **kwargs):
        """Log an error message."""
        if not cls._initialized:
            cls.initialize()
        cls._logfire_instance.error(message, **kwargs)


# Convenience functions for different logging categories
def get_main_logger():
    """Get logger for main application logic."""
    return LogfireManager.get_logger("mpzsql.main")

def get_duckdb_logger():
    """Get logger for DuckDB operations.""" 
    return LogfireManager.get_logger("mpzsql.duckdb")

def get_protobuf_logger():
    """Get logger for protobuf operations."""
    return LogfireManager.get_logger("mpzsql.protobuf")

def get_actions_logger():
    """Get logger for FlightSQL actions."""
    return LogfireManager.get_logger("mpzsql.actions")

def get_routing_logger():
    """Get logger for server routing."""
    return LogfireManager.get_logger("mpzsql.routing")

def get_auth_logger():
    """Get logger for authentication."""
    return LogfireManager.get_logger("mpzsql.auth")

def get_transaction_logger():
    """Get logger for transactions."""
    return LogfireManager.get_logger("mpzsql.transaction")

def get_sqlite_logger():
    """Get logger for SQLite operations."""
    return LogfireManager.get_logger("mpzsql.sqlite")
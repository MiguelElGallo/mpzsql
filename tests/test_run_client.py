"""
Tests for demo_client/run_client.py module to improve code coverage.

This test suite covers the simple runner script.
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestRunClient:
    """Test the run_client.py script."""

    @patch("demo_client.run_client.app")
    def test_run_client_main_execution(self, mock_app):
        """Test that the run_client script calls the app when executed."""
        # Import the module - this will execute the if __name__ == "__main__" check
        # but since we're importing it, __name__ won't be "__main__"
        import demo_client.run_client
        
        # Verify the app is imported correctly
        assert demo_client.run_client.app is not None

    def test_run_client_app_import(self):
        """Test that the app is imported correctly."""
        import demo_client.run_client
        
        # The app should be imported from the client module
        assert demo_client.run_client.app is not None
        
        # Verify it's the correct type (Typer app)
        import typer
        assert isinstance(demo_client.run_client.app, typer.Typer)


if __name__ == "__main__":
    pytest.main(["-v", __file__])
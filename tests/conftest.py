"""Shared pytest fixtures for lakehouse tests."""

import pytest


@pytest.fixture
def sample_query() -> str:
    """Return a trivial SQL query for smoke tests."""
    return "SELECT 1 AS value"

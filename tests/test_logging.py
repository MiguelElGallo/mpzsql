"""Tests for lakehouse.logging — structured logging setup."""

from __future__ import annotations

import logging

import pytest

from lakehouse.logging import configure_logging


class TestConfigureLogging:
    """Tests for configure_logging()."""

    @pytest.fixture(autouse=True)
    def _reset_root_logger(self):
        """Remove all handlers from the root logger before each test."""
        root = logging.getLogger()
        original_level = root.level
        original_handlers = root.handlers[:]
        root.handlers.clear()
        yield
        root.handlers = original_handlers
        root.level = original_level

    def test_sets_debug_level(self):
        configure_logging("DEBUG")
        assert logging.getLogger().level == logging.DEBUG

    def test_sets_info_level(self):
        configure_logging("INFO")
        assert logging.getLogger().level == logging.INFO

    def test_sets_warning_level(self):
        configure_logging("WARNING")
        assert logging.getLogger().level == logging.WARNING

    def test_default_is_info(self):
        configure_logging()
        assert logging.getLogger().level == logging.INFO

    def test_case_insensitive(self):
        configure_logging("debug")
        assert logging.getLogger().level == logging.DEBUG

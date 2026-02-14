"""Structured logging setup.

Provides a :func:`configure_logging` helper that sets up Python's
:mod:`logging` module with a consistent format for the Lakehouse server.
"""

from __future__ import annotations

import logging
import sys

__all__ = ["configure_logging"]


def configure_logging(level: str = "INFO") -> None:
    """Configure root logger with a consistent format.

    Args:
        level: Logging level (``DEBUG``, ``INFO``, ``WARNING``, etc.).
    """
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        stream=sys.stderr,
        force=True,
    )

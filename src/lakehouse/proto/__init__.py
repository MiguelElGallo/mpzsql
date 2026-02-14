"""Flight SQL protobuf message helpers.

Provides pack/unpack utilities for google.protobuf.Any <-> Flight SQL messages,
and a registry mapping type_url strings to their concrete message classes.
"""

from __future__ import annotations

from typing import overload

from google.protobuf.any_pb2 import Any as AnyPB
from google.protobuf.message import Message

from lakehouse.proto import FlightSql_pb2 as fs

__all__ = [
    "fs",
    "known_type_urls",
    "pack_any",
    "type_url_for",
    "unpack_any",
]

# ---------------------------------------------------------------------------
# Type-URL prefix used by Flight SQL (standard googleapis convention)
# ---------------------------------------------------------------------------
_TYPE_URL_PREFIX = "type.googleapis.com"

# ---------------------------------------------------------------------------
# Registry: type_url -> concrete protobuf Message class
# Built automatically from every message descriptor in FlightSql_pb2.
# ---------------------------------------------------------------------------
_REGISTRY: dict[str, type[Message]] = {}


def _build_registry() -> None:
    """Populate ``_REGISTRY`` from all message types in ``FlightSql_pb2``."""
    for name in dir(fs):
        obj = getattr(fs, name)
        if (
            isinstance(obj, type)
            and issubclass(obj, Message)
            and obj is not Message
            and hasattr(obj, "DESCRIPTOR")
        ):
            type_url = f"{_TYPE_URL_PREFIX}/{obj.DESCRIPTOR.full_name}"
            _REGISTRY[type_url] = obj


_build_registry()

# Cached frozenset built once after registry is populated
_KNOWN_TYPE_URLS: frozenset[str] = frozenset(_REGISTRY)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def pack_any(msg: Message) -> AnyPB:
    """Pack a protobuf *Message* into a ``google.protobuf.Any`` wrapper.

    Args:
        msg: Any concrete protobuf message instance.

    Returns:
        An ``Any`` message with ``type_url`` and ``value`` set.
    """
    any_msg = AnyPB()
    any_msg.Pack(msg)
    return any_msg


@overload
def unpack_any(any_msg: AnyPB | bytes) -> Message: ...


@overload
def unpack_any[M: Message](any_msg: AnyPB | bytes, expected_type: type[M]) -> M: ...


def unpack_any[M: Message](
    any_msg: AnyPB | bytes,
    expected_type: type[M] | None = None,
) -> Message | M:
    """Unpack a ``google.protobuf.Any`` (or raw bytes) into the concrete Flight SQL message.

    Args:
        any_msg: Either an ``Any`` protobuf or raw serialised bytes of an ``Any``.
        expected_type: If provided, the unpacked message is validated against
            this type and the return value is narrowed accordingly.

    Returns:
        The concrete Flight SQL message.

    Raises:
        ValueError: If the ``type_url`` is not a known Flight SQL message type,
            or if the bytes are empty/malformed (no ``type_url`` present).
        TypeError: If *any_msg* is neither ``Any`` nor ``bytes``, or if
            the unpacked message does not match *expected_type*.
    """
    if isinstance(any_msg, bytes):
        if not any_msg:
            err = "Cannot unpack Any: empty bytes (no type_url)"
            raise ValueError(err)
        parsed = AnyPB()
        parsed.ParseFromString(any_msg)
        any_msg = parsed
    elif not isinstance(any_msg, AnyPB):
        err = f"Expected google.protobuf.Any or bytes, got {type(any_msg)}"
        raise TypeError(err)

    type_url: str = any_msg.type_url
    if not type_url:
        err = "Cannot unpack Any: malformed message with empty type_url"
        raise ValueError(err)

    cls = _REGISTRY.get(type_url)
    if cls is None:
        err = f"Unknown Flight SQL type_url: {type_url!r}"
        raise ValueError(err)

    concrete = cls()
    any_msg.Unpack(concrete)

    if expected_type is not None and not isinstance(concrete, expected_type):
        err = f"Expected {expected_type.__name__}, got {type(concrete).__name__}"
        raise TypeError(err)

    return concrete


def type_url_for(msg_or_cls: Message | type[Message]) -> str:
    """Return the canonical ``type_url`` for a message or message class.

    This does **not** validate that the type is a registered Flight SQL message.

    Args:
        msg_or_cls: A protobuf message instance or class.

    Returns:
        The fully-qualified ``type.googleapis.com/...`` URL string.
    """
    descriptor = (
        msg_or_cls.DESCRIPTOR if isinstance(msg_or_cls, type) else type(msg_or_cls).DESCRIPTOR
    )
    return f"{_TYPE_URL_PREFIX}/{descriptor.full_name}"


def known_type_urls() -> frozenset[str]:
    """Return the cached set of all registered Flight SQL type_url strings."""
    return _KNOWN_TYPE_URLS

"""Tests for lakehouse.proto — pack/unpack/type_url helpers."""

import pytest
from google.protobuf.any_pb2 import Any as AnyPB
from google.protobuf.message import Message

from lakehouse.proto import (
    _REGISTRY,
    fs,
    known_type_urls,
    pack_any,
    type_url_for,
    unpack_any,
)

# ---------------------------------------------------------------------------
# pack_any
# ---------------------------------------------------------------------------


class TestPackAny:
    """Tests for the pack_any() function."""

    def test_pack_returns_any_pb(self) -> None:
        """Packing a message should return an Any protobuf."""
        cmd = fs.CommandStatementQuery(query="SELECT 1")
        result = pack_any(cmd)
        assert isinstance(result, AnyPB)

    def test_pack_sets_type_url(self) -> None:
        """The packed Any should contain the correct type_url."""
        cmd = fs.CommandStatementQuery(query="SELECT 1")
        result = pack_any(cmd)
        expected = "type.googleapis.com/arrow.flight.protocol.sql.CommandStatementQuery"
        assert result.type_url == expected

    def test_pack_sets_value(self) -> None:
        """The packed Any should have a non-empty value field."""
        cmd = fs.CommandStatementQuery(query="SELECT 1")
        result = pack_any(cmd)
        assert len(result.value) > 0

    def test_pack_empty_message(self) -> None:
        """Packing a message with no fields set should still work."""
        cmd = fs.CommandGetCatalogs()
        result = pack_any(cmd)
        assert isinstance(result, AnyPB)
        assert "CommandGetCatalogs" in result.type_url


# ---------------------------------------------------------------------------
# unpack_any
# ---------------------------------------------------------------------------


class TestUnpackAny:
    """Tests for the unpack_any() function."""

    def test_roundtrip_from_any(self) -> None:
        """Pack then unpack should recover the original message."""
        original = fs.CommandStatementQuery(query="SELECT 42")
        packed = pack_any(original)
        recovered = unpack_any(packed)
        assert isinstance(recovered, fs.CommandStatementQuery)
        assert recovered.query == "SELECT 42"

    def test_roundtrip_from_bytes(self) -> None:
        """Unpack should accept raw serialised bytes of an Any."""
        original = fs.CommandStatementQuery(query="SELECT 99")
        packed = pack_any(original)
        raw_bytes = packed.SerializeToString()
        recovered = unpack_any(raw_bytes)
        assert isinstance(recovered, fs.CommandStatementQuery)
        assert recovered.query == "SELECT 99"

    def test_roundtrip_prepared_statement(self) -> None:
        """Roundtrip a CommandPreparedStatementQuery message."""
        original = fs.CommandPreparedStatementQuery(prepared_statement_handle=b"\x01\x02\x03")
        packed = pack_any(original)
        recovered = unpack_any(packed)
        assert isinstance(recovered, fs.CommandPreparedStatementQuery)
        assert recovered.prepared_statement_handle == b"\x01\x02\x03"

    def test_expected_type_correct(self) -> None:
        """When expected_type matches, the result should be typed correctly."""
        original = fs.CommandStatementQuery(query="hello")
        packed = pack_any(original)
        recovered = unpack_any(packed, expected_type=fs.CommandStatementQuery)
        assert isinstance(recovered, fs.CommandStatementQuery)
        assert recovered.query == "hello"

    def test_expected_type_mismatch_raises_type_error(self) -> None:
        """When expected_type doesn't match, TypeError should be raised."""
        original = fs.CommandStatementQuery(query="hello")
        packed = pack_any(original)
        with pytest.raises(TypeError, match="Expected CommandGetCatalogs"):
            unpack_any(packed, expected_type=fs.CommandGetCatalogs)

    def test_empty_bytes_raises_value_error(self) -> None:
        """Passing empty bytes should raise ValueError."""
        with pytest.raises(ValueError, match="empty bytes"):
            unpack_any(b"")

    def test_malformed_any_empty_type_url_raises(self) -> None:
        """An Any with no type_url should raise ValueError."""
        empty_any = AnyPB()  # type_url is ""
        with pytest.raises(ValueError, match="empty type_url"):
            unpack_any(empty_any)

    def test_unknown_type_url_raises_value_error(self) -> None:
        """An Any with an unrecognised type_url should raise ValueError."""
        fake_any = AnyPB()
        fake_any.type_url = "type.googleapis.com/some.Unknown"
        fake_any.value = b"\x00"
        with pytest.raises(ValueError, match="Unknown Flight SQL type_url"):
            unpack_any(fake_any)

    def test_wrong_input_type_raises_type_error(self) -> None:
        """Passing a non-Any/non-bytes value should raise TypeError."""
        with pytest.raises(TypeError, match=r"Expected google\.protobuf\.Any"):
            unpack_any(12345)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# type_url_for
# ---------------------------------------------------------------------------


class TestTypeUrlFor:
    """Tests for the type_url_for() function."""

    def test_from_class(self) -> None:
        """type_url_for should work on message classes."""
        url = type_url_for(fs.CommandStatementQuery)
        assert url == ("type.googleapis.com/arrow.flight.protocol.sql.CommandStatementQuery")

    def test_from_instance(self) -> None:
        """type_url_for should work on message instances."""
        cmd = fs.CommandStatementQuery(query="x")
        url = type_url_for(cmd)
        assert url == ("type.googleapis.com/arrow.flight.protocol.sql.CommandStatementQuery")

    def test_class_and_instance_match(self) -> None:
        """Class and instance should produce the same type_url."""
        cmd = fs.CommandGetCatalogs()
        assert type_url_for(cmd) == type_url_for(fs.CommandGetCatalogs)


# ---------------------------------------------------------------------------
# known_type_urls
# ---------------------------------------------------------------------------


class TestKnownTypeUrls:
    """Tests for the known_type_urls() function."""

    def test_returns_frozenset(self) -> None:
        """Should return a frozenset."""
        result = known_type_urls()
        assert isinstance(result, frozenset)

    def test_contains_expected_types(self) -> None:
        """Should contain core Flight SQL message types."""
        urls = known_type_urls()
        assert ("type.googleapis.com/arrow.flight.protocol.sql.CommandStatementQuery") in urls
        assert ("type.googleapis.com/arrow.flight.protocol.sql.CommandGetCatalogs") in urls
        assert ("type.googleapis.com/arrow.flight.protocol.sql.CommandGetTables") in urls

    def test_minimum_count(self) -> None:
        """Registry should contain at least 20 Flight SQL message types."""
        assert len(known_type_urls()) >= 20

    def test_same_object_returned(self) -> None:
        """known_type_urls should return the cached frozenset (same identity)."""
        a = known_type_urls()
        b = known_type_urls()
        assert a is b


# ---------------------------------------------------------------------------
# Registry integration — every registered type round-trips
# ---------------------------------------------------------------------------


class TestRegistryRoundTrip:
    """Verify every registered Flight SQL type can be packed and unpacked."""

    def test_all_registered_types_roundtrip(self) -> None:
        """Pack and unpack a default instance of every registered type."""
        for url in sorted(known_type_urls()):
            cls = _REGISTRY[url]
            instance = cls()
            packed = pack_any(instance)
            recovered = unpack_any(packed)
            assert isinstance(recovered, Message)
            assert type(recovered).__name__ == cls.__name__

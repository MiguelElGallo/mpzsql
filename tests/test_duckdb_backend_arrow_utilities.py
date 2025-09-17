"""Unit tests for DuckDB backend Arrow helper utilities."""

from __future__ import annotations

from decimal import Decimal
from typing import Iterator
from unittest.mock import Mock

import pyarrow as pa
import pytest

from mpzsql.backends.duckdb_backend import DuckDBBackend
from mpzsql.config import ServerConfig


@pytest.fixture
def backend() -> Iterator[DuckDBBackend]:
    """Provide a DuckDB backend instance backed by an in-memory database."""

    config = Mock(spec=ServerConfig)
    config.database = ":memory:"
    config.read_only = False
    config.init_sql = None
    config.print_queries = True

    backend = DuckDBBackend(config)
    try:
        yield backend
    finally:
        backend.close()


def test_convert_large_arrow_types_for_jdbc_compatibility(backend: DuckDBBackend) -> None:
    """Ensure large Arrow logical types are converted to JDBC friendly variants."""

    large_utf8 = pa.array(["alpha", "beta"], type=pa.large_string())
    large_binary = pa.array([b"a", b"b"], type=pa.large_binary())
    large_list = pa.array([[1, 2], [3]], type=pa.large_list(pa.int32()))
    decimal_small = pa.array(
        [Decimal("123.45"), Decimal("678.90")], type=pa.decimal256(20, 2)
    )
    decimal_big = pa.array([Decimal("1"), Decimal("2")], type=pa.decimal256(50, 0))

    table = pa.table(
        {
            "text_col": large_utf8,
            "binary_col": large_binary,
            "list_col": large_list,
            "decimal_small": decimal_small,
            "decimal_big": decimal_big,
        }
    )

    converted = backend._convert_large_utf8_to_utf8(table)

    assert converted.schema.field("text_col").type == pa.string()
    assert converted.schema.field("binary_col").type == pa.binary()
    assert converted.schema.field("list_col").type == pa.list_(pa.int32())
    assert converted.schema.field("decimal_small").type == pa.decimal128(20, 2)
    assert converted.schema.field("decimal_big").type == pa.string()

    assert converted.column("text_col").to_pylist() == ["alpha", "beta"]
    assert converted.column("binary_col").to_pylist() == [b"a", b"b"]
    assert converted.column("list_col").to_pylist() == [[1, 2], [3]]
    assert [str(value) for value in converted.column("decimal_small").to_pylist()] == [
        "123.45",
        "678.90",
    ]
    assert converted.column("decimal_big").to_pylist() == ["1", "2"]


def test_ensure_arrow_table_returns_original_table(backend: DuckDBBackend) -> None:
    """Tables should flow through `_ensure_arrow_table` unchanged."""

    table = pa.table({"value": [1, 2, 3]})

    assert backend._ensure_arrow_table(table) is table


def test_ensure_arrow_table_materializes_record_batch_reader(
    backend: DuckDBBackend,
) -> None:
    """Record batch readers should be materialized into tables."""

    batch = pa.record_batch([pa.array([1, 2])], names=["value"])
    reader = pa.RecordBatchReader.from_batches(batch.schema, [batch])

    materialized = backend._ensure_arrow_table(reader)

    assert isinstance(materialized, pa.Table)
    assert materialized.to_pylist() == [{"value": 1}, {"value": 2}]


def test_ensure_arrow_table_materializes_reader_that_returns_batch(
    backend: DuckDBBackend,
) -> None:
    """Readers that return a single batch should recurse until a table is produced."""

    batch = pa.record_batch([pa.array([42])], names=["answer"])

    class DummyReader:
        def __init__(self, inner_batch: pa.RecordBatch):
            self._batch = inner_batch

        def read_all(self) -> pa.RecordBatch:
            return self._batch

    materialized = backend._ensure_arrow_table(DummyReader(batch))

    assert isinstance(materialized, pa.Table)
    assert materialized.to_pylist() == [{"answer": 42}]


def test_ensure_arrow_table_from_iterable_batches(backend: DuckDBBackend) -> None:
    """Iterables of record batches should be combined into a single table."""

    batches = [
        pa.record_batch([pa.array([1, 2])], names=["value"]),
        pa.record_batch([pa.array([3])], names=["value"]),
    ]

    materialized = backend._ensure_arrow_table(batches)

    assert isinstance(materialized, pa.Table)
    assert materialized.to_pylist() == [
        {"value": 1},
        {"value": 2},
        {"value": 3},
    ]


def test_ensure_arrow_table_iterable_schema_only_placeholder(
    backend: DuckDBBackend,
) -> None:
    """Iterables exposing a schema attribute should return an empty table with that schema."""

    schema = pa.schema([])

    class SchemaIterable:
        def __init__(self, arrow_schema: pa.Schema):
            self.schema = arrow_schema

        def __iter__(self):
            return iter(())

    materialized = backend._ensure_arrow_table(SchemaIterable(schema))

    assert isinstance(materialized, pa.Table)
    assert materialized.schema == schema
    assert materialized.num_rows == 0


def test_ensure_arrow_table_unsupported_type(backend: DuckDBBackend) -> None:
    """Unsupported Arrow payloads should raise a TypeError."""

    with pytest.raises(TypeError):
        backend._ensure_arrow_table(42)

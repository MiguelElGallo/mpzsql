"""SQLite-to-DuckLake import helpers."""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import duckdb

if TYPE_CHECKING:
    from pathlib import Path

    import pyarrow as pa

    from lakehouse.azure_token import PostgresTokenManager
    from lakehouse.config import ServerConfig

logger = logging.getLogger(__name__)

ARGUS_TABLES: tuple[str, ...] = (
    "readings",
    "device_state",
    "room_state",
    "alert_events",
)

SOURCE_ALIAS = "sqlite_source"
SOURCE_ROWID_COLUMN = "_sqlite_rowid"
MARKER_TABLE = "sqlite_import_waterlevel_markers"
DEFAULT_BATCH_SIZE = 50_000


@dataclass(frozen=True, slots=True)
class TableSchema:
    """DuckDB schema information for a source table."""

    columns: tuple[tuple[str, str, bool], ...]

    @property
    def column_names(self) -> tuple[str, ...]:
        """Column names in source order."""
        return tuple(name for name, _, _ in self.columns)


@dataclass(frozen=True, slots=True)
class Watermark:
    """Per-table cursor used for incremental reads."""

    ts_utc: str | None
    rowid: int | None

    @property
    def is_empty(self) -> bool:
        """Whether the watermark is unset."""
        return self.ts_utc is None or self.rowid is None


def quote_identifier(identifier: str) -> str:
    """Quote a SQL identifier."""
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


def quote_literal(value: str) -> str:
    """Quote a SQL string literal."""
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def source_db_fingerprint(source_db_path: Path) -> str:
    """Create a stable source identity fingerprint.

    The live SQLite file grows continuously, so size and mtime are deliberately
    excluded. The fingerprint should change when the file at a path is replaced,
    not every time the current writer appends a row.
    """
    stat = source_db_path.stat()
    payload = f"{source_db_path.resolve()}|{stat.st_dev}|{stat.st_ino}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def connect_target_ducklake(
    config: ServerConfig,
) -> tuple[duckdb.DuckDBPyConnection, PostgresTokenManager]:
    """Create and initialise the DuckLake target connection."""
    from lakehouse.azure_token import PostgresTokenManager
    from lakehouse.ducklake import initialize_ducklake

    target_db = duckdb.connect(database=":memory:")
    token_manager = PostgresTokenManager(target_db, config)
    initial_token = token_manager.get_initial_token()
    storage_token = token_manager.get_initial_storage_token()
    initialize_ducklake(
        target_db,
        config,
        token=initial_token,
        storage_token=storage_token,
    )
    return target_db, token_manager


def attach_source_sqlite(db: duckdb.DuckDBPyConnection, source_db_path: Path) -> None:
    """Attach the live SQLite database read-only."""
    db.execute("INSTALL sqlite")
    db.execute("LOAD sqlite")
    db.execute(
        "ATTACH "
        f"{quote_literal(str(source_db_path))} AS {quote_identifier(SOURCE_ALIAS)} "
        "(TYPE sqlite, READ_ONLY)"
    )


def describe_source_table(
    db: duckdb.DuckDBPyConnection,
    table_name: str,
) -> TableSchema:
    """Return the DuckDB schema for a source SQLite table."""
    rows = db.execute(
        f"DESCRIBE SELECT * FROM {quote_identifier(SOURCE_ALIAS)}.{quote_identifier(table_name)}"
    ).fetchall()

    columns: list[tuple[str, str, bool]] = []
    for name, type_name, nullable, *_ in rows:
        columns.append((str(name), str(type_name), str(nullable).upper() != "NO"))
    return TableSchema(columns=tuple(columns))


def create_target_tables(
    db: duckdb.DuckDBPyConnection,
    schemas: dict[str, TableSchema],
) -> None:
    """Create the destination Argus tables and the watermark table."""
    for table_name, schema in schemas.items():
        column_defs = ", ".join(
            (f"{quote_identifier(name)} {type_name}" + (" NOT NULL" if not nullable else ""))
            for name, type_name, nullable in schema.columns
        )
        db.execute(f"CREATE TABLE IF NOT EXISTS {quote_identifier(table_name)} ({column_defs})")

    db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {quote_identifier(MARKER_TABLE)} (
            run_id VARCHAR,
            source_db_path VARCHAR,
            source_db_fingerprint VARCHAR,
            table_name VARCHAR,
            status VARCHAR,
            from_ts_utc VARCHAR,
            from_rowid BIGINT,
            to_ts_utc VARCHAR,
            to_rowid BIGINT,
            rows_copied BIGINT,
            started_at TIMESTAMP WITH TIME ZONE,
            finished_at TIMESTAMP WITH TIME ZONE,
            error_message VARCHAR
        )
        """
    )


def load_last_completed_watermark(
    db: duckdb.DuckDBPyConnection,
    *,
    source_db_path: Path,
    fingerprint: str,
    table_name: str,
) -> Watermark:
    """Load the latest successful watermark for a table."""
    row = db.execute(
        f"""
        SELECT to_ts_utc, to_rowid
        FROM {quote_identifier(MARKER_TABLE)}
        WHERE source_db_path = ?
          AND source_db_fingerprint = ?
          AND table_name = ?
          AND status = 'completed'
        ORDER BY to_ts_utc DESC, to_rowid DESC, finished_at DESC, started_at DESC
        LIMIT 1
        """,
        [str(source_db_path), fingerprint, table_name],
    ).fetchone()
    if row is None:
        return Watermark(ts_utc=None, rowid=None)
    return Watermark(ts_utc=str(row[0]), rowid=int(row[1]))


def load_source_high_rowid(db: duckdb.DuckDBPyConnection, table_name: str) -> int | None:
    """Return the highest source rowid visible at the start of a table import."""
    row = db.execute(
        f"""
        SELECT MAX(rowid)
        FROM {quote_identifier(SOURCE_ALIAS)}.{quote_identifier(table_name)}
        """
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return int(row[0])


def build_source_batch_query(
    table_name: str,
    watermark: Watermark,
    *,
    high_rowid: int | None = None,
    limit: int | None = None,
) -> str:
    """Build the live source query for the next batch."""
    source_table = f"{quote_identifier(SOURCE_ALIAS)}.{quote_identifier(table_name)}"
    base = f"SELECT rowid AS {quote_identifier(SOURCE_ROWID_COLUMN)}, * FROM {source_table}"
    conditions: list[str] = []

    if high_rowid is not None:
        conditions.append(f"{quote_identifier(SOURCE_ROWID_COLUMN)} <= {high_rowid}")

    if not watermark.is_empty:
        assert watermark.ts_utc is not None
        assert watermark.rowid is not None
        conditions.append(
            f"(ts_utc > {quote_literal(watermark.ts_utc)} "
            f"OR (ts_utc = {quote_literal(watermark.ts_utc)} "
            f"AND {quote_identifier(SOURCE_ROWID_COLUMN)} > {watermark.rowid}))"
        )

    where_clause = ""
    if conditions:
        where_clause = f" WHERE {' AND '.join(conditions)}"

    suffix = ""
    if limit is not None:
        suffix = f" LIMIT {limit}"

    return f"{base}{where_clause} ORDER BY ts_utc, {quote_identifier(SOURCE_ROWID_COLUMN)}{suffix}"


def _view_name(run_id: str, table_name: str, batch_index: int) -> str:
    return f"sqlite_import_{run_id}_{table_name}_{batch_index}"


def _batch_watermark(batch_table: pa.Table) -> tuple[str, int]:
    """Return the highest (ts_utc, rowid) tuple in a batch."""
    ts_values = batch_table["ts_utc"].to_pylist()
    rowid_values = batch_table[SOURCE_ROWID_COLUMN].to_pylist()
    if not ts_values or not rowid_values:
        msg = "Cannot compute a watermark from an empty batch"
        raise ValueError(msg)
    return str(ts_values[-1]), int(rowid_values[-1])


def _insert_success_marker(
    db: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
    source_db_path: Path,
    fingerprint: str,
    table_name: str,
    watermark_start: Watermark,
    watermark_end: tuple[str, int],
    rows_copied: int,
    started_at: datetime,
    finished_at: datetime,
) -> None:
    db.execute(
        f"""
        INSERT INTO {quote_identifier(MARKER_TABLE)} (
            run_id,
            source_db_path,
            source_db_fingerprint,
            table_name,
            status,
            from_ts_utc,
            from_rowid,
            to_ts_utc,
            to_rowid,
            rows_copied,
            started_at,
            finished_at,
            error_message
        ) VALUES (?, ?, ?, ?, 'completed', ?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        [
            run_id,
            str(source_db_path),
            fingerprint,
            table_name,
            watermark_start.ts_utc,
            watermark_start.rowid,
            watermark_end[0],
            watermark_end[1],
            rows_copied,
            started_at,
            finished_at,
        ],
    )


def _insert_failure_marker(
    db: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
    source_db_path: Path,
    fingerprint: str,
    table_name: str,
    watermark_start: Watermark,
    rows_copied: int,
    started_at: datetime,
    finished_at: datetime,
    error_message: str,
) -> None:
    db.execute(
        f"""
        INSERT INTO {quote_identifier(MARKER_TABLE)} (
            run_id,
            source_db_path,
            source_db_fingerprint,
            table_name,
            status,
            from_ts_utc,
            from_rowid,
            to_ts_utc,
            to_rowid,
            rows_copied,
            started_at,
            finished_at,
            error_message
        ) VALUES (?, ?, ?, ?, 'failed', ?, ?, NULL, NULL, ?, ?, ?, ?)
        """,
        [
            run_id,
            str(source_db_path),
            fingerprint,
            table_name,
            watermark_start.ts_utc,
            watermark_start.rowid,
            rows_copied,
            started_at,
            finished_at,
            error_message,
        ],
    )


def import_table(
    db: duckdb.DuckDBPyConnection,
    *,
    source_db_path: Path,
    fingerprint: str,
    table_name: str,
    batch_size: int,
) -> int:
    """Copy one table from SQLite into DuckLake."""
    run_id = uuid.uuid4().hex
    started_at = datetime.now(UTC)
    watermark = load_last_completed_watermark(
        db,
        source_db_path=source_db_path,
        fingerprint=fingerprint,
        table_name=table_name,
    )
    total_rows = 0
    batch_index = 0
    high_rowid = load_source_high_rowid(db, table_name)
    if high_rowid is None:
        logger.info("Imported 0 rows into %s", table_name)
        return 0
    table_schema = describe_source_table(db, table_name)
    data_columns = [quote_identifier(column) for column in table_schema.column_names]

    while True:
        query = build_source_batch_query(
            table_name,
            watermark,
            high_rowid=high_rowid,
            limit=batch_size,
        )
        batch_table = db.execute(query).to_arrow_table()
        if batch_table.num_rows == 0:
            break

        batch_watermark = _batch_watermark(batch_table)
        view_name = _view_name(run_id, table_name, batch_index)
        batch_index += 1
        db.register(view_name, batch_table)

        try:
            db.execute("BEGIN")
            db.execute(
                f"""
                INSERT INTO {quote_identifier(table_name)}
                SELECT {", ".join(data_columns)}
                FROM {quote_identifier(view_name)}
                """
            )
            finished_at = datetime.now(UTC)
            _insert_success_marker(
                db,
                run_id=run_id,
                source_db_path=source_db_path,
                fingerprint=fingerprint,
                table_name=table_name,
                watermark_start=watermark,
                watermark_end=batch_watermark,
                rows_copied=batch_table.num_rows,
                started_at=started_at,
                finished_at=finished_at,
            )
            db.execute("COMMIT")
        except Exception as exc:
            try:
                db.execute("ROLLBACK")
            except Exception:
                logger.exception("Failed to roll back after a batch error")
            finished_at = datetime.now(UTC)
            try:
                _insert_failure_marker(
                    db,
                    run_id=run_id,
                    source_db_path=source_db_path,
                    fingerprint=fingerprint,
                    table_name=table_name,
                    watermark_start=watermark,
                    rows_copied=total_rows,
                    started_at=started_at,
                    finished_at=finished_at,
                    error_message=str(exc),
                )
            except Exception:
                logger.exception("Failed to record a failure marker for %s", table_name)
            raise
        finally:
            unregister = getattr(db, "unregister", None)
            if unregister is not None:
                unregister(view_name)
            else:
                db.execute(f"DROP VIEW IF EXISTS {quote_identifier(view_name)}")

        total_rows += batch_table.num_rows
        watermark = Watermark(ts_utc=batch_watermark[0], rowid=batch_watermark[1])

    logger.info("Imported %s rows into %s", total_rows, table_name)
    return total_rows


def import_sqlite_to_ducklake(
    source_db_path: Path,
    *,
    config: ServerConfig,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, int]:
    """Import the four Argus tables into the target DuckLake catalog."""
    if not config.ducklake_enabled:
        msg = "DuckLake configuration is required for the import CLI"
        raise ValueError(msg)

    db, token_manager = connect_target_ducklake(config)
    try:
        fingerprint = source_db_fingerprint(source_db_path)
        attach_source_sqlite(db, source_db_path)
        attached_fingerprint = source_db_fingerprint(source_db_path)
        if attached_fingerprint != fingerprint:
            msg = "Source SQLite database changed while attaching; retry the import"
            raise RuntimeError(msg)
        schemas = {
            table_name: describe_source_table(db, table_name) for table_name in ARGUS_TABLES
        }
        create_target_tables(db, schemas)

        total_rows: dict[str, int] = {}
        for table_name in ARGUS_TABLES:
            total_rows[table_name] = import_table(
                db,
                source_db_path=source_db_path,
                fingerprint=fingerprint,
                table_name=table_name,
                batch_size=batch_size,
            )
        return total_rows
    finally:
        token_manager.stop()
        try:
            db.close()
        except Exception:
            logger.exception("Failed to close the DuckDB connection")

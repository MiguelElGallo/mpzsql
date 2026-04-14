"""Tests for the SQLite-to-DuckLake import helpers."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import duckdb
from typer.testing import CliRunner

from lakehouse.config import ServerConfig
from lakehouse.sqlite_import import importer as sqlite_importer
from lakehouse.sqlite_import.cli import app
from lakehouse.sqlite_import.importer import (
    MARKER_TABLE,
    SOURCE_ALIAS,
    SOURCE_ROWID_COLUMN,
    TableSchema,
    Watermark,
    attach_source_sqlite,
    build_source_batch_query,
    create_target_tables,
    import_sqlite_to_ducklake,
    import_table,
    load_last_completed_watermark,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


runner = CliRunner()


READINGS_SCHEMA = TableSchema(
    columns=(
        ("ts_utc", "VARCHAR", True),
        ("x_mandt", "VARCHAR", True),
        ("room_id", "VARCHAR", True),
        ("device_id", "VARCHAR", True),
        ("source_host", "VARCHAR", True),
        ("entity_key", "BIGINT", True),
        ("entity_name", "VARCHAR", True),
        ("entity_object_id", "VARCHAR", True),
        ("entity_platform", "VARCHAR", True),
        ("kind", "VARCHAR", True),
        ("value_bool", "BIGINT", True),
        ("value_float", "DOUBLE", True),
        ("value_text", "VARCHAR", True),
        ("unit", "VARCHAR", True),
        ("raw_json", "VARCHAR", True),
    )
)


def _open_source_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE readings (
            ts_utc TEXT,
            x_mandt TEXT,
            room_id TEXT,
            device_id TEXT,
            source_host TEXT,
            entity_key INTEGER,
            entity_name TEXT,
            entity_object_id TEXT,
            entity_platform TEXT,
            kind TEXT,
            value_bool INTEGER,
            value_float REAL,
            value_text TEXT,
            unit TEXT,
            raw_json TEXT
        )
        """
    )
    conn.executemany(
        "INSERT INTO readings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                "2026-01-01T00:00:00Z",
                "7777",
                "firstroom",
                "front",
                "192.168.1.173",
                1,
                "Distance",
                "distance_to_detection_object",
                "sensor",
                "distance",
                None,
                1.2,
                None,
                "m",
                '{"kind":"distance"}',
            ),
            (
                "2026-01-01T00:00:00Z",
                "7777",
                "firstroom",
                "front",
                "192.168.1.173",
                2,
                "Heart rate",
                "real-time_heart_rate",
                "sensor",
                "heart_rate",
                None,
                72.0,
                None,
                "bpm",
                '{"kind":"heart_rate"}',
            ),
            (
                "2026-01-01T00:00:05Z",
                "7777",
                "firstroom",
                "back",
                "192.168.1.174",
                3,
                "Illuminance",
                "seeed_mr60bha2_illuminance",
                "sensor",
                "illuminance",
                None,
                15.0,
                None,
                "lx",
                '{"kind":"illuminance"}',
            ),
        ],
    )
    conn.execute(
        """
        CREATE TABLE device_state (
            ts_utc TEXT,
            x_mandt TEXT,
            room_id TEXT,
            device_id TEXT,
            source_host TEXT,
            health_state TEXT,
            presence_state TEXT,
            presence_conf REAL,
            immobility_state TEXT,
            immobility_conf REAL,
            vitals_state TEXT,
            vitals_conf REAL,
            reasons_json TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO device_state VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "2026-01-01T00:00:00Z",
            "7777",
            "firstroom",
            "front",
            "192.168.1.173",
            "healthy",
            "present",
            0.91,
            "unknown",
            0.0,
            "normal",
            0.8,
            '["distance"]',
        ),
    )
    conn.execute(
        """
        CREATE TABLE room_state (
            ts_utc TEXT,
            x_mandt TEXT,
            room_id TEXT,
            health_state TEXT,
            presence_state TEXT,
            presence_conf REAL,
            immobility_state TEXT,
            immobility_conf REAL,
            vitals_state TEXT,
            vitals_conf REAL,
            contributing_devices_json TEXT,
            reasons_json TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO room_state VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "2026-01-01T00:00:00Z",
            "7777",
            "firstroom",
            "healthy",
            "present",
            0.91,
            "unknown",
            0.0,
            "normal",
            0.8,
            '["front"]',
            '["healthy_device"]',
        ),
    )
    conn.execute(
        """
        CREATE TABLE alert_events (
            alert_id TEXT,
            ts_utc TEXT,
            x_mandt TEXT,
            room_id TEXT,
            alert_type TEXT,
            status TEXT,
            old_state_json TEXT,
            new_state_json TEXT,
            sent_to_cloud INTEGER,
            cloud_ref TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO alert_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "alert-1",
            "2026-01-01T00:00:00Z",
            "7777",
            "firstroom",
            "presence",
            "active",
            None,
            '{"presence":"present"}',
            0,
            None,
        ),
    )
    conn.commit()
    return conn


def _write_source_db(path: Path) -> None:
    conn = _open_source_db(path)
    conn.close()


def test_build_source_batch_query_uses_ts_and_rowid_cursor() -> None:
    query = build_source_batch_query(
        "readings",
        Watermark(ts_utc="2026-01-01T00:00:00Z", rowid=1),
        high_rowid=99,
        limit=25,
    )

    assert f'"{SOURCE_ALIAS}"."readings"' in query
    assert f'rowid AS "{SOURCE_ROWID_COLUMN}"' in query
    assert "ts_utc > '2026-01-01T00:00:00Z'" in query
    assert f'"{SOURCE_ROWID_COLUMN}" > 1' in query
    assert f'"{SOURCE_ROWID_COLUMN}" <= 99' in query
    assert f'ORDER BY ts_utc, "{SOURCE_ROWID_COLUMN}" LIMIT 25' in query


def test_marker_table_creation_and_latest_completed_lookup(tmp_path: Path) -> None:
    db = duckdb.connect(":memory:")
    source = tmp_path / "argus.sqlite3"
    try:
        create_target_tables(db, {"readings": READINGS_SCHEMA})
        db.execute(
            f"""
            INSERT INTO {MARKER_TABLE}
                (run_id, source_db_path, source_db_fingerprint, table_name, status,
                 from_ts_utc, from_rowid, to_ts_utc, to_rowid, rows_copied,
                 started_at, finished_at, error_message)
            VALUES
                ('failed-run', ?, 'fp', 'readings', 'failed',
                 NULL, NULL, '2026-01-01T00:00:00Z', 1, 1,
                 TIMESTAMPTZ '2026-01-01 00:00:00+00',
                 TIMESTAMPTZ '2026-01-01 00:00:01+00', 'boom'),
                ('done-run-1', ?, 'fp', 'readings', 'completed',
                 NULL, NULL, '2026-01-01T00:00:05Z', 3, 2,
                 TIMESTAMPTZ '2026-01-01 00:00:02+00',
                 TIMESTAMPTZ '2026-01-01 00:00:03+00', NULL),
                ('done-run-2', ?, 'fp', 'readings', 'completed',
                 '2026-01-01T00:00:00Z', 2, '2026-01-01T00:00:00Z', 2, 1,
                 TIMESTAMPTZ '2026-01-01 00:00:04+00',
                 TIMESTAMPTZ '2026-01-01 00:00:05+00', NULL)
            """,
            [str(source), str(source), str(source)],
        )

        watermark = load_last_completed_watermark(
            db,
            source_db_path=source,
            fingerprint="fp",
            table_name="readings",
        )

        assert watermark == Watermark(ts_utc="2026-01-01T00:00:05Z", rowid=3)
    finally:
        db.close()


def test_import_table_copies_duplicate_timestamps_once(tmp_path: Path) -> None:
    source = tmp_path / "argus.sqlite3"
    _write_source_db(source)
    db = duckdb.connect(":memory:")
    try:
        attach_source_sqlite(db, source)
        create_target_tables(db, {"readings": READINGS_SCHEMA})

        rows_copied = import_table(
            db,
            source_db_path=source,
            fingerprint="fp",
            table_name="readings",
            batch_size=1,
        )
        second_pass_rows = import_table(
            db,
            source_db_path=source,
            fingerprint="fp",
            table_name="readings",
            batch_size=10,
        )

        readings = db.execute(
            "SELECT ts_utc, device_id, kind, value_float FROM readings ORDER BY ts_utc, rowid"
        ).fetchall()
        markers = db.execute(
            f"""
            SELECT to_ts_utc, to_rowid, rows_copied
            FROM {MARKER_TABLE}
            WHERE status = 'completed'
            ORDER BY to_ts_utc, to_rowid
            """
        ).fetchall()

        assert rows_copied == 3
        assert second_pass_rows == 0
        assert readings == [
            ("2026-01-01T00:00:00Z", "front", "distance", 1.2),
            ("2026-01-01T00:00:00Z", "front", "heart_rate", 72.0),
            ("2026-01-01T00:00:05Z", "back", "illuminance", 15.0),
        ]
        assert markers == [
            ("2026-01-01T00:00:00Z", 1, 1),
            ("2026-01-01T00:00:00Z", 2, 1),
            ("2026-01-01T00:00:05Z", 3, 1),
        ]
    finally:
        db.close()


def test_import_sqlite_to_ducklake_with_local_target_and_wal_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "argus.sqlite3"
    writer = _open_source_db(source)

    class DummyTokenManager:
        def stop(self) -> None:
            return

    def connect_local_target(
        _config: ServerConfig,
    ) -> tuple[duckdb.DuckDBPyConnection, DummyTokenManager]:
        return duckdb.connect(":memory:"), DummyTokenManager()

    monkeypatch.setattr(sqlite_importer, "connect_target_ducklake", connect_local_target)

    config = ServerConfig(
        azure_storage_account="storageacct",
        ducklake_data_path="az://container/",
        pg_host="postgres.example.com",
        pg_database="ducklake",
        pg_user="entra_user",
    )
    try:
        counts = import_sqlite_to_ducklake(source, config=config, batch_size=2)
    finally:
        writer.close()

    assert counts == {
        "readings": 3,
        "device_state": 1,
        "room_state": 1,
        "alert_events": 1,
    }


def test_cli_help_exposes_source_path_and_batch_size() -> None:
    result = runner.invoke(app, ["import-sqlite", "--help"])

    assert result.exit_code == 0
    output = result.output.lower()
    assert "source_db_path" in output
    assert "--batch-size" in output

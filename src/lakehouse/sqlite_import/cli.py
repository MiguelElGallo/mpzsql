"""Typer CLI for SQLite-to-DuckLake imports."""

from __future__ import annotations

import logging
import pathlib
import sys
from typing import Annotated

import typer

from lakehouse.config import ServerConfig
from lakehouse.sqlite_import.importer import import_sqlite_to_ducklake

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="lakehouse-sqlite-import",
    help="Import a live SQLite database into DuckLake.",
    add_completion=False,
)


@app.command()
def import_sqlite(
    source_db_path: Annotated[
        pathlib.Path,
        typer.Argument(
            exists=True,
            readable=True,
            dir_okay=False,
            resolve_path=True,
            help="Path to the source SQLite database file.",
        ),
    ],
    batch_size: Annotated[
        int,
        typer.Option(min=1, help="Rows per Arrow batch when streaming from SQLite."),
    ] = 50_000,
) -> None:
    """Import the live Argus SQLite database into DuckLake."""
    config = ServerConfig()
    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
        stream=sys.stderr,
    )

    logger.info("Starting SQLite-to-DuckLake import")
    logger.info("  Source: %s", source_db_path)
    logger.info("  Batch size: %d", batch_size)
    logger.info("  DuckLake alias: %s", config.ducklake_alias)
    source_path = pathlib.Path(source_db_path)
    total_rows = import_sqlite_to_ducklake(
        source_path,
        config=config,
        batch_size=batch_size,
    )
    logger.info("Import complete: %s", total_rows)


def main() -> None:
    """Console-script entrypoint."""
    app()


if __name__ == "__main__":
    main()

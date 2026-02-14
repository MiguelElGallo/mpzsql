r"""CLI tool to create a table and insert N random records into a Lakehouse server.

Uses PyArrow + ADBC Flight SQL for efficient bulk Arrow-native ingestion.

Usage::

    # Local, no auth
    uv run python tools/load_data.py --rows 50000

    # Local with auth
    uv run python tools/load_data.py --password mysecret --rows 100000

    # Against Azure deployment
    uv run python tools/load_data.py \\
      --endpoint "grpc+tls://ca-lakehouse.xxx.azurecontainerapps.io:443" \\
      --password "$PASSWORD" \\
      --table sales_data \\
      --rows 1000000
"""

from __future__ import annotations

import random
import string
import time
from typing import Annotated

import pyarrow as pa
import typer

app = typer.Typer(help="Load random data into a Lakehouse server via Arrow Flight SQL.")

# ── Random data pools ──────────────────────────────────────────────────────

FIRST_NAMES = [
    "Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Hank",
    "Ivy", "Jack", "Karen", "Leo", "Mona", "Nick", "Olivia", "Paul",
    "Quinn", "Rosa", "Sam", "Tina", "Uma", "Vic", "Wendy", "Xander",
    "Yara", "Zack",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
]

DOMAINS = [
    "example.com", "test.org", "demo.net", "corp.io", "mail.dev",
    "acme.co", "widgets.biz", "data.cloud",
]

CATEGORIES = [
    "Electronics", "Clothing", "Home & Garden", "Sports", "Books",
    "Automotive", "Health", "Toys", "Food & Beverage", "Office Supplies",
]


def _generate_batch(
    start_id: int,
    count: int,
    rng: random.Random,
) -> pa.RecordBatch:
    """Generate a single Arrow RecordBatch with *count* random rows."""
    ids = list(range(start_id, start_id + count))
    names = []
    emails = []
    amounts = []
    quantities = []
    is_actives = []
    created_ats = []
    categories = []

    # Base timestamp: now minus up to 365 days (in microseconds)
    now_us = int(time.time() * 1_000_000)
    year_us = 365 * 24 * 3600 * 1_000_000

    for _ in range(count):
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        suffix = "".join(rng.choices(string.digits, k=4))
        name = f"{first} {last}"
        email = f"{first.lower()}.{last.lower()}{suffix}@{rng.choice(DOMAINS)}"

        names.append(name)
        emails.append(email)
        amounts.append(round(rng.uniform(0.01, 10_000.00), 2))
        quantities.append(rng.randint(1, 500))
        is_actives.append(rng.random() > 0.3)
        created_ats.append(now_us - rng.randint(0, year_us))
        categories.append(rng.choice(CATEGORIES))

    schema = pa.schema([
        ("id", pa.int64()),
        ("name", pa.utf8()),
        ("email", pa.utf8()),
        ("amount", pa.float64()),
        ("quantity", pa.int32()),
        ("is_active", pa.bool_()),
        ("created_at", pa.timestamp("us")),
        ("category", pa.utf8()),
    ])

    return pa.record_batch(
        [ids, names, emails, amounts, quantities, is_actives, created_ats, categories],
        schema=schema,
    )


@app.command()
def load(
    endpoint: Annotated[
        str, typer.Option(help="Lakehouse server URI.")
    ] = "grpc://localhost:31337",
    username: Annotated[
        str, typer.Option(help="Auth username.")
    ] = "lakehouse",
    password: Annotated[
        str | None, typer.Option(help="Auth password (omit for no auth).")
    ] = None,
    table: Annotated[
        str, typer.Option(help="Target table name.")
    ] = "test_data",
    rows: Annotated[
        int, typer.Option(help="Number of random rows to insert.", min=1)
    ] = 1000,
    batch_size: Annotated[
        int, typer.Option(help="Rows per Arrow batch.", min=1)
    ] = 10_000,
    seed: Annotated[
        int | None, typer.Option(help="Random seed for reproducibility.")
    ] = None,
) -> None:
    """Create a table and load it with random data via Arrow Flight SQL."""
    # Lazy import so --help is fast even without adbc installed
    import adbc_driver_flightsql.dbapi as flight_sql
    from adbc_driver_flightsql import DatabaseOptions

    rng = random.Random(seed)

    # ── Connect ────────────────────────────────────────────────────────
    # The ADBC FlightSQL driver's built-in AUTHORIZATION_HEADER option
    # triggers a gRPC Handshake whose token exchange is incompatible with
    # the server's middleware-based auth.  Instead we obtain a Bearer JWT
    # via PyArrow Flight's authenticate_basic_token() and inject it as a
    # per-RPC header so every call carries valid credentials.
    db_kwargs: dict[str, str] = {}
    if password:
        import pyarrow.flight as flight

        typer.echo(f"Authenticating to {endpoint} ...")
        pa_client = flight.connect(endpoint)
        _header, value = pa_client.authenticate_basic_token(username, password)
        bearer_token = value.decode() if isinstance(value, bytes) else value
        db_kwargs[
            f"{DatabaseOptions.RPC_CALL_HEADER_PREFIX.value}authorization"
        ] = bearer_token
        db_kwargs[DatabaseOptions.WITH_COOKIE_MIDDLEWARE.value] = "false"

    typer.echo(f"Connecting to {endpoint} ...")
    conn = flight_sql.connect(endpoint, db_kwargs=db_kwargs)
    cursor = conn.cursor()

    # ── Generate & ingest ──────────────────────────────────────────────
    num_batches = max(1, (rows + batch_size - 1) // batch_size)
    typer.echo(
        f"Creating table '{table}' with {rows:,} random rows "
        f"(batch size: {batch_size:,})..."
    )

    t0 = time.perf_counter()
    rows_inserted = 0

    for i in range(num_batches):
        batch_rows = min(batch_size, rows - rows_inserted)
        batch = _generate_batch(start_id=rows_inserted + 1, count=batch_rows, rng=rng)
        arrow_table = pa.Table.from_batches([batch])

        # First batch creates the table; subsequent batches append.
        mode = "create" if i == 0 else "append"
        cursor.adbc_ingest(table, arrow_table, mode=mode)

        rows_inserted += batch_rows
        typer.echo(f"  Batch {i + 1}/{num_batches}: {batch_rows:,} rows ingested")

    elapsed = time.perf_counter() - t0

    typer.echo(f"\nDone. Inserted {rows_inserted:,} rows into '{table}' in {elapsed:.1f}s")

    # ── Verify ─────────────────────────────────────────────────────────
    # Try the unqualified name first; fall back to catalog-qualified name
    # (DuckLake places ingested tables under its catalog, e.g. "lakehouse").
    verified = False
    for name in (table, f"lakehouse.{table}"):
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {name}")
            (count,) = cursor.fetchone()  # type: ignore[assignment]
            if count == rows_inserted:
                typer.echo(f"Verification: SELECT COUNT(*) = {count:,} ✓")
            else:
                typer.echo(
                    f"Verification FAILED: expected {rows_inserted:,}, got {count:,} ✗",
                    err=True,
                )
                raise typer.Exit(code=1)
            verified = True
            break
        except Exception:
            continue
    if not verified:
        typer.echo(
            f"Verification FAILED: could not query table '{table}'", err=True,
        )
        raise typer.Exit(code=1)

    cursor.close()
    conn.close()


if __name__ == "__main__":
    app()

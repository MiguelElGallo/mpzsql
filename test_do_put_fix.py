#!/usr/bin/env python3
"""
Test script to verify the do_put fix that prevents table overwriting.

This script simulates the scenario where:
1. First batch creates a table with 5M rows
2. Second batch should append 1M rows (not overwrite)
3. Final table should have 6M rows total
"""

import random

import pyarrow as pa

from src.mpzsql.backends.duckdb_backend import DuckDBBackend
from src.mpzsql.config import ServerConfig


def create_test_data(num_rows, start_id=0):
    """Create test Arrow table with specified number of rows."""
    return pa.table(
        {
            "id": pa.array(range(start_id, start_id + num_rows), type=pa.int64()),
            "name": pa.array(
                [f"user_{i}" for i in range(start_id, start_id + num_rows)],
                type=pa.string(),
            ),
            "value": pa.array(
                [random.random() for _ in range(num_rows)], type=pa.float64()
            ),
        }
    )


def test_do_put_fix():
    """Test that multiple batches append instead of overwrite."""
    print("🧪 Testing do_put fix...")

    # Create backend with minimal config
    config = ServerConfig(secret_key="test-key")
    backend = DuckDBBackend(config)

    table_name = "test_multipart_table"

    try:
        # Simulate first batch (5M rows)
        print("📦 Creating first batch (simulated 5M rows with 1000 rows)...")
        first_batch = create_test_data(1000, start_id=0)
        backend.create_table_from_arrow(table_name, first_batch)

        # Check row count after first batch
        count_after_first = backend.get_table_row_count(table_name)
        print(f"✅ After first batch: {count_after_first} rows")

        # Simulate second batch (1M rows)
        print("📦 Creating second batch (simulated 1M rows with 500 rows)...")
        second_batch = create_test_data(500, start_id=1000)
        backend.create_table_from_arrow(table_name, second_batch)

        # Check final row count
        final_count = backend.get_table_row_count(table_name)
        print(f"✅ After second batch: {final_count} rows")

        # Verify the fix worked
        expected_total = 1000 + 500  # 1500 total
        if final_count == expected_total:
            print(
                f"🎉 SUCCESS! Table has {final_count} rows (expected {expected_total})"
            )
            print("🔧 Fix verified: Second batch appended instead of overwriting")
        else:
            print(f"❌ FAILED! Expected {expected_total} rows, got {final_count}")
            if final_count == 500:
                print("💡 This suggests the old bug (overwrite) is still present")

        # Clean up
        backend.execute_sql(f"DROP TABLE IF EXISTS {table_name}")

    finally:
        backend.close()


if __name__ == "__main__":
    test_do_put_fix()

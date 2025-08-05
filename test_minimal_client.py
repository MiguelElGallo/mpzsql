#!/usr/bin/env python3
"""Minimal client test to isolate the connection issue."""

import os
from adbc_driver_flightsql import dbapi as mpzsql, DatabaseOptions

# Get TLS certificate and key paths from environment variables
tls_cert_path = os.getenv("MPZSQL_TLS_CERT_PATH")
tls_key_path = os.getenv("MPZSQL_TLS_KEY_PATH")

# Build db_kwargs with TLS configuration
db_kwargs = {
    "username": os.getenv("MPZSQL_USERNAME", "user"),
    "password": os.getenv("MPZSQL_PASSWORD", "password"),
}

# Skip TLS verification to avoid certificate validation issues
db_kwargs[DatabaseOptions.TLS_SKIP_VERIFY.value] = "true"

print("Attempting to connect...")
try:
    # Just try to connect, don't execute any queries
    conn = mpzsql.connect(uri="grpc+tls://localhost:8080", db_kwargs=db_kwargs)
    print("✓ Connection successful!")
    
    # Try to get connection info
    print("Getting connection info...")
    cursor = conn.cursor()
    print("✓ Cursor created!")
    
    cursor.close()
    conn.close()
    print("✓ Connection closed successfully!")
    
except Exception as e:
    print(f"✗ Connection failed: {e}")
    import traceback
    traceback.print_exc()

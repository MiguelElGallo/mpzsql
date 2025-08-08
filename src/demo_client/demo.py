#!/usr/bin/env python3
"""Example script demonstrating how to use the MPZSQL demo client."""

import sys
from pathlib import Path

# Add the src directory to Python path so we can import our client
sys.path.insert(0, str(Path(__file__).parent.parent))

from demo_client.client import MPZSQLClient


def main():
    """Run a simple demonstration of the client."""
    print("🚀 MPZSQL FlightSQL Client Demo")
    print("=" * 50)

    # Create client with default settings
    client = MPZSQLClient(
        host="127.0.0.1",
        port=8080,
        username=None,  # No auth for demo
        password=None,
        certificate=None,  # No TLS for demo
    )

    # Connect to server
    if not client.connect():
        print("❌ Failed to connect to server")
        return 1

    try:
        print("\n📊 Testing server connection...")
        client.get_server_info()

        print("\n🔍 Running test queries...")

        # Test queries
        test_queries = [
            "SELECT 1 as id, 'Hello' as greeting",
            "SELECT 42 as answer, 'Universe' as question",
            "SELECT CURRENT_TIMESTAMP as now",
        ]

        for i, query in enumerate(test_queries, 1):
            print(f"\n📝 Query {i}: {query}")
            result = client.execute_query(query)
            if result:
                client._display_table(result, f"Result {i}")

        print("\n✅ Demo completed successfully!")

    except KeyboardInterrupt:
        print("\n⏹️ Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        return 1
    finally:
        client.disconnect()

    return 0


if __name__ == "__main__":
    sys.exit(main())

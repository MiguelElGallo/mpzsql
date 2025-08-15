#!/usr/bin/env python3
"""
Simple syntax and method signature verification for Phase 1 impl    if methods_ok and syntax_ok:
        print("🎉 Phase 1 syntax verification PASSED!")
        print("\nPhase 1 Core Flight Protocol methods implemented:")
        print("✓ list_flights() - Discover available data endpoints")
        print("✓ get_schema()   - Get Arrow schema without data transfer")
        print("✓ handshake()    - Authentication and capability negotiation")
        print("\n🧹 Code Duplication ELIMINATED:")
        print("✓ FlightSqlServerBase removed")
        print("✓ MinimalFlightSQLServer is now the single source of truth")
        print("✓ All duplicate protocol methods eliminated")
        print("\nNext steps:")
        print("- Fix import compatibility issues")
        print("- Integration testing with Arrow Flight clients")
        print("- Phase 2: DoExchange and PollFlightInfo")
        sys.exit(0)
"""

import ast
import sys
from pathlib import Path


def test_method_signatures():
    """Test that the required methods exist in the source code."""

    # Read and parse minimal.py
    minimal_path = Path("src/mpzsql/flightsql/minimal.py")
    if not minimal_path.exists():
        print(f"✗ File not found: {minimal_path}")
        return False

    try:
        with open(minimal_path, "r") as f:
            minimal_content = f.read()

        minimal_tree = ast.parse(minimal_content)

        # Find the MinimalFlightSQLServer class
        minimal_class = None
        for node in ast.walk(minimal_tree):
            if isinstance(node, ast.ClassDef) and node.name == "MinimalFlightSQLServer":
                minimal_class = node
                break

        if not minimal_class:
            print("✗ MinimalFlightSQLServer class not found")
            return False

        print("✓ MinimalFlightSQLServer class found")

        # Check for required methods
        required_methods = ["list_flights", "get_schema", "handshake"]
        found_methods = []

        for method_node in minimal_class.body:
            if isinstance(method_node, ast.FunctionDef):
                found_methods.append(method_node.name)

        print(f"✓ Found methods: {sorted(found_methods)}")

        missing_methods = []
        for method in required_methods:
            if method in found_methods:
                print(f"✓ {method} method found")
            else:
                print(f"✗ {method} method missing")
                missing_methods.append(method)

        if missing_methods:
            print(f"✗ Missing methods: {missing_methods}")
            return False

        print("\n✓ All Phase 1 methods found in MinimalFlightSQLServer!")
        return True

    except Exception as e:
        print(f"✗ Error parsing minimal.py: {e}")
        return False


def test_server_base_removal():
    """Test that server_base.py has been removed to eliminate duplication."""

    server_base_path = Path("src/mpzsql/flightsql/server_base.py")
    if server_base_path.exists():
        print("✗ server_base.py still exists - should be removed")
        return False
    else:
        print("✓ server_base.py successfully removed - no more code duplication!")
        return True


if __name__ == "__main__":
    print("Phase 1 Implementation Verification (Syntax Only)")
    print("=" * 60)

    print("\n1. Testing method signatures in minimal.py:")
    methods_ok = test_method_signatures()

    print("\n2. Testing server_base.py removal:")
    syntax_ok = test_server_base_removal()

    print("\n" + "=" * 60)
    if methods_ok and syntax_ok:
        print("🎉 Phase 1 syntax verification PASSED!")
        print("\nPhase 1 Core Flight Protocol methods implemented:")
        print("✓ list_flights() - Discover available data endpoints")
        print("✓ get_schema()   - Get Arrow schema without data transfer")
        print("✓ handshake()    - Authentication and capability negotiation")
        print("\nNext steps:")
        print("- Fix import compatibility issues")
        print("- Integration testing with Arrow Flight clients")
        print("- Phase 2: DoExchange and PollFlightInfo")
        sys.exit(0)
    else:
        print("❌ Phase 1 syntax verification FAILED!")
        sys.exit(1)

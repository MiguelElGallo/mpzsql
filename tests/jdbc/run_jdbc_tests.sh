#!/usr/bin/env bash
# run_jdbc_tests.sh — Build & run JDBC integration tests.
#
# Usage:
#   ./tests/jdbc/run_jdbc_tests.sh [grpc://host:port]
#
# The Flight SQL server must already be running.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FLIGHT_URL="${1:-grpc://127.0.0.1:31337}"

echo "╔════════════════════════════════════════════════════════════╗"
echo "║  JDBC Integration Tests — Arrow Flight SQL JDBC Driver    ║"
echo "╠════════════════════════════════════════════════════════════╣"
echo "║  Server : ${FLIGHT_URL}"
echo "╚════════════════════════════════════════════════════════════╝"

cd "$SCRIPT_DIR"
mvn -q test -Dflight.url="$FLIGHT_URL" 2>&1

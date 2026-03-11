#!/usr/bin/env bash
# run_jdbc_tests.sh — Build & run JDBC integration tests.
#
# Usage:
#   ./tests/jdbc/run_jdbc_tests.sh
#   ./tests/jdbc/run_jdbc_tests.sh [grpc://host:port]
#
# Without an argument, this script starts a temporary local DuckLake-backed
# Flight SQL server using the current DUCKLAKE_* environment variables.
# With an argument, it targets an already-running Flight SQL server.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ $# -gt 0 ]]; then
	FLIGHT_URL="$1"
else
	FLIGHT_URL=""
fi

echo "╔════════════════════════════════════════════════════════════╗"
echo "║  JDBC Integration Tests — Arrow Flight SQL JDBC Driver    ║"
echo "╠════════════════════════════════════════════════════════════╣"
if [[ -n "$FLIGHT_URL" ]]; then
	echo "║  Server : ${FLIGHT_URL}"
else
	echo "║  Server : temporary local DuckLake server"
fi
echo "╚════════════════════════════════════════════════════════════╝"

cd "$SCRIPT_DIR"
if [[ -n "$FLIGHT_URL" ]]; then
	mvn -q test -Dflight.url="$FLIGHT_URL" 2>&1
else
	uv run python "$SCRIPT_DIR/run_local_jdbc_tests.py" 2>&1
fi

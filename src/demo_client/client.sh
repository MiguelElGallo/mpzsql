#!/bin/bash
# Helper script for MPZSQL demo client operations.
# Usage: ./client.sh [command] [options]
#
# Commands:
#   demo     - Run the demo script
#   test     - Test connection to server
#   query    - Execute a single query (requires query as second argument)
#   connect  - Start interactive mode
#   help     - Show this help
#
# Examples:
#   ./client.sh demo
#   ./client.sh test
#   ./client.sh query "SELECT 1 as test"
#   ./client.sh connect
#   ./client.sh connect --user admin --password secret

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Python executable (use virtual environment if available)
if [ -f "$PROJECT_ROOT/.venv/bin/python" ]; then
    PYTHON="$PROJECT_ROOT/.venv/bin/python"
else
    PYTHON="python3"
fi

# Change to project root
cd "$PROJECT_ROOT"

case "${1:-help}" in
    "demo")
        echo "🚀 Running MPZSQL FlightSQL Demo..."
        "$PYTHON" src/demo_client/demo.py
        ;;

    "test")
        echo "🔧 Testing connection to MPZSQL server..."
        "$PYTHON" src/demo_client/client.py test-connection "${@:2}"
        ;;

    "query")
        if [ -z "$2" ]; then
            echo "❌ Error: Query required"
            echo "Usage: $0 query \"SELECT 1 as test\""
            exit 1
        fi
        echo "📝 Executing query: $2"
        "$PYTHON" src/demo_client/client.py query "$2" "${@:3}"
        ;;

    "connect")
        echo "🔗 Starting interactive mode..."
        "$PYTHON" src/demo_client/client.py connect "${@:2}"
        ;;

    "help"|"--help"|"-h")
        echo "MPZSQL FlightSQL Demo Client Helper"
        echo "=================================="
        echo ""
        echo "Usage: $0 [command] [options]"
        echo ""
        echo "Commands:"
        echo "  demo     - Run the demo script"
        echo "  test     - Test connection to server"
        echo "  query    - Execute a single query (requires query as second argument)"
        echo "  connect  - Start interactive mode"
        echo "  help     - Show this help"
        echo ""
        echo "Examples:"
        echo "  $0 demo"
        echo "  $0 test"
        echo "  $0 test --host localhost --port 9090"
        echo "  $0 query \"SELECT 1 as test\""
        echo "  $0 query \"SELECT * FROM my_table\" --user admin --password secret"
        echo "  $0 connect"
        echo "  $0 connect --user admin --password secret"
        echo ""
        echo "Default server: 127.0.0.1:8080"
        ;;

    *)
        echo "❌ Unknown command: $1"
        echo "Run '$0 help' for usage information"
        exit 1
        ;;
esac

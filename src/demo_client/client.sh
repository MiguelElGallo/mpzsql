#!/bin/bash

# MPZSQL Flight Client Launcher Script
# This script sets up the environment and runs the Arrow Flight client with TLS and authentication

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

echo "🚀 MPZSQL Arrow Flight Client"
echo "============================="

# Load environment variables from config
CONFIG_FILE="$PROJECT_ROOT/test_postgresql_config.sh"
if [[ -f "$CONFIG_FILE" ]]; then
    echo "📋 Loading configuration from $CONFIG_FILE..."
    source "$CONFIG_FILE"
    echo "✅ Configuration loaded successfully"
else
    echo "❌ Error: Configuration file not found at $CONFIG_FILE"
    echo "Please ensure test_postgresql_config.sh exists in the project root"
    exit 1
fi

# Activate virtual environment if it exists
VENV_PATH="$PROJECT_ROOT/.venv/bin/activate"
if [[ -f "$VENV_PATH" ]]; then
    echo "� Activating Python virtual environment..."
    source "$VENV_PATH"
    echo "✅ Virtual environment activated"
fi

# Check if client.py exists
CLIENT_PATH="$SCRIPT_DIR/client.py"
if [[ ! -f "$CLIENT_PATH" ]]; then
    echo "❌ Error: client.py not found at $CLIENT_PATH"
    exit 1
fi

# Display configuration
echo ""
echo "🔧 Connection Configuration:"
echo "   Server: 127.0.0.1:8080"
echo "   Username: $MPZSQL_USERNAME"
echo "   TLS Certificate: $MPZSQL_TLS_CERT_PATH"
echo "   TLS Key: $MPZSQL_TLS_KEY_PATH"
echo ""

# Show usage if no arguments provided
if [ $# -eq 0 ]; then
    echo "📚 Usage Examples:"
    echo "   $0 --info                              # Show server information"
    echo "   $0 --list-tables                       # List available tables"
    echo "   $0 --list-databases                    # List available databases"
    echo "   $0 --query \"SHOW TABLES\"               # Execute SQL query"
    echo "   $0 --query \"SELECT * FROM my_table LIMIT 5\"  # Query with limit"
    echo "   $0 --file \"sample_commands.sql\"        # Execute SQL file"
    echo "   $0 --verbose --info                    # Enable verbose logging"
    echo ""
    echo "For more options, run: $0 --help"
    echo ""
fi

# Change to the client directory and run the client
cd "$SCRIPT_DIR"
echo "▶️  Running: python client.py $*"
echo ""
python client.py "$@"

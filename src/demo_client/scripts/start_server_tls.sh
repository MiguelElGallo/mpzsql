#!/bin/bash
# Start MPZSQL server with authentication and TLS for testing
# Usage: ./start_server_tls.sh [options]

set -e

# Default values
HOST="localhost"
PORT="8080"
USERNAME="admin"
PASSWORD="secret"
CERT_DIR="../../../certs"
CERT_FILE="$CERT_DIR/server.crt"
KEY_FILE="$CERT_DIR/server.key"
BACKEND="duckdb"
DATABASE=""

# Function to show usage
show_usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --host HOST          Server hostname (default: $HOST)"
    echo "  --port PORT          Server port (default: $PORT)"
    echo "  --username USER      Authentication username (default: $USERNAME)"
    echo "  --password PASS      Authentication password (default: $PASSWORD)"
    echo "  --cert-file CERT     TLS certificate file (default: $CERT_FILE)"
    echo "  --key-file KEY       TLS private key file (default: $KEY_FILE)"
    echo "  --backend BACKEND    Database backend (default: $BACKEND)"
    echo "  --database DB        Database file path (optional)"
    echo "  --help, -h           Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Start with defaults"
    echo "  $0 --port 9090 --username testuser   # Custom port and username"
    echo "  $0 --backend sqlite --database test.db # Use SQLite backend"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --host)
            HOST="$2"
            shift 2
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --username)
            USERNAME="$2"
            shift 2
            ;;
        --password)
            PASSWORD="$2"
            shift 2
            ;;
        --cert-file)
            CERT_FILE="$2"
            shift 2
            ;;
        --key-file)
            KEY_FILE="$2"
            shift 2
            ;;
        --backend)
            BACKEND="$2"
            shift 2
            ;;
        --database)
            DATABASE="$2"
            shift 2
            ;;
        --help|-h)
            show_usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Check if certificates exist
if [[ ! -f "$CERT_FILE" || ! -f "$KEY_FILE" ]]; then
    echo "❌ TLS certificates not found!"
    echo "   Certificate: $CERT_FILE"
    echo "   Private Key: $KEY_FILE"
    echo ""
    echo "🔧 Generate certificates first by running:"
    echo "   ./generate_cert.sh"
    exit 1
fi

# Build server command
SERVER_CMD="python3 -m mpzsql.cli"
SERVER_CMD="$SERVER_CMD --hostname $HOST"
SERVER_CMD="$SERVER_CMD --port $PORT"
SERVER_CMD="$SERVER_CMD --username $USERNAME"
SERVER_CMD="$SERVER_CMD --password $PASSWORD"
SERVER_CMD="$SERVER_CMD --tls-cert $CERT_FILE"
SERVER_CMD="$SERVER_CMD --tls-key $KEY_FILE"
SERVER_CMD="$SERVER_CMD --backend $BACKEND"

if [[ -n "$DATABASE" ]]; then
    SERVER_CMD="$SERVER_CMD --database $DATABASE"
fi

# Add some useful startup SQL
SERVER_CMD="$SERVER_CMD --init-sql \"CREATE TABLE IF NOT EXISTS test_table (id INTEGER, name VARCHAR); INSERT OR REPLACE INTO test_table VALUES (1, 'Alice'), (2, 'Bob'), (3, 'Charlie');\""

echo "🚀 Starting MPZSQL server with TLS and authentication..."
echo ""
echo "📋 Server Configuration:"
echo "   Host: $HOST"
echo "   Port: $PORT"
echo "   Username: $USERNAME"
echo "   Password: $PASSWORD"
echo "   TLS Certificate: $CERT_FILE"
echo "   TLS Private Key: $KEY_FILE"
echo "   Backend: $BACKEND"
if [[ -n "$DATABASE" ]]; then
    echo "   Database: $DATABASE"
fi
echo ""
echo "🔗 To connect with the demo client:"
echo "   ./client_tls.sh"
echo "   # or manually:"
echo "   python3 ../client.py connect --cert $CERT_FILE --user $USERNAME --password $PASSWORD --host $HOST --port $PORT"
echo ""
echo "🛑 Press Ctrl+C to stop the server"
echo ""
echo "▶️  Executing: $SERVER_CMD"
echo ""

# Start the server
exec $SERVER_CMD

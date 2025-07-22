#!/bin/bash
# MPZSQL demo client with TLS and authentication support
# Usage: ./client_tls.sh [command] [options]

set -e

# Default values
HOST="localhost"
PORT="8080"
USERNAME="admin"
PASSWORD="secret"
CERT_DIR="../../../certs"
CERT_FILE="$CERT_DIR/server.crt"

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT_SCRIPT="$SCRIPT_DIR/../client.py"

# Function to show usage
show_usage() {
    echo "Usage: $0 [command] [options]"
    echo ""
    echo "Commands:"
    echo "  connect              Start interactive mode (default)"
    echo "  test                 Test connection to server"
    echo "  query \"SQL\"          Execute a single query"
    echo "  demo                 Run demo queries"
    echo "  help                 Show this help message"
    echo ""
    echo "Options:"
    echo "  --host HOST          Server hostname (default: $HOST)"
    echo "  --port PORT          Server port (default: $PORT)"
    echo "  --username USER      Authentication username (default: $USERNAME)"
    echo "  --password PASS      Authentication password (default: $PASSWORD)"
    echo "  --cert-file CERT     TLS certificate file (default: $CERT_FILE)"
    echo "  --no-tls             Disable TLS (use plain connection)"
    echo "  --no-auth            Disable authentication"
    echo ""
    echo "Examples:"
    echo "  $0                                           # Interactive mode with defaults"
    echo "  $0 test                                      # Test connection"
    echo "  $0 query \"SELECT * FROM test_table\"          # Execute single query"
    echo "  $0 connect --port 9090                      # Connect to custom port"
    echo "  $0 test --no-tls --no-auth                  # Plain connection without auth"
}

# Default command
COMMAND="connect"
USE_TLS=true
USE_AUTH=true
QUERY=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        connect|test|demo|help)
            COMMAND="$1"
            shift
            ;;
        query)
            COMMAND="query"
            if [[ $# -gt 1 && ! "$2" =~ ^-- ]]; then
                QUERY="$2"
                shift 2
            else
                echo "❌ Error: query command requires a SQL statement"
                echo "Usage: $0 query \"SELECT * FROM table\""
                exit 1
            fi
            ;;
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
        --no-tls)
            USE_TLS=false
            shift
            ;;
        --no-auth)
            USE_AUTH=false
            shift
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

# Handle help command
if [[ "$COMMAND" == "help" ]]; then
    show_usage
    exit 0
fi

# Check if client script exists
if [[ ! -f "$CLIENT_SCRIPT" ]]; then
    echo "❌ Client script not found: $CLIENT_SCRIPT"
    echo "Make sure you're running this from the project root directory."
    exit 1
fi

# Check if certificate exists when using TLS
if [[ "$USE_TLS" == true && ! -f "$CERT_FILE" ]]; then
    echo "❌ TLS certificate not found: $CERT_FILE"
    echo ""
    echo "🔧 Generate certificates first by running:"
    echo "   ./generate_cert.sh"
    echo ""
    echo "Or disable TLS with --no-tls flag"
    exit 1
fi

# Build client command
CLIENT_CMD="python3 $CLIENT_SCRIPT"

# Add command
case $COMMAND in
    connect)
        CLIENT_CMD="$CLIENT_CMD connect"
        ;;
    test)
        CLIENT_CMD="$CLIENT_CMD test-connection"
        ;;
    query)
        CLIENT_CMD="$CLIENT_CMD query \"$QUERY\""
        ;;
    demo)
        echo "🚀 Running demo with TLS and authentication..."
        echo ""
        echo "📋 Connection Configuration:"
        echo "   Host: $HOST"
        echo "   Port: $PORT"
        if [[ "$USE_AUTH" == true ]]; then
            echo "   Username: $USERNAME"
            echo "   Password: $PASSWORD"
        else
            echo "   Authentication: Disabled"
        fi
        if [[ "$USE_TLS" == true ]]; then
            echo "   TLS Certificate: $CERT_FILE"
        else
            echo "   TLS: Disabled"
        fi
        echo ""
        
        # Run multiple demo queries
        DEMO_QUERIES=(
            "SELECT 1 as test, 'Hello World' as message"
            "SELECT CURRENT_TIMESTAMP as server_time"
            "SELECT * FROM test_table"
            "SELECT COUNT(*) as total_rows FROM test_table"
        )
        
        for query in "${DEMO_QUERIES[@]}"; do
            echo "🔍 Executing: $query"
            CMD="python3 $CLIENT_SCRIPT query \"$query\""
            CMD="$CMD --host $HOST --port $PORT"
            
            if [[ "$USE_AUTH" == true ]]; then
                CMD="$CMD --user $USERNAME --password $PASSWORD"
            fi
            
            if [[ "$USE_TLS" == true ]]; then
                CMD="$CMD --cert $CERT_FILE"
            fi
            
            eval $CMD
            echo ""
        done
        exit 0
        ;;
esac

# Add connection parameters
CLIENT_CMD="$CLIENT_CMD --host $HOST --port $PORT"

if [[ "$USE_AUTH" == true ]]; then
    CLIENT_CMD="$CLIENT_CMD --user $USERNAME --password $PASSWORD"
fi

if [[ "$USE_TLS" == true ]]; then
    CLIENT_CMD="$CLIENT_CMD --cert $CERT_FILE"
fi

# Show connection info
echo "🔗 Connecting to MPZSQL server..."
echo ""
echo "📋 Connection Configuration:"
echo "   Host: $HOST"
echo "   Port: $PORT"
if [[ "$USE_AUTH" == true ]]; then
    echo "   Username: $USERNAME"
    echo "   Password: $PASSWORD"
else
    echo "   Authentication: Disabled"
fi
if [[ "$USE_TLS" == true ]]; then
    echo "   TLS Certificate: $CERT_FILE"
else
    echo "   TLS: Disabled"
fi
echo ""
echo "▶️  Executing: $CLIENT_CMD"
echo ""

# Execute the client command
exec $CLIENT_CMD

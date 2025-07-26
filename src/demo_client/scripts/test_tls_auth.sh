#!/bin/bash
# Comprehensive test script for MPZSQL server with TLS and authentication
# This script tests the complete flow: server startup and client connection

set -e

echo "🧪 MPZSQL TLS Authentication Test Suite"
echo "========================================"
echo ""

# Configuration
TEST_HOST="localhost"
TEST_PORT="8081"  # Use different port to avoid conflicts
TEST_USERNAME="testuser"
TEST_PASSWORD="testpass123"
PROJECT_ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
CERT_DIR="$PROJECT_ROOT/certs"
CERT_FILE="$CERT_DIR/letsencrypt-server.crt"
KEY_FILE="$CERT_DIR/letsencrypt-server.key"
# Paths for server command (from project root)
SERVER_CERT_FILE="certs/letsencrypt-server.crt"
SERVER_KEY_FILE="certs/letsencrypt-server.key"
SERVER_PID=""

# Cleanup function
cleanup() {
    echo ""
    echo "🧹 Cleaning up..."
    
    # Kill server if running
    if [[ -n "$SERVER_PID" ]]; then
        echo "   Stopping server (PID: $SERVER_PID)..."
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
    
    echo "✅ Cleanup complete"
}

# Set up cleanup on exit
trap cleanup EXIT

echo "🚀 Step 1: Starting MPZSQL server with TLS and authentication..."
echo "=============================================================="

# Build server command (without --test-mode as it doesn't exist)
SERVER_CMD="uv run mpzsql-server"
SERVER_CMD="$SERVER_CMD --hostname $TEST_HOST"
SERVER_CMD="$SERVER_CMD --port $TEST_PORT"
SERVER_CMD="$SERVER_CMD --username $TEST_USERNAME"
SERVER_CMD="$SERVER_CMD --password $TEST_PASSWORD"
SERVER_CMD="$SERVER_CMD --tls-cert $SERVER_CERT_FILE"
SERVER_CMD="$SERVER_CMD --tls-key $SERVER_KEY_FILE"
SERVER_CMD="$SERVER_CMD --backend duckdb"

echo "📋 Server Configuration:"
echo "   Host: $TEST_HOST"
echo "   Port: $TEST_PORT"
echo "   Username: $TEST_USERNAME"
echo "   Password: $TEST_PASSWORD"
echo "   TLS Certificate: $SERVER_CERT_FILE"
echo ""

# Start server in background
echo "▶️  Starting server..."

# Check if port is already in use
if lsof -i :$TEST_PORT >/dev/null 2>&1; then
    echo "⚠️  Port $TEST_PORT is already in use. Attempting to kill existing processes..."
    lsof -t -i :$TEST_PORT | xargs kill -9 2>/dev/null || true
    sleep 2
fi

# Change to project root for server startup
LOG_PATH="$PROJECT_ROOT/server_test.log"
# Temporarily unset Logfire token to avoid authentication issues during testing
(cd "$PROJECT_ROOT" && unset LOGFIRE_WRITE_TOKEN && $SERVER_CMD > "$LOG_PATH" 2>&1) &
SERVER_PID=$!

echo "✅ Server started (PID: $SERVER_PID)"
echo "   Log file: $LOG_PATH"
echo ""

# Wait for server to start
echo "⏳ Waiting for server to start..."
sleep 5

# Check if server process is still running
if kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "✅ Server is running (PID: $SERVER_PID)"
else
    echo "❌ Server failed to start. Log output:"
    echo "----------------------------------------"
    if [ -f "$LOG_PATH" ]; then
        tail -20 "$LOG_PATH"
    else
        echo "Log file not found at: $LOG_PATH"
    fi
    exit 1
fi
echo ""

echo "🔗 Step 2: Testing client connections..."
echo "======================================="

# Change to client directory
cd "$PROJECT_ROOT/src/demo_client"

# Test 1: Connection test
echo "🧪 Test 1: Basic connection test"
echo "---------------------------------"

CLIENT_CMD="uv run python3 client.py test-connection"
CLIENT_CMD="$CLIENT_CMD --host $TEST_HOST --port $TEST_PORT"
CLIENT_CMD="$CLIENT_CMD --user $TEST_USERNAME --password $TEST_PASSWORD"
CLIENT_CMD="$CLIENT_CMD --cert $CERT_FILE"

if $CLIENT_CMD; then
    echo "✅ Connection test passed"
else
    echo "❌ Connection test failed"
    exit 1
fi
echo ""

# Test 2: Simple query
echo "🧪 Test 2: Simple query execution"
echo "----------------------------------"

QUERY_CMD="uv run python3 client.py query"
QUERY_CMD="$QUERY_CMD --host $TEST_HOST --port $TEST_PORT"
QUERY_CMD="$QUERY_CMD --user $TEST_USERNAME --password $TEST_PASSWORD"
QUERY_CMD="$QUERY_CMD --cert $CERT_FILE"

if $QUERY_CMD "SELECT 1 as test_number, 'Hello TLS' as test_message"; then
    echo "✅ Simple query test passed"
else
    echo "❌ Simple query test failed"
    exit 1
fi
echo ""

# Test 3: Data creation and query
echo "🧪 Test 3: Data creation and query"
echo "-----------------------------------"

# Create test table (DDL operation)
if uv run python3 client.py execute \
    --host "$TEST_HOST" --port "$TEST_PORT" \
    --user "$TEST_USERNAME" --password "$TEST_PASSWORD" \
    --cert "$CERT_FILE" \
    "CREATE OR REPLACE TABLE test_data (id INTEGER, name VARCHAR)"; then
    echo "✅ Table creation successful"
else
    echo "❌ Table creation failed"
    exit 1
fi

# Insert test data (DML operation)
if uv run python3 client.py execute \
    --host "$TEST_HOST" --port "$TEST_PORT" \
    --user "$TEST_USERNAME" --password "$TEST_PASSWORD" \
    --cert "$CERT_FILE" \
    "INSERT INTO test_data VALUES (1, 'test1'), (2, 'test2'), (3, 'test3')"; then
    echo "✅ Data insertion successful"
else
    echo "❌ Data insertion failed"
    exit 1
fi

# Query the data (SELECT operation)
if $QUERY_CMD "SELECT * FROM test_data ORDER BY id"; then
    echo "✅ Data query test passed"
else
    echo "❌ Data query test failed"
    exit 1
fi
echo ""

# Test 4: Authentication failure test
echo "🧪 Test 4: Authentication failure test"
echo "---------------------------------------"

FAIL_CMD="uv run python3 client.py query \"SELECT 1 as auth_test\""
FAIL_CMD="$FAIL_CMD --host $TEST_HOST --port $TEST_PORT"
FAIL_CMD="$FAIL_CMD --user wronguser --password wrongpass"
FAIL_CMD="$FAIL_CMD --cert $CERT_FILE"

# Test should fail because authentication will be rejected during query execution
if $FAIL_CMD 2>/dev/null; then
    echo "❌ Authentication failure test failed (should have been rejected)"
    exit 1
else
    echo "✅ Authentication failure test passed (correctly rejected wrong credentials)"
fi
echo ""

# Test 5: TLS requirement test (if server only accepts TLS)
echo "🧪 Test 5: TLS requirement test"
echo "--------------------------------"

NOTLS_CMD="uv run python3 client.py test-connection"
NOTLS_CMD="$NOTLS_CMD --host $TEST_HOST --port $TEST_PORT"
NOTLS_CMD="$NOTLS_CMD --user $TEST_USERNAME --password $TEST_PASSWORD"
# Note: not providing --cert means plain connection

if $NOTLS_CMD 2>/dev/null; then
    echo "⚠️  TLS requirement test: Server accepts plain connections"
else
    echo "✅ TLS requirement test passed (correctly requires TLS)"
fi
echo ""

echo "🎉 All tests completed successfully!"
echo "===================================="
echo ""
echo "📊 Summary:"
echo "   ✅ Server startup with TLS and authentication"
echo "   ✅ Client connection test"
echo "   ✅ Query execution"
echo "   ✅ Authentication validation"
echo ""
echo "🔧 Manual testing commands:"
echo "   # Test connection:"
echo "   uv run python3 client.py test-connection --cert $CERT_FILE --user $TEST_USERNAME --password $TEST_PASSWORD --host $TEST_HOST --port $TEST_PORT"
echo ""
echo "   # Interactive mode:"
echo "   uv run python3 client.py connect --cert $CERT_FILE --user $TEST_USERNAME --password $TEST_PASSWORD --host $TEST_HOST --port $TEST_PORT"
echo ""
echo "   # Execute query:"
echo "   uv run python3 client.py query \"SELECT * FROM test_data\" --cert $CERT_FILE --user $TEST_USERNAME --password $TEST_PASSWORD --host $TEST_HOST --port $TEST_PORT"

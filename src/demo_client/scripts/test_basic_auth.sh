#!/bin/bash
# Simple test script for MPZSQL server with basic authentication (no TLS)
# This script tests the complete flow: server startup and client connection

set -e

echo "🧪 MPZSQL Basic Authentication Test"
echo "==================================="
echo ""

# Configuration
TEST_HOST="localhost"
TEST_PORT="8082"  # Use different port to avoid conflicts
TEST_USERNAME="testuser"
TEST_PASSWORD="testpass123"
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

echo "🚀 Step 1: Starting MPZSQL server with authentication (no TLS)..."
echo "================================================================"

# Build server command
SERVER_CMD="python3 -m mpzsql.cli"
SERVER_CMD="$SERVER_CMD --hostname $TEST_HOST"
SERVER_CMD="$SERVER_CMD --port $TEST_PORT"
SERVER_CMD="$SERVER_CMD --username $TEST_USERNAME"
SERVER_CMD="$SERVER_CMD --password $TEST_PASSWORD"
SERVER_CMD="$SERVER_CMD --backend duckdb"

echo "📋 Server Configuration:"
echo "   Host: $TEST_HOST"
echo "   Port: $TEST_PORT"
echo "   Username: $TEST_USERNAME"
echo "   Password: $TEST_PASSWORD"
echo "   TLS: Disabled"
echo ""

# Start server in background
echo "▶️  Starting server..."
$SERVER_CMD > server_basic_test.log 2>&1 &
SERVER_PID=$!

echo "✅ Server started (PID: $SERVER_PID)"
echo "   Log file: server_basic_test.log"
echo ""

# Wait for server to start
echo "⏳ Waiting for server to start..."
sleep 3

# Check if server is still running
if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "❌ Server failed to start. Log output:"
    echo "----------------------------------------"
    tail -20 server_basic_test.log
    exit 1
fi

echo "✅ Server is running"
echo ""

echo "🔗 Step 2: Testing client connections (no TLS)..."
echo "================================================="

echo "🧪 Test 1: Basic connection test (no TLS)"
echo "-------------------------------------------"

CLIENT_CMD="python3 ../client.py test-connection"
CLIENT_CMD="$CLIENT_CMD --host $TEST_HOST --port $TEST_PORT"
# Don't add --cert parameter (no TLS)
# Don't add --user/--password (ADBC auth parameters not working yet)

if $CLIENT_CMD; then
    echo "✅ Basic connection test passed"
else
    echo "❌ Basic connection test failed"
    exit 1
fi
echo ""

# Test 2: Simple query
echo "🧪 Test 2: Simple query execution (no TLS)"
echo "--------------------------------------------"

QUERY_CMD="python3 ../client.py query"
QUERY_CMD="$QUERY_CMD --host $TEST_HOST --port $TEST_PORT"
# Don't add --cert parameter (no TLS)
# Don't add --user/--password (ADBC auth parameters not working yet)

if $QUERY_CMD "SELECT 1 as test_number, 'Hello MPZSQL' as test_message"; then
    echo "✅ Simple query test passed"
else
    echo "❌ Simple query test failed"
    exit 1
fi
echo ""

# Test 3: Table creation and data insertion
echo "🧪 Test 3: Table creation and data queries (no TLS)"
echo "-----------------------------------------------------"

# Create table
if $QUERY_CMD "CREATE TABLE IF NOT EXISTS test_data (id INTEGER, name VARCHAR, value REAL)"; then
    echo "✅ Table creation successful"
else
    echo "❌ Table creation failed"
    exit 1
fi

# Insert data
if $QUERY_CMD "INSERT INTO test_data VALUES (1, 'Alice', 3.14), (2, 'Bob', 2.71), (3, 'Charlie', 1.41)"; then
    echo "✅ Data insertion successful"
else
    echo "❌ Data insertion failed"
    exit 1
fi

# Query data
if $QUERY_CMD "SELECT * FROM test_data ORDER BY id"; then
    echo "✅ Data query successful"
else
    echo "❌ Data query failed"
    exit 1
fi

echo ""

echo "🎉 All tests completed successfully!"
echo "===================================="
echo ""
echo "📊 Summary:"
echo "   ✅ Server startup without TLS"
echo "   ✅ Client connection test"
echo "   ✅ Query execution"
echo "   ✅ Table creation and data queries"
echo ""
echo "🔧 Manual testing commands:"
echo "   # Test connection:"
echo "   python3 ../client.py test-connection --host $TEST_HOST --port $TEST_PORT"
echo ""
echo "   # Interactive mode:"
echo "   python3 ../client.py connect --host $TEST_HOST --port $TEST_PORT"
echo ""
echo "   # Single query:"
echo "   python3 ../client.py query \"SELECT * FROM test_data\" --host $TEST_HOST --port $TEST_PORT"
echo ""
echo "🛑 Server will be stopped automatically on exit"

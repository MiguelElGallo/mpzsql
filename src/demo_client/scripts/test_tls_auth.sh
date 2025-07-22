#!/bin/bash
# Comprehensive test script for MPZSQL server with TLS and authentication
# This script tests the complete flow: certificate generation, server startup, and client connection

set -e

echo "🧪 MPZSQL TLS Authentication Test Suite"
echo "========================================"
echo ""

# Configuration
TEST_HOST="localhost"
TEST_PORT="8081"  # Use different port to avoid conflicts
TEST_USERNAME="testuser"
TEST_PASSWORD="testpass123"
CERT_DIR="../../../test_certs"
CERT_FILE="$CERT_DIR/server.crt"
KEY_FILE="$CERT_DIR/server.key"
# Paths for server command (from project root)
SERVER_CERT_FILE="test_certs/server.crt"
SERVER_KEY_FILE="test_certs/server.key"
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
    
    # Remove test certificates
    if [[ -d "$CERT_DIR" ]]; then
        echo "   Removing test certificates..."
        rm -rf "$CERT_DIR"
    fi
    
    echo "✅ Cleanup complete"
}

# Set up cleanup on exit
trap cleanup EXIT

echo "🔧 Step 1: Generating test certificates..."
echo "========================================="

# Create test certificates directory
mkdir -p "$CERT_DIR"

# Create OpenSSL configuration
CONFIG_FILE="$CERT_DIR/openssl.conf"
cat > "$CONFIG_FILE" << EOF
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
req_extensions = v3_req

[dn]
C=US
ST=Test State
L=Test City
O=MPZSQL Test
OU=Test Unit
CN=$TEST_HOST

[v3_req]
basicConstraints = CA:FALSE
keyUsage = nonRepudiation, digitalSignature, keyEncipherment
subjectAltName = @alt_names

[alt_names]
DNS.1 = $TEST_HOST
DNS.2 = localhost
DNS.3 = 127.0.0.1
IP.1 = 127.0.0.1
IP.2 = ::1
EOF

# Generate certificate
openssl req -x509 -newkey rsa:2048 -keyout "$KEY_FILE" -out "$CERT_FILE" \
    -days 1 -nodes -config "$CONFIG_FILE" -extensions v3_req 2>/dev/null

chmod 600 "$KEY_FILE"
chmod 644 "$CERT_FILE"

echo "✅ Test certificates generated"
echo "   Certificate: $CERT_FILE"
echo "   Private Key: $KEY_FILE"
echo ""

echo "🚀 Step 2: Starting MPZSQL server with TLS and authentication..."
echo "=============================================================="

# Build server command
SERVER_CMD="python3 -m mpzsql.cli"
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
echo "   TLS Certificate: $CERT_FILE"
echo ""

# Start server in background
echo "▶️  Starting server..."

# Check if port is already in use
if lsof -i :$TEST_PORT >/dev/null 2>&1; then
    echo "⚠️  Port $TEST_PORT is already in use. Attempting to kill existing processes..."
    lsof -t -i :$TEST_PORT | xargs kill -9 2>/dev/null || true
    sleep 2
fi

# Change to project root and use PYTHONPATH for server startup
LOG_PATH="$(pwd)/server_test.log"
(cd ../../../ && PYTHONPATH=src $SERVER_CMD > "$LOG_PATH" 2>&1) &
SERVER_PID=$!

echo "✅ Server started (PID: $SERVER_PID)"
echo "   Log file: server_test.log"
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
    if [ -f server_test.log ]; then
        tail -20 server_test.log
    else
        echo "Log file not found at: $(pwd)/server_test.log"
    fi
    exit 1
fi
echo ""

echo "🔗 Step 3: Testing client connections..."
echo "======================================="

# Test 1: Connection test
echo "🧪 Test 1: Basic connection test"
echo "---------------------------------"

CLIENT_CMD="python3 ./client.py test-connection"
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

QUERY_CMD="python3 ./client.py query"
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
if python3 ./client.py execute \
    --host "$TEST_HOST" --port "$TEST_PORT" \
    --user "$TEST_USERNAME" --password "$TEST_PASSWORD" \
    --cert "$CERT_FILE" \
    "CREATE TABLE test_data (id INTEGER, name VARCHAR)"; then
    echo "✅ Table creation successful"
else
    echo "❌ Table creation failed"
    exit 1
fi

# Insert test data (DML operation)
if python3 ./client.py execute \
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

FAIL_CMD="python3 ./client.py query \"SELECT 1 as auth_test\""
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

NOTLS_CMD="python3 ./client.py test-connection"
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
echo "   ✅ Certificate generation"
echo "   ✅ Server startup with TLS and authentication"
echo "   ✅ Client connection test"
echo "   ✅ Query execution"
echo "   ✅ Authentication validation"
echo ""
echo "🔧 Manual testing commands:"
echo "   # Test connection:"
echo "   python3 ./client.py test-connection --cert $CERT_FILE --user $TEST_USERNAME --password $TEST_PASSWORD --host $TEST_HOST --port $TEST_PORT"
echo ""
echo "   # Interactive mode:"
echo "   python3 ./client.py connect --cert $CERT_FILE --user $TEST_USERNAME --password $TEST_PASSWORD --host $TEST_HOST --port $TEST_PORT"
echo ""
echo "   # Execute query:"
echo "   python3 ./client.py query \"SELECT * FROM test_data\" --cert $CERT_FILE --user $TEST_USERNAME --password $TEST_PASSWORD --host $TEST_HOST --port $TEST_PORT"

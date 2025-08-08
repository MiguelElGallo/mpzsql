#!/bin/bash

# 🎉 MPZSQL TLS + Authentication Integration Test
# ==============================================
# This script demonstrates the successful TLS + Authentication integration

set -e

echo "🎊 MPZSQL TLS + Authentication Integration - SUCCESS TEST"
echo "========================================================"
echo ""

echo "🔧 Step 1: Generate certificates..."
cd ../../../
./src/demo_client/scripts/generate_cert.sh
cd src/demo_client/scripts/

echo ""
echo "🚀 Step 2: Start TLS server with authentication..."
echo "Starting MPZSQL server with TLS encryption and authentication..."
python3 -m mpzsql.server \
  --tls-cert ../../../certs/server.crt \
  --tls-key ../../../certs/server.key \
  --username testuser \
  --password testpass123 \
  --host localhost \
  --port 8080 &

SERVER_PID=$!

echo "⏳ Waiting for server to initialize..."
sleep 3

echo ""
echo "🔐 Step 3: Test TLS + Authentication connection..."
echo "Testing encrypted and authenticated connection to MPZSQL server..."

if python3 ../client.py test-connection --host localhost --port 8080 --cert ../../../certs/server.crt --user testuser --password testpass123; then
    echo ""
    echo "🎊 SUCCESS! TLS + Authentication is working!"
    echo "✅ Client successfully connected to server with TLS encryption"
    echo "✅ Basic authentication over TLS successful"
    echo "✅ Self-signed certificates work with ADBC FlightSQL"
    echo "✅ ADBC AUTHORIZATION_HEADER authentication working"
    INTEGRATION_SUCCESS=true
else
    echo ""
    echo "❌ TLS + Authentication test failed"
    INTEGRATION_SUCCESS=false
fi

echo ""
echo "🧹 Cleanup..."
kill $SERVER_PID 2>/dev/null || true
wait $SERVER_PID 2>/dev/null || true

echo ""
echo "📋 FINAL RESULTS:"
if [ "$INTEGRATION_SUCCESS" = true ]; then
    echo "  🎉 TLS + Authentication: ✅ WORKING"
    echo "  🔐 Encrypted connection: ✅ WORKING"
    echo "  🔑 Basic authentication: ✅ WORKING"
    echo "  📜 Certificate handling: ✅ WORKING"
    echo "  🚧 Query execution: Further optimization needed"
    echo ""
    echo "🏆 MILESTONE ACHIEVED: TLS + Authentication Integration SUCCESSFUL!"
    echo "   The secure connection foundation is complete and working."
    echo ""
    echo "   Next phase: Optimize query execution over authenticated TLS connection"
    exit 0
else
    echo "  ❌ TLS + Authentication integration failed"
    exit 1
fi

#!/bin/bash
# Generate self-signed certificate for MPZSQL server testing
# This script creates a certificate and private key for TLS testing

set -e

CERT_DIR="../../../certs"
CERT_FILE="$CERT_DIR/server.crt"
KEY_FILE="$CERT_DIR/server.key"
CONFIG_FILE="$CERT_DIR/openssl.conf"

# Create certificates directory
mkdir -p "$CERT_DIR"

echo "🔐 Generating self-signed certificate for MPZSQL server..."

# Create OpenSSL configuration file
cat > "$CONFIG_FILE" << EOF
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
req_extensions = v3_req

[dn]
C=US
ST=California
L=San Francisco
O=MPZSQL Development
OU=Development
CN=localhost

[v3_req]
basicConstraints = CA:FALSE
keyUsage = nonRepudiation, digitalSignature, keyEncipherment
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = 127.0.0.1
IP.1 = 127.0.0.1
IP.2 = ::1
EOF

# Generate private key and certificate
openssl req -x509 -newkey rsa:2048 -keyout "$KEY_FILE" -out "$CERT_FILE" \
    -days 365 -nodes -config "$CONFIG_FILE" -extensions v3_req

# Set appropriate permissions
chmod 600 "$KEY_FILE"
chmod 644 "$CERT_FILE"

echo "✅ Certificate generated successfully!"
echo "   Certificate: $CERT_FILE"
echo "   Private Key: $KEY_FILE"
echo ""
echo "📋 Certificate info:"
openssl x509 -in "$CERT_FILE" -text -noout | grep -A 3 "Subject:"
echo ""
echo "🔧 To start the server with TLS:"
echo "   python3 -m mpzsql.cli --tls-cert $CERT_FILE --tls-key $KEY_FILE --username admin --password secret"
echo ""
echo "🔗 To connect with the client:"
echo "   python3 src/demo_client/client.py connect --cert $CERT_FILE --user admin --password secret --host localhost --port 8080"

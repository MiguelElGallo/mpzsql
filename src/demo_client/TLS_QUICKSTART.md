# TLS and Authentication Quick Start Guide

🎉 **STATUS: COMPLETE SUCCESS!** All TLS + Authentication functionality is working perfectly!

This guide walks you through testing MPZSQL with TLS encryption and user authentication.

## Prerequisites

- OpenSSL installed (for certificate generation)
- MPZSQL server dependencies installed
- Python environment set up

## Quick Start (Automated)

**From the `src/demo_client/` directory**, run the comprehensive test script to automatically test everything:

```bash
# Make sure you're in the src/demo_client/ directory
cd src/demo_client/
./scripts/test_tls_auth.sh
```

This script will:
1. Generate test certificates
2. Start the server with TLS and authentication
3. Run multiple client tests
4. Clean up automatically

## Manual Setup

**All commands below assume you're in the `src/demo_client/` directory:**

```bash
cd src/demo_client/
```

### 1. Generate Certificates

```bash
./scripts/generate_cert.sh
```

This creates:
- `../../certs/server.crt` - TLS certificate (relative to project root)
- `../../certs/server.key` - Private key (relative to project root)

### 2. Start Server with TLS and Authentication

```bash
./scripts/start_server_tls.sh
```

Default configuration:
- Host: localhost
- Port: 8080
- Username: admin
- Password: secret
- TLS enabled with generated certificates

### 3. Connect Client with TLS and Authentication

```bash
./scripts/client_tls.sh
```

Available commands:
- `./scripts/client_tls.sh test` - Test connection
- `./scripts/client_tls.sh demo` - Run demo queries
- `./scripts/client_tls.sh query "SELECT 1"` - Execute single query
- `./scripts/client_tls.sh` - Interactive mode (use only when running manually)

## Manual Commands

**From the project root directory** (for server startup):

### Server Startup

```bash
# From project root directory
cd /path/to/mpzsql/
python3 -m mpzsql.cli \
    --hostname localhost \
    --port 8080 \
    --username admin \
    --password secret \
    --tls-cert certs/server.crt \
    --tls-key certs/server.key \
    --backend duckdb
```

**From the `src/demo_client/` directory** (for client commands):

### Client Connection

```bash
# From src/demo_client/ directory
cd src/demo_client/
# Test connection
python3 client.py test-connection \
    --cert ../../certs/server.crt \
    --user admin \
    --password secret \
    --host localhost \
    --port 8080

# Execute query
python3 client.py query "SELECT 1 as test" \
    --cert ../../certs/server.crt \
    --user admin \
    --password secret

# Interactive mode (for manual use only)
# python3 client.py connect \
#     --cert ../../certs/server.crt \
#     --user admin \
#     --password secret
```

## Configuration Options

### Server Options

| Option | Default | Description |
|--------|---------|-------------|
| `--hostname` | localhost | Server hostname |
| `--port` | 8080 | Server port |
| `--username` | admin | Authentication username |
| `--password` | secret | Authentication password |
| `--tls-cert` | certs/server.crt | TLS certificate file |
| `--tls-key` | certs/server.key | TLS private key file |
| `--backend` | duckdb | Database backend |

### Client Options

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | localhost | Server hostname |
| `--port` | 8080 | Server port |
| `--user` | admin | Authentication username |
| `--password` | secret | Authentication password |
| `--cert` | ../../certs/server.crt | TLS certificate file |

## Troubleshooting

### Certificate Issues

If you get certificate errors:

```bash
# Regenerate certificates (from src/demo_client/ directory)
rm -rf ../../certs/
./scripts/generate_cert.sh
```

### Connection Issues

1. Verify server is running:
   ```bash
   ps aux | grep mpzsql
   ```

2. Check server logs:
   ```bash
   tail -f mpzsql.log
   ```

3. Test without TLS first:
   ```bash
   # From src/demo_client/ directory
   python3 client.py test-connection --host localhost --port 8080
   ```

### Authentication Issues

1. Verify credentials match server configuration
2. Try without authentication:
   ```bash
   # From project root directory
   python3 -m mpzsql.cli --hostname localhost --port 8080
   # From src/demo_client/ directory (test connection only)
   python3 client.py test-connection
   ```

## ✅ Working Query Demo

For a complete demonstration of TLS + Authentication with query execution:

```bash
# Activate virtual environment first
source .venv/bin/activate

# Run the complete query demonstration
python3 demo_tls_query.py
```

This will show:
- ✅ TLS connection establishment
- ✅ Authentication over TLS
- ✅ Multiple SQL queries executed successfully
- ✅ Results displayed in formatted tables

## Troubleshooting

If you encounter issues:

1. **Virtual Environment**: Always activate first
   ```bash
   source .venv/bin/activate
   ```

2. **Module Not Found**: Use PYTHONPATH when starting server
   ```bash
   PYTHONPATH=src python3 -m mpzsql.cli --hostname localhost --port 8080
   ```

## Security Notes

- The generated certificates are self-signed and for testing only
- Use proper CA-signed certificates in production
- Store passwords securely (environment variables, secrets management)
- Consider using mTLS for additional security

## Files Created

- `generate_cert.sh` - Certificate generation script
- `start_server_tls.sh` - Server startup script with TLS
- `client_tls.sh` - Client connection script with TLS
- `test_tls_auth.sh` - Comprehensive test suite
- `certs/` - Certificate directory
  - `server.crt` - TLS certificate
  - `server.key` - Private key
  - `openssl.conf` - OpenSSL configuration

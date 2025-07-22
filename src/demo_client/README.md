# MPZSQL Demo Client

This demo client shows how to connect to the MPZSQL FlightSQL server and perform basic operations using the ADBC FlightSQL driver.

## Features

- Connect to MPZSQL FlightSQL server using ADBC (Apache Arrow Database Connectivity)
- Support for TLS connections with certificates
- Basic authentication with username/password
- Interactive SQL query execution
- Command-line single query execution
- Connection testing
- Beautiful terminal output with Rich

## Quick Start

**Note: Commands below assume you're in the `src/demo_client/` directory:**

```bash
cd src/demo_client/
```

### Run the Demo

The easiest way to test the client is to run the demo script:

```bash
# From src/demo_client/ directory
python demo.py
```

This will connect to a server running on `127.0.0.1:8080` and execute several test queries.

### Basic Usage

Test connection:
```bash
# From src/demo_client/ directory
python client.py test-connection
```

Execute a single query:
```bash
python client.py query "SELECT 1 as test, 'Hello World' as message"
```

Start interactive mode:
```bash
python client.py connect
```

## Command Line Options

All commands support the following options:

- `--host`, `-h`: Server host (default: 127.0.0.1)
- `--port`, `-p`: Server port (default: 8080)
- `--user`, `-u`: Username for authentication (optional)
- `--password`, `-P`: Password for authentication (optional)
- `--cert`, `-c`: Path to TLS certificate file (optional)

## Interactive Commands

When in interactive mode, you can use the following commands:

- `help` or `h`: Show available commands
- `info` or `server`: Get server information
- `catalogs` or `databases`: List available catalogs/databases
- `SELECT ...`: Execute SQL queries
- `SHOW ...`: Execute SHOW commands
- `quit`, `exit`, or `q`: Exit the client

## Examples

### Basic Connection Test

```bash
# Test connection to local server
python src/demo_client/client.py test-connection

# Test connection with custom host/port
python src/demo_client/client.py test-connection --host localhost --port 9090
```

### Query Execution

```bash
# Execute a simple query
python src/demo_client/client.py query "SELECT 1 as id, 'Hello World' as message"

# Execute a query with authentication
python src/demo_client/client.py query "SHOW TABLES" --user admin --password secret
```

### Interactive Session

```bash
# Start interactive session
python src/demo_client/client.py connect

# Example interactive session:
mpzsql> SELECT 1 as test
mpzsql> SHOW DATABASES
mpzsql> help
mpzsql> quit
```

### TLS and Authentication Examples

```bash
# Test connection with TLS and authentication
python src/demo_client/client.py test-connection \
    --cert certs/server.crt \
    --user admin \
    --password secret

# Execute query with TLS
python src/demo_client/client.py query "SELECT * FROM test_table" \
    --cert certs/server.crt \
    --user admin \
    --password secret \
    --host localhost \
    --port 8080

# Interactive session with TLS and authentication
python src/demo_client/client.py connect \
    --cert certs/server.crt \
    --user admin \
    --password secret
```

### Using the Helper Scripts

The project includes helper scripts for easy testing with TLS and authentication:

```bash
# Generate self-signed certificates
./generate_cert.sh

# Start server with TLS and authentication
./start_server_tls.sh

# Connect client with TLS and authentication
./client_tls.sh

# Run comprehensive test suite
./test_tls_auth.sh
```

## Dependencies

The client uses the following main dependencies:

- `pyarrow`: For FlightSQL communication
- `typer`: For CLI interface
- `rich`: For beautiful terminal output

These are already included in the main project dependencies.

## Notes

- The client defaults to connecting to `127.0.0.1:8080` which is the default MPZSQL server configuration
- Authentication is optional - the server may or may not require it depending on configuration
- TLS support is available if you have a certificate file
- All query results are displayed in a formatted table with a limit of 100 rows for readability

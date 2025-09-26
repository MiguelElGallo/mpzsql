# MPZSQL Arrow Flight Client

This is a simple Arrow Flight client that connects to the MPZSQL server using TLS encryption and basic authentication.

## Features

- **TLS Encryption**: Secure connections using certificates from `test_postgresql_config.sh`
- **Basic Authentication**: Username/password authentication with bearer token support
- **Modular Design**: Separate functions for configuration, connection, authentication, and operations
- **Command Line Interface**: Easy-to-use CLI with multiple operation modes
- **Error Handling**: Comprehensive error handling and logging support

## Prerequisites

1. **Server Running**: Make sure the MPZSQL server is running on `127.0.0.1:8080`
2. **Environment Setup**: Environment variables must be set via `test_postgresql_config.sh`
3. **Python Dependencies**: Ensure `pyarrow` is installed in your environment

## Quick Start

### Using the Shell Script (Recommended)

The easiest way to run the client is using the provided shell script:

```bash
# Navigate to the demo client directory
cd src/demo_client

# Basic connection test (loads config and connects)
./client.sh

# List all available flights
./client.sh --list

# Execute a SQL query
./client.sh --query "SHOW TABLES"

# Get information about a specific flight/table
./client.sh --flight-info "my_table"

# Execute a server action
./client.sh --action "GetSqlInfo"

# Enable verbose logging
./client.sh --verbose --query "SELECT 1 as test"
```

### Using Python Directly

You can also run the client directly with Python after setting up the environment:

```bash
# Load environment variables
source ../../test_postgresql_config.sh

# Activate virtual environment (if available)
source ../../.venv/bin/activate

# Run the client
python client.py --help
python client.py --list
python client.py --query "SHOW TABLES"
```

## Environment Variables

The client reads configuration from these environment variables (set by `test_postgresql_config.sh`):

- `MPZSQL_USERNAME`: Username for authentication (default from config: "user")
- `MPZSQL_PASSWORD`: Password for authentication (default from config: "password")
- `MPZSQL_TLS_CERT_PATH`: Path to TLS certificate file
- `MPZSQL_TLS_KEY_PATH`: Path to TLS private key file

## Available Operations

### List Flights
```bash
./client.sh --list
```
Lists all available datasets/tables on the server with schema information.

### Execute SQL Query
```bash
./client.sh --query "SELECT * FROM my_table LIMIT 10"
./client.sh --query "SHOW TABLES" --limit 20
```
Execute SQL queries and display results. Use `--limit` to control how many rows are shown.

### Get Flight Information
```bash
./client.sh --flight-info "table_name"
./client.sh --flight-info "SELECT * FROM table_name"
```
Get metadata about a specific flight/table including schema and endpoint information.

### Execute Server Actions
```bash
./client.sh --action "GetSqlInfo"
./client.sh --action "GetCatalogs"
./client.sh --action "GetDbSchemas" --action-body "catalog_name"
```
Execute custom server actions with optional body parameters.

## Command Line Options

- `--host HOST`: Server hostname (default: 127.0.0.1)
- `--port PORT`: Server port (default: 8080)  
- `--verbose, -v`: Enable verbose logging
- `--list`: List all available flights
- `--query SQL`: Execute SQL query
- `--flight-info PATH`: Get flight information
- `--action TYPE`: Execute server action
- `--action-body BODY`: Body for server action
- `--limit N`: Limit rows in query results (default: 10)

## Examples

### Basic Server Information
```bash
# Test connection and show server info
./client.sh
```

### Database Exploration
```bash
# List all tables
./client.sh --query "SHOW TABLES"

# Show table schema
./client.sh --flight-info "my_table"

# Query data with limit
./client.sh --query "SELECT * FROM orders" --limit 5
```

### Server Capabilities
```bash
# Get SQL info
./client.sh --action "GetSqlInfo"

# Get catalogs
./client.sh --action "GetCatalogs"

# Get schemas  
./client.sh --action "GetDbSchemas"
```

### Debugging
```bash
# Enable verbose logging for troubleshooting
./client.sh --verbose --list
./client.sh --verbose --query "SELECT 1"
```

## Architecture

The client is structured with clear separation of concerns:

1. **Configuration (`read_server_config()`)**: Loads settings from environment variables
2. **TLS Connection (`create_tls_connection()`)**: Establishes encrypted connection using certificates  
3. **Authentication (`authenticate_client()`)**: Performs basic auth and gets bearer token
4. **Client Class (`MPZSQLFlightClient`)**: Main client class with operation methods
5. **CLI Interface (`main()`)**: Command line argument parsing and execution

## Error Handling

The client includes comprehensive error handling for:
- Missing environment variables or certificate files
- TLS connection failures
- Authentication errors
- Query execution errors
- Network timeouts and connection issues

Use `--verbose` flag to get detailed error information and logs.

## Troubleshooting

### Connection Issues
1. Verify the server is running: Check that MPZSQL server is running on 127.0.0.1:8080
2. Check certificates: Ensure certificate paths in config are correct and files exist
3. Verify credentials: Check that username/password in config are correct

### Environment Issues  
1. Load config: Make sure to source `test_postgresql_config.sh` before running
2. Virtual environment: Activate the Python virtual environment if using one
3. Dependencies: Ensure `pyarrow` is installed: `pip install pyarrow`

### Common Error Messages
- "MPZSQL_USERNAME environment variable is required": Source the config file
- "TLS certificate file not found": Check certificate path in config
- "Authentication failed": Verify username/password are correct
- "Connection refused": Ensure server is running on the specified host/port
#!/bin/bash

# Discover the actual schema of tables in Azure DuckLake through MPZSQL server
# This will help us fix the test SQL files to match the real table structures

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT_DIR="${SCRIPT_DIR}/src/demo_client"
DISCOVERY_LOG="${SCRIPT_DIR}/azure_schema_discovery.log"

# Initialize log file
echo "MPZSQL Azure Schema Discovery - $(date)" > "$DISCOVERY_LOG"
echo "=========================================" >> "$DISCOVERY_LOG"
echo "" >> "$DISCOVERY_LOG"

print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
    echo "$message" >> "$DISCOVERY_LOG"
}

# Function to run a discovery query
discover_query() {
    local query=$1
    local description=$2
    
    print_status "$BLUE" "🔍 $description"
    echo "Query: $query" >> "$DISCOVERY_LOG"
    echo "----------------------------------------" >> "$DISCOVERY_LOG"
    
    cd "$CLIENT_DIR"
    if python client.py --query "$query" >> "$DISCOVERY_LOG" 2>&1; then
        print_status "$GREEN" "✅ $description - Success"
    else
        print_status "$RED" "❌ $description - Failed"
    fi
    echo "" >> "$DISCOVERY_LOG"
    echo "" >> "$DISCOVERY_LOG"
}

main() {
    print_status "$YELLOW" "🚀 Discovering Azure DuckLake Schema"
    print_status "$YELLOW" "==================================="
    
    # Source config and activate venv
    source "${SCRIPT_DIR}/test_postgresql_config.sh"
    source "${SCRIPT_DIR}/.venv/bin/activate"
    
    print_status "$BLUE" "📊 Discovering table schemas in Azure DuckLake..."
    
    # Test basic connection
    discover_query "SELECT current_database() as current_db, current_schema() as current_schema;" "Connection Test"
    
    # Show available catalogs/databases
    discover_query "SHOW DATABASES;" "Available Databases"
    
    # Try to find tables in my_ducklake
    discover_query "USE my_ducklake; SHOW TABLES;" "Tables in my_ducklake"
    
    # Discover sales_data schema (the problematic table)
    print_status "$YELLOW" "🔍 Analyzing sales_data table schema..."
    discover_query "DESCRIBE my_ducklake.sales_data;" "sales_data Schema"
    discover_query "SELECT * FROM my_ducklake.sales_data LIMIT 3;" "sales_data Sample Data"
    discover_query "SELECT COUNT(*) as row_count FROM my_ducklake.sales_data;" "sales_data Row Count"
    
    # Try to discover other tables mentioned in tests
    print_status "$YELLOW" "🔍 Checking other test tables..."
    discover_query "DESCRIBE my_ducklake.basic_test;" "basic_test Schema (if exists)"
    discover_query "DESCRIBE my_ducklake.employees;" "employees Schema (if exists)"
    discover_query "DESCRIBE my_ducklake.departments;" "departments Schema (if exists)"
    
    # Check what columns actually exist
    print_status "$YELLOW" "🔍 Column analysis..."
    discover_query "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'sales_data';" "sales_data Columns Detail"
    
    print_status "$GREEN" "🎉 Schema Discovery Complete!"
    print_status "$BLUE" "📄 Full results saved to: $DISCOVERY_LOG"
    print_status "$BLUE" "📄 Use this information to fix the test SQL files"
}

main "$@"
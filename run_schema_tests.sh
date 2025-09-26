#!/bin/bash

# MPZSQL Schema Detection Test Suite
# Tests the fixed schema detection functionality with comprehensive SQL operations

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_SQL_DIR="${SCRIPT_DIR}/test_sql"
CLIENT_DIR="${SCRIPT_DIR}/src/demo_client"
LOG_FILE="${SCRIPT_DIR}/test_results.log"

# Initialize log file
echo "MPZSQL Schema Detection Test Suite - $(date)" > "$LOG_FILE"
echo "=================================================" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# Function to print colored output
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
    echo "$message" >> "$LOG_FILE"
}

# Function to run a SQL file
run_sql_file() {
    local file=$1
    local description=$2
    
    print_status "$BLUE" "Running: $description"
    print_status "$BLUE" "File: $(basename "$file")"
    echo "----------------------------------------" >> "$LOG_FILE"
    echo "Running: $description" >> "$LOG_FILE"
    echo "File: $(basename "$file")" >> "$LOG_FILE"
    echo "Timestamp: $(date)" >> "$LOG_FILE"
    echo "" >> "$LOG_FILE"
    
    # Change to client directory and run the SQL file
    cd "$CLIENT_DIR"
    if python client.py --file "$file" >> "$LOG_FILE" 2>&1; then
        print_status "$GREEN" "✅ SUCCESS: $description completed"
        echo "STATUS: SUCCESS" >> "$LOG_FILE"
    else
        print_status "$RED" "❌ FAILED: $description failed"
        echo "STATUS: FAILED" >> "$LOG_FILE"
        return 1
    fi
    echo "" >> "$LOG_FILE"
    echo "" >> "$LOG_FILE"
}

# Function to run a single query
run_query() {
    local query=$1
    local description=$2
    
    print_status "$BLUE" "Running: $description"
    echo "----------------------------------------" >> "$LOG_FILE"
    echo "Running: $description" >> "$LOG_FILE"
    echo "Query: $query" >> "$LOG_FILE"
    echo "Timestamp: $(date)" >> "$LOG_FILE"
    echo "" >> "$LOG_FILE"
    
    cd "$CLIENT_DIR"
    if python client.py --query "$query" >> "$LOG_FILE" 2>&1; then
        print_status "$GREEN" "✅ SUCCESS: $description completed"
        echo "STATUS: SUCCESS" >> "$LOG_FILE"
    else
        print_status "$RED" "❌ FAILED: $description failed"
        echo "STATUS: FAILED" >> "$LOG_FILE"
        return 1
    fi
    echo "" >> "$LOG_FILE"
    echo "" >> "$LOG_FILE"
}

# Main execution
main() {
    print_status "$YELLOW" "🚀 Starting MPZSQL Schema Detection Test Suite"
    print_status "$YELLOW" "================================================="
    
    # Check prerequisites
    if [ ! -f "${SCRIPT_DIR}/test_postgresql_config.sh" ]; then
        print_status "$RED" "❌ ERROR: test_postgresql_config.sh not found"
        exit 1
    fi
    
    if [ ! -d "$CLIENT_DIR" ]; then
        print_status "$RED" "❌ ERROR: Client directory not found: $CLIENT_DIR"
        exit 1
    fi
    
    if [ ! -d "$TEST_SQL_DIR" ]; then
        print_status "$RED" "❌ ERROR: Test SQL directory not found: $TEST_SQL_DIR"
        exit 1
    fi
    
    # Source the PostgreSQL configuration
    print_status "$BLUE" "Loading PostgreSQL configuration..."
    source "${SCRIPT_DIR}/test_postgresql_config.sh"
    
    # Activate virtual environment
    print_status "$BLUE" "Activating virtual environment..."
    source "${SCRIPT_DIR}/.venv/bin/activate"
    
    # Test connection first
    print_status "$BLUE" "Testing basic connection..."
    run_query "SELECT 'Connection test successful' as status, current_timestamp as test_time;" "Connection Test"
    
    # Run the test files in sequence
    print_status "$YELLOW" "📋 Running DDL and DML Tests"
    print_status "$YELLOW" "=============================="
    
    # Phase 1: Basic DDL
    run_sql_file "$TEST_SQL_DIR/01_basic_ddl.sql" "Basic DDL Operations (CREATE TABLE)"
    
    # Phase 2: Multiple Inserts
    run_sql_file "$TEST_SQL_DIR/02_multiple_inserts.sql" "Multiple INSERT Operations"
    
    # Phase 3: Complex Selects
    print_status "$YELLOW" "🔍 Running SELECT Query Tests"
    print_status "$YELLOW" "============================="
    run_sql_file "$TEST_SQL_DIR/03_complex_selects.sql" "Complex SELECT Queries"
    
    # Phase 4: Advanced Queries
    print_status "$YELLOW" "🧠 Running Advanced Query Tests"
    print_status "$YELLOW" "==============================="
    run_sql_file "$TEST_SQL_DIR/04_advanced_queries.sql" "Advanced Queries (JOINs, Window Functions)"
    
    # Phase 5: Analytics Queries
    print_status "$YELLOW" "📊 Running Analytics Query Tests"
    print_status "$YELLOW" "================================"
    run_sql_file "$TEST_SQL_DIR/05_analytics_queries.sql" "Data Analysis and Reporting"
    
    # Additional spot tests for edge cases
    print_status "$YELLOW" "🎯 Running Edge Case Tests"
    print_status "$YELLOW" "========================="
    
    # Test empty result set
    run_query "SELECT * FROM my_ducklake.basic_test WHERE id = 9999;" "Empty Result Set Test"
    
    # Test NULL handling
    run_query "SELECT NULL as null_col, 'test' as text_col, 42 as num_col;" "NULL Value Handling Test"
    
    # Test various data types
    run_query "SELECT 1 as int_col, 1.5 as float_col, 'text' as str_col, true as bool_col, current_date as date_col, current_timestamp as ts_col;" "Data Type Variety Test"
    
    # Test large result set (if data exists)
    run_query "SELECT COUNT(*) as total_records FROM my_ducklake.sales_data;" "Record Count Test"
    
    print_status "$GREEN" "🎉 Test Suite Completed Successfully!"
    print_status "$GREEN" "====================================="
    print_status "$BLUE" "📄 Full results logged to: $LOG_FILE"
    print_status "$BLUE" "📄 Review the log file for detailed output and any potential issues"
}

# Run the main function
main "$@"
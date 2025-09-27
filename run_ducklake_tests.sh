#!/bin/bash

# MPZSQL Ducklake Test Suite
# Tests DuckLake file listing and merge operations

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
LOG_FILE="${SCRIPT_DIR}/ducklake_test_results.log"

# Initialize log file
echo "MPZSQL Ducklake Test Suite - $(date)" > "$LOG_FILE"
echo "=============================================" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# Function to print colored output
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
    echo "$message" >> "$LOG_FILE"
}

# Function to run a SQL file with proper error detection
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
    
    # Capture both stdout and stderr, and the exit code
    if python client.py --file "$file" >> "$LOG_FILE" 2>&1; then
        exit_code=$?
        
        # Also check if the log contains error messages
        if tail -50 "$LOG_FILE" | grep -q "Error\|Failed\|Exception"; then
            print_status "$RED" "❌ FAILED: $description (errors found in output)"
            echo "STATUS: FAILED - Errors in output" >> "$LOG_FILE"
            return 1
        else
            print_status "$GREEN" "✅ SUCCESS: $description completed"
            echo "STATUS: SUCCESS" >> "$LOG_FILE"
        fi
    else
        exit_code=$?
        print_status "$RED" "❌ FAILED: $description (exit code: $exit_code)"
        echo "STATUS: FAILED - Exit code: $exit_code" >> "$LOG_FILE"
        return 1
    fi
    echo "" >> "$LOG_FILE"
    echo "" >> "$LOG_FILE"
}

# Function to run a single query with error detection
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
    
    # Capture output and check for errors
    if python client.py --query "$query" >> "$LOG_FILE" 2>&1; then
        # Check if output contains error messages
        if tail -20 "$LOG_FILE" | grep -q "Error\|Failed\|Exception"; then
            print_status "$RED" "❌ FAILED: $description (errors found in output)"
            echo "STATUS: FAILED - Errors in output" >> "$LOG_FILE"
            return 1
        else
            print_status "$GREEN" "✅ SUCCESS: $description completed"
            echo "STATUS: SUCCESS" >> "$LOG_FILE"
        fi
    else
        exit_code=$?
        print_status "$RED" "❌ FAILED: $description (exit code: $exit_code)"
        echo "STATUS: FAILED - Exit code: $exit_code" >> "$LOG_FILE"
        return 1
    fi
    echo "" >> "$LOG_FILE"
    echo "" >> "$LOG_FILE"
}

# Main execution
main() {
    print_status "$YELLOW" "🚀 Starting MPZSQL Ducklake Test Suite"
    print_status "$YELLOW" "======================================="
    
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
    run_query "SELECT 'Ducklake test suite started' as status, current_timestamp as test_time;" "Connection Test"
    
    # Test ducklake file listing operations
    print_status "$YELLOW" "📂 Testing Ducklake File Operations"
    print_status "$YELLOW" "==================================="
    
    # Run ducklake list files SQL
    if [ -f "$TEST_SQL_DIR/01_lakefiles.sql" ]; then
        run_sql_file "$TEST_SQL_DIR/01_lakefiles.sql" "Ducklake List Files Operations"
    else
        print_status "$YELLOW" "⚠️  Lake files test file not found, running individual queries"
        
        # List files for basic_test table
        run_query "SELECT * FROM ducklake_list_files('my_ducklake', 'basic_test', schema => 'main');" "List Files for basic_test"
        
        # List files for sales_data table
        run_query "SELECT * FROM ducklake_list_files('my_ducklake', 'sales_data', schema => 'main');" "List Files for sales_data"
    fi
    
    # Test ducklake merge operations
    print_status "$YELLOW" "🔄 Testing Ducklake Merge Operations"
    print_status "$YELLOW" "===================================="
    
    # Run ducklake merge files SQL
    if [ -f "$TEST_SQL_DIR/02_lakemergfiles.sql" ]; then
        run_sql_file "$TEST_SQL_DIR/02_lakemergfiles.sql" "Ducklake Merge Files Operations"
    else
        print_status "$YELLOW" "⚠️  Lake merge files test file not found, running individual queries"
        
        # Merge files for basic_test table
        run_query "CALL ducklake_merge_adjacent_files('my_ducklake', 'basic_test', schema => 'main');" "Merge Files for basic_test"
        
        # Merge files for sales_data table
        run_query "CALL ducklake_merge_adjacent_files('my_ducklake', 'sales_data', schema => 'main');" "Merge Files for sales_data"
    fi
    
    # Additional ducklake verification tests
    print_status "$YELLOW" "🎯 Running Ducklake Verification Tests"
    print_status "$YELLOW" "======================================"
    
    # Test catalog information
    run_query "SHOW TABLES FROM my_ducklake;" "Show Ducklake Tables"
    
    # Test schema information
    run_query "DESCRIBE my_ducklake.basic_test;" "Describe basic_test Schema"
    run_query "DESCRIBE my_ducklake.sales_data;" "Describe sales_data Schema"
    
    # Test file count validation after operations
    run_query "SELECT COUNT(*) as file_count FROM ducklake_list_files('my_ducklake', 'basic_test', schema => 'main');" "Verify basic_test File Count"
    run_query "SELECT COUNT(*) as file_count FROM ducklake_list_files('my_ducklake', 'sales_data', schema => 'main');" "Verify sales_data File Count"
    
    # Summary
    print_status "$GREEN" "🎉 Ducklake Test Suite Completed!"
    print_status "$GREEN" "================================="
    print_status "$BLUE" "📄 Full results logged to: $LOG_FILE"
    print_status "$BLUE" "📄 This test suite tests DuckLake file operations"
    print_status "$BLUE" "📄 Review the log file for detailed output and any remaining issues"
    
    # Count successes and failures
    success_count=$(grep -c "STATUS: SUCCESS" "$LOG_FILE" || echo "0")
    failure_count=$(grep -c "STATUS: FAILED" "$LOG_FILE" || echo "0")
    
    print_status "$BLUE" "📊 Test Results Summary:"
    print_status "$GREEN" "   ✅ Successful tests: $success_count"
    if [ $failure_count -gt 0 ]; then
        print_status "$RED" "   ❌ Failed tests: $failure_count"
    else
        print_status "$GREEN" "   ❌ Failed tests: $failure_count"
    fi
}

# Run the main function
main "$@"
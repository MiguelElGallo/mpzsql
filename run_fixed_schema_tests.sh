#!/bin/bash

# MPZSQL Fixed Schema Test Suite
# Tests schema detection with ACTUAL Azure table schemas (no DDL, only working SELECT queries)

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
LOG_FILE="${SCRIPT_DIR}/fixed_test_results.log"

# Initialize log file
echo "MPZSQL Fixed Schema Test Suite - $(date)" > "$LOG_FILE"
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
    print_status "$YELLOW" "🚀 Starting MPZSQL Fixed Schema Test Suite"
    print_status "$YELLOW" "============================================="
    
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
    run_query "SELECT 'Fixed test suite started' as status, current_timestamp as test_time;" "Connection Test"
    
    # Test actual table existence and basic queries
    print_status "$YELLOW" "📊 Testing Actual Azure Tables"
    print_status "$YELLOW" "=============================="
    
    # Test basic_test table (actual columns: id, data)
    run_query "SELECT COUNT(*) as basic_test_rows FROM my_ducklake.basic_test;" "basic_test Row Count"
    run_query "SELECT * FROM my_ducklake.basic_test LIMIT 3;" "basic_test Sample Data"
    
    # Test sales_data table (actual columns: product, price, quantity, sale_date)
    run_query "SELECT COUNT(*) as sales_data_rows FROM my_ducklake.sales_data;" "sales_data Row Count"
    run_query "SELECT * FROM my_ducklake.sales_data LIMIT 3;" "sales_data Sample Data"
    
    # Run fixed SQL files that match actual schemas
    print_status "$YELLOW" "🔍 Running Fixed SELECT Query Tests"
    print_status "$YELLOW" "==================================="
    
    if [ -f "$TEST_SQL_DIR/03_fixed_complex_selects.sql" ]; then
        run_sql_file "$TEST_SQL_DIR/03_fixed_complex_selects.sql" "Fixed Complex SELECT Queries"
    else
        print_status "$YELLOW" "⚠️  Fixed complex selects file not found, running individual queries"
        
        # Simple aggregation that should work
        run_query "SELECT COUNT(*) as total_products, AVG(price) as avg_price, SUM(quantity) as total_qty FROM my_ducklake.sales_data;" "Basic Aggregation Test"
        
        # Grouping by actual columns
        run_query "SELECT product, COUNT(*) as count, SUM(quantity) as total_qty FROM my_ducklake.sales_data GROUP BY product;" "Product Grouping Test"
    fi
    
    # Analytics tests with actual schema
    print_status "$YELLOW" "📊 Running Fixed Analytics Tests"
    print_status "$YELLOW" "==============================="
    
    if [ -f "$TEST_SQL_DIR/05_fixed_analytics_queries.sql" ]; then
        run_sql_file "$TEST_SQL_DIR/05_fixed_analytics_queries.sql" "Fixed Analytics Queries"
    else
        print_status "$YELLOW" "⚠️  Fixed analytics file not found, running individual queries"
        
        # Revenue analysis
        run_query "SELECT SUM(price * quantity) as total_revenue FROM my_ducklake.sales_data;" "Total Revenue Test"
        
        # Date-based analysis
        run_query "SELECT sale_date, COUNT(*) as daily_count FROM my_ducklake.sales_data GROUP BY sale_date;" "Daily Sales Test"
    fi
    
    # Final verification tests
    print_status "$YELLOW" "🎯 Running Verification Tests"
    print_status "$YELLOW" "============================"
    
    # Test data types and null handling
    run_query "SELECT typeof(product) as product_type, typeof(price) as price_type, typeof(quantity) as qty_type FROM my_ducklake.sales_data LIMIT 1;" "Data Type Verification"
    
    # Test basic mathematical operations
    run_query "SELECT product, price, quantity, (price * quantity) as calculated_total FROM my_ducklake.sales_data WHERE quantity > 0;" "Mathematical Operations Test"
    
    # Test sorting and filtering
    run_query "SELECT * FROM my_ducklake.sales_data WHERE price > 50 ORDER BY price DESC LIMIT 5;" "Sorting and Filtering Test"
    
    # Summary
    print_status "$GREEN" "🎉 Fixed Test Suite Completed!"
    print_status "$GREEN" "=============================="
    print_status "$BLUE" "📄 Full results logged to: $LOG_FILE"
    print_status "$BLUE" "📄 This test suite uses actual Azure table schemas"
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
#!/bin/bash

# MPZSQL Small Batch Insert Test Suite
# Performs batch inserts of 100 rows, 1000 times for all tables

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
LOG_FILE="${SCRIPT_DIR}/insertsmall_test_results.log"

# Batch configuration
BATCH_SIZE=100
TOTAL_BATCHES=1000
TOTAL_ROWS=$((BATCH_SIZE * TOTAL_BATCHES))

# Initialize log file
echo "MPZSQL Small Batch Insert Test Suite - $(date)" > "$LOG_FILE"
echo "=============================================" >> "$LOG_FILE"
echo "Configuration:" >> "$LOG_FILE"
echo "  Batch Size: $BATCH_SIZE rows per batch" >> "$LOG_FILE"
echo "  Total Batches: $TOTAL_BATCHES batches" >> "$LOG_FILE"
echo "  Total Rows per Table: $TOTAL_ROWS rows" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# Function to print colored output
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
    echo "$message" >> "$LOG_FILE"
}

# Function to run a single query with error detection
run_query() {
    local query=$1
    local description=$2
    
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

# Function to generate basic_test batch insert
generate_basic_test_batch() {
    local start_id=$1
    local batch_num=$2
    
    local query="INSERT INTO my_ducklake.basic_test (id, data) VALUES"
    
    for ((i=0; i<BATCH_SIZE; i++)); do
        local id=$((start_id + i))
        local data="batch_${batch_num}_row_${i}_data_$(date +%s)"
        
        if [ $i -eq 0 ]; then
            query="${query} ($id, '$data')"
        else
            query="${query}, ($id, '$data')"
        fi
    done
    
    echo "$query;"
}

# Function to generate sales_data batch insert
generate_sales_data_batch() {
    local start_offset=$1
    local batch_num=$2
    
    local query="INSERT INTO my_ducklake.sales_data (product, price, quantity, sale_date) VALUES"
    
    # Products array
    products=("Product_A" "Product_B" "Product_C" "Product_D" "Product_E" "Widget_X" "Widget_Y" "Gadget_Z")
    
    for ((i=0; i<BATCH_SIZE; i++)); do
        local product_idx=$((i % ${#products[@]}))
        local product="${products[$product_idx]}_batch${batch_num}"
        local price=$(awk "BEGIN {printf \"%.2f\", 10.0 + ($i * 0.5) + ($batch_num * 0.1)}")
        local quantity=$((1 + (i % 20) + (batch_num % 10)))
        local days_offset=$(((start_offset + i) % 365))
        local sale_date=$(date -j -v-${days_offset}d +%Y-%m-%d)
        
        if [ $i -eq 0 ]; then
            query="${query} ('$product', $price, $quantity, '$sale_date')"
        else
            query="${query}, ('$product', $price, $quantity, '$sale_date')"
        fi
    done
    
    echo "$query;"
}

# Function to perform batch inserts for a table
perform_batch_inserts() {
    local table_name=$1
    local generate_func=$2
    
    print_status "$YELLOW" "🚀 Starting batch inserts for $table_name"
    print_status "$BLUE" "Inserting $TOTAL_ROWS rows in $TOTAL_BATCHES batches of $BATCH_SIZE"
    
    local start_time=$(date +%s)
    local successful_batches=0
    local failed_batches=0
    
    for ((batch=1; batch<=TOTAL_BATCHES; batch++)); do
        local start_id=$(((batch-1) * BATCH_SIZE + 1))
        
        # Generate the batch query
        local batch_query
        if [ "$generate_func" = "basic_test" ]; then
            batch_query=$(generate_basic_test_batch $start_id $batch)
        elif [ "$generate_func" = "sales_data" ]; then
            batch_query=$(generate_sales_data_batch $start_id $batch)
        fi
        
        # Execute the batch
        if run_query "$batch_query" "Batch $batch/$TOTAL_BATCHES for $table_name" > /dev/null 2>&1; then
            successful_batches=$((successful_batches + 1))
            # Print progress every 100 batches
            if [ $((batch % 100)) -eq 0 ]; then
                print_status "$GREEN" "  ✅ Completed $batch/$TOTAL_BATCHES batches"
            fi
        else
            failed_batches=$((failed_batches + 1))
            print_status "$RED" "  ❌ Failed batch $batch/$TOTAL_BATCHES"
        fi
    done
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    print_status "$GREEN" "📊 $table_name Insert Summary:"
    print_status "$GREEN" "   ✅ Successful batches: $successful_batches/$TOTAL_BATCHES"
    print_status "$GREEN" "   ❌ Failed batches: $failed_batches/$TOTAL_BATCHES"
    print_status "$GREEN" "   ⏱️  Duration: ${duration} seconds"
    print_status "$GREEN" "   📈 Rows per second: $(( (successful_batches * BATCH_SIZE) / (duration + 1) ))"
    echo "" >> "$LOG_FILE"
    echo "=== $table_name BATCH INSERT SUMMARY ===" >> "$LOG_FILE"
    echo "Successful batches: $successful_batches/$TOTAL_BATCHES" >> "$LOG_FILE"
    echo "Failed batches: $failed_batches/$TOTAL_BATCHES" >> "$LOG_FILE"
    echo "Duration: ${duration} seconds" >> "$LOG_FILE"
    echo "Rows per second: $(( (successful_batches * BATCH_SIZE) / (duration + 1) ))" >> "$LOG_FILE"
    echo "" >> "$LOG_FILE"
}

# Function to verify table counts
verify_table_counts() {
    print_status "$BLUE" "🔍 Verifying table row counts..."
    
    run_query "SELECT COUNT(*) as basic_test_total_rows FROM my_ducklake.basic_test;" "Verify basic_test row count"
    run_query "SELECT COUNT(*) as sales_data_total_rows FROM my_ducklake.sales_data;" "Verify sales_data row count"
}

# Main execution
main() {
    print_status "$YELLOW" "🚀 Starting MPZSQL Small Batch Insert Test Suite"
    print_status "$YELLOW" "================================================="
    print_status "$BLUE" "Configuration: $BATCH_SIZE rows × $TOTAL_BATCHES batches = $TOTAL_ROWS rows per table"
    
    # Check prerequisites
    if [ ! -f "${SCRIPT_DIR}/test_postgresql_config.sh" ]; then
        print_status "$RED" "❌ ERROR: test_postgresql_config.sh not found"
        exit 1
    fi
    
    if [ ! -d "$CLIENT_DIR" ]; then
        print_status "$RED" "❌ ERROR: Client directory not found: $CLIENT_DIR"
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
    run_query "SELECT 'Small batch insert suite started' as status, current_timestamp as test_time;" "Connection Test"
    
    # Get initial row counts
    print_status "$BLUE" "Getting initial row counts..."
    run_query "SELECT COUNT(*) as initial_basic_test_rows FROM my_ducklake.basic_test;" "Initial basic_test count"
    run_query "SELECT COUNT(*) as initial_sales_data_rows FROM my_ducklake.sales_data;" "Initial sales_data count"
    
    # Perform batch inserts for basic_test table
    print_status "$YELLOW" "📊 BASIC_TEST TABLE INSERTS"
    print_status "$YELLOW" "==========================="
    perform_batch_inserts "basic_test" "basic_test"
    
    print_status "$YELLOW" "📊 SALES_DATA TABLE INSERTS"
    print_status "$YELLOW" "=========================="
    perform_batch_inserts "sales_data" "sales_data"
    
    # Final verification
    print_status "$YELLOW" "🎯 Final Verification"
    print_status "$YELLOW" "==================="
    verify_table_counts
    
    # Summary
    print_status "$GREEN" "🎉 Small Batch Insert Test Suite Completed!"
    print_status "$GREEN" "==========================================="
    print_status "$BLUE" "📄 Full results logged to: $LOG_FILE"
    print_status "$BLUE" "📄 Inserted $TOTAL_ROWS rows into each table"
    print_status "$BLUE" "📄 Total rows inserted: $((TOTAL_ROWS * 2))"
    
    # Count overall successes and failures
    success_count=$(grep -c "STATUS: SUCCESS" "$LOG_FILE" || echo "0")
    failure_count=$(grep -c "STATUS: FAILED" "$LOG_FILE" || echo "0")
    
    print_status "$BLUE" "📊 Overall Test Results Summary:"
    print_status "$GREEN" "   ✅ Successful operations: $success_count"
    if [ $failure_count -gt 0 ]; then
        print_status "$RED" "   ❌ Failed operations: $failure_count"
    else
        print_status "$GREEN" "   ❌ Failed operations: $failure_count"
    fi
}

# Run the main function
main "$@"
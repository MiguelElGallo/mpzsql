#!/bin/bash

# MPZSQL Small Batch Insert Test Suite - DEBUG VERSION
# Performs batch inserts with memory monitoring and crash detection

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
LOG_FILE="${SCRIPT_DIR}/insertsmall_debug_results.log"

# Batch configuration - REDUCED for debugging
BATCH_SIZE=100
TOTAL_BATCHES=20  # Reduced from 1000 to 20 for debugging
TOTAL_ROWS=$((BATCH_SIZE * TOTAL_BATCHES))

# Memory monitoring configuration
MEMORY_LOG_FILE="${SCRIPT_DIR}/memory_usage.log"
SERVER_PID=""

# Initialize log files
echo "MPZSQL Small Batch Insert Test Suite - DEBUG VERSION - $(date)" > "$LOG_FILE"
echo "=============================================" >> "$LOG_FILE"
echo "Configuration:" >> "$LOG_FILE"
echo "  Batch Size: $BATCH_SIZE rows per batch" >> "$LOG_FILE"
echo "  Total Batches: $TOTAL_BATCHES batches (REDUCED FOR DEBUGGING)" >> "$LOG_FILE"
echo "  Total Rows per Table: $TOTAL_ROWS rows" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# Initialize memory log
echo "MEMORY USAGE LOG - $(date)" > "$MEMORY_LOG_FILE"
echo "timestamp,batch_num,client_memory_mb,server_memory_mb,system_memory_free_mb" >> "$MEMORY_LOG_FILE"

# Function to print colored output
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
    echo "$message" >> "$LOG_FILE"
}

# Function to get memory usage
get_memory_usage() {
    local batch_num=$1
    local timestamp=$(date "+%Y-%m-%d %H:%M:%S")
    
    # Get client process memory (current script and python processes)
    local client_memory_kb=0
    local client_memory_mb=0
    
    # Try to get memory usage for current process
    if command -v ps >/dev/null 2>&1; then
        client_memory_kb=$(ps -o rss= -p $$ 2>/dev/null | awk '{print $1}' || echo "0")
        client_memory_mb=$((client_memory_kb / 1024))
    fi
    
    # Get server memory usage if we can find the server PID
    local server_memory_mb="N/A"
    if [ ! -z "$SERVER_PID" ] && ps -p "$SERVER_PID" > /dev/null 2>&1; then
        local server_memory_kb=$(ps -o rss= -p "$SERVER_PID" 2>/dev/null | awk '{print $1}' || echo "0")
        if [ "$server_memory_kb" -gt 0 ]; then
            server_memory_mb=$((server_memory_kb / 1024))
        fi
    else
        # Try to find Python server process
        if command -v pgrep >/dev/null 2>&1; then
            local python_pids=$(pgrep -f "python.*mpzsql" 2>/dev/null || echo "")
            if [ ! -z "$python_pids" ]; then
                local server_memory_kb=$(ps -o rss= -p $python_pids 2>/dev/null | awk '{sum += $1} END {print sum}' || echo "0")
                if [ ! -z "$server_memory_kb" ] && [ "$server_memory_kb" -gt 0 ]; then
                    server_memory_mb=$((server_memory_kb / 1024))
                fi
            fi
        fi
    fi
    
    # Get system free memory (macOS specific)
    local system_memory_free_mb="N/A"
    if command -v vm_stat >/dev/null 2>&1; then
        local pages_free=$(vm_stat | grep "Pages free" | awk '{print $3}' | sed 's/\.//' 2>/dev/null || echo "0")
        if [ "$pages_free" -gt 0 ]; then
            system_memory_free_mb=$((pages_free * 4096 / 1024 / 1024))
        fi
    fi
    
    # Log to memory file
    echo "$timestamp,$batch_num,$client_memory_mb,$server_memory_mb,$system_memory_free_mb" >> "$MEMORY_LOG_FILE"
    
    # Print memory info for debugging
    print_status "$BLUE" "📊 Memory: Client=${client_memory_mb}MB, Server=${server_memory_mb}MB, Free=${system_memory_free_mb}MB"
    
    # Print to console if memory is concerning
    if [ "$client_memory_mb" -gt 500 ] || ([ "$server_memory_mb" != "N/A" ] && [ "$server_memory_mb" -gt 1000 ]); then
        print_status "$YELLOW" "⚠️  HIGH MEMORY: Client=${client_memory_mb}MB, Server=${server_memory_mb}MB, Free=${system_memory_free_mb}MB"
    fi
}

# Function to run a single query with enhanced error detection
run_query_debug() {
    local query=$1
    local description=$2
    local batch_num=${3:-0}
    
    echo "----------------------------------------" >> "$LOG_FILE"
    echo "Running: $description" >> "$LOG_FILE"
    echo "Batch: $batch_num" >> "$LOG_FILE"
    echo "Query length: ${#query} characters" >> "$LOG_FILE"
    echo "Timestamp: $(date)" >> "$LOG_FILE"
    echo "" >> "$LOG_FILE"
    
    cd "$CLIENT_DIR"
    
    # Monitor memory before query
    get_memory_usage "$batch_num"
    
    # Capture output with enhanced error detection (no timeout on macOS)
    if python client.py --query "$query" >> "$LOG_FILE" 2>&1; then
        # Check if output contains error messages
        if tail -20 "$LOG_FILE" | grep -q "Error\|Failed\|Exception\|Segmentation fault\|Bus error"; then
            print_status "$RED" "❌ FAILED: $description (errors found in output)"
            echo "STATUS: FAILED - Errors in output" >> "$LOG_FILE"
            
            # Get crash details
            echo "CRASH DETAILS:" >> "$LOG_FILE"
            tail -50 "$LOG_FILE" | grep -A 5 -B 5 "Error\|Failed\|Exception\|Segmentation fault\|Bus error" >> "$LOG_FILE"
            return 1
        else
            echo "STATUS: SUCCESS" >> "$LOG_FILE"
            
            # Monitor memory after successful query
            get_memory_usage "$batch_num"
        fi
    else
        exit_code=$?
        print_status "$RED" "❌ FAILED: $description (exit code: $exit_code, possibly crash)"
        echo "STATUS: FAILED - Exit code: $exit_code" >> "$LOG_FILE"
        
        # Check for specific crash types
        if [ $exit_code -eq 139 ]; then
            echo "SEGFAULT: Segmentation fault detected" >> "$LOG_FILE"
        elif [ $exit_code -eq 134 ]; then
            echo "SIGABRT: Process aborted (possibly memory issue)" >> "$LOG_FILE"
        fi
        
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
        local data="debug_batch_${batch_num}_row_${i}_$(date +%s)"
        
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
    products=("Debug_Product_A" "Debug_Product_B" "Debug_Widget" "Debug_Gadget")
    
    for ((i=0; i<BATCH_SIZE; i++)); do
        local product_idx=$((i % ${#products[@]}))
        local product="${products[$product_idx]}_batch${batch_num}"
        local price=$(awk "BEGIN {printf \"%.2f\", 10.0 + ($i * 0.5) + ($batch_num * 0.1)}")
        local quantity=$((1 + (i % 10) + (batch_num % 5)))
        local days_offset=$(((start_offset + i) % 30))  # Reduced date range
        local sale_date=$(date -j -v-${days_offset}d +%Y-%m-%d)
        
        if [ $i -eq 0 ]; then
            query="${query} ('$product', $price, $quantity, '$sale_date')"
        else
            query="${query}, ('$product', $price, $quantity, '$sale_date')"
        fi
    done
    
    echo "$query;"
}

# Function to perform batch inserts for a table with enhanced debugging
perform_batch_inserts_debug() {
    local table_name=$1
    local generate_func=$2
    
    print_status "$YELLOW" "🚀 Starting DEBUG batch inserts for $table_name"
    print_status "$BLUE" "Inserting $TOTAL_ROWS rows in $TOTAL_BATCHES batches of $BATCH_SIZE (DEBUG MODE)"
    
    local start_time=$(date +%s)
    local successful_batches=0
    local failed_batches=0
    
    # Get initial memory baseline
    print_status "$BLUE" "📊 Getting baseline memory usage..."
    get_memory_usage 0
    
    for ((batch=1; batch<=TOTAL_BATCHES; batch++)); do
        local start_id=$(((batch-1) * BATCH_SIZE + 1))
        
        print_status "$BLUE" "📝 Preparing batch $batch/$TOTAL_BATCHES for $table_name..."
        
        # Generate the batch query
        local batch_query
        if [ "$generate_func" = "basic_test" ]; then
            batch_query=$(generate_basic_test_batch $start_id $batch)
        elif [ "$generate_func" = "sales_data" ]; then
            batch_query=$(generate_sales_data_batch $start_id $batch)
        fi
        
        print_status "$BLUE" "🚀 Executing batch $batch/$TOTAL_BATCHES for $table_name (query size: ${#batch_query} chars)..."
        
        # Execute the batch with enhanced debugging
        if run_query_debug "$batch_query" "Batch $batch/$TOTAL_BATCHES for $table_name" "$batch"; then
            successful_batches=$((successful_batches + 1))
            print_status "$GREEN" "  ✅ Completed batch $batch/$TOTAL_BATCHES successfully"
            
            # Memory check after each batch
            sleep 1  # Small pause to let memory settle
        else
            failed_batches=$((failed_batches + 1))
            print_status "$RED" "  ❌ Failed batch $batch/$TOTAL_BATCHES"
            print_status "$RED" "  🛑 STOPPING INSERTS DUE TO FAILURE (for debugging)"
            break
        fi
    done
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    print_status "$GREEN" "📊 $table_name DEBUG Insert Summary:"
    print_status "$GREEN" "   ✅ Successful batches: $successful_batches/$TOTAL_BATCHES"
    print_status "$GREEN" "   ❌ Failed batches: $failed_batches/$TOTAL_BATCHES"
    print_status "$GREEN" "   ⏱️  Duration: ${duration} seconds"
    if [ $successful_batches -gt 0 ]; then
        print_status "$GREEN" "   📈 Rows per second: $(( (successful_batches * BATCH_SIZE) / (duration + 1) ))"
    fi
    
    echo "" >> "$LOG_FILE"
    echo "=== $table_name DEBUG BATCH INSERT SUMMARY ===" >> "$LOG_FILE"
    echo "Successful batches: $successful_batches/$TOTAL_BATCHES" >> "$LOG_FILE"
    echo "Failed batches: $failed_batches/$TOTAL_BATCHES" >> "$LOG_FILE"
    echo "Duration: ${duration} seconds" >> "$LOG_FILE"
    if [ $successful_batches -gt 0 ]; then
        echo "Rows per second: $(( (successful_batches * BATCH_SIZE) / (duration + 1) ))" >> "$LOG_FILE"
    fi
    echo "" >> "$LOG_FILE"
}

# Function to check PyArrow and environment info
check_environment() {
    print_status "$BLUE" "🔍 Checking Python and PyArrow environment..."
    
    cd "$CLIENT_DIR"
    
    # Check Python version
    python --version >> "$LOG_FILE" 2>&1
    
    # Check PyArrow version and info with better error handling
    python -c "
import sys
import os
print('=== ENVIRONMENT INFO ===')
print('Python version:', sys.version)
print('Python executable:', sys.executable)
print('Process ID:', os.getpid())

try:
    import pyarrow as pa
    print('PyArrow version:', pa.__version__)
    print('PyArrow build info:', pa.cpp_build_info)
    try:
        print('PyArrow built with CUDA:', pa.cuda.have_cuda() if hasattr(pa, 'cuda') else 'N/A')
    except:
        print('PyArrow CUDA check: N/A (error checking)')
    
    try:
        pool = pa.default_memory_pool()
        print('PyArrow memory pool:', type(pool).__name__)
        print('PyArrow allocated bytes:', pool.bytes_allocated())
    except Exception as e:
        print('PyArrow memory pool error:', str(e))
        
except ImportError as e:
    print('PyArrow import error:', str(e))

try:
    import psutil
    print('System memory:', psutil.virtual_memory())
    print('psutil available: YES')
except ImportError:
    print('psutil available: NO (not installed)')
    # Get basic memory info from system commands instead
    try:
        import subprocess
        result = subprocess.run(['free', '-m'], capture_output=True, text=True)
        if result.returncode == 0:
            print('Basic memory info:', result.stdout.strip().replace('\n', ' | '))
        else:
            print('Basic memory info: unavailable')
    except:
        print('Basic memory info: unavailable (no free command)')

try:
    import adbc_driver_flightsql
    print('ADBC FlightSQL version:', adbc_driver_flightsql.__version__)
except ImportError as e:
    print('ADBC FlightSQL import error:', str(e))

print('========================')
" >> "$LOG_FILE" 2>&1
    
    if [ $? -eq 0 ]; then
        print_status "$GREEN" "✅ Environment info logged"
    else
        print_status "$YELLOW" "⚠️  Environment check had issues, but continuing..."
    fi
}

# Main execution
main() {
    print_status "$YELLOW" "🚀 Starting MPZSQL Small Batch Insert Test Suite - DEBUG VERSION"
    print_status "$YELLOW" "================================================================="
    print_status "$BLUE" "Configuration: $BATCH_SIZE rows × $TOTAL_BATCHES batches = $TOTAL_ROWS rows per table"
    print_status "$YELLOW" "⚠️  DEBUG MODE: Reduced batch count, enhanced monitoring, memory tracking"
    
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
    
    # Check environment info (allow failures)
    set +e  # Temporarily disable exit on error
    check_environment
    set -e  # Re-enable exit on error
    
    # Test connection first
    print_status "$BLUE" "Testing basic connection..."
    run_query_debug "SELECT 'Debug insert suite started' as status, current_timestamp as test_time;" "Connection Test" 0
    
    # Get initial row counts
    print_status "$BLUE" "Getting initial row counts..."
    run_query_debug "SELECT COUNT(*) as initial_basic_test_rows FROM my_ducklake.basic_test;" "Initial basic_test count" 0
    run_query_debug "SELECT COUNT(*) as initial_sales_data_rows FROM my_ducklake.sales_data;" "Initial sales_data count" 0
    
    # Perform batch inserts for basic_test table
    print_status "$YELLOW" "📊 BASIC_TEST TABLE DEBUG INSERTS"
    print_status "$YELLOW" "=================================="
    perform_batch_inserts_debug "basic_test" "basic_test"
    
    print_status "$YELLOW" "📊 SALES_DATA TABLE DEBUG INSERTS"
    print_status "$YELLOW" "================================="
    perform_batch_inserts_debug "sales_data" "sales_data"
    
    # Final verification
    print_status "$YELLOW" "🎯 Final Verification"
    print_status "$YELLOW" "==================="
    run_query_debug "SELECT COUNT(*) as final_basic_test_rows FROM my_ducklake.basic_test;" "Final basic_test count" 999
    run_query_debug "SELECT COUNT(*) as final_sales_data_rows FROM my_ducklake.sales_data;" "Final sales_data count" 999
    
    # Summary
    print_status "$GREEN" "🎉 DEBUG Test Suite Completed!"
    print_status "$GREEN" "=============================="
    print_status "$BLUE" "📄 Full results logged to: $LOG_FILE"
    print_status "$BLUE" "📄 Memory usage logged to: $MEMORY_LOG_FILE"
    print_status "$BLUE" "📄 Attempted to insert $TOTAL_ROWS rows into each table"
    
    # Count overall successes and failures
    success_count=$(grep -c "STATUS: SUCCESS" "$LOG_FILE" || echo "0")
    failure_count=$(grep -c "STATUS: FAILED" "$LOG_FILE" || echo "0")
    
    print_status "$BLUE" "📊 Overall Debug Test Results:"
    print_status "$GREEN" "   ✅ Successful operations: $success_count"
    if [ $failure_count -gt 0 ]; then
        print_status "$RED" "   ❌ Failed operations: $failure_count"
        print_status "$YELLOW" "   🔍 Check logs for crash details and memory usage patterns"
    else
        print_status "$GREEN" "   ❌ Failed operations: $failure_count"
    fi
    
    print_status "$BLUE" "📊 Next steps for debugging:"
    print_status "$BLUE" "   1. Review $MEMORY_LOG_FILE for memory usage patterns"
    print_status "$BLUE" "   2. Check $LOG_FILE for crash details"
    print_status "$BLUE" "   3. If crashes persist, reduce batch size further"
    print_status "$BLUE" "   4. Consider running with server logs enabled"
}

# Trap to cleanup on exit
cleanup() {
    print_status "$YELLOW" "🧹 Cleaning up..."
    # Any cleanup needed
}
trap cleanup EXIT

# Run the main function
main "$@"
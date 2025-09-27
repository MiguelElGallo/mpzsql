#!/bin/bash

# MPZSQL Small Batch Insert Test Suite - SIMPLE DEBUG VERSION
# Performs batch inserts with basic monitoring (no psutil dependency)

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
LOG_FILE="${SCRIPT_DIR}/insertsmall_simple_debug.log"

# Batch configuration - REDUCED for debugging
BATCH_SIZE=100
TOTAL_BATCHES=10  # Even smaller for testing
TOTAL_ROWS=$((BATCH_SIZE * TOTAL_BATCHES))

# Initialize log file
echo "MPZSQL Simple Debug Insert Test - $(date)" > "$LOG_FILE"
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

# Function to get basic system info (no psutil needed)
get_basic_system_info() {
    echo "=== SYSTEM INFO ===" >> "$LOG_FILE"
    echo "Date: $(date)" >> "$LOG_FILE"
    echo "User: $(whoami)" >> "$LOG_FILE"
    echo "Working directory: $(pwd)" >> "$LOG_FILE"
    echo "Python version: $(python --version 2>&1)" >> "$LOG_FILE"
    
    # Basic memory info (macOS)
    if command -v vm_stat >/dev/null 2>&1; then
        echo "Memory info:" >> "$LOG_FILE"
        vm_stat | head -10 >> "$LOG_FILE"
    fi
    
    # Process info
    echo "Current process PID: $$" >> "$LOG_FILE"
    echo "=================" >> "$LOG_FILE"
}

# Function to run a single query with basic error detection
run_query_simple() {
    local query=$1
    local description=$2
    local batch_num=${3:-0}
    
    print_status "$BLUE" "🔄 $description (batch $batch_num)"
    
    echo "----------------------------------------" >> "$LOG_FILE"
    echo "Running: $description" >> "$LOG_FILE"
    echo "Batch: $batch_num" >> "$LOG_FILE"
    echo "Query length: ${#query} characters" >> "$LOG_FILE"
    echo "Timestamp: $(date)" >> "$LOG_FILE"
    echo "First 100 chars: ${query:0:100}..." >> "$LOG_FILE"
    echo "" >> "$LOG_FILE"
    
    cd "$CLIENT_DIR"
    
    # Execute without timeout (since timeout command may not be available on macOS)
    if python client.py --query "$query" >> "$LOG_FILE" 2>&1; then
        local exit_code=$?
        
        # Check if output contains error messages
        if tail -10 "$LOG_FILE" | grep -q -i "error\|failed\|exception\|segmentation\|abort"; then
            print_status "$RED" "❌ FAILED: $description (errors found in output)"
            echo "STATUS: FAILED - Errors detected" >> "$LOG_FILE"
            echo "Last 20 lines of output:" >> "$LOG_FILE"
            tail -20 "$LOG_FILE" >> "$LOG_FILE"
            return 1
        else
            print_status "$GREEN" "✅ SUCCESS: $description"
            echo "STATUS: SUCCESS" >> "$LOG_FILE"
        fi
    else
        local exit_code=$?
        print_status "$RED" "❌ FAILED: $description (exit code: $exit_code)"
        echo "STATUS: FAILED - Exit code: $exit_code" >> "$LOG_FILE"
        
        # Identify crash types
        case $exit_code in
            139) echo "CRASH TYPE: SEGMENTATION FAULT" >> "$LOG_FILE" ;;
            134) echo "CRASH TYPE: SIGABRT (likely memory issue)" >> "$LOG_FILE" ;;
            127) echo "CRASH TYPE: COMMAND NOT FOUND (path/environment issue)" >> "$LOG_FILE" ;;
            *) echo "CRASH TYPE: Unknown exit code $exit_code" >> "$LOG_FILE" ;;
        esac
        
        return 1
    fi
    echo "" >> "$LOG_FILE"
}

# Function to generate basic_test batch insert
generate_basic_test_batch() {
    local start_id=$1
    local batch_num=$2
    
    local query="INSERT INTO my_ducklake.basic_test (id, data) VALUES"
    
    for ((i=0; i<BATCH_SIZE; i++)); do
        local id=$((start_id + i))
        local data="simple_debug_batch_${batch_num}_row_${i}_$(date +%s)"
        
        if [ $i -eq 0 ]; then
            query="${query} ($id, '$data')"
        else
            query="${query}, ($id, '$data')"
        fi
    done
    
    echo "$query;"
}

# Function to perform batch inserts for basic_test table
perform_basic_test_inserts() {
    print_status "$YELLOW" "🚀 Starting simple debug batch inserts for basic_test"
    print_status "$BLUE" "Inserting $TOTAL_ROWS rows in $TOTAL_BATCHES batches of $BATCH_SIZE"
    
    local start_time=$(date +%s)
    local successful_batches=0
    local failed_batches=0
    
    for ((batch=1; batch<=TOTAL_BATCHES; batch++)); do
        local start_id=$(((batch-1) * BATCH_SIZE + 10000))  # Start from 10000 to avoid conflicts
        
        print_status "$BLUE" "📝 Preparing batch $batch/$TOTAL_BATCHES..."
        
        # Generate the batch query
        local batch_query=$(generate_basic_test_batch $start_id $batch)
        
        # Execute the batch
        if run_query_simple "$batch_query" "Batch $batch/$TOTAL_BATCHES for basic_test" "$batch"; then
            successful_batches=$((successful_batches + 1))
            print_status "$GREEN" "  ✅ Completed batch $batch/$TOTAL_BATCHES"
        else
            failed_batches=$((failed_batches + 1))
            print_status "$RED" "  ❌ Failed batch $batch/$TOTAL_BATCHES"
            print_status "$RED" "  🛑 STOPPING on first failure for debugging"
            break
        fi
        
        # Small pause between batches
        sleep 0.5
    done
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    print_status "$GREEN" "📊 Simple Debug Insert Summary:"
    print_status "$GREEN" "   ✅ Successful batches: $successful_batches/$TOTAL_BATCHES"
    print_status "$GREEN" "   ❌ Failed batches: $failed_batches/$TOTAL_BATCHES"
    print_status "$GREEN" "   ⏱️  Duration: ${duration} seconds"
    if [ $successful_batches -gt 0 ]; then
        print_status "$GREEN" "   📈 Rows per second: $(( (successful_batches * BATCH_SIZE) / (duration + 1) ))"
    fi
    
    echo "" >> "$LOG_FILE"
    echo "=== SIMPLE DEBUG SUMMARY ===" >> "$LOG_FILE"
    echo "Successful batches: $successful_batches/$TOTAL_BATCHES" >> "$LOG_FILE"
    echo "Failed batches: $failed_batches/$TOTAL_BATCHES" >> "$LOG_FILE"
    echo "Duration: ${duration} seconds" >> "$LOG_FILE"
    echo "" >> "$LOG_FILE"
}

# Main execution
main() {
    print_status "$YELLOW" "🚀 Starting MPZSQL Simple Debug Insert Test"
    print_status "$YELLOW" "============================================"
    print_status "$BLUE" "Configuration: $BATCH_SIZE rows × $TOTAL_BATCHES batches = $TOTAL_ROWS rows"
    print_status "$YELLOW" "⚠️  SIMPLE MODE: Basic error detection, no external dependencies"
    
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
    
    # Get basic system info
    print_status "$BLUE" "Collecting basic system info..."
    get_basic_system_info
    
    # Test connection first
    print_status "$BLUE" "Testing basic connection..."
    if ! run_query_simple "SELECT 'Simple debug test started' as status, current_timestamp as test_time;" "Connection Test" 0; then
        print_status "$RED" "❌ Connection test failed, aborting"
        exit 1
    fi
    
    # Get initial row count
    print_status "$BLUE" "Getting initial row count..."
    run_query_simple "SELECT COUNT(*) as initial_basic_test_rows FROM my_ducklake.basic_test;" "Initial basic_test count" 0
    
    # Perform batch inserts
    perform_basic_test_inserts
    
    # Final verification
    print_status "$YELLOW" "🎯 Final Verification"
    print_status "$YELLOW" "==================="
    run_query_simple "SELECT COUNT(*) as final_basic_test_rows FROM my_ducklake.basic_test;" "Final basic_test count" 999
    
    # Summary
    print_status "$GREEN" "🎉 Simple Debug Test Completed!"
    print_status "$GREEN" "==============================="
    print_status "$BLUE" "📄 Full results logged to: $LOG_FILE"
    
    # Count results
    success_count=$(grep -c "STATUS: SUCCESS" "$LOG_FILE" || echo "0")
    failure_count=$(grep -c "STATUS: FAILED" "$LOG_FILE" || echo "0")
    
    print_status "$BLUE" "📊 Test Results:"
    print_status "$GREEN" "   ✅ Successful operations: $success_count"
    if [ $failure_count -gt 0 ]; then
        print_status "$RED" "   ❌ Failed operations: $failure_count"
        print_status "$YELLOW" "   🔍 Check $LOG_FILE for detailed error information"
        print_status "$YELLOW" "   🔍 Look for CRASH TYPE and error messages"
    else
        print_status "$GREEN" "   ❌ Failed operations: $failure_count"
    fi
}

# Trap to cleanup on exit
cleanup() {
    print_status "$YELLOW" "🧹 Cleanup complete"
}
trap cleanup EXIT

# Run the main function
main "$@"
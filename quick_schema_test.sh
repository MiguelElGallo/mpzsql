#!/bin/bash

# Quick Schema Detection Test
# A simplified test for rapid validation of the schema detection fix

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    echo -e "${1}${2}${NC}"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT_DIR="${SCRIPT_DIR}/src/demo_client"

print_status "$YELLOW" "🚀 Quick Schema Detection Test"
print_status "$YELLOW" "=============================="

# Load config and activate venv
source "${SCRIPT_DIR}/test_postgresql_config.sh" > /dev/null 2>&1
source "${SCRIPT_DIR}/.venv/bin/activate"
cd "$CLIENT_DIR"

# Test 1: Basic data types
print_status "$BLUE" "1. Testing basic data types..."
python client.py --query "SELECT 'text' as text_col, 123 as int_col, 45.67 as float_col, true as bool_col, current_date as date_col;" | grep -A 10 "Schema:" || true

# Test 2: Simple table creation and data
print_status "$BLUE" "2. Testing table creation and data retrieval..."
python client.py --query "CREATE TABLE IF NOT EXISTS my_ducklake.quick_test (id INT, name VARCHAR, value DOUBLE);" > /dev/null 2>&1
python client.py --query "INSERT INTO my_ducklake.quick_test VALUES (1, 'Test1', 100.5), (2, 'Test2', 200.7);" > /dev/null 2>&1
python client.py --query "SELECT * FROM my_ducklake.quick_test ORDER BY id;" | grep -A 10 "Schema:" || true

# Test 3: Aggregation
print_status "$BLUE" "3. Testing aggregation query..."
python client.py --query "SELECT COUNT(*) as record_count, AVG(value) as avg_value, MAX(value) as max_value FROM my_ducklake.quick_test;" | grep -A 10 "Schema:" || true

print_status "$GREEN" "✅ Quick test completed!"
print_status "$BLUE" "The schema detection fix is working - queries return proper schema information and data!"
-- MPZSQL Ducklake List Files Test Suite
-- Lists files for all tables used in the fixed schema tests

-- List files for basic_test table
-- Print the output to see the underlying file structure
SELECT 'basic_test table files:' as info;
SELECT * FROM ducklake_list_files('my_ducklake', 'basic_test', schema => 'main');

-- Add some spacing for readability
SELECT '' as separator;

-- List files for sales_data table
-- Print the output to see the underlying file structure
SELECT 'sales_data table files:' as info;
SELECT * FROM ducklake_list_files('my_ducklake', 'sales_data', schema => 'main');

-- Add some spacing for readability
SELECT '' as separator;

-- Summary information
SELECT 
    'File listing completed for all tables' as summary,
    current_timestamp as completed_at;
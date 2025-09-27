-- MPZSQL Ducklake Merge Files Test Suite
-- Merges adjacent files for all tables used in the fixed schema tests

-- Merge files for basic_test table
SELECT 'Merging files for basic_test table...' as info;
CALL ducklake_merge_adjacent_files('my_ducklake', 'basic_test', schema => 'main');

-- Verify merge operation completed
SELECT 'basic_test merge operation completed' as status;

-- Add some spacing for readability
SELECT '' as separator;

-- Merge files for sales_data table
SELECT 'Merging files for sales_data table...' as info;
CALL ducklake_merge_adjacent_files('my_ducklake', 'sales_data', schema => 'main');

-- Verify merge operation completed
SELECT 'sales_data merge operation completed' as status;

-- Add some spacing for readability
SELECT '' as separator;

-- Summary information
SELECT 
    'File merge operations completed for all tables' as summary,
    current_timestamp as completed_at;
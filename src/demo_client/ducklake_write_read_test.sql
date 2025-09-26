-- Test writing and reading data in my_ducklake database
-- This verifies the full DuckLake integration is working

-- Switch to the my_ducklake database
USE my_ducklake;

-- Clean slate - drop table if exists
DROP TABLE IF EXISTS main.ducklake_test_table;

-- Create a test table in main schema
CREATE TABLE main.ducklake_test_table (
    id INTEGER,
    product_name VARCHAR(100),
    price DECIMAL(10,2),
    category VARCHAR(50),
    in_stock BOOLEAN,
    created_date DATE
);

-- Insert test data (multiple rows)
INSERT INTO main.ducklake_test_table VALUES
(1, 'Laptop Pro', 1299.99, 'Electronics', true, '2024-01-15');

INSERT INTO main.ducklake_test_table VALUES
(2, 'Coffee Mug', 12.50, 'Kitchen', true, '2024-01-16');

INSERT INTO main.ducklake_test_table VALUES
(3, 'Desk Chair', 249.00, 'Furniture', false, '2024-01-17');

INSERT INTO main.ducklake_test_table VALUES
(4, 'Smartphone', 699.99, 'Electronics', true, '2024-01-18');

-- Verify we can read the data back
SELECT * FROM main.ducklake_test_table;

-- Test filtered queries
SELECT * FROM main.ducklake_test_table WHERE category = 'Electronics';

-- Test aggregate functions
SELECT COUNT(*) as total_products FROM main.ducklake_test_table;

-- Test with grouping
SELECT category, COUNT(*) as product_count, AVG(price) as avg_price 
FROM main.ducklake_test_table 
GROUP BY category;
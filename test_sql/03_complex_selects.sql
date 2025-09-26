-- Complex SELECT Queries Test
-- Test various types of SELECT operations to verify schema detection

-- Simple SELECT with all columns
SELECT * FROM my_ducklake.basic_test ORDER BY id;

-- SELECT with specific columns and calculations
SELECT 
    product_name,
    price,
    quantity,
    (price * quantity) as total_value
FROM my_ducklake.sales_data 
ORDER BY total_value DESC;

-- SELECT with aggregations
SELECT 
    region,
    COUNT(*) as product_count,
    SUM(quantity) as total_quantity,
    AVG(price) as avg_price,
    MAX(price) as max_price,
    MIN(price) as min_price
FROM my_ducklake.sales_data 
GROUP BY region 
ORDER BY total_quantity DESC;

-- SELECT with filtering and type casting
SELECT 
    product_name,
    CAST(price AS INTEGER) as price_rounded,
    quantity,
    sale_date
FROM my_ducklake.sales_data 
WHERE price > 100.00 
  AND quantity >= 10
ORDER BY price DESC;

-- Employee data with string functions
SELECT 
    emp_id,
    CONCAT(first_name, ' ', last_name) as full_name,
    UPPER(department) as dept_upper,
    salary,
    CASE 
        WHEN salary >= 90000 THEN 'Senior'
        WHEN salary >= 70000 THEN 'Mid-level'
        ELSE 'Junior'
    END as salary_level
FROM my_ducklake.employees 
ORDER BY salary DESC;
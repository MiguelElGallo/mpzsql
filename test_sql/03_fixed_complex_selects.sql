-- Fixed Complex SELECT Queries Test
-- Test various types of SELECT operations using ACTUAL Azure table schemas

-- Simple SELECT with all columns from basic_test (actual columns: id, data)
SELECT * FROM my_ducklake.basic_test ORDER BY id;

-- SELECT with specific columns from sales_data (actual columns: product, price, quantity, sale_date)
SELECT 
    product,
    price,
    quantity,
    (price * quantity) as total_value
FROM my_ducklake.sales_data 
ORDER BY total_value DESC;

-- SELECT with aggregations using actual columns
SELECT 
    COUNT(*) as product_count,
    SUM(quantity) as total_quantity,
    AVG(price) as avg_price,
    MAX(price) as max_price,
    MIN(price) as min_price
FROM my_ducklake.sales_data;

-- SELECT with filtering and type casting using actual columns
SELECT 
    product,
    CAST(price AS INTEGER) as price_rounded,
    quantity,
    sale_date
FROM my_ducklake.sales_data 
WHERE price > 100.00 
  AND quantity >= 5
ORDER BY price DESC;

-- GROUP BY with actual columns
SELECT 
    product,
    SUM(quantity) as total_sold,
    AVG(price) as avg_price,
    COUNT(*) as num_records
FROM my_ducklake.sales_data 
GROUP BY product
ORDER BY total_sold DESC;

-- Date-based analysis using actual sale_date column
SELECT 
    sale_date,
    COUNT(*) as daily_transactions,
    SUM(quantity) as daily_quantity,
    SUM(price * quantity) as daily_revenue
FROM my_ducklake.sales_data 
GROUP BY sale_date 
ORDER BY sale_date DESC;

-- Basic string operations on actual columns
SELECT 
    UPPER(product) as product_upper,
    LOWER(product) as product_lower,
    LENGTH(product) as product_name_length,
    price,
    quantity
FROM my_ducklake.sales_data 
ORDER BY product_name_length DESC;
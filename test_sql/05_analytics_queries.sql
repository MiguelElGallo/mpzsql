-- Data Analysis and Reporting Queries
-- Test analytical queries with various aggregations

-- Daily sales summary with multiple metrics
SELECT 
    sale_date,
    COUNT(DISTINCT product_id) as unique_products,
    SUM(quantity) as total_units_sold,
    SUM(price * quantity) as total_revenue,
    AVG(price) as avg_product_price,
    MAX(price * quantity) as highest_sale_value
FROM my_ducklake.sales_data 
GROUP BY sale_date 
ORDER BY sale_date DESC;

-- Product performance analysis
SELECT 
    product_name,
    SUM(quantity) as total_sold,
    SUM(price * quantity) as total_revenue,
    AVG(price) as avg_price,
    COUNT(*) as num_transactions,
    MIN(sale_date) as first_sale,
    MAX(sale_date) as last_sale
FROM my_ducklake.sales_data 
GROUP BY product_name
HAVING SUM(quantity) > 10
ORDER BY total_revenue DESC;

-- Regional analysis with percentages
SELECT 
    region,
    COUNT(*) as transaction_count,
    SUM(quantity) as total_quantity,
    SUM(price * quantity) as total_revenue,
    ROUND(
        (SUM(price * quantity) / 
         (SELECT SUM(price * quantity) FROM my_ducklake.sales_data)) * 100, 
        2
    ) as revenue_percentage
FROM my_ducklake.sales_data 
GROUP BY region
ORDER BY total_revenue DESC;

-- Price range analysis
SELECT 
    CASE 
        WHEN price < 50 THEN 'Budget (< $50)'
        WHEN price < 150 THEN 'Mid-range ($50-$149)'
        WHEN price < 500 THEN 'Premium ($150-$499)'
        ELSE 'Luxury ($500+)'
    END as price_category,
    COUNT(*) as product_count,
    SUM(quantity) as total_sold,
    AVG(price) as avg_price_in_category,
    SUM(price * quantity) as category_revenue
FROM my_ducklake.sales_data
GROUP BY price_category
ORDER BY category_revenue DESC;
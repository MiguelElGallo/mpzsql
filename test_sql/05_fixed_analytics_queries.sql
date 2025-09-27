-- Fixed Analytics Queries Test  
-- Test analytical queries using ACTUAL Azure table schemas

-- Daily sales summary with actual columns
SELECT 
    sale_date,
    COUNT(*) as transaction_count,
    SUM(quantity) as total_units_sold,
    SUM(price * quantity) as total_revenue,
    AVG(price) as avg_product_price,
    MAX(price * quantity) as highest_sale_value
FROM my_ducklake.sales_data 
GROUP BY sale_date 
ORDER BY sale_date DESC;

-- Product performance analysis with actual columns
SELECT 
    product,
    SUM(quantity) as total_sold,
    SUM(price * quantity) as total_revenue,
    AVG(price) as avg_price,
    COUNT(*) as num_transactions,
    MIN(sale_date) as first_sale,
    MAX(sale_date) as last_sale
FROM my_ducklake.sales_data 
GROUP BY product
HAVING SUM(quantity) > 2
ORDER BY total_revenue DESC;

-- Price range analysis using actual price column
SELECT 
    CASE 
        WHEN price < 50 THEN 'Budget (< $50)'
        WHEN price < 150 THEN 'Mid-range ($50-$149)'
        WHEN price < 300 THEN 'Premium ($150-$299)'
        ELSE 'Luxury ($300+)'
    END as price_category,
    COUNT(*) as product_count,
    SUM(quantity) as total_quantity,
    AVG(price) as avg_price_in_category,
    SUM(price * quantity) as category_revenue
FROM my_ducklake.sales_data
GROUP BY price_category
ORDER BY category_revenue DESC;

-- Quantity distribution analysis
SELECT 
    CASE 
        WHEN quantity <= 3 THEN 'Low (1-3)'
        WHEN quantity <= 7 THEN 'Medium (4-7)'
        ELSE 'High (8+)'
    END as quantity_range,
    COUNT(*) as product_count,
    AVG(price) as avg_price,
    SUM(price * quantity) as total_revenue
FROM my_ducklake.sales_data
GROUP BY quantity_range
ORDER BY avg_price DESC;

-- Revenue per product with percentages
SELECT 
    product,
    SUM(price * quantity) as product_revenue,
    ROUND(
        (SUM(price * quantity) / 
         (SELECT SUM(price * quantity) FROM my_ducklake.sales_data)) * 100, 
        2
    ) as revenue_percentage
FROM my_ducklake.sales_data 
GROUP BY product
ORDER BY product_revenue DESC;
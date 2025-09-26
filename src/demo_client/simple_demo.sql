-- Simple SQL commands for MPZSQL/DuckLake demo
-- Switch to the my_ducklake database
USE my_ducklake;

-- Create a simple demo table  
CREATE TABLE main.demo_products (
    product_id INTEGER,
    product_name VARCHAR(100),
    category VARCHAR(50),
    price DECIMAL(8,2),
    in_stock BOOLEAN
);
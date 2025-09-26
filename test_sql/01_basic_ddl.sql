-- Basic DDL Operations Test
-- Test creating tables with different data types

-- Create a simple test table
CREATE TABLE my_ducklake.basic_test (
    id INTEGER,
    name VARCHAR(100),
    amount DOUBLE,
    active BOOLEAN,
    created_at TIMESTAMP
);

-- Create a sales data table
CREATE TABLE my_ducklake.sales_data (
    product_id INTEGER,
    product_name VARCHAR(200),
    price DECIMAL(10,2),
    quantity INTEGER,
    sale_date DATE,
    region VARCHAR(50)
);

-- Create an employee table for testing
CREATE TABLE my_ducklake.employees (
    emp_id INTEGER PRIMARY KEY,
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    department VARCHAR(50),
    salary DOUBLE,
    hire_date DATE
);
-- Complete test for MPZSQL/DuckLake
-- This test creates a table, inserts data, and queries it all in one session

-- Switch to the my_ducklake database
USE my_ducklake;

-- Drop table if it exists to start fresh
DROP TABLE IF EXISTS main.test_customers;

-- Create the table
CREATE TABLE main.test_customers (
    id INTEGER,
    name VARCHAR(100),
    email VARCHAR(150),
    city VARCHAR(50),
    active BOOLEAN
);

-- Insert test data
INSERT INTO main.test_customers VALUES
(1, 'Alice Smith', 'alice@example.com', 'New York', true);

INSERT INTO main.test_customers VALUES
(2, 'Bob Johnson', 'bob@example.com', 'Los Angeles', true);

INSERT INTO main.test_customers VALUES
(3, 'Charlie Brown', 'charlie@example.com', 'Chicago', false);

-- Query the data
SELECT * FROM main.test_customers;

-- Get count
SELECT COUNT(*) as total_count FROM main.test_customers;

-- Query with filter
SELECT * FROM main.test_customers WHERE active = true;
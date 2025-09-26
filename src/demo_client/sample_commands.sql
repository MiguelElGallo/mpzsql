-- Sample SQL commands for MPZSQL/DuckLake
-- This file demonstrates creating a table, inserting data, and querying

-- First, let's switch to the my_ducklake database
USE my_ducklake;

-- Create a simple table in the main schema (no primary keys or defaults as they're not supported)
CREATE TABLE main.demo_customers (
    customer_id INTEGER,
    customer_name VARCHAR(100),
    email VARCHAR(150),
    city VARCHAR(50),
    registration_date DATE,
    total_orders INTEGER,
    total_spent DECIMAL(10,2),
    is_premium BOOLEAN
);

-- Insert some dummy data into the table
INSERT INTO main.demo_customers VALUES
(1, 'John Smith', 'john.smith@email.com', 'New York', '2023-01-15', 5, 1250.50, true);

INSERT INTO main.demo_customers VALUES
(2, 'Sarah Johnson', 'sarah.j@email.com', 'Los Angeles', '2023-02-20', 3, 890.25, false);

INSERT INTO main.demo_customers VALUES
(3, 'Mike Wilson', 'mike.wilson@email.com', 'Chicago', '2023-01-30', 8, 2150.75, true);

INSERT INTO main.demo_customers VALUES
(4, 'Emily Brown', 'emily.brown@email.com', 'Houston', '2023-03-10', 2, 450.00, false);

INSERT INTO main.demo_customers VALUES
(5, 'David Garcia', 'david.garcia@email.com', 'Phoenix', '2023-02-05', 6, 1680.30, true);

-- Query all data from the table
SELECT * FROM main.demo_customers;

-- Get count of all records
SELECT COUNT(*) as total_customers FROM main.demo_customers;
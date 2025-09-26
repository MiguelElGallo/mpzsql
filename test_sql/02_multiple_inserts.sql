-- Multiple INSERT Operations Test
-- Test inserting various types of data

-- Insert basic test data
INSERT INTO my_ducklake.basic_test VALUES 
    (1, 'Test Record 1', 100.50, true, '2025-09-26 10:00:00'),
    (2, 'Test Record 2', 250.75, false, '2025-09-26 11:00:00'),
    (3, 'Test Record 3', 99.99, true, '2025-09-26 12:00:00');

-- Insert sales data with multiple rows
INSERT INTO my_ducklake.sales_data VALUES 
    (1, 'Laptop Computer', 1299.99, 5, '2025-09-26', 'North America'),
    (2, 'Wireless Mouse', 29.99, 50, '2025-09-26', 'Europe'),
    (3, 'Mechanical Keyboard', 149.99, 15, '2025-09-26', 'Asia'),
    (4, 'Monitor 27inch', 299.99, 8, '2025-09-26', 'North America'),
    (5, 'USB-C Hub', 79.99, 25, '2025-09-26', 'Europe');

-- Insert employee data
INSERT INTO my_ducklake.employees VALUES 
    (101, 'John', 'Smith', 'Engineering', 95000.00, '2023-01-15'),
    (102, 'Sarah', 'Johnson', 'Marketing', 68000.00, '2023-03-20'),
    (103, 'Mike', 'Davis', 'Engineering', 87000.00, '2023-02-10'),
    (104, 'Lisa', 'Wilson', 'Sales', 72000.00, '2023-04-05'),
    (105, 'Tom', 'Brown', 'HR', 63000.00, '2023-01-30'),
    (106, 'Amy', 'Taylor', 'Engineering', 92000.00, '2023-05-12'),
    (107, 'Chris', 'Anderson', 'Marketing', 65000.00, '2023-06-18');

-- Additional sales data for testing aggregations
INSERT INTO my_ducklake.sales_data VALUES 
    (6, 'Tablet 10inch', 399.99, 12, '2025-09-25', 'Asia'),
    (7, 'Smartphone', 799.99, 20, '2025-09-25', 'North America'),
    (8, 'Headphones', 199.99, 30, '2025-09-25', 'Europe'),
    (9, 'Smart Watch', 299.99, 18, '2025-09-24', 'Asia'),
    (10, 'Bluetooth Speaker', 89.99, 22, '2025-09-24', 'North America');
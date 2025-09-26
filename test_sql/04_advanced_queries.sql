-- Advanced Queries with JOINs and Window Functions
-- Test more complex SQL operations

-- Create a departments table for JOIN testing
CREATE TABLE my_ducklake.departments (
    dept_id INTEGER PRIMARY KEY,
    dept_name VARCHAR(50),
    manager_id INTEGER,
    budget DOUBLE
);

-- Insert department data
INSERT INTO my_ducklake.departments VALUES 
    (1, 'Engineering', 101, 500000.00),
    (2, 'Marketing', 102, 200000.00),
    (3, 'Sales', 104, 150000.00),
    (4, 'HR', 105, 100000.00);

-- JOIN query to test schema detection with multiple tables
SELECT 
    e.emp_id,
    CONCAT(e.first_name, ' ', e.last_name) as employee_name,
    e.department,
    e.salary,
    d.budget as dept_budget,
    ROUND((e.salary / d.budget) * 100, 2) as salary_budget_ratio
FROM my_ducklake.employees e
JOIN my_ducklake.departments d ON e.department = d.dept_name
ORDER BY salary_budget_ratio DESC;

-- Window function query
SELECT 
    product_name,
    region,
    price,
    quantity,
    (price * quantity) as total_value,
    ROW_NUMBER() OVER (PARTITION BY region ORDER BY (price * quantity) DESC) as rank_in_region,
    SUM(price * quantity) OVER (PARTITION BY region) as region_total
FROM my_ducklake.sales_data
ORDER BY region, rank_in_region;

-- Subquery with aggregation
SELECT 
    department,
    COUNT(*) as emp_count,
    AVG(salary) as avg_salary,
    (SELECT AVG(salary) FROM my_ducklake.employees) as company_avg_salary,
    AVG(salary) - (SELECT AVG(salary) FROM my_ducklake.employees) as salary_diff_from_avg
FROM my_ducklake.employees 
GROUP BY department
HAVING COUNT(*) > 1
ORDER BY avg_salary DESC;
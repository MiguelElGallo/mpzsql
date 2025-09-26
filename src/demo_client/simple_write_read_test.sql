-- Simple test to verify data write and read works
USE my_ducklake;

CREATE TABLE main.simple_test (
    id INTEGER,
    name VARCHAR(50)
);

INSERT INTO main.simple_test VALUES (1, 'Test Record');

SELECT * FROM main.simple_test;
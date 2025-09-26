#!/usr/bin/env python3
"""
Simple script to demonstrate write and read operations in my_ducklake database.
This uses the working execute_query method instead of file execution.
"""

import sys
import os

# Add the demo_client directory to path
sys.path.insert(0, os.path.dirname(__file__))

from client import MPZSQLFlightClient, read_server_config

def main():
    print("🎯 DuckLake Write/Read Demonstration")
    print("=" * 50)
    
    # Load configuration
    config = read_server_config()
    client = MPZSQLFlightClient(config)
    
    try:
        # Connect to server
        print("\n🔌 Connecting to server...")
        client.connect()
        print("✅ Connected successfully")
        
        # Use my_ducklake database
        print("\n📊 Switching to my_ducklake database...")
        client.execute_query("USE my_ducklake")
        
        # Create a demo table
        print("\n🏗️  Creating demo table...")
        client.execute_query("""
            DROP TABLE IF EXISTS main.demo_products
        """)
        
        client.execute_query("""
            CREATE TABLE main.demo_products (
                id INTEGER,
                product_name VARCHAR(100),
                price DECIMAL(10,2),
                category VARCHAR(50),
                in_stock BOOLEAN
            )
        """)
        
        # Insert data
        print("\n📝 Inserting test data...")
        client.execute_query("""
            INSERT INTO main.demo_products VALUES 
            (1, 'Laptop', 999.99, 'Electronics', true)
        """)
        
        client.execute_query("""
            INSERT INTO main.demo_products VALUES 
            (2, 'Coffee Maker', 79.50, 'Kitchen', true)
        """)
        
        client.execute_query("""
            INSERT INTO main.demo_products VALUES 
            (3, 'Office Chair', 199.99, 'Furniture', false)
        """)
        
        # Read data back
        print("\n🔍 Reading data back...")
        print("\n--- All Products ---")
        client.execute_query("SELECT * FROM main.demo_products")
        
        print("\n--- Product Count ---")
        client.execute_query("SELECT COUNT(*) as total_products FROM main.demo_products")
        
        print("\n--- Electronics Only ---")
        client.execute_query("SELECT * FROM main.demo_products WHERE category = 'Electronics'")
        
        print("\n--- In Stock Products ---")
        client.execute_query("SELECT * FROM main.demo_products WHERE in_stock = true")
        
        print("\n🎉 Write/Read demonstration completed successfully!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    
    finally:
        client.disconnect()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
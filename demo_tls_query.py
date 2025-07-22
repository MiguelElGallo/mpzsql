#!/usr/bin/env python3
"""
MPZSQL TLS + Authentication Query Demo
Demonstrates executing SQL queries over encrypted and authenticated connection
"""

import base64
import adbc_driver_flightsql.dbapi
from adbc_driver_flightsql import DatabaseOptions
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

def demo_tls_auth_query():
    """Demonstrate query execution with TLS + Authentication"""
    
    # Connection parameters
    host = "localhost"
    port = 8080
    username = "admin"
    password = "secret"
    
    console.print(Panel.fit(
        f"🔐 MPZSQL TLS + Authentication Query Demo\n\n"
        f"Host: {host}:{port}\n"
        f"User: {username}\n"
        f"Encryption: TLS\n"
        f"Authentication: Basic",
        title="🚀 Demo Configuration"
    ))
    
    try:
        # Prepare authentication header
        auth_header = base64.b64encode(f"{username}:{password}".encode()).decode()
        
        # Configure ADBC connection with TLS + Auth
        db_kwargs = {
            DatabaseOptions.AUTHORIZATION_HEADER.value: f"Basic {auth_header}",
            DatabaseOptions.TLS_SKIP_VERIFY.value: "true"  # For self-signed certs
        }
        
        console.print("🔗 Establishing TLS + Authentication connection...")
        
        # Connect to server
        connection = adbc_driver_flightsql.dbapi.connect(
            f"grpc+tls://{host}:{port}",
            db_kwargs=db_kwargs
        )
        
        console.print("✅ Connected successfully!")
        
        # Create cursor for query execution
        cursor = connection.cursor()
        
        # Demo queries to execute
        queries = [
            ("Simple Hello", "SELECT 'Hello from TLS + Auth!' as message"),
            ("Current Time", "SELECT CURRENT_TIMESTAMP as current_time"),
            ("Math Calculation", "SELECT 42 * 2 as answer, 'The meaning of life times two' as description"),
            ("Database Info", "SELECT 'MPZSQL with DuckDB backend' as database_system, '1.0' as version"),
            ("Sample Data", "SELECT 'Alice' as name, 25 as age UNION SELECT 'Bob', 30 UNION SELECT 'Charlie', 35")
        ]
        
        for query_name, sql in queries:
            console.print(f"\n🔍 Executing: {query_name}")
            console.print(f"SQL: [cyan]{sql}[/cyan]")
            
            try:
                # Execute query
                cursor.execute(sql)
                results = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
                
                # Display results in a table
                table = Table(title=f"Results: {query_name}")
                for col in columns:
                    table.add_column(col, style="cyan")
                
                for row in results:
                    table.add_row(*[str(cell) for cell in row])
                
                console.print(table)
                console.print("✅ Query executed successfully!")
                
            except Exception as e:
                console.print(f"❌ Query failed: {e}")
        
        # Close connection
        cursor.close()
        connection.close()
        console.print("\n📡 Disconnected from server")
        
        console.print(Panel.fit(
            "🎉 TLS + Authentication Query Demo Complete!\n\n"
            "✅ Encrypted connection established\n"
            "✅ Authentication successful\n"
            "✅ Queries executed over secure channel\n"
            "✅ Results retrieved successfully",
            title="🏆 Demo Results",
            style="green"
        ))
        
    except Exception as e:
        console.print(f"❌ Connection failed: {e}")
        console.print("\n💡 Make sure the TLS server is running with:")
        console.print("   ./start_server_tls.sh")

if __name__ == "__main__":
    demo_tls_auth_query()

# PostgreSQL Token Refresh Solution

## IMPORTANT NOTES
- **Azure Token Mode**: Tokens are only used when `PASSWORD = "AZURE"` in the configuration. This is a special flag indicating Azure authentication mode, not an actual password.
- **Token Refresh Scope**: Token validation and refresh should only be performed if `config.postgresql_password == "AZURE"`. Regular password authentication doesn't need token refresh.
- **DuckDB Secret Type**: The system uses DuckDB **anonymous secrets** (`CREATE SECRET (TYPE postgres, ...)` without a name) so DuckLake can automatically find them.

## Problem
The Azure PostgreSQL token expires after ~1.4 hours, but the server has no automatic refresh mechanism. When queries are executed with expired tokens, DuckLake cannot connect to PostgreSQL, causing query failures.

**CRITICAL**: The Python token refresh logic is never called during query execution because DuckDB uses its internal cached secret.

## Execution Flow Analysis
```text
1. Server Startup (if config.postgresql_password == "AZURE"):
   - get_azure_postgresql_token() called → Fresh JWT token obtained
   - CREATE SECRET (TYPE postgres, ..., PASSWORD='jwt_token') → Anonymous secret stored in DuckDB
   - _azure_credential_manager.set_duckdb_connection(con, config) → Enables automatic refresh
   - ATTACH 'ducklake:postgres:...' AS my_ducklake → DuckLake catalog attached

2. Query Execution (hours later):
   - Client sends: SELECT COUNT(*) FROM my_ducklake.basic_test;
   - FlightSQL → DuckDB backend → self.connection.execute(query)
   - DuckDB internally: Uses cached anonymous secret to connect to PostgreSQL
   - PostgreSQL: FATAL: The access token has expired (JWT expired 13+ hours ago)
   - Error propagates back → Query fails
   
3. The Problem:
   - get_azure_postgresql_token() is NEVER called during query execution
   - Python's token refresh logic (with 5-minute buffer) is bypassed entirely
   - DuckDB's anonymous secret remains stale until manually refreshed
   
4. Current Refresh Mechanism (_refresh_duckdb_secret):
   - Drops existing anonymous secret: DROP SECRET (TYPE postgres);
   - Creates new anonymous secret: CREATE SECRET (TYPE postgres, ..., PASSWORD='fresh_jwt');
   - But this is never triggered automatically during runtime!
```

## Root Cause
1. `schedule_token_refresh()` is a placeholder with no implementation
2. **Token refresh logic is NEVER called during query execution** - DuckDB uses its internal cached secret to connect to PostgreSQL, bypassing Python's token management entirely
3. **No token validation occurs at query time** - the system should check token validity before executing queries that require PostgreSQL access
4. DuckDB PostgreSQL anonymous secret remains stale with expired tokens

## Solution: Query-Time Token Validation and Refresh

Instead of complex background threads, implement a simple approach: **check token validity before each query execution and refresh if needed**.

### 1. Enhanced Query Execution with Token Check


```python
# In DuckDBBackend.execute_query() method
def execute_query(self, query: str, params: list | None = None) -> pa.Table:
    """Execute a SQL query using DuckDB and return the results as a PyArrow Table."""
    try:
        # Check token validity if this server requires Azure PostgreSQL tokens
        # (determined at boot time based on config.is_postgresql_enabled + config.postgresql_password == "AZURE")
        if self._needs_azure_token_refresh():
            self._ensure_fresh_postgresql_token()
            
        duckdb_log.info(f"Executing query: {query}")
        duckdb_logger.info("Executing DuckDB query", query=query)
        if params:
            duckdb_log.info(f"With parameters: {params}")
            duckdb_logger.info("Query parameters provided", params=params)
        fh.flush()  # Force flush before execution
        result = self.connection.execute(query, params).fetch_arrow_table()
        duckdb_log.info(f"Query result:\n{result}")
        duckdb_logger.info(
            "Query executed successfully",
            rows=len(result),
            columns=len(result.schema),
        )
        fh.flush()  # Force flush after execution
        return result
    except Exception as e:
        # Check if error is due to expired token and attempt recovery
        if self._is_token_expiry_error(str(e)):
            return self._retry_with_fresh_token(query, params)
        
        duckdb_log.error(f"Error executing query: {query}\n{e}")
        duckdb_logger.error("Query execution failed", query=query, error=str(e))
        fh.flush()  # Force flush on error
        raise

def _needs_azure_token_refresh(self) -> bool:
    """
    Check if this DuckLake server needs Azure token refresh.
    This is determined at boot time based on:
    1. config.is_postgresql_enabled (PostgreSQL + Azure Storage configured)
    2. config.postgresql_password == "AZURE" (Azure token authentication mode)
    """
    return (hasattr(self, 'config') and 
            self.config.is_postgresql_enabled and 
            self.config.postgresql_password == "AZURE")

def _is_token_expiry_error(self, error_msg: str) -> bool:
    """Check if error indicates token expiration."""
    token_expiry_indicators = [
        "access token has expired",
        "FATAL:  The access token has expired",
        "Acquire a new token and try again",
    ]
    return any(indicator.lower() in error_msg.lower() for indicator in token_expiry_indicators)

def _ensure_fresh_postgresql_token(self):
    """Ensure PostgreSQL token is fresh before query execution."""
    from mpzsql.cli import _azure_credential_manager
    
    # Only check if using Azure authentication
    if (hasattr(self, 'config') and 
        self.config.postgresql_password == "AZURE"):
        
        try:
            # Check if token needs refresh (existing logic with 5-minute buffer)
            old_token = _azure_credential_manager._cached_token
            _azure_credential_manager.get_postgresql_token()  # Uses existing refresh logic
            
            # If token changed, update DuckDB anonymous secret
            if old_token != _azure_credential_manager._cached_token:
                self._refresh_duckdb_anonymous_secret()
                
        except Exception as e:
            logger.warning(f"Failed to ensure fresh PostgreSQL token: {e}")
            # Don't fail the query - let DuckDB try with existing token

def _retry_with_fresh_token(self, query: str, params: list | None = None) -> pa.Table:
    """Retry query execution after refreshing the PostgreSQL token."""
    from mpzsql.cli import _azure_credential_manager
    
    logger.info("Detected token expiry error, attempting to refresh token and retry")
    
    try:
        # Force refresh the token
        _azure_credential_manager.get_postgresql_token(force_refresh=True)
        self._refresh_duckdb_anonymous_secret()
        
        logger.info("Token refreshed, retrying query execution")
        
        # Retry the query
        result = self.connection.execute(query, params).fetch_arrow_table()
        logger.info("Query retry successful after token refresh")
        return result
        
    except Exception as retry_error:
        logger.error(f"Query retry failed even after token refresh: {retry_error}")
        raise

def _refresh_duckdb_anonymous_secret(self):
    """Refresh the DuckDB anonymous PostgreSQL secret with fresh token."""
    from mpzsql.cli import _azure_credential_manager, create_duckdb_postgresql_secret_sql
    
    if not hasattr(self, 'config'):
        return
        
    try:
        logger.info("Refreshing DuckDB anonymous PostgreSQL secret")
        
        # Drop existing anonymous PostgreSQL secret
        try:
            drop_sql = "DROP SECRET (TYPE postgres);"
            self.connection.execute(drop_sql)
        except Exception:
            pass  # Ignore if secret doesn't exist
            
        # Create new anonymous secret with fresh token
        create_sql = create_duckdb_postgresql_secret_sql(
            host=self.config.postgresql_server,
            port=self.config.postgresql_port,
            database=self.config.postgresql_catalogdb,
            user=self.config.postgresql_user,
            password=_azure_credential_manager._cached_token,
        )
        
        self.connection.execute(create_sql).fetchall()
        logger.info("DuckDB anonymous PostgreSQL secret refreshed successfully")
        
    except Exception as e:
        logger.error(f"Failed to refresh DuckDB anonymous secret: {e}")
        raise
```

### 2. Server Integration

No background threads or complex startup logic needed! Simply ensure the DuckDB backend has access to the server configuration:

```python
# In cli.py when creating the backend
def main():
    # ... existing server setup ...
    
    # Create backend with config access for token validation
    if config.backend == "duckdb":
        backend = DuckDBBackend(config, con)
        # Pass config so backend can check postgresql_password == "AZURE"
    
    # Start server - no additional token refresh setup needed
    server = MPZSQLServer(config, con)
    server.start()
```

### 3. Implementation Advantages

**Simplicity**: 
- No background threads to manage
- No complex timing logic
- No startup/shutdown coordination

**Reliability**:
- Tokens are checked exactly when needed
- Immediate retry on token expiry errors
- No race conditions between background refresh and query execution

**Performance**:
- Token validation only happens for queries that need PostgreSQL access
- Existing 5-minute buffer logic prevents unnecessary token requests
- Minimal overhead for non-PostgreSQL queries

### 4. Query Flow with Token Validation

```text
1. Query arrives: SELECT COUNT(*) FROM my_ducklake.basic_test;
2. Check if this DuckLake server needs Azure tokens: _needs_azure_token_refresh() → True
   (Based on boot-time config: is_postgresql_enabled && postgresql_password == "AZURE")
3. Check token validity: _ensure_fresh_postgresql_token()
   - If token expires within 15 minutes → Get fresh token
   - If token changed → Update anonymous DuckDB secret
4. Execute query with fresh secret
5. If query fails with token error → _retry_with_fresh_token()
```

## Implementation Priority

1. **High Priority**: Implement boot-time configuration check in `DuckDBBackend._needs_azure_token_refresh()`
2. **Medium Priority**: Add token validation in `DuckDBBackend.execute_query()` for DuckLake servers
3. **Low Priority**: Enhance error detection patterns for different token expiry scenarios

## Testing

1. Start server with `PASSWORD="AZURE"` configuration
2. Wait for token to expire (or manually set a short-lived token)
3. Execute query against DuckLake: `SELECT COUNT(*) FROM my_ducklake.basic_test;`
4. Verify token refresh happens automatically before query execution
5. Verify DuckDB anonymous secret is updated with fresh token
6. Verify query succeeds without user intervention

## Monitoring

Add logging to track:

```markdown

- Token validation checks at query time
- Token refresh operations triggered by queries
- Anonymous DuckDB secret updates
- Query retry attempts after token expiry errors

## Summary

This solution implements **boot-time configuration-based token refresh** for DuckLake servers:

**Boot-time determination**: DuckLake servers are identified at startup by checking:

- `config.is_postgresql_enabled` (PostgreSQL server + Azure Storage configured) 
- `config.postgresql_password == "AZURE"` (Azure token authentication mode)

**Query-time validation**: When both conditions are met, all queries trigger token freshness checks before execution.

**Benefits**:

- No background threads to manage
- No complex query analysis logic required  
- DuckLake servers always get fresh tokens
- Tokens are checked exactly when needed
- Automatic error recovery if token expires during query

**Efficiency**: Token validation only happens for DuckLake servers requiring Azure authentication.

The implementation ensures that DuckLake servers maintain fresh PostgreSQL access tokens without requiring per-query pattern matching or background thread management.
```
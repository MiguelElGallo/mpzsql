"""
Simplified FlightSQL implementation that focuses on the essential JDBC workflow.

This implementation uses a more pragmatic approach, focusing on making JDBC clients work
by implementing the minimum viable FlightSQL protocol support.
"""

import logging
import uuid
from typing import Optional, Dict, Any
import pyarrow as pa
import pyarrow.flight as pf

logger = logging.getLogger(__name__)


class SimplifiedFlightSQL:
    """
    Simplified FlightSQL implementation that focuses on JDBC compatibility.
    
    Instead of trying to implement the full protobuf schema (which requires 
    exact knowledge of Arrow's internal protobuf definitions), this approach
    focuses on the data flow that JDBC clients expect.
    """
    
    def __init__(self, backend, config):
        self.backend = backend
        self.config = config
        self.prepared_statements: Dict[str, Dict[str, Any]] = {}
        
    def handle_action(self, action_type: str, action_body: bytes) -> pf.Result:
        """Handle FlightSQL actions with simplified but compatible responses."""
        
        logger.info(f"SimplifiedFlightSQL handling action: {action_type} ({len(action_body)} bytes)")
        
        if action_type == "CreatePreparedStatement":
            return self._handle_create_prepared_statement(action_body)
        elif action_type == "ClosePreparedStatement":
            return self._handle_close_prepared_statement(action_body)
        elif action_type == "CommandStatementQuery":
            return self._handle_statement_query(action_body)
        elif action_type == "CommandGetCatalogs":
            return self._handle_get_catalogs()
        elif action_type == "CommandGetSchemas":
            return self._handle_get_schemas()
        elif action_type == "CommandGetTables":
            return self._handle_get_tables()
        elif action_type == "CommandGetTableTypes":
            return self._handle_get_table_types()
        else:
            logger.debug(f"Unhandled action type: {action_type}")
            return pf.Result(pa.py_buffer(b''))
    
    def _extract_sql_from_bytes(self, data: bytes) -> Optional[str]:
        """Extract SQL string from various possible formats."""
        if not data:
            return None
        
        # Method 1: Try FlightSQL protobuf parsing first (for JDBC clients)
        try:
            from mpzsql.flightsql.protobuf import FlightSQLProtobuf
            sql = FlightSQLProtobuf.parse_command_statement_query(data)
            if sql:
                logger.debug(f"Extracted SQL via protobuf parsing: {sql}")
                return sql
                
            # Also try parsing as CreatePreparedStatement request
            sql = FlightSQLProtobuf.parse_create_prepared_statement_request(data)
            if sql:
                logger.debug(f"Extracted SQL via prepared statement parsing: {sql}")
                return sql
        except Exception as e:
            logger.debug(f"FlightSQL protobuf parsing failed: {e}")
            
        # Method 2: Direct UTF-8 decode (for simple Python clients)
        try:
            sql = data.decode('utf-8').strip()
            if sql and len(sql) > 3:  # Reasonable SQL length
                return sql
        except UnicodeDecodeError:
            pass
        
        # Method 3: Skip potential length prefixes and try decode
        for offset in [1, 2, 4, 8, 16]:
            if len(data) > offset:
                try:
                    sql = data[offset:].decode('utf-8', errors='ignore').strip()
                    # Look for SQL keywords
                    sql_upper = sql.upper()
                    if any(keyword in sql_upper for keyword in ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP']):
                        # Clean up the SQL
                        sql = ''.join(c for c in sql if ord(c) >= 32 or c in '\\t\\n\\r')
                        if len(sql) > 5:
                            return sql.strip()
                except Exception:
                    continue
                    
        # Method 4: Scan through the bytes looking for SQL patterns
        try:
            decoded = data.decode('utf-8', errors='replace')
            for keyword in ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP']:
                if keyword in decoded.upper():
                    # Find the start of the SQL
                    start_idx = decoded.upper().find(keyword)
                    if start_idx >= 0:
                        sql = decoded[start_idx:].strip()
                        # Clean up control characters
                        sql = ''.join(c for c in sql if ord(c) >= 32 or c in '\\t\\n\\r')
                        if len(sql) > len(keyword):
                            return sql
        except Exception:
            pass
            
        logger.debug(f"Could not extract SQL from {len(data)} bytes")
        return None
    
    def _handle_create_prepared_statement(self, action_body: bytes) -> pf.Result:
        """Handle CreatePreparedStatement - the key action for JDBC queries."""
        try:
            logger.info(f"CreatePreparedStatement called with {len(action_body)} bytes")
            
            # Extract SQL from the action body
            sql = self._extract_sql_from_bytes(action_body)
            
            if not sql:
                logger.error("Could not extract SQL from CreatePreparedStatement request")
                # Log the raw bytes for debugging
                logger.debug(f"Raw action body: {action_body[:200]}...")
                return pf.Result(pa.py_buffer(b''))
            
            # Generate prepared statement handle
            handle = f"stmt_{uuid.uuid4().hex[:16]}"
            
            # Get the schema for this SQL query
            try:
                schema = self.backend.get_statement_schema(sql)
                # Serialize the schema to bytes for the protobuf message
                import io
                schema_buffer = io.BytesIO()
                with pa.ipc.new_stream(schema_buffer, schema) as writer:
                    pass  # Just write the schema, no data
                dataset_schema_bytes = schema_buffer.getvalue()
            except Exception as e:
                logger.warning(f"Could not get schema for SQL '{sql}': {e}")
                # Use empty schema as fallback
                dataset_schema_bytes = None
            
            # Store the prepared statement
            self.prepared_statements[handle] = {
                'sql': sql,
                'schema': schema if 'schema' in locals() else None
            }
            
            logger.info(f"Created prepared statement {handle} for SQL: {sql}")
            
            # Create proper FlightSQL ActionCreatePreparedStatementResult protobuf response
            from mpzsql.flightsql.protobuf import FlightSQLProtobuf
            handle_bytes = handle.encode('utf-8')
            
            # For now, we'll omit parameter_schema (most queries don't have parameters)
            result_data = FlightSQLProtobuf.create_action_create_prepared_statement_result(
                prepared_statement_handle=handle_bytes,
                dataset_schema=dataset_schema_bytes,
                parameter_schema=None
            )
            
            logger.info(f"Returning {len(result_data)} bytes for prepared statement result")
            
            return pf.Result(pa.py_buffer(result_data))
            
        except Exception as e:
            logger.error(f"Error in CreatePreparedStatement: {e}")
            import traceback
            traceback.print_exc()
            return pf.Result(pa.py_buffer(b''))
    
    def _create_minimal_prepared_statement_result(self, handle_bytes: bytes) -> bytes:
        """
        Create a proper FlightSQL ActionCreatePreparedStatementResult protobuf message.
        
        Based on the Arrow FlightSQL specification, this should contain:
        - prepared_statement_handle (bytes)
        - dataset_schema (optional)
        - parameter_schema (optional)
        """
        try:
            # Create a proper protobuf message for ActionCreatePreparedStatementResult
            # According to the FlightSQL spec, this message has these fields:
            # - bytes prepared_statement_handle = 1;
            # - bytes dataset_schema = 2;            // optional
            # - bytes parameter_schema = 3;          // optional
            
            # Field 1: prepared_statement_handle (bytes, field number 1, wire type 2)
            field1_tag = (1 << 3) | 2  # field 1, wire type 2 (length-delimited)
            handle_length = len(handle_bytes)
            
            # Encode varint length
            def encode_varint(value):
                result = []
                while value > 127:
                    result.append((value & 127) | 128)
                    value >>= 7
                result.append(value & 127)
                return bytes(result)
            
            message = bytes([field1_tag]) + encode_varint(handle_length) + handle_bytes
            
            logger.debug(f"Created protobuf message: {message.hex()}")
            return message
            
        except Exception as e:
            logger.error(f"Error creating protobuf result: {e}")
            # Fallback to empty response
            return b''
    
    def _handle_close_prepared_statement(self, action_body: bytes) -> pf.Result:
        """Handle ClosePreparedStatement."""
        # Simple cleanup - remove old statements if we have too many
        if len(self.prepared_statements) > 100:
            handles_to_remove = list(self.prepared_statements.keys())[:50]
            for handle in handles_to_remove:
                del self.prepared_statements[handle]
        
        return pf.Result(pa.py_buffer(b''))
    
    def _handle_statement_query(self, action_body: bytes) -> pf.Result:
        """Handle direct statement query."""
        sql = self._extract_sql_from_bytes(action_body)
        if sql:
            # Return a simple response indicating the query was accepted
            return pf.Result(pa.py_buffer(b'query_accepted'))
        else:
            return pf.Result(pa.py_buffer(b''))
    
    def _handle_get_catalogs(self) -> pf.Result:
        """Handle catalog metadata request."""
        try:
            catalogs = ['main']  # Default catalog
            catalog_table = pa.table({'catalog_name': catalogs})
            
            import io
            buffer = io.BytesIO()
            with pa.ipc.new_stream(buffer, catalog_table.schema) as writer:
                writer.write_table(catalog_table)
            
            return pf.Result(pa.py_buffer(buffer.getvalue()))
        except Exception as e:
            logger.error(f"Error in get_catalogs: {e}")
            return pf.Result(pa.py_buffer(b''))
    
    def _handle_get_schemas(self) -> pf.Result:
        """Handle schema metadata request."""
        try:
            schemas_table = pa.table({
                'catalog_name': ['main'],
                'schema_name': ['main']
            })
            
            import io
            buffer = io.BytesIO()
            with pa.ipc.new_stream(buffer, schemas_table.schema) as writer:
                writer.write_table(schemas_table)
            
            return pf.Result(pa.py_buffer(buffer.getvalue()))
        except Exception as e:
            logger.error(f"Error in get_schemas: {e}")
            return pf.Result(pa.py_buffer(b''))
    
    def _handle_get_tables(self) -> pf.Result:
        """Handle table metadata request."""
        try:
            # Get tables from backend if available
            tables = []
            if hasattr(self.backend, 'get_tables'):
                try:
                    table_info = self.backend.get_tables()
                    for table in table_info:
                        if isinstance(table, tuple) and len(table) >= 3:
                            tables.append({
                                'catalog_name': table[0] or 'main',
                                'schema_name': table[1] or 'main',
                                'table_name': table[2],
                                'table_type': table[3] if len(table) > 3 else 'TABLE'
                            })
                except Exception as e:
                    logger.debug(f"Error getting tables from backend: {e}")
            
            # Create table metadata
            if tables:
                tables_table = pa.table({
                    'catalog_name': [t['catalog_name'] for t in tables],
                    'schema_name': [t['schema_name'] for t in tables],
                    'table_name': [t['table_name'] for t in tables],
                    'table_type': [t['table_type'] for t in tables]
                })
            else:
                # Empty table with correct schema
                tables_table = pa.table({
                    'catalog_name': pa.array([], type=pa.string()),
                    'schema_name': pa.array([], type=pa.string()),
                    'table_name': pa.array([], type=pa.string()),
                    'table_type': pa.array([], type=pa.string())
                })
            
            import io
            buffer = io.BytesIO()
            with pa.ipc.new_stream(buffer, tables_table.schema) as writer:
                writer.write_table(tables_table)
            
            return pf.Result(pa.py_buffer(buffer.getvalue()))
        except Exception as e:
            logger.error(f"Error in get_tables: {e}")
            return pf.Result(pa.py_buffer(b''))
    
    def _handle_get_table_types(self) -> pf.Result:
        """Handle table types metadata request."""
        try:
            table_types = ['TABLE', 'VIEW', 'SYSTEM TABLE']
            types_table = pa.table({'table_type': table_types})
            
            import io
            buffer = io.BytesIO()
            with pa.ipc.new_stream(buffer, types_table.schema) as writer:
                writer.write_table(types_table)
            
            return pf.Result(pa.py_buffer(buffer.getvalue()))
        except Exception as e:
            logger.error(f"Error in get_table_types: {e}")
            return pf.Result(pa.py_buffer(b''))
    
    def get_prepared_statements(self) -> Dict[str, Dict[str, Any]]:
        """Get the prepared statements dictionary for server integration."""
        return self.prepared_statements
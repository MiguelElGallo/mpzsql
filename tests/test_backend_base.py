"""
Comprehensive tests for MPZSQL database backend base interface.

Tests for mpzsql.backends.base module covering the abstract DatabaseBackend
interface and ensuring proper contract definition for backend implementations.
"""

import pytest
import pyarrow as pa
from abc import ABC

from mpzsql.backends.base import DatabaseBackend
from mpzsql.config import ServerConfig


class TestDatabaseBackendAbstractInterface:
    """Test the abstract interface definition of DatabaseBackend."""

    def test_is_abstract_base_class(self) -> None:
        """Test that DatabaseBackend is an abstract base class."""
        assert issubclass(DatabaseBackend, ABC)
        assert hasattr(DatabaseBackend, '__abstractmethods__')
        
        # Verify all expected methods are abstract
        expected_abstract_methods = {
            'execute_sql',
            'execute_query', 
            'execute_update',
            'get_statement_schema',
            'get_catalogs',
            'get_schemas',
            'get_tables',
            'get_sql_info',
            'get_db_schemas',
            'get_columns',
            'close'
        }
        
        assert DatabaseBackend.__abstractmethods__ == expected_abstract_methods

    def test_cannot_instantiate_abstract_class(self) -> None:
        """Test that DatabaseBackend cannot be instantiated directly."""
        config = ServerConfig(secret_key="test")
        
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            DatabaseBackend(config)  # type: ignore[abstract]  # Intentionally trying to instantiate abstract class

    def test_constructor_signature(self) -> None:
        """Test that the constructor has the correct signature."""
        # Create a concrete implementation to test constructor
        class ConcreteDatabaseBackend(DatabaseBackend):
            def execute_sql(self, sql: str) -> None:
                pass
            def execute_query(self, query: str, params: list | None = None) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
            def execute_update(self, query: str, params: list | None = None) -> int:
                return 0
            def get_statement_schema(self, query: str) -> pa.Schema:
                return pa.schema([])
            def get_catalogs(self) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
            def get_schemas(self, catalog: str | None = None) -> list[tuple[str, str]]:
                return []
            def get_tables(self, catalog: str | None = None, db_schema_filter_pattern: str | None = None,
                         table_name_filter_pattern: str | None = None, table_types: list[str] | None = None,
                         include_schema: bool = False) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
            def get_sql_info(self, info_codes: list[int]) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
            def get_db_schemas(self, catalog: str | None = None, db_schema_filter_pattern: str | None = None) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
            def get_columns(self, catalog: str | None = None, db_schema_filter_pattern: str | None = None,
                          table_name_filter_pattern: str | None = None, column_name_filter_pattern: str | None = None) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
            def close(self) -> None:
                pass
        
        config = ServerConfig(secret_key="test")
        backend = ConcreteDatabaseBackend(config)
        
        assert backend.config is config
        assert isinstance(backend.config, ServerConfig)


class TestDatabaseBackendMethodSignatures:
    """Test the method signatures of all abstract methods."""

    def test_execute_sql_signature(self) -> None:
        """Test execute_sql method signature."""
        method = DatabaseBackend.execute_sql
        
        # Check it's abstract
        assert hasattr(method, '__isabstractmethod__')
        assert method.__isabstractmethod__ is True
        
        # Check annotations (if available in Python version)
        if hasattr(method, '__annotations__'):
            annotations = method.__annotations__
            assert 'sql' in annotations
            assert annotations.get('return') is None or annotations.get('return') is type(None)

    def test_execute_query_signature(self) -> None:
        """Test execute_query method signature."""
        method = DatabaseBackend.execute_query
        
        assert hasattr(method, '__isabstractmethod__')
        assert method.__isabstractmethod__ is True
        
        # Check method can accept both positional and keyword arguments
        import inspect
        sig = inspect.signature(method)
        params = list(sig.parameters.keys())
        assert 'self' in params
        assert 'query' in params
        assert 'params' in params
        
        # Check params parameter has default None
        assert sig.parameters['params'].default is None

    def test_execute_update_signature(self) -> None:
        """Test execute_update method signature.""" 
        method = DatabaseBackend.execute_update
        
        assert hasattr(method, '__isabstractmethod__')
        assert method.__isabstractmethod__ is True
        
        import inspect
        sig = inspect.signature(method)
        params = list(sig.parameters.keys())
        assert 'self' in params
        assert 'query' in params
        assert 'params' in params
        
        # Check params parameter has default None
        assert sig.parameters['params'].default is None

    def test_get_statement_schema_signature(self) -> None:
        """Test get_statement_schema method signature."""
        method = DatabaseBackend.get_statement_schema
        
        assert hasattr(method, '__isabstractmethod__')
        assert method.__isabstractmethod__ is True
        
        import inspect
        sig = inspect.signature(method)
        params = list(sig.parameters.keys())
        assert 'self' in params
        assert 'query' in params

    def test_get_catalogs_signature(self) -> None:
        """Test get_catalogs method signature."""
        method = DatabaseBackend.get_catalogs
        
        assert hasattr(method, '__isabstractmethod__')
        assert method.__isabstractmethod__ is True
        
        import inspect
        sig = inspect.signature(method)
        params = list(sig.parameters.keys())
        assert 'self' in params
        # Should have no other required parameters
        assert len([p for p in sig.parameters.values() if p.default is inspect.Parameter.empty and p.name != 'self']) == 0

    def test_get_schemas_signature(self) -> None:
        """Test get_schemas method signature."""
        method = DatabaseBackend.get_schemas
        
        assert hasattr(method, '__isabstractmethod__')
        assert method.__isabstractmethod__ is True
        
        import inspect
        sig = inspect.signature(method)
        params = list(sig.parameters.keys())
        assert 'self' in params
        assert 'catalog' in params
        
        # Check catalog parameter has default None
        assert sig.parameters['catalog'].default is None

    def test_get_tables_signature(self) -> None:
        """Test get_tables method signature with all parameters."""
        method = DatabaseBackend.get_tables
        
        assert hasattr(method, '__isabstractmethod__')
        assert method.__isabstractmethod__ is True
        
        import inspect
        sig = inspect.signature(method)
        params = list(sig.parameters.keys())
        assert 'self' in params
        assert 'catalog' in params
        assert 'db_schema_filter_pattern' in params
        assert 'table_name_filter_pattern' in params
        assert 'table_types' in params
        assert 'include_schema' in params
        
        # Check default values
        assert sig.parameters['catalog'].default is None
        assert sig.parameters['db_schema_filter_pattern'].default is None
        assert sig.parameters['table_name_filter_pattern'].default is None
        assert sig.parameters['table_types'].default is None
        assert sig.parameters['include_schema'].default is False

    def test_get_sql_info_signature(self) -> None:
        """Test get_sql_info method signature."""
        method = DatabaseBackend.get_sql_info
        
        assert hasattr(method, '__isabstractmethod__')
        assert method.__isabstractmethod__ is True
        
        import inspect
        sig = inspect.signature(method)
        params = list(sig.parameters.keys())
        assert 'self' in params
        assert 'info_codes' in params

    def test_get_db_schemas_signature(self) -> None:
        """Test get_db_schemas method signature."""
        method = DatabaseBackend.get_db_schemas
        
        assert hasattr(method, '__isabstractmethod__')
        assert method.__isabstractmethod__ is True
        
        import inspect
        sig = inspect.signature(method)
        params = list(sig.parameters.keys())
        assert 'self' in params
        assert 'catalog' in params
        assert 'db_schema_filter_pattern' in params
        
        # Check default values
        assert sig.parameters['catalog'].default is None
        assert sig.parameters['db_schema_filter_pattern'].default is None

    def test_get_columns_signature(self) -> None:
        """Test get_columns method signature."""
        method = DatabaseBackend.get_columns
        
        assert hasattr(method, '__isabstractmethod__')
        assert method.__isabstractmethod__ is True
        
        import inspect
        sig = inspect.signature(method)
        params = list(sig.parameters.keys())
        assert 'self' in params
        assert 'catalog' in params
        assert 'db_schema_filter_pattern' in params
        assert 'table_name_filter_pattern' in params
        assert 'column_name_filter_pattern' in params
        
        # Check default values
        assert sig.parameters['catalog'].default is None
        assert sig.parameters['db_schema_filter_pattern'].default is None
        assert sig.parameters['table_name_filter_pattern'].default is None
        assert sig.parameters['column_name_filter_pattern'].default is None

    def test_close_signature(self) -> None:
        """Test close method signature."""
        method = DatabaseBackend.close
        
        assert hasattr(method, '__isabstractmethod__')
        assert method.__isabstractmethod__ is True
        
        import inspect
        sig = inspect.signature(method)
        params = list(sig.parameters.keys())
        assert 'self' in params
        # Should have no other parameters
        assert len([p for p in sig.parameters.values() if p.default is inspect.Parameter.empty and p.name != 'self']) == 0


class TestDatabaseBackendImplementationContract:
    """Test the implementation contract requirements."""

    def test_minimal_concrete_implementation(self) -> None:
        """Test that a minimal concrete implementation can be created."""
        class MinimalBackend(DatabaseBackend):
            def execute_sql(self, sql: str) -> None:
                pass
                
            def execute_query(self, query: str, params: list | None = None) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
                
            def execute_update(self, query: str, params: list | None = None) -> int:
                return 0
                
            def get_statement_schema(self, query: str) -> pa.Schema:
                return pa.schema([])
                
            def get_catalogs(self) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
                
            def get_schemas(self, catalog: str | None = None) -> list[tuple[str, str]]:
                return []
                
            def get_tables(self, catalog: str | None = None, db_schema_filter_pattern: str | None = None,
                         table_name_filter_pattern: str | None = None, table_types: list[str] | None = None,
                         include_schema: bool = False) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
                
            def get_sql_info(self, info_codes: list[int]) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
                
            def get_db_schemas(self, catalog: str | None = None, db_schema_filter_pattern: str | None = None) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
                
            def get_columns(self, catalog: str | None = None, db_schema_filter_pattern: str | None = None,
                          table_name_filter_pattern: str | None = None, column_name_filter_pattern: str | None = None) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
                
            def close(self) -> None:
                pass

        config = ServerConfig(secret_key="test")
        backend = MinimalBackend(config)
        
        # Should be able to create and use the backend
        assert isinstance(backend, DatabaseBackend)
        assert backend.config is config
        
        # All methods should be callable
        backend.execute_sql("SELECT 1")
        result = backend.execute_query("SELECT 1")
        assert isinstance(result, pa.Table)
        
        count = backend.execute_update("INSERT INTO test VALUES (1)")
        assert isinstance(count, int)
        
        schema = backend.get_statement_schema("SELECT 1")
        assert isinstance(schema, pa.Schema)
        
        catalogs = backend.get_catalogs()
        assert isinstance(catalogs, pa.Table)
        
        schemas = backend.get_schemas()
        assert isinstance(schemas, list)
        
        tables = backend.get_tables()
        assert isinstance(tables, pa.Table)
        
        sql_info = backend.get_sql_info([])
        assert isinstance(sql_info, pa.Table)
        
        db_schemas = backend.get_db_schemas()
        assert isinstance(db_schemas, pa.Table)
        
        columns = backend.get_columns()
        assert isinstance(columns, pa.Table)
        
        backend.close()  # Should not raise

    def test_partial_implementation_fails(self) -> None:
        """Test that partial implementations cannot be instantiated."""
        class PartialBackend(DatabaseBackend):
            def execute_sql(self, sql: str) -> None:
                pass
            # Missing all other required methods

        config = ServerConfig(secret_key="test")
        
        with pytest.raises(TypeError):
            PartialBackend(config)

    def test_method_signature_mismatch_still_works(self) -> None:
        """Test that implementations with different signatures still work (Python flexibility)."""
        class FlexibleBackend(DatabaseBackend):
            def execute_sql(self, sql: str) -> None:
                pass
                
            def execute_query(self, query: str, params: list | None = None, **kwargs) -> pa.Table:
                # Additional kwargs allowed
                return pa.Table.from_arrays([], names=[])
                
            def execute_update(self, query: str, params: list | None = None) -> int:
                return 0
                
            def get_statement_schema(self, query: str) -> pa.Schema:
                return pa.schema([])
                
            def get_catalogs(self) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
                
            def get_schemas(self, catalog: str | None = None) -> list[tuple[str, str]]:
                return []
                
            def get_tables(self, catalog: str | None = None, db_schema_filter_pattern: str | None = None,
                         table_name_filter_pattern: str | None = None, table_types: list[str] | None = None,
                         include_schema: bool = False, **extra) -> pa.Table:
                # Additional parameters allowed
                return pa.Table.from_arrays([], names=[])
                
            def get_sql_info(self, info_codes: list[int]) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
                
            def get_db_schemas(self, catalog: str | None = None, db_schema_filter_pattern: str | None = None) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
                
            def get_columns(self, catalog: str | None = None, db_schema_filter_pattern: str | None = None,
                          table_name_filter_pattern: str | None = None, column_name_filter_pattern: str | None = None) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
                
            def close(self) -> None:
                pass

        config = ServerConfig(secret_key="test")
        backend = FlexibleBackend(config)
        
        # Should work with extra parameters
        result = backend.execute_query("SELECT 1", None, extra_param="value")
        assert isinstance(result, pa.Table)
        
        tables = backend.get_tables(extra_filter="additional")
        assert isinstance(tables, pa.Table)


class TestDatabaseBackendInheritance:
    """Test inheritance behavior and subclass requirements."""

    def test_subclass_detection(self) -> None:
        """Test that concrete implementations are proper subclasses."""
        class ConcreteBackend(DatabaseBackend):
            def execute_sql(self, sql: str) -> None: pass
            def execute_query(self, query: str, params: list | None = None) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
            def execute_update(self, query: str, params: list | None = None) -> int: return 0
            def get_statement_schema(self, query: str) -> pa.Schema: return pa.schema([])
            def get_catalogs(self) -> pa.Table: return pa.Table.from_arrays([], names=[])
            def get_schemas(self, catalog: str | None = None) -> list[tuple[str, str]]: return []
            def get_tables(self, catalog: str | None = None, db_schema_filter_pattern: str | None = None,
                         table_name_filter_pattern: str | None = None, table_types: list[str] | None = None,
                         include_schema: bool = False) -> pa.Table: return pa.Table.from_arrays([], names=[])
            def get_sql_info(self, info_codes: list[int]) -> pa.Table: return pa.Table.from_arrays([], names=[])
            def get_db_schemas(self, catalog: str | None = None, db_schema_filter_pattern: str | None = None) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
            def get_columns(self, catalog: str | None = None, db_schema_filter_pattern: str | None = None,
                          table_name_filter_pattern: str | None = None, column_name_filter_pattern: str | None = None) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
            def close(self) -> None: pass

        assert issubclass(ConcreteBackend, DatabaseBackend)
        assert issubclass(ConcreteBackend, ABC)
        
        config = ServerConfig(secret_key="test")
        backend = ConcreteBackend(config)
        assert isinstance(backend, DatabaseBackend)
        assert isinstance(backend, ConcreteBackend)

    def test_multiple_inheritance_possible(self) -> None:
        """Test that multiple inheritance with DatabaseBackend works."""
        class SomeMixin:
            def helper_method(self) -> None:
                return "helper"

        class MultiInheritanceBackend(DatabaseBackend, SomeMixin):
            def execute_sql(self, sql: str) -> None: pass
            def execute_query(self, query: str, params: list | None = None) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
            def execute_update(self, query: str, params: list | None = None) -> int: return 0
            def get_statement_schema(self, query: str) -> pa.Schema: return pa.schema([])
            def get_catalogs(self) -> pa.Table: return pa.Table.from_arrays([], names=[])
            def get_schemas(self, catalog: str | None = None) -> list[tuple[str, str]]: return []
            def get_tables(self, catalog: str | None = None, db_schema_filter_pattern: str | None = None,
                         table_name_filter_pattern: str | None = None, table_types: list[str] | None = None,
                         include_schema: bool = False) -> pa.Table: return pa.Table.from_arrays([], names=[])
            def get_sql_info(self, info_codes: list[int]) -> pa.Table: return pa.Table.from_arrays([], names=[])
            def get_db_schemas(self, catalog: str | None = None, db_schema_filter_pattern: str | None = None) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
            def get_columns(self, catalog: str | None = None, db_schema_filter_pattern: str | None = None,
                          table_name_filter_pattern: str | None = None, column_name_filter_pattern: str | None = None) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
            def close(self) -> None: pass

        config = ServerConfig(secret_key="test")
        backend = MultiInheritanceBackend(config)
        
        assert isinstance(backend, DatabaseBackend)
        assert isinstance(backend, SomeMixin)
        assert backend.helper_method() == "helper"

    def test_abstract_method_override_detection(self) -> None:
        """Test detection of which abstract methods are overridden."""
        class PartialBackend(DatabaseBackend):
            def execute_sql(self, sql: str) -> None:
                pass
            
            def close(self) -> None:
                pass
            
            # Missing other methods

        # Check that only some methods are implemented
        remaining_abstract = PartialBackend.__abstractmethods__
        assert 'execute_sql' not in remaining_abstract
        assert 'close' not in remaining_abstract
        assert 'execute_query' in remaining_abstract
        assert 'get_catalogs' in remaining_abstract


class TestDatabaseBackendDocumentation:
    """Test that the interface is properly documented."""

    def test_class_has_docstring(self) -> None:
        """Test that DatabaseBackend has a docstring."""
        assert DatabaseBackend.__doc__ is not None
        assert len(DatabaseBackend.__doc__.strip()) > 0
        assert "Abstract base class" in DatabaseBackend.__doc__

    def test_constructor_has_docstring(self) -> None:
        """Test that __init__ method has a docstring."""
        assert DatabaseBackend.__init__.__doc__ is not None
        assert len(DatabaseBackend.__init__.__doc__.strip()) > 0

    def test_all_abstract_methods_have_docstrings(self) -> None:
        """Test that all abstract methods have docstrings."""
        abstract_methods = DatabaseBackend.__abstractmethods__
        
        for method_name in abstract_methods:
            method = getattr(DatabaseBackend, method_name)
            assert method.__doc__ is not None, f"Method {method_name} missing docstring"
            assert len(method.__doc__.strip()) > 0, f"Method {method_name} has empty docstring"

    def test_method_docstrings_describe_purpose(self) -> None:
        """Test that method docstrings describe their purpose."""
        # Sample a few key methods
        assert "Execute SQL commands" in DatabaseBackend.execute_sql.__doc__
        assert "Execute a query" in DatabaseBackend.execute_query.__doc__
        assert "Arrow" in DatabaseBackend.execute_query.__doc__
        assert "UPDATE, INSERT or DELETE" in DatabaseBackend.execute_update.__doc__
        assert "schema" in DatabaseBackend.get_statement_schema.__doc__.lower()
        assert "catalogs" in DatabaseBackend.get_catalogs.__doc__.lower()
        assert "Close" in DatabaseBackend.close.__doc__


class TestDatabaseBackendEdgeCases:
    """Test edge cases and error conditions."""

    def test_config_parameter_required(self) -> None:
        """Test that config parameter is required in constructor."""
        class TestBackend(DatabaseBackend):
            def execute_sql(self, sql: str) -> None: pass
            def execute_query(self, query: str, params: list | None = None) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
            def execute_update(self, query: str, params: list | None = None) -> int: return 0
            def get_statement_schema(self, query: str) -> pa.Schema: return pa.schema([])
            def get_catalogs(self) -> pa.Table: return pa.Table.from_arrays([], names=[])
            def get_schemas(self, catalog: str | None = None) -> list[tuple[str, str]]: return []
            def get_tables(self, catalog: str | None = None, db_schema_filter_pattern: str | None = None,
                         table_name_filter_pattern: str | None = None, table_types: list[str] | None = None,
                         include_schema: bool = False) -> pa.Table: return pa.Table.from_arrays([], names=[])
            def get_sql_info(self, info_codes: list[int]) -> pa.Table: return pa.Table.from_arrays([], names=[])
            def get_db_schemas(self, catalog: str | None = None, db_schema_filter_pattern: str | None = None) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
            def get_columns(self, catalog: str | None = None, db_schema_filter_pattern: str | None = None,
                          table_name_filter_pattern: str | None = None, column_name_filter_pattern: str | None = None) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
            def close(self) -> None: pass

        # Should require config parameter
        with pytest.raises(TypeError):
            TestBackend()  # type: ignore[call-arg]  # Intentionally missing required parameter

    def test_config_attribute_accessible(self) -> None:
        """Test that config attribute is accessible after initialization."""
        class TestBackend(DatabaseBackend):
            def execute_sql(self, sql: str) -> None: pass
            def execute_query(self, query: str, params: list | None = None) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
            def execute_update(self, query: str, params: list | None = None) -> int: return 0
            def get_statement_schema(self, query: str) -> pa.Schema: return pa.schema([])
            def get_catalogs(self) -> pa.Table: return pa.Table.from_arrays([], names=[])
            def get_schemas(self, catalog: str | None = None) -> list[tuple[str, str]]: return []
            def get_tables(self, catalog: str | None = None, db_schema_filter_pattern: str | None = None,
                         table_name_filter_pattern: str | None = None, table_types: list[str] | None = None,
                         include_schema: bool = False) -> pa.Table: return pa.Table.from_arrays([], names=[])
            def get_sql_info(self, info_codes: list[int]) -> pa.Table: return pa.Table.from_arrays([], names=[])
            def get_db_schemas(self, catalog: str | None = None, db_schema_filter_pattern: str | None = None) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
            def get_columns(self, catalog: str | None = None, db_schema_filter_pattern: str | None = None,
                          table_name_filter_pattern: str | None = None, column_name_filter_pattern: str | None = None) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
            def close(self) -> None: pass

        config = ServerConfig(secret_key="test", backend="duckdb")
        backend = TestBackend(config)
        
        assert hasattr(backend, 'config')
        assert backend.config is config
        assert backend.config.secret_key == "test"
        assert backend.config.backend == "duckdb"

    def test_subclass_can_override_constructor(self) -> None:
        """Test that subclasses can override the constructor."""
        class CustomBackend(DatabaseBackend):
            def __init__(self, config: ServerConfig, custom_param: str = "default"):
                super().__init__(config)
                self.custom_param = custom_param
            
            def execute_sql(self, sql: str) -> None: pass
            def execute_query(self, query: str, params: list | None = None) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
            def execute_update(self, query: str, params: list | None = None) -> int: return 0
            def get_statement_schema(self, query: str) -> pa.Schema: return pa.schema([])
            def get_catalogs(self) -> pa.Table: return pa.Table.from_arrays([], names=[])
            def get_schemas(self, catalog: str | None = None) -> list[tuple[str, str]]: return []
            def get_tables(self, catalog: str | None = None, db_schema_filter_pattern: str | None = None,
                         table_name_filter_pattern: str | None = None, table_types: list[str] | None = None,
                         include_schema: bool = False) -> pa.Table: return pa.Table.from_arrays([], names=[])
            def get_sql_info(self, info_codes: list[int]) -> pa.Table: return pa.Table.from_arrays([], names=[])
            def get_db_schemas(self, catalog: str | None = None, db_schema_filter_pattern: str | None = None) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
            def get_columns(self, catalog: str | None = None, db_schema_filter_pattern: str | None = None,
                          table_name_filter_pattern: str | None = None, column_name_filter_pattern: str | None = None) -> pa.Table:
                return pa.Table.from_arrays([], names=[])
            def close(self) -> None: pass

        config = ServerConfig(secret_key="test")
        
        # Test with default custom parameter
        backend1 = CustomBackend(config)
        assert backend1.config is config
        assert backend1.custom_param == "default"
        
        # Test with custom parameter
        backend2 = CustomBackend(config, "custom_value")
        assert backend2.config is config
        assert backend2.custom_param == "custom_value"
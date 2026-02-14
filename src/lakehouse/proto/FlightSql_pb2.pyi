from google.protobuf import descriptor_pb2 as _descriptor_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SqlInfo(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    FLIGHT_SQL_SERVER_NAME: _ClassVar[SqlInfo]
    FLIGHT_SQL_SERVER_VERSION: _ClassVar[SqlInfo]
    FLIGHT_SQL_SERVER_ARROW_VERSION: _ClassVar[SqlInfo]
    FLIGHT_SQL_SERVER_READ_ONLY: _ClassVar[SqlInfo]
    FLIGHT_SQL_SERVER_SQL: _ClassVar[SqlInfo]
    FLIGHT_SQL_SERVER_SUBSTRAIT: _ClassVar[SqlInfo]
    FLIGHT_SQL_SERVER_SUBSTRAIT_MIN_VERSION: _ClassVar[SqlInfo]
    FLIGHT_SQL_SERVER_SUBSTRAIT_MAX_VERSION: _ClassVar[SqlInfo]
    FLIGHT_SQL_SERVER_TRANSACTION: _ClassVar[SqlInfo]
    FLIGHT_SQL_SERVER_CANCEL: _ClassVar[SqlInfo]
    FLIGHT_SQL_SERVER_BULK_INGESTION: _ClassVar[SqlInfo]
    FLIGHT_SQL_SERVER_INGEST_TRANSACTIONS_SUPPORTED: _ClassVar[SqlInfo]
    FLIGHT_SQL_SERVER_STATEMENT_TIMEOUT: _ClassVar[SqlInfo]
    FLIGHT_SQL_SERVER_TRANSACTION_TIMEOUT: _ClassVar[SqlInfo]
    SQL_DDL_CATALOG: _ClassVar[SqlInfo]
    SQL_DDL_SCHEMA: _ClassVar[SqlInfo]
    SQL_DDL_TABLE: _ClassVar[SqlInfo]
    SQL_IDENTIFIER_CASE: _ClassVar[SqlInfo]
    SQL_IDENTIFIER_QUOTE_CHAR: _ClassVar[SqlInfo]
    SQL_QUOTED_IDENTIFIER_CASE: _ClassVar[SqlInfo]
    SQL_ALL_TABLES_ARE_SELECTABLE: _ClassVar[SqlInfo]
    SQL_NULL_ORDERING: _ClassVar[SqlInfo]
    SQL_KEYWORDS: _ClassVar[SqlInfo]
    SQL_NUMERIC_FUNCTIONS: _ClassVar[SqlInfo]
    SQL_STRING_FUNCTIONS: _ClassVar[SqlInfo]
    SQL_SYSTEM_FUNCTIONS: _ClassVar[SqlInfo]
    SQL_DATETIME_FUNCTIONS: _ClassVar[SqlInfo]
    SQL_SEARCH_STRING_ESCAPE: _ClassVar[SqlInfo]
    SQL_EXTRA_NAME_CHARACTERS: _ClassVar[SqlInfo]
    SQL_SUPPORTS_COLUMN_ALIASING: _ClassVar[SqlInfo]
    SQL_NULL_PLUS_NULL_IS_NULL: _ClassVar[SqlInfo]
    SQL_SUPPORTS_CONVERT: _ClassVar[SqlInfo]
    SQL_SUPPORTS_TABLE_CORRELATION_NAMES: _ClassVar[SqlInfo]
    SQL_SUPPORTS_DIFFERENT_TABLE_CORRELATION_NAMES: _ClassVar[SqlInfo]
    SQL_SUPPORTS_EXPRESSIONS_IN_ORDER_BY: _ClassVar[SqlInfo]
    SQL_SUPPORTS_ORDER_BY_UNRELATED: _ClassVar[SqlInfo]
    SQL_SUPPORTED_GROUP_BY: _ClassVar[SqlInfo]
    SQL_SUPPORTS_LIKE_ESCAPE_CLAUSE: _ClassVar[SqlInfo]
    SQL_SUPPORTS_NON_NULLABLE_COLUMNS: _ClassVar[SqlInfo]
    SQL_SUPPORTED_GRAMMAR: _ClassVar[SqlInfo]
    SQL_ANSI92_SUPPORTED_LEVEL: _ClassVar[SqlInfo]
    SQL_SUPPORTS_INTEGRITY_ENHANCEMENT_FACILITY: _ClassVar[SqlInfo]
    SQL_OUTER_JOINS_SUPPORT_LEVEL: _ClassVar[SqlInfo]
    SQL_SCHEMA_TERM: _ClassVar[SqlInfo]
    SQL_PROCEDURE_TERM: _ClassVar[SqlInfo]
    SQL_CATALOG_TERM: _ClassVar[SqlInfo]
    SQL_CATALOG_AT_START: _ClassVar[SqlInfo]
    SQL_SCHEMAS_SUPPORTED_ACTIONS: _ClassVar[SqlInfo]
    SQL_CATALOGS_SUPPORTED_ACTIONS: _ClassVar[SqlInfo]
    SQL_SUPPORTED_POSITIONED_COMMANDS: _ClassVar[SqlInfo]
    SQL_SELECT_FOR_UPDATE_SUPPORTED: _ClassVar[SqlInfo]
    SQL_STORED_PROCEDURES_SUPPORTED: _ClassVar[SqlInfo]
    SQL_SUPPORTED_SUBQUERIES: _ClassVar[SqlInfo]
    SQL_CORRELATED_SUBQUERIES_SUPPORTED: _ClassVar[SqlInfo]
    SQL_SUPPORTED_UNIONS: _ClassVar[SqlInfo]
    SQL_MAX_BINARY_LITERAL_LENGTH: _ClassVar[SqlInfo]
    SQL_MAX_CHAR_LITERAL_LENGTH: _ClassVar[SqlInfo]
    SQL_MAX_COLUMN_NAME_LENGTH: _ClassVar[SqlInfo]
    SQL_MAX_COLUMNS_IN_GROUP_BY: _ClassVar[SqlInfo]
    SQL_MAX_COLUMNS_IN_INDEX: _ClassVar[SqlInfo]
    SQL_MAX_COLUMNS_IN_ORDER_BY: _ClassVar[SqlInfo]
    SQL_MAX_COLUMNS_IN_SELECT: _ClassVar[SqlInfo]
    SQL_MAX_COLUMNS_IN_TABLE: _ClassVar[SqlInfo]
    SQL_MAX_CONNECTIONS: _ClassVar[SqlInfo]
    SQL_MAX_CURSOR_NAME_LENGTH: _ClassVar[SqlInfo]
    SQL_MAX_INDEX_LENGTH: _ClassVar[SqlInfo]
    SQL_DB_SCHEMA_NAME_LENGTH: _ClassVar[SqlInfo]
    SQL_MAX_PROCEDURE_NAME_LENGTH: _ClassVar[SqlInfo]
    SQL_MAX_CATALOG_NAME_LENGTH: _ClassVar[SqlInfo]
    SQL_MAX_ROW_SIZE: _ClassVar[SqlInfo]
    SQL_MAX_ROW_SIZE_INCLUDES_BLOBS: _ClassVar[SqlInfo]
    SQL_MAX_STATEMENT_LENGTH: _ClassVar[SqlInfo]
    SQL_MAX_STATEMENTS: _ClassVar[SqlInfo]
    SQL_MAX_TABLE_NAME_LENGTH: _ClassVar[SqlInfo]
    SQL_MAX_TABLES_IN_SELECT: _ClassVar[SqlInfo]
    SQL_MAX_USERNAME_LENGTH: _ClassVar[SqlInfo]
    SQL_DEFAULT_TRANSACTION_ISOLATION: _ClassVar[SqlInfo]
    SQL_TRANSACTIONS_SUPPORTED: _ClassVar[SqlInfo]
    SQL_SUPPORTED_TRANSACTIONS_ISOLATION_LEVELS: _ClassVar[SqlInfo]
    SQL_DATA_DEFINITION_CAUSES_TRANSACTION_COMMIT: _ClassVar[SqlInfo]
    SQL_DATA_DEFINITIONS_IN_TRANSACTIONS_IGNORED: _ClassVar[SqlInfo]
    SQL_SUPPORTED_RESULT_SET_TYPES: _ClassVar[SqlInfo]
    SQL_SUPPORTED_CONCURRENCIES_FOR_RESULT_SET_UNSPECIFIED: _ClassVar[SqlInfo]
    SQL_SUPPORTED_CONCURRENCIES_FOR_RESULT_SET_FORWARD_ONLY: _ClassVar[SqlInfo]
    SQL_SUPPORTED_CONCURRENCIES_FOR_RESULT_SET_SCROLL_SENSITIVE: _ClassVar[SqlInfo]
    SQL_SUPPORTED_CONCURRENCIES_FOR_RESULT_SET_SCROLL_INSENSITIVE: _ClassVar[SqlInfo]
    SQL_BATCH_UPDATES_SUPPORTED: _ClassVar[SqlInfo]
    SQL_SAVEPOINTS_SUPPORTED: _ClassVar[SqlInfo]
    SQL_NAMED_PARAMETERS_SUPPORTED: _ClassVar[SqlInfo]
    SQL_LOCATORS_UPDATE_COPY: _ClassVar[SqlInfo]
    SQL_STORED_FUNCTIONS_USING_CALL_SYNTAX_SUPPORTED: _ClassVar[SqlInfo]

class SqlSupportedTransaction(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SQL_SUPPORTED_TRANSACTION_NONE: _ClassVar[SqlSupportedTransaction]
    SQL_SUPPORTED_TRANSACTION_TRANSACTION: _ClassVar[SqlSupportedTransaction]
    SQL_SUPPORTED_TRANSACTION_SAVEPOINT: _ClassVar[SqlSupportedTransaction]

class SqlSupportedCaseSensitivity(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SQL_CASE_SENSITIVITY_UNKNOWN: _ClassVar[SqlSupportedCaseSensitivity]
    SQL_CASE_SENSITIVITY_CASE_INSENSITIVE: _ClassVar[SqlSupportedCaseSensitivity]
    SQL_CASE_SENSITIVITY_UPPERCASE: _ClassVar[SqlSupportedCaseSensitivity]
    SQL_CASE_SENSITIVITY_LOWERCASE: _ClassVar[SqlSupportedCaseSensitivity]

class SqlNullOrdering(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SQL_NULLS_SORTED_HIGH: _ClassVar[SqlNullOrdering]
    SQL_NULLS_SORTED_LOW: _ClassVar[SqlNullOrdering]
    SQL_NULLS_SORTED_AT_START: _ClassVar[SqlNullOrdering]
    SQL_NULLS_SORTED_AT_END: _ClassVar[SqlNullOrdering]

class SupportedSqlGrammar(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SQL_MINIMUM_GRAMMAR: _ClassVar[SupportedSqlGrammar]
    SQL_CORE_GRAMMAR: _ClassVar[SupportedSqlGrammar]
    SQL_EXTENDED_GRAMMAR: _ClassVar[SupportedSqlGrammar]

class SupportedAnsi92SqlGrammarLevel(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ANSI92_ENTRY_SQL: _ClassVar[SupportedAnsi92SqlGrammarLevel]
    ANSI92_INTERMEDIATE_SQL: _ClassVar[SupportedAnsi92SqlGrammarLevel]
    ANSI92_FULL_SQL: _ClassVar[SupportedAnsi92SqlGrammarLevel]

class SqlOuterJoinsSupportLevel(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SQL_JOINS_UNSUPPORTED: _ClassVar[SqlOuterJoinsSupportLevel]
    SQL_LIMITED_OUTER_JOINS: _ClassVar[SqlOuterJoinsSupportLevel]
    SQL_FULL_OUTER_JOINS: _ClassVar[SqlOuterJoinsSupportLevel]

class SqlSupportedGroupBy(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SQL_GROUP_BY_UNRELATED: _ClassVar[SqlSupportedGroupBy]
    SQL_GROUP_BY_BEYOND_SELECT: _ClassVar[SqlSupportedGroupBy]

class SqlSupportedElementActions(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SQL_ELEMENT_IN_PROCEDURE_CALLS: _ClassVar[SqlSupportedElementActions]
    SQL_ELEMENT_IN_INDEX_DEFINITIONS: _ClassVar[SqlSupportedElementActions]
    SQL_ELEMENT_IN_PRIVILEGE_DEFINITIONS: _ClassVar[SqlSupportedElementActions]

class SqlSupportedPositionedCommands(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SQL_POSITIONED_DELETE: _ClassVar[SqlSupportedPositionedCommands]
    SQL_POSITIONED_UPDATE: _ClassVar[SqlSupportedPositionedCommands]

class SqlSupportedSubqueries(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SQL_SUBQUERIES_IN_COMPARISONS: _ClassVar[SqlSupportedSubqueries]
    SQL_SUBQUERIES_IN_EXISTS: _ClassVar[SqlSupportedSubqueries]
    SQL_SUBQUERIES_IN_INS: _ClassVar[SqlSupportedSubqueries]
    SQL_SUBQUERIES_IN_QUANTIFIEDS: _ClassVar[SqlSupportedSubqueries]

class SqlSupportedUnions(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SQL_UNION: _ClassVar[SqlSupportedUnions]
    SQL_UNION_ALL: _ClassVar[SqlSupportedUnions]

class SqlTransactionIsolationLevel(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SQL_TRANSACTION_NONE: _ClassVar[SqlTransactionIsolationLevel]
    SQL_TRANSACTION_READ_UNCOMMITTED: _ClassVar[SqlTransactionIsolationLevel]
    SQL_TRANSACTION_READ_COMMITTED: _ClassVar[SqlTransactionIsolationLevel]
    SQL_TRANSACTION_REPEATABLE_READ: _ClassVar[SqlTransactionIsolationLevel]
    SQL_TRANSACTION_SERIALIZABLE: _ClassVar[SqlTransactionIsolationLevel]

class SqlSupportedTransactions(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SQL_TRANSACTION_UNSPECIFIED: _ClassVar[SqlSupportedTransactions]
    SQL_DATA_DEFINITION_TRANSACTIONS: _ClassVar[SqlSupportedTransactions]
    SQL_DATA_MANIPULATION_TRANSACTIONS: _ClassVar[SqlSupportedTransactions]

class SqlSupportedResultSetType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SQL_RESULT_SET_TYPE_UNSPECIFIED: _ClassVar[SqlSupportedResultSetType]
    SQL_RESULT_SET_TYPE_FORWARD_ONLY: _ClassVar[SqlSupportedResultSetType]
    SQL_RESULT_SET_TYPE_SCROLL_INSENSITIVE: _ClassVar[SqlSupportedResultSetType]
    SQL_RESULT_SET_TYPE_SCROLL_SENSITIVE: _ClassVar[SqlSupportedResultSetType]

class SqlSupportedResultSetConcurrency(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SQL_RESULT_SET_CONCURRENCY_UNSPECIFIED: _ClassVar[SqlSupportedResultSetConcurrency]
    SQL_RESULT_SET_CONCURRENCY_READ_ONLY: _ClassVar[SqlSupportedResultSetConcurrency]
    SQL_RESULT_SET_CONCURRENCY_UPDATABLE: _ClassVar[SqlSupportedResultSetConcurrency]

class SqlSupportsConvert(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SQL_CONVERT_BIGINT: _ClassVar[SqlSupportsConvert]
    SQL_CONVERT_BINARY: _ClassVar[SqlSupportsConvert]
    SQL_CONVERT_BIT: _ClassVar[SqlSupportsConvert]
    SQL_CONVERT_CHAR: _ClassVar[SqlSupportsConvert]
    SQL_CONVERT_DATE: _ClassVar[SqlSupportsConvert]
    SQL_CONVERT_DECIMAL: _ClassVar[SqlSupportsConvert]
    SQL_CONVERT_FLOAT: _ClassVar[SqlSupportsConvert]
    SQL_CONVERT_INTEGER: _ClassVar[SqlSupportsConvert]
    SQL_CONVERT_INTERVAL_DAY_TIME: _ClassVar[SqlSupportsConvert]
    SQL_CONVERT_INTERVAL_YEAR_MONTH: _ClassVar[SqlSupportsConvert]
    SQL_CONVERT_LONGVARBINARY: _ClassVar[SqlSupportsConvert]
    SQL_CONVERT_LONGVARCHAR: _ClassVar[SqlSupportsConvert]
    SQL_CONVERT_NUMERIC: _ClassVar[SqlSupportsConvert]
    SQL_CONVERT_REAL: _ClassVar[SqlSupportsConvert]
    SQL_CONVERT_SMALLINT: _ClassVar[SqlSupportsConvert]
    SQL_CONVERT_TIME: _ClassVar[SqlSupportsConvert]
    SQL_CONVERT_TIMESTAMP: _ClassVar[SqlSupportsConvert]
    SQL_CONVERT_TINYINT: _ClassVar[SqlSupportsConvert]
    SQL_CONVERT_VARBINARY: _ClassVar[SqlSupportsConvert]
    SQL_CONVERT_VARCHAR: _ClassVar[SqlSupportsConvert]

class XdbcDataType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    XDBC_UNKNOWN_TYPE: _ClassVar[XdbcDataType]
    XDBC_CHAR: _ClassVar[XdbcDataType]
    XDBC_NUMERIC: _ClassVar[XdbcDataType]
    XDBC_DECIMAL: _ClassVar[XdbcDataType]
    XDBC_INTEGER: _ClassVar[XdbcDataType]
    XDBC_SMALLINT: _ClassVar[XdbcDataType]
    XDBC_FLOAT: _ClassVar[XdbcDataType]
    XDBC_REAL: _ClassVar[XdbcDataType]
    XDBC_DOUBLE: _ClassVar[XdbcDataType]
    XDBC_DATETIME: _ClassVar[XdbcDataType]
    XDBC_INTERVAL: _ClassVar[XdbcDataType]
    XDBC_VARCHAR: _ClassVar[XdbcDataType]
    XDBC_DATE: _ClassVar[XdbcDataType]
    XDBC_TIME: _ClassVar[XdbcDataType]
    XDBC_TIMESTAMP: _ClassVar[XdbcDataType]
    XDBC_LONGVARCHAR: _ClassVar[XdbcDataType]
    XDBC_BINARY: _ClassVar[XdbcDataType]
    XDBC_VARBINARY: _ClassVar[XdbcDataType]
    XDBC_LONGVARBINARY: _ClassVar[XdbcDataType]
    XDBC_BIGINT: _ClassVar[XdbcDataType]
    XDBC_TINYINT: _ClassVar[XdbcDataType]
    XDBC_BIT: _ClassVar[XdbcDataType]
    XDBC_WCHAR: _ClassVar[XdbcDataType]
    XDBC_WVARCHAR: _ClassVar[XdbcDataType]

class XdbcDatetimeSubcode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    XDBC_SUBCODE_UNKNOWN: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_YEAR: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_DATE: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_TIME: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_MONTH: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_TIMESTAMP: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_DAY: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_TIME_WITH_TIMEZONE: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_HOUR: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_TIMESTAMP_WITH_TIMEZONE: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_MINUTE: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_SECOND: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_YEAR_TO_MONTH: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_DAY_TO_HOUR: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_DAY_TO_MINUTE: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_DAY_TO_SECOND: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_HOUR_TO_MINUTE: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_HOUR_TO_SECOND: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_MINUTE_TO_SECOND: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_INTERVAL_YEAR: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_INTERVAL_MONTH: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_INTERVAL_DAY: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_INTERVAL_HOUR: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_INTERVAL_MINUTE: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_INTERVAL_SECOND: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_INTERVAL_YEAR_TO_MONTH: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_INTERVAL_DAY_TO_HOUR: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_INTERVAL_DAY_TO_MINUTE: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_INTERVAL_DAY_TO_SECOND: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_INTERVAL_HOUR_TO_MINUTE: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_INTERVAL_HOUR_TO_SECOND: _ClassVar[XdbcDatetimeSubcode]
    XDBC_SUBCODE_INTERVAL_MINUTE_TO_SECOND: _ClassVar[XdbcDatetimeSubcode]

class Nullable(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    NULLABILITY_NO_NULLS: _ClassVar[Nullable]
    NULLABILITY_NULLABLE: _ClassVar[Nullable]
    NULLABILITY_UNKNOWN: _ClassVar[Nullable]

class Searchable(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SEARCHABLE_NONE: _ClassVar[Searchable]
    SEARCHABLE_CHAR: _ClassVar[Searchable]
    SEARCHABLE_BASIC: _ClassVar[Searchable]
    SEARCHABLE_FULL: _ClassVar[Searchable]

class UpdateDeleteRules(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CASCADE: _ClassVar[UpdateDeleteRules]
    RESTRICT: _ClassVar[UpdateDeleteRules]
    SET_NULL: _ClassVar[UpdateDeleteRules]
    NO_ACTION: _ClassVar[UpdateDeleteRules]
    SET_DEFAULT: _ClassVar[UpdateDeleteRules]
FLIGHT_SQL_SERVER_NAME: SqlInfo
FLIGHT_SQL_SERVER_VERSION: SqlInfo
FLIGHT_SQL_SERVER_ARROW_VERSION: SqlInfo
FLIGHT_SQL_SERVER_READ_ONLY: SqlInfo
FLIGHT_SQL_SERVER_SQL: SqlInfo
FLIGHT_SQL_SERVER_SUBSTRAIT: SqlInfo
FLIGHT_SQL_SERVER_SUBSTRAIT_MIN_VERSION: SqlInfo
FLIGHT_SQL_SERVER_SUBSTRAIT_MAX_VERSION: SqlInfo
FLIGHT_SQL_SERVER_TRANSACTION: SqlInfo
FLIGHT_SQL_SERVER_CANCEL: SqlInfo
FLIGHT_SQL_SERVER_BULK_INGESTION: SqlInfo
FLIGHT_SQL_SERVER_INGEST_TRANSACTIONS_SUPPORTED: SqlInfo
FLIGHT_SQL_SERVER_STATEMENT_TIMEOUT: SqlInfo
FLIGHT_SQL_SERVER_TRANSACTION_TIMEOUT: SqlInfo
SQL_DDL_CATALOG: SqlInfo
SQL_DDL_SCHEMA: SqlInfo
SQL_DDL_TABLE: SqlInfo
SQL_IDENTIFIER_CASE: SqlInfo
SQL_IDENTIFIER_QUOTE_CHAR: SqlInfo
SQL_QUOTED_IDENTIFIER_CASE: SqlInfo
SQL_ALL_TABLES_ARE_SELECTABLE: SqlInfo
SQL_NULL_ORDERING: SqlInfo
SQL_KEYWORDS: SqlInfo
SQL_NUMERIC_FUNCTIONS: SqlInfo
SQL_STRING_FUNCTIONS: SqlInfo
SQL_SYSTEM_FUNCTIONS: SqlInfo
SQL_DATETIME_FUNCTIONS: SqlInfo
SQL_SEARCH_STRING_ESCAPE: SqlInfo
SQL_EXTRA_NAME_CHARACTERS: SqlInfo
SQL_SUPPORTS_COLUMN_ALIASING: SqlInfo
SQL_NULL_PLUS_NULL_IS_NULL: SqlInfo
SQL_SUPPORTS_CONVERT: SqlInfo
SQL_SUPPORTS_TABLE_CORRELATION_NAMES: SqlInfo
SQL_SUPPORTS_DIFFERENT_TABLE_CORRELATION_NAMES: SqlInfo
SQL_SUPPORTS_EXPRESSIONS_IN_ORDER_BY: SqlInfo
SQL_SUPPORTS_ORDER_BY_UNRELATED: SqlInfo
SQL_SUPPORTED_GROUP_BY: SqlInfo
SQL_SUPPORTS_LIKE_ESCAPE_CLAUSE: SqlInfo
SQL_SUPPORTS_NON_NULLABLE_COLUMNS: SqlInfo
SQL_SUPPORTED_GRAMMAR: SqlInfo
SQL_ANSI92_SUPPORTED_LEVEL: SqlInfo
SQL_SUPPORTS_INTEGRITY_ENHANCEMENT_FACILITY: SqlInfo
SQL_OUTER_JOINS_SUPPORT_LEVEL: SqlInfo
SQL_SCHEMA_TERM: SqlInfo
SQL_PROCEDURE_TERM: SqlInfo
SQL_CATALOG_TERM: SqlInfo
SQL_CATALOG_AT_START: SqlInfo
SQL_SCHEMAS_SUPPORTED_ACTIONS: SqlInfo
SQL_CATALOGS_SUPPORTED_ACTIONS: SqlInfo
SQL_SUPPORTED_POSITIONED_COMMANDS: SqlInfo
SQL_SELECT_FOR_UPDATE_SUPPORTED: SqlInfo
SQL_STORED_PROCEDURES_SUPPORTED: SqlInfo
SQL_SUPPORTED_SUBQUERIES: SqlInfo
SQL_CORRELATED_SUBQUERIES_SUPPORTED: SqlInfo
SQL_SUPPORTED_UNIONS: SqlInfo
SQL_MAX_BINARY_LITERAL_LENGTH: SqlInfo
SQL_MAX_CHAR_LITERAL_LENGTH: SqlInfo
SQL_MAX_COLUMN_NAME_LENGTH: SqlInfo
SQL_MAX_COLUMNS_IN_GROUP_BY: SqlInfo
SQL_MAX_COLUMNS_IN_INDEX: SqlInfo
SQL_MAX_COLUMNS_IN_ORDER_BY: SqlInfo
SQL_MAX_COLUMNS_IN_SELECT: SqlInfo
SQL_MAX_COLUMNS_IN_TABLE: SqlInfo
SQL_MAX_CONNECTIONS: SqlInfo
SQL_MAX_CURSOR_NAME_LENGTH: SqlInfo
SQL_MAX_INDEX_LENGTH: SqlInfo
SQL_DB_SCHEMA_NAME_LENGTH: SqlInfo
SQL_MAX_PROCEDURE_NAME_LENGTH: SqlInfo
SQL_MAX_CATALOG_NAME_LENGTH: SqlInfo
SQL_MAX_ROW_SIZE: SqlInfo
SQL_MAX_ROW_SIZE_INCLUDES_BLOBS: SqlInfo
SQL_MAX_STATEMENT_LENGTH: SqlInfo
SQL_MAX_STATEMENTS: SqlInfo
SQL_MAX_TABLE_NAME_LENGTH: SqlInfo
SQL_MAX_TABLES_IN_SELECT: SqlInfo
SQL_MAX_USERNAME_LENGTH: SqlInfo
SQL_DEFAULT_TRANSACTION_ISOLATION: SqlInfo
SQL_TRANSACTIONS_SUPPORTED: SqlInfo
SQL_SUPPORTED_TRANSACTIONS_ISOLATION_LEVELS: SqlInfo
SQL_DATA_DEFINITION_CAUSES_TRANSACTION_COMMIT: SqlInfo
SQL_DATA_DEFINITIONS_IN_TRANSACTIONS_IGNORED: SqlInfo
SQL_SUPPORTED_RESULT_SET_TYPES: SqlInfo
SQL_SUPPORTED_CONCURRENCIES_FOR_RESULT_SET_UNSPECIFIED: SqlInfo
SQL_SUPPORTED_CONCURRENCIES_FOR_RESULT_SET_FORWARD_ONLY: SqlInfo
SQL_SUPPORTED_CONCURRENCIES_FOR_RESULT_SET_SCROLL_SENSITIVE: SqlInfo
SQL_SUPPORTED_CONCURRENCIES_FOR_RESULT_SET_SCROLL_INSENSITIVE: SqlInfo
SQL_BATCH_UPDATES_SUPPORTED: SqlInfo
SQL_SAVEPOINTS_SUPPORTED: SqlInfo
SQL_NAMED_PARAMETERS_SUPPORTED: SqlInfo
SQL_LOCATORS_UPDATE_COPY: SqlInfo
SQL_STORED_FUNCTIONS_USING_CALL_SYNTAX_SUPPORTED: SqlInfo
SQL_SUPPORTED_TRANSACTION_NONE: SqlSupportedTransaction
SQL_SUPPORTED_TRANSACTION_TRANSACTION: SqlSupportedTransaction
SQL_SUPPORTED_TRANSACTION_SAVEPOINT: SqlSupportedTransaction
SQL_CASE_SENSITIVITY_UNKNOWN: SqlSupportedCaseSensitivity
SQL_CASE_SENSITIVITY_CASE_INSENSITIVE: SqlSupportedCaseSensitivity
SQL_CASE_SENSITIVITY_UPPERCASE: SqlSupportedCaseSensitivity
SQL_CASE_SENSITIVITY_LOWERCASE: SqlSupportedCaseSensitivity
SQL_NULLS_SORTED_HIGH: SqlNullOrdering
SQL_NULLS_SORTED_LOW: SqlNullOrdering
SQL_NULLS_SORTED_AT_START: SqlNullOrdering
SQL_NULLS_SORTED_AT_END: SqlNullOrdering
SQL_MINIMUM_GRAMMAR: SupportedSqlGrammar
SQL_CORE_GRAMMAR: SupportedSqlGrammar
SQL_EXTENDED_GRAMMAR: SupportedSqlGrammar
ANSI92_ENTRY_SQL: SupportedAnsi92SqlGrammarLevel
ANSI92_INTERMEDIATE_SQL: SupportedAnsi92SqlGrammarLevel
ANSI92_FULL_SQL: SupportedAnsi92SqlGrammarLevel
SQL_JOINS_UNSUPPORTED: SqlOuterJoinsSupportLevel
SQL_LIMITED_OUTER_JOINS: SqlOuterJoinsSupportLevel
SQL_FULL_OUTER_JOINS: SqlOuterJoinsSupportLevel
SQL_GROUP_BY_UNRELATED: SqlSupportedGroupBy
SQL_GROUP_BY_BEYOND_SELECT: SqlSupportedGroupBy
SQL_ELEMENT_IN_PROCEDURE_CALLS: SqlSupportedElementActions
SQL_ELEMENT_IN_INDEX_DEFINITIONS: SqlSupportedElementActions
SQL_ELEMENT_IN_PRIVILEGE_DEFINITIONS: SqlSupportedElementActions
SQL_POSITIONED_DELETE: SqlSupportedPositionedCommands
SQL_POSITIONED_UPDATE: SqlSupportedPositionedCommands
SQL_SUBQUERIES_IN_COMPARISONS: SqlSupportedSubqueries
SQL_SUBQUERIES_IN_EXISTS: SqlSupportedSubqueries
SQL_SUBQUERIES_IN_INS: SqlSupportedSubqueries
SQL_SUBQUERIES_IN_QUANTIFIEDS: SqlSupportedSubqueries
SQL_UNION: SqlSupportedUnions
SQL_UNION_ALL: SqlSupportedUnions
SQL_TRANSACTION_NONE: SqlTransactionIsolationLevel
SQL_TRANSACTION_READ_UNCOMMITTED: SqlTransactionIsolationLevel
SQL_TRANSACTION_READ_COMMITTED: SqlTransactionIsolationLevel
SQL_TRANSACTION_REPEATABLE_READ: SqlTransactionIsolationLevel
SQL_TRANSACTION_SERIALIZABLE: SqlTransactionIsolationLevel
SQL_TRANSACTION_UNSPECIFIED: SqlSupportedTransactions
SQL_DATA_DEFINITION_TRANSACTIONS: SqlSupportedTransactions
SQL_DATA_MANIPULATION_TRANSACTIONS: SqlSupportedTransactions
SQL_RESULT_SET_TYPE_UNSPECIFIED: SqlSupportedResultSetType
SQL_RESULT_SET_TYPE_FORWARD_ONLY: SqlSupportedResultSetType
SQL_RESULT_SET_TYPE_SCROLL_INSENSITIVE: SqlSupportedResultSetType
SQL_RESULT_SET_TYPE_SCROLL_SENSITIVE: SqlSupportedResultSetType
SQL_RESULT_SET_CONCURRENCY_UNSPECIFIED: SqlSupportedResultSetConcurrency
SQL_RESULT_SET_CONCURRENCY_READ_ONLY: SqlSupportedResultSetConcurrency
SQL_RESULT_SET_CONCURRENCY_UPDATABLE: SqlSupportedResultSetConcurrency
SQL_CONVERT_BIGINT: SqlSupportsConvert
SQL_CONVERT_BINARY: SqlSupportsConvert
SQL_CONVERT_BIT: SqlSupportsConvert
SQL_CONVERT_CHAR: SqlSupportsConvert
SQL_CONVERT_DATE: SqlSupportsConvert
SQL_CONVERT_DECIMAL: SqlSupportsConvert
SQL_CONVERT_FLOAT: SqlSupportsConvert
SQL_CONVERT_INTEGER: SqlSupportsConvert
SQL_CONVERT_INTERVAL_DAY_TIME: SqlSupportsConvert
SQL_CONVERT_INTERVAL_YEAR_MONTH: SqlSupportsConvert
SQL_CONVERT_LONGVARBINARY: SqlSupportsConvert
SQL_CONVERT_LONGVARCHAR: SqlSupportsConvert
SQL_CONVERT_NUMERIC: SqlSupportsConvert
SQL_CONVERT_REAL: SqlSupportsConvert
SQL_CONVERT_SMALLINT: SqlSupportsConvert
SQL_CONVERT_TIME: SqlSupportsConvert
SQL_CONVERT_TIMESTAMP: SqlSupportsConvert
SQL_CONVERT_TINYINT: SqlSupportsConvert
SQL_CONVERT_VARBINARY: SqlSupportsConvert
SQL_CONVERT_VARCHAR: SqlSupportsConvert
XDBC_UNKNOWN_TYPE: XdbcDataType
XDBC_CHAR: XdbcDataType
XDBC_NUMERIC: XdbcDataType
XDBC_DECIMAL: XdbcDataType
XDBC_INTEGER: XdbcDataType
XDBC_SMALLINT: XdbcDataType
XDBC_FLOAT: XdbcDataType
XDBC_REAL: XdbcDataType
XDBC_DOUBLE: XdbcDataType
XDBC_DATETIME: XdbcDataType
XDBC_INTERVAL: XdbcDataType
XDBC_VARCHAR: XdbcDataType
XDBC_DATE: XdbcDataType
XDBC_TIME: XdbcDataType
XDBC_TIMESTAMP: XdbcDataType
XDBC_LONGVARCHAR: XdbcDataType
XDBC_BINARY: XdbcDataType
XDBC_VARBINARY: XdbcDataType
XDBC_LONGVARBINARY: XdbcDataType
XDBC_BIGINT: XdbcDataType
XDBC_TINYINT: XdbcDataType
XDBC_BIT: XdbcDataType
XDBC_WCHAR: XdbcDataType
XDBC_WVARCHAR: XdbcDataType
XDBC_SUBCODE_UNKNOWN: XdbcDatetimeSubcode
XDBC_SUBCODE_YEAR: XdbcDatetimeSubcode
XDBC_SUBCODE_DATE: XdbcDatetimeSubcode
XDBC_SUBCODE_TIME: XdbcDatetimeSubcode
XDBC_SUBCODE_MONTH: XdbcDatetimeSubcode
XDBC_SUBCODE_TIMESTAMP: XdbcDatetimeSubcode
XDBC_SUBCODE_DAY: XdbcDatetimeSubcode
XDBC_SUBCODE_TIME_WITH_TIMEZONE: XdbcDatetimeSubcode
XDBC_SUBCODE_HOUR: XdbcDatetimeSubcode
XDBC_SUBCODE_TIMESTAMP_WITH_TIMEZONE: XdbcDatetimeSubcode
XDBC_SUBCODE_MINUTE: XdbcDatetimeSubcode
XDBC_SUBCODE_SECOND: XdbcDatetimeSubcode
XDBC_SUBCODE_YEAR_TO_MONTH: XdbcDatetimeSubcode
XDBC_SUBCODE_DAY_TO_HOUR: XdbcDatetimeSubcode
XDBC_SUBCODE_DAY_TO_MINUTE: XdbcDatetimeSubcode
XDBC_SUBCODE_DAY_TO_SECOND: XdbcDatetimeSubcode
XDBC_SUBCODE_HOUR_TO_MINUTE: XdbcDatetimeSubcode
XDBC_SUBCODE_HOUR_TO_SECOND: XdbcDatetimeSubcode
XDBC_SUBCODE_MINUTE_TO_SECOND: XdbcDatetimeSubcode
XDBC_SUBCODE_INTERVAL_YEAR: XdbcDatetimeSubcode
XDBC_SUBCODE_INTERVAL_MONTH: XdbcDatetimeSubcode
XDBC_SUBCODE_INTERVAL_DAY: XdbcDatetimeSubcode
XDBC_SUBCODE_INTERVAL_HOUR: XdbcDatetimeSubcode
XDBC_SUBCODE_INTERVAL_MINUTE: XdbcDatetimeSubcode
XDBC_SUBCODE_INTERVAL_SECOND: XdbcDatetimeSubcode
XDBC_SUBCODE_INTERVAL_YEAR_TO_MONTH: XdbcDatetimeSubcode
XDBC_SUBCODE_INTERVAL_DAY_TO_HOUR: XdbcDatetimeSubcode
XDBC_SUBCODE_INTERVAL_DAY_TO_MINUTE: XdbcDatetimeSubcode
XDBC_SUBCODE_INTERVAL_DAY_TO_SECOND: XdbcDatetimeSubcode
XDBC_SUBCODE_INTERVAL_HOUR_TO_MINUTE: XdbcDatetimeSubcode
XDBC_SUBCODE_INTERVAL_HOUR_TO_SECOND: XdbcDatetimeSubcode
XDBC_SUBCODE_INTERVAL_MINUTE_TO_SECOND: XdbcDatetimeSubcode
NULLABILITY_NO_NULLS: Nullable
NULLABILITY_NULLABLE: Nullable
NULLABILITY_UNKNOWN: Nullable
SEARCHABLE_NONE: Searchable
SEARCHABLE_CHAR: Searchable
SEARCHABLE_BASIC: Searchable
SEARCHABLE_FULL: Searchable
CASCADE: UpdateDeleteRules
RESTRICT: UpdateDeleteRules
SET_NULL: UpdateDeleteRules
NO_ACTION: UpdateDeleteRules
SET_DEFAULT: UpdateDeleteRules
EXPERIMENTAL_FIELD_NUMBER: _ClassVar[int]
experimental: _descriptor.FieldDescriptor

class CommandGetSqlInfo(_message.Message):
    __slots__ = ("info",)
    INFO_FIELD_NUMBER: _ClassVar[int]
    info: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, info: _Optional[_Iterable[int]] = ...) -> None: ...

class CommandGetXdbcTypeInfo(_message.Message):
    __slots__ = ("data_type",)
    DATA_TYPE_FIELD_NUMBER: _ClassVar[int]
    data_type: int
    def __init__(self, data_type: _Optional[int] = ...) -> None: ...

class CommandGetCatalogs(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CommandGetDbSchemas(_message.Message):
    __slots__ = ("catalog", "db_schema_filter_pattern")
    CATALOG_FIELD_NUMBER: _ClassVar[int]
    DB_SCHEMA_FILTER_PATTERN_FIELD_NUMBER: _ClassVar[int]
    catalog: str
    db_schema_filter_pattern: str
    def __init__(self, catalog: _Optional[str] = ..., db_schema_filter_pattern: _Optional[str] = ...) -> None: ...

class CommandGetTables(_message.Message):
    __slots__ = ("catalog", "db_schema_filter_pattern", "table_name_filter_pattern", "table_types", "include_schema")
    CATALOG_FIELD_NUMBER: _ClassVar[int]
    DB_SCHEMA_FILTER_PATTERN_FIELD_NUMBER: _ClassVar[int]
    TABLE_NAME_FILTER_PATTERN_FIELD_NUMBER: _ClassVar[int]
    TABLE_TYPES_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_SCHEMA_FIELD_NUMBER: _ClassVar[int]
    catalog: str
    db_schema_filter_pattern: str
    table_name_filter_pattern: str
    table_types: _containers.RepeatedScalarFieldContainer[str]
    include_schema: bool
    def __init__(self, catalog: _Optional[str] = ..., db_schema_filter_pattern: _Optional[str] = ..., table_name_filter_pattern: _Optional[str] = ..., table_types: _Optional[_Iterable[str]] = ..., include_schema: bool = ...) -> None: ...

class CommandGetTableTypes(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CommandGetPrimaryKeys(_message.Message):
    __slots__ = ("catalog", "db_schema", "table")
    CATALOG_FIELD_NUMBER: _ClassVar[int]
    DB_SCHEMA_FIELD_NUMBER: _ClassVar[int]
    TABLE_FIELD_NUMBER: _ClassVar[int]
    catalog: str
    db_schema: str
    table: str
    def __init__(self, catalog: _Optional[str] = ..., db_schema: _Optional[str] = ..., table: _Optional[str] = ...) -> None: ...

class CommandGetExportedKeys(_message.Message):
    __slots__ = ("catalog", "db_schema", "table")
    CATALOG_FIELD_NUMBER: _ClassVar[int]
    DB_SCHEMA_FIELD_NUMBER: _ClassVar[int]
    TABLE_FIELD_NUMBER: _ClassVar[int]
    catalog: str
    db_schema: str
    table: str
    def __init__(self, catalog: _Optional[str] = ..., db_schema: _Optional[str] = ..., table: _Optional[str] = ...) -> None: ...

class CommandGetImportedKeys(_message.Message):
    __slots__ = ("catalog", "db_schema", "table")
    CATALOG_FIELD_NUMBER: _ClassVar[int]
    DB_SCHEMA_FIELD_NUMBER: _ClassVar[int]
    TABLE_FIELD_NUMBER: _ClassVar[int]
    catalog: str
    db_schema: str
    table: str
    def __init__(self, catalog: _Optional[str] = ..., db_schema: _Optional[str] = ..., table: _Optional[str] = ...) -> None: ...

class CommandGetCrossReference(_message.Message):
    __slots__ = ("pk_catalog", "pk_db_schema", "pk_table", "fk_catalog", "fk_db_schema", "fk_table")
    PK_CATALOG_FIELD_NUMBER: _ClassVar[int]
    PK_DB_SCHEMA_FIELD_NUMBER: _ClassVar[int]
    PK_TABLE_FIELD_NUMBER: _ClassVar[int]
    FK_CATALOG_FIELD_NUMBER: _ClassVar[int]
    FK_DB_SCHEMA_FIELD_NUMBER: _ClassVar[int]
    FK_TABLE_FIELD_NUMBER: _ClassVar[int]
    pk_catalog: str
    pk_db_schema: str
    pk_table: str
    fk_catalog: str
    fk_db_schema: str
    fk_table: str
    def __init__(self, pk_catalog: _Optional[str] = ..., pk_db_schema: _Optional[str] = ..., pk_table: _Optional[str] = ..., fk_catalog: _Optional[str] = ..., fk_db_schema: _Optional[str] = ..., fk_table: _Optional[str] = ...) -> None: ...

class ActionCreatePreparedStatementRequest(_message.Message):
    __slots__ = ("query", "transaction_id")
    QUERY_FIELD_NUMBER: _ClassVar[int]
    TRANSACTION_ID_FIELD_NUMBER: _ClassVar[int]
    query: str
    transaction_id: bytes
    def __init__(self, query: _Optional[str] = ..., transaction_id: _Optional[bytes] = ...) -> None: ...

class SubstraitPlan(_message.Message):
    __slots__ = ("plan", "version")
    PLAN_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    plan: bytes
    version: str
    def __init__(self, plan: _Optional[bytes] = ..., version: _Optional[str] = ...) -> None: ...

class ActionCreatePreparedSubstraitPlanRequest(_message.Message):
    __slots__ = ("plan", "transaction_id")
    PLAN_FIELD_NUMBER: _ClassVar[int]
    TRANSACTION_ID_FIELD_NUMBER: _ClassVar[int]
    plan: SubstraitPlan
    transaction_id: bytes
    def __init__(self, plan: _Optional[_Union[SubstraitPlan, _Mapping]] = ..., transaction_id: _Optional[bytes] = ...) -> None: ...

class ActionCreatePreparedStatementResult(_message.Message):
    __slots__ = ("prepared_statement_handle", "dataset_schema", "parameter_schema")
    PREPARED_STATEMENT_HANDLE_FIELD_NUMBER: _ClassVar[int]
    DATASET_SCHEMA_FIELD_NUMBER: _ClassVar[int]
    PARAMETER_SCHEMA_FIELD_NUMBER: _ClassVar[int]
    prepared_statement_handle: bytes
    dataset_schema: bytes
    parameter_schema: bytes
    def __init__(self, prepared_statement_handle: _Optional[bytes] = ..., dataset_schema: _Optional[bytes] = ..., parameter_schema: _Optional[bytes] = ...) -> None: ...

class ActionClosePreparedStatementRequest(_message.Message):
    __slots__ = ("prepared_statement_handle",)
    PREPARED_STATEMENT_HANDLE_FIELD_NUMBER: _ClassVar[int]
    prepared_statement_handle: bytes
    def __init__(self, prepared_statement_handle: _Optional[bytes] = ...) -> None: ...

class ActionBeginTransactionRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ActionBeginSavepointRequest(_message.Message):
    __slots__ = ("transaction_id", "name")
    TRANSACTION_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    transaction_id: bytes
    name: str
    def __init__(self, transaction_id: _Optional[bytes] = ..., name: _Optional[str] = ...) -> None: ...

class ActionBeginTransactionResult(_message.Message):
    __slots__ = ("transaction_id",)
    TRANSACTION_ID_FIELD_NUMBER: _ClassVar[int]
    transaction_id: bytes
    def __init__(self, transaction_id: _Optional[bytes] = ...) -> None: ...

class ActionBeginSavepointResult(_message.Message):
    __slots__ = ("savepoint_id",)
    SAVEPOINT_ID_FIELD_NUMBER: _ClassVar[int]
    savepoint_id: bytes
    def __init__(self, savepoint_id: _Optional[bytes] = ...) -> None: ...

class ActionEndTransactionRequest(_message.Message):
    __slots__ = ("transaction_id", "action")
    class EndTransaction(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        END_TRANSACTION_UNSPECIFIED: _ClassVar[ActionEndTransactionRequest.EndTransaction]
        END_TRANSACTION_COMMIT: _ClassVar[ActionEndTransactionRequest.EndTransaction]
        END_TRANSACTION_ROLLBACK: _ClassVar[ActionEndTransactionRequest.EndTransaction]
    END_TRANSACTION_UNSPECIFIED: ActionEndTransactionRequest.EndTransaction
    END_TRANSACTION_COMMIT: ActionEndTransactionRequest.EndTransaction
    END_TRANSACTION_ROLLBACK: ActionEndTransactionRequest.EndTransaction
    TRANSACTION_ID_FIELD_NUMBER: _ClassVar[int]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    transaction_id: bytes
    action: ActionEndTransactionRequest.EndTransaction
    def __init__(self, transaction_id: _Optional[bytes] = ..., action: _Optional[_Union[ActionEndTransactionRequest.EndTransaction, str]] = ...) -> None: ...

class ActionEndSavepointRequest(_message.Message):
    __slots__ = ("savepoint_id", "action")
    class EndSavepoint(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        END_SAVEPOINT_UNSPECIFIED: _ClassVar[ActionEndSavepointRequest.EndSavepoint]
        END_SAVEPOINT_RELEASE: _ClassVar[ActionEndSavepointRequest.EndSavepoint]
        END_SAVEPOINT_ROLLBACK: _ClassVar[ActionEndSavepointRequest.EndSavepoint]
    END_SAVEPOINT_UNSPECIFIED: ActionEndSavepointRequest.EndSavepoint
    END_SAVEPOINT_RELEASE: ActionEndSavepointRequest.EndSavepoint
    END_SAVEPOINT_ROLLBACK: ActionEndSavepointRequest.EndSavepoint
    SAVEPOINT_ID_FIELD_NUMBER: _ClassVar[int]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    savepoint_id: bytes
    action: ActionEndSavepointRequest.EndSavepoint
    def __init__(self, savepoint_id: _Optional[bytes] = ..., action: _Optional[_Union[ActionEndSavepointRequest.EndSavepoint, str]] = ...) -> None: ...

class CommandStatementQuery(_message.Message):
    __slots__ = ("query", "transaction_id")
    QUERY_FIELD_NUMBER: _ClassVar[int]
    TRANSACTION_ID_FIELD_NUMBER: _ClassVar[int]
    query: str
    transaction_id: bytes
    def __init__(self, query: _Optional[str] = ..., transaction_id: _Optional[bytes] = ...) -> None: ...

class CommandStatementSubstraitPlan(_message.Message):
    __slots__ = ("plan", "transaction_id")
    PLAN_FIELD_NUMBER: _ClassVar[int]
    TRANSACTION_ID_FIELD_NUMBER: _ClassVar[int]
    plan: SubstraitPlan
    transaction_id: bytes
    def __init__(self, plan: _Optional[_Union[SubstraitPlan, _Mapping]] = ..., transaction_id: _Optional[bytes] = ...) -> None: ...

class TicketStatementQuery(_message.Message):
    __slots__ = ("statement_handle",)
    STATEMENT_HANDLE_FIELD_NUMBER: _ClassVar[int]
    statement_handle: bytes
    def __init__(self, statement_handle: _Optional[bytes] = ...) -> None: ...

class CommandPreparedStatementQuery(_message.Message):
    __slots__ = ("prepared_statement_handle",)
    PREPARED_STATEMENT_HANDLE_FIELD_NUMBER: _ClassVar[int]
    prepared_statement_handle: bytes
    def __init__(self, prepared_statement_handle: _Optional[bytes] = ...) -> None: ...

class CommandStatementUpdate(_message.Message):
    __slots__ = ("query", "transaction_id")
    QUERY_FIELD_NUMBER: _ClassVar[int]
    TRANSACTION_ID_FIELD_NUMBER: _ClassVar[int]
    query: str
    transaction_id: bytes
    def __init__(self, query: _Optional[str] = ..., transaction_id: _Optional[bytes] = ...) -> None: ...

class CommandPreparedStatementUpdate(_message.Message):
    __slots__ = ("prepared_statement_handle",)
    PREPARED_STATEMENT_HANDLE_FIELD_NUMBER: _ClassVar[int]
    prepared_statement_handle: bytes
    def __init__(self, prepared_statement_handle: _Optional[bytes] = ...) -> None: ...

class CommandStatementIngest(_message.Message):
    __slots__ = ("table_definition_options", "table", "schema", "catalog", "temporary", "transaction_id", "options")
    class TableDefinitionOptions(_message.Message):
        __slots__ = ("if_not_exist", "if_exists")
        class TableNotExistOption(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            TABLE_NOT_EXIST_OPTION_UNSPECIFIED: _ClassVar[CommandStatementIngest.TableDefinitionOptions.TableNotExistOption]
            TABLE_NOT_EXIST_OPTION_CREATE: _ClassVar[CommandStatementIngest.TableDefinitionOptions.TableNotExistOption]
            TABLE_NOT_EXIST_OPTION_FAIL: _ClassVar[CommandStatementIngest.TableDefinitionOptions.TableNotExistOption]
        TABLE_NOT_EXIST_OPTION_UNSPECIFIED: CommandStatementIngest.TableDefinitionOptions.TableNotExistOption
        TABLE_NOT_EXIST_OPTION_CREATE: CommandStatementIngest.TableDefinitionOptions.TableNotExistOption
        TABLE_NOT_EXIST_OPTION_FAIL: CommandStatementIngest.TableDefinitionOptions.TableNotExistOption
        class TableExistsOption(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            TABLE_EXISTS_OPTION_UNSPECIFIED: _ClassVar[CommandStatementIngest.TableDefinitionOptions.TableExistsOption]
            TABLE_EXISTS_OPTION_FAIL: _ClassVar[CommandStatementIngest.TableDefinitionOptions.TableExistsOption]
            TABLE_EXISTS_OPTION_APPEND: _ClassVar[CommandStatementIngest.TableDefinitionOptions.TableExistsOption]
            TABLE_EXISTS_OPTION_REPLACE: _ClassVar[CommandStatementIngest.TableDefinitionOptions.TableExistsOption]
        TABLE_EXISTS_OPTION_UNSPECIFIED: CommandStatementIngest.TableDefinitionOptions.TableExistsOption
        TABLE_EXISTS_OPTION_FAIL: CommandStatementIngest.TableDefinitionOptions.TableExistsOption
        TABLE_EXISTS_OPTION_APPEND: CommandStatementIngest.TableDefinitionOptions.TableExistsOption
        TABLE_EXISTS_OPTION_REPLACE: CommandStatementIngest.TableDefinitionOptions.TableExistsOption
        IF_NOT_EXIST_FIELD_NUMBER: _ClassVar[int]
        IF_EXISTS_FIELD_NUMBER: _ClassVar[int]
        if_not_exist: CommandStatementIngest.TableDefinitionOptions.TableNotExistOption
        if_exists: CommandStatementIngest.TableDefinitionOptions.TableExistsOption
        def __init__(self, if_not_exist: _Optional[_Union[CommandStatementIngest.TableDefinitionOptions.TableNotExistOption, str]] = ..., if_exists: _Optional[_Union[CommandStatementIngest.TableDefinitionOptions.TableExistsOption, str]] = ...) -> None: ...
    class OptionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    TABLE_DEFINITION_OPTIONS_FIELD_NUMBER: _ClassVar[int]
    TABLE_FIELD_NUMBER: _ClassVar[int]
    SCHEMA_FIELD_NUMBER: _ClassVar[int]
    CATALOG_FIELD_NUMBER: _ClassVar[int]
    TEMPORARY_FIELD_NUMBER: _ClassVar[int]
    TRANSACTION_ID_FIELD_NUMBER: _ClassVar[int]
    OPTIONS_FIELD_NUMBER: _ClassVar[int]
    table_definition_options: CommandStatementIngest.TableDefinitionOptions
    table: str
    schema: str
    catalog: str
    temporary: bool
    transaction_id: bytes
    options: _containers.ScalarMap[str, str]
    def __init__(self, table_definition_options: _Optional[_Union[CommandStatementIngest.TableDefinitionOptions, _Mapping]] = ..., table: _Optional[str] = ..., schema: _Optional[str] = ..., catalog: _Optional[str] = ..., temporary: bool = ..., transaction_id: _Optional[bytes] = ..., options: _Optional[_Mapping[str, str]] = ...) -> None: ...

class DoPutUpdateResult(_message.Message):
    __slots__ = ("record_count",)
    RECORD_COUNT_FIELD_NUMBER: _ClassVar[int]
    record_count: int
    def __init__(self, record_count: _Optional[int] = ...) -> None: ...

class DoPutPreparedStatementResult(_message.Message):
    __slots__ = ("prepared_statement_handle",)
    PREPARED_STATEMENT_HANDLE_FIELD_NUMBER: _ClassVar[int]
    prepared_statement_handle: bytes
    def __init__(self, prepared_statement_handle: _Optional[bytes] = ...) -> None: ...

class ActionCancelQueryRequest(_message.Message):
    __slots__ = ("info",)
    INFO_FIELD_NUMBER: _ClassVar[int]
    info: bytes
    def __init__(self, info: _Optional[bytes] = ...) -> None: ...

class ActionCancelQueryResult(_message.Message):
    __slots__ = ("result",)
    class CancelResult(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        CANCEL_RESULT_UNSPECIFIED: _ClassVar[ActionCancelQueryResult.CancelResult]
        CANCEL_RESULT_CANCELLED: _ClassVar[ActionCancelQueryResult.CancelResult]
        CANCEL_RESULT_CANCELLING: _ClassVar[ActionCancelQueryResult.CancelResult]
        CANCEL_RESULT_NOT_CANCELLABLE: _ClassVar[ActionCancelQueryResult.CancelResult]
    CANCEL_RESULT_UNSPECIFIED: ActionCancelQueryResult.CancelResult
    CANCEL_RESULT_CANCELLED: ActionCancelQueryResult.CancelResult
    CANCEL_RESULT_CANCELLING: ActionCancelQueryResult.CancelResult
    CANCEL_RESULT_NOT_CANCELLABLE: ActionCancelQueryResult.CancelResult
    RESULT_FIELD_NUMBER: _ClassVar[int]
    result: ActionCancelQueryResult.CancelResult
    def __init__(self, result: _Optional[_Union[ActionCancelQueryResult.CancelResult, str]] = ...) -> None: ...

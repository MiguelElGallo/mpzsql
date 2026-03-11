"""Concrete DuckDB-backed Flight SQL server.

This module implements :class:`DuckDBFlightSqlServer`, the concrete subclass of
:class:`~lakehouse.dispatch.FlightSqlServer` that fulfils every Flight SQL
handler by executing queries against a DuckDB in-process database and streaming
results as Apache Arrow record batches.

The mapping to the C++ original is 1-to-1:

* ``GetFlightInfoStatement``  → :meth:`get_flight_info_statement`
* ``DoGetStatement``          → :meth:`do_get_statement`
* ``DoGetCatalogs``           → :meth:`do_get_catalogs`
* ``DoGetDbSchemas``          → :meth:`do_get_db_schemas`
* ``DoGetTables``             → :meth:`do_get_tables`
* ``DoGetTableTypes``         → :meth:`do_get_table_types`
* ``DoPutCommandStatementUpdate`` → :meth:`do_put_statement_update`
* ``CreatePreparedStatement`` → :meth:`create_prepared_statement`
* ``ClosePreparedStatement``  → :meth:`close_prepared_statement`
* ``DoGetPreparedStatement``  → :meth:`do_get_prepared_statement`
* ``DoPutPreparedStatementUpdate`` → :meth:`do_put_prepared_statement_update`
* ``BeginTransaction`` / ``EndTransaction`` → :meth:`begin_transaction` / :meth:`end_transaction`
* ``DoGetPrimaryKeys``        → :meth:`do_get_primary_keys`
* ``DoGetImportedKeys``       → :meth:`do_get_imported_keys`
* ``DoGetExportedKeys``       → :meth:`do_get_exported_keys`
* ``DoGetCrossReference``     → :meth:`do_get_cross_reference`
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import duckdb
import pyarrow as pa
import pyarrow.flight as flight

from lakehouse.dispatch import FlightSqlServer
from lakehouse.proto import fs, pack_any
from lakehouse.session import SessionManager

logger = logging.getLogger(__name__)

__all__ = ["DuckDBFlightSqlServer"]

# ---------------------------------------------------------------------------
# SQL templates (mirrored from duckdb_server.cpp)
# ---------------------------------------------------------------------------
_CATALOGS_QUERY = (
    "SELECT DISTINCT catalog_name FROM information_schema.schemata ORDER BY catalog_name"
)

_DB_SCHEMAS_QUERY_BASE = (
    "SELECT catalog_name, schema_name AS db_schema_name "
    "FROM information_schema.schemata WHERE 1 = 1"
)

_TABLE_TYPES_QUERY = (
    "SELECT * FROM VALUES ('BASE TABLE'), ('LOCAL TEMPORARY'), ('VIEW') "
    "AS table_types (table_type)"
)

_PRIMARY_KEYS_QUERY_BASE = (
    "SELECT database_name AS catalog_name"
    "     , schema_name"
    "     , table_name"
    "     , UNNEST(constraint_column_names) AS column_name"
    "     , UNNEST(constraint_column_indexes) + 1 AS key_sequence"
    "     , constraint_name AS key_name"
    " FROM duckdb_constraints()"
    " WHERE constraint_type = 'PRIMARY KEY'"
)

_IMPORTED_EXPORTED_KEYS_QUERY = """\
SELECT * FROM (
    SELECT fk.database_name     AS pk_catalog_name,
           fk.schema_name       AS pk_schema_name,
           fk.referenced_table  AS pk_table_name,
           UNNEST(fk.referenced_column_names)   AS pk_column_name,
           fk.database_name     AS fk_catalog_name,
           fk.schema_name       AS fk_schema_name,
           fk.table_name        AS fk_table_name,
           UNNEST(fk.constraint_column_names)   AS fk_column_name,
           UNNEST(fk.constraint_column_indexes) AS key_sequence,
           fk.constraint_name   AS fk_key_name,
           pk.constraint_name   AS pk_key_name,
           1                    AS update_rule,
           1                    AS delete_rule
    FROM duckdb_constraints() AS fk
    JOIN duckdb_constraints() AS pk
      ON (fk.referenced_table = pk.table_name
          AND fk.constraint_type = 'FOREIGN KEY'
          AND pk.constraint_type = 'PRIMARY KEY')
) WHERE {filter}
ORDER BY pk_catalog_name, pk_schema_name, pk_table_name, pk_key_name, key_sequence\
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_flight_info_for_command(
    descriptor: flight.FlightDescriptor,
    schema: pa.Schema,
) -> flight.FlightInfo:
    """Build a ``FlightInfo`` from a descriptor and schema.

    Mirrors the C++ ``GetFlightInfoForCommand`` free function.
    """
    endpoints = [flight.FlightEndpoint(flight.Ticket(descriptor.command), [])]
    return flight.FlightInfo(schema, descriptor, endpoints, -1, -1)


def _execute_query(
    conn: duckdb.DuckDBPyConnection,
    sql: str,
    params: list[object] | None = None,
) -> pa.Table:
    """Execute *sql* on *conn* and return an Arrow Table.

    Args:
        conn: DuckDB cursor / connection.
        sql: SQL query string.
        params: Optional positional parameters for parameter binding.

    Returns:
        The query result as a ``pyarrow.Table``.
    """
    result = conn.execute(sql, params) if params else conn.execute(sql)
    return result.fetch_arrow_table()


# Mapping from DuckDB type names to PyArrow types (for parameter inference).
_DUCKDB_TO_ARROW: dict[str, pa.DataType] = {
    "INTEGER": pa.int32(),
    "INT": pa.int32(),
    "INT4": pa.int32(),
    "BIGINT": pa.int64(),
    "INT8": pa.int64(),
    "SMALLINT": pa.int16(),
    "INT2": pa.int16(),
    "TINYINT": pa.int8(),
    "HUGEINT": pa.int64(),
    "UINTEGER": pa.uint32(),
    "UBIGINT": pa.uint64(),
    "USMALLINT": pa.uint16(),
    "UTINYINT": pa.uint8(),
    "FLOAT": pa.float32(),
    "REAL": pa.float32(),
    "FLOAT4": pa.float32(),
    "DOUBLE": pa.float64(),
    "FLOAT8": pa.float64(),
    "VARCHAR": pa.utf8(),
    "TEXT": pa.utf8(),
    "STRING": pa.utf8(),
    "BOOLEAN": pa.bool_(),
    "BOOL": pa.bool_(),
    "DATE": pa.date32(),
    # JDBC prepared statements bind java.sql.Timestamp as an instant. Mark the
    # Arrow parameter as UTC to keep the client from shifting the wall-clock
    # value before it reaches the server.
    "TIMESTAMP": pa.timestamp("ms", tz="UTC"),
    "TIMESTAMP WITH TIME ZONE": pa.timestamp("ms", tz="UTC"),
    "BLOB": pa.binary(),
}


def _infer_parameter_schema(
    cursor: duckdb.DuckDBPyConnection,
    query: str,
    param_count: int,
) -> pa.Schema:
    """Try to infer Arrow types for ``?`` placeholders in *query*.

    For INSERT/UPDATE/DELETE, describes the target table and maps column
    types to Arrow types.  Falls back to ``pa.utf8()`` on failure.
    """
    import re

    try:
        # Extract table name from INSERT INTO <table> / UPDATE <table> / DELETE FROM <table>
        match = re.match(
            r"\s*(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+([^\s(]+)",
            query,
            re.IGNORECASE,
        )
        if match:
            table = match.group(1)
            desc = cursor.execute(f"DESCRIBE {table}").fetchall()
            # desc rows: (column_name, column_type, null, key, default, extra)
            col_types = [row[1].upper() for row in desc]
            fields: list[pa.Field] = []
            for i in range(param_count):
                if i < len(col_types):
                    arrow_t = _DUCKDB_TO_ARROW.get(col_types[i], pa.utf8())
                else:
                    arrow_t = pa.utf8()
                fields.append(pa.field(f"parameter_{i + 1}", arrow_t))
            return pa.schema(fields)
    except Exception:
        pass

    # Fallback: all params as utf8
    return pa.schema([pa.field(f"parameter_{i + 1}", pa.utf8()) for i in range(param_count)])


def _record_batch_stream(table: pa.Table) -> flight.RecordBatchStream:
    """Wrap a ``pa.Table`` into a ``RecordBatchStream``."""
    return flight.RecordBatchStream(table)


def _arrow_type_to_sql(arrow_type: pa.DataType) -> str:
    """Map a PyArrow type to a DuckDB SQL type name for CREATE TABLE."""
    mapping: dict[str, str] = {
        "bool": "BOOLEAN",
        "int8": "TINYINT",
        "int16": "SMALLINT",
        "int32": "INTEGER",
        "int64": "BIGINT",
        "uint8": "UTINYINT",
        "uint16": "USMALLINT",
        "uint32": "UINTEGER",
        "uint64": "UBIGINT",
        "float16": "FLOAT",
        "float": "FLOAT",
        "double": "DOUBLE",
        "string": "VARCHAR",
        "large_string": "VARCHAR",
        "utf8": "VARCHAR",
        "large_utf8": "VARCHAR",
        "binary": "BLOB",
        "large_binary": "BLOB",
        "date32": "DATE",
        "date32[day]": "DATE",
        "timestamp[us]": "TIMESTAMP",
        "timestamp[ms]": "TIMESTAMP",
        "timestamp[ns]": "TIMESTAMP",
        "timestamp[s]": "TIMESTAMP",
        "time64[us]": "TIME",
        "time32[ms]": "TIME",
    }
    type_str = str(arrow_type)
    if type_str.startswith("decimal"):
        return type_str.upper()  # e.g. DECIMAL(18,3)
    if type_str.startswith("list") or type_str.startswith("large_list"):
        return "VARCHAR[]"  # fallback
    return mapping.get(type_str, "VARCHAR")


@dataclass
class _PreparedMeta:
    """Server-side metadata for a prepared statement.

    Stored alongside the DuckDB cursor (in SessionManager) so that
    ``get_flight_info_prepared_statement`` can return the real schema and
    ``do_put_prepared_statement_query`` can re-execute with params.
    """

    query: str
    schema: pa.Schema


def _get_session_id(context: flight.ServerCallContext) -> str:
    """Extract a session identifier from the call context.

    For now, uses the peer identity.  Once auth middleware is integrated
    this will return the authenticated session-id from the middleware token.
    """
    return context.peer() or "anonymous"


# ---------------------------------------------------------------------------
# PrepareQueryForGetTables (mirrored from duckdb_server.cpp)
# ---------------------------------------------------------------------------
def _prepare_get_tables_query(
    command: fs.CommandGetTables,
) -> tuple[str, list[object]]:
    """Build the SQL query and bind parameters for ``GetTables``.

    Mirrors C++ ``PrepareQueryForGetTables``.
    """
    params: list[object] = []
    query = (
        "SELECT table_catalog AS catalog_name, table_schema AS db_schema_name, "
        "table_name, table_type FROM information_schema.tables WHERE 1 = 1"
    )

    query += " AND table_catalog = "
    if command.catalog:
        query += "?"
        params.append(command.catalog)
    else:
        query += "CURRENT_DATABASE()"

    if command.db_schema_filter_pattern:
        query += " AND table_schema LIKE ?"
        params.append(command.db_schema_filter_pattern)

    if command.table_name_filter_pattern:
        query += " AND table_name LIKE ?"
        params.append(command.table_name_filter_pattern)

    if command.table_types:
        placeholders = ", ".join("?" for _ in command.table_types)
        query += f" AND table_type IN ({placeholders})"
        params.extend(command.table_types)

    query += " ORDER BY catalog_name, db_schema_name, table_name"
    return query, params


# ---------------------------------------------------------------------------
# Flight SQL SqlSchema helpers — known schemas for metadata endpoints
# ---------------------------------------------------------------------------
_CATALOGS_SCHEMA = pa.schema([pa.field("catalog_name", pa.utf8(), nullable=False)])

_DB_SCHEMAS_SCHEMA = pa.schema(
    [
        pa.field("catalog_name", pa.utf8()),
        pa.field("db_schema_name", pa.utf8(), nullable=False),
    ]
)

_TABLES_SCHEMA = pa.schema(
    [
        pa.field("catalog_name", pa.utf8()),
        pa.field("db_schema_name", pa.utf8()),
        pa.field("table_name", pa.utf8()),
        pa.field("table_type", pa.utf8()),
    ]
)

_TABLES_SCHEMA_WITH_SCHEMA = pa.schema(
    [
        pa.field("catalog_name", pa.utf8()),
        pa.field("db_schema_name", pa.utf8()),
        pa.field("table_name", pa.utf8()),
        pa.field("table_type", pa.utf8()),
        pa.field("table_schema", pa.binary()),
    ]
)

_TABLE_TYPES_SCHEMA = pa.schema([pa.field("table_type", pa.utf8())])

_PRIMARY_KEYS_SCHEMA = pa.schema(
    [
        pa.field("catalog_name", pa.utf8()),
        pa.field("schema_name", pa.utf8()),
        pa.field("table_name", pa.utf8()),
        pa.field("column_name", pa.utf8()),
        pa.field("key_sequence", pa.int32()),
        pa.field("key_name", pa.utf8()),
    ]
)

_FK_KEYS_SCHEMA = pa.schema(
    [
        pa.field("pk_catalog_name", pa.utf8()),
        pa.field("pk_schema_name", pa.utf8()),
        pa.field("pk_table_name", pa.utf8()),
        pa.field("pk_column_name", pa.utf8()),
        pa.field("fk_catalog_name", pa.utf8()),
        pa.field("fk_schema_name", pa.utf8()),
        pa.field("fk_table_name", pa.utf8()),
        pa.field("fk_column_name", pa.utf8()),
        pa.field("key_sequence", pa.int32()),
        pa.field("fk_key_name", pa.utf8()),
        pa.field("pk_key_name", pa.utf8()),
        pa.field("update_rule", pa.int32()),
        pa.field("delete_rule", pa.int32()),
    ]
)

# ---------------------------------------------------------------------------
# XDBC type info schema + hardcoded DuckDB types
# (mirrored from duckdb_type_info.cpp)
# ---------------------------------------------------------------------------
_XDBC_TYPE_INFO_SCHEMA = pa.schema(
    [
        pa.field("type_name", pa.utf8(), nullable=False),
        pa.field("data_type", pa.int32(), nullable=False),
        pa.field("column_size", pa.int32()),
        pa.field("literal_prefix", pa.utf8()),
        pa.field("literal_suffix", pa.utf8()),
        pa.field("create_params", pa.list_(pa.utf8())),
        pa.field("nullable", pa.int32(), nullable=False),
        pa.field("case_sensitive", pa.bool_(), nullable=False),
        pa.field("searchable", pa.int32(), nullable=False),
        pa.field("unsigned_attribute", pa.bool_()),
        pa.field("fixed_prec_scale", pa.bool_(), nullable=False),
        pa.field("auto_increment", pa.bool_()),
        pa.field("local_type_name", pa.utf8()),
        pa.field("minimum_scale", pa.int32()),
        pa.field("maximum_scale", pa.int32()),
        pa.field("sql_data_type", pa.int32(), nullable=False),
        pa.field("datetime_subcode", pa.int32()),
        pa.field("num_prec_radix", pa.int32()),
        pa.field("interval_precision", pa.int32()),
    ]
)

# Each row: (type_name, data_type, column_size, literal_prefix, literal_suffix,
#            create_params, nullable, case_sensitive, searchable,
#            unsigned_attribute, fixed_prec_scale, auto_increment,
#            local_type_name, minimum_scale, maximum_scale,
#            sql_data_type, datetime_subcode, num_prec_radix, interval_precision)
_XDBC_TYPE_ROWS: list[
    tuple[
        str,
        int,
        int,
        str | None,
        str | None,
        list[str],
        int,
        bool,
        int,
        bool,
        bool,
        bool,
        str,
        int,
        int,
        int,
        int,
        int,
        int,
    ]
] = [
    # (type_name, data_type, col_size, lit_pre, lit_suf, create_params,
    #  nullable, case_sens, searchable, unsigned, fixed_prec, auto_inc,
    #  local_name, min_scale, max_scale, sql_dt, dt_sub, prec_radix, intv)
    (
        "boolean",
        16,
        1,
        None,
        None,
        [],
        1,
        False,
        3,
        False,
        False,
        False,
        "boolean",
        0,
        0,
        16,
        0,
        0,
        0,
    ),
    (
        "tinyint",
        -6,
        3,
        None,
        None,
        [],
        1,
        False,
        3,
        False,
        False,
        False,
        "tinyint",
        0,
        0,
        -6,
        0,
        0,
        0,
    ),
    (
        "smallint",
        5,
        5,
        None,
        None,
        [],
        1,
        False,
        3,
        False,
        False,
        False,
        "smallint",
        0,
        0,
        5,
        0,
        0,
        0,
    ),
    (
        "integer",
        4,
        10,
        None,
        None,
        [],
        1,
        False,
        3,
        False,
        False,
        False,
        "integer",
        0,
        0,
        4,
        0,
        0,
        0,
    ),
    (
        "bigint",
        -5,
        19,
        None,
        None,
        [],
        1,
        False,
        3,
        False,
        False,
        False,
        "bigint",
        0,
        0,
        -5,
        0,
        0,
        0,
    ),
    (
        "hugeint",
        -5,
        38,
        None,
        None,
        [],
        1,
        False,
        3,
        False,
        False,
        False,
        "hugeint",
        0,
        0,
        -5,
        0,
        0,
        0,
    ),
    ("float", 6, 7, None, None, [], 1, False, 3, False, False, False, "float", 0, 0, 6, 0, 0, 0),
    (
        "double",
        8,
        15,
        None,
        None,
        [],
        1,
        False,
        3,
        False,
        False,
        False,
        "double",
        0,
        0,
        8,
        0,
        0,
        0,
    ),
    (
        "decimal",
        3,
        38,
        None,
        None,
        [],
        1,
        False,
        3,
        False,
        False,
        False,
        "decimal",
        0,
        0,
        3,
        0,
        0,
        0,
    ),
    (
        "varchar",
        12,
        255,
        "'",
        "'",
        ["length"],
        1,
        False,
        3,
        False,
        False,
        False,
        "varchar",
        0,
        0,
        12,
        0,
        0,
        0,
    ),
    (
        "text",
        -1,
        65536,
        "'",
        "'",
        ["length"],
        1,
        False,
        3,
        False,
        False,
        False,
        "text",
        0,
        0,
        -1,
        0,
        0,
        0,
    ),
    ("date", 91, 10, "'", "'", [], 1, False, 3, False, False, False, "date", 0, 0, 91, 0, 0, 0),
    ("time", 92, 8, "'", "'", [], 1, False, 3, False, False, False, "time", 0, 0, 92, 0, 0, 0),
    (
        "timestamp",
        93,
        32,
        "'",
        "'",
        [],
        1,
        False,
        3,
        False,
        False,
        False,
        "timestamp",
        0,
        0,
        93,
        0,
        0,
        0,
    ),
]

# Pre-sorted data_type values for filtering (matches C++ data_type_vector order)
_XDBC_DATA_TYPES = [row[1] for row in _XDBC_TYPE_ROWS]


def _build_xdbc_type_info_table(
    data_type_filter: int | None = None,
) -> pa.Table:
    """Build the XDBC type info ``pa.Table``.

    If *data_type_filter* is given, only rows matching that JDBC data type are
    included (mirroring C++ ``DoGetTypeInfoResult(int)``).
    """
    rows = _XDBC_TYPE_ROWS
    if data_type_filter is not None:
        rows = [r for r in rows if r[1] == data_type_filter]

    columns: dict[str, list[object]] = {f.name: [] for f in _XDBC_TYPE_INFO_SCHEMA}
    for row in rows:
        for i, f in enumerate(_XDBC_TYPE_INFO_SCHEMA):
            columns[f.name].append(row[i])

    arrays = []
    for f in _XDBC_TYPE_INFO_SCHEMA:
        arrays.append(pa.array(columns[f.name], type=f.type))
    return pa.table(
        dict(
            zip(
                [f.name for f in _XDBC_TYPE_INFO_SCHEMA],
                arrays,
                strict=True,
            )
        ),
        schema=_XDBC_TYPE_INFO_SCHEMA,
    )


# ---------------------------------------------------------------------------
# SQL Info schema + server metadata
# (mirrored from duckdb_sql_info.cpp / Flight SQL spec)
# ---------------------------------------------------------------------------
_SQL_INFO_UNION_TYPE = pa.dense_union(
    [
        pa.field("string_value", pa.utf8()),
        pa.field("bool_value", pa.bool_()),
        pa.field("bigint_value", pa.int64()),
        pa.field("int32_bitmask", pa.int32()),
        pa.field("string_list", pa.list_(pa.utf8())),
        pa.field(
            "int32_to_int32_list_map",
            pa.map_(pa.int32(), pa.list_(pa.int32())),
        ),
    ]
)

_SQL_INFO_SCHEMA = pa.schema(
    [
        pa.field("info_name", pa.uint32()),
        pa.field("value", _SQL_INFO_UNION_TYPE),
    ]
)

# SqlInfo enum constants (matching Flight SQL protobuf values)
_FLIGHT_SQL_SERVER_NAME = 0
_FLIGHT_SQL_SERVER_VERSION = 1
_FLIGHT_SQL_SERVER_ARROW_VERSION = 2
_FLIGHT_SQL_SERVER_READ_ONLY = 500
_FLIGHT_SQL_SERVER_SQL = 501
_FLIGHT_SQL_SERVER_SUBSTRAIT = 502
_FLIGHT_SQL_SERVER_TRANSACTION = 504
_FLIGHT_SQL_SERVER_CANCEL = 505
_FLIGHT_SQL_SERVER_BULK_INGESTION = 507
_FLIGHT_SQL_SERVER_INGEST_TRANSACTIONS_SUPPORTED = 508
_FLIGHT_SQL_SERVER_STATEMENT_TIMEOUT = 100
_FLIGHT_SQL_SERVER_TRANSACTION_TIMEOUT = 101
_SQL_DDL_CATALOG = 500
_SQL_DDL_SCHEMA = 501
_SQL_DDL_TABLE = 502
_SQL_IDENTIFIER_QUOTE_CHAR = 503
_SQL_IDENTIFIER_CASE = 504


def _build_sql_info_table(
    info_ids: list[int] | None = None,
) -> pa.Table:
    """Build the ``SqlInfo`` result table.

    The server metadata map is constructed inline (matching the C++ original).
    When *info_ids* is ``None`` or empty, all known entries are returned;
    otherwise only the requested subset.
    """
    # Type codes for the dense union: 0=string, 1=bool, 2=int64, 3=int32
    # Entries: (info_name, type_code, value)
    entries: list[tuple[int, int, object]] = [
        (_FLIGHT_SQL_SERVER_NAME, 0, "lakehouse"),
        (_FLIGHT_SQL_SERVER_VERSION, 0, f"duckdb {duckdb.__duckdb_version__}"),
        (_FLIGHT_SQL_SERVER_ARROW_VERSION, 0, pa.__version__),
        (_FLIGHT_SQL_SERVER_READ_ONLY, 1, False),
        (_FLIGHT_SQL_SERVER_SQL, 1, True),
        (_FLIGHT_SQL_SERVER_SUBSTRAIT, 1, False),
        (_FLIGHT_SQL_SERVER_TRANSACTION, 2, 1),  # TRANSACTION supported
        (_FLIGHT_SQL_SERVER_CANCEL, 1, True),
        (_FLIGHT_SQL_SERVER_BULK_INGESTION, 1, True),
        (_FLIGHT_SQL_SERVER_INGEST_TRANSACTIONS_SUPPORTED, 1, True),
        (_FLIGHT_SQL_SERVER_STATEMENT_TIMEOUT, 3, 0),  # no timeout
        (_FLIGHT_SQL_SERVER_TRANSACTION_TIMEOUT, 3, 0),  # no timeout
    ]

    # Filter if specific IDs requested
    if info_ids:
        requested = set(info_ids)
        entries = [e for e in entries if e[0] in requested]

    # Build the dense union column
    info_names: list[int] = []
    type_codes_list: list[int] = []
    # Child arrays: one list per union type (indexed by type_code)
    children: list[list[object]] = [[], [], [], [], [], []]

    for info_name, type_code, value in entries:
        info_names.append(info_name)
        type_codes_list.append(type_code)
        children[type_code].append(value)

    offsets: list[int] = []
    child_counts = [0, 0, 0, 0, 0, 0]
    for tc in type_codes_list:
        offsets.append(child_counts[tc])
        child_counts[tc] += 1

    child_arrays = [
        pa.array(children[0], type=pa.utf8()),
        pa.array(children[1], type=pa.bool_()),
        pa.array(children[2], type=pa.int64()),
        pa.array(children[3], type=pa.int32()),
        pa.array(children[4], type=pa.list_(pa.utf8())),
        pa.array(children[5], type=pa.map_(pa.int32(), pa.list_(pa.int32()))),
    ]

    union_arr = pa.UnionArray.from_dense(
        pa.array(type_codes_list, type=pa.int8()),
        pa.array(offsets, type=pa.int32()),
        child_arrays,
        field_names=[
            "string_value",
            "bool_value",
            "bigint_value",
            "int32_bitmask",
            "string_list",
            "int32_to_int32_list_map",
        ],
    )

    return pa.table(
        {
            "info_name": pa.array(info_names, type=pa.uint32()),
            "value": union_arr,
        }
    )


# ---------------------------------------------------------------------------
# DuckDBFlightSqlServer
# ---------------------------------------------------------------------------
class DuckDBFlightSqlServer(FlightSqlServer):
    """Flight SQL server backed by an in-memory DuckDB database.

    Inherits dispatch logic from :class:`FlightSqlServer` and implements
    every handler stub with real DuckDB execution.

    Args:
        location: gRPC listen address (e.g. ``"grpc://0.0.0.0:31337"``).
        db_path: DuckDB database path.  Defaults to ``":memory:"``.
        **kwargs: Forwarded to :class:`FlightSqlServer`.
    """

    def __init__(
        self,
        location: str = "grpc://0.0.0.0:31337",
        *,
        db_path: str = ":memory:",
        ducklake_alias: str = "",
        **kwargs: object,
    ) -> None:
        """Initialise the DuckDB Flight SQL server."""
        super().__init__(location, **kwargs)
        self._db = duckdb.connect(db_path)
        self._sessions = SessionManager(self._db, ducklake_alias=ducklake_alias)
        self._prepared_meta: dict[tuple[str, str], _PreparedMeta] = {}
        logger.info(
            "DuckDBFlightSqlServer initialised (db=%s, location=%s)",
            db_path,
            location,
        )

    # -- helpers -----------------------------------------------------------

    def _get_session(self, context: flight.ServerCallContext) -> duckdb.DuckDBPyConnection:
        """Resolve the DuckDB cursor for the current caller.

        Creates a session (and underlying DuckDB cursor) on first access.
        """
        session_id = _get_session_id(context)
        session = self._sessions.get_or_create(session_id)
        return session.connection

    def shutdown(self) -> None:
        """Gracefully shut down: close all sessions and DuckDB instance."""
        self._sessions.close_all()
        self._db.close()
        super().shutdown()

    # ═══════════════════════════════════════════════════════════════════════
    #  get_flight_info handlers
    # ═══════════════════════════════════════════════════════════════════════

    def get_flight_info_statement(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandStatementQuery,
        descriptor: flight.FlightDescriptor,
    ) -> flight.FlightInfo:
        """Execute the query to compute schema, return ``FlightInfo``.

        Mirrors C++ ``GetFlightInfoStatement``: prepare the query to
        determine output schema, then build a ``FlightInfo`` with that
        schema and a ticket containing the SQL.
        """
        conn = self._get_session(context)
        query = command.query
        # Use LIMIT 0 trick to get the schema without reading data
        schema_query = f"SELECT * FROM ({query}) AS __schema_probe LIMIT 0"
        table = _execute_query(conn, schema_query)
        schema = table.schema

        # Build ticket containing the original query
        ticket_msg = fs.TicketStatementQuery(statement_handle=query.encode("utf-8"))
        ticket_bytes = pack_any(ticket_msg).SerializeToString()
        endpoints = [flight.FlightEndpoint(flight.Ticket(ticket_bytes), [])]
        return flight.FlightInfo(schema, descriptor, endpoints, -1, -1)

    def get_flight_info_prepared_statement(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandPreparedStatementQuery,
        descriptor: flight.FlightDescriptor,
    ) -> flight.FlightInfo:
        """Return ``FlightInfo`` for a prepared statement.

        When the prepared statement has an empty schema (DDL/DML such as
        ``CREATE TABLE``, ``INSERT``, ``UPDATE``, etc.), ADBC clients will
        **not** follow up with a ``DoGet`` call — they see the empty schema
        and assume there are no results.  Without eager execution here, the
        SQL would never actually run.

        JDBC clients use a completely different path
        (``DoPut(CommandStatementUpdate)``) for DDL/DML, so this does not
        affect them.
        """
        session_id = _get_session_id(context)
        handle = command.prepared_statement_handle.decode("utf-8")
        meta = self._prepared_meta.get((session_id, handle))
        schema = meta.schema if meta is not None else pa.schema([])

        # DDL/DML: empty schema means ADBC won't call DoGet, so execute now.
        # Skip parameterised queries (they go through DoPut for binding).
        if len(schema) == 0 and meta is not None and "?" not in meta.query:
            # Execute on the session connection (not the prepared-statement
            # child cursor) so that transaction state (BEGIN/COMMIT/ROLLBACK)
            # and table mutations share the same cursor context.
            session = self._sessions.get_or_create(session_id)
            try:
                session.connection.execute(meta.query)
                logger.debug("Eagerly executed DDL/DML: %s", meta.query[:120])
            except Exception:
                logger.exception("Failed to eagerly execute: %s", meta.query[:120])
                raise

        return _get_flight_info_for_command(descriptor, schema)

    def get_flight_info_catalogs(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetCatalogs,
        descriptor: flight.FlightDescriptor,
    ) -> flight.FlightInfo:
        """Return ``FlightInfo`` for ``GetCatalogs``."""
        return _get_flight_info_for_command(descriptor, _CATALOGS_SCHEMA)

    def get_flight_info_db_schemas(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetDbSchemas,
        descriptor: flight.FlightDescriptor,
    ) -> flight.FlightInfo:
        """Return ``FlightInfo`` for ``GetDbSchemas``."""
        return _get_flight_info_for_command(descriptor, _DB_SCHEMAS_SCHEMA)

    def get_flight_info_tables(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetTables,
        descriptor: flight.FlightDescriptor,
    ) -> flight.FlightInfo:
        """Return ``FlightInfo`` for ``GetTables``."""
        schema = _TABLES_SCHEMA_WITH_SCHEMA if command.include_schema else _TABLES_SCHEMA
        return _get_flight_info_for_command(descriptor, schema)

    def get_flight_info_table_types(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetTableTypes,
        descriptor: flight.FlightDescriptor,
    ) -> flight.FlightInfo:
        """Return ``FlightInfo`` for ``GetTableTypes``."""
        return _get_flight_info_for_command(descriptor, _TABLE_TYPES_SCHEMA)

    def get_flight_info_primary_keys(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetPrimaryKeys,
        descriptor: flight.FlightDescriptor,
    ) -> flight.FlightInfo:
        """Return ``FlightInfo`` for ``GetPrimaryKeys``."""
        return _get_flight_info_for_command(descriptor, _PRIMARY_KEYS_SCHEMA)

    def get_flight_info_imported_keys(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetImportedKeys,
        descriptor: flight.FlightDescriptor,
    ) -> flight.FlightInfo:
        """Return ``FlightInfo`` for ``GetImportedKeys``."""
        return _get_flight_info_for_command(descriptor, _FK_KEYS_SCHEMA)

    def get_flight_info_exported_keys(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetExportedKeys,
        descriptor: flight.FlightDescriptor,
    ) -> flight.FlightInfo:
        """Return ``FlightInfo`` for ``GetExportedKeys``."""
        return _get_flight_info_for_command(descriptor, _FK_KEYS_SCHEMA)

    def get_flight_info_cross_reference(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetCrossReference,
        descriptor: flight.FlightDescriptor,
    ) -> flight.FlightInfo:
        """Return ``FlightInfo`` for ``GetCrossReference``."""
        return _get_flight_info_for_command(descriptor, _FK_KEYS_SCHEMA)

    def get_flight_info_xdbc_type_info(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetXdbcTypeInfo,
        descriptor: flight.FlightDescriptor,
    ) -> flight.FlightInfo:
        """Return ``FlightInfo`` for ``GetXdbcTypeInfo``.

        Mirrors C++ ``GetFlightInfoTypeInfo``.
        """
        return _get_flight_info_for_command(descriptor, _XDBC_TYPE_INFO_SCHEMA)

    def get_flight_info_sql_info(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetSqlInfo,
        descriptor: flight.FlightDescriptor,
    ) -> flight.FlightInfo:
        """Return ``FlightInfo`` for ``GetSqlInfo``.

        Mirrors C++ ``GetFlightInfoSqlInfo`` (built in to
        ``FlightSqlServerBase``).
        """
        return _get_flight_info_for_command(descriptor, _SQL_INFO_SCHEMA)

    # ═══════════════════════════════════════════════════════════════════════
    #  do_get handlers
    # ═══════════════════════════════════════════════════════════════════════

    def do_get_statement(
        self,
        context: flight.ServerCallContext,
        command: fs.TicketStatementQuery,
    ) -> flight.RecordBatchStream:
        """Execute the SQL query and stream Arrow record batches.

        Mirrors C++ ``DoGetStatement``.
        """
        conn = self._get_session(context)
        sql = command.statement_handle.decode("utf-8")
        table = _execute_query(conn, sql)
        return _record_batch_stream(table)

    def do_get_prepared_statement(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandPreparedStatementQuery,
    ) -> flight.RecordBatchStream:
        """Execute a prepared statement and stream results.

        If parameters were already bound via ``DoPut``, the cursor holds
        pending results.  Otherwise the query is executed now (no params).
        """
        session_id = _get_session_id(context)
        handle = command.prepared_statement_handle.decode("utf-8")
        self._sessions.get_or_create(session_id)  # ensure session exists
        cursor = self._sessions.get_prepared_statement(session_id, handle)
        meta = self._prepared_meta.get((session_id, handle))

        # DoPut (if called) already executed with params; try fetching directly.
        try:
            table = cursor.fetch_arrow_table()
        except Exception:
            table = None

        if table is None and meta is not None:
            # No prior execution — run the query now (parameterless path).
            table = _execute_query(cursor, meta.query)

        if table is None:
            table = pa.table({})

        return _record_batch_stream(table)

    def do_get_catalogs(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetCatalogs,
    ) -> flight.RecordBatchStream:
        """Return catalog names from ``information_schema.schemata``.

        Mirrors C++ ``DoGetCatalogs``.
        """
        conn = self._get_session(context)
        table = _execute_query(conn, _CATALOGS_QUERY)
        table = table.cast(_CATALOGS_SCHEMA)
        return _record_batch_stream(table)

    def do_get_db_schemas(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetDbSchemas,
    ) -> flight.RecordBatchStream:
        """Return database schemas with optional filtering.

        Mirrors C++ ``DoGetDbSchemas``.
        """
        conn = self._get_session(context)
        params: list[object] = []
        query = _DB_SCHEMAS_QUERY_BASE

        query += " AND catalog_name = "
        if command.catalog:
            query += "?"
            params.append(command.catalog)
        else:
            query += "CURRENT_DATABASE()"

        if command.db_schema_filter_pattern:
            query += " AND schema_name LIKE ?"
            params.append(command.db_schema_filter_pattern)

        query += " ORDER BY catalog_name, db_schema_name"
        table = _execute_query(conn, query, params or None)
        table = table.cast(_DB_SCHEMAS_SCHEMA)
        return _record_batch_stream(table)

    def do_get_tables(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetTables,
    ) -> flight.RecordBatchStream:
        """Return table metadata with optional filtering.

        Mirrors C++ ``DoGetTables``.  When ``include_schema`` is set, an
        extra binary column ``table_schema`` is appended containing the
        IPC-serialized Arrow schema for each table.
        """
        conn = self._get_session(context)
        query, params = _prepare_get_tables_query(command)
        table = _execute_query(conn, query, params or None)

        if command.include_schema:
            schemas: list[bytes] = []
            for i in range(table.num_rows):
                catalog = table.column("catalog_name")[i].as_py()
                db_schema = table.column("db_schema_name")[i].as_py()
                tbl_name = table.column("table_name")[i].as_py()
                schema_sql = f'SELECT * FROM "{catalog}"."{db_schema}"."{tbl_name}" LIMIT 0'
                schema_table = _execute_query(conn, schema_sql)
                buf = schema_table.schema.serialize().to_pybytes()
                schemas.append(buf)

            schema_col = pa.array(schemas, type=pa.binary())
            table = table.append_column(pa.field("table_schema", pa.binary()), schema_col)
            table = table.cast(_TABLES_SCHEMA_WITH_SCHEMA)
        else:
            table = table.cast(_TABLES_SCHEMA)

        return _record_batch_stream(table)

    def do_get_table_types(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetTableTypes,
    ) -> flight.RecordBatchStream:
        """Return supported table types.

        Mirrors C++ ``DoGetTableTypes``.
        """
        conn = self._get_session(context)
        table = _execute_query(conn, _TABLE_TYPES_QUERY)
        table = table.cast(_TABLE_TYPES_SCHEMA)
        return _record_batch_stream(table)

    def do_get_primary_keys(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetPrimaryKeys,
    ) -> flight.RecordBatchStream:
        """Return primary key info for a table.

        Mirrors C++ ``DoGetPrimaryKeys``.
        """
        conn = self._get_session(context)
        params: list[object] = []
        query = _PRIMARY_KEYS_QUERY_BASE

        query += " AND catalog_name = "
        if command.catalog:
            query += "?"
            params.append(command.catalog)
        else:
            query += "CURRENT_DATABASE()"

        if command.db_schema:
            query += " AND schema_name LIKE ?"
            params.append(command.db_schema)

        query += " AND table_name LIKE ?"
        params.append(command.table)

        table = _execute_query(conn, query, params)
        table = table.cast(_PRIMARY_KEYS_SCHEMA)
        return _record_batch_stream(table)

    def do_get_imported_keys(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetImportedKeys,
    ) -> flight.RecordBatchStream:
        """Return foreign keys that reference other tables' primary keys.

        Mirrors C++ ``DoGetImportedKeys``.
        """
        filter_parts = ["fk_table_name = ?"]
        params: list[object] = [command.table]

        filter_parts.append("fk_catalog_name = ")
        if command.catalog:
            filter_parts[-1] += "?"
            params.append(command.catalog)
        else:
            filter_parts[-1] += "CURRENT_DATABASE()"

        if command.db_schema:
            filter_parts.append("fk_schema_name = ?")
            params.append(command.db_schema)

        conn = self._get_session(context)
        query = _IMPORTED_EXPORTED_KEYS_QUERY.format(filter=" AND ".join(filter_parts))
        table = _execute_query(conn, query, params)
        table = table.cast(_FK_KEYS_SCHEMA)
        return _record_batch_stream(table)

    def do_get_exported_keys(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetExportedKeys,
    ) -> flight.RecordBatchStream:
        """Return foreign keys that reference a table's primary key.

        Mirrors C++ ``DoGetExportedKeys``.
        """
        filter_parts = ["pk_table_name = ?"]
        params: list[object] = [command.table]

        filter_parts.append("pk_catalog_name = ")
        if command.catalog:
            filter_parts[-1] += "?"
            params.append(command.catalog)
        else:
            filter_parts[-1] += "CURRENT_DATABASE()"

        if command.db_schema:
            filter_parts.append("pk_schema_name = ?")
            params.append(command.db_schema)

        conn = self._get_session(context)
        query = _IMPORTED_EXPORTED_KEYS_QUERY.format(filter=" AND ".join(filter_parts))
        table = _execute_query(conn, query, params)
        table = table.cast(_FK_KEYS_SCHEMA)
        return _record_batch_stream(table)

    def do_get_cross_reference(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetCrossReference,
    ) -> flight.RecordBatchStream:
        """Return cross-reference (FK→PK relationship) between two tables.

        Mirrors C++ ``DoGetCrossReference``.
        """
        filter_parts = ["pk_table_name = ?"]
        params: list[object] = [command.pk_table]

        filter_parts.append("pk_catalog_name = ")
        if command.pk_catalog:
            filter_parts[-1] += "?"
            params.append(command.pk_catalog)
        else:
            filter_parts[-1] += "CURRENT_DATABASE()"

        if command.pk_db_schema:
            filter_parts.append("pk_schema_name = ?")
            params.append(command.pk_db_schema)

        filter_parts.append("fk_table_name = ?")
        params.append(command.fk_table)

        filter_parts.append("fk_catalog_name = ")
        if command.fk_catalog:
            filter_parts[-1] += "?"
            params.append(command.fk_catalog)
        else:
            filter_parts[-1] += "CURRENT_DATABASE()"

        if command.fk_db_schema:
            filter_parts.append("fk_schema_name = ?")
            params.append(command.fk_db_schema)

        conn = self._get_session(context)
        query = _IMPORTED_EXPORTED_KEYS_QUERY.format(filter=" AND ".join(filter_parts))
        table = _execute_query(conn, query, params)
        table = table.cast(_FK_KEYS_SCHEMA)
        return _record_batch_stream(table)

    def do_get_xdbc_type_info(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetXdbcTypeInfo,
    ) -> flight.RecordBatchStream:
        """Return XDBC/JDBC type information.

        Mirrors C++ ``DoGetXdbcTypeInfo`` / ``DoGetTypeInfo``.
        Optionally filters by ``data_type`` when set in the command.
        """
        data_type_filter = command.data_type if command.data_type else None
        table = _build_xdbc_type_info_table(data_type_filter)
        return _record_batch_stream(table)

    def do_get_sql_info(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandGetSqlInfo,
    ) -> flight.RecordBatchStream:
        """Return server SQL metadata.

        Mirrors C++ ``DoGetSqlInfo`` (built in to ``FlightSqlServerBase``).
        When the client requests specific info IDs, only those are returned;
        otherwise all known entries are sent.
        """
        info_ids = list(command.info) if command.info else None
        table = _build_sql_info_table(info_ids)
        return _record_batch_stream(table)

    # ═══════════════════════════════════════════════════════════════════════
    #  do_put handlers
    # ═══════════════════════════════════════════════════════════════════════

    def do_put_statement_update(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandStatementUpdate,
        reader: flight.MetadataRecordBatchReader,
        writer: flight.FlightMetadataWriter,
    ) -> None:
        """Execute an INSERT/UPDATE/DELETE and write the affected row count.

        Mirrors C++ ``DoPutCommandStatementUpdate``.
        """
        conn = self._get_session(context)
        result = conn.execute(command.query)
        row = result.fetchone()
        row_count = row[0] if row is not None else 0

        # Write the DoPutUpdateResult back (raw serialised — NOT Any-wrapped)
        update_result = fs.DoPutUpdateResult(record_count=row_count)
        writer.write(update_result.SerializeToString())

    def do_put_prepared_statement_update(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandPreparedStatementUpdate,
        reader: flight.MetadataRecordBatchReader,
        writer: flight.FlightMetadataWriter,
    ) -> None:
        """Execute a prepared UPDATE/INSERT/DELETE statement.

        Mirrors C++ ``DoPutPreparedStatementUpdate``.
        """
        session_id = _get_session_id(context)
        handle = command.prepared_statement_handle.decode("utf-8")
        cursor = self._sessions.get_prepared_statement(session_id, handle)
        meta = self._prepared_meta.get((session_id, handle))

        # Read parameter batches and bind
        params: list[object] = []
        try:
            batch = reader.read_chunk()
            if batch.data is not None and batch.data.num_rows > 0:
                for col_idx in range(batch.data.num_columns):
                    params.append(batch.data.column(col_idx)[0].as_py())
        except StopIteration:
            pass

        # Execute and get affected row count
        if meta is not None and params:
            result = cursor.execute(meta.query, params)
        elif meta is not None:
            result = cursor.execute(meta.query)
        else:
            result = cursor.execute("")  # fallback — should not happen

        row = result.fetchone()
        row_count = row[0] if row is not None else 0

        update_result = fs.DoPutUpdateResult(record_count=row_count)
        writer.write(update_result.SerializeToString())

    def do_put_prepared_statement_query(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandPreparedStatementQuery,
        reader: flight.MetadataRecordBatchReader,
        writer: flight.FlightMetadataWriter,
    ) -> None:
        """Bind parameters to a prepared statement.

        Mirrors C++ ``DoPutPreparedStatementQuery``.  Reads parameter
        record batches from *reader* and binds them to the prepared
        statement's cursor by re-executing the stored query with params.
        """
        session_id = _get_session_id(context)
        handle = command.prepared_statement_handle.decode("utf-8")
        cursor = self._sessions.get_prepared_statement(session_id, handle)
        meta = self._prepared_meta.get((session_id, handle))

        if meta is None:
            return  # no metadata — cannot bind

        # Read parameter batches — typically a single batch
        try:
            batch = reader.read_chunk()
            if batch.data is not None and batch.data.num_rows > 0:
                params: list[object] = []
                for col_idx in range(batch.data.num_columns):
                    params.append(batch.data.column(col_idx)[0].as_py())
                cursor.execute(meta.query, params)
        except StopIteration:
            pass

    def do_put_statement_ingest(
        self,
        context: flight.ServerCallContext,
        command: fs.CommandStatementIngest,
        reader: flight.MetadataRecordBatchReader,
        writer: flight.FlightMetadataWriter,
    ) -> None:
        """Bulk-ingest Arrow data into a table.

        Mirrors C++ ``DoPutCommandStatementIngest``.  Handles
        ``table_definition_options`` (if_not_exist / if_exists) and
        reads record batches from *reader* into the target table.
        """
        conn = self._get_session(context)

        # ── build fully-qualified, quoted table name ──────────────────
        def _quote(name: str) -> str:
            return '"' + name.replace('"', '""') + '"'

        parts: list[str] = []
        if command.catalog:
            parts.append(_quote(command.catalog))
        if command.schema:
            parts.append(_quote(command.schema))
        parts.append(_quote(command.table))
        fq_table = ".".join(parts)

        # ── check table existence ─────────────────────────────────────
        exists_query = "SELECT 1 FROM information_schema.tables WHERE table_name = ?"
        exists_params: list[str] = [command.table]
        if command.schema:
            exists_query += " AND table_schema = ?"
            exists_params.append(command.schema)
        if command.catalog:
            exists_query += " AND table_catalog = ?"
            exists_params.append(command.catalog)

        result = conn.execute(exists_query, exists_params).fetchone()
        table_exists = result is not None

        # ── read all data from reader first ───────────────────────────
        batches: list[pa.RecordBatch] = []
        try:
            while True:
                chunk = reader.read_chunk()
                if chunk.data is not None and chunk.data.num_rows > 0:
                    batches.append(chunk.data)
        except StopIteration:
            pass

        if not batches:
            # Nothing to ingest — write zero-row result
            result_record = fs.DoPutUpdateResult(record_count=0)
            buf = result_record.SerializeToString()
            writer.write(buf)
            return

        arrow_table = pa.Table.from_batches(batches)

        # ── handle table_definition_options ────────────────────────────
        opts = command.table_definition_options
        # Enum values from CommandStatementIngest.TableDefinitionOptions:
        #   if_not_exist: UNSPECIFIED=0, CREATE=1, FAIL=2
        #   if_exists:    UNSPECIFIED=0, FAIL=1, APPEND=2, REPLACE=3

        if not table_exists:
            if opts and opts.if_not_exist == 2:  # FAIL
                raise flight.FlightServerError(
                    f"Table {fq_table} does not exist and IF_NOT_EXIST is set to FAIL"
                )
            # Default / CREATE: create the table from Arrow schema
            col_defs: list[str] = []
            for field in arrow_table.schema:
                col_defs.append(f"{_quote(field.name)} {_arrow_type_to_sql(field.type)}")
            create_sql = f"CREATE TABLE {fq_table} ({', '.join(col_defs)})"
            conn.execute(create_sql)
        else:
            if opts:
                if opts.if_exists == 1:  # FAIL
                    raise flight.FlightServerError(
                        f"Table {fq_table} already exists and IF_EXISTS is set to FAIL"
                    )
                if opts.if_exists == 3:  # REPLACE
                    conn.execute(f"DROP TABLE {fq_table}")
                    col_defs = []
                    for field in arrow_table.schema:
                        col_defs.append(f"{_quote(field.name)} {_arrow_type_to_sql(field.type)}")
                    create_sql = f"CREATE TABLE {fq_table} ({', '.join(col_defs)})"
                    conn.execute(create_sql)
                # APPEND (2) or UNSPECIFIED (0): just insert

        # ── insert data ───────────────────────────────────────────────
        conn.execute(f"INSERT INTO {fq_table} SELECT * FROM arrow_table")
        total_rows = arrow_table.num_rows

        result_record = fs.DoPutUpdateResult(record_count=total_rows)
        buf = result_record.SerializeToString()
        writer.write(buf)
        logger.debug(
            "Ingested %d rows into %s",
            total_rows,
            fq_table,
        )

    # ═══════════════════════════════════════════════════════════════════════
    #  do_action handlers
    # ═══════════════════════════════════════════════════════════════════════

    def create_prepared_statement(
        self,
        context: flight.ServerCallContext,
        request: fs.ActionCreatePreparedStatementRequest,
    ) -> fs.ActionCreatePreparedStatementResult:
        """Create a prepared statement and return its handle + schema.

        Mirrors C++ ``CreatePreparedStatement``.  Uses a ``LIMIT 0`` wrapper
        to infer the result schema without actually executing the query.  If
        that fails (DDL, DML, or parameterised queries whose placeholders
        are not yet bound), an empty schema is returned instead.
        """
        session_id = _get_session_id(context)
        self._sessions.get_or_create(session_id)  # ensure session exists
        handle, cursor = self._sessions.add_prepared_statement(session_id)

        query = request.query

        # Try to infer schema via LIMIT 0 trick.  This fails for DDL/DML
        # (e.g. CREATE TABLE) and parameterised queries (unbound ?).
        try:
            schema_sql = f"SELECT * FROM ({query}) AS __ps LIMIT 0"
            schema_table = _execute_query(cursor, schema_sql)
            dataset_schema = schema_table.schema
        except Exception:
            dataset_schema = pa.schema([])

        dataset_schema_bytes = dataset_schema.serialize().to_pybytes()

        # Build parameter schema from placeholder count
        param_count = query.count("?")
        if param_count:
            param_schema = _infer_parameter_schema(cursor, query, param_count)
            param_schema_bytes = param_schema.serialize().to_pybytes()
        else:
            param_schema_bytes = b""

        # Store metadata for later use by get_flight_info / do_put
        self._prepared_meta[(session_id, handle)] = _PreparedMeta(
            query=query, schema=dataset_schema
        )

        result = fs.ActionCreatePreparedStatementResult(
            prepared_statement_handle=handle.encode("utf-8"),
            dataset_schema=dataset_schema_bytes,
            parameter_schema=param_schema_bytes,
        )
        logger.debug("Created prepared statement %s", handle)
        return result

    def close_prepared_statement(
        self,
        context: flight.ServerCallContext,
        request: fs.ActionClosePreparedStatementRequest,
    ) -> None:
        """Close a prepared statement.

        Mirrors C++ ``ClosePreparedStatement``.
        """
        session_id = _get_session_id(context)
        handle = request.prepared_statement_handle.decode("utf-8")
        self._sessions.close_prepared_statement(session_id, handle)
        self._prepared_meta.pop((session_id, handle), None)
        logger.debug("Closed prepared statement %s", handle)

    def begin_transaction(
        self,
        context: flight.ServerCallContext,
        request: fs.ActionBeginTransactionRequest,
    ) -> fs.ActionBeginTransactionResult:
        """Begin a transaction and return its handle.

        Mirrors C++ ``BeginTransaction``.
        """
        session_id = _get_session_id(context)
        self._sessions.get_or_create(session_id)  # ensure session exists
        handle = self._sessions.begin_transaction(session_id)
        return fs.ActionBeginTransactionResult(transaction_id=handle.encode("utf-8"))

    def end_transaction(
        self,
        context: flight.ServerCallContext,
        request: fs.ActionEndTransactionRequest,
    ) -> None:
        """Commit or rollback a transaction.

        Mirrors C++ ``EndTransaction``.
        """
        session_id = _get_session_id(context)
        handle = request.transaction_id.decode("utf-8")
        commit = request.action != 2  # END_TRANSACTION_ROLLBACK = 2
        self._sessions.end_transaction(session_id, handle, commit=commit)

    def begin_savepoint(
        self,
        context: flight.ServerCallContext,
        request: fs.ActionBeginSavepointRequest,
    ) -> fs.ActionBeginSavepointResult:
        """Create a savepoint within an existing transaction.

        DuckDB does not support SQL ``SAVEPOINT`` statements.
        This returns an error to the client.
        """
        raise flight.FlightServerError("Savepoints are not supported by DuckDB")

    def end_savepoint(
        self,
        context: flight.ServerCallContext,
        request: fs.ActionEndSavepointRequest,
    ) -> None:
        """Release or rollback to a savepoint.

        DuckDB does not support SQL ``SAVEPOINT`` statements.
        This returns an error to the client.
        """
        raise flight.FlightServerError("Savepoints are not supported by DuckDB")

    def cancel_query(
        self,
        context: flight.ServerCallContext,
        request: fs.ActionCancelQueryRequest,
    ) -> fs.ActionCancelQueryResult:
        """Cancel a running query.

        Mirrors C++ ``CancelQuery``.  Since single-threaded DuckDB
        queries are not easily cancellable, we return ``CANCELLING`` to
        acknowledge the request.
        """
        logger.debug("Cancel query requested")
        return fs.ActionCancelQueryResult(
            result=fs.ActionCancelQueryResult.CancelResult.CANCEL_RESULT_CANCELLING,
        )

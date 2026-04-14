# ADBC Coverage Matrix

This matrix documents ADBC compatibility for this repository's Flight SQL server backed by DuckDB/DuckLake. It is scoped to server-visible behavior through the Python `adbc-driver-flightsql` client, not to implementing the ADBC C ABI inside this server.

Primary sources:
- [ADBC API Standard](https://arrow.apache.org/adbc/current/format/specification.html)
- [ADBC Flight SQL driver](https://arrow.apache.org/adbc/current/driver/flight_sql.html)
- [ADBC driver implementation status](https://arrow.apache.org/adbc/current/driver/status.html)
- [Canonical `adbc.h`](https://raw.githubusercontent.com/apache/arrow-adbc/main/c/include/arrow-adbc/adbc.h)
- [Arrow Flight SQL protocol](https://arrow.apache.org/docs/format/FlightSql.html)

Status values:
- `covered`: implemented and exercised by repo tests or live smoke tests.
- `partial`: implemented for the main path, with known limitations.
- `unsupported-by-server`: the Flight SQL server does not implement this feature.
- `not-supported-by-python-flightsql-driver`: the server may expose a Flight SQL feature, but the Python ADBC Flight SQL driver does not currently expose a matching ADBC path.
- `client-only/N/A`: ADBC driver manager, client ABI, or client option behavior that this server does not implement.
- `needs-verification`: not enough repo evidence to claim support.

| ADBC area | Status | Notes |
| --- | --- | --- |
| ADBC object and driver ABI: database, connection, statement lifecycle, driver loading, option getter/setter variants, `AdbcError` layout | `client-only/N/A` | These are ADBC driver/driver-manager responsibilities from the ADBC API and `adbc.h`, not Flight SQL server APIs. |
| Connection URI and basic client setup | `covered` | Python `adbc-driver-flightsql` connects to local and deployed Flight SQL endpoints. |
| Authorization header bearer flow | `covered` | Supported Azure path is PyArrow Basic-token bootstrap followed by ADBC Bearer auth. |
| Direct ADBC Basic auth against Azure Container App | `needs-verification` | Tracked as an opt-in `xfail` path; do not document as the supported Azure ADBC path. |
| TLS server authentication | `covered` | Covered by TLS e2e tests and live Azure smoke path. |
| mTLS client certificates, OAuth flows, cookies, timeout knobs, queue size, custom call headers | `client-only/N/A` | Mostly Flight SQL driver options. Only server-observable effects should be promoted to support claims after dedicated tests. |
| SQL query execution and Arrow result fetch | `covered` | Maps to Flight SQL statement query `GetFlightInfo`/`DoGet`. |
| SQL update, DDL/DML, and row counts | `covered` | Maps to Flight SQL update `DoPut` with update-result metadata. |
| Execute schema / Flight `GetSchema` | `covered` | Server implements Flight `GetSchema` for statement queries, prepared statements, and metadata commands, with direct unit and ADBC `execute_schema` acceptance coverage. |
| Prepared statement create/close | `covered` | Server supports Flight SQL prepared statement actions. |
| Prepared statement query/update with single-row parameter batches | `covered` | Supported by current handler behavior and tests. |
| Prepared statement multi-row parameter batches | `partial` | Current implementation should be treated as single-row oriented until multi-row parameter binding is tested or implemented. |
| Metadata: `GetInfo`, catalogs, schemas, tables, table types, table schema, XDBC type info | `covered` | Maps to Flight SQL metadata commands and local ADBC `GetObjects` depth/filter tests. |
| Metadata: primary keys, imported/exported keys, cross-reference | `covered` | Server has Flight SQL handlers and unit coverage. |
| ADBC `GetObjects` table constraints | `not-supported-by-python-flightsql-driver` | The Flight SQL driver docs note `AdbcConnectionGetObjects()` does not currently populate column constraint info such as primary/foreign keys. |
| ADBC metadata pattern/filter semantics | `partial` | Flight SQL driver docs note catalog filters are simple string matches, not `LIKE` patterns. |
| Transactions: begin/end, commit, rollback, autocommit discovery | `covered` | Current Flight SQL and SQL transaction `SqlInfo` IDs are emitted from the generated proto constants, and ADBC DBAPI rollback/autocommit discovery is covered. |
| Savepoints | `unsupported-by-server` | Server reports savepoints as unsupported. |
| Cancellation via ADBC and Flight SQL actions | `partial` | Server supports deprecated `CancelQuery` behavior returning cancellation state, but does not guarantee true DuckDB query interruption and does not claim modern `CancelFlightInfo` coverage. |
| Partitioned or incremental results | `partial` | ADBC `ExecutePartitions`/`ReadPartition` is covered for the server's single-endpoint result path. Multi-endpoint distributed optimization and incremental execution are not implemented. |
| Bulk ingest via Flight SQL `CommandStatementIngest` | `covered` | Server-side ingest handlers and tests cover create/append/replace/fail behavior. |
| Bulk ingest through Python `adbc-driver-flightsql` | `partial` | The current local `adbc-driver-flightsql` exposes and passes `adbc_ingest`; the test xfails if a driver/environment returns `NotSupportedError` because the upstream Flight SQL driver docs still state bulk ingestion is not currently implemented. |
| ADBC statistics APIs: `GetStatistics`, `GetStatisticNames` | `unsupported-by-server` | No server support is claimed for ADBC statistics metadata. |
| Substrait plans | `unsupported-by-server` | Substrait commands are intentionally not implemented and should not be listed as supported protocol surface. |
| Rich ADBC error details | `needs-verification` | Server maps errors to Flight/gRPC status paths, but ADBC driver-specific error-detail propagation has no dedicated coverage. |
| Flight SQL session options | `unsupported-by-server` | Session option get/set/erase lifecycle is not part of the current server support claim. |

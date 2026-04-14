"""Opt-in tests against the deployed Azure Container App backend.

The default live check authenticates with PyArrow's Basic-token handshake and
then runs the query through ADBC with the returned Bearer token.  That proves
the deployed backend, Key Vault password, TLS endpoint, and Bearer auth path are
working.

The separate ADBC Basic-auth check is gated by ``LAKEHOUSE_LIVE_BACKEND_ADBC_BASIC``
and is marked ``xfail`` because ADBC's Basic-to-Bearer exchange is the currently
tracked client path that fails against the deployed Container App.  A result
with all bearer-path tests passing and one xfailed direct-Basic test means the
supported ADBC live checks passed and the known ADBC Basic issue reproduced.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import subprocess
import uuid

import pytest

from lakehouse._azd_env import resolve_container_app_env

_LIVE_BACKEND_FLAG = "LAKEHOUSE_LIVE_BACKEND"
_LIVE_BACKEND_ADBC_BASIC_FLAG = "LAKEHOUSE_LIVE_BACKEND_ADBC_BASIC"
_JDBC_DIR = os.path.join(os.path.dirname(__file__), "jdbc")

pytestmark = pytest.mark.skipif(
    os.environ.get(_LIVE_BACKEND_FLAG) != "1",
    reason=f"set {_LIVE_BACKEND_FLAG}=1 to query the deployed Azure Container App",
)


def _run_az(args: list[str], purpose: str) -> str:
    if shutil.which("az") is None:
        pytest.skip("Azure CLI (az) not found")
    result = subprocess.run(
        ["az", *args],
        capture_output=True,
        check=False,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Azure CLI failed while {purpose} (exit {result.returncode})")
    value = result.stdout.strip()
    if not value:
        raise RuntimeError(f"Azure CLI returned no value while {purpose}")
    return value


def _discover_endpoint(values: dict[str, str]) -> str:
    fqdn = _run_az(
        [
            "containerapp",
            "show",
            "-g",
            values["AZURE_RESOURCE_GROUP"],
            "-n",
            values["CONTAINER_APP_NAME"],
            "--query",
            "properties.configuration.ingress.fqdn",
            "-o",
            "tsv",
        ],
        "discovering the Container App endpoint",
    )
    return f"grpc+tls://{fqdn}:443"


def _read_password(values: dict[str, str]) -> str:
    return _run_az(
        [
            "keyvault",
            "secret",
            "show",
            "--vault-name",
            values["KEY_VAULT_NAME"],
            "--name",
            "lakehouse-password",
            "--query",
            "value",
            "-o",
            "tsv",
        ],
        "reading the lakehouse-password Key Vault secret",
    )


def _redact_auth_material(message: str, *secrets: str) -> str:
    message = re.sub(r"Basic\s+[A-Za-z0-9+/=_-]+", "Basic <redacted>", message)
    message = re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer <redacted>", message)
    for secret in secrets:
        if secret:
            message = message.replace(secret, "<redacted>")
    return message


def _bootstrap_bearer_header(endpoint: str, username: str, password: str) -> str:
    import pyarrow.flight as flight

    client = flight.connect(endpoint)
    header_name, header_value = client.authenticate_basic_token(username, password)
    if isinstance(header_name, bytes):
        header_name = header_name.decode()
    if isinstance(header_value, bytes):
        header_value = header_value.decode()
    if header_name.lower() != "authorization" or not header_value.startswith("Bearer "):
        raise RuntimeError("Basic auth did not return a Bearer authorization header")
    return header_value


def _connect_with_pyarrow_bootstrapped_bearer(endpoint: str, password: str):
    import adbc_driver_flightsql.dbapi as flightsql
    from adbc_driver_flightsql import DatabaseOptions

    bearer_header = _bootstrap_bearer_header(endpoint, "lakehouse", password)
    return flightsql.connect(
        endpoint,
        db_kwargs={DatabaseOptions.AUTHORIZATION_HEADER.value: bearer_header},
    )


def _connect_with_adbc_basic(endpoint: str, password: str):
    import base64

    import adbc_driver_flightsql.dbapi as flightsql
    from adbc_driver_flightsql import DatabaseOptions

    token = base64.b64encode(f"lakehouse:{password}".encode()).decode()
    return flightsql.connect(
        endpoint,
        db_kwargs={DatabaseOptions.AUTHORIZATION_HEADER.value: f"Basic {token}"},
    )


def _set_autocommit_if_supported(conn, enabled: bool) -> None:
    import adbc_driver_manager

    with contextlib.suppress(adbc_driver_manager.NotSupportedError):
        conn.adbc_connection.set_autocommit(enabled)


def _run_live_check_with_credentials(connect, check):
    resolution = resolve_container_app_env()
    if not resolution.ready:
        pytest.skip(resolution.skip_reason("Azure Container App azd outputs missing"))

    conn = None
    failure: str | None = None
    password = ""
    try:
        endpoint = _discover_endpoint(resolution.values)
        password = _read_password(resolution.values)
        conn = connect(endpoint, password)
        _set_autocommit_if_supported(conn, True)
        check(conn, endpoint, password)
    except Exception as exc:
        detail = _redact_auth_material(str(exc), password)[:500]
        failure = f"{type(exc).__name__}: {detail}"
    finally:
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.close()

    if failure is not None:
        pytest.fail(f"Live Azure backend query failed ({failure})", pytrace=False)


def _run_live_check(connect, check):
    def check_without_credentials(conn, _endpoint, _password):
        check(conn)

    _run_live_check_with_credentials(connect, check_without_credentials)


def _run_live_query(connect):
    def check(conn):
        cursor = conn.execute("SELECT 1 AS value")
        try:
            assert cursor.fetchall() == [(1,)]
        finally:
            cursor.close()

    _run_live_check(connect, check)


def _run_live_jdbc_test(test_class: str) -> None:
    if shutil.which("mvn") is None:
        pytest.skip("Maven (mvn) not found")

    resolution = resolve_container_app_env()
    if not resolution.ready:
        pytest.skip(resolution.skip_reason("Azure Container App azd outputs missing"))

    password = ""
    try:
        endpoint = _discover_endpoint(resolution.values)
        password = _read_password(resolution.values)
        result = subprocess.run(
            [
                "mvn",
                "-q",
                "test",
                f"-Dflight.url={endpoint}",
                "-Dflight.user=lakehouse",
                f"-Dflight.password={password}",
                "-Dlive.azure.jdbc.required=true",
                f"-Dtest={test_class}",
            ],
            cwd=_JDBC_DIR,
            capture_output=True,
            text=True,
            timeout=240,
        )
    except Exception as exc:
        detail = _redact_auth_material(str(exc), password)[:500]
        pytest.fail(
            f"Live Azure JDBC test failed ({type(exc).__name__}: {detail})",
            pytrace=False,
        )

    if result.returncode != 0:
        stdout = _redact_auth_material(result.stdout, password)
        stderr = _redact_auth_material(result.stderr, password)
        print("=== Maven stdout ===")
        print(stdout[-3000:] if len(stdout) > 3000 else stdout)
        print("=== Maven stderr ===")
        print(stderr[-3000:] if len(stderr) > 3000 else stderr)

    assert result.returncode == 0, f"mvn test failed (exit {result.returncode})"


def _unique_table(prefix: str) -> str:
    return f"live_adbc_{prefix}_{uuid.uuid4().hex[:12]}"


def _ducklake_table(table_name: str) -> str:
    return f"lakehouse.main.{table_name}"


def _find_get_objects_table(table, table_name: str):
    for catalog in table.to_pylist():
        for schema in catalog.get("catalog_db_schemas") or []:
            for found_table in schema.get("db_schema_tables") or []:
                if found_table["table_name"] == table_name:
                    return found_table
    return None


def test_deployed_container_app_accepts_pyarrow_bootstrapped_bearer_query():
    _run_live_query(_connect_with_pyarrow_bootstrapped_bearer)


def test_deployed_container_app_supports_adbc_execute_schema():
    def check(conn):
        cursor = conn.cursor()
        try:
            schema = cursor.adbc_execute_schema("SELECT 1 AS value, 'ok' AS label")
        finally:
            cursor.close()

        assert schema.names == ["value", "label"]

    _run_live_check(_connect_with_pyarrow_bootstrapped_bearer, check)


def test_deployed_container_app_supports_adbc_get_objects_table_filter():
    table_name = _unique_table("objects")
    other_table_name = _unique_table("objects_other")

    def check(conn):
        try:
            conn.execute(f"DROP TABLE IF EXISTS {table_name}").close()
            conn.execute(f"DROP TABLE IF EXISTS {other_table_name}").close()
            conn.execute(f"CREATE TABLE {table_name} (id INT, label TEXT)").close()
            conn.execute(f"CREATE TABLE {other_table_name} (id INT)").close()

            reader = conn.adbc_get_objects(depth="tables", table_name_filter=table_name)
            table = reader.read_all()
            found_table = _find_get_objects_table(table, table_name)
            other_table = _find_get_objects_table(table, other_table_name)

            assert found_table is not None
            assert found_table["table_type"] in {"BASE TABLE", "TABLE"}
            assert found_table["table_columns"] is None
            assert found_table["table_constraints"] is None
            assert other_table is None
        finally:
            with contextlib.suppress(Exception):
                conn.execute(f"DROP TABLE IF EXISTS {table_name}").close()
            with contextlib.suppress(Exception):
                conn.execute(f"DROP TABLE IF EXISTS {other_table_name}").close()

    _run_live_check(_connect_with_pyarrow_bootstrapped_bearer, check)


def test_deployed_container_app_supports_adbc_transaction_commit_and_rollback():
    table_name = _unique_table("txn")
    fq_table_name = _ducklake_table(table_name)

    def check(conn, endpoint, password):
        verify_conn = None
        cursor = None
        try:
            conn.execute(f"DROP TABLE IF EXISTS {fq_table_name}").close()
            conn.execute(f"CREATE TABLE {fq_table_name} (id INT)").close()

            conn.adbc_connection.set_autocommit(False)
            conn.execute(f"INSERT INTO {fq_table_name} VALUES (1)").close()
            conn.commit()
            conn.execute(f"INSERT INTO {fq_table_name} VALUES (2)").close()
            conn.rollback()
            conn.adbc_connection.set_autocommit(True)

            verify_conn = _connect_with_pyarrow_bootstrapped_bearer(endpoint, password)
            _set_autocommit_if_supported(verify_conn, True)
            cursor = verify_conn.execute(f"SELECT id FROM {fq_table_name} ORDER BY id")
            assert cursor.fetchall() == [(1,)]
        finally:
            if cursor is not None:
                with contextlib.suppress(Exception):
                    cursor.close()
            if verify_conn is not None:
                with contextlib.suppress(Exception):
                    verify_conn.close()
            with contextlib.suppress(Exception):
                conn.adbc_connection.set_autocommit(True)
            with contextlib.suppress(Exception):
                conn.execute(f"DROP TABLE IF EXISTS {fq_table_name}").close()

    _run_live_check_with_credentials(_connect_with_pyarrow_bootstrapped_bearer, check)


def test_deployed_container_app_persists_writes_after_disconnect():
    table_name = _unique_table("persist")
    fq_table_name = _ducklake_table(table_name)

    def check(conn, endpoint, password):
        reader_conn = None
        cleanup_conn = None
        cursor = None
        dropped = False
        try:
            conn.execute(f"DROP TABLE IF EXISTS {fq_table_name}").close()
            conn.execute(f"CREATE TABLE {fq_table_name} (id INT, label TEXT)").close()
            conn.execute(
                f"INSERT INTO {fq_table_name} VALUES (101, 'alpha'), (202, 'beta')"
            ).close()
            conn.close()

            reader_conn = _connect_with_pyarrow_bootstrapped_bearer(endpoint, password)
            _set_autocommit_if_supported(reader_conn, True)
            cursor = reader_conn.execute(
                f"SELECT id, label FROM {fq_table_name} ORDER BY id"
            )

            assert cursor.fetchall() == [(101, "alpha"), (202, "beta")]
        finally:
            if cursor is not None:
                with contextlib.suppress(Exception):
                    cursor.close()
            if reader_conn is not None:
                with contextlib.suppress(Exception):
                    reader_conn.execute(f"DROP TABLE IF EXISTS {fq_table_name}").close()
                    dropped = True
                with contextlib.suppress(Exception):
                    reader_conn.close()
            if not dropped:
                cleanup_conn = _connect_with_pyarrow_bootstrapped_bearer(endpoint, password)
                with contextlib.suppress(Exception):
                    cleanup_conn.execute(f"DROP TABLE IF EXISTS {fq_table_name}").close()
                    dropped = True
                with contextlib.suppress(Exception):
                    cleanup_conn.close()

    _run_live_check_with_credentials(_connect_with_pyarrow_bootstrapped_bearer, check)


def test_deployed_container_app_persists_jdbc_writes_after_disconnect():
    _run_live_jdbc_test("FlightSqlJdbcAzurePersistenceTest")


def test_deployed_container_app_supports_adbc_execute_partitions():
    def check(conn):
        cursor = conn.cursor()
        try:
            partitions, schema = cursor.adbc_execute_partitions(
                "SELECT 1 AS value UNION ALL SELECT 2 AS value ORDER BY value"
            )

            assert len(partitions) == 1
            assert schema.names == ["value"]

            cursor.adbc_read_partition(partitions[0])
            assert cursor.fetchall() == [(1,), (2,)]
        finally:
            cursor.close()

    _run_live_check(_connect_with_pyarrow_bootstrapped_bearer, check)


def test_deployed_container_app_accepts_idle_adbc_cancel():
    def check(conn):
        cursor = conn.cursor()
        try:
            cursor.adbc_cancel()
            cursor.execute("SELECT 1 AS value")
            assert cursor.fetchall() == [(1,)]
        finally:
            cursor.close()

    _run_live_check(_connect_with_pyarrow_bootstrapped_bearer, check)


@pytest.mark.skipif(
    os.environ.get(_LIVE_BACKEND_ADBC_BASIC_FLAG) != "1",
    reason=f"set {_LIVE_BACKEND_ADBC_BASIC_FLAG}=1 to exercise ADBC Basic auth",
)
@pytest.mark.xfail(
    reason="ADBC Basic-to-Bearer handshake currently fails against the deployed Container App",
    strict=False,
)
def test_deployed_container_app_accepts_adbc_basic_query():
    _run_live_query(_connect_with_adbc_basic)

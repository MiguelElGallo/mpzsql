"""Opt-in tests against the deployed Azure Container App backend.

The default live check authenticates with PyArrow's Basic-token handshake and
then runs the query through ADBC with the returned Bearer token.  That proves
the deployed backend, Key Vault password, TLS endpoint, and Bearer auth path are
working.

The separate ADBC Basic-auth check is gated by ``LAKEHOUSE_LIVE_BACKEND_ADBC_BASIC``
and is marked ``xfail`` because ADBC's Basic-to-Bearer exchange is the currently
tracked client path that fails against the deployed Container App.  A result like
``1 passed, 1 xfailed`` means the supported bearer smoke test passed and the
known ADBC Basic issue reproduced as expected.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import subprocess

import pytest

from lakehouse._azd_env import resolve_container_app_env

_LIVE_BACKEND_FLAG = "LAKEHOUSE_LIVE_BACKEND"
_LIVE_BACKEND_ADBC_BASIC_FLAG = "LAKEHOUSE_LIVE_BACKEND_ADBC_BASIC"

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


def _run_live_query(connect):
    resolution = resolve_container_app_env()
    if not resolution.ready:
        pytest.skip(resolution.skip_reason("Azure Container App azd outputs missing"))

    conn = None
    cursor = None
    failure: str | None = None
    password = ""
    try:
        endpoint = _discover_endpoint(resolution.values)
        password = _read_password(resolution.values)
        conn = connect(endpoint, password)
        cursor = conn.execute("SELECT 1 AS value")
        assert cursor.fetchall() == [(1,)]
    except Exception as exc:
        detail = _redact_auth_material(str(exc), password)[:500]
        failure = f"{type(exc).__name__}: {detail}"
    finally:
        if cursor is not None:
            with contextlib.suppress(Exception):
                cursor.close()
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.close()

    if failure is not None:
        pytest.fail(f"Live Azure backend query failed ({failure})", pytrace=False)


def test_deployed_container_app_accepts_pyarrow_bootstrapped_bearer_query():
    _run_live_query(_connect_with_pyarrow_bootstrapped_bearer)


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

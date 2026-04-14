from __future__ import annotations

import subprocess

from lakehouse._azd_env import (
    DUCKLAKE_REQUIRED_ENV,
    apply_env_resolution,
    load_azd_values,
    parse_azd_env_lines,
    postgres_firewall_hint,
    resolve_container_app_env,
    resolve_ducklake_env,
)


def _write_azd_env(tmp_path, body: str, env_name: str = "lakehouse-dev") -> None:
    azure_dir = tmp_path / ".azure"
    env_dir = azure_dir / env_name
    env_dir.mkdir(parents=True)
    (azure_dir / "config.json").write_text(
        f'{{"version": 1, "defaultEnvironment": "{env_name}"}}',
        encoding="utf-8",
    )
    (env_dir / ".env").write_text(body, encoding="utf-8")
    (tmp_path / "azure.yaml").write_text("name: lakehouse\n", encoding="utf-8")


def _azd_ducklake_body() -> str:
    return """
AZURE_ENV_NAME="lakehouse-dev"
POSTGRES_FQDN="pg.example.postgres.database.azure.com"
POSTGRES_DATABASE_NAME="ducklake"
POSTGRES_ENTRA_ADMIN_PRINCIPAL_NAME="user#EXT#@example.onmicrosoft.com"
STORAGE_ACCOUNT_NAME="stlakehouse"
DUCKLAKE_DATA_PATH="az://lakehouse/data/"
AZURE_RESOURCE_GROUP="rg-lakehouse"
CONTAINER_APP_NAME="ca-lakehouse"
KEY_VAULT_NAME="kv-lakehouse"
POSTGRES_ADMIN_PASSWORD="super-secret-password"
"""


def test_parse_azd_env_lines_handles_quotes_and_hashes():
    values = parse_azd_env_lines(
        """
export AZURE_ENV_NAME="lakehouse-dev"
POSTGRES_ENTRA_ADMIN_PRINCIPAL_NAME='user#EXT#@example.onmicrosoft.com'
DUCKLAKE_DATA_PATH=az://lakehouse/data/
"""
    )

    assert values["AZURE_ENV_NAME"] == "lakehouse-dev"
    assert values["POSTGRES_ENTRA_ADMIN_PRINCIPAL_NAME"] == ("user#EXT#@example.onmicrosoft.com")
    assert values["DUCKLAKE_DATA_PATH"] == "az://lakehouse/data/"


def test_resolve_ducklake_env_maps_azd_outputs_from_default_environment(tmp_path):
    _write_azd_env(tmp_path, _azd_ducklake_body())

    resolution = resolve_ducklake_env(tmp_path, environ={}, use_azd_cli=False)

    assert resolution.ready
    assert resolution.missing == ()
    assert resolution.source == "azd-file"
    assert resolution.azd_environment == "lakehouse-dev"
    assert resolution.values == {
        "DUCKLAKE_PG_HOST": "pg.example.postgres.database.azure.com",
        "DUCKLAKE_PG_DATABASE": "ducklake",
        "DUCKLAKE_PG_USER": "user#EXT#@example.onmicrosoft.com",
        "DUCKLAKE_AZURE_STORAGE_ACCOUNT": "stlakehouse",
        "DUCKLAKE_DATA_PATH": "az://lakehouse/data/",
    }


def test_resolve_ducklake_env_prefers_explicit_environment_values(tmp_path):
    _write_azd_env(tmp_path, _azd_ducklake_body())

    resolution = resolve_ducklake_env(
        tmp_path,
        environ={"DUCKLAKE_PG_HOST": "manual.postgres.database.azure.com"},
        use_azd_cli=False,
    )

    assert resolution.ready
    assert resolution.source == "environment+azd-file"
    assert resolution.values["DUCKLAKE_PG_HOST"] == "manual.postgres.database.azure.com"
    assert resolution.values["DUCKLAKE_PG_DATABASE"] == "ducklake"


def test_apply_env_resolution_treats_blank_environment_values_as_unset(tmp_path):
    _write_azd_env(tmp_path, _azd_ducklake_body())
    environ = {"DUCKLAKE_PG_HOST": ""}

    resolution = resolve_ducklake_env(tmp_path, environ=environ, use_azd_cli=False)
    apply_env_resolution(resolution, environ)

    assert resolution.ready
    assert environ["DUCKLAKE_PG_HOST"] == "pg.example.postgres.database.azure.com"
    assert environ["DUCKLAKE_PG_DATABASE"] == "ducklake"


def test_resolve_ducklake_env_reports_missing_config_without_crashing(tmp_path):
    (tmp_path / "azure.yaml").write_text("name: lakehouse\n", encoding="utf-8")

    resolution = resolve_ducklake_env(tmp_path, environ={}, use_azd_cli=False)

    assert not resolution.ready
    assert resolution.missing == DUCKLAKE_REQUIRED_ENV
    assert "DuckLake env vars missing" in resolution.skip_reason("DuckLake env vars missing")


def test_resolve_ducklake_env_does_not_leak_secret_values(tmp_path):
    _write_azd_env(tmp_path, _azd_ducklake_body())

    resolution = resolve_ducklake_env(tmp_path, environ={}, use_azd_cli=False)

    assert "super-secret-password" not in repr(resolution)
    assert "super-secret-password" not in resolution.skip_reason("DuckLake env vars missing")


def test_azd_cli_values_are_preferred_before_file_values(tmp_path):
    _write_azd_env(tmp_path, _azd_ducklake_body())

    def runner(command, cwd):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="""
AZURE_ENV_NAME="lakehouse-cli"
POSTGRES_FQDN="pg.cli.postgres.database.azure.com"
POSTGRES_DATABASE_NAME="ducklake_cli"
POSTGRES_ENTRA_ADMIN_PRINCIPAL_NAME="cli-user@example.com"
STORAGE_ACCOUNT_NAME="stcli"
DUCKLAKE_DATA_PATH="az://cli/data/"
""",
            stderr="",
        )

    values = load_azd_values(tmp_path, command_runner=runner)
    resolution = resolve_ducklake_env(tmp_path, environ={}, command_runner=runner)

    assert values.source == "azd-cli"
    assert values.environment == "lakehouse-cli"
    assert resolution.source == "azd-cli"
    assert resolution.values["DUCKLAKE_PG_HOST"] == "pg.cli.postgres.database.azure.com"


def test_resolve_container_app_env_maps_non_secret_azd_outputs(tmp_path):
    _write_azd_env(tmp_path, _azd_ducklake_body())

    resolution = resolve_container_app_env(tmp_path, environ={}, use_azd_cli=False)

    assert resolution.ready
    assert resolution.values == {
        "AZURE_RESOURCE_GROUP": "rg-lakehouse",
        "CONTAINER_APP_NAME": "ca-lakehouse",
        "KEY_VAULT_NAME": "kv-lakehouse",
    }


def test_postgres_firewall_hint_points_to_ip_allowlist_without_values():
    hint = postgres_firewall_hint()

    assert "./scripts/allow-current-ip-postgres.sh" in hint
    assert "az postgres flexible-server firewall-rule create" in hint
    assert "pg.example.postgres.database.azure.com" not in hint
    assert "super-secret-password" not in hint

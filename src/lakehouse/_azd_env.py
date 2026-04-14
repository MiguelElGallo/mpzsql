"""Local Azure Developer CLI environment discovery helpers.

The azd environment directory is intentionally ignored by git because it
contains local deployment state and may include secrets.  This module reads
that state only to derive the non-secret values needed by local e2e tests.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "CONTAINER_APP_AZD_ENV_KEYS",
    "DUCKLAKE_REQUIRED_ENV",
    "AzdValues",
    "EnvResolution",
    "apply_env_resolution",
    "load_azd_values",
    "parse_azd_env_lines",
    "postgres_firewall_hint",
    "resolve_container_app_env",
    "resolve_ducklake_env",
]

DUCKLAKE_REQUIRED_ENV: tuple[str, ...] = (
    "DUCKLAKE_PG_HOST",
    "DUCKLAKE_PG_DATABASE",
    "DUCKLAKE_PG_USER",
    "DUCKLAKE_AZURE_STORAGE_ACCOUNT",
    "DUCKLAKE_DATA_PATH",
)

DUCKLAKE_AZD_ENV_MAP: Mapping[str, str] = {
    "POSTGRES_FQDN": "DUCKLAKE_PG_HOST",
    "POSTGRES_DATABASE_NAME": "DUCKLAKE_PG_DATABASE",
    "POSTGRES_ENTRA_ADMIN_PRINCIPAL_NAME": "DUCKLAKE_PG_USER",
    "STORAGE_ACCOUNT_NAME": "DUCKLAKE_AZURE_STORAGE_ACCOUNT",
    "DUCKLAKE_DATA_PATH": "DUCKLAKE_DATA_PATH",
}

CONTAINER_APP_AZD_ENV_KEYS: tuple[str, ...] = (
    "AZURE_RESOURCE_GROUP",
    "CONTAINER_APP_NAME",
    "KEY_VAULT_NAME",
)

_CommandRunner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class EnvResolution:
    """Resolved environment values plus missing-key metadata."""

    values: dict[str, str]
    missing: tuple[str, ...]
    source: str
    azd_environment: str | None = None

    @property
    def ready(self) -> bool:
        """Whether all required values were discovered."""
        return not self.missing

    def skip_reason(self, prefix: str = "Required environment values missing") -> str:
        """Return a secret-safe pytest skip reason."""
        if self.ready:
            return ""
        missing = ", ".join(self.missing)
        detail = (
            "set explicit environment variables or run `azd up` to populate "
            "the local .azure environment"
        )
        if self.azd_environment:
            detail = f"{detail} ({self.azd_environment})"
        return f"{prefix}: {missing}; {detail}."


@dataclass(frozen=True)
class AzdValues:
    """Raw azd values plus their source metadata."""

    values: dict[str, str]
    source: str
    environment: str | None


def parse_azd_env_lines(lines: str) -> dict[str, str]:
    """Parse azd KEY=VALUE lines without expanding shell syntax."""
    values: dict[str, str] = {}
    for raw_line in lines.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = _parse_env_value(raw_value.strip())
    return values


def load_azd_values(
    repo_root: Path | None = None,
    *,
    use_azd_cli: bool = True,
    command_runner: _CommandRunner | None = None,
) -> AzdValues:
    """Load local azd values from the CLI, falling back to .azure files."""
    root = find_repo_root(repo_root)
    runner = command_runner or _run_command
    default_environment = _read_default_environment(root)

    if use_azd_cli:
        cli_values = _load_cli_values(root, runner)
        if cli_values.values:
            environment = cli_values.values.get("AZURE_ENV_NAME") or default_environment
            return AzdValues(cli_values.values, cli_values.source, environment)

    return _load_file_values(root, default_environment)


def resolve_ducklake_env(
    repo_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
    *,
    use_azd_cli: bool = True,
    command_runner: _CommandRunner | None = None,
) -> EnvResolution:
    """Resolve DuckLake e2e variables from explicit env and azd state."""
    env = os.environ if environ is None else environ
    azd = load_azd_values(
        repo_root,
        use_azd_cli=use_azd_cli,
        command_runner=command_runner,
    )
    azd_values = _map_azd_to_ducklake(azd.values)
    values = _resolve_values(DUCKLAKE_REQUIRED_ENV, env, azd_values)
    missing = tuple(name for name in DUCKLAKE_REQUIRED_ENV if not values.get(name))
    source = _source_label(DUCKLAKE_REQUIRED_ENV, env, azd_values, azd.source)
    return EnvResolution(values, missing, source, azd.environment)


def resolve_container_app_env(
    repo_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
    *,
    use_azd_cli: bool = True,
    command_runner: _CommandRunner | None = None,
) -> EnvResolution:
    """Resolve non-secret azd values needed to find the deployed Container App."""
    env = os.environ if environ is None else environ
    azd = load_azd_values(
        repo_root,
        use_azd_cli=use_azd_cli,
        command_runner=command_runner,
    )
    values = _resolve_values(CONTAINER_APP_AZD_ENV_KEYS, env, azd.values)
    missing = tuple(name for name in CONTAINER_APP_AZD_ENV_KEYS if not values.get(name))
    source = _source_label(CONTAINER_APP_AZD_ENV_KEYS, env, azd.values, azd.source)
    return EnvResolution(values, missing, source, azd.environment)


def apply_env_resolution(
    resolution: EnvResolution,
    environ: MutableMapping[str, str] | None = None,
) -> None:
    """Apply discovered values, treating blank explicit env vars as unset."""
    env = os.environ if environ is None else environ
    for name, value in resolution.values.items():
        if not env.get(name):
            env[name] = value


def postgres_firewall_hint() -> str:
    """Return a secret-safe hint for Azure PostgreSQL network failures."""
    return (
        "If Azure PostgreSQL is unreachable, allow this machine's current public IP "
        "on the PostgreSQL Flexible Server firewall. Prefer running "
        "`./scripts/allow-current-ip-postgres.sh`, or create an equivalent temporary "
        "rule with `az postgres flexible-server firewall-rule create`."
    )


def find_repo_root(start: Path | None = None) -> Path:
    """Find the nearest ancestor that looks like this azd project root."""
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / "azure.yaml").is_file():
            return candidate
    return current


def _parse_env_value(raw_value: str) -> str:
    if raw_value == "":
        return ""
    try:
        parts = shlex.split(raw_value, posix=True)
    except ValueError:
        return raw_value.strip().strip("\"'")
    if not parts:
        return ""
    return " ".join(parts)


def _run_command(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        check=False,
        text=True,
    )


def _load_cli_values(root: Path, runner: _CommandRunner) -> AzdValues:
    if runner is _run_command and shutil.which("azd") is None:
        return AzdValues({}, "missing", None)
    try:
        result = runner(("azd", "env", "get-values"), root)
    except OSError:
        return AzdValues({}, "missing", None)
    if result.returncode != 0:
        return AzdValues({}, "missing", None)
    values = parse_azd_env_lines(result.stdout)
    return AzdValues(values, "azd-cli", values.get("AZURE_ENV_NAME"))


def _load_file_values(root: Path, default_environment: str | None) -> AzdValues:
    for environment in _candidate_environments(root, default_environment):
        env_file = root / ".azure" / environment / ".env"
        if env_file.is_file():
            return AzdValues(
                parse_azd_env_lines(env_file.read_text(encoding="utf-8")),
                "azd-file",
                environment,
            )
    return AzdValues({}, "missing", default_environment)


def _read_default_environment(root: Path) -> str | None:
    config_file = root / ".azure" / "config.json"
    if not config_file.is_file():
        return None
    try:
        raw_config = json.loads(config_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    environment = raw_config.get("defaultEnvironment")
    if isinstance(environment, str) and environment:
        return environment
    return None


def _candidate_environments(root: Path, default_environment: str | None) -> tuple[str, ...]:
    names: list[str] = []
    if default_environment:
        names.append(default_environment)
    azure_dir = root / ".azure"
    if azure_dir.is_dir():
        for child in sorted(azure_dir.iterdir()):
            if child.is_dir() and (child / ".env").is_file() and child.name not in names:
                names.append(child.name)
    return tuple(names)


def _map_azd_to_ducklake(azd_values: Mapping[str, str]) -> dict[str, str]:
    return {
        ducklake_key: azd_values[azd_key]
        for azd_key, ducklake_key in DUCKLAKE_AZD_ENV_MAP.items()
        if azd_values.get(azd_key)
    }


def _resolve_values(
    required_keys: Sequence[str],
    environ: Mapping[str, str],
    azd_values: Mapping[str, str],
) -> dict[str, str]:
    values: dict[str, str] = {}
    for name in required_keys:
        if environ.get(name):
            values[name] = environ[name]
        elif azd_values.get(name):
            values[name] = azd_values[name]
    return values


def _source_label(
    required_keys: Sequence[str],
    environ: Mapping[str, str],
    azd_values: Mapping[str, str],
    azd_source: str,
) -> str:
    sources: list[str] = []
    if any(environ.get(name) for name in required_keys):
        sources.append("environment")
    if azd_source != "missing" and any(azd_values.get(name) for name in required_keys):
        sources.append(azd_source)
    return "+".join(sources) if sources else "missing"

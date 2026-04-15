from __future__ import annotations

from pathlib import Path


_JDBC_TEST_DIR = Path(__file__).resolve().parent / "jdbc" / "src" / "test" / "java" / "lakehouse"


def jdbc_test_classes_for(profile: str) -> list[str]:
    """Return JDBC test class names for a bridge profile.

    The selection is based on the Java test filename so that new generic JDBC
    test classes are picked up automatically:

    - ``FlightSqlJdbcTest`` is local/plaintext only.
    - ``FlightSqlJdbcTlsTest`` is TLS-only.
    - ``FlightSqlJdbcAzurePersistenceTest`` is live-Azure-only.
    - any other ``FlightSqlJdbc*Test`` class is treated as transport-neutral
      and runs in all three bridge entry points.
    """

    if profile not in {"local", "tls", "live"}:
        raise ValueError(f"Unknown JDBC bridge profile: {profile}")

    classes: dict[str, list[str]] = {"local": [], "tls": [], "live": []}
    if not _JDBC_TEST_DIR.exists():
        return classes[profile]

    for path in sorted(_JDBC_TEST_DIR.glob("FlightSqlJdbc*Test.java")):
        name = path.stem
        if name == "FlightSqlJdbcTest":
            classes["local"].append(name)
        elif name == "FlightSqlJdbcTlsTest":
            classes["tls"].append(name)
        elif name == "FlightSqlJdbcAzurePersistenceTest":
            classes["live"].append(name)
        else:
            classes["local"].append(name)
            classes["tls"].append(name)
            classes["live"].append(name)

    selected = classes[profile]
    if not selected:
        raise RuntimeError(f"No JDBC test classes discovered for profile {profile}")
    return selected

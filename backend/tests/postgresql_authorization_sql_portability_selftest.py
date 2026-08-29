from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = BACKEND_ROOT / "app" / "services"

SCOPE_FILES = (
    "authorization_foundation_service.py",
    "authorization_membership_service.py",
    "platform_authorization_management_service.py",
    "authorization_ui_fixture_provisioning.py",
    "system_superuser_session_provisioning.py",
    "beta_superuser_provisioning_service.py",
)

FORBIDDEN_SQL_PATTERNS = {
    "CREATE TABLE": re.compile(r"\bCREATE\s+TABLE\b", re.IGNORECASE),
    "CREATE INDEX": re.compile(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b", re.IGNORECASE),
    "CREATE TRIGGER": re.compile(r"\bCREATE\s+TRIGGER\b", re.IGNORECASE),
    "ALTER TABLE": re.compile(r"\bALTER\s+TABLE\b", re.IGNORECASE),
    "DROP schema object": re.compile(r"\bDROP\s+(?:TABLE|INDEX|TRIGGER)\b", re.IGNORECASE),
    "PRAGMA": re.compile(r"\bPRAGMA\b", re.IGNORECASE),
    "sqlite_master": re.compile(r"\bsqlite_master\b", re.IGNORECASE),
    "AUTOINCREMENT": re.compile(r"\bAUTOINCREMENT\b", re.IGNORECASE),
    "INSERT OR IGNORE": re.compile(r"\bINSERT\s+OR\s+IGNORE\b", re.IGNORECASE),
    "INSERT OR REPLACE": re.compile(r"\bINSERT\s+OR\s+REPLACE\b", re.IGNORECASE),
    "GLOB": re.compile(r"\bGLOB\b", re.IGNORECASE),
    "SQLite datetime()": re.compile(r"\bdatetime\s*\(", re.IGNORECASE),
}

AUTH_INTEGER_BOOLEAN_PATTERNS = {
    "integer active comparison/assignment": re.compile(
        r"\bactive\s*=\s*[01]\b",
        re.IGNORECASE,
    ),
    "integer active COALESCE": re.compile(
        r"\bCOALESCE\s*\(\s*(?:\w+\.)?active\s*,\s*[01]\s*\)",
        re.IGNORECASE,
    ),
}


def _scope_paths() -> tuple[Path, ...]:
    paths = tuple(SERVICE_ROOT / filename for filename in SCOPE_FILES)
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise AssertionError(f"PR2j static gate scope files ontbreken: {missing}")
    return paths


def _string_value(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            value.value
            for value in node.values
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
        )
    return None


def _text_sql_literals(source: str) -> list[str]:
    tree = ast.parse(source)
    sql: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        is_text = (
            isinstance(func, ast.Name) and func.id == "text"
        ) or (
            isinstance(func, ast.Attribute) and func.attr == "text"
        )
        if not is_text:
            continue
        value = _string_value(node.args[0])
        if value is not None:
            sql.append(value)
    return sql


def _auth_values_clause_uses_integer_boolean(sql: str) -> bool:
    normalized = " ".join(sql.split())
    upper = normalized.upper()
    if "INSERT INTO AUTH_" not in upper or " ACTIVE" not in upper or "VALUES" not in upper:
        return False
    values_clause = normalized.split("VALUES", 1)[1]
    values_clause = re.split(r"\bON\s+CONFLICT\b", values_clause, maxsplit=1, flags=re.IGNORECASE)[0]
    return bool(re.search(r"(?<![:\w])[01](?!\w)", values_clause))


def _assert_runtime_sql_portable() -> None:
    failures: list[str] = []
    for path in _scope_paths():
        source = path.read_text(encoding="utf-8")
        for index, sql in enumerate(_text_sql_literals(source), start=1):
            for label, pattern in FORBIDDEN_SQL_PATTERNS.items():
                if pattern.search(sql):
                    failures.append(f"{path.name}: SQL#{index}: {label}")

            if "auth_" not in sql.lower():
                continue
            for label, pattern in AUTH_INTEGER_BOOLEAN_PATTERNS.items():
                if pattern.search(sql):
                    failures.append(f"{path.name}: SQL#{index}: {label}")
            if _auth_values_clause_uses_integer_boolean(sql):
                failures.append(
                    f"{path.name}: SQL#{index}: integer literal in auth INSERT VALUES clause"
                )

    if failures:
        raise AssertionError(
            "PR2j authorization runtime SQL is not PostgreSQL portable:\n- "
            + "\n- ".join(sorted(failures))
        )
    print("POSTGRESQL_AUTHORIZATION_SQL_PORTABLE_GREEN")


def _assert_runtime_schema_authority_absent() -> None:
    failures: list[str] = []
    for path in _scope_paths():
        source = path.read_text(encoding="utf-8")
        for index, sql in enumerate(_text_sql_literals(source), start=1):
            normalized = " ".join(sql.upper().split())
            if any(
                token in normalized
                for token in (
                    "CREATE TABLE",
                    "CREATE INDEX",
                    "CREATE UNIQUE INDEX",
                    "CREATE TRIGGER",
                    "ALTER TABLE",
                    "DROP TABLE",
                    "DROP INDEX",
                    "DROP TRIGGER",
                )
            ):
                failures.append(f"{path.name}: SQL#{index}")
    if failures:
        raise AssertionError(
            "PR2j authorization paths still own runtime schema mutations: "
            + ", ".join(sorted(failures))
        )
    print("POSTGRESQL_AUTHORIZATION_RUNTIME_DDL_ABSENT_GREEN")


def _assert_validation_only_schema_contract() -> None:
    source = (SERVICE_ROOT / "authorization_foundation_service.py").read_text(
        encoding="utf-8"
    )
    required = (
        "def validate_authorization_foundation_schema",
        "inspector = inspect(conn)",
        "def ensure_authorization_foundation",
        "validate_authorization_foundation_schema(conn)",
        "_seed_registry(conn)",
    )
    missing = [token for token in required if token not in source]
    if missing:
        raise AssertionError(
            f"PR2j authorization validation/DML contract incomplete: {missing}"
        )
    print("POSTGRESQL_AUTHORIZATION_VALIDATION_ONLY_SCHEMA_GREEN")


def main() -> None:
    scope = _scope_paths()
    if len(scope) != len(SCOPE_FILES):
        raise AssertionError("PR2j static gate resolved incomplete service scope")
    print(
        "POSTGRESQL_AUTHORIZATION_SCOPE_GREEN "
        f"service_files={len(scope)}"
    )
    _assert_runtime_sql_portable()
    _assert_runtime_schema_authority_absent()
    _assert_validation_only_schema_contract()
    print("POSTGRESQL_AUTHORIZATION_STATIC_AUTHORITY_SELFTEST_GREEN")


if __name__ == "__main__":
    main()

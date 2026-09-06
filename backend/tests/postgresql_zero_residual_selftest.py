from __future__ import annotations

import ast
from pathlib import Path
import re


BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"

# Explicit SQLite test/dev compatibility is allowed only at these narrow
# boundaries. Production request/runtime SQL remains fully scanned.
EXPLICIT_SQLITE_TEST_DEV_PATHS: set[Path] = set()
EXPLICIT_SQLITE_TEST_DEV_FUNCTIONS = {
    Path("api/routes/kassa_regression_routes.py"): {"_init_test_database"},
}

# Transitional existing-SQLite adoption and the dedicated production-data
# migration utilities are explicit compatibility boundaries, never request/runtime
# SQL. Pin their exact SQLite introspection so it cannot silently spread.
SQLITE_COMPATIBILITY_SQL_ALLOWLIST = {
    Path("schema_migration_preflight.py"): {
        "sqlite_master": 3,
    },
    Path("maintenance/postgresql_data_migration.py"): {
        "PRAGMA": 3,
        "sqlite_master": 2,
    },
    Path("maintenance/postgresql_data_migration_head.py"): {
        "PRAGMA": 1,
    },
    Path("maintenance/postgresql_legacy_production_rebuild.py"): {
        "PRAGMA": 8,
        "sqlite_master": 4,
    },
}

# PostgreSQL Boolean authority established by the canonical migration.
# App code is deliberately raw-SQL heavy, so these columns cannot be discovered
# reliably from ORM models alone.
CANONICAL_POSTGRESQL_BOOLEAN_COLUMNS = {
    "is_active",
    "is_auto_prefilled",
    "is_deleted",
    "is_primary",
    "is_validated",
    "member_allowed",
    "totals_overridden",
}

DDL_PATTERNS = {
    "CREATE TABLE": re.compile(r"\bCREATE\s+TABLE\b", re.IGNORECASE),
    "CREATE INDEX": re.compile(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b", re.IGNORECASE),
    "ALTER TABLE": re.compile(r"\bALTER\s+TABLE\b", re.IGNORECASE),
    "DROP TABLE/INDEX": re.compile(r"\bDROP\s+(?:TABLE|INDEX)\b", re.IGNORECASE),
}

# High-confidence SQLite-only constructs that may never occur in PostgreSQL
# application SQL. These patterns intentionally cover column/expression arguments,
# not only historical datetime('now') forms.
SQLITE_SQL_PATTERNS = {
    "PRAGMA": re.compile(r"^\s*PRAGMA\s+\w+", re.IGNORECASE),
    "sqlite_master": re.compile(r"\bsqlite_master\b", re.IGNORECASE),
    "AUTOINCREMENT": re.compile(r"\bAUTOINCREMENT\b", re.IGNORECASE),
    "INSERT OR IGNORE": re.compile(r"\bINSERT\s+OR\s+IGNORE\b", re.IGNORECASE),
    "INSERT OR REPLACE": re.compile(r"\bINSERT\s+OR\s+REPLACE\b", re.IGNORECASE),
    "GLOB": re.compile(r"\bGLOB\b", re.IGNORECASE),
    "COLLATE NOCASE": re.compile(r"\bCOLLATE\s+NOCASE\b", re.IGNORECASE),
    "last_insert_rowid": re.compile(r"\blast_insert_rowid\s*\(", re.IGNORECASE),
    "SQLite datetime()": re.compile(r"\bdatetime\s*\(", re.IGNORECASE),
    "SQLite strftime()": re.compile(r"\bstrftime\s*\(", re.IGNORECASE),
    "SQLite julianday()": re.compile(r"\bjulianday\s*\(", re.IGNORECASE),
    "SQLite unixepoch()": re.compile(r"\bunixepoch\s*\(", re.IGNORECASE),
    "SQLite GROUP_CONCAT()": re.compile(r"\bGROUP_CONCAT\s*\(", re.IGNORECASE),
    "SQLite IFNULL()": re.compile(r"\bIFNULL\s*\(", re.IGNORECASE),
    "SQLite IIF()": re.compile(r"\bIIF\s*\(", re.IGNORECASE),
    "SQLite changes()": re.compile(r"\bchanges\s*\(", re.IGNORECASE),
    "SQLite randomblob()": re.compile(r"\brandomblob\s*\(", re.IGNORECASE),
    "SQLite hex()": re.compile(r"\bhex\s*\(", re.IGNORECASE),
    "SQLite zeroblob()": re.compile(r"\bzeroblob\s*\(", re.IGNORECASE),
    "SQLite typeof()": re.compile(r"\btypeof\s*\(", re.IGNORECASE),
}

SQL_FRAGMENT_MARKER = re.compile(
    r"\b(?:SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|ORDER\s+BY|GROUP\s+BY|HAVING|"
    r"JOIN|SET|VALUES|CREATE|ALTER|DROP|PRAGMA|ON\s+CONFLICT|datetime|strftime|"
    r"julianday|unixepoch|GROUP_CONCAT|IFNULL|IIF|changes|randomblob|zeroblob|typeof|hex)\b",
    re.IGNORECASE,
)
EXECUTION_SINKS = {"execute", "exec_driver_sql", "executescript"}


def _relative(path: Path) -> Path:
    return path.relative_to(APP_ROOT)


def _python_paths() -> list[Path]:
    return sorted(
        path
        for path in APP_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts
        and "testing" not in _relative(path).parts
    )


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        prefix = _call_name(func.value)
        return f"{prefix}.{func.attr}" if prefix else func.attr
    return ""


def _string_literals(node: ast.AST):
    for candidate in ast.walk(node):
        if isinstance(candidate, ast.Constant) and isinstance(candidate.value, str):
            yield candidate


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for candidate in ast.walk(tree):
        if not isinstance(candidate, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(candidate, "body", None) or []
        if not body or not isinstance(body[0], ast.Expr):
            continue
        value = body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            ids.add(id(value))
    return ids


def _explicit_compat_ranges(tree: ast.AST, relative: Path) -> tuple[tuple[int, int], ...]:
    names = EXPLICIT_SQLITE_TEST_DEV_FUNCTIONS.get(relative, set())
    if not names:
        return ()
    ranges: list[tuple[int, int]] = []
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            ranges.append((node.lineno, int(node.end_lineno or node.lineno)))
            found.add(node.name)
    missing = names - found
    if missing:
        raise AssertionError(
            f"Pinned SQLite test/dev function disappeared from {relative}: {sorted(missing)}"
        )
    return tuple(ranges)


def _inside_ranges(line: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(start <= line <= end for start, end in ranges)


def _boolean_column_names(trees: dict[Path, ast.AST]) -> set[str]:
    names: set[str] = set(CANONICAL_POSTGRESQL_BOOLEAN_COLUMNS)
    for tree in trees.values():
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            if not isinstance(value, ast.Call):
                continue
            call_name = _call_name(value.func).rsplit(".", 1)[-1]
            if call_name not in {"Column", "mapped_column"}:
                continue
            if not any(
                (isinstance(arg, ast.Name) and arg.id == "Boolean")
                or (isinstance(arg, ast.Attribute) and arg.attr == "Boolean")
                for arg in value.args
            ):
                continue
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets.extend(node.targets)
            elif node.target is not None:
                targets.append(node.target)
            for target in targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def _boolean_integer_pattern(column_name: str) -> re.Pattern[str]:
    escaped = re.escape(column_name)
    return re.compile(
        rf"(?:\b\w+\.)?\b{escaped}\b\s*(?:=|<>|!=)\s*[01]\b|"
        rf"\b[01]\s*(?:=|<>|!=)\s*(?:\w+\.)?\b{escaped}\b|"
        rf"\bSET\s+(?:\w+\.)?\b{escaped}\b\s*=\s*[01]\b|"
        rf"\bCOALESCE\s*\(\s*(?:\w+\.)?\b{escaped}\b\s*,\s*[01]\s*\)",
        re.IGNORECASE,
    )


def _is_integer_boolean_expr(node: ast.AST | None) -> bool:
    if isinstance(node, ast.Constant):
        return type(node.value) is int and node.value in {0, 1}
    if isinstance(node, ast.IfExp):
        return _is_integer_boolean_expr(node.body) and _is_integer_boolean_expr(node.orelse)
    return False


def _integer_boolean_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _is_integer_boolean_expr(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and _is_integer_boolean_expr(node.value):
            if isinstance(node.target, ast.Name):
                names.add(node.target.id)
    return names


def _mapping_boolean_violations(
    node: ast.AST,
    boolean_columns: set[str],
    integer_boolean_names: set[str],
) -> list[tuple[int, str]]:
    violations: list[tuple[int, str]] = []
    for candidate in ast.walk(node):
        if not isinstance(candidate, ast.Dict):
            continue
        for key_node, value_node in zip(candidate.keys, candidate.values):
            if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
                continue
            key = key_node.value
            if key not in boolean_columns:
                continue
            bad_value = _is_integer_boolean_expr(value_node)
            if isinstance(value_node, ast.Name) and value_node.id in integer_boolean_names:
                bad_value = True
            if bad_value:
                violations.append(
                    (int(getattr(value_node, "lineno", getattr(candidate, "lineno", 0)) or 0), key)
                )
    return violations


def _looks_like_sql_fragment(value: str) -> bool:
    return bool(SQL_FRAGMENT_MARKER.search(value))


def main() -> None:
    paths = _python_paths()
    trees = {
        path: ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for path in paths
    }
    boolean_columns = _boolean_column_names(trees)

    ddl_violations: list[str] = []
    sqlite_violations: list[str] = []
    boolean_violations: list[str] = []
    compatibility_hits: dict[tuple[Path, str], int] = {}

    for path, tree in trees.items():
        relative = _relative(path)
        if relative in EXPLICIT_SQLITE_TEST_DEV_PATHS:
            continue
        compat_ranges = _explicit_compat_ranges(tree, relative)
        integer_boolean_names = _integer_boolean_names(tree)
        docstring_ids = _docstring_ids(tree)

        # Scan every SQL-looking literal, not only literals nested directly in
        # conn.execute(...). This catches dynamically assembled SQL fragments.
        for string_node in _string_literals(tree):
            if id(string_node) in docstring_ids:
                continue
            value = string_node.value
            string_line = int(getattr(string_node, "lineno", 0) or 0)
            if _inside_ranges(string_line, compat_ranges):
                continue
            if not _looks_like_sql_fragment(value):
                continue

            for label, pattern in DDL_PATTERNS.items():
                if pattern.search(value):
                    ddl_violations.append(f"{relative}:{string_line}:{label}")

            for label, pattern in SQLITE_SQL_PATTERNS.items():
                matches = pattern.findall(value)
                if not matches:
                    continue
                expected = SQLITE_COMPATIBILITY_SQL_ALLOWLIST.get(relative, {}).get(label)
                if expected is not None:
                    key = (relative, label)
                    compatibility_hits[key] = compatibility_hits.get(key, 0) + len(matches)
                    continue
                sqlite_violations.append(f"{relative}:{string_line}:{label}")

            for column_name in sorted(boolean_columns):
                if _boolean_integer_pattern(column_name).search(value):
                    boolean_violations.append(
                        f"{relative}:{string_line}:{column_name}=integer-literal"
                    )

        # Keep execution-sink awareness for create_all and bound Boolean params.
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            line = int(getattr(node, "lineno", 0) or 0)
            if _inside_ranges(line, compat_ranges):
                continue
            call_name = _call_name(node.func)
            short_name = call_name.rsplit(".", 1)[-1]
            if call_name.endswith(".create_all"):
                ddl_violations.append(f"{relative}:{line}:create_all")
                continue
            if short_name not in EXECUTION_SINKS:
                continue
            for mapping_line, column_name in _mapping_boolean_violations(
                node, boolean_columns, integer_boolean_names
            ):
                boolean_violations.append(
                    f"{relative}:{mapping_line}:{column_name}=integer-bound-param"
                )

    compatibility_drift: list[str] = []
    for relative, labels in SQLITE_COMPATIBILITY_SQL_ALLOWLIST.items():
        for label, expected_count in labels.items():
            actual_count = compatibility_hits.get((relative, label), 0)
            if actual_count != expected_count:
                compatibility_drift.append(
                    f"{relative}:{label}:expected={expected_count}:actual={actual_count}"
                )

    categories = [
        ("RUNTIME_DDL", sorted(set(ddl_violations))),
        ("SQLITE_SQL", sorted(set(sqlite_violations))),
        ("BOOLEAN", sorted(set(boolean_violations))),
        ("COMPATIBILITY_BOUNDARY", sorted(set(compatibility_drift))),
    ]
    all_violations: list[str] = []
    for category, violations in categories:
        for violation in violations:
            finding = f"{category}:{violation}"
            all_violations.append(finding)
            print(f"POSTGRESQL_ZERO_RESIDUAL_FINDING={finding}")

    if all_violations:
        raise AssertionError(
            "PostgreSQL zero-residual violations remain in backend/app: "
            + ", ".join(all_violations)
        )

    print("POSTGRESQL_ZERO_RESIDUAL_RUNTIME_DDL_GREEN")
    print("POSTGRESQL_ZERO_RESIDUAL_SQLITE_SQL_GREEN")
    print("POSTGRESQL_ZERO_RESIDUAL_BOOLEAN_GREEN")
    print("POSTGRESQL_ZERO_RESIDUAL_COMPATIBILITY_BOUNDARY_GREEN")
    print(f"POSTGRESQL_ZERO_RESIDUAL_BOOLEAN_COLUMNS={len(boolean_columns)}")
    print(f"POSTGRESQL_ZERO_RESIDUAL_APP_FILES={len(paths)}")
    print("POSTGRESQL_ZERO_RESIDUAL_GATE_GREEN")


if __name__ == "__main__":
    main()

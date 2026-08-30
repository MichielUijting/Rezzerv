from __future__ import annotations

import ast
from pathlib import Path
import re


BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"

# Explicit SQLite test/dev compatibility is allowed only at these narrow
# boundaries. Production request/runtime SQL remains fully scanned.
EXPLICIT_SQLITE_TEST_DEV_PATHS = {
    Path("cli/import_gpc_catalog_controlled.py"),
    Path("cli/rehearse_gpc_bilingual_import.py"),
    Path("testing_receipt_parser_diagnosis_routes.py"),
}
EXPLICIT_SQLITE_TEST_DEV_FUNCTIONS = {
    Path("api/routes/kassa_regression_routes.py"): {"_init_test_database"},
}

# Transitional existing-SQLite adoption remains production-cutover debt. Pin
# its exact runtime introspection so it cannot silently spread before that
# later cutover removes the compatibility path entirely.
SQLITE_COMPATIBILITY_SQL_ALLOWLIST = {
    Path("schema_migration_preflight.py"): {
        "sqlite_master": 2,
    },
}

DDL_PATTERNS = {
    "CREATE TABLE": re.compile(r"\bCREATE\s+TABLE\b", re.IGNORECASE),
    "CREATE INDEX": re.compile(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b", re.IGNORECASE),
    "ALTER TABLE": re.compile(r"\bALTER\s+TABLE\b", re.IGNORECASE),
    "DROP TABLE/INDEX": re.compile(r"\bDROP\s+(?:TABLE|INDEX)\b", re.IGNORECASE),
}
SQLITE_SQL_PATTERNS = {
    "PRAGMA": re.compile(r"\bPRAGMA\b", re.IGNORECASE),
    "sqlite_master": re.compile(r"\bsqlite_master\b", re.IGNORECASE),
    "AUTOINCREMENT": re.compile(r"\bAUTOINCREMENT\b", re.IGNORECASE),
    "INSERT OR IGNORE": re.compile(r"\bINSERT\s+OR\s+IGNORE\b", re.IGNORECASE),
    "INSERT OR REPLACE": re.compile(r"\bINSERT\s+OR\s+REPLACE\b", re.IGNORECASE),
    "GLOB": re.compile(r"\bGLOB\b", re.IGNORECASE),
    "COLLATE NOCASE": re.compile(r"\bCOLLATE\s+NOCASE\b", re.IGNORECASE),
    "last_insert_rowid": re.compile(r"\blast_insert_rowid\s*\(", re.IGNORECASE),
    "SQLite datetime": re.compile(
        r"\b(?:datetime|date|time|strftime|julianday)\s*\(\s*['\"](?:now|unixepoch)",
        re.IGNORECASE,
    ),
}
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
    names: set[str] = set()
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
        rf"\bSET\s+(?:\w+\.)?\b{escaped}\b\s*=\s*[01]\b",
        re.IGNORECASE,
    )


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

            for string_node in _string_literals(node):
                value = string_node.value
                string_line = int(getattr(string_node, "lineno", line) or line)

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

    compatibility_drift: list[str] = []
    for relative, labels in SQLITE_COMPATIBILITY_SQL_ALLOWLIST.items():
        for label, expected_count in labels.items():
            actual_count = compatibility_hits.get((relative, label), 0)
            if actual_count != expected_count:
                compatibility_drift.append(
                    f"{relative}:{label}:expected={expected_count}:actual={actual_count}"
                )

    if ddl_violations:
        raise AssertionError(
            "Runtime DDL remains in backend/app: " + ", ".join(sorted(set(ddl_violations)))
        )
    print("POSTGRESQL_ZERO_RESIDUAL_RUNTIME_DDL_GREEN")

    if sqlite_violations:
        raise AssertionError(
            "SQLite-only production SQL remains in backend/app: "
            + ", ".join(sorted(set(sqlite_violations)))
        )
    print("POSTGRESQL_ZERO_RESIDUAL_SQLITE_SQL_GREEN")

    if boolean_violations:
        raise AssertionError(
            "Integer Boolean SQL remains in backend/app: "
            + ", ".join(sorted(set(boolean_violations)))
        )
    print("POSTGRESQL_ZERO_RESIDUAL_BOOLEAN_GREEN")

    if compatibility_drift:
        raise AssertionError(
            "Pinned SQLite compatibility boundary drifted: "
            + ", ".join(sorted(compatibility_drift))
        )
    print("POSTGRESQL_ZERO_RESIDUAL_COMPATIBILITY_BOUNDARY_GREEN")
    print(f"POSTGRESQL_ZERO_RESIDUAL_BOOLEAN_COLUMNS={len(boolean_columns)}")
    print(f"POSTGRESQL_ZERO_RESIDUAL_APP_FILES={len(paths)}")
    print("POSTGRESQL_ZERO_RESIDUAL_GATE_GREEN")


if __name__ == "__main__":
    main()

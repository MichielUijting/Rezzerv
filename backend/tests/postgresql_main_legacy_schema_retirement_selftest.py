from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = BACKEND_ROOT / "app" / "main.py"
STARTUP_ROOT = BACKEND_ROOT / "app" / "startup"


def main() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")
    upper = source.upper()
    forbidden = (
        "CREATE TABLE",
        "ALTER TABLE",
        "CREATE INDEX",
        "DROP TABLE",
        "DROP INDEX",
        "PRAGMA ",
    )
    for marker in forbidden:
        if marker in upper:
            raise AssertionError(f"Legacy schema DDL remains in main.py: {marker}")

    tree = ast.parse(source)
    legacy = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("ensure_release_")
    ]
    if legacy:
        raise AssertionError(legacy)

    for node in tree.body:
        if isinstance(node, (ast.With, ast.AsyncWith)):
            segment = ast.get_source_segment(source, node) or ""
            if "engine.begin()" in segment:
                raise AssertionError("Top-level database side effect remains in main.py")

    required = (
        STARTUP_ROOT / "runtime_schema_validation.py",
        STARTUP_ROOT / "runtime_observability.py",
        STARTUP_ROOT / "runtime_initialization.py",
    )
    for path in required:
        if not path.exists():
            raise AssertionError(f"Missing startup module: {path}")

    if "validate_runtime_schema(engine)" not in source:
        raise AssertionError("Runtime schema validation is not centralized")
    if "run_runtime_initialization(" not in source:
        raise AssertionError("Runtime initialization is not centralized")
    if 'app.add_event_handler("startup", log_runtime_datastore_configuration_event)' not in source:
        raise AssertionError("Startup observability is not registered through startup module")
    if "sa_inspect(conn).get_columns(table_name)" not in source:
        raise AssertionError("Active table metadata helper is not dialect-independent")

    print("POSTGRESQL_MAIN_LEGACY_DDL_ABSENT_GREEN")
    print("POSTGRESQL_MAIN_TABLE_METADATA_PORTABLE_GREEN")
    print("POSTGRESQL_MAIN_TOP_LEVEL_DB_SIDE_EFFECTS_CENTRALIZED_GREEN")
    print("POSTGRESQL_MAIN_STARTUP_STRUCTURE_GREEN")
    print("POSTGRESQL_MAIN_LEGACY_SCHEMA_RETIREMENT_SELFTEST_GREEN")


if __name__ == "__main__":
    main()

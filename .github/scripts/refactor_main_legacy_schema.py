from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN_PATH = ROOT / "backend/app/main.py"
STARTUP_ROOT = ROOT / "backend/app/startup"
TEST_PATH = ROOT / "backend/tests/postgresql_main_legacy_schema_retirement_selftest.py"

DDL_MARKERS = (
    "CREATE TABLE",
    "ALTER TABLE",
    "CREATE INDEX",
    "DROP TABLE",
    "DROP INDEX",
    "PRAGMA ",
)


def _function_segment(source: str, node: ast.AST) -> str:
    return ast.get_source_segment(source, node) or ""


def _is_legacy_schema_function(node: ast.FunctionDef | ast.AsyncFunctionDef, source: str) -> bool:
    segment_upper = _function_segment(source, node).upper()
    if any(marker in segment_upper for marker in DDL_MARKERS):
        return True
    if node.name.startswith("ensure_release_"):
        return True
    return False


def _portable_table_columns(source: str) -> str:
    old = '''def get_table_columns(conn, table_name: str) -> set[str]:\n    return {row['name'] for row in conn.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()}\n'''
    new = '''def get_table_columns(conn, table_name: str) -> set[str]:\n    """Read canonical table metadata without mutating schema or assuming SQLite."""\n    return {str(column["name"]) for column in sa_inspect(conn).get_columns(table_name)}\n'''
    if old not in source:
        raise SystemExit("Expected legacy get_table_columns implementation not found")
    return source.replace(old, new, 1)


def _candidate_nodes(source: str) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    tree = ast.parse(source)
    return [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and _is_legacy_schema_function(node, source)
    ]


def _active_references(
    source: str,
    candidates: list[ast.FunctionDef | ast.AsyncFunctionDef],
) -> dict[str, list[str]]:
    names = {node.name for node in candidates}
    ranges = [
        (int(node.lineno), int(node.end_lineno or node.lineno))
        for node in candidates
    ]

    def in_candidate(line: int) -> bool:
        return any(start <= line <= end for start, end in ranges)

    refs: dict[str, list[str]] = {name: [] for name in names}
    main_tree = ast.parse(source)
    for node in ast.walk(main_tree):
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id in names
            and not in_candidate(int(getattr(node, "lineno", 0) or 0))
        ):
            refs[node.id].append(f"backend/app/main.py:{getattr(node, 'lineno', '?')}")

    for py_path in (ROOT / "backend").rglob("*.py"):
        if py_path == MAIN_PATH:
            continue
        try:
            py_tree = ast.parse(py_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in ast.walk(py_tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            module = str(node.module or "")
            if module not in {"app.main", "backend.app.main"}:
                continue
            for alias in node.names:
                if alias.name in names:
                    refs[alias.name].append(
                        f"{py_path.relative_to(ROOT)}:{getattr(node, 'lineno', '?')} import"
                    )

    return {name: values for name, values in refs.items() if values}


def _remove_functions(
    source: str,
    candidates: list[ast.FunctionDef | ast.AsyncFunctionDef],
) -> str:
    lines = source.splitlines(keepends=True)
    remove: set[int] = set()
    for node in candidates:
        start = int(node.lineno)
        end = int(node.end_lineno or node.lineno)
        if start > 1 and not lines[start - 2].strip():
            start -= 1
        remove.update(range(start, end + 1))
    return "".join(
        line for number, line in enumerate(lines, start=1) if number not in remove
    )


def _centralize_schema_validation(source: str) -> str:
    old_import = "from app.db import engine, get_runtime_datastore_info\n"
    new_import = (
        "from app.db import engine\n"
        "from app.startup.runtime_initialization import run_runtime_initialization\n"
        "from app.startup.runtime_observability import log_runtime_datastore_configuration_event\n"
        "from app.startup.runtime_schema_validation import validate_runtime_schema\n"
    )
    if old_import not in source:
        raise SystemExit("Expected app.db import not found")
    source = source.replace(old_import, new_import, 1)
    source = source.replace("    ensure_external_article_product_link_schema,\n", "", 1)

    old = (
        "app = FastAPI()\n"
        "# Externe-databases-koppelingen: idempotente schema-initialisatie.\n"
        "with engine.begin() as schema_conn:\n"
        "    ensure_external_article_product_link_schema(schema_conn)\n"
    )
    if old not in source:
        raise SystemExit("Expected inline runtime schema validation block not found")
    return source.replace(
        old,
        "app = FastAPI()\n"
        "# Runtime schema validation is centralized; Alembic remains exclusive schema authority.\n"
        "validate_runtime_schema(engine)\n",
        1,
    )


def _centralize_observability(source: str) -> str:
    tree = ast.parse(source)
    node = next(
        (
            item
            for item in tree.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == "log_runtime_datastore_configuration"
        ),
        None,
    )
    if node is None:
        raise SystemExit("Expected log_runtime_datastore_configuration startup handler not found")
    start = int(node.lineno)
    if node.decorator_list:
        start = min(start, *(int(item.lineno) for item in node.decorator_list))
    end = int(node.end_lineno or node.lineno)
    lines = source.splitlines(keepends=True)
    return "".join(
        lines[: start - 1]
        + ['app.add_event_handler("startup", log_runtime_datastore_configuration_event)\n']
        + lines[end:]
    )


def _centralize_runtime_initialization(source: str) -> str:
    old = '''with engine.begin() as external_link_cleanup_conn:\n    external_link_cleanup_count = (\n        deactivate_incomplete_confirmed_external_links(\n            external_link_cleanup_conn\n        )\n    )\n\nlogger.info(\n    "Incomplete kassabonartikelkoppelingen gedeactiveerd: %s",\n    external_link_cleanup_count,\n)\n\nbootstrap_auth_registry()\nwith engine.begin() as authorization_membership_backfill_conn:\n    migrate_legacy_household_memberships(authorization_membership_backfill_conn)\nrefresh_runtime_users_from_db()\nensure_receipt_storage_root()\nseed_store_providers()\nadmin_household = ensure_household("admin@rezzerv.local")\nadmin_household_id = str(admin_household.get("id") or "1")\nensure_default_receipt_sources(engine, RECEIPT_STORAGE_ROOT, admin_household_id)\ndedupe_receipts_for_household(engine, admin_household_id)\n'''
    new = '''run_runtime_initialization(\n    engine=engine,\n    logger=logger,\n    deactivate_incomplete_confirmed_external_links=deactivate_incomplete_confirmed_external_links,\n    bootstrap_auth_registry=bootstrap_auth_registry,\n    migrate_legacy_household_memberships=migrate_legacy_household_memberships,\n    refresh_runtime_users_from_db=refresh_runtime_users_from_db,\n    ensure_receipt_storage_root=ensure_receipt_storage_root,\n    seed_store_providers=seed_store_providers,\n    ensure_household=ensure_household,\n    ensure_default_receipt_sources=ensure_default_receipt_sources,\n    dedupe_receipts_for_household=dedupe_receipts_for_household,\n    receipt_storage_root=RECEIPT_STORAGE_ROOT,\n)\n'''
    if old not in source:
        raise SystemExit("Expected import-time runtime initialization block not found")
    return source.replace(old, new, 1)


def _write_startup_modules() -> None:
    STARTUP_ROOT.mkdir(parents=True, exist_ok=True)
    (STARTUP_ROOT / "__init__.py").write_text(
        '"""Runtime startup orchestration and validation boundaries."""\n',
        encoding="utf-8",
    )
    (STARTUP_ROOT / "runtime_schema_validation.py").write_text(
        '''"""Runtime schema validation only; Alembic exclusively owns schema mutation."""\n\nfrom app.services.external_article_product_link_service import (\n    ensure_external_article_product_link_schema,\n)\n\n\ndef validate_runtime_schema(engine) -> None:\n    with engine.begin() as connection:\n        ensure_external_article_product_link_schema(connection)\n''',
        encoding="utf-8",
    )
    (STARTUP_ROOT / "runtime_observability.py").write_text(
        '''"""Startup observability for the configured runtime datastore."""\n\nimport logging\n\nfrom app.db import get_runtime_datastore_info\n\n\nlogger = logging.getLogger("rezzerv.api")\n\n\nasync def log_runtime_datastore_configuration_event() -> None:\n    datastore_info = get_runtime_datastore_info()\n    logger.info("Datastore: %s", datastore_info.get("datastore", "onbekend"))\n    logger.info(\n        "Database: %s",\n        datastore_info.get("database")\n        or datastore_info.get("database_url")\n        or "onbekend",\n    )\n    if datastore_info.get("storage"):\n        logger.info("Storage: %s", datastore_info["storage"])\n''',
        encoding="utf-8",
    )
    (STARTUP_ROOT / "runtime_initialization.py").write_text(
        '''"""Ordered DML/bootstrap initialization performed after migration preflight."""\n\nfrom __future__ import annotations\n\nfrom pathlib import Path\nfrom typing import Any, Callable\n\n\ndef run_runtime_initialization(\n    *,\n    engine,\n    logger,\n    deactivate_incomplete_confirmed_external_links: Callable[[Any], int],\n    bootstrap_auth_registry: Callable[[], None],\n    migrate_legacy_household_memberships: Callable[[Any], Any],\n    refresh_runtime_users_from_db: Callable[[], None],\n    ensure_receipt_storage_root: Callable[[], None],\n    seed_store_providers: Callable[[], None],\n    ensure_household: Callable[[str], dict[str, Any]],\n    ensure_default_receipt_sources: Callable[[Any, Path, str], Any],\n    dedupe_receipts_for_household: Callable[[Any, str], Any],\n    receipt_storage_root: Path,\n) -> None:\n    with engine.begin() as connection:\n        cleanup_count = deactivate_incomplete_confirmed_external_links(connection)\n    logger.info(\n        "Incomplete kassabonartikelkoppelingen gedeactiveerd: %s",\n        cleanup_count,\n    )\n\n    bootstrap_auth_registry()\n    with engine.begin() as connection:\n        migrate_legacy_household_memberships(connection)\n    refresh_runtime_users_from_db()\n    ensure_receipt_storage_root()\n    seed_store_providers()\n\n    admin_household = ensure_household("admin@rezzerv.local")\n    admin_household_id = str(admin_household.get("id") or "1")\n    ensure_default_receipt_sources(engine, receipt_storage_root, admin_household_id)\n    dedupe_receipts_for_household(engine, admin_household_id)\n''',
        encoding="utf-8",
    )


def _write_selftest() -> None:
    TEST_PATH.write_text(
        '''from __future__ import annotations\n\nimport ast\nfrom pathlib import Path\n\nBACKEND_ROOT = Path(__file__).resolve().parents[1]\nMAIN_PATH = BACKEND_ROOT / "app" / "main.py"\nSTARTUP_ROOT = BACKEND_ROOT / "app" / "startup"\n\n\ndef main() -> None:\n    source = MAIN_PATH.read_text(encoding="utf-8")\n    upper = source.upper()\n    forbidden = (\n        "CREATE TABLE",\n        "ALTER TABLE",\n        "CREATE INDEX",\n        "DROP TABLE",\n        "DROP INDEX",\n        "PRAGMA ",\n    )\n    for marker in forbidden:\n        if marker in upper:\n            raise AssertionError(f"Legacy schema DDL remains in main.py: {marker}")\n\n    tree = ast.parse(source)\n    legacy = [\n        node.name\n        for node in tree.body\n        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))\n        and node.name.startswith("ensure_release_")\n    ]\n    if legacy:\n        raise AssertionError(legacy)\n\n    for node in tree.body:\n        if isinstance(node, (ast.With, ast.AsyncWith)):\n            segment = ast.get_source_segment(source, node) or ""\n            if "engine.begin()" in segment:\n                raise AssertionError("Top-level database side effect remains in main.py")\n\n    required = (\n        STARTUP_ROOT / "runtime_schema_validation.py",\n        STARTUP_ROOT / "runtime_observability.py",\n        STARTUP_ROOT / "runtime_initialization.py",\n    )\n    for path in required:\n        if not path.exists():\n            raise AssertionError(f"Missing startup module: {path}")\n\n    if "validate_runtime_schema(engine)" not in source:\n        raise AssertionError("Runtime schema validation is not centralized")\n    if "run_runtime_initialization(" not in source:\n        raise AssertionError("Runtime initialization is not centralized")\n    if 'app.add_event_handler("startup", log_runtime_datastore_configuration_event)' not in source:\n        raise AssertionError("Startup observability is not registered through startup module")\n    if "sa_inspect(conn).get_columns(table_name)" not in source:\n        raise AssertionError("Active table metadata helper is not dialect-independent")\n\n    print("POSTGRESQL_MAIN_LEGACY_DDL_ABSENT_GREEN")\n    print("POSTGRESQL_MAIN_TABLE_METADATA_PORTABLE_GREEN")\n    print("POSTGRESQL_MAIN_TOP_LEVEL_DB_SIDE_EFFECTS_CENTRALIZED_GREEN")\n    print("POSTGRESQL_MAIN_STARTUP_STRUCTURE_GREEN")\n    print("POSTGRESQL_MAIN_LEGACY_SCHEMA_RETIREMENT_SELFTEST_GREEN")\n\n\nif __name__ == "__main__":\n    main()\n''',
        encoding="utf-8",
    )


def main() -> None:
    original = MAIN_PATH.read_text(encoding="utf-8")
    source = _portable_table_columns(original)
    candidates = _candidate_nodes(source)
    active = _active_references(source, candidates)
    if active:
        lines = ["Refusing to remove legacy schema functions still referenced from app.main:"]
        for name, refs in sorted(active.items()):
            lines.append(f"  {name}: {refs}")
        raise SystemExit("\n".join(lines))

    source = _remove_functions(source, candidates)
    source = _centralize_schema_validation(source)
    source = _centralize_observability(source)
    source = _centralize_runtime_initialization(source)

    residual = [marker for marker in DDL_MARKERS if marker in source.upper()]
    if residual:
        raise SystemExit(f"Legacy schema DDL still remains in main.py: {residual}")

    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.With, ast.AsyncWith)):
            segment = ast.get_source_segment(source, node) or ""
            if "engine.begin()" in segment:
                raise SystemExit("Top-level engine.begin() side effect remains in main.py")

    _write_startup_modules()
    _write_selftest()
    MAIN_PATH.write_text(source, encoding="utf-8")

    removed_lines = len(original.splitlines()) - len(source.splitlines())
    print(f"Removed {len(candidates)} dead legacy schema/release functions")
    print(f"main.py line reduction: {removed_lines}")


if __name__ == "__main__":
    main()

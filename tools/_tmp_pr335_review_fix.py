from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    source = file_path.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one replacement anchor, found {count}")
    file_path.write_text(source.replace(old, new, 1), encoding="utf-8")


def patch_main() -> None:
    path = Path("backend/app/main.py")
    source = path.read_text(encoding="utf-8")
    start = source.index("def resolve_or_create_inventory_household_article(")
    end = source.index("\n\ndef create_inventory_event(", start)
    section = source[start:end]
    old = "ORDER BY datetime(created_at) ASC, id ASC"
    if section.count(old) != 1:
        raise SystemExit("resolve_or_create_inventory_household_article fallback ordering anchor mismatch")
    section = section.replace(old, "ORDER BY created_at ASC, id ASC", 1)
    path.write_text(source[:start] + section + source[end:], encoding="utf-8")


def patch_migration() -> None:
    path = "backend/alembic/versions/20260828_03_inventory_temporal_schema_authority.py"
    replace_once(
        path,
        "from datetime import date, datetime, time, timezone\nfrom typing import Any, Sequence, Union\n",
        "from datetime import date, datetime, time, timezone\nimport re\nfrom typing import Any, Sequence, Union\n",
    )
    replace_once(
        path,
        '''def _index_contract(inspector: sa.Inspector) -> dict[str, tuple[str, ...]]:\n    return {\n        str(item.get("name") or ""): tuple(item.get("column_names") or ())\n        for item in inspector.get_indexes("inventory_events")\n    }\n\n\ndef _ensure_indexes(bind: sa.engine.Connection) -> None:\n    inspector = sa.inspect(bind)\n    indexes = _index_contract(inspector)\n    expected = {\n        _TEMPORAL_ORDER_INDEX: _TEMPORAL_ORDER_COLUMNS,\n        _SOURCE_REFERENCE_INDEX: _SOURCE_REFERENCE_COLUMNS,\n    }\n    for index_name, columns in expected.items():\n        actual = indexes.get(index_name)\n        if actual is None:\n            op.create_index(index_name, "inventory_events", list(columns), unique=False)\n        elif actual != columns:\n            raise RuntimeError(\n                f"Inventory temporal index drift: {index_name} "\n                f"expected={columns!r} actual={actual!r}"\n            )\n''',
        '''def _index_contract(inspector: sa.Inspector) -> dict[str, dict[str, Any]]:\n    return {\n        str(item.get("name") or ""): item\n        for item in inspector.get_indexes("inventory_events")\n    }\n\n\ndef _validate_temporal_index(\n    index_name: str,\n    index: dict[str, Any] | None,\n    expected_columns: tuple[str, ...],\n) -> None:\n    if not index:\n        raise RuntimeError(f"Inventory temporal index ontbreekt: {index_name}")\n    actual_columns = tuple(index.get("column_names") or ())\n    actual_unique = bool(index.get("unique"))\n    if actual_columns != expected_columns or actual_unique:\n        raise RuntimeError(\n            f"Inventory temporal index drift: {index_name} "\n            f"expected_columns={expected_columns!r} expected_unique=False "\n            f"actual_columns={actual_columns!r} actual_unique={actual_unique}"\n        )\n\n\ndef _ensure_indexes(bind: sa.engine.Connection) -> None:\n    inspector = sa.inspect(bind)\n    indexes = _index_contract(inspector)\n    expected = {\n        _TEMPORAL_ORDER_INDEX: _TEMPORAL_ORDER_COLUMNS,\n        _SOURCE_REFERENCE_INDEX: _SOURCE_REFERENCE_COLUMNS,\n    }\n    for index_name, columns in expected.items():\n        actual = indexes.get(index_name)\n        if actual is None:\n            op.create_index(index_name, "inventory_events", list(columns), unique=False)\n        else:\n            _validate_temporal_index(index_name, actual, columns)\n''',
    )
    replace_once(
        path,
        '''def _validate_locationless_identity_index(bind: sa.engine.Connection) -> None:\n''',
        '''def _normalized_predicate_terms(index_sql: str | None) -> frozenset[str]:\n    raw = str(index_sql or "")\n    where_match = re.search(r"\\bwhere\\b", raw, flags=re.IGNORECASE)\n    if not where_match:\n        return frozenset()\n    predicate = raw[where_match.end():].lower().replace('"', '')\n    predicate = re.sub(r"::[a-z_][a-z0-9_]*", "", predicate)\n    return frozenset(\n        re.sub(r"[\\s()]+", "", term)\n        for term in re.split(r"\\s+and\\s+", predicate)\n        if term.strip()\n    )\n\n\ndef _validate_locationless_identity_index(bind: sa.engine.Connection) -> None:\n''',
    )
    replace_once(
        path,
        '''    index_sql = _locationless_index_sql(bind)\n    normalized = " ".join(str(index_sql or "").lower().replace('"', '').split())\n    for fragment in (\n        "household_article_id is not null",\n        "space_id is null",\n        "sublocation_id is null",\n        "status",\n        "'active'",\n    ):\n        if fragment not in normalized:\n            raise RuntimeError(\n                "Canonical locationless inventory index wijkt af: "\n                f"missing={fragment!r} index={index_sql!r}"\n            )\n''',
        '''    index_sql = _locationless_index_sql(bind)\n    expected_terms = _normalized_predicate_terms(\n        f"CREATE INDEX canonical ON inventory (household_id, household_article_id) "\n        f"WHERE {_LOCATIONLESS_ACTIVE_IDENTITY_PREDICATE}"\n    )\n    actual_terms = _normalized_predicate_terms(index_sql)\n    if actual_terms != expected_terms:\n        raise RuntimeError(\n            "Canonical locationless inventory index predicate wijkt af: "\n            f"expected={sorted(expected_terms)!r} actual={sorted(actual_terms)!r} "\n            f"index={index_sql!r}"\n        )\n''',
    )
    replace_once(
        path,
        '''    indexes = _index_contract(inspector)\n    expected_indexes = {\n        _TEMPORAL_ORDER_INDEX: _TEMPORAL_ORDER_COLUMNS,\n        _SOURCE_REFERENCE_INDEX: _SOURCE_REFERENCE_COLUMNS,\n    }\n    for index_name, expected_columns in expected_indexes.items():\n        if indexes.get(index_name) != expected_columns:\n            raise RuntimeError(\n                f"Inventory temporal index ontbreekt of wijkt af: {index_name}"\n            )\n''',
        '''    indexes = _index_contract(inspector)\n    expected_indexes = {\n        _TEMPORAL_ORDER_INDEX: _TEMPORAL_ORDER_COLUMNS,\n        _SOURCE_REFERENCE_INDEX: _SOURCE_REFERENCE_COLUMNS,\n    }\n    for index_name, expected_columns in expected_indexes.items():\n        _validate_temporal_index(index_name, indexes.get(index_name), expected_columns)\n''',
    )


def patch_canonical_service() -> None:
    path = "backend/app/services/canonical_inventory_identity_service.py"
    replace_once(path, "from __future__ import annotations\n\nimport uuid\n", "from __future__ import annotations\n\nimport re\nimport uuid\n")
    replace_once(
        path,
        'LOCATIONLESS_ACTIVE_IDENTITY_INDEX = "uq_inventory_active_locationless_household_article"\n',
        '''LOCATIONLESS_ACTIVE_IDENTITY_INDEX = "uq_inventory_active_locationless_household_article"\nLOCATIONLESS_ACTIVE_IDENTITY_PREDICATE = (\n    "COALESCE(status, 'active') = 'active' "\n    "AND household_article_id IS NOT NULL "\n    "AND space_id IS NULL "\n    "AND sublocation_id IS NULL"\n)\n''',
    )
    replace_once(
        path,
        '''def ensure_locationless_inventory_identity_guard(conn) -> None:\n''',
        '''def _normalized_predicate_terms(index_sql: str | None) -> frozenset[str]:\n    raw = str(index_sql or "")\n    where_match = re.search(r"\\bwhere\\b", raw, flags=re.IGNORECASE)\n    if not where_match:\n        return frozenset()\n    predicate = raw[where_match.end():].lower().replace('"', '')\n    predicate = re.sub(r"::[a-z_][a-z0-9_]*", "", predicate)\n    return frozenset(\n        re.sub(r"[\\s()]+", "", term)\n        for term in re.split(r"\\s+and\\s+", predicate)\n        if term.strip()\n    )\n\n\ndef ensure_locationless_inventory_identity_guard(conn) -> None:\n''',
    )
    replace_once(
        path,
        '''    normalized = " ".join(str(index_sql).lower().replace('"', '').split())\n    for fragment in (\n        "household_article_id is not null",\n        "space_id is null",\n        "sublocation_id is null",\n        "status",\n        "'active'",\n    ):\n        if fragment not in normalized:\n            raise RuntimeError(\n                "Canonical locationless inventory index wijkt af: "\n                f"missing={fragment!r} index={index_sql!r}"\n            )\n''',
        '''    expected_terms = _normalized_predicate_terms(\n        f"CREATE INDEX canonical ON inventory (household_id, household_article_id) "\n        f"WHERE {LOCATIONLESS_ACTIVE_IDENTITY_PREDICATE}"\n    )\n    actual_terms = _normalized_predicate_terms(index_sql)\n    if actual_terms != expected_terms:\n        raise RuntimeError(\n            "Canonical locationless inventory index predicate wijkt af: "\n            f"expected={sorted(expected_terms)!r} actual={sorted(actual_terms)!r} "\n            f"index={index_sql!r}"\n        )\n''',
    )


def patch_temporal_service() -> None:
    path = "backend/app/services/temporal_inventory_service.py"
    replace_once(
        path,
        '''    indexes = {\n        str(index.get("name") or ""): tuple(index.get("column_names") or ())\n        for index in inspector.get_indexes("inventory_events")\n    }\n    for index_name, expected_columns in _TEMPORAL_INDEX_CONTRACT.items():\n        actual_columns = indexes.get(index_name)\n        if actual_columns != expected_columns:\n            raise RuntimeError(\n                "Temporal inventory schema drift: "\n                f"{index_name} expected={expected_columns!r} actual={actual_columns!r}"\n            )\n''',
        '''    indexes = {\n        str(index.get("name") or ""): index\n        for index in inspector.get_indexes("inventory_events")\n    }\n    for index_name, expected_columns in _TEMPORAL_INDEX_CONTRACT.items():\n        index = indexes.get(index_name)\n        actual_columns = tuple((index or {}).get("column_names") or ())\n        actual_unique = bool((index or {}).get("unique"))\n        if not index or actual_columns != expected_columns or actual_unique:\n            raise RuntimeError(\n                "Temporal inventory schema drift: "\n                f"{index_name} expected_columns={expected_columns!r} expected_unique=False "\n                f"actual_columns={actual_columns!r} actual_unique={actual_unique}"\n            )\n''',
    )


def patch_runtime_tests() -> None:
    path = Path("backend/tests/test_locationless_inventory_identity_guard.py")
    source = path.read_text(encoding="utf-8")
    addition = '''\n\ndef test_wrong_locationless_predicate_is_rejected_even_with_matching_tokens():\n    engine = _engine()\n    with engine.begin() as conn:\n        _seed_schema(conn, with_identity_index=False)\n        conn.execute(text(f"""\n            CREATE UNIQUE INDEX {LOCATIONLESS_ACTIVE_IDENTITY_INDEX}\n            ON inventory (household_id, household_article_id)\n            WHERE COALESCE(status, 'active') <> 'active'\n              AND household_article_id IS NOT NULL\n              AND space_id IS NULL\n              AND sublocation_id IS NULL\n        """))\n\n        with pytest.raises(RuntimeError, match="predicate wijkt af"):\n            ensure_locationless_inventory_identity_guard(conn)\n'''
    if "test_wrong_locationless_predicate_is_rejected_even_with_matching_tokens" not in source:
        path.write_text(source.rstrip() + addition + "\n", encoding="utf-8")

    temporal_path = Path("backend/tests/test_temporal_inventory_service.py")
    temporal = temporal_path.read_text(encoding="utf-8")
    temporal_addition = '''\n\ndef test_runtime_guard_rejects_unique_temporal_index_lookalike():\n    conn = _connection()\n    conn.execute(text("DROP INDEX idx_inventory_events_temporal_order"))\n    conn.execute(text(\n        "CREATE UNIQUE INDEX idx_inventory_events_temporal_order "\n        "ON inventory_events (household_id, household_article_id, effective_at, event_priority, id)"\n    ))\n    with pytest.raises(RuntimeError, match="expected_unique=False"):\n        ensure_temporal_inventory_schema(conn)\n\n\ndef test_migration_rejects_existing_unique_temporal_index_lookalike():\n    conn = _connection(migrate=False)\n    for ddl in (\n        "ALTER TABLE inventory_events ADD COLUMN effective_at TEXT",\n        "ALTER TABLE inventory_events ADD COLUMN recorded_at TEXT",\n        "ALTER TABLE inventory_events ADD COLUMN effective_at_precision TEXT NOT NULL DEFAULT 'datetime'",\n        "ALTER TABLE inventory_events ADD COLUMN event_priority INTEGER NOT NULL DEFAULT 100",\n        "ALTER TABLE inventory_events ADD COLUMN source_reference TEXT",\n        "ALTER TABLE inventory_events ADD COLUMN source_line_id TEXT",\n        "ALTER TABLE inventory_events ADD COLUMN replayed_at TEXT",\n    ):\n        conn.execute(text(ddl))\n    conn.execute(text(\n        "CREATE UNIQUE INDEX idx_inventory_events_temporal_order "\n        "ON inventory_events (household_id, household_article_id, effective_at, event_priority, id)"\n    ))\n    with pytest.raises(RuntimeError, match="expected_unique=False"):\n        _upgrade_temporal_schema(conn)\n\n\ndef test_migration_rejects_wrong_locationless_predicate():\n    conn = _connection(migrate=False)\n    conn.execute(text("DROP INDEX uq_inventory_active_locationless_household_article"))\n    conn.execute(text(\n        "CREATE UNIQUE INDEX uq_inventory_active_locationless_household_article "\n        "ON inventory (household_id, household_article_id) "\n        "WHERE COALESCE(status, 'active') <> 'active' "\n        "AND household_article_id IS NOT NULL "\n        "AND space_id IS NULL AND sublocation_id IS NULL"\n    ))\n    with pytest.raises(RuntimeError, match="predicate wijkt af"):\n        _upgrade_temporal_schema(conn)\n'''
    if "test_runtime_guard_rejects_unique_temporal_index_lookalike" not in temporal:
        temporal_path.write_text(temporal.rstrip() + temporal_addition + "\n", encoding="utf-8")


def patch_migration_selftest() -> None:
    path = "backend/tests/migration_foundation_selftest.py"
    replace_once(
        path,
        '''    indexes = {\n        str(index.get("name") or ""): tuple(index.get("column_names") or ())\n        for index in inspector.get_indexes("inventory_events")\n    }\n    for index_name, expected_columns in EXPECTED_TEMPORAL_INDEXES.items():\n        if indexes.get(index_name) != expected_columns:\n            raise AssertionError(\n                f"Invalid {index_name}: expected={expected_columns!r} "\n                f"actual={indexes.get(index_name)!r}"\n            )\n''',
        '''    indexes = {\n        str(index.get("name") or ""): index\n        for index in inspector.get_indexes("inventory_events")\n    }\n    for index_name, expected_columns in EXPECTED_TEMPORAL_INDEXES.items():\n        index = indexes.get(index_name)\n        actual_columns = tuple((index or {}).get("column_names") or ())\n        actual_unique = bool((index or {}).get("unique"))\n        if not index or actual_columns != expected_columns or actual_unique:\n            raise AssertionError(\n                f"Invalid {index_name}: expected_columns={expected_columns!r} "\n                f"expected_unique=False actual_columns={actual_columns!r} "\n                f"actual_unique={actual_unique}"\n            )\n''',
    )


def create_postgresql_writer_selftest() -> None:
    path = Path("backend/tests/postgresql_inventory_writer_selftest.py")
    content = '''from __future__ import annotations\n\nimport ast\nimport importlib.util\nimport os\nfrom pathlib import Path\nimport uuid\n\nfrom sqlalchemy import create_engine, text\n\n\nROOT = Path(__file__).resolve().parents[1]\nMAIN_PATH = ROOT / "app" / "main.py"\nMIGRATION_PATH = ROOT / "alembic" / "versions" / "20260828_03_inventory_temporal_schema_authority.py"\n\n\nclass _HTTPException(Exception):\n    def __init__(self, status_code: int, detail: str):\n        super().__init__(detail)\n        self.status_code = status_code\n        self.detail = detail\n\n\ndef _load_resolver():\n    module = ast.parse(MAIN_PATH.read_text(encoding="utf-8"), filename=str(MAIN_PATH))\n    node = next(\n        item for item in module.body\n        if isinstance(item, ast.FunctionDef)\n        and item.name == "resolve_or_create_inventory_household_article"\n    )\n    isolated = ast.Module(body=[node], type_ignores=[])\n    ast.fix_missing_locations(isolated)\n    namespace = {\n        "HTTPException": _HTTPException,\n        "normalize_household_article_name": lambda value: " ".join(str(value or "").strip().split()),\n        "text": text,\n        "uuid": uuid,\n    }\n    exec(compile(isolated, str(MAIN_PATH), "exec"), namespace)\n    return namespace["resolve_or_create_inventory_household_article"]\n\n\ndef _load_migration():\n    spec = importlib.util.spec_from_file_location("inventory_temporal_authority_review", MIGRATION_PATH)\n    assert spec and spec.loader\n    module = importlib.util.module_from_spec(spec)\n    spec.loader.exec_module(module)\n    return module\n\n\ndef main() -> None:\n    database_url = os.environ["DATABASE_URL"]\n    engine = create_engine(database_url, future=True)\n    resolver = _load_resolver()\n    migration = _load_migration()\n\n    with engine.begin() as connection:\n        connection.execute(text("""\n            CREATE TEMP TABLE household_articles (\n                id TEXT PRIMARY KEY,\n                household_id TEXT NOT NULL,\n                naam TEXT,\n                custom_name TEXT,\n                status TEXT,\n                created_at TIMESTAMPTZ\n            ) ON COMMIT DROP\n        """))\n        connection.execute(text("""\n            INSERT INTO household_articles (id, household_id, naam, status, created_at)\n            VALUES ('ha-review', 'house-review', 'Melk', 'active', NOW())\n        """))\n        resolved = resolver(\n            connection,\n            household_id="house-review",\n            article_name="Melk",\n            preferred_household_article_id=None,\n            source="review-selftest",\n        )\n        assert resolved == "ha-review"\n    print("POSTGRESQL_INVENTORY_WRITER_FALLBACK_GREEN")\n\n    with engine.connect() as connection:\n        transaction = connection.begin()\n        try:\n            connection.execute(text("DROP INDEX uq_inventory_active_locationless_household_article"))\n            connection.execute(text("""\n                CREATE UNIQUE INDEX uq_inventory_active_locationless_household_article\n                ON inventory (household_id, household_article_id)\n                WHERE COALESCE(status, 'active') <> 'active'\n                  AND household_article_id IS NOT NULL\n                  AND space_id IS NULL\n                  AND sublocation_id IS NULL\n            """))\n            try:\n                migration._validate_locationless_identity_index(connection)\n            except RuntimeError as exc:\n                assert "predicate wijkt af" in str(exc)\n            else:\n                raise AssertionError("Malformed PostgreSQL locationless predicate was accepted")\n        finally:\n            transaction.rollback()\n    print("POSTGRESQL_LOCATIONLESS_PREDICATE_DRIFT_REJECTED_GREEN")\n\n    with engine.connect() as connection:\n        transaction = connection.begin()\n        try:\n            connection.execute(text("DROP INDEX idx_inventory_events_temporal_order"))\n            connection.execute(text("""\n                CREATE UNIQUE INDEX idx_inventory_events_temporal_order\n                ON inventory_events (household_id, household_article_id, effective_at, event_priority, id)\n            """))\n            try:\n                migration._validate_contract(connection)\n            except RuntimeError as exc:\n                assert "expected_unique=False" in str(exc)\n            else:\n                raise AssertionError("Unique temporal index lookalike was accepted")\n        finally:\n            transaction.rollback()\n    print("POSTGRESQL_TEMPORAL_UNIQUE_DRIFT_REJECTED_GREEN")\n    print("POSTGRESQL_INVENTORY_REVIEW_SELFTEST_GREEN")\n    engine.dispose()\n\n\nif __name__ == "__main__":\n    main()\n'''
    path.write_text(content, encoding="utf-8")


def patch_postgresql_workflow() -> None:
    path = ".github/workflows/postgresql-migration-foundation-validation.yml"
    replace_once(
        path,
        "      - 'backend/tests/migration_foundation_selftest.py'\n",
        "      - 'backend/tests/migration_foundation_selftest.py'\n      - 'backend/tests/postgresql_inventory_writer_selftest.py'\n",
    )
    replace_once(
        path,
        "          grep -F 'MIGRATION_FOUNDATION_SELFTEST_GREEN' /tmp/migration-postgresql.log\n",
        "          grep -F 'MIGRATION_FOUNDATION_SELFTEST_GREEN' /tmp/migration-postgresql.log\n          python backend/tests/postgresql_inventory_writer_selftest.py | tee /tmp/postgresql-inventory-review.log\n          grep -F 'POSTGRESQL_INVENTORY_WRITER_FALLBACK_GREEN' /tmp/postgresql-inventory-review.log\n          grep -F 'POSTGRESQL_LOCATIONLESS_PREDICATE_DRIFT_REJECTED_GREEN' /tmp/postgresql-inventory-review.log\n          grep -F 'POSTGRESQL_TEMPORAL_UNIQUE_DRIFT_REJECTED_GREEN' /tmp/postgresql-inventory-review.log\n          grep -F 'POSTGRESQL_INVENTORY_REVIEW_SELFTEST_GREEN' /tmp/postgresql-inventory-review.log\n",
    )


def main() -> None:
    patch_main()
    patch_migration()
    patch_canonical_service()
    patch_temporal_service()
    patch_runtime_tests()
    patch_migration_selftest()
    create_postgresql_writer_selftest()
    patch_postgresql_workflow()


if __name__ == "__main__":
    main()

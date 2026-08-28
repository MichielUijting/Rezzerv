from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    source = file_path.read_text(encoding='utf-8')
    if source.count(old) != 1:
        raise SystemExit(f'{path}: anchor count={source.count(old)}')
    file_path.write_text(source.replace(old, new, 1), encoding='utf-8')


migration = 'backend/alembic/versions/20260828_03_inventory_temporal_schema_authority.py'
replace_once(
    migration,
    '''_LOCATIONLESS_ACTIVE_IDENTITY_PREDICATE = (\n    "COALESCE(status, 'active') = 'active' "\n    "AND household_article_id IS NOT NULL "\n    "AND space_id IS NULL "\n    "AND sublocation_id IS NULL"\n)\n''',
    '''_LOCATIONLESS_ACTIVE_IDENTITY_PREDICATE = (\n    "COALESCE(status, 'active') = 'active' "\n    "AND household_article_id IS NOT NULL "\n    "AND space_id IS NULL "\n    "AND sublocation_id IS NULL"\n)\n_LEGACY_LOCATIONLESS_ACTIVE_IDENTITY_PREDICATE = (\n    "status = 'active' "\n    "AND household_article_id IS NOT NULL "\n    "AND space_id IS NULL "\n    "AND sublocation_id IS NULL"\n)\n''',
)
replace_once(
    migration,
    '''    indexes = {\n        str(item.get("name") or ""): item\n        for item in inspector.get_indexes("inventory")\n    }\n    if _LOCATIONLESS_ACTIVE_IDENTITY_INDEX not in indexes:\n        predicate = sa.text(_LOCATIONLESS_ACTIVE_IDENTITY_PREDICATE)\n        op.create_index(\n            _LOCATIONLESS_ACTIVE_IDENTITY_INDEX,\n            "inventory",\n            list(_LOCATIONLESS_ACTIVE_IDENTITY_COLUMNS),\n            unique=True,\n            sqlite_where=predicate,\n            postgresql_where=predicate,\n        )\n    _validate_locationless_identity_index(bind)\n''',
    '''    indexes = {\n        str(item.get("name") or ""): item\n        for item in inspector.get_indexes("inventory")\n    }\n    existing = indexes.get(_LOCATIONLESS_ACTIVE_IDENTITY_INDEX)\n    if existing is not None:\n        if not bool(existing.get("unique")) or tuple(existing.get("column_names") or ()) != _LOCATIONLESS_ACTIVE_IDENTITY_COLUMNS:\n            raise RuntimeError("Canonical locationless inventory index wijkt af in uniqueness/kolommen")\n        actual_terms = _normalized_predicate_terms(_locationless_index_sql(bind))\n        canonical_terms = _normalized_predicate_terms(\n            f"CREATE INDEX canonical ON inventory (household_id, household_article_id) "\n            f"WHERE {_LOCATIONLESS_ACTIVE_IDENTITY_PREDICATE}"\n        )\n        legacy_terms = _normalized_predicate_terms(\n            f"CREATE INDEX legacy ON inventory (household_id, household_article_id) "\n            f"WHERE {_LEGACY_LOCATIONLESS_ACTIVE_IDENTITY_PREDICATE}"\n        )\n        if actual_terms == legacy_terms:\n            op.drop_index(_LOCATIONLESS_ACTIVE_IDENTITY_INDEX, table_name="inventory")\n            existing = None\n        elif actual_terms != canonical_terms:\n            _validate_locationless_identity_index(bind)\n\n    if existing is None:\n        predicate = sa.text(_LOCATIONLESS_ACTIVE_IDENTITY_PREDICATE)\n        op.create_index(\n            _LOCATIONLESS_ACTIVE_IDENTITY_INDEX,\n            "inventory",\n            list(_LOCATIONLESS_ACTIVE_IDENTITY_COLUMNS),\n            unique=True,\n            sqlite_where=predicate,\n            postgresql_where=predicate,\n        )\n    _validate_locationless_identity_index(bind)\n''',
)

test_path = Path('backend/tests/test_temporal_inventory_service.py')
test_source = test_path.read_text(encoding='utf-8')
addition = '''\n\ndef test_migration_normalizes_known_legacy_locationless_predicate():\n    conn = _connection(migrate=False)\n    conn.execute(text("DROP INDEX uq_inventory_active_locationless_household_article"))\n    conn.execute(text(\n        "CREATE UNIQUE INDEX uq_inventory_active_locationless_household_article "\n        "ON inventory (household_id, household_article_id) "\n        "WHERE status = 'active' "\n        "AND household_article_id IS NOT NULL "\n        "AND space_id IS NULL AND sublocation_id IS NULL"\n    ))\n\n    _upgrade_temporal_schema(conn)\n\n    index_sql = conn.execute(text(\n        "SELECT sql FROM sqlite_master "\n        "WHERE type='index' AND name='uq_inventory_active_locationless_household_article'"\n    )).scalar_one()\n    normalized = "".join(str(index_sql).lower().split())\n    assert "coalesce(status,'active')='active'" in normalized\n    ensure_locationless_inventory_identity_guard(conn)\n'''
if 'test_migration_normalizes_known_legacy_locationless_predicate' not in test_source:
    test_path.write_text(test_source.rstrip() + addition + '\n', encoding='utf-8')

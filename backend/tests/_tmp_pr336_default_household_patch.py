from pathlib import Path

path = Path('backend/app/main.py')
source = path.read_text(encoding='utf-8')
needle = """def bootstrap_auth_registry():\n    with engine.begin() as conn:\n        default_household_id = '1'\n        default_household_name = DEFAULT_AUTH_USERS['admin@rezzerv.local'].get('household_name') or 'Mijn huishouden'\n        conn.execute(\n            text(\n                '''\n                INSERT INTO household_registry (id, naam, created_at)\n"""
replacement = """def bootstrap_auth_registry():\n    with engine.begin() as conn:\n        default_household_id = '1'\n        default_household_name = DEFAULT_AUTH_USERS['admin@rezzerv.local'].get('household_name') or 'Mijn huishouden'\n        conn.execute(\n            text(\n                '''\n                INSERT INTO households (id, naam, created_at)\n                VALUES (:id, :naam, CURRENT_TIMESTAMP)\n                ON CONFLICT(id) DO NOTHING\n                '''\n            ),\n            {'id': default_household_id, 'naam': default_household_name},\n        )\n        conn.execute(\n            text(\n                '''\n                INSERT INTO household_registry (id, naam, created_at)\n"""
if source.count(needle) != 1:
    raise SystemExit(f'expected one bootstrap_auth_registry insertion point, found {source.count(needle)}')
source = source.replace(needle, replacement, 1)
path.write_text(source, encoding='utf-8')
print('PR336_DEFAULT_HOUSEHOLD_DML_PATCH_APPLIED')

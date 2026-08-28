from pathlib import Path

path = Path('backend/app/services/receipt_service.py')
source = path.read_text(encoding='utf-8')
old_import = 'from sqlalchemy import bindparam, text\n'
new_import = 'from sqlalchemy import bindparam, inspect, text\n'
old_helper = """def _column_exists(conn, table_name: str, column_name: str) -> bool:\n    rows = conn.execute(text(f'PRAGMA table_info({table_name})')).mappings().all()\n    return any(str(row.get('name') or '').lower() == column_name.lower() for row in rows)\n"""
new_helper = """def _column_exists(conn, table_name: str, column_name: str) -> bool:\n    columns = inspect(conn).get_columns(table_name)\n    return any(str(column.get('name') or '').lower() == column_name.lower() for column in columns)\n"""
if source.count(old_import) != 1:
    raise SystemExit(f'expected one SQLAlchemy import, found {source.count(old_import)}')
if source.count(old_helper) != 1:
    raise SystemExit(f'expected one SQLite-only column helper, found {source.count(old_helper)}')
source = source.replace(old_import, new_import, 1).replace(old_helper, new_helper, 1)
path.write_text(source, encoding='utf-8')
print('PR336_RECEIPT_COLUMN_INSPECTION_PATCH_APPLIED')

from pathlib import Path

path = Path("backend/app/services/receipt_service.py")
source = path.read_text(encoding="utf-8")

old_update = """                conn.execute(\n                    text(\n                        'UPDATE receipt_sources SET label = :label, source_path = :source_path, is_active = 1, updated_at = CURRENT_TIMESTAMP WHERE id = :id'\n                    ),\n                    definition,\n                )\n"""
new_update = """                conn.execute(\n                    text(\n                        'UPDATE receipt_sources SET label = :label, source_path = :source_path, is_active = :is_active, updated_at = CURRENT_TIMESTAMP WHERE id = :id'\n                    ),\n                    {**definition, 'is_active': True},\n                )\n"""
old_insert = """                conn.execute(\n                    text(\n                        '''\n                        INSERT INTO receipt_sources (id, household_id, type, label, source_path, is_active)\n                        VALUES (:id, :household_id, :type, :label, :source_path, 1)\n                        '''\n                    ),\n                    {**definition, 'household_id': household_id},\n                )\n"""
new_insert = """                conn.execute(\n                    text(\n                        '''\n                        INSERT INTO receipt_sources (id, household_id, type, label, source_path, is_active)\n                        VALUES (:id, :household_id, :type, :label, :source_path, :is_active)\n                        '''\n                    ),\n                    {**definition, 'household_id': household_id, 'is_active': True},\n                )\n"""

if source.count(old_update) != 1:
    raise SystemExit(f"expected exactly one receipt_sources UPDATE snippet, found {source.count(old_update)}")
if source.count(old_insert) != 1:
    raise SystemExit(f"expected exactly one receipt_sources INSERT snippet, found {source.count(old_insert)}")

source = source.replace(old_update, new_update, 1).replace(old_insert, new_insert, 1)
path.write_text(source, encoding="utf-8")
print("PR336_RECEIPT_SOURCE_BOOLEAN_PATCH_APPLIED")

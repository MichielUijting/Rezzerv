from pathlib import Path
import re

path = Path('backend/app/main.py')
source = path.read_text(encoding='utf-8')

source, release_1221_count = re.subn(
    r'(?m)^ensure_release_1221_schema\(\)\s*\n',
    '',
    source,
)
if release_1221_count != 1:
    raise SystemExit(f'Expected exactly one top-level ensure_release_1221_schema call, found {release_1221_count}')

startup_block = '''Base.metadata.create_all(bind=engine)
ensure_household_settings_schema()
ensure_user_settings_schema()
ensure_household_permission_policies_schema()
ensure_household_role_change_audit_schema()
ensure_household_articles_schema()
ensure_article_group_schema()
ensure_product_enrichment_schema()
ensure_global_product_catalog_schema()
ensure_external_product_candidates_schema()
ensure_release_b_household_article_global_product_integrity()
ensure_release_c_product_enrichment_centralization()
ensure_release_2_schema()
ensure_release_3_schema()
ensure_release_4_schema()
ensure_release_803_schema()
ensure_release_813_schema()
ensure_release_814_schema()
ensure_release_902_schema()
ensure_release_932_schema()
ensure_release_933_schema()
ensure_release_935_schema()
ensure_release_940_schema()
ensure_release_941_receipt_edit_schema()
ensure_release_963_schema()
ensure_release_965_schema()
ensure_release_1031_schema()
ensure_release_1041_schema()
ensure_release_1046_schema()
ensure_release_1113_schema()
'''
replacement = '''# Production schema authority is Alembic-only. Runtime startup must not create,
# alter, index, or repair schema objects; app.runtime_preflight migrates before
# Uvicorn imports this module.
'''
if source.count(startup_block) != 1:
    raise SystemExit(f'Expected exactly one legacy startup schema block, found {source.count(startup_block)}')
source = source.replace(startup_block, replacement, 1)

source, import_count = re.subn(
    r'(?m)^from app\.db import engine, Base\s*$',
    'from app.db import engine',
    source,
)
if import_count != 1:
    raise SystemExit(f'Expected one legacy engine/Base import, found {import_count}')

path.write_text(source, encoding='utf-8')
print('MAIN_STARTUP_SCHEMA_MUTATORS_REMOVED')

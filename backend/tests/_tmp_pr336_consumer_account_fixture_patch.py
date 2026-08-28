from pathlib import Path

path = Path('backend/tests/consumer_account_registration_selftest.py')
source = path.read_text(encoding='utf-8')
old_import = 'from app.services.authorization_foundation_service import ensure_authorization_foundation\n'
new_import = old_import + 'from app.testing.authorization_schema_fixture import install_authorization_schema\n'
old_setup = '        ensure_roles_v2_account_and_household_foundation(conn)\n        ensure_authorization_foundation(conn)\n'
new_setup = '        ensure_roles_v2_account_and_household_foundation(conn)\n        install_authorization_schema(conn)\n        ensure_authorization_foundation(conn)\n'
if source.count(old_import) != 1:
    raise SystemExit(f'expected one authorization foundation import, found {source.count(old_import)}')
if 'from app.testing.authorization_schema_fixture import install_authorization_schema\n' in source:
    raise SystemExit('authorization schema fixture import already present')
if source.count(old_setup) != 1:
    raise SystemExit(f'expected one consumer fixture setup block, found {source.count(old_setup)}')
source = source.replace(old_import, new_import, 1).replace(old_setup, new_setup, 1)
path.write_text(source, encoding='utf-8')
print('PR336_CONSUMER_ACCOUNT_FIXTURE_PATCH_APPLIED')

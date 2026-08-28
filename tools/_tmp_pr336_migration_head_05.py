from pathlib import Path

path = Path('backend/tests/migration_foundation_selftest.py')
text = path.read_text(encoding='utf-8')

old_head = 'HEAD_REVISION = "20260828_04"'
new_head = 'HEAD_REVISION = "20260828_05"'
if text.count(old_head) != 1:
    raise SystemExit(f'Expected exactly one {old_head!r}')
text = text.replace(old_head, new_head, 1)

anchor = '        "-- table: frontteam_personal_households (table=frontteam_personal_households)",\n'
addition = (
    anchor
    + '        "-- table: actor_object_attributions (table=actor_object_attributions)",\n'
    + '        "-- index: idx_actor_object_attributions_household_actor (table=actor_object_attributions)",\n'
)
if text.count(anchor) != 1:
    raise SystemExit('Expected one migration-extension anchor')
text = text.replace(anchor, addition, 1)

path.write_text(text, encoding='utf-8')
print('PR336_MIGRATION_HEAD_05_PATCH_GREEN')

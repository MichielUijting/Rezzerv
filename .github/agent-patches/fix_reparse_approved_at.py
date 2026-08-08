from pathlib import Path

MAIN = Path('backend/app/main.py')
TEST = Path('backend/tests/test_receipt_inventory_lifecycle_route_wiring.py')

text = MAIN.read_text(encoding='utf-8')
old = "SELECT id AS receipt_table_id, household_id, store_name, store_branch, purchase_at, created_at, currency"
new = "SELECT id AS receipt_table_id, household_id, store_name, store_branch, purchase_at, created_at, approved_at, currency"
if old not in text and new not in text:
    raise SystemExit('reparse receipt header select anchor not found')
if old in text:
    text = text.replace(old, new, 1)
MAIN.write_text(text, encoding='utf-8')

test = TEST.read_text(encoding='utf-8')
needle = "    assert \"ensure_unpack_batch_for_receipt(\" in route\n"
addition = needle + "    assert \"approved_at, currency\" in route\n"
if "approved_at, currency" not in test:
    if needle not in test:
        raise SystemExit('route test anchor not found')
    test = test.replace(needle, addition, 1)
TEST.write_text(test, encoding='utf-8')

print('approved_at preserved for reparse unpack rebuild')

"""Statisch contract voor Stap 6: Kassa leest productkoppelingen centraal."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MAIN = ROOT / "backend/app/main.py"


def block(source: str, start: str, end: str) -> str:
    start_index = source.index(start)
    end_index = source.index(end, start_index)
    return source[start_index:end_index]


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


source = MAIN.read_text(encoding="utf-8")

sync_block = block(
    source,
    "def sync_receipt_table_line_product_links(",
    "\ndef sync_purchase_import_line_product_links(",
)
create_block = block(
    source,
    '@app.post("/api/receipts/{receipt_table_id}/lines")',
    '\n@app.post("/api/receipts/{receipt_table_id}/approve")',
)

assert_true(
    "get_confirmed_external_article_product_link(" in sync_block,
    "Kassa-synchronisatie leest niet uit de centrale koppeldienst",
)
assert_true(
    "resolve_receipt_line_product_links(" not in sync_block,
    "Kassa-synchronisatie bevat nog een parallelle productresolver",
)
assert_true(
    "find_global_product_match_for_receipt_line(" not in create_block,
    "Nieuwe Kassa-regels gebruiken nog de oude productzoeker",
)
assert_true(
    "matched_global_product_id = None" in create_block,
    "Nieuwe Kassa-regels starten niet expliciet zonder productmatch",
)
assert_true(
    create_block.count("sync_receipt_table_line_product_links(") == 1,
    "Nieuwe Kassa-regels worden niet exact één keer centraal gesynchroniseerd",
)
assert_true(
    "create_global_product=False" in create_block,
    "Kassa mag bij synchronisatie geen universeel product creëren",
)
assert_true(
    "create_household_article=False" in create_block,
    "Kassa mag bij synchronisatie geen huishoudartikel creëren",
)

print("PASS: Kassa-synchronisatie leest de centrale koppeling")
print("PASS: Kassa-synchronisatie bevat geen parallelle resolver")
print("PASS: nieuwe Kassa-regels starten zonder lokale productmatch")
print("PASS: nieuwe Kassa-regels worden exact één keer centraal gesynchroniseerd")
print("PASS: Kassa creëert geen universeel of huishoudartikel tijdens synchronisatie")

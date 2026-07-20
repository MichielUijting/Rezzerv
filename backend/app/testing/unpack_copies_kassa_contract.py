"""Statisch contract voor Stap 7: Uitpakken bewaart het Kassa-product."""
from pathlib import Path

CANDIDATES = (
    Path("/app/app/main.py"),
    Path(__file__).resolve().parents[1] / "main.py",
    Path(__file__).resolve().parents[3] / "backend/app/main.py",
)
MAIN = next((path for path in CANDIDATES if path.exists()), None)
if MAIN is None:
    raise FileNotFoundError("main.py niet gevonden")
source = MAIN.read_text(encoding="utf-8")


def block(start: str, end: str) -> str:
    start_index = source.index(start)
    end_index = source.index(end, start_index)
    return source[start_index:end_index]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


sync_block = block(
    "def sync_unpack_batch_lines_for_receipt(",
    "\ndef ensure_receipt_ready_for_unpack(",
)
map_block = block(
    '@app.post("/api/purchase-import-lines/{line_id}/map")',
    '\n@app.post("/api/purchase-import-lines/{line_id}/create-article")',
)
create_block = block(
    '@app.post("/api/purchase-import-lines/{line_id}/create-article")',
    '\n@app.post("/api/purchase-import-lines/{line_id}/target-location")',
)
process_block = block(
    '            lines = conn.execute(',
    '                resolved_location = resolve_store_storage_target_location',
)

require(
    "matched_global_product_id = (" in sync_block
    and "str(line.get('matched_global_product_id') or '').strip()" in sync_block,
    "Uitpakken kopieert matched_global_product_id niet letterlijk uit Kassa",
)
require(
    "get_confirmed_external_article_product_link(" not in sync_block
    and "resolve_receipt_line_product_links(" not in sync_block,
    "Uitpakken voert tijdens kopiëren nog een eigen productzoeker uit",
)
for label, current in (("map", map_block), ("create", create_block), ("process", process_block)):
    require(
        'startswith("receipt-line:")' in current,
        f"{label}-route herkent Kassa-regels niet expliciet",
    )
require(
    map_block.count("sync_purchase_import_line_product_links(") == 1,
    "Map-route bevat een onverwacht aantal synchronisatieaanroepen",
)
require(
    create_block.count("sync_purchase_import_line_product_links(") == 1,
    "Create-route bevat een onverwacht aantal synchronisatieaanroepen",
)
require(
    process_block.count("sync_purchase_import_line_product_links(") == 1,
    "Process-route bevat een onverwacht aantal synchronisatieaanroepen",
)

print(f"PASS: main.py gevonden op {MAIN}")
print("PASS: Uitpakken kopieert matched_global_product_id letterlijk uit Kassa")
print("PASS: kopiëren bevat geen centrale of kandidaatgebaseerde herzoeking")
print("PASS: Mijn-artikelkeuze wijzigt het Kassa-product niet")
print("PASS: verwerken naar Voorraad wijzigt het Kassa-product niet")
print("PASS: niet-Kassa-importbronnen behouden hun bestaande synchronisatie")

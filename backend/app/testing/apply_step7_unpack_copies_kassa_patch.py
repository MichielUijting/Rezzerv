"""Pas Stap 7 gecontroleerd toe: Uitpakken bewaart het Kassa-product letterlijk."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MAIN = ROOT / "backend/app/main.py"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: verwacht exact 1 match, gevonden {count}")
    return source.replace(old, new, 1)


source = MAIN.read_text(encoding="utf-8")

source = replace_once(
    source,
    'text("SELECT id, batch_id, target_location_id, location_override_mode FROM purchase_import_lines WHERE id = :id"),',
    'text("SELECT id, batch_id, external_line_ref, target_location_id, location_override_mode FROM purchase_import_lines WHERE id = :id"),',
    "map-route bronveld",
)
source = replace_once(
    source,
    '''        sync_purchase_import_line_product_links(conn, line_id, household_id)
        status = update_batch_status(conn, line["batch_id"])
''',
    '''        if not str(line.get("external_line_ref") or "").strip().startswith("receipt-line:"):
            sync_purchase_import_line_product_links(conn, line_id, household_id)
        status = update_batch_status(conn, line["batch_id"])
''',
    "map-route behoud Kassa-product",
)

source = replace_once(
    source,
    '''                SELECT pil.id, pil.batch_id, pib.household_id
                FROM purchase_import_lines pil
''',
    '''                SELECT pil.id, pil.batch_id, pil.external_line_ref, pib.household_id
                FROM purchase_import_lines pil
''',
    "create-article bronveld",
)
source = replace_once(
    source,
    '''        sync_purchase_import_line_product_links(conn, line_id, str(line["household_id"]))
        status = update_batch_status(conn, line["batch_id"])
''',
    '''        if not str(line.get("external_line_ref") or "").strip().startswith("receipt-line:"):
            sync_purchase_import_line_product_links(conn, line_id, str(line["household_id"]))
        status = update_batch_status(conn, line["batch_id"])
''',
    "create-article behoud Kassa-product",
)

source = replace_once(
    source,
    '''                    SELECT id, article_name_raw, brand_raw, external_article_code, quantity_raw, unit_raw, review_decision, matched_household_article_id,
                           matched_global_product_id, target_location_id, processing_status, processed_event_id
''',
    '''                    SELECT id, external_line_ref, article_name_raw, brand_raw, external_article_code, quantity_raw, unit_raw, review_decision, matched_household_article_id,
                           matched_global_product_id, target_location_id, processing_status, processed_event_id
''',
    "process-route bronveld",
)
source = replace_once(
    source,
    '''                synced_links = sync_purchase_import_line_product_links(conn, line_id, str(batch["household_id"]))
                if synced_links:
                    article_id = synced_links.get('matched_household_article_id') or article_id
                    matched_global_product_id = synced_links.get('matched_global_product_id') or matched_global_product_id
''',
    '''                if not str(line.get("external_line_ref") or "").strip().startswith("receipt-line:"):
                    synced_links = sync_purchase_import_line_product_links(conn, line_id, str(batch["household_id"]))
                    if synced_links:
                        article_id = synced_links.get('matched_household_article_id') or article_id
                        matched_global_product_id = synced_links.get('matched_global_product_id') or matched_global_product_id
''',
    "process-route behoud Kassa-product",
)

MAIN.write_text(source, encoding="utf-8", newline="\n")
print("PATCH_TOEGEPAST=JA")
print("BESTAND=backend\\app\\main.py")

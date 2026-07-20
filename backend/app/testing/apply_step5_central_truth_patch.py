"""Pas Stap 5 gecontroleerd toe op backendprojectie en frontendstatus."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend/app/services/external_product_candidate_store.py"
FRONTEND = ROOT / "frontend/src/features/externalDatabases/ReceiptItemsOverview.jsx"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: verwacht exact 1 match, gevonden {count}")
    return text.replace(old, new, 1)


def patch_backend() -> None:
    text = BACKEND.read_text(encoding="utf-8")
    import_anchor = "from sqlalchemy import text\n"
    import_block = (
        "from sqlalchemy import text\n"
        "from app.services.external_article_ui_projection import (\n"
        "    project_central_link_truth_rows,\n"
        ")\n"
    )
    if "project_central_link_truth_rows" not in text:
        text = replace_once(text, import_anchor, import_block, "backend import")

    old_dict = '''        next_payload["items"] = _m2c2i_fix7b_dedupe_top_receipt_items(enriched_rows)
        next_payload["total"] = len(next_payload["items"])
        return next_payload
'''
    new_dict = '''        with engine.connect() as conn:
            centrally_projected_rows = project_central_link_truth_rows(conn, enriched_rows)
        next_payload["items"] = _m2c2i_fix7b_dedupe_top_receipt_items(centrally_projected_rows)
        next_payload["total"] = len(next_payload["items"])
        return next_payload
'''
    if "centrally_projected_rows" not in text:
        text = replace_once(text, old_dict, new_dict, "backend dict-projectie")

    old_list = '''    rows = payload or []
    return _m2c2i_fix2_apply_status_fields([
        dict(row) if hasattr(row, "items") else row
        for row in rows
    ])
'''
    new_list = '''    rows = payload or []
    enriched_rows = _m2c2i_fix2_apply_status_fields([
        dict(row) if hasattr(row, "items") else row
        for row in rows
    ])
    with engine.connect() as conn:
        return project_central_link_truth_rows(conn, enriched_rows)
'''
    if "return project_central_link_truth_rows(conn, enriched_rows)" not in text:
        text = replace_once(text, old_list, new_list, "backend lijstprojectie")

    BACKEND.write_text(text, encoding="utf-8", newline="\n")


def patch_frontend() -> None:
    text = FRONTEND.read_text(encoding="utf-8")
    old_candidate = "function hasCatalogLink(candidate) { return Boolean(candidate?.is_linked_to_catalog === true || text(candidate?.global_product_id, '') || text(candidate?.product_identity_id, '') || text(candidate?.matched_global_product_id, '') || text(candidate?.matched_global_article_id, '')) }"
    new_candidate = "function hasCatalogLink(candidate) { return candidate?.central_link_active === true }"
    if new_candidate not in text:
        text = replace_once(text, old_candidate, new_candidate, "frontend kandidaatstatus")

    old_item = '''function receiptItemHasCatalogLink(rawItem) {
  const status = text(rawItem?.candidate_status || rawItem?.status || rawItem?.match_status, '').toLowerCase()
  return Boolean(
    rawItem?.is_linked_to_catalog === true
    || rawItem?.is_existing_link_for_receipt_item === true
    || text(rawItem?.global_product_id, '')
    || text(rawItem?.canonical_catalog_product_id, '')
    || text(rawItem?.matched_global_product_id, '')
    || status === 'linked_to_catalog'
    || status === 'matched'
  )
}
'''
    new_item = '''function receiptItemHasCatalogLink(rawItem) {
  // Alleen een actieve centrale koppeling betekent Gekoppeld.
  return rawItem?.central_link_active === true
}
'''
    if new_item not in text:
        text = replace_once(text, old_item, new_item, "frontend itemstatus")

    FRONTEND.write_text(text, encoding="utf-8", newline="\n")


patch_backend()
patch_frontend()
print("PATCH_TOEGEPAST=JA")
print(f"BACKEND={BACKEND.relative_to(ROOT)}")
print(f"FRONTEND={FRONTEND.relative_to(ROOT)}")

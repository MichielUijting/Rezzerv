from pathlib import Path

MAIN = Path('backend/app/main.py')
TEST = Path('backend/tests/test_receipt_inventory_lifecycle_route_wiring.py')

text = MAIN.read_text(encoding='utf-8')

import_anchor = "from app.services.receipt_service import dedupe_receipts_for_household, ensure_default_receipt_sources, ensure_share_receipt_source, ingest_receipt, parse_receipt_content, repair_receipts_for_household, reparse_receipt, scan_receipt_source, serialize_receipt_row\n"
import_block = import_anchor + "from app.services.receipt_inventory_lifecycle_service import (\n    remove_receipt_inventory_events,\n    retime_receipt_inventory_events,\n)\n"
if 'from app.services.receipt_inventory_lifecycle_service import (' not in text:
    if import_anchor not in text:
        raise SystemExit('receipt_service import anchor not found')
    text = text.replace(import_anchor, import_block, 1)

header_anchor = """        conn.execute(\n            text(\"\"\"\n            UPDATE receipt_tables\n            SET store_name = :store_name,\n                purchase_at = :purchase_at,\n                store_name_source = :store_name_source,\n                purchase_at_source = :purchase_at_source,\n                total_amount = :total_amount,\n                reference = :reference,\n                notes = :notes,\n                corrected_by_user_email = :user_email,\n                reviewed_at = CURRENT_TIMESTAMP,\n                updated_at = CURRENT_TIMESTAMP\n            WHERE id = :id\n            \"\"\"),\n            {**values, 'id': receipt_table_id, 'user_email': str(context.get('email') or '').strip().lower()},\n        )\n        recompute_receipt_review_state(conn, receipt_table_id)\n"""
header_replacement = """        conn.execute(\n            text(\"\"\"\n            UPDATE receipt_tables\n            SET store_name = :store_name,\n                purchase_at = :purchase_at,\n                store_name_source = :store_name_source,\n                purchase_at_source = :purchase_at_source,\n                total_amount = :total_amount,\n                reference = :reference,\n                notes = :notes,\n                corrected_by_user_email = :user_email,\n                reviewed_at = CURRENT_TIMESTAMP,\n                updated_at = CURRENT_TIMESTAMP\n            WHERE id = :id\n            \"\"\"),\n            {**values, 'id': receipt_table_id, 'user_email': str(context.get('email') or '').strip().lower()},\n        )\n        if payload.purchase_at is not None and str(values.get('purchase_at') or '') != str(current.get('purchase_at') or ''):\n            retime_receipt_inventory_events(\n                conn,\n                receipt_table_id=receipt_table_id,\n                purchase_at=values.get('purchase_at'),\n                household_id=str(context.get('active_household_id') or ''),\n            )\n        recompute_receipt_review_state(conn, receipt_table_id)\n"""
if 'retime_receipt_inventory_events(\n                conn,\n                receipt_table_id=receipt_table_id' not in text:
    if header_anchor not in text:
        raise SystemExit('receipt header mutation anchor not found')
    text = text.replace(header_anchor, header_replacement, 1)

delete_anchor = """        receipt_params = {f\"rid_{idx}\": value for idx, value in enumerate(deleted_receipt_ids)}\n        receipt_placeholders = \", \".join([f\":rid_{idx}\" for idx, _ in enumerate(deleted_receipt_ids)])\n        conn.execute(text(f\"UPDATE receipt_tables SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id IN ({receipt_placeholders})\"), receipt_params)\n"""
delete_replacement = """        receipt_params = {f\"rid_{idx}\": value for idx, value in enumerate(deleted_receipt_ids)}\n        receipt_placeholders = \", \".join([f\":rid_{idx}\" for idx, _ in enumerate(deleted_receipt_ids)])\n        for row in rows:\n            remove_receipt_inventory_events(\n                conn,\n                receipt_table_id=str(row['receipt_table_id']),\n                household_id=str(row.get('household_id') or ''),\n            )\n        conn.execute(text(f\"UPDATE receipt_tables SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id IN ({receipt_placeholders})\"), receipt_params)\n"""
if "for row in rows:\n            remove_receipt_inventory_events(" not in text:
    if delete_anchor not in text:
        raise SystemExit('receipt delete mutation anchor not found')
    text = text.replace(delete_anchor, delete_replacement, 1)

reparse_anchor = """@app.post(\"/api/receipts/{receipt_table_id}/reparse\")\ndef reparse_receipt_table(receipt_table_id: str, authorization: Optional[str] = Header(None)):\n    with engine.begin() as conn:\n        require_entity_household_access(conn, \"receipt_tables\", receipt_table_id, authorization, admin_only=True)\n    result = reparse_receipt(engine, RECEIPT_STORAGE_ROOT, receipt_table_id)\n    if result is None:\n        raise HTTPException(status_code=404, detail=\"Receipt table niet gevonden\")\n    return result\n"""
reparse_replacement = """@app.post(\"/api/receipts/{receipt_table_id}/reparse\")\ndef reparse_receipt_table(receipt_table_id: str, authorization: Optional[str] = Header(None)):\n    with engine.begin() as conn:\n        require_entity_household_access(conn, \"receipt_tables\", receipt_table_id, authorization, admin_only=True)\n        receipt_owner = conn.execute(\n            text(\"SELECT household_id FROM receipt_tables WHERE id = :id LIMIT 1\"),\n            {'id': receipt_table_id},\n        ).mappings().first()\n    result = reparse_receipt(engine, RECEIPT_STORAGE_ROOT, receipt_table_id)\n    if result is None:\n        raise HTTPException(status_code=404, detail=\"Receipt table niet gevonden\")\n    if not result.get('deleted') and str(result.get('parse_status') or '') != 'skipped_deleted_or_archived':\n        with engine.begin() as conn:\n            lifecycle_result = remove_receipt_inventory_events(\n                conn,\n                receipt_table_id=receipt_table_id,\n                household_id=str((receipt_owner or {}).get('household_id') or ''),\n            )\n            batch_rows = conn.execute(\n                text(\"SELECT id FROM purchase_import_batches WHERE source_type = 'receipt' AND source_reference = :source_reference\"),\n                {'source_reference': f'receipt:{receipt_table_id}'},\n            ).mappings().all()\n            batch_ids = [str(row['id']) for row in batch_rows if row.get('id')]\n            if batch_ids:\n                conn.execute(\n                    text(\"DELETE FROM purchase_import_lines WHERE batch_id IN :ids\").bindparams(bindparam('ids', expanding=True)),\n                    {'ids': batch_ids},\n                )\n                conn.execute(\n                    text(\"DELETE FROM purchase_import_batches WHERE id IN :ids\").bindparams(bindparam('ids', expanding=True)),\n                    {'ids': batch_ids},\n                )\n            receipt_header = conn.execute(\n                text(\"\"\"\n                SELECT id AS receipt_table_id, household_id, store_name, store_branch, purchase_at, created_at, currency\n                FROM receipt_tables\n                WHERE id = :id AND deleted_at IS NULL\n                LIMIT 1\n                \"\"\"),\n                {'id': receipt_table_id},\n            ).mappings().first()\n            if receipt_header:\n                ensure_unpack_batch_for_receipt(conn, dict(receipt_header))\n        result['inventory_lifecycle'] = {\n            **lifecycle_result,\n            'recreated_unpack_batch': bool(receipt_header),\n            'requires_reunpack': bool(lifecycle_result.get('removed_event_count')),\n        }\n    return result\n"""
if "result['inventory_lifecycle']" not in text:
    if reparse_anchor not in text:
        raise SystemExit('receipt reparse route anchor not found')
    text = text.replace(reparse_anchor, reparse_replacement, 1)

MAIN.write_text(text, encoding='utf-8')

TEST.write_text(r'''from pathlib import Path


MAIN = Path(__file__).resolve().parents[1] / "app" / "main.py"


def _main_source() -> str:
    return MAIN.read_text(encoding="utf-8")


def test_receipt_header_date_correction_retimes_inventory_events():
    source = _main_source()
    route = source.split('@app.patch("/api/receipts/{receipt_table_id}")', 1)[1].split('@app.patch("/api/receipts/{receipt_table_id}/lines/{line_id}")', 1)[0]
    assert "retime_receipt_inventory_events(" in route
    assert "payload.purchase_at is not None" in route
    assert "household_id=str(context.get('active_household_id') or '')" in route


def test_receipt_soft_delete_removes_source_inventory_events_before_archive():
    source = _main_source()
    route = source.split('@app.post("/api/receipts/delete")', 1)[1].split('@app.post("/api/admin/receipts/purge-archived")', 1)[0]
    remove_index = route.index("remove_receipt_inventory_events(")
    archive_index = route.index("UPDATE receipt_tables SET deleted_at = CURRENT_TIMESTAMP")
    assert remove_index < archive_index
    assert "household_id=str(row.get('household_id') or '')" in route


def test_receipt_reparse_clears_old_inventory_effect_and_rebuilds_unpack_batch():
    source = _main_source()
    route = source.split('@app.post("/api/receipts/{receipt_table_id}/reparse")', 1)[1].split('@app.post("/api/receipts/reparse-suspicious")', 1)[0]
    assert "result = reparse_receipt(" in route
    assert "remove_receipt_inventory_events(" in route
    assert "DELETE FROM purchase_import_lines" in route
    assert "DELETE FROM purchase_import_batches" in route
    assert "ensure_unpack_batch_for_receipt(" in route
    assert "'requires_reunpack': bool(lifecycle_result.get('removed_event_count'))" in route
''', encoding='utf-8')

print('receipt lifecycle route wiring applied')

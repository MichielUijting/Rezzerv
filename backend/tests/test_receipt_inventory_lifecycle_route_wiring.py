from pathlib import Path


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
    assert "approved_at, currency" in route
    assert "'requires_reunpack': bool(lifecycle_result.get('removed_event_count'))" in route

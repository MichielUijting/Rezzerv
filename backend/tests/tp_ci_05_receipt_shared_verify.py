#!/usr/bin/env python3
"""PostgreSQL end-state authority for TP-CI-05 shared Receipt runner.

The browser proof remains the source of runtime identities. This verifier preserves
standalone Receipt authority assertions while allowing one application build to be
reused across isolated database phases.
"""
from __future__ import annotations

import json
import os
import sys
from decimal import Decimal

from sqlalchemy import text

from app.db import engine
from app.main import build_almost_out_items, evaluate_household_article_almost_out, get_household_article_row_by_id


def proof() -> dict:
    value = os.environ.get("TP_CI_05_PROOF_JSON", "")
    assert value, "TP_CI_05_PROOF_JSON missing"
    return json.loads(value)


def dec(value) -> Decimal:
    return Decimal(str(value))


def boundary(marker: str) -> None:
    assert engine.dialect.name == "postgresql", engine.dialect.name
    with engine.begin() as conn:
        current_user = str(conn.execute(text("SELECT current_user")).scalar_one())
        runtime_create = bool(conn.execute(text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")).scalar_one())
        alembic_head = str(conn.execute(text("SELECT version_num FROM public.alembic_version")).scalar_one())
    assert current_user == "rezzerv_app", current_user
    assert runtime_create is False
    assert alembic_head
    print(f"runtime_user={current_user}")
    print(f"alembic_head={alembic_head}")
    print(marker)


def verify_l4_03() -> None:
    p = proof()
    assert p["almostOutBefore"] is False, p
    assert p["almostOutAfter"] is True, p
    household_id = str(p["householdId"])
    receipt_id = str(p["receiptId"])
    batch_id = str(p["batchId"])
    line_id = str(p["lineId"])
    location_name = str(p["locationName"])
    inventory_id = str(p["inventoryId"])
    article_id = str(p["householdArticleId"])
    initial_quantity = dec(p["initialQuantity"])
    min_stock = dec(p["minStock"])
    ideal_stock = dec(p["idealStock"])
    consume_quantity = dec(p["consumeQuantity"])
    final_quantity = dec(p["finalQuantity"])
    email = os.environ["TP_CI_05_EMAIL"].strip().lower()
    assert initial_quantity > min_stock
    assert final_quantity <= min_stock
    assert initial_quantity - consume_quantity == final_quantity
    with engine.begin() as conn:
        membership = conn.execute(text("SELECT household_id, role FROM public.household_memberships WHERE lower(trim(user_email))=:email"), {"email": email}).mappings().one()
        assert str(membership["household_id"]) == household_id
        assert str(membership["role"]) == "admin"
        cfg = conn.execute(text("SELECT inventory_tracking_level, location_tracking_level, almost_out_enabled FROM public.household_product_configuration WHERE household_id=:hid"), {"hid": household_id}).mappings().one()
        assert str(cfg["inventory_tracking_level"]) == "quantity"
        assert str(cfg["location_tracking_level"]) == "global"
        assert bool(cfg["almost_out_enabled"]) is True
        receipt = conn.execute(text("SELECT household_id, approved_at FROM public.receipt_tables WHERE id=:id"), {"id": receipt_id}).mappings().one()
        assert str(receipt["household_id"]) == household_id and receipt["approved_at"] is not None
        batch = conn.execute(text("SELECT household_id FROM public.purchase_import_batches WHERE id=:id"), {"id": batch_id}).mappings().one()
        assert str(batch["household_id"]) == household_id
        line = conn.execute(text("SELECT quantity_raw,target_location_id,processing_status,processed_event_id FROM public.purchase_import_lines WHERE id=:id"), {"id": line_id}).mappings().one()
        assert dec(line["quantity_raw"]) > 0
        assert str(line["processing_status"]) == "processed"
        assert line["processed_event_id"] is not None
        space = conn.execute(text("SELECT id,household_id,naam FROM public.spaces WHERE id=:id"), {"id": str(line["target_location_id"])}).mappings().one()
        assert str(space["household_id"]) == household_id and str(space["naam"]) == location_name
        inventory = conn.execute(text("SELECT id,aantal,household_article_id,space_id,status FROM public.inventory WHERE id=:id AND household_id=:hid"), {"id": inventory_id, "hid": household_id}).mappings().first()
        if final_quantity == 0:
            assert inventory is None, inventory
        else:
            assert inventory is not None
            assert str(inventory["household_article_id"]) == article_id
            assert str(inventory["space_id"]) == str(space["id"])
            assert dec(inventory["aantal"] or 0) == final_quantity
            assert str(inventory["status"] or "active") == "active"
        article = conn.execute(text("SELECT min_stock,ideal_stock FROM public.household_articles WHERE id=:id AND household_id=:hid"), {"id": article_id, "hid": household_id}).mappings().one()
        assert dec(article["min_stock"]) == min_stock and dec(article["ideal_stock"]) == ideal_stock
        purchase = conn.execute(text("SELECT household_id,household_article_id,location_id,event_type,quantity,source FROM public.inventory_events WHERE id=:id"), {"id": str(line["processed_event_id"])}).mappings().one()
        assert str(purchase["household_id"]) == household_id
        assert str(purchase["household_article_id"]) == article_id
        assert str(purchase["location_id"]) == str(space["id"])
        assert str(purchase["event_type"]) == "purchase" and dec(purchase["quantity"]) > 0
        assert str(purchase["source"]) == "store_import"
        consume = conn.execute(text("SELECT household_id,household_article_id,location_id,event_type,quantity,old_quantity,new_quantity,source FROM public.inventory_events WHERE household_id=:hid AND household_article_id=:aid AND event_type='consume' ORDER BY created_at DESC, id DESC LIMIT 1"), {"hid": household_id, "aid": article_id}).mappings().one()
        assert str(consume["household_id"]) == household_id and str(consume["household_article_id"]) == article_id
        assert str(consume["location_id"]) == str(space["id"])
        assert dec(consume["quantity"]) == -consume_quantity
        assert dec(consume["old_quantity"]) == initial_quantity and dec(consume["new_quantity"]) == final_quantity
        assert str(consume["source"]) == "manual_inventory_api"
        article_row = get_household_article_row_by_id(conn, household_id, article_id)
        evaluation = evaluate_household_article_almost_out(conn, household_id, article_row)
        almost_out_ids = {str(item.get("household_article_id") or "") for item in build_almost_out_items(conn, household_id)}
        assert str(evaluation.get("data_state") or "") == "ok"
        assert dec(evaluation.get("current_quantity") or 0) == final_quantity
        assert bool(evaluation.get("include_in_almost_out")) is True
        assert article_id in almost_out_ids
    print("P0_L4_03_ALMOST_OUT_TRANSITION_GREEN")
    print("P0_L4_03_POSTGRESQL_END_STATE_GREEN")


def verify_l4_04() -> None:
    p = proof()
    assert str(p["locationTrackingLevel"]) == "none"
    household_id = str(p["householdId"]); receipt_id = str(p["receiptId"]); batch_id = str(p["batchId"])
    line_id = str(p["lineId"]); inventory_id = str(p["inventoryId"]); article_id = str(p["householdArticleId"])
    email = os.environ["TP_CI_05_EMAIL"].strip().lower()
    with engine.begin() as conn:
        membership = conn.execute(text("SELECT household_id,role FROM public.household_memberships WHERE lower(trim(user_email))=:email"), {"email": email}).mappings().one()
        assert str(membership["household_id"]) == household_id and str(membership["role"]) == "admin"
        cfg = conn.execute(text("SELECT inventory_tracking_level,location_tracking_level,almost_out_enabled FROM public.household_product_configuration WHERE household_id=:hid"), {"hid": household_id}).mappings().one()
        assert str(cfg["inventory_tracking_level"]) == "quantity" and str(cfg["location_tracking_level"]) == "none" and bool(cfg["almost_out_enabled"]) is True
        receipt = conn.execute(text("SELECT household_id,approved_at FROM public.receipt_tables WHERE id=:id"), {"id": receipt_id}).mappings().one()
        assert str(receipt["household_id"]) == household_id and receipt["approved_at"] is not None
        batch = conn.execute(text("SELECT household_id FROM public.purchase_import_batches WHERE id=:id"), {"id": batch_id}).mappings().one()
        assert str(batch["household_id"]) == household_id
        line = conn.execute(text("SELECT processing_status,target_location_id,processed_event_id FROM public.purchase_import_lines WHERE id=:id"), {"id": line_id}).mappings().one()
        assert str(line["processing_status"]) == "processed" and line["target_location_id"] is None and line["processed_event_id"] is not None
        purchase = conn.execute(text("SELECT household_id,household_article_id,location_id,event_type,source FROM public.inventory_events WHERE id=:id"), {"id": str(line["processed_event_id"])}).mappings().one()
        assert str(purchase["household_id"]) == household_id and str(purchase["household_article_id"]) == article_id
        assert purchase["location_id"] is None and str(purchase["event_type"]) == "purchase" and str(purchase["source"]) == "store_import"
        consume = conn.execute(text("SELECT household_id,household_article_id,location_id,event_type FROM public.inventory_events WHERE household_id=:hid AND household_article_id=:aid AND event_type='consume' ORDER BY created_at DESC,id DESC LIMIT 1"), {"hid": household_id, "aid": article_id}).mappings().one()
        assert str(consume["household_id"]) == household_id and str(consume["household_article_id"]) == article_id
        assert consume["location_id"] is None and str(consume["event_type"]) == "consume"
        inventory = conn.execute(text("SELECT id FROM public.inventory WHERE id=:id AND household_id=:hid"), {"id": inventory_id, "hid": household_id}).mappings().first()
        assert inventory is None, inventory
    print("P0_L4_04_POSTGRESQL_END_STATE_GREEN")


def verify_l4_05() -> None:
    p = proof()
    household_id = str(p["householdId"]); receipt_id = str(p["receiptId"]); batch_id = str(p["batchId"]); line_id = str(p["lineId"])
    expected_quantity = dec(p["expectedQuantity"]); event_id = str(p["processedEventId"]); article_id = str(p["householdArticleId"]); location_id = str(p["targetLocationId"])
    assert int(p["processResponseCount"]) >= 2
    assert dec(p["browserInventoryTotal"]) == expected_quantity and expected_quantity > 0
    with engine.begin() as conn:
        receipt = conn.execute(text("SELECT household_id,approved_at FROM public.receipt_tables WHERE id=:id"), {"id": receipt_id}).mappings().one()
        assert str(receipt["household_id"]) == household_id and receipt["approved_at"] is not None
        batch = conn.execute(text("SELECT household_id,import_status FROM public.purchase_import_batches WHERE id=:id"), {"id": batch_id}).mappings().one()
        assert str(batch["household_id"]) == household_id and str(batch["import_status"]) == "processed"
        line = conn.execute(text("SELECT quantity_raw,processing_status,processed_event_id,matched_household_article_id,target_location_id,final_location_id FROM public.purchase_import_lines WHERE id=:id"), {"id": line_id}).mappings().one()
        assert str(line["processing_status"]) == "processed" and str(line["processed_event_id"]) == event_id
        assert str(line["matched_household_article_id"]) == article_id and dec(line["quantity_raw"]) == expected_quantity
        assert str(line["target_location_id"] or line["final_location_id"] or "") == location_id
        event = conn.execute(text("SELECT household_id,household_article_id,event_type,quantity,source,location_id FROM public.inventory_events WHERE id=:id"), {"id": event_id}).mappings().one()
        assert str(event["household_id"]) == household_id and str(event["household_article_id"]) == article_id
        assert str(event["event_type"]) == "purchase" and str(event["source"]) == "store_import" and dec(event["quantity"]) == expected_quantity and str(event["location_id"]) == location_id
        events = conn.execute(text("SELECT id,quantity FROM public.inventory_events WHERE household_id=:hid AND household_article_id=:aid AND event_type='purchase' AND source='store_import' ORDER BY created_at,id"), {"hid": household_id, "aid": article_id}).mappings().all()
        assert len(events) == 1 and str(events[0]["id"]) == event_id and dec(events[0]["quantity"]) == expected_quantity
        total = dec(conn.execute(text("SELECT COALESCE(SUM(aantal),0) FROM public.inventory WHERE household_id=:hid AND household_article_id=:aid AND COALESCE(status,'active')='active'"), {"hid": household_id, "aid": article_id}).scalar_one())
        assert total == expected_quantity
    print("P0_L4_05_SINGLE_PURCHASE_EVENT_GREEN")
    print("P0_L4_05_SINGLE_INVENTORY_INCREMENT_GREEN")
    print("P0_L4_05_POSTGRESQL_IDEMPOTENCY_GREEN")


def verify_nonphysical() -> None:
    p = proof()
    household_id = str(p["householdId"]); receipt_id = str(p["receiptId"]); batch_id = str(p["batchId"])
    physical_line_id = str(p["processedPhysicalLineId"]); physical_event_id = str(p["processedPhysicalEventId"])
    with engine.begin() as conn:
        receipt = conn.execute(text("SELECT household_id,approved_at FROM receipt_tables WHERE id=:id"), {"id": receipt_id}).mappings().one()
        assert str(receipt["household_id"]) == household_id and receipt["approved_at"] is not None
        loyalty_rows = conn.execute(text("SELECT id,raw_label,line_role,inventory_eligible FROM receipt_table_lines WHERE receipt_table_id=:rid AND upper(COALESCE(raw_label,'')) LIKE '%KOOPZEGEL%' ORDER BY line_index,id"), {"rid": receipt_id}).mappings().all()
        assert len(loyalty_rows) == 1
        loyalty = loyalty_rows[0]
        assert str(loyalty["line_role"]) == "loyalty" and bool(loyalty["inventory_eligible"]) is False
        loyalty_ref = f"receipt-line:{loyalty['id']}"
        assert conn.execute(text("SELECT id FROM purchase_import_lines WHERE batch_id=:bid AND external_line_ref=:ref"), {"bid": batch_id, "ref": loyalty_ref}).mappings().all() == []
        line = conn.execute(text("SELECT external_line_ref,processing_status,processed_event_id,matched_household_article_id FROM purchase_import_lines WHERE id=:id AND batch_id=:bid"), {"id": physical_line_id, "bid": batch_id}).mappings().one()
        assert str(line["processing_status"]) == "processed" and str(line["processed_event_id"]) == physical_event_id and str(line["external_line_ref"]).startswith("receipt-line:") and line["matched_household_article_id"] is not None
        event = conn.execute(text("SELECT household_id,household_article_id,event_type,source FROM inventory_events WHERE id=:id"), {"id": physical_event_id}).mappings().one()
        assert str(event["household_id"]) == household_id and str(event["household_article_id"]) == str(line["matched_household_article_id"])
        assert str(event["event_type"]) == "purchase" and str(event["source"]) == "store_import"
        physical_inventory = int(conn.execute(text("SELECT COUNT(*) FROM inventory WHERE household_id=:hid AND household_article_id=:aid AND COALESCE(aantal,0)>0"), {"hid": household_id, "aid": str(line["matched_household_article_id"])}).scalar_one())
        assert physical_inventory >= 1
        loyalty_articles = int(conn.execute(text("SELECT COUNT(*) FROM household_articles WHERE household_id=:hid AND lower(COALESCE(naam,'')) LIKE '%koopzegel%'"), {"hid": household_id}).scalar_one())
        loyalty_inventory = int(conn.execute(text("SELECT COUNT(*) FROM inventory WHERE household_id=:hid AND lower(COALESCE(naam,'')) LIKE '%koopzegel%'"), {"hid": household_id}).scalar_one())
        loyalty_events = int(conn.execute(text("SELECT COUNT(*) FROM inventory_events WHERE household_id=:hid AND lower(COALESCE(article_name,'')) LIKE '%koopzegel%'"), {"hid": household_id}).scalar_one())
        assert loyalty_articles == loyalty_inventory == loyalty_events == 0
    print("P0_NONPHYSICAL_POSTGRESQL_END_STATE_GREEN")


def verify_f6() -> None:
    p = proof()
    assert str(p["processStatus"]) == "500"
    assert str(p["inventoryRowsAfter"]) == "0"
    assert str(p["almostOutRowsBefore"]) == str(p["almostOutRowsAfter"])
    household_id = str(p["householdId"]); receipt_id = str(p["receiptId"]); batch_id = str(p["batchId"]); line_id = str(p["lineId"]); location_name = str(p["locationName"]); line_status_before = str(p["lineProcessingStatusBefore"] or "")
    email = os.environ["TP_CI_05_EMAIL"].strip().lower()
    with engine.begin() as conn:
        membership = conn.execute(text("SELECT household_id,role FROM public.household_memberships WHERE lower(trim(user_email))=:email"), {"email": email}).mappings().one()
        assert str(membership["household_id"]) == household_id and str(membership["role"]) == "admin"
        receipt = conn.execute(text("SELECT household_id,approved_at FROM public.receipt_tables WHERE id=:id"), {"id": receipt_id}).mappings().one()
        assert str(receipt["household_id"]) == household_id and receipt["approved_at"] is not None
        batch = conn.execute(text("SELECT household_id,processed_at FROM public.purchase_import_batches WHERE id=:id"), {"id": batch_id}).mappings().one()
        assert str(batch["household_id"]) == household_id and batch["processed_at"] is None
        line = conn.execute(text("SELECT target_location_id,processing_status,processed_event_id FROM public.purchase_import_lines WHERE id=:id"), {"id": line_id}).mappings().one()
        assert str(line["processing_status"] or "") == line_status_before and line["processed_event_id"] is None and line["target_location_id"] is not None
        space = conn.execute(text("SELECT household_id,naam FROM public.spaces WHERE id=:id"), {"id": str(line["target_location_id"])}).mappings().one()
        assert str(space["household_id"]) == household_id and str(space["naam"]) == location_name
        inventory_count = int(conn.execute(text("SELECT COUNT(*) FROM public.inventory WHERE household_id=:hid"), {"hid": household_id}).scalar_one())
        event_count = int(conn.execute(text("SELECT COUNT(*) FROM public.inventory_events WHERE household_id=:hid"), {"hid": household_id}).scalar_one())
        almost_out = build_almost_out_items(conn, household_id)
        assert inventory_count == 0 and event_count == 0 and len(almost_out) == 0
    print("F6_RECEIPT_BATCH_STATE_ROLLED_BACK_GREEN")
    print("F6_RECEIPT_INVENTORY_ZERO_EFFECT_GREEN")
    print("F6_RECEIPT_ALMOST_OUT_ZERO_EFFECT_GREEN")
    print("F6_RECEIPT_POSTGRESQL_ROLLBACK_GREEN")


COMMANDS = {
    "boundary-l4-03": lambda: boundary("P0_L4_03_POSTGRESQL_BOUNDARY_GREEN"),
    "boundary-l4-04": lambda: boundary("P0_L4_04_POSTGRESQL_BOUNDARY_GREEN"),
    "boundary-l4-05": lambda: boundary("P0_L4_05_POSTGRESQL_BOUNDARY_GREEN"),
    "boundary-nonphysical": lambda: boundary("P0_NONPHYSICAL_POSTGRESQL_BOUNDARY_GREEN"),
    "verify-l4-03": verify_l4_03,
    "verify-l4-04": verify_l4_04,
    "verify-l4-05": verify_l4_05,
    "verify-nonphysical": verify_nonphysical,
    "verify-f6": verify_f6,
}


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = COMMANDS.get(command)
    if fn is None:
        print(f"unknown command: {command}", file=sys.stderr)
        return 2
    fn()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

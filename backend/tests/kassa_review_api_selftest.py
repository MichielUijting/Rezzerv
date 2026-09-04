"""P0 F3-04: Kassa review -> approval -> Uitpakken boundary on PostgreSQL.

The authority starts with canonical receipt rows already present in Kassa. Parser/OCR
is deliberately outside this slice. From that boundary onward it uses the production
FastAPI detail, line-review and approval routes against a DML-only PostgreSQL runtime.
It verifies persisted review/approval state, canonical weighted quantity, household
isolation, approval validation and the hand-off to Uitpakken without processing
inventory itself (covered by F3-03).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hashlib
import json

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.receipt_ingestion.receipt_line_semantics import derive_receipt_line_semantics
from app.testing.canonical_scenario_catalog import REPO_ROOT, load_canonical_scenario_catalog
from app.testing.postgresql_onboarding_selftest_fixture import (
    create_postgresql_runtime_test_engine,
    seed_admin_member_household,
)

TARGET_HOUSEHOLD = "f3-kassa-target"
ISOLATION_HOUSEHOLD = "f3-kassa-isolation"
TARGET_ADMIN_EMAIL = "f3-kassa-admin@rezzerv.local"
ISOLATION_ADMIN_EMAIL = "f3-kassa-isolation-admin@rezzerv.local"
SEED_PASSWORD = "F3KassaSeed123!"


def _headers(email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer rezzerv-dev-token::{email.lower()}"}


def _prepare_database(engine) -> None:
    seed_admin_member_household(
        engine,
        household_id=TARGET_HOUSEHOLD,
        household_name="F3 Kassa doelhuishouden",
        admin_id="f3-kassa-admin",
        admin_email=TARGET_ADMIN_EMAIL,
        admin_password=SEED_PASSWORD,
        admin_membership_id="f3-kassa-admin-membership",
        member_id="f3-kassa-member",
        member_email="f3-kassa-member@rezzerv.local",
        member_password=SEED_PASSWORD,
        member_membership_id="f3-kassa-member-membership",
    )
    seed_admin_member_household(
        engine,
        household_id=ISOLATION_HOUSEHOLD,
        household_name="F3 Kassa isolatiehuishouden",
        admin_id="f3-kassa-isolation-admin",
        admin_email=ISOLATION_ADMIN_EMAIL,
        admin_password=SEED_PASSWORD,
        admin_membership_id="f3-kassa-isolation-admin-membership",
        member_id="f3-kassa-isolation-member",
        member_email="f3-kassa-isolation-member@rezzerv.local",
        member_password=SEED_PASSWORD,
        member_membership_id="f3-kassa-isolation-member-membership",
    )


def _catalog_and_baseline() -> tuple[dict, list[dict]]:
    catalog = load_canonical_scenario_catalog()
    fixtures = catalog["receipt_fixtures"]
    sources = {str(item["source"]) for item in fixtures.values()}
    assert len(sources) == 1
    baseline = json.loads((REPO_ROOT / sources.pop()).read_text(encoding="utf-8"))
    return catalog, baseline


def _canonical_receipt(fixture_name: str) -> tuple[dict, dict]:
    catalog, baseline = _catalog_and_baseline()
    fixture = catalog["receipt_fixtures"][fixture_name]
    receipt_id = str(fixture["selector"]["receipt_id"])
    matches = [row for row in baseline if str(row.get("receipt_id")) == receipt_id]
    assert len(matches) == 1, (fixture_name, receipt_id)
    return fixture, matches[0]


def _decimal(value):
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _purchase_at(receipt: dict) -> str:
    date_value = str(receipt.get("purchase_date") or "2026-01-01")
    time_value = str(receipt.get("purchase_time") or "12:00")
    return datetime.fromisoformat(f"{date_value}T{time_value}:00").isoformat()


def _seed_receipt(
    engine,
    *,
    fixture_name: str,
    seed_key: str,
    blank_store: bool = False,
) -> dict:
    fixture, receipt = _canonical_receipt(fixture_name)
    receipt_table_id = f"f3-kassa-receipt-{seed_key}"
    raw_receipt_id = f"f3-kassa-raw-{seed_key}"
    source_file = str(receipt.get("source_file") or f"{seed_key}.pdf")
    sha256_hash = hashlib.sha256(f"f3-04:{seed_key}".encode("utf-8")).hexdigest()
    lines = list(receipt.get("lines") or [])
    assert lines

    selected_product = str((fixture.get("selector") or {}).get("product_name") or "")
    line_ids: dict[str, str] = {}

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO raw_receipts (
                    id, household_id, source_id, original_filename, mime_type,
                    storage_path, sha256_hash, raw_status
                ) VALUES (
                    :id, :household_id, NULL, :original_filename, 'application/pdf',
                    :storage_path, :sha256_hash, 'parsed'
                )
                """
            ),
            {
                "id": raw_receipt_id,
                "household_id": TARGET_HOUSEHOLD,
                "original_filename": source_file,
                "storage_path": f"/tmp/rezzerv-f3-kassa/{source_file}",
                "sha256_hash": sha256_hash,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO receipt_tables (
                    id, raw_receipt_id, household_id, store_name, store_branch,
                    purchase_at, total_amount, discount_total, currency, parse_status,
                    confidence_score, line_count, logical_receipt_key, workflow_state
                ) VALUES (
                    :id, :raw_receipt_id, :household_id, :store_name, NULL,
                    :purchase_at, :total_amount, :discount_total, :currency, 'review_needed',
                    :confidence_score, :line_count, :logical_receipt_key, 'active'
                )
                """
            ),
            {
                "id": receipt_table_id,
                "raw_receipt_id": raw_receipt_id,
                "household_id": TARGET_HOUSEHOLD,
                "store_name": "" if blank_store else str(receipt.get("store_name") or ""),
                "purchase_at": _purchase_at(receipt),
                "total_amount": _decimal(receipt.get("total_amount")),
                "discount_total": _decimal(receipt.get("discount_total") or 0),
                "currency": str(receipt.get("currency") or "EUR"),
                "confidence_score": 0.80,
                "line_count": len(lines),
                "logical_receipt_key": f"f3-04:{seed_key}",
            },
        )

        for index, line in enumerate(lines, start=1):
            name = str(line.get("product_name") or line.get("expected_label") or "").strip()
            assert name
            line_id = f"f3-kassa-line-{seed_key}-{index}"
            line_ids[name] = line_id
            semantic_input = {
                **line,
                "raw_label": name,
                "receipt_line_text": name,
                "unit": line.get("unit_size"),
            }
            semantics = derive_receipt_line_semantics(
                semantic_input,
                store_name=str(receipt.get("store_name") or "") or None,
            )
            is_selected_uncertain = bool(selected_product and name == selected_product and fixture_name == "uncertain_match")
            is_first_normal = fixture_name == "normal_physical" and index == 1
            conn.execute(
                text(
                    """
                    INSERT INTO receipt_table_lines (
                        id, receipt_table_id, line_index, raw_label, normalized_label,
                        quantity, unit, unit_price, line_total, discount_amount, barcode,
                        article_match_status, matched_article_id, confidence_score,
                        logical_line_key, is_validated, line_role, inventory_eligible
                    ) VALUES (
                        :id, :receipt_table_id, :line_index, :raw_label, :normalized_label,
                        :quantity, :unit, :unit_price, :line_total, :discount_amount, :barcode,
                        :article_match_status, NULL, :confidence_score,
                        :logical_line_key, :is_validated, :line_role, :inventory_eligible
                    )
                    """
                ),
                {
                    "id": line_id,
                    "receipt_table_id": receipt_table_id,
                    "line_index": int(line.get("line_number") or index),
                    "raw_label": name,
                    "normalized_label": name.lower(),
                    "quantity": _decimal(line.get("quantity")),
                    "unit": line.get("unit_size"),
                    "unit_price": _decimal(line.get("unit_price")),
                    "line_total": _decimal(line.get("line_total")),
                    "discount_amount": _decimal(line.get("discount_amount") or 0),
                    "barcode": line.get("barcode"),
                    "article_match_status": "uncertain" if is_selected_uncertain else "unmatched",
                    "confidence_score": 0.40 if is_selected_uncertain else 0.95,
                    "logical_line_key": f"f3-04:{seed_key}:{index}",
                    "is_validated": not (is_selected_uncertain or is_first_normal),
                    "line_role": semantics["line_role"],
                    "inventory_eligible": 1 if semantics["inventory_eligible"] else 0,
                },
            )

    return {
        "fixture": fixture,
        "receipt": receipt,
        "receipt_table_id": receipt_table_id,
        "raw_receipt_id": raw_receipt_id,
        "line_ids": line_ids,
    }


def _line_for_product(seed: dict, product_name: str) -> tuple[str, dict]:
    matches = [
        line for line in seed["receipt"]["lines"]
        if str(line.get("product_name") or "").strip() == product_name
    ]
    assert matches
    return seed["line_ids"][product_name], matches[0]


def _review_line(client: TestClient, receipt_id: str, line_id: str, line: dict, headers: dict[str, str]):
    response = client.patch(
        f"/api/receipts/{receipt_id}/lines/{line_id}",
        headers=headers,
        json={
            "article_name": str(line.get("product_name") or ""),
            "quantity": float(line.get("quantity")) if line.get("quantity") is not None else None,
            "unit": line.get("unit_size"),
            "unit_price": float(line.get("unit_price")) if line.get("unit_price") is not None else None,
            "line_total": float(line.get("line_total")) if line.get("line_total") is not None else None,
            "is_validated": True,
            "is_deleted": False,
        },
    )
    assert response.status_code == 200, response.text
    return response


def run() -> int:
    checks: list[str] = []
    engine = create_postgresql_runtime_test_engine()
    try:
        assert engine.dialect.name == "postgresql"
        with engine.begin() as conn:
            assert bool(conn.execute(text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")).scalar_one()) is False
        checks.append("postgresql_dml_only_runtime")

        _prepare_database(engine)
        normal = _seed_receipt(engine, fixture_name="normal_physical", seed_key="normal")
        uncertain = _seed_receipt(engine, fixture_name="uncertain_match", seed_key="uncertain")
        loyalty = _seed_receipt(engine, fixture_name="non_physical_loyalty", seed_key="loyalty")
        invalid = _seed_receipt(engine, fixture_name="normal_physical", seed_key="invalid", blank_store=True)

        from app import main as main_module

        main_module.engine = engine
        owner_headers = _headers(TARGET_ADMIN_EMAIL)
        isolation_headers = _headers(ISOLATION_ADMIN_EMAIL)

        with TestClient(main_module.app) as client:
            normal_detail = client.get(f"/api/receipts/{normal['receipt_table_id']}", headers=owner_headers)
            assert normal_detail.status_code == 200, normal_detail.text
            assert len(normal_detail.json().get("lines") or []) == int(normal["receipt"]["article_count"])
            checks.append("canonical_kassa_fixture_is_visible_through_real_api")

            normal_first = normal["receipt"]["lines"][0]
            normal_first_id = normal["line_ids"][str(normal_first["product_name"])]
            _review_line(client, normal["receipt_table_id"], normal_first_id, normal_first, owner_headers)
            with engine.begin() as conn:
                reviewed = conn.execute(
                    text("SELECT is_validated, corrected_raw_label FROM receipt_table_lines WHERE id = :id"),
                    {"id": normal_first_id},
                ).mappings().one()
                assert reviewed["is_validated"] is True
                assert str(reviewed["corrected_raw_label"] or "") == str(normal_first["product_name"])
                assert int(conn.execute(text("SELECT COUNT(*) FROM purchase_import_batches WHERE source_type = 'receipt' AND source_reference = :ref"), {"ref": f"receipt:{normal['receipt_table_id']}"}).scalar_one()) == 0
            checks.append("review_edit_persists_canonical_line_state")

            uncertain_product = str(uncertain["fixture"]["selector"]["product_name"])
            uncertain_id, uncertain_line = _line_for_product(uncertain, uncertain_product)
            with engine.begin() as conn:
                before = conn.execute(text("SELECT is_validated FROM receipt_table_lines WHERE id = :id"), {"id": uncertain_id}).scalar_one()
                assert before is False
            _review_line(client, uncertain["receipt_table_id"], uncertain_id, uncertain_line, owner_headers)
            with engine.begin() as conn:
                after = conn.execute(text("SELECT rtl.is_validated, rt.reviewed_at FROM receipt_table_lines rtl JOIN receipt_tables rt ON rt.id = rtl.receipt_table_id WHERE rtl.id = :id"), {"id": uncertain_id}).mappings().one()
                assert after["is_validated"] is True
                assert after["reviewed_at"] is not None
            checks.append("uncertain_line_accepts_explicit_review")

            weighted_fixture = load_canonical_scenario_catalog()["receipt_fixtures"]["weighted_quantity"]
            weighted_product = str(weighted_fixture["selector"]["product_name"])
            weighted_id, _ = _line_for_product(uncertain, weighted_product)
            with engine.begin() as conn:
                quantity = conn.execute(text("SELECT quantity FROM receipt_table_lines WHERE id = :id"), {"id": weighted_id}).scalar_one()
                assert Decimal(str(quantity)) == Decimal(str(weighted_fixture["contract"]["quantity"])) == Decimal("0.404")
            checks.append("weighted_quantity_roundtrips_exactly_in_kassa")

            foreign_read = client.get(f"/api/receipts/{normal['receipt_table_id']}", headers=isolation_headers)
            assert foreign_read.status_code == 403, foreign_read.text
            foreign_review = client.patch(
                f"/api/receipts/{normal['receipt_table_id']}/lines/{normal_first_id}",
                headers=isolation_headers,
                json={"is_validated": True},
            )
            assert foreign_review.status_code == 403, foreign_review.text
            foreign_approve = client.post(f"/api/receipts/{normal['receipt_table_id']}/approve", headers=isolation_headers)
            assert foreign_approve.status_code == 403, foreign_approve.text
            checks.append("cross_household_kassa_read_write_and_approval_are_blocked")

            with engine.begin() as conn:
                inventory_event_count_before_approval = int(
                    conn.execute(text("SELECT COUNT(*) FROM inventory_events")).scalar_one()
                )

            approved = client.post(f"/api/receipts/{normal['receipt_table_id']}/approve", headers=owner_headers)
            assert approved.status_code == 200, approved.text
            with engine.begin() as conn:
                receipt_row = conn.execute(
                    text("SELECT parse_status, approved_at, approved_by_user_email, reviewed_at, totals_overridden FROM receipt_tables WHERE id = :id"),
                    {"id": normal["receipt_table_id"]},
                ).mappings().one()
                assert receipt_row["parse_status"] == "approved", receipt_row
                assert receipt_row["approved_at"] is not None
                assert str(receipt_row["approved_by_user_email"] or "") == TARGET_ADMIN_EMAIL
                assert receipt_row["reviewed_at"] is not None
                assert receipt_row["totals_overridden"] is False
                batch_rows = conn.execute(
                    text("SELECT id FROM purchase_import_batches WHERE household_id = :household_id AND source_type = 'receipt' AND source_reference = :ref"),
                    {"household_id": TARGET_HOUSEHOLD, "ref": f"receipt:{normal['receipt_table_id']}"},
                ).mappings().all()
                assert len(batch_rows) == 1, batch_rows
                inventory_event_count_after_approval = int(
                    conn.execute(text("SELECT COUNT(*) FROM inventory_events")).scalar_one()
                )
                assert inventory_event_count_after_approval == inventory_event_count_before_approval
            checks.append("approval_persists_state_and_creates_unpack_boundary_without_inventory_mutation")

            loyalty_approved = client.post(f"/api/receipts/{loyalty['receipt_table_id']}/approve", headers=owner_headers)
            assert loyalty_approved.status_code == 200, loyalty_approved.text
            loyalty_product = str(loyalty["fixture"]["selector"]["product_name"])
            with engine.begin() as conn:
                loyalty_semantics = conn.execute(
                    text("SELECT line_role, inventory_eligible FROM receipt_table_lines WHERE receipt_table_id = :receipt_id AND raw_label = :label"),
                    {"receipt_id": loyalty["receipt_table_id"], "label": loyalty_product},
                ).mappings().one()
                assert int(loyalty_semantics["inventory_eligible"] or 0) == 0, loyalty_semantics
                unpack_lines = conn.execute(
                    text("SELECT pil.article_name_raw FROM purchase_import_lines pil JOIN purchase_import_batches pib ON pib.id = pil.batch_id WHERE pib.source_type = 'receipt' AND pib.source_reference = :ref"),
                    {"ref": f"receipt:{loyalty['receipt_table_id']}"},
                ).scalars().all()
                assert unpack_lines, "Goedkeuring moet fysieke regels naar Uitpakken aanbieden"
                assert loyalty_product.lower() not in {str(value or "").strip().lower() for value in unpack_lines}
            checks.append("non_physical_line_remains_outside_unpack_inventory_flow")

            invalid_approval = client.post(f"/api/receipts/{invalid['receipt_table_id']}/approve", headers=owner_headers)
            assert invalid_approval.status_code == 400, invalid_approval.text
            with engine.begin() as conn:
                invalid_row = conn.execute(text("SELECT approved_at FROM receipt_tables WHERE id = :id"), {"id": invalid["receipt_table_id"]}).scalar_one()
                assert invalid_row is None
                invalid_batches = int(conn.execute(text("SELECT COUNT(*) FROM purchase_import_batches WHERE source_type = 'receipt' AND source_reference = :ref"), {"ref": f"receipt:{invalid['receipt_table_id']}"}).scalar_one())
                assert invalid_batches == 0
            checks.append("approval_validation_rejects_incomplete_receipt")

        for check in checks:
            print(f"PASS {check}")
        print(f"RESULT {len(checks)}/9 checks passed")
        assert len(checks) == 9
        print("KASSA_REVIEW_API_POSTGRESQL_GREEN")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(run())

from __future__ import annotations

import uuid

from sqlalchemy import text

from app.db import engine
from app.services.off_product_link_service import link_off_product_with_product_type
from app.services.product_inventory_group_store import ensure_product_inventory_group_schema


def _count(conn, table_name: str) -> int:
    return int(conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar() or 0)


def main() -> int:
    ensure_product_inventory_group_schema()
    suffix = uuid.uuid4().hex
    batch_id = f"off-link-batch-{suffix}"
    line_id = f"off-link-line-{suffix}"
    product_type_key = f"test.off.halfvolle.melk.{suffix}"
    gtin = f"98{suffix[:11]}"

    with engine.begin() as conn:
        before = {
            "candidates": _count(conn, "external_product_candidates"),
            "inventory": _count(conn, "inventory"),
            "events": _count(conn, "inventory_events"),
        }
        connection = conn.execute(text("""
            SELECT hsc.id AS connection_id, hsc.store_provider_id
            FROM household_store_connections hsc
            WHERE hsc.household_id = '1'
            ORDER BY hsc.linked_at DESC, hsc.id DESC
            LIMIT 1
        """)).mappings().first()
        if not connection:
            provider = conn.execute(text("""
                SELECT id
                FROM store_providers
                WHERE status = 'active'
                ORDER BY id
                LIMIT 1
            """)).mappings().first()
            if not provider:
                provider_id = f"off-link-provider-{suffix}"
                conn.execute(text("""
                    INSERT INTO store_providers (
                        id, code, name, status, import_mode
                    ) VALUES (
                        :id, :code, 'OFF-link contracttest',
                        'active', 'mock'
                    )
                """), {
                    "id": provider_id,
                    "code": f"off-link-contract-{suffix[:12]}",
                })
            else:
                provider_id = str(provider["id"])

            connection_id = f"off-link-connection-{suffix}"
            conn.execute(text("""
                INSERT INTO household_store_connections (
                    id, household_id, store_provider_id,
                    connection_status, linked_at, created_at, updated_at
                ) VALUES (
                    :id, '1', :store_provider_id,
                    'active', CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """), {
                "id": connection_id,
                "store_provider_id": provider_id,
            })
            connection = {
                "connection_id": connection_id,
                "store_provider_id": provider_id,
            }

        conn.execute(text("""
            INSERT INTO purchase_import_batches (
                id, household_id, store_provider_id, connection_id,
                source_type, source_reference,
                import_status, raw_payload, created_at
            ) VALUES (
                :id, '1', :store_provider_id, :connection_id,
                'contract_selftest', :source_reference,
                'in_review', '{}', CURRENT_TIMESTAMP
            )
        """), {
            "id": batch_id,
            "store_provider_id": str(connection["store_provider_id"]),
            "connection_id": str(connection["connection_id"]),
            "source_reference": f"contract:{suffix}",
        })
        conn.execute(text("""
            INSERT INTO purchase_import_lines (
                id, batch_id, external_line_ref, external_article_code,
                article_name_raw, brand_raw, quantity_raw, unit_raw,
                currency_code, match_status, review_decision,
                processing_status, created_at, updated_at
            ) VALUES (
                :id, :batch_id, :external_line_ref, NULL,
                'Contract Halfvolle melk', 'Contractmerk', 1, 'stuk',
                'EUR', 'unmatched', 'pending',
                'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {"id": line_id, "batch_id": batch_id, "external_line_ref": f"line:{suffix}"})

    assignment = {
        "create": {
            "inventory_group_key": product_type_key,
            "canonical_name": "Halfvolle koemelk contracttest",
            "base_unit": "ml",
            "aggregation_mode": "volume",
        },
        "mapping_source": "contract_selftest",
        "confidence_score": 0.99,
    }
    off_product = {
        "gtin": gtin,
        "product_name": "Contract Halfvolle melk 1 l",
        "brand": "Contractmerk",
        "quantity": "1 l",
        "category": "Halfvolle melk",
    }

    result = link_off_product_with_product_type(
        receipt_item_id=f"purchase-import-line:{line_id}",
        off_product=off_product,
        product_type_assignment=assignment,
    )
    assert result.get("ok") and result.get("linked"), result
    assert result.get("creates_external_candidate") is False, result
    assert result.get("mutates_inventory") is False, result
    global_product_id = str((result.get("global_product") or {}).get("id") or "")

    rollback_gtin = f"97{suffix[:11]}"
    try:
        link_off_product_with_product_type(
            receipt_item_id=f"purchase-import-line:{line_id}",
            off_product={**off_product, "gtin": rollback_gtin, "product_name": "Rollback melk"},
            product_type_assignment={
                "create": {
                    "inventory_group_key": f"test.rollback.{suffix}",
                    "canonical_name": "Rollback producttype",
                    "base_unit": "ml",
                    "aggregation_mode": "volume",
                },
                "mapping_source": "contract_selftest_rollback",
            },
            force_failure_after_link=True,
        )
        raise AssertionError("Geforceerde rollbackfout bleef uit")
    except RuntimeError as exc:
        assert "rollbackcontrole" in str(exc)

    try:
        with engine.begin() as conn:
            after = {
                "candidates": _count(conn, "external_product_candidates"),
                "inventory": _count(conn, "inventory"),
                "events": _count(conn, "inventory_events"),
            }
            assert after == before, {"before": before, "after": after}
            line = conn.execute(text("""
                SELECT matched_global_product_id, match_status
                FROM purchase_import_lines WHERE id = :id
            """), {"id": line_id}).mappings().first()
            assert str((line or {}).get("matched_global_product_id") or "") == global_product_id, line
            assert str((line or {}).get("match_status") or "") == "matched", line
            membership_count = conn.execute(text("""
                SELECT COUNT(*) FROM product_group_memberships
                WHERE global_product_id = :global_product_id
                  AND inventory_group_key = :key
                  AND active = 1 AND confirmed_by_user = 1
            """), {"global_product_id": global_product_id, "key": product_type_key}).scalar() or 0
            assert int(membership_count) == 1, membership_count
            rollback_product_count = conn.execute(text("""
                SELECT COUNT(*) FROM global_products WHERE primary_gtin = :gtin
            """), {"gtin": rollback_gtin}).scalar() or 0
            assert int(rollback_product_count) == 0, rollback_product_count
        print("PASS off_result_product_type_atomic_contract")
        print("PASS off_result_does_not_persist_candidate_or_inventory")
        print("PASS off_result_rollback_contract")
        print("OFF_PRODUCT_TYPE_LINK_CONTRACT_GREEN")
        return 0
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM purchase_import_lines WHERE id = :id"), {"id": line_id})
            conn.execute(text("DELETE FROM purchase_import_batches WHERE id = :id"), {"id": batch_id})
            conn.execute(text("DELETE FROM product_group_memberships WHERE global_product_id = :id"), {"id": global_product_id})
            conn.execute(text("DELETE FROM product_identities WHERE global_product_id = :id OR identity_value = :gtin"), {"id": global_product_id, "gtin": gtin})
            conn.execute(text("DELETE FROM global_products WHERE id = :id"), {"id": global_product_id})
            conn.execute(text("DELETE FROM product_inventory_groups WHERE inventory_group_key = :key"), {"key": product_type_key})


if __name__ == "__main__":
    raise SystemExit(main())

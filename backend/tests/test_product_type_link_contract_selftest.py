
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.db import engine
from app.services.external_product_candidate_store import promote_external_product_candidate_with_product_type
from app.services.product_inventory_group_store import ensure_product_inventory_group_schema


def main() -> int:
    ensure_product_inventory_group_schema()
    suffix = uuid.uuid4().hex
    candidate_id = f"product-type-contract-candidate-{suffix}"
    context_key = f"product-type-contract-context-{suffix}"
    product_type_key = f"test.halfvolle.melk.{suffix}"
    gtin = f"99{suffix[:11]}"

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO external_product_candidates (
                id, purchase_import_line_id, source_name, source_product_code,
                candidate_name, candidate_brand, candidate_category, score,
                status, context_key, candidate_source_name,
                candidate_source_product_code, candidate_status,
                is_user_confirmed, created_at, updated_at
            ) VALUES (
                :id, :line_id, 'open_food_facts', :gtin,
                'Contract Halfvolle melk', 'Contractmerk', 'Halfvolle melk', 0.99,
                'candidate', :context_key, 'open_food_facts',
                :gtin, 'candidate', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {"id": candidate_id, "line_id": f"contract-line-{suffix}", "gtin": gtin, "context_key": context_key})

    result = promote_external_product_candidate_with_product_type(
        candidate_id,
        product_type_assignment={
            "create": {
                "inventory_group_key": product_type_key,
                "canonical_name": "Halfvolle koemelk contracttest",
                "base_unit": "ml",
                "aggregation_mode": "volume",
            },
            "mapping_source": "contract_selftest",
            "confidence_score": 0.99,
        },
    )
    assert result.get("ok") and result.get("promoted"), result
    assert result.get("mutates_inventory") is False, result
    global_product_id = str(result.get("global_product_id") or "")

    try:
        with engine.begin() as conn:
            membership_count = conn.execute(text("""
                SELECT COUNT(*) FROM product_group_memberships
                WHERE global_product_id = :global_product_id
                  AND inventory_group_key = :key
                  AND active = 1
                  AND confirmed_by_user = 1
            """), {"global_product_id": global_product_id, "key": product_type_key}).scalar() or 0
            linked = conn.execute(text("SELECT global_product_id FROM external_product_candidates WHERE id = :id"), {"id": candidate_id}).scalar()
            assert int(membership_count) == 1, membership_count
            assert str(linked or "") == global_product_id, linked
        print("PASS candidate_and_product_type_atomic_contract")
        print("PRODUCT_TYPE_LINK_CONTRACT_GREEN")
        return 0
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM external_product_candidates WHERE id = :id"), {"id": candidate_id})
            conn.execute(text("DELETE FROM product_group_memberships WHERE global_product_id = :id"), {"id": global_product_id})
            conn.execute(text("DELETE FROM product_identities WHERE global_product_id = :id OR identity_value = :gtin"), {"id": global_product_id, "gtin": gtin})
            conn.execute(text("DELETE FROM global_products WHERE id = :id"), {"id": global_product_id})
            conn.execute(text("DELETE FROM product_inventory_groups WHERE inventory_group_key = :key"), {"key": product_type_key})


if __name__ == "__main__":
    raise SystemExit(main())

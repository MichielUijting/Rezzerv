from __future__ import annotations

from sqlalchemy import inspect, text

from app.db import engine
from app.services.gpc_localization_service import (
    LOCALIZED_COLUMNS,
    ensure_gpc_localization_schema,
    synchronize_dutch_product_type_display_names,
)


def main() -> None:
    ensure_gpc_localization_schema()
    columns = {str(column.get("name") or "") for column in inspect(engine).get_columns("gpc_product_groups")}
    missing_columns = sorted(set(LOCALIZED_COLUMNS) - columns)
    assert not missing_columns, missing_columns
    print("PASS gpc_localized_columns")

    with engine.begin() as conn:
        before_inventory = int(conn.execute(text("SELECT COUNT(*) FROM inventory")).scalar() or 0)
        before_events = int(conn.execute(text("SELECT COUNT(*) FROM inventory_events")).scalar() or 0)

    result = synchronize_dutch_product_type_display_names()
    assert result["ok"] is True
    assert result["display_policy"] == "dutch_required"
    assert result["missing_dutch"] == 0
    assert result["missing_english"] == 0
    assert result["mutates_inventory"] is False
    print("PASS gpc_localization_complete")

    with engine.begin() as conn:
        mismatch_count = int(conn.execute(text("""
            SELECT COUNT(*)
            FROM product_inventory_groups p
            JOIN gpc_product_groups g ON g.gpc_brick_code = p.gpc_brick_code
            WHERE COALESCE(p.active, 1) = 1
              AND COALESCE(g.active, 1) = 1
              AND trim(COALESCE(p.display_name, '')) <> trim(COALESCE(g.gpc_brick_name_nl, ''))
        """)).scalar() or 0)
        after_inventory = int(conn.execute(text("SELECT COUNT(*) FROM inventory")).scalar() or 0)
        after_events = int(conn.execute(text("SELECT COUNT(*) FROM inventory_events")).scalar() or 0)

    assert mismatch_count == 0, mismatch_count
    assert before_inventory == after_inventory
    assert before_events == after_events
    print("PASS product_type_display_uses_dutch")
    print("PASS gpc_localization_does_not_mutate_inventory")
    print("GPC_DUTCH_LOCALIZATION_CONTRACT_GREEN")


if __name__ == "__main__":
    main()

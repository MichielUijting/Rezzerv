from __future__ import annotations

from app.services.product_type_quantity_event_service import (
    aggregate_product_type_quantity_events,
    ensure_product_type_quantity_event_schema,
    record_product_type_quantity_event,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    ensure_product_type_quantity_event_schema()
    print("PASS product_type_quantity_event_schema")

    unresolved = record_product_type_quantity_event(
        household_id="1",
        event_type="purchase",
        source_quantity=1,
        source_unit="stuk",
    )
    _assert(unresolved.get("event_recorded") is False, "onopgelost event mag niet worden opgeslagen")
    _assert(unresolved.get("status") == "missing_household_article", "onverwachte resolverstatus")
    print("PASS product_type_quantity_event_blocks_unresolved")

    aggregated = aggregate_product_type_quantity_events("1")
    _assert(aggregated.get("basis") == "product_type_snapshot", "historiebasis onjuist")
    _assert(aggregated.get("historical_membership_recalculated") is False, "historie mag koppelingen niet herberekenen")
    _assert(aggregated.get("read_only") is True, "aggregatie moet read-only zijn")
    _assert(isinstance(aggregated.get("items"), list), "historie-items ontbreken")
    print("PASS product_type_quantity_event_snapshot_aggregation")

    print("PRODUCT_TYPE_QUANTITY_EVENT_PHASE_G_GREEN")


if __name__ == "__main__":
    main()

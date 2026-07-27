from __future__ import annotations

from app.services.product_type_readiness_audit_service import build_product_type_readiness_audit


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    result = build_product_type_readiness_audit("1")

    _assert(result.get("basis") == "product_type_end_to_end", "auditbasis onjuist")
    _assert(result.get("read_only") is True, "audit moet read-only zijn")
    _assert(result.get("mutates_inventory") is False, "audit mag voorraad niet muteren")
    _assert(result.get("mutates_purchase_list") is False, "audit mag inkooplijst niet muteren")

    checks = result.get("checks") or []
    _assert(len(checks) == 5, "niet alle Producttypeketencontracten gecontroleerd")
    _assert(all(check.get("ok") is True for check in checks), "Producttypeketencontract niet groen")
    _assert(result.get("contract_green") is True, "ketencontract moet groen zijn")
    print("PASS product_type_readiness_contract_chain")

    coverage = result.get("coverage") or {}
    source_rows = int(coverage.get("source_inventory_rows") or 0)
    projected_rows = int(coverage.get("projected_inventory_rows") or 0)
    excluded_rows = int(coverage.get("excluded_inventory_rows") or 0)
    _assert(source_rows == projected_rows + excluded_rows, "audit verantwoordt niet alle voorraadregels")
    print("PASS product_type_readiness_coverage_accounting")

    blockers = result.get("blockers") or []
    if blockers:
        _assert(result.get("operationally_ready") is False, "audit mag bij blockers niet operationeel gereed zijn")
    print("PASS product_type_readiness_blocker_contract")

    print("PRODUCT_TYPE_READINESS_AUDIT_PHASE_I_GREEN")


if __name__ == "__main__":
    main()

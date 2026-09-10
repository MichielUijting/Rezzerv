#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT_PATH = ROOT / "quality" / "acceptance" / "f6_failure_recovery_gap_audit.json"
CLOSURE_PATH = ROOT / "quality" / "acceptance" / "p0_residual_closure.json"

EXPECTED_BASELINE = "2e2bac74318fc2e73726ed68e1b29fef464fb619"
EXPECTED_CATEGORIES = {
    "auth_401_403",
    "functional_4xx",
    "controlled_5xx",
    "timeout_temporary_failure",
    "invalid_import",
    "retry_duplicate_request",
    "interrupted_flow",
    "safe_resume",
    "standard_user_feedback",
    "db_consistency_after_error",
}
EXPECTED_STATUSES = {"covered", "partial", "gap", "na"}
EXPECTED_PRIORITY_SLICES = {f"F6-{index:02d}" for index in range(1, 6)}
EXPECTED_COUNTS = {"covered": 23, "partial": 58, "gap": 36, "na": 23}

SHARED_KASSA_WORKFLOW = ".github/workflows/tp-ci-02-kassa-shared-stack-postgresql-validation.yml"
MIGRATED_EVIDENCE = {
    ".github/workflows/p0-kassa-review-fullstack-postgresql-validation.yml": SHARED_KASSA_WORKFLOW,
    ".github/workflows/f6-kassa-review-controlled-5xx-postgresql-validation.yml": SHARED_KASSA_WORKFLOW,
}


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def require(condition: bool, marker: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL {marker}")
    print(f"PASS {marker}")


def evidence_exists(evidence_path: str) -> bool:
    path = ROOT / evidence_path
    if path.exists():
        return True
    replacement = MIGRATED_EVIDENCE.get(evidence_path)
    if not replacement:
        return False
    replacement_path = ROOT / replacement
    if replacement_path.exists():
        print(f"PASS evidence_migrated_{evidence_path}_to_{replacement}")
        return True
    return False


def main() -> None:
    audit = load_json(AUDIT_PATH)
    closure = load_json(CLOSURE_PATH)

    require(audit.get("schema_version") == 1, "f6_audit_schema_version")
    require(audit.get("baseline", {}).get("branch") == "main", "f6_audit_baseline_branch_main")
    require(audit.get("baseline", {}).get("commit") == EXPECTED_BASELINE, "f6_audit_baseline_exact")
    require(set(audit.get("status_values", [])) == EXPECTED_STATUSES, "f6_audit_status_values_exact")
    require(set(audit.get("categories", {})) == EXPECTED_CATEGORIES, "f6_audit_exact_10_categories")

    closed_p0 = {
        row.get("id")
        for row in closure.get("scenarios", [])
        if row.get("status") == "closed"
    }
    require(len(closed_p0) == 14, "f6_source_has_14_closed_p0_scenarios")

    scenarios = audit.get("scenarios", [])
    ids = [row.get("id") for row in scenarios]
    require(len(ids) == len(set(ids)) == 14, "f6_audit_has_14_unique_scenarios")
    require(set(ids) == closed_p0, "f6_audit_matches_exact_closed_p0_set")

    counts = Counter()
    for row in scenarios:
        scenario_id = row["id"]
        assessments = row.get("assessments", {})
        require(set(assessments) == EXPECTED_CATEGORIES, f"{scenario_id}_has_exact_10_categories")
        require(set(assessments.values()) <= EXPECTED_STATUSES, f"{scenario_id}_statuses_valid")
        counts.update(assessments.values())

        evidence = row.get("evidence") or []
        if any(status in {"covered", "partial"} for status in assessments.values()):
            require(bool(evidence), f"{scenario_id}_has_evidence_for_non_gap_claims")
        for evidence_path in evidence:
            require(evidence_exists(evidence_path), f"{scenario_id}_evidence_exists_{evidence_path}")

    summary = audit.get("summary", {})
    require(summary.get("total_p0_scenarios") == 14, "f6_summary_14_p0")
    require(summary.get("categories_per_scenario") == 10, "f6_summary_10_categories")
    require(summary.get("total_assessments") == 140, "f6_summary_140_assessments")
    for status, expected in EXPECTED_COUNTS.items():
        require(counts[status] == expected, f"f6_count_{status}_{expected}")
        require(summary.get(status) == expected, f"f6_summary_{status}_{expected}")

    slices = audit.get("priority_slices", [])
    slice_ids = {row.get("id") for row in slices}
    require(slice_ids == EXPECTED_PRIORITY_SLICES, "f6_priority_slices_f6_01_through_f6_05")
    require(all(row.get("priority") == "P0" for row in slices), "f6_priority_slices_are_p0")
    require(all(row.get("scope") and row.get("exit") for row in slices), "f6_priority_slices_have_scope_and_exit")

    controlled_5xx_gaps = sum(
        1 for row in scenarios if row["assessments"]["controlled_5xx"] == "gap"
    )
    require(controlled_5xx_gaps >= 10, "f6_controlled_5xx_is_confirmed_cross_cutting_gap")

    receipt = next(row for row in scenarios if row["id"] == "P0-RECEIPT-INVENTORY-ALMOSTOUT")
    require(receipt["assessments"]["retry_duplicate_request"] == "covered", "f6_reuses_l4_05_idempotency_authority")
    require(receipt["assessments"]["controlled_5xx"] == "covered", "f6_receipt_controlled_5xx_covered")
    require(receipt["assessments"]["standard_user_feedback"] == "covered", "f6_receipt_standard_feedback_covered")
    require(receipt["assessments"]["db_consistency_after_error"] == "covered", "f6_receipt_db_consistency_after_error_covered")
    receipt_evidence = set(receipt.get("evidence") or [])
    require(
        "frontend/tests/e2e/f6-receipt-controlled-5xx.fullstack.spec.js" in receipt_evidence,
        "f6_receipt_browser_authority_registered",
    )
    require(
        ".github/workflows/f6-receipt-controlled-5xx-postgresql-validation.yml" in receipt_evidence,
        "f6_receipt_postgresql_workflow_registered",
    )

    kassa = next(row for row in scenarios if row["id"] == "P0-KASSA-REVIEW")
    require(kassa["assessments"]["controlled_5xx"] == "covered", "f6_kassa_controlled_5xx_covered")
    require(kassa["assessments"]["standard_user_feedback"] == "covered", "f6_kassa_standard_feedback_covered")
    require(kassa["assessments"]["db_consistency_after_error"] == "covered", "f6_kassa_db_consistency_after_error_covered")
    kassa_evidence = set(kassa.get("evidence") or [])
    require(
        "backend/tests/f6_kassa_controlled_5xx_fixture.py" in kassa_evidence,
        "f6_kassa_postgresql_fixture_registered",
    )
    require(
        "frontend/tests/e2e/f6-kassa-review-controlled-5xx.fullstack.spec.js" in kassa_evidence,
        "f6_kassa_browser_authority_registered",
    )
    require(
        ".github/workflows/f6-kassa-review-controlled-5xx-postgresql-validation.yml" in kassa_evidence,
        "f6_kassa_historical_postgresql_workflow_registered",
    )
    require((ROOT / SHARED_KASSA_WORKFLOW).exists(), "f6_kassa_shared_postgresql_workflow_registered")

    account = next(row for row in scenarios if row["id"] == "P0-ACCOUNT-SESSION")
    require(account["assessments"]["auth_401_403"] == "covered", "f6_reuses_account_stale_session_401")

    inventory = next(row for row in scenarios if row["id"] == "P0-INVENTORY")
    require(inventory["assessments"]["controlled_5xx"] == "covered", "f6_inventory_controlled_5xx_covered")
    require(inventory["assessments"]["standard_user_feedback"] == "covered", "f6_inventory_standard_feedback_covered")
    require(inventory["assessments"]["db_consistency_after_error"] == "covered", "f6_inventory_db_consistency_after_error_covered")
    inventory_evidence = set(inventory.get("evidence") or [])
    require(
        "frontend/tests/e2e/f6-inventory-controlled-5xx.fullstack.spec.js" in inventory_evidence,
        "f6_inventory_browser_authority_registered",
    )
    require(
        ".github/workflows/f6-inventory-controlled-5xx-postgresql-validation.yml" in inventory_evidence,
        "f6_inventory_postgresql_workflow_registered",
    )

    print("F6_FAILURE_RECOVERY_GAP_AUDIT_GREEN")


if __name__ == "__main__":
    main()

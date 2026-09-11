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
EXPECTED_COUNTS = {"covered": 39, "partial": 52, "gap": 26, "na": 23}

SHARED_KASSA_WORKFLOW = ".github/workflows/tp-ci-02-kassa-shared-stack-postgresql-validation.yml"
F6_02_WORKFLOW = ".github/workflows/f6-02-temporary-failure-safe-retry-postgresql-validation.yml"
F6_02_PROOF_RUN = "34617055659"
F6_02_PROOF_JOB = "103321480244"
F6_02_PROOF_SHA = "0b79b1b4fe9ae6fc47d0dcacaca78e1be56c44bf"
F6_03_SPEC = "frontend/tests/e2e/f6-03-invalid-import-fail-closed.fullstack.spec.js"
F6_03_WORKFLOW = ".github/workflows/f6-03-invalid-import-fail-closed-postgresql-validation.yml"
F6_03_PROOF_RUN = "34625163561"
F6_03_PROOF_JOB = "103348569125"
F6_03_PROOF_SHA = "309e113a8e4cfb550d54b28d78861029f66861d6"
F6_04_SPEC = "frontend/tests/e2e/f6-04-interrupted-mutation-safe-resume.fullstack.spec.js"
F6_04_WORKFLOW = ".github/workflows/f6-04-interrupted-mutation-safe-resume-postgresql-validation.yml"
F6_04_PROOF_RUN = "34629433456"
F6_04_PROOF_JOB = "103362376024"
F6_04_PROOF_SHA = "da0d94c74cd02b3dbc658ab9713ddf18bdd6f7ce"
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
    require(controlled_5xx_gaps == 9, "f6_controlled_5xx_remaining_gaps_9")

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

    require(receipt["assessments"]["timeout_temporary_failure"] == "covered", "f6_02_receipt_temporary_failure_covered")
    require(receipt["assessments"]["safe_resume"] == "covered", "f6_02_receipt_safe_resume_covered")
    require(
        "frontend/tests/e2e/f6-02-receipt-temporary-retry.fullstack.spec.js" in receipt_evidence,
        "f6_02_receipt_browser_authority_registered",
    )
    require(F6_02_WORKFLOW in receipt_evidence, "f6_02_receipt_workflow_registered")
    receipt_timeout_note = receipt.get("notes", {}).get("timeout_temporary_failure", "")
    require(F6_02_PROOF_RUN in receipt_timeout_note, "f6_02_receipt_proof_run_registered")
    require(F6_02_PROOF_JOB in receipt_timeout_note, "f6_02_receipt_proof_job_registered")
    require(F6_02_PROOF_SHA in receipt_timeout_note, "f6_02_receipt_candidate_registered")

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

    require(kassa["assessments"]["timeout_temporary_failure"] == "covered", "f6_02_kassa_temporary_failure_covered")
    require(kassa["assessments"]["safe_resume"] == "covered", "f6_02_kassa_safe_resume_covered")
    require(
        "frontend/tests/e2e/f6-02-kassa-temporary-retry.fullstack.spec.js" in kassa_evidence,
        "f6_02_kassa_browser_authority_registered",
    )
    require(F6_02_WORKFLOW in kassa_evidence, "f6_02_kassa_workflow_registered")
    kassa_timeout_note = kassa.get("notes", {}).get("timeout_temporary_failure", "")
    require(F6_02_PROOF_RUN in kassa_timeout_note, "f6_02_kassa_proof_run_registered")
    require(F6_02_PROOF_JOB in kassa_timeout_note, "f6_02_kassa_proof_job_registered")
    require(F6_02_PROOF_SHA in kassa_timeout_note, "f6_02_kassa_candidate_registered")

    unpacking = next(row for row in scenarios if row["id"] == "P0-UNPACKING")
    require(unpacking["assessments"]["controlled_5xx"] == "covered", "f6_unpacking_controlled_5xx_covered")
    require(unpacking["assessments"]["standard_user_feedback"] == "covered", "f6_unpacking_standard_feedback_covered")
    require(unpacking["assessments"]["db_consistency_after_error"] == "covered", "f6_unpacking_db_consistency_after_error_covered")
    unpacking_evidence = set(unpacking.get("evidence") or [])
    require(
        "backend/tests/f6_unpacking_controlled_5xx_verify.py" in unpacking_evidence,
        "f6_unpacking_postgresql_verifier_registered",
    )
    require(
        "frontend/tests/e2e/f6-unpacking-controlled-5xx.fullstack.spec.js" in unpacking_evidence,
        "f6_unpacking_browser_authority_registered",
    )
    require(
        ".github/workflows/f6-failure-recovery-gap-audit-validation.yml" in unpacking_evidence,
        "f6_unpacking_postgresql_workflow_registered",
    )

    require(unpacking["assessments"]["timeout_temporary_failure"] == "covered", "f6_02_unpacking_temporary_failure_covered")
    require(unpacking["assessments"]["safe_resume"] == "covered", "f6_02_unpacking_safe_resume_covered")
    require(
        "frontend/tests/e2e/f6-02-unpacking-temporary-retry.fullstack.spec.js" in unpacking_evidence,
        "f6_02_unpacking_browser_authority_registered",
    )
    require(F6_02_WORKFLOW in unpacking_evidence, "f6_02_unpacking_workflow_registered")
    unpacking_timeout_note = unpacking.get("notes", {}).get("timeout_temporary_failure", "")
    require(F6_02_PROOF_RUN in unpacking_timeout_note, "f6_02_unpacking_proof_run_registered")
    require(F6_02_PROOF_JOB in unpacking_timeout_note, "f6_02_unpacking_proof_job_registered")
    require(F6_02_PROOF_SHA in unpacking_timeout_note, "f6_02_unpacking_candidate_registered")

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

    f6_01_scope = {"P0-RECEIPT-INVENTORY-ALMOSTOUT", "P0-KASSA-REVIEW", "P0-UNPACKING", "P0-INVENTORY"}
    f6_01_rows = [row for row in scenarios if row["id"] in f6_01_scope]
    require(len(f6_01_rows) == 4, "f6_01_exact_four_scope_scenarios")
    require(
        all(
            row["assessments"]["controlled_5xx"] == "covered"
            and row["assessments"]["standard_user_feedback"] == "covered"
            and row["assessments"]["db_consistency_after_error"] == "covered"
            for row in f6_01_rows
        ),
        "f6_01_scope_fully_covered",
    )

    f6_02_scope = {"P0-RECEIPT-INVENTORY-ALMOSTOUT", "P0-KASSA-REVIEW", "P0-UNPACKING"}
    f6_02_rows = [row for row in scenarios if row["id"] in f6_02_scope]
    require(len(f6_02_rows) == 3, "f6_02_exact_three_scope_scenarios")
    require(
        all(
            row["assessments"]["timeout_temporary_failure"] == "covered"
            and row["assessments"]["safe_resume"] == "covered"
            for row in f6_02_rows
        ),
        "f6_02_scope_fully_covered",
    )
    require((ROOT / F6_02_WORKFLOW).exists(), "f6_02_shared_postgresql_workflow_registered")

    f6_03_scope = {"P0-RECEIPT-INVENTORY-ALMOSTOUT", "P0-KASSA-REVIEW"}
    f6_03_rows = [row for row in scenarios if row["id"] in f6_03_scope]
    require(len(f6_03_rows) == 2, "f6_03_exact_two_scope_scenarios")
    require(
        all(row["assessments"]["invalid_import"] == "covered" for row in f6_03_rows),
        "f6_03_invalid_import_scope_fully_covered",
    )
    require((ROOT / F6_03_SPEC).exists(), "f6_03_browser_authority_registered")
    require((ROOT / F6_03_WORKFLOW).exists(), "f6_03_postgresql_workflow_registered")
    for row in f6_03_rows:
        evidence = set(row.get("evidence") or [])
        require(F6_03_SPEC in evidence, f"f6_03_{row['id']}_spec_registered")
        require(F6_03_WORKFLOW in evidence, f"f6_03_{row['id']}_workflow_registered")
        proof_note = row.get("notes", {}).get("invalid_import", "")
        require(F6_03_PROOF_RUN in proof_note, f"f6_03_{row['id']}_proof_run_registered")
        require(F6_03_PROOF_JOB in proof_note, f"f6_03_{row['id']}_proof_job_registered")
        require(F6_03_PROOF_SHA in proof_note, f"f6_03_{row['id']}_candidate_registered")

    f6_04_scope = {"P0-ONBOARDING", "P0-SETTINGS-PROJECTION", "P0-INVENTORY"}
    f6_04_rows = [row for row in scenarios if row["id"] in f6_04_scope]
    require(len(f6_04_rows) == 3, "f6_04_exact_three_scope_scenarios")
    require(
        all(
            row["assessments"]["interrupted_flow"] == "covered"
            and row["assessments"]["safe_resume"] == "covered"
            for row in f6_04_rows
        ),
        "f6_04_interrupted_mutation_scope_fully_covered",
    )
    require((ROOT / F6_04_SPEC).exists(), "f6_04_browser_authority_registered")
    require((ROOT / F6_04_WORKFLOW).exists(), "f6_04_postgresql_workflow_registered")
    for row in f6_04_rows:
        evidence = set(row.get("evidence") or [])
        require(F6_04_SPEC in evidence, f"f6_04_{row['id']}_spec_registered")
        require(F6_04_WORKFLOW in evidence, f"f6_04_{row['id']}_workflow_registered")
        interrupted_note = row.get("notes", {}).get("interrupted_flow", "")
        safe_resume_note = row.get("notes", {}).get("safe_resume", "")
        for marker, value in (("proof_run", F6_04_PROOF_RUN), ("proof_job", F6_04_PROOF_JOB), ("candidate", F6_04_PROOF_SHA)):
            require(value in interrupted_note, f"f6_04_{row['id']}_interrupted_{marker}_registered")
            require(value in safe_resume_note, f"f6_04_{row['id']}_resume_{marker}_registered")

    account = next(row for row in scenarios if row["id"] == "P0-ACCOUNT-SESSION")
    require(account["assessments"]["auth_401_403"] == "covered", "f6_reuses_account_stale_session_401")

    print("F6_FAILURE_RECOVERY_GAP_AUDIT_GREEN")


if __name__ == "__main__":
    main()

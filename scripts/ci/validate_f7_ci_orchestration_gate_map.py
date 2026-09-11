#!/usr/bin/env python3
"""Fail-closed validator for the F7-01 CI orchestration audit gate map."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "quality/ci/f7_ci_orchestration_gate_map.json"
EXPECTED_MAIN_SHA = "d3c3cbb507c50e8920a6dd0b684d9d825537c1a1"
EXPECTED_GATES = [
    "pr_fast_regression",
    "full_regression",
    "deep_nightly",
    "release_acceptance",
]
EXPECTED_STATUS = {
    "pr_fast_regression": "partial",
    "full_regression": "partial",
    "deep_nightly": "gap",
    "release_acceptance": "partial",
}
EXPECTED_SHARED_CLUSTERS = {
    "TP-CI-02": ("quality/ci/tp_ci_02_kassa_shared_stack_paths.json", 2, 0, 2),
    "TP-CI-03": ("quality/ci/tp_ci_03_account_authorization_shared_stack_paths.json", 2, 2, 0),
    "TP-CI-04": ("quality/ci/tp_ci_04_inventory_shared_stack_paths.json", 3, 3, 0),
    "TP-CI-05": ("quality/ci/tp_ci_05_receipt_shared_stack_paths.json", 5, 5, 0),
    "TP-CI-07": ("quality/ci/tp_ci_07_core_p0_shared_stack_paths.json", 4, 4, 0),
}
TP_WORKFLOWS = [
    ".github/workflows/tp-ci-02-kassa-shared-stack-postgresql-validation.yml",
    ".github/workflows/tp-ci-03-account-authorization-shared-stack-postgresql-validation.yml",
    ".github/workflows/tp-ci-04-inventory-shared-stack-postgresql-validation.yml",
    ".github/workflows/tp-ci-05-receipt-shared-stack-postgresql-validation.yml",
    ".github/workflows/tp-ci-07-core-p0-shared-stack-postgresql-validation.yml",
]
MANUAL_FALLBACK_WORKFLOWS = [
    ".github/workflows/p0-account-session-fullstack-postgresql-validation.yml",
    ".github/workflows/p0-authorization-isolation-fullstack-postgresql-validation.yml",
    ".github/workflows/p0-inventory-correction-fullstack-postgresql-validation.yml",
    ".github/workflows/p0-almost-out-recalculation-fullstack-postgresql-validation.yml",
    ".github/workflows/f6-inventory-controlled-5xx-postgresql-validation.yml",
    ".github/workflows/p0-receipt-inventory-fullstack-postgresql-validation.yml",
    ".github/workflows/p0-receipt-inventory-locations-off-fullstack-postgresql-validation.yml",
    ".github/workflows/p0-receipt-inventory-idempotency-fullstack-postgresql-validation.yml",
    ".github/workflows/p0-receipt-nonphysical-fullstack-postgresql-validation.yml",
    ".github/workflows/f6-receipt-controlled-5xx-postgresql-validation.yml",
    ".github/workflows/p0-onboarding-fullstack-postgresql-validation.yml",
    ".github/workflows/p0-article-identity-history-fullstack-postgresql-validation.yml",
    ".github/workflows/p0-platform-authority-fullstack-postgresql-validation.yml",
    ".github/workflows/p0-unpacking-fullstack-postgresql-validation.yml",
]
STALE_FALLBACK_REFERENCES = [
    ".github/workflows/p0-kassa-review-fullstack-postgresql-validation.yml",
    ".github/workflows/f6-kassa-review-controlled-5xx-postgresql-validation.yml",
]


def fail(message: str) -> None:
    raise SystemExit(f"FAIL F7-01: {message}")


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def read_text(path: str) -> str:
    target = ROOT / path
    require(target.is_file(), f"missing mapped file: {path}")
    return target.read_text(encoding="utf-8")


def main() -> int:
    require(AUDIT.is_file(), "audit map missing")
    try:
        data = json.loads(AUDIT.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"audit map is invalid JSON: {type(exc).__name__}")

    require(data.get("schema_version") == 1, "schema_version must be 1")
    require(data.get("audit_id") == "F7-01", "audit_id must be F7-01")
    require(data.get("audited_main_sha") == EXPECTED_MAIN_SHA, "audited main SHA drift")
    require(data.get("gate_order") == EXPECTED_GATES, "roadmap gate order drift")

    gates = data.get("gates")
    require(isinstance(gates, dict), "gates must be an object")
    require(list(gates) == EXPECTED_GATES, "gate taxonomy/order mismatch")

    all_residual_ids: set[str] = set()
    mapped_workflows: set[str] = set()
    for gate_name in EXPECTED_GATES:
        gate = gates[gate_name]
        require(gate.get("status") == EXPECTED_STATUS[gate_name], f"unexpected {gate_name} status")
        workflows = gate.get("primary_workflows")
        require(isinstance(workflows, list) and workflows, f"{gate_name} has no primary workflows")
        for workflow in workflows:
            require(isinstance(workflow, str) and workflow.startswith(".github/workflows/"), f"invalid workflow path in {gate_name}")
            read_text(workflow)
            mapped_workflows.add(workflow)

        residuals = gate.get("residuals")
        require(isinstance(residuals, list) and residuals, f"{gate_name} must expose residuals")
        for residual in residuals:
            rid = residual.get("id")
            require(isinstance(rid, str) and rid.startswith("F7-"), f"invalid residual id in {gate_name}")
            require(rid not in all_residual_ids, f"duplicate residual id: {rid}")
            all_residual_ids.add(rid)
            require(residual.get("status") == "open", f"F7-01 may only record open residuals: {rid}")
            require(bool(str(residual.get("description") or "").strip()), f"missing residual description: {rid}")

    pr_fast = gates["pr_fast_regression"]
    clusters = pr_fast.get("shared_stack_clusters")
    require(isinstance(clusters, list) and len(clusters) == 5, "expected five shared-stack clusters")
    seen_clusters: set[str] = set()
    authority_count = 0
    fallback_reference_count = 0
    manual_count = 0
    stale_count = 0
    for cluster in clusters:
        cid = cluster.get("id")
        require(cid in EXPECTED_SHARED_CLUSTERS, f"unexpected shared cluster: {cid}")
        require(cid not in seen_clusters, f"duplicate shared cluster: {cid}")
        seen_clusters.add(cid)
        expected_manifest, expected_authorities, expected_manual, expected_stale = EXPECTED_SHARED_CLUSTERS[cid]
        require(cluster.get("manifest") == expected_manifest, f"manifest drift for {cid}")
        read_text(expected_manifest)
        authorities = cluster.get("authorities")
        require(isinstance(authorities, list) and len(authorities) == expected_authorities, f"authority count drift for {cid}")
        require(cluster.get("fallback_references") == expected_authorities, f"fallback reference count drift for {cid}")
        require(cluster.get("existing_manual_fallbacks") == expected_manual, f"manual fallback count drift for {cid}")
        require(cluster.get("stale_fallback_references") == expected_stale, f"stale fallback count drift for {cid}")
        authority_count += len(authorities)
        fallback_reference_count += expected_authorities
        manual_count += expected_manual
        stale_count += expected_stale

    require(seen_clusters == set(EXPECTED_SHARED_CLUSTERS), "shared cluster coverage incomplete")
    require(authority_count == 16, "expected sixteen authorities across shared clusters")
    require(fallback_reference_count == 16, "expected sixteen fallback references")
    require(manual_count == 14, "expected fourteen existing manual fallback workflows")
    require(stale_count == 2, "expected two stale fallback references")

    governance = pr_fast.get("fallback_governance")
    require(isinstance(governance, dict), "fallback_governance missing")
    require(governance.get("manual_only_workflows") == MANUAL_FALLBACK_WORKFLOWS, "manual fallback workflow inventory drift")
    require(governance.get("stale_references") == STALE_FALLBACK_REFERENCES, "stale fallback reference inventory drift")
    require(governance.get("duplicate_pr_fallbacks") == [], "duplicate automatic PR fallbacks must be empty")

    for workflow in MANUAL_FALLBACK_WORKFLOWS:
        text = read_text(workflow)
        require("\n  workflow_dispatch:\n" in text, f"manual fallback lost workflow_dispatch: {workflow}")
        require("\n  pull_request:" not in text, f"manual fallback regained pull_request trigger: {workflow}")

    tp_ci_02_text = read_text(".github/workflows/tp-ci-02-kassa-shared-stack-postgresql-validation.yml")
    for stale in STALE_FALLBACK_REFERENCES:
        require(not (ROOT / stale).exists(), f"stale reference unexpectedly exists: {stale}")
        require(stale in tp_ci_02_text, f"stale TP-CI-02 reference no longer present; refresh F7-01 audit: {stale}")

    cross = data.get("cross_cutting")
    require(isinstance(cross, dict), "cross_cutting missing")
    require(cross.get("delta_planner") == "scripts/ci/shared_fullstack_plan.py", "delta planner mapping drift")
    read_text("scripts/ci/shared_fullstack_plan.py")
    require(cross.get("shared_stack_manifest_count") == 5, "shared stack manifest count drift")
    require(cross.get("shared_stack_authority_count") == 16, "shared stack authority count drift")
    require(cross.get("fallback_reference_count") == 16, "fallback reference count drift")
    require(cross.get("existing_manual_fallback_workflow_count") == 14, "existing manual fallback count drift")
    require(cross.get("stale_fallback_reference_count") == 2, "stale fallback reference count drift")
    require(cross.get("duplicate_pr_fallback_workflow_count") == 0, "duplicate PR fallback count drift")

    for workflow in TP_WORKFLOWS:
        text = read_text(workflow)
        require("pull_request:" in text, f"{workflow} lost pull_request trigger")
        require("workflow_dispatch:" in text, f"{workflow} lost manual fallback")
        require("github.event.pull_request.head.sha || github.sha" in text, f"{workflow} lost exact candidate checkout")
        require("scripts/ci/shared_fullstack_plan.py" in text, f"{workflow} lost shared delta planner")

    full_text = read_text(".github/workflows/pr253-full-frontend-regression.yml")
    require("github.event.pull_request.head.sha || github.sha" in full_text, "full frontend regression lost exact candidate checkout")
    release_text = read_text(".github/workflows/pr253-v0112109-release-package.yml")
    require("PRODUCT_SHA: ${{ github.event.pull_request.head.sha || github.sha }}" in release_text, "release package lost PRODUCT_SHA candidate identity")

    exit_state = data.get("f7_01_exit")
    require(isinstance(exit_state, dict), "f7_01_exit missing")
    require(exit_state.get("gate_taxonomy_recorded") is True, "gate taxonomy not recorded")
    require(exit_state.get("existing_shared_runners_mapped") is True, "shared runners not mapped")
    require(exit_state.get("fallback_governance_audited") is True, "fallback governance not audited")
    require(exit_state.get("residual_backlog_explicit") is True, "residual backlog not explicit")
    require(exit_state.get("behavior_changed") is False, "F7-01 must remain audit-only")
    require(exit_state.get("next_slice") == "F7-02", "next slice must be F7-02")

    print("PASS f7_01_gate_taxonomy_complete")
    print("PASS f7_01_existing_shared_runners_mapped")
    print("PASS f7_01_candidate_identity_contracts_present")
    print("PASS f7_01_fallback_governance_audited")
    print(f"PASS f7_01_residual_backlog_explicit count={len(all_residual_ids)}")
    print(f"F7_01_MAPPED_WORKFLOWS={len(mapped_workflows)}")
    print("F7_01_SHARED_CLUSTERS=5")
    print("F7_01_SHARED_AUTHORITIES=16")
    print("F7_01_FALLBACK_REFERENCES=16")
    print("F7_01_MANUAL_FALLBACKS=14")
    print("F7_01_STALE_FALLBACK_REFERENCES=2")
    print("F7_01_DUPLICATE_PR_FALLBACKS=0")
    print("F7_01_CI_ORCHESTRATION_AUDIT_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

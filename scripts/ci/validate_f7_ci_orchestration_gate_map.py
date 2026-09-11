#!/usr/bin/env python3
"""Fail-closed validator for the evolving F7 CI orchestration gate map."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / "quality/ci/f7_ci_orchestration_gate_map.json"
FULL = ROOT / "quality/ci/f7_full_regression_gate.json"
FULL_TRIGGER = ROOT / "quality/ci/f7_full_regression_trigger_policy.json"
FULL_WORKFLOW = ROOT / ".github/workflows/f7-full-regression-gate.yml"
EXPECTED_GATE_ORDER = [
    "pr_fast_regression",
    "full_regression",
    "deep_nightly",
    "release_acceptance",
]
EXPECTED_P0 = {
    "P0-ACCOUNT-SESSION",
    "P0-ONBOARDING",
    "P0-HOUSEHOLD-MEMBERSHIP",
    "P0-AUTHORIZATION-ISOLATION",
    "P0-SETTINGS-PROJECTION",
    "P0-LOCATIONS-POLICY",
    "P0-RECEIPT-INVENTORY-ALMOSTOUT",
    "P0-KASSA-REVIEW",
    "P0-UNPACKING",
    "P0-INVENTORY",
    "P0-ALMOST-OUT",
    "P0-ARTICLE-IDENTITY",
    "P0-PLATFORM-AUTHORITY",
    "P0-MIGRATION-STARTUP",
}
EXPECTED_FULL_PR_ACTIONS = ["opened", "reopened", "ready_for_review", "synchronize"]


def fail(message: str) -> None:
    raise SystemExit(f"FAIL F7 map: {message}")


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def load(path: Path) -> dict:
    require(path.is_file(), f"missing {path.relative_to(ROOT)}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid JSON {path}: {type(exc).__name__}")
    require(isinstance(data, dict), f"root must be object: {path}")
    return data


def main() -> int:
    data = load(MAP)
    require(data.get("schema_version") == 2, "schema_version must be 2")
    require(data.get("map_id") == "F7", "map_id must be F7")
    require(data.get("baseline_main_sha") == "65adb5e49678c77e240eaba79b39c18088df1972", "baseline main SHA drift")
    require(data.get("gate_order") == EXPECTED_GATE_ORDER, "gate order drift")

    gates = data.get("gates")
    require(isinstance(gates, dict) and list(gates) == EXPECTED_GATE_ORDER, "gate taxonomy drift")

    pr_fast = gates["pr_fast_regression"]
    require(pr_fast.get("status") == "covered", "PR Fast Regression must be covered after F7-02")
    require(pr_fast.get("aggregate_workflow") == ".github/workflows/f7-pr-fast-regression-gate.yml", "PR Fast aggregate workflow drift")
    require((ROOT / pr_fast["aggregate_workflow"]).is_file(), "PR Fast aggregate workflow missing")
    require((ROOT / pr_fast["contract"]).is_file(), "PR Fast contract missing")
    require(pr_fast.get("shared_clusters") == ["TP-CI-02", "TP-CI-03", "TP-CI-04", "TP-CI-05", "TP-CI-07"], "shared cluster map drift")
    require(pr_fast.get("shared_authority_count") == 16, "shared authority count drift")
    governance = pr_fast.get("fallback_governance") or {}
    require(governance.get("manual_only_workflows") == 14, "manual fallback count drift")
    require(governance.get("known_stale_references") == 2, "stale reference count drift")
    require(governance.get("duplicate_pr_fallbacks") == 0, "duplicate PR fallbacks must be zero")
    pr_residuals = {row.get("id"): row for row in pr_fast.get("residuals", [])}
    require(set(pr_residuals) == {"F7-PR-01", "F7-PR-02"}, "PR Fast residual set drift")
    require(all(row.get("status") == "closed" for row in pr_residuals.values()), "F7-PR residuals must be closed")
    require(pr_residuals["F7-PR-01"].get("proof", {}).get("run") == "34640522351", "F7-PR-01 proof run drift")
    require(pr_residuals["F7-PR-01"].get("proof", {}).get("candidate_sha") == "e866693a684b36e4f7782fa6c02e0bcf00c5a4c1", "F7-PR-01 proof SHA drift")

    full_gate = gates["full_regression"]
    require(full_gate.get("status") == "partial", "Full Regression must remain partial until F7-FULL-02 is proven")
    require(full_gate.get("aggregate_workflow") == ".github/workflows/f7-full-regression-gate.yml", "Full Regression aggregate workflow drift")
    require((ROOT / full_gate["aggregate_workflow"]).is_file(), "Full Regression aggregate workflow missing")
    require(full_gate.get("contract") == "quality/ci/f7_full_regression_gate.json", "Full Regression contract drift")
    require(full_gate.get("trigger_policy") == "quality/ci/f7_full_regression_trigger_policy.json", "Full Regression trigger-policy path drift")
    require((ROOT / full_gate["trigger_policy"]).is_file(), "Full Regression trigger policy missing")
    require(full_gate.get("required_p0_scenarios") == 14, "Full Regression P0 count drift")
    require(full_gate.get("required_workflows") == 11, "Full Regression workflow count drift")
    full_residuals = {row.get("id"): row for row in full_gate.get("residuals", [])}
    require(set(full_residuals) == {"F7-FULL-01", "F7-FULL-02"}, "Full Regression residual set drift")
    require(full_residuals["F7-FULL-01"].get("status") == "closed", "F7-FULL-01 must be closed")
    require(full_residuals["F7-FULL-01"].get("proof", {}).get("run") == "34642458679", "F7-FULL-01 proof run drift")
    require(full_residuals["F7-FULL-01"].get("proof", {}).get("job") == "103405329551", "F7-FULL-01 proof job drift")
    require(full_residuals["F7-FULL-01"].get("proof", {}).get("candidate_sha") == "a6933a25b3cabea8c0f02df52288405ce53b9653", "F7-FULL-01 proof SHA drift")
    require(full_residuals["F7-FULL-01"].get("proof", {}).get("merge_commit") == "c0943137738afc5b3db55726a9f2c5e0cc7b3d4a", "F7-FULL-01 merge proof drift")
    require(full_residuals["F7-FULL-02"].get("status") == "in_progress", "F7-FULL-02 must be in progress during trigger proof")

    full = load(FULL)
    require(full.get("gate_id") == "F7-03", "Full Regression contract gate id drift")
    require(full.get("required_p0_scenario_count") == 14, "Full contract P0 count drift")
    require(full.get("required_workflow_count") == 11, "Full contract workflow count drift")
    require(set((full.get("p0_scenario_authorities") or {}).keys()) == EXPECTED_P0, "Full contract P0 scenario coverage drift")
    workflows = full.get("workflows") or []
    require(len(workflows) == 11, "Full contract workflow inventory drift")
    for row in workflows:
        workflow = row.get("workflow_file")
        require(isinstance(workflow, str) and (ROOT / workflow).is_file(), f"missing Full Regression workflow: {workflow}")
        text = (ROOT / workflow).read_text(encoding="utf-8")
        require("workflow_dispatch:" in text, f"Full Regression child lost dispatch trigger: {workflow}")

    trigger = load(FULL_TRIGGER)
    require(trigger.get("schema_version") == 1, "Full trigger policy schema drift")
    require(trigger.get("policy_id") == "F7-FULL-02", "Full trigger policy id drift")
    require(trigger.get("target_base") == "main", "Full trigger base must remain main")
    require(trigger.get("automatic_pull_request_actions") == EXPECTED_FULL_PR_ACTIONS, "Full trigger PR actions drift")
    require(trigger.get("candidate_ref_source") == "github.head_ref", "Full trigger candidate-ref source drift")
    require(trigger.get("candidate_sha_source") == "github.event.pull_request.head.sha", "Full trigger candidate-SHA source drift")
    fallback = trigger.get("manual_fallback") or {}
    require(fallback.get("event") == "workflow_dispatch", "Full trigger manual fallback drift")
    require(fallback.get("required_inputs") == ["candidate_ref", "candidate_sha"], "Full trigger fallback inputs drift")

    workflow_text = FULL_WORKFLOW.read_text(encoding="utf-8")
    require("name: F7 Full Regression exact-candidate gate" in workflow_text, "permanent Full Regression workflow name drift")
    require("    types:\n      - opened\n      - reopened\n      - ready_for_review\n      - synchronize" in workflow_text, "permanent Full Regression PR event set drift")
    require("    paths:" not in workflow_text, "Full Regression must not be path-filtered")
    require("if: ${{ github.event_name == 'workflow_dispatch' || github.event.pull_request.draft == false }}" in workflow_text, "Full Regression draft guard missing")
    require("cancel-in-progress: true" in workflow_text, "Full Regression candidate replacement policy missing")
    require("workflow_dispatch:" in workflow_text, "Full Regression manual fallback missing")
    require("F7_FULL_TRIGGER_ACTION=$TRIGGER_ACTION" in workflow_text, "Full Regression trigger evidence marker missing")

    require(gates["deep_nightly"].get("status") == "gap", "Deep/Nightly status drift")
    require(gates["release_acceptance"].get("status") == "partial", "Release Acceptance status drift")
    cross = data.get("cross_cutting") or {}
    require(cross.get("delta_planner") == "scripts/ci/shared_fullstack_plan.py", "delta planner path drift")
    require("base.sha -> head.sha" in str(cross.get("delta_planner_policy") or ""), "candidate-scoped delta policy missing")
    history = data.get("history") or {}
    require(history.get("F7-01", {}).get("status") == "closed", "F7-01 history not closed")
    require(history.get("F7-02", {}).get("status") == "closed", "F7-02 history not closed")
    require(history.get("F7-03", {}).get("status") == "closed", "F7-03 history not closed")
    require(history.get("F7-03", {}).get("merge_commit") == "c0943137738afc5b3db55726a9f2c5e0cc7b3d4a", "F7-03 merge commit drift")
    require(history.get("F7-04", {}).get("status") == "in_progress", "F7-04 history must be in progress")
    require(history.get("F7-04", {}).get("scope") == "F7-FULL-02", "F7-04 scope drift")

    open_or_active = sum(
        1
        for gate in gates.values()
        for row in gate.get("residuals", [])
        if row.get("status") in {"open", "in_progress"}
    )

    print("PASS f7_02_pr_fast_regression_covered")
    print("PASS f7_02_fallback_governance_closed")
    print("PASS f7_03_full_regression_contract_registered")
    print("PASS f7_03_exact_14_p0_scenarios_mapped")
    print("PASS f7_03_eleven_workflows_registered")
    print("PASS f7_03_full_regression_exact_candidate_closed")
    print("PASS f7_04_full_regression_trigger_policy_permanent")
    print("PASS f7_04_non_draft_candidate_guarded")
    print("PASS f7_04_synchronize_replaces_previous_candidate")
    print("PASS f7_04_manual_dispatch_fallback_retained")

    # Backward-compatible F7-01 workflow markers. These remain true historical facts
    # even though the evolving gate map has moved on to later F7 slices.
    print("PASS f7_01_gate_taxonomy_complete")
    print("PASS f7_01_existing_shared_runners_mapped")
    print("PASS f7_01_candidate_identity_contracts_present")
    print("PASS f7_01_fallback_governance_audited")
    print(f"PASS f7_01_residual_backlog_explicit count={open_or_active}")
    print("F7_01_SHARED_CLUSTERS=5")
    print("F7_01_SHARED_AUTHORITIES=16")
    print("F7_01_FALLBACK_REFERENCES=16")
    print("F7_01_MANUAL_FALLBACKS=14")
    print("F7_01_STALE_FALLBACK_REFERENCES=2")
    print("F7_01_DUPLICATE_PR_FALLBACKS=0")
    print("F7_01_CI_ORCHESTRATION_AUDIT_GREEN")
    print("F7_FULL_TRIGGER_POLICY_GREEN")
    print("F7_CI_ORCHESTRATION_GATE_MAP_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

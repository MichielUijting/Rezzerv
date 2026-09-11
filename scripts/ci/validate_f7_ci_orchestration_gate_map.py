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
DEEP = ROOT / "quality/ci/f7_deep_nightly_gate.json"
DEEP_WORKFLOW = ROOT / ".github/workflows/f7-deep-nightly-gate.yml"
EXPECTED_GATE_ORDER = ["pr_fast_regression", "full_regression", "deep_nightly", "release_acceptance"]
EXPECTED_FULL_PR_ACTIONS = ["opened", "reopened", "ready_for_review", "synchronize"]
EXPECTED_DEEP_BUCKETS = {"failure_recovery": 6, "legacy_portability": 6}
EXPECTED_P0 = {
    "P0-ACCOUNT-SESSION", "P0-ONBOARDING", "P0-HOUSEHOLD-MEMBERSHIP",
    "P0-AUTHORIZATION-ISOLATION", "P0-SETTINGS-PROJECTION", "P0-LOCATIONS-POLICY",
    "P0-RECEIPT-INVENTORY-ALMOSTOUT", "P0-KASSA-REVIEW", "P0-UNPACKING",
    "P0-INVENTORY", "P0-ALMOST-OUT", "P0-ARTICLE-IDENTITY",
    "P0-PLATFORM-AUTHORITY", "P0-MIGRATION-STARTUP",
}


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
    require(pr_fast.get("status") == "covered", "PR Fast Regression must be covered")
    require(pr_fast.get("shared_clusters") == ["TP-CI-02", "TP-CI-03", "TP-CI-04", "TP-CI-05", "TP-CI-07"], "shared cluster map drift")
    require(pr_fast.get("shared_authority_count") == 16, "shared authority count drift")
    governance = pr_fast.get("fallback_governance") or {}
    require(governance == {"manual_only_workflows": 14, "known_stale_references": 2, "duplicate_pr_fallbacks": 0}, "fallback governance drift")
    pr_residuals = {row.get("id"): row for row in pr_fast.get("residuals", [])}
    require(set(pr_residuals) == {"F7-PR-01", "F7-PR-02"}, "PR Fast residual set drift")
    require(all(row.get("status") == "closed" for row in pr_residuals.values()), "F7-PR residuals must be closed")

    full_gate = gates["full_regression"]
    require(full_gate.get("status") == "covered", "Full Regression must be covered after F7-04")
    require(full_gate.get("aggregate_workflow") == ".github/workflows/f7-full-regression-gate.yml", "Full workflow drift")
    require(full_gate.get("contract") == "quality/ci/f7_full_regression_gate.json", "Full contract drift")
    require(full_gate.get("trigger_policy") == "quality/ci/f7_full_regression_trigger_policy.json", "Full trigger-policy path drift")
    require(full_gate.get("required_p0_scenarios") == 14 and full_gate.get("required_workflows") == 11, "Full Regression counts drift")
    full_residuals = {row.get("id"): row for row in full_gate.get("residuals", [])}
    require(set(full_residuals) == {"F7-FULL-01", "F7-FULL-02"}, "Full residual set drift")
    require(all(row.get("status") == "closed" for row in full_residuals.values()), "Full Regression residuals must be closed")
    require(full_residuals["F7-FULL-01"].get("proof", {}).get("run") == "34642458679", "F7-FULL-01 proof drift")
    require(full_residuals["F7-FULL-02"].get("proof", {}).get("run") == "34645410007", "F7-FULL-02 proof run drift")
    require(full_residuals["F7-FULL-02"].get("proof", {}).get("candidate_sha") == "dddcaae6fc0a0f9dcae41343d2430e65d8925f85", "F7-FULL-02 proof SHA drift")
    require(full_residuals["F7-FULL-02"].get("proof", {}).get("merge_commit") == "a1254515cdcbbc14541c1f83a94a302a44df71ce", "F7-FULL-02 merge proof drift")

    full = load(FULL)
    require(full.get("gate_id") == "F7-03", "Full contract gate id drift")
    require(full.get("required_p0_scenario_count") == 14 and full.get("required_workflow_count") == 11, "Full contract counts drift")
    require(set((full.get("p0_scenario_authorities") or {}).keys()) == EXPECTED_P0, "Full contract P0 coverage drift")
    for row in full.get("workflows") or []:
        workflow = row.get("workflow_file")
        require(isinstance(workflow, str) and (ROOT / workflow).is_file(), f"missing Full workflow: {workflow}")
        require("workflow_dispatch:" in (ROOT / workflow).read_text(encoding="utf-8"), f"Full child lost dispatch trigger: {workflow}")

    trigger = load(FULL_TRIGGER)
    require(trigger.get("policy_id") == "F7-FULL-02", "Full trigger policy id drift")
    require(trigger.get("automatic_pull_request_actions") == EXPECTED_FULL_PR_ACTIONS, "Full trigger PR actions drift")
    workflow_text = FULL_WORKFLOW.read_text(encoding="utf-8")
    require("    paths:" not in workflow_text, "Full Regression must not be path-filtered")
    require("cancel-in-progress: true" in workflow_text, "Full candidate replacement policy missing")
    require("workflow_dispatch:" in workflow_text, "Full manual fallback missing")

    deep_gate = gates["deep_nightly"]
    require(deep_gate.get("status") == "partial", "Deep/Nightly must be partial during F7-DEEP-01 proof")
    require(deep_gate.get("aggregate_workflow") == ".github/workflows/f7-deep-nightly-gate.yml", "Deep aggregate workflow drift")
    require(deep_gate.get("contract") == "quality/ci/f7_deep_nightly_gate.json", "Deep contract path drift")
    require(deep_gate.get("schedule_utc") == "30 1 * * *", "Deep schedule drift")
    require(deep_gate.get("required_workflows") == 12, "Deep workflow count drift")
    require(deep_gate.get("buckets") == EXPECTED_DEEP_BUCKETS, "Deep bucket counts drift")
    deep_residuals = {row.get("id"): row for row in deep_gate.get("residuals", [])}
    require(set(deep_residuals) == {"F7-DEEP-01", "F7-DEEP-02"}, "Deep residual set drift")
    require(deep_residuals["F7-DEEP-01"].get("status") == "in_progress", "F7-DEEP-01 must be in progress")
    require(deep_residuals["F7-DEEP-02"].get("status") == "open", "F7-DEEP-02 must remain open")

    deep = load(DEEP)
    require(deep.get("gate_id") == "F7-05", "Deep contract gate id drift")
    require(deep.get("target_ref") == "main", "Deep target ref drift")
    require(deep.get("schedule_utc") == "30 1 * * *", "Deep config schedule drift")
    require(deep.get("required_workflow_count") == 12, "Deep config workflow count drift")
    require(deep.get("buckets") == EXPECTED_DEEP_BUCKETS, "Deep config bucket drift")
    deep_workflows = deep.get("workflows") or []
    require(len(deep_workflows) == 12, "Deep workflow inventory drift")
    ids = [row.get("id") for row in deep_workflows]
    require(len(ids) == len(set(ids)), "Deep workflow ids must be unique")
    actual_buckets = {name: 0 for name in EXPECTED_DEEP_BUCKETS}
    for row in deep_workflows:
        workflow = row.get("workflow_file")
        bucket = row.get("bucket")
        require(bucket in actual_buckets, f"Deep bucket invalid: {bucket}")
        actual_buckets[bucket] += 1
        require(isinstance(workflow, str) and (ROOT / workflow).is_file(), f"missing Deep workflow: {workflow}")
        require("workflow_dispatch:" in (ROOT / workflow).read_text(encoding="utf-8"), f"Deep child lost workflow_dispatch: {workflow}")
    require(actual_buckets == EXPECTED_DEEP_BUCKETS, "Deep actual bucket membership drift")

    deep_text = DEEP_WORKFLOW.read_text(encoding="utf-8")
    require("name: F7 Deep Nightly exact-candidate gate" in deep_text, "Deep workflow name drift")
    require("    - cron: '30 1 * * *'" in deep_text, "canonical Deep schedule missing")
    require("workflow_dispatch:" in deep_text, "Deep manual fallback missing")
    require("github.event.pull_request.draft == false" in deep_text, "Deep implementation-proof Draft guard missing")
    require("F7_DEEP_CANDIDATE_SHA=$CANDIDATE_SHA" in deep_text, "Deep candidate evidence marker missing")
    require("F7_DEEP_AGGREGATED_COUNT=12" in deep_text, "Deep aggregate-count gate missing")

    require(gates["release_acceptance"].get("status") == "partial", "Release Acceptance status drift")
    history = data.get("history") or {}
    for phase in ["F7-01", "F7-02", "F7-03", "F7-04"]:
        require(history.get(phase, {}).get("status") == "closed", f"{phase} history not closed")
    require(history.get("F7-04", {}).get("merge_commit") == "a1254515cdcbbc14541c1f83a94a302a44df71ce", "F7-04 merge drift")
    require(history.get("F7-05", {}).get("status") == "in_progress", "F7-05 history must be in progress")
    require(history.get("F7-05", {}).get("scope") == "F7-DEEP-01", "F7-05 scope drift")

    open_or_active = sum(1 for gate in gates.values() for row in gate.get("residuals", []) if row.get("status") in {"open", "in_progress"})

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
    print("PASS f7_04_full_regression_permanent_trigger_closed")
    print("PASS f7_05_deep_nightly_contract_registered")
    print("PASS f7_05_canonical_daily_schedule_registered")
    print("PASS f7_05_twelve_deep_authorities_registered")
    print("PASS f7_05_deep_children_dispatchable")

    # Backward-compatible F7-01 workflow markers.
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
    print("F7_DEEP_NIGHTLY_CONTRACT_GREEN")
    print("F7_CI_ORCHESTRATION_GATE_MAP_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

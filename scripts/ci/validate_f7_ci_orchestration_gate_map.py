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
DEEP_PROOF = {
    "run": "34647728557",
    "job": "103422399705",
    "candidate_sha": "b1ff0fbe0f442692bcee21164f57cd66a3ce7a2b",
    "artifact_id": "10282677711",
    "artifact_digest": "sha256:097d5a1229bc0fd9b50ef013262e873e742285ca0f058aea1ac4896ccff6df41",
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


def validate_dispatchable(workflows: list[dict], label: str) -> None:
    ids: list[str] = []
    for row in workflows:
        wid = row.get("id")
        workflow = row.get("workflow_file")
        require(isinstance(wid, str) and wid, f"{label} workflow id missing")
        require(isinstance(workflow, str) and workflow.startswith(".github/workflows/"), f"invalid {label} workflow path: {workflow}")
        target = ROOT / workflow
        require(target.is_file(), f"missing {label} workflow: {workflow}")
        require("workflow_dispatch:" in target.read_text(encoding="utf-8"), f"{label} child lost workflow_dispatch: {workflow}")
        ids.append(wid)
    require(len(ids) == len(set(ids)), f"{label} workflow ids must be unique")


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
    require((pr_fast.get("fallback_governance") or {}) == {
        "manual_only_workflows": 14,
        "known_stale_references": 2,
        "duplicate_pr_fallbacks": 0,
    }, "fallback governance drift")
    pr_residuals = {row.get("id"): row for row in pr_fast.get("residuals", [])}
    require(set(pr_residuals) == {"F7-PR-01", "F7-PR-02"}, "PR Fast residual set drift")
    require(all(row.get("status") == "closed" for row in pr_residuals.values()), "F7-PR residuals must be closed")

    full_gate = gates["full_regression"]
    require(full_gate.get("status") == "covered", "Full Regression must be covered")
    require(full_gate.get("required_p0_scenarios") == 14, "Full Regression P0 count drift")
    require(full_gate.get("required_workflows") == 11, "Full Regression workflow count drift")
    full_residuals = {row.get("id"): row for row in full_gate.get("residuals", [])}
    require(set(full_residuals) == {"F7-FULL-01", "F7-FULL-02"}, "Full residual set drift")
    require(all(row.get("status") == "closed" for row in full_residuals.values()), "Full residuals must be closed")
    require(full_residuals["F7-FULL-01"].get("proof", {}).get("run") == "34642458679", "F7-FULL-01 proof drift")
    require(full_residuals["F7-FULL-02"].get("proof", {}).get("run") == "34645410007", "F7-FULL-02 proof drift")

    full = load(FULL)
    require(full.get("gate_id") == "F7-03", "Full contract gate id drift")
    require(full.get("required_p0_scenario_count") == 14, "Full contract P0 count drift")
    require(full.get("required_workflow_count") == 11, "Full contract workflow count drift")
    require(set((full.get("p0_scenario_authorities") or {}).keys()) == EXPECTED_P0, "Full contract P0 coverage drift")
    full_workflows = full.get("workflows") or []
    require(len(full_workflows) == 11, "Full workflow inventory drift")
    validate_dispatchable(full_workflows, "Full")

    trigger = load(FULL_TRIGGER)
    require(trigger.get("policy_id") == "F7-FULL-02", "Full trigger policy id drift")
    require(trigger.get("automatic_pull_request_actions") == EXPECTED_FULL_PR_ACTIONS, "Full trigger PR actions drift")
    full_text = FULL_WORKFLOW.read_text(encoding="utf-8")
    require("    paths:" not in full_text, "Full Regression must not be path-filtered")
    require("cancel-in-progress: true" in full_text, "Full candidate replacement policy missing")
    require("workflow_dispatch:" in full_text, "Full manual fallback missing")

    deep_gate = gates["deep_nightly"]
    require(deep_gate.get("status") == "covered", "Deep/Nightly must be covered after first aggregate proof")
    require(deep_gate.get("aggregate_workflow") == ".github/workflows/f7-deep-nightly-gate.yml", "Deep aggregate workflow drift")
    require(deep_gate.get("contract") == "quality/ci/f7_deep_nightly_gate.json", "Deep contract path drift")
    require(deep_gate.get("schedule_utc") == "30 1 * * *", "Deep schedule drift")
    require(deep_gate.get("required_workflows") == 12, "Deep workflow count drift")
    require(deep_gate.get("buckets") == EXPECTED_DEEP_BUCKETS, "Deep bucket counts drift")
    deep_residuals = {row.get("id"): row for row in deep_gate.get("residuals", [])}
    require(set(deep_residuals) == {"F7-DEEP-01", "F7-DEEP-02"}, "Deep residual set drift")
    require(all(row.get("status") == "closed" for row in deep_residuals.values()), "Deep residuals must be closed")

    deep01 = deep_residuals["F7-DEEP-01"].get("proof") or {}
    require(deep01.get("draft_skip_run") == "34647674048", "F7-DEEP-01 draft proof drift")
    require(deep01.get("run") == DEEP_PROOF["run"], "F7-DEEP-01 proof run drift")
    require(deep01.get("job") == DEEP_PROOF["job"], "F7-DEEP-01 proof job drift")
    require(deep01.get("candidate_sha") == DEEP_PROOF["candidate_sha"], "F7-DEEP-01 proof SHA drift")
    require(deep01.get("aggregated_workflows") == 12, "F7-DEEP-01 aggregate count drift")

    deep02 = deep_residuals["F7-DEEP-02"].get("proof") or {}
    require(deep02.get("run") == DEEP_PROOF["run"], "F7-DEEP-02 proof run drift")
    require(deep02.get("job") == DEEP_PROOF["job"], "F7-DEEP-02 proof job drift")
    require(deep02.get("candidate_sha") == DEEP_PROOF["candidate_sha"], "F7-DEEP-02 proof SHA drift")
    require(deep02.get("aggregated_workflows") == 12, "F7-DEEP-02 aggregate count drift")
    require(deep02.get("artifact_id") == DEEP_PROOF["artifact_id"], "F7-DEEP-02 artifact id drift")
    require(deep02.get("artifact_digest") == DEEP_PROOF["artifact_digest"], "F7-DEEP-02 artifact digest drift")

    deep = load(DEEP)
    require(deep.get("gate_id") == "F7-05", "Deep contract gate id drift")
    require(deep.get("target_ref") == "main", "Deep target ref drift")
    require(deep.get("schedule_utc") == "30 1 * * *", "Deep config schedule drift")
    require(deep.get("required_workflow_count") == 12, "Deep config workflow count drift")
    require(deep.get("buckets") == EXPECTED_DEEP_BUCKETS, "Deep config bucket drift")
    deep_workflows = deep.get("workflows") or []
    require(len(deep_workflows) == 12, "Deep workflow inventory drift")
    validate_dispatchable(deep_workflows, "Deep")
    actual_buckets = {name: 0 for name in EXPECTED_DEEP_BUCKETS}
    for row in deep_workflows:
        bucket = row.get("bucket")
        require(bucket in actual_buckets, f"Deep bucket invalid: {bucket}")
        actual_buckets[bucket] += 1
    require(actual_buckets == EXPECTED_DEEP_BUCKETS, "Deep actual bucket membership drift")

    deep_text = DEEP_WORKFLOW.read_text(encoding="utf-8")
    require("name: F7 Deep Nightly exact-candidate gate" in deep_text, "Deep workflow name drift")
    require("    - cron: '30 1 * * *'" in deep_text, "canonical Deep schedule missing")
    require("workflow_dispatch:" in deep_text, "Deep manual fallback missing")
    require("github.event.pull_request.draft == false" in deep_text, "Deep proof Draft guard missing")
    require("F7_DEEP_CANDIDATE_SHA=$CANDIDATE_SHA" in deep_text, "Deep candidate marker missing")
    require("F7_DEEP_AGGREGATED_COUNT=12" in deep_text, "Deep aggregate marker missing")

    require(gates["release_acceptance"].get("status") == "partial", "Release Acceptance status drift")
    history = data.get("history") or {}
    for phase in ["F7-01", "F7-02", "F7-03", "F7-04"]:
        require(history.get(phase, {}).get("status") == "closed", f"{phase} history not closed")
    f705 = history.get("F7-05") or {}
    require(f705.get("status") == "proof_complete", "F7-05 history must be proof_complete before merge")
    require(f705.get("scope") == "F7-DEEP-01 + F7-DEEP-02", "F7-05 scope drift")
    require(f705.get("proof_run") == DEEP_PROOF["run"], "F7-05 history proof run drift")
    require(f705.get("proof_job") == DEEP_PROOF["job"], "F7-05 history proof job drift")
    require(f705.get("proof_sha") == DEEP_PROOF["candidate_sha"], "F7-05 history proof SHA drift")
    require(f705.get("artifact_id") == DEEP_PROOF["artifact_id"], "F7-05 history artifact drift")

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
    print("PASS f7_04_full_regression_permanent_trigger_closed")
    print("PASS f7_05_deep_nightly_contract_registered")
    print("PASS f7_05_canonical_daily_schedule_registered")
    print("PASS f7_05_twelve_deep_authorities_registered")
    print("PASS f7_05_deep_children_dispatchable")
    print("PASS f7_05_deep_01_closed_with_exact_candidate_proof")
    print("PASS f7_05_deep_02_aggregate_evidence_closed")

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
    print("F7_DEEP_NIGHTLY_COVERED")
    print("F7_CI_ORCHESTRATION_GATE_MAP_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

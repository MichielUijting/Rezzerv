#!/usr/bin/env python3
"""Fail-closed validator for the evolving F7 CI orchestration gate map."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / "quality/ci/f7_ci_orchestration_gate_map.json"
FULL = ROOT / "quality/ci/f7_full_regression_gate.json"
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
    require(full_gate.get("status") == "partial", "Full Regression must remain partial during F7-03 proof")
    require(full_gate.get("aggregate_workflow") == ".github/workflows/f7-full-regression-gate.yml", "Full Regression aggregate workflow drift")
    require((ROOT / full_gate["aggregate_workflow"]).is_file(), "Full Regression aggregate workflow missing")
    require(full_gate.get("contract") == "quality/ci/f7_full_regression_gate.json", "Full Regression contract drift")
    require(full_gate.get("required_p0_scenarios") == 14, "Full Regression P0 count drift")
    require(full_gate.get("required_workflows") == 11, "Full Regression workflow count drift")
    full_residuals = {row.get("id"): row for row in full_gate.get("residuals", [])}
    require(set(full_residuals) == {"F7-FULL-01", "F7-FULL-02"}, "Full Regression residual set drift")
    require(full_residuals["F7-FULL-01"].get("status") == "in_progress", "F7-FULL-01 must be in progress")
    require(full_residuals["F7-FULL-02"].get("status") == "open", "F7-FULL-02 must remain open")

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

    require(gates["deep_nightly"].get("status") == "gap", "Deep/Nightly status drift")
    require(gates["release_acceptance"].get("status") == "partial", "Release Acceptance status drift")
    cross = data.get("cross_cutting") or {}
    require(cross.get("delta_planner") == "scripts/ci/shared_fullstack_plan.py", "delta planner path drift")
    require("base.sha -> head.sha" in str(cross.get("delta_planner_policy") or ""), "candidate-scoped delta policy missing")
    history = data.get("history") or {}
    require(history.get("F7-01", {}).get("status") == "closed", "F7-01 history not closed")
    require(history.get("F7-02", {}).get("status") == "closed", "F7-02 history not closed")
    require(history.get("F7-03", {}).get("status") == "in_progress", "F7-03 history must be in progress")

    print("PASS f7_02_pr_fast_regression_covered")
    print("PASS f7_02_fallback_governance_closed")
    print("PASS f7_03_full_regression_contract_registered")
    print("PASS f7_03_exact_14_p0_scenarios_mapped")
    print("PASS f7_03_eleven_workflows_registered")
    print("F7_01_CI_ORCHESTRATION_AUDIT_GREEN")
    print("F7_CI_ORCHESTRATION_GATE_MAP_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLOSURE_PATH = ROOT / "quality/acceptance/p0_residual_closure.json"
MATRIX_PATH = ROOT / "quality/acceptance/functional_acceptance_matrix.json"
REGISTRY_PATH = ROOT / "quality/regression/historical_defect_registry.json"

EXPECTED_P0_IDS = {
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

EXPECTED_CLOSED = {
    "P0-ACCOUNT-SESSION",
    "P0-ONBOARDING",
    "P0-HOUSEHOLD-MEMBERSHIP",
    "P0-AUTHORIZATION-ISOLATION",
    "P0-SETTINGS-PROJECTION",
    "P0-LOCATIONS-POLICY",
    "P0-ARTICLE-IDENTITY",
    "P0-MIGRATION-STARTUP",
}

EXPECTED_RESIDUAL = EXPECTED_P0_IDS - EXPECTED_CLOSED
EXPECTED_F5_IDS = {f"F5-{index:02d}" for index in range(1, 15)}


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def fail(message: str) -> None:
    raise SystemExit(f"FAIL {message}")


def require(condition: bool, marker: str) -> None:
    if not condition:
        fail(marker)
    print(f"PASS {marker}")


def main() -> None:
    closure = load_json(CLOSURE_PATH)
    matrix = load_json(MATRIX_PATH)
    registry = load_json(REGISTRY_PATH)

    require(closure.get("schema_version") == 1, "closure_schema_version")
    require(closure.get("baseline", {}).get("branch") == "main", "closure_baseline_is_main")
    require(closure.get("baseline", {}).get("commit") == "c7ef1a7a04d87fbcd37ea2164a95871e4c26515f", "closure_baseline_matches_f5_14_merge")

    source_matrix = closure.get("sources", {}).get("functional_acceptance_matrix", {})
    source_registry = closure.get("sources", {}).get("historical_defect_registry", {})
    require(source_matrix.get("path") == "quality/acceptance/functional_acceptance_matrix.json", "closure_matrix_source_path")
    require(source_registry.get("path") == "quality/regression/historical_defect_registry.json", "closure_registry_source_path")
    require(source_matrix.get("blob_sha") == git_blob_sha(MATRIX_PATH), "closure_matrix_source_blob_exact")
    require(source_registry.get("blob_sha") == git_blob_sha(REGISTRY_PATH), "closure_registry_source_blob_exact")

    matrix_p0_ids = {
        scenario.get("id")
        for scenario in matrix.get("scenarios", [])
        if scenario.get("priority") == "P0"
    }
    require(matrix_p0_ids == EXPECTED_P0_IDS, "matrix_has_exact_14_p0_scenarios")

    closure_scenarios = closure.get("scenarios", [])
    closure_ids = [scenario.get("id") for scenario in closure_scenarios]
    require(len(closure_ids) == len(set(closure_ids)) == 14, "closure_has_14_unique_p0_scenarios")
    require(set(closure_ids) == EXPECTED_P0_IDS, "closure_covers_every_matrix_p0_scenario")

    statuses = {scenario.get("id"): scenario.get("status") for scenario in closure_scenarios}
    closed = {scenario_id for scenario_id, status in statuses.items() if status == "closed"}
    residual = {scenario_id for scenario_id, status in statuses.items() if status == "residual"}
    require(set(statuses.values()) <= {"closed", "residual"}, "closure_status_values_are_strict")
    require(closed == EXPECTED_CLOSED, "closure_exact_closed_set")
    require(residual == EXPECTED_RESIDUAL, "closure_exact_residual_set")

    summary = closure.get("summary", {})
    require(summary.get("total_p0_scenarios") == 14, "closure_summary_total_14")
    require(summary.get("closed") == len(EXPECTED_CLOSED) == 8, "closure_summary_closed_8")
    require(summary.get("residual") == len(EXPECTED_RESIDUAL) == 6, "closure_summary_residual_6")

    for scenario in closure_scenarios:
        scenario_id = scenario["id"]
        evidence = scenario.get("evidence") or []
        require(bool(evidence), f"{scenario_id}_has_evidence")
        for evidence_path in evidence:
            require((ROOT / evidence_path).exists(), f"{scenario_id}_evidence_exists_{evidence_path}")
        if scenario.get("status") == "residual":
            require(bool(scenario.get("residual_scope")), f"{scenario_id}_residual_scope_explicit")
        else:
            require(not scenario.get("residual_scope"), f"{scenario_id}_closed_has_no_residual_scope")

    account_session = next(row for row in closure_scenarios if row.get("id") == "P0-ACCOUNT-SESSION")
    account_proof = account_session.get("proof", {})
    require(account_proof.get("workflow_run_id") == 34163055850, "account_session_proof_run_exact")
    require(account_proof.get("candidate_sha") == "f6b9b2a0105ff67563dcd6e8400e601a3748014b", "account_session_proof_candidate_exact")
    require(account_proof.get("conclusion") == "success", "account_session_proof_success")

    authorization_isolation = next(row for row in closure_scenarios if row.get("id") == "P0-AUTHORIZATION-ISOLATION")
    authorization_proof = authorization_isolation.get("proof", {})
    require(authorization_proof.get("workflow_run_id") == 34166819340, "authorization_isolation_proof_run_exact")
    require(authorization_proof.get("candidate_sha") == "7cea876321a320c5f059649cd7cae9b689a17f65", "authorization_isolation_proof_candidate_exact")
    require(authorization_proof.get("conclusion") == "success", "authorization_isolation_proof_success")

    registry_rows = {row.get("id"): row for row in registry.get("defect_classes", [])}
    require(EXPECTED_F5_IDS <= set(registry_rows), "registry_contains_f5_01_through_f5_14")
    require(all(registry_rows[f5_id].get("status") == "covered" for f5_id in EXPECTED_F5_IDS), "all_f5_01_through_f5_14_are_covered")
    require(all(registry_rows[f5_id].get("proof", {}).get("conclusion") == "success" for f5_id in EXPECTED_F5_IDS), "all_f5_proofs_are_success")

    residual_text = json.dumps(
        [scenario for scenario in closure_scenarios if scenario.get("status") == "residual"],
        ensure_ascii=False,
    )
    require("F5-15" not in residual_text, "closure_does_not_invent_f5_15")

    print("P0_RESIDUAL_CLOSURE_GREEN")


if __name__ == "__main__":
    main()

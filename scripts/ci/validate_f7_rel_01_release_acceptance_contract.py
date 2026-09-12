#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "quality/ci/f7_release_acceptance_gate.json"
MAP = ROOT / "quality/ci/f7_ci_orchestration_gate_map.json"
WORKFLOW = ROOT / ".github/workflows/f7-release-acceptance-gate.yml"

EXPECTED_PROOF = {
    "run": "34682184495",
    "job": "103523224993",
    "candidate_sha": "84006eef88bb613a2ef9249f446b5692fffb1bb7",
    "artifact_id": "10294407368",
    "artifact_digest": "sha256:783a49a473343d1601b02fcf88715db10d011488353d61b57e3276e0cd7067d3",
}


def require(condition: bool, marker: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL {marker}")
    print(f"PASS {marker}")


def load(path: Path) -> dict:
    require(path.is_file(), f"exists_{path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def valid_sha(value: object) -> bool:
    text = str(value or "")
    return len(text) == 40 and all(ch in "0123456789abcdef" for ch in text)


def valid_numeric_id(value: object) -> bool:
    text = str(value or "")
    return text.isdigit() and int(text) > 0


def valid_sha256_digest(value: object) -> bool:
    text = str(value or "")
    return text.startswith("sha256:") and len(text) == 71 and all(ch in "0123456789abcdef" for ch in text[7:])


def main() -> int:
    contract = load(CONTRACT)
    gate_map = load(MAP)
    workflow = WORKFLOW.read_text(encoding="utf-8") if WORKFLOW.is_file() else ""

    require(contract.get("schema_version") == 1, "f7_rel_01_contract_schema")
    require(contract.get("gate_id") == "F7-REL-01", "f7_rel_01_gate_id")
    require(contract.get("status") == "closed", "f7_rel_01_contract_closed")
    require(contract.get("target_base") == "main", "f7_rel_01_target_main")
    require(contract.get("required_authority_count") == 4, "f7_rel_01_four_authorities")
    require(len(contract.get("authorities") or []) == 4, "f7_rel_01_authority_inventory")
    require("F7-REL-02" in str(contract.get("po_acceptance_policy") or ""), "f7_rel_01_po_boundary_retained")

    release_gate = (gate_map.get("gates") or {}).get("release_acceptance") or {}
    require(release_gate.get("status") == "partial", "f7_rel_01_release_gate_partial_until_rel02")
    residuals = {row.get("id"): row for row in release_gate.get("residuals", [])}
    require(set(residuals) == {"F7-REL-01", "F7-REL-02", "F7-REL-03"}, "f7_rel_01_release_residual_set")
    rel01 = residuals["F7-REL-01"]
    require(rel01.get("status") == "closed", "f7_rel_01_map_closed")
    require(rel01.get("aggregate_workflow") == ".github/workflows/f7-release-acceptance-gate.yml", "f7_rel_01_map_workflow")
    require(rel01.get("contract") == "quality/ci/f7_release_acceptance_gate.json", "f7_rel_01_map_contract")
    require(residuals["F7-REL-02"].get("status") == "open", "f7_rel_02_remains_open")
    require(residuals["F7-REL-03"].get("status") == "closed", "f7_rel_03_remains_closed")

    contract_proof = contract.get("closure_proof") or {}
    map_proof = rel01.get("proof") or {}
    required_keys = {"run", "job", "candidate_sha", "artifact_id", "artifact_digest"}
    require(set(contract_proof) == required_keys, "f7_rel_01_contract_proof_keys_exact")
    require(set(map_proof) == required_keys, "f7_rel_01_map_proof_keys_exact")
    require(contract_proof == map_proof, "f7_rel_01_contract_map_proof_exact_match")
    require(contract_proof == EXPECTED_PROOF, "f7_rel_01_authoritative_proof_exact")
    require(valid_numeric_id(contract_proof.get("run")), "f7_rel_01_proof_run_valid")
    require(valid_numeric_id(contract_proof.get("job")), "f7_rel_01_proof_job_valid")
    require(valid_sha(contract_proof.get("candidate_sha")), "f7_rel_01_proof_candidate_sha_valid")
    require(valid_numeric_id(contract_proof.get("artifact_id")), "f7_rel_01_proof_artifact_id_valid")
    require(valid_sha256_digest(contract_proof.get("artifact_digest")), "f7_rel_01_proof_artifact_digest_valid")

    history = gate_map.get("history") or {}
    f707 = history.get("F7-07") or {}
    require(f707.get("status") == "proof_complete", "f7_07_history_proof_complete")
    require(f707.get("scope") == "F7-REL-01", "f7_07_history_scope")
    require(f707.get("proof_run") == EXPECTED_PROOF["run"], "f7_07_history_run")
    require(f707.get("proof_job") == EXPECTED_PROOF["job"], "f7_07_history_job")
    require(f707.get("proof_sha") == EXPECTED_PROOF["candidate_sha"], "f7_07_history_sha")
    require(f707.get("artifact_id") == EXPECTED_PROOF["artifact_id"], "f7_07_history_artifact")
    require(f707.get("artifact_digest") == EXPECTED_PROOF["artifact_digest"], "f7_07_history_digest")

    require(WORKFLOW.is_file(), "f7_rel_01_workflow_exists")
    for fragment in (
        "name: F7 REL-01 Release Acceptance exact-candidate gate",
        "workflow_dispatch:",
        "uses: ./.github/workflows/f7-release-package-authority.yml",
        "F7_REL_01_CANDIDATE_IDENTITY_GREEN",
        "F7_REL_01_AGGREGATED_COUNT=4",
        "F7_REL_01_RELEASE_ACCEPTANCE_GATE_GREEN",
        "python scripts/ci/validate_f7_rel_01_release_acceptance_contract.py",
        "F7_REL_01_CLOSURE_CONTRACT_GREEN",
    ):
        require(fragment in workflow, f"f7_rel_01_workflow_fragment_{fragment.replace(' ', '_')[:60]}")

    print("F7_REL_01_CLOSURE_CONTRACT_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

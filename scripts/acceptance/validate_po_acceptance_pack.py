#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "quality/acceptance/po_acceptance_pack.json"
RESULT_TEMPLATE = ROOT / "quality/acceptance/po_acceptance_result.template.json"
MATRIX = ROOT / "quality/acceptance/functional_acceptance_matrix.json"
F7_MAP = ROOT / "quality/ci/f7_ci_orchestration_gate_map.json"

EXPECTED_PACK_ID = "F8-PO-01"
EXPECTED_JOURNEY_IDS = ["PO-01", "PO-02", "PO-03", "PO-04"]
EXPECTED_TOTAL_MINUTES = 25
EXPECTED_MATRIX_BLOB = "75549a41080aeba2bbc8518437764a7904922de3"
FORBIDDEN_MANUAL_TERMS = {
    "postgresql",
    "database",
    "api inspection",
    "ci log",
    "workflow inspection",
    "container inspection",
    "docker",
    "playwright",
    "sql query",
    "commit sha",
}


def fail(message: str) -> None:
    raise SystemExit(f"FAIL F8 PO acceptance pack: {message}")


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def load(path: Path) -> dict:
    require(path.is_file(), f"missing {path.relative_to(ROOT)}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid JSON {path.relative_to(ROOT)}: {type(exc).__name__}")
    require(isinstance(data, dict), f"root must be object: {path.relative_to(ROOT)}")
    return data


def git_blob_sha(path: Path) -> str:
    payload = path.read_bytes()
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def flatten_text(journey: dict) -> str:
    parts = [
        str(journey.get("title") or ""),
        str(journey.get("purpose") or ""),
    ]
    parts.extend(str(item) for item in journey.get("steps") or [])
    parts.extend(str(item) for item in journey.get("acceptance_criteria") or [])
    return " ".join(parts).lower()


def main() -> int:
    pack = load(PACK)
    result_template = load(RESULT_TEMPLATE)
    matrix = load(MATRIX)
    gate_map = load(F7_MAP)

    require(pack.get("schema_version") == 1, "pack schema_version must be 1")
    require(pack.get("pack_id") == EXPECTED_PACK_ID, "pack_id drift")
    require(pack.get("status") == "ready_for_po", "pack must remain ready_for_po until explicit PO execution")
    require(pack.get("release_dependency") == "F7-REL-02", "release dependency must be F7-REL-02")
    require(pack.get("source_matrix") == "quality/acceptance/functional_acceptance_matrix.json", "source matrix path drift")
    require(pack.get("source_matrix_blob") == EXPECTED_MATRIX_BLOB, "declared source matrix blob drift")
    require(git_blob_sha(MATRIX) == EXPECTED_MATRIX_BLOB, "functional acceptance matrix changed without PO pack review")

    scenarios = matrix.get("scenarios") or []
    require(isinstance(scenarios, list) and scenarios, "matrix scenarios missing")
    manual_p0 = {
        row.get("id")
        for row in scenarios
        if row.get("priority") == "P0" and row.get("manual_po_acceptance") is True
    }
    require(None not in manual_p0, "manual P0 scenario without id")
    require(len(manual_p0) == 13, f"expected 13 manual P0 scenarios, found {len(manual_p0)}")

    technical_p0 = {
        row.get("id")
        for row in scenarios
        if row.get("priority") == "P0" and row.get("manual_po_acceptance") is False
    }
    require(technical_p0 == {"P0-MIGRATION-STARTUP"}, f"technical-only P0 scope drift: {sorted(technical_p0)}")

    policy = pack.get("policy") or {}
    require(policy.get("no_manual_regression_replay") is True, "no_manual_regression_replay must be true")
    require(policy.get("technical_authority_excluded") == ["P0-MIGRATION-STARTUP"], "technical authority exclusion drift")
    require(set(policy.get("blocking_dimensions") or []) == {
        "clarity",
        "user_flow",
        "feedback",
        "product_intent",
        "role_and_context_comprehension",
    }, "blocking dimensions drift")

    journeys = pack.get("journeys") or []
    require(len(journeys) == 4, "pack must contain exactly four fixed journeys")
    ids = [row.get("id") for row in journeys]
    require(ids == EXPECTED_JOURNEY_IDS, f"journey order drift: {ids}")
    require([row.get("order") for row in journeys] == [1, 2, 3, 4], "journey numeric order drift")

    total_minutes = sum(int(row.get("estimated_minutes") or 0) for row in journeys)
    require(pack.get("expected_total_minutes") == EXPECTED_TOTAL_MINUTES, "declared total duration drift")
    require(total_minutes == EXPECTED_TOTAL_MINUTES, f"journey duration total must be {EXPECTED_TOTAL_MINUTES}")
    require(total_minutes <= 30, "PO pack must remain a short acceptance check of at most 30 minutes")

    covered: list[str] = []
    for journey in journeys:
        covers = journey.get("covers") or []
        steps = journey.get("steps") or []
        criteria = journey.get("acceptance_criteria") or []
        require(isinstance(covers, list) and covers, f"{journey.get('id')} covers missing")
        require(3 <= len(steps) <= 6, f"{journey.get('id')} must have 3-6 user steps")
        require(3 <= len(criteria) <= 5, f"{journey.get('id')} must have 3-5 acceptance criteria")
        covered.extend(covers)
        manual_text = flatten_text(journey)
        for forbidden in FORBIDDEN_MANUAL_TERMS:
            require(forbidden not in manual_text, f"{journey.get('id')} leaks technical evidence instruction: {forbidden}")

    require(len(covered) == len(set(covered)), "manual P0 scenarios must appear in exactly one journey")
    require(set(covered) == manual_p0, f"manual P0 coverage mismatch; missing={sorted(manual_p0 - set(covered))} extra={sorted(set(covered) - manual_p0)}")
    require("P0-MIGRATION-STARTUP" not in covered, "technical migration/startup authority must not be replayed by PO")

    execution_policy = pack.get("execution_policy") or {}
    require(execution_policy.get("bind_result_to_candidate_sha") is True, "PO result must bind to exact candidate SHA")
    require(execution_policy.get("allowed_journey_verdicts") == ["accepted", "rejected"], "journey verdict contract drift")
    require("automated" in str(execution_policy.get("evidence_boundary") or "").lower(), "technical evidence boundary must remain explicit")

    require(result_template.get("schema_version") == 1, "result template schema drift")
    require(result_template.get("pack_id") == EXPECTED_PACK_ID, "result template pack id drift")
    require(result_template.get("candidate_ref") is None, "result template candidate_ref must start empty")
    require(result_template.get("candidate_sha") is None, "result template candidate_sha must start empty")
    require(result_template.get("executed_at") is None, "result template executed_at must start empty")
    require(result_template.get("executed_by") == "PO", "result template executor must be PO")
    require(result_template.get("overall_verdict") == "pending", "result template must not synthesize acceptance")
    template_journeys = result_template.get("journeys") or []
    require([row.get("id") for row in template_journeys] == EXPECTED_JOURNEY_IDS, "result template journey set/order drift")
    require(all(row.get("verdict") == "pending" for row in template_journeys), "result template journey verdicts must be pending")
    require(all(row.get("notes") == "" for row in template_journeys), "result template notes must start empty")
    require(result_template.get("blocking_findings") == [], "result template blocking findings must start empty")
    require(result_template.get("non_blocking_observations") == [], "result template observations must start empty")

    release_gate = ((gate_map.get("gates") or {}).get("release_acceptance") or {})
    require(release_gate.get("status") == "partial", "release acceptance must remain partial until PO verdict and Phase 9")
    residuals = {row.get("id"): row for row in release_gate.get("residuals", [])}
    require((residuals.get("F7-REL-02") or {}).get("status") == "open", "F7-REL-02 must remain open until explicit PO result")

    print("PASS f8_po_source_matrix_bound")
    print("PASS f8_po_exact_13_manual_p0_scenarios")
    print("PASS f8_po_technical_p0_excluded")
    print("PASS f8_po_four_fixed_journeys")
    print("PASS f8_po_pack_max_30_minutes")
    print("PASS f8_po_no_manual_regression_replay")
    print("PASS f8_po_candidate_bound_result_template_pending")
    print("PASS f8_po_rel02_remains_open_until_explicit_verdict")
    print("F8_PO_ACCEPTANCE_PACK_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

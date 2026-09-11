#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT_PATH = ROOT / "quality" / "acceptance" / "f6_failure_recovery_gap_audit.json"
P0_CLOSURE_PATH = ROOT / "quality" / "acceptance" / "p0_residual_closure.json"
FINAL_PATH = ROOT / "quality" / "acceptance" / "f6_final_closure.json"

EXPECTED_RAW_COUNTS = {"covered": 43, "partial": 48, "gap": 26, "na": 23}
EXPECTED_NON_BLOCKING_COUNTS = {"covered": 9, "partial": 48, "gap": 26, "na": 23}
EXPECTED_SLICES = {
    "F6-01": {
        "scenarios": {
            "P0-RECEIPT-INVENTORY-ALMOSTOUT",
            "P0-KASSA-REVIEW",
            "P0-UNPACKING",
            "P0-INVENTORY",
        },
        "categories": {"controlled_5xx", "standard_user_feedback", "db_consistency_after_error"},
        "proof_runs": {"34448095919", "34454139847", "34590138290", "34397204686"},
    },
    "F6-02": {
        "scenarios": {"P0-RECEIPT-INVENTORY-ALMOSTOUT", "P0-KASSA-REVIEW", "P0-UNPACKING"},
        "categories": {"timeout_temporary_failure", "safe_resume"},
        "proof_runs": {"34617055659"},
    },
    "F6-03": {
        "scenarios": {"P0-RECEIPT-INVENTORY-ALMOSTOUT", "P0-KASSA-REVIEW"},
        "categories": {"invalid_import"},
        "proof_runs": {"34625163561"},
    },
    "F6-04": {
        "scenarios": {"P0-ONBOARDING", "P0-SETTINGS-PROJECTION", "P0-INVENTORY"},
        "categories": {"interrupted_flow", "safe_resume"},
        "proof_runs": {"34629433456"},
    },
    "F6-05": {
        "scenarios": {
            "P0-ACCOUNT-SESSION",
            "P0-HOUSEHOLD-MEMBERSHIP",
            "P0-AUTHORIZATION-ISOLATION",
            "P0-PLATFORM-AUTHORITY",
        },
        "categories": {"auth_401_403", "functional_4xx"},
        "proof_runs": {"34634787635"},
    },
}


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def require(condition: bool, marker: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL {marker}")
    print(f"PASS {marker}")


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def pairs(scenarios, categories):
    return {(scenario, category) for scenario in scenarios for category in categories}


def main() -> None:
    audit = load_json(AUDIT_PATH)
    p0 = load_json(P0_CLOSURE_PATH)
    final = load_json(FINAL_PATH)

    require(final.get("schema_version") == 1, "f6_final_schema_version")
    require(final.get("phase") == "F6", "f6_final_phase")
    require(final.get("status") == "closure_candidate", "f6_final_status_closure_candidate")

    sources = final.get("source_authorities", {})
    audit_source = sources.get("failure_recovery_audit", {})
    p0_source = sources.get("p0_residual_closure", {})
    require(audit_source.get("path") == str(AUDIT_PATH.relative_to(ROOT)), "f6_final_audit_path_exact")
    require(p0_source.get("path") == str(P0_CLOSURE_PATH.relative_to(ROOT)), "f6_final_p0_path_exact")
    require(git_blob_sha(AUDIT_PATH) == audit_source.get("blob_sha"), "f6_final_audit_blob_exact")
    require(git_blob_sha(P0_CLOSURE_PATH) == p0_source.get("blob_sha"), "f6_final_p0_blob_exact")

    raw_counts = Counter()
    scenario_map = {}
    for row in audit.get("scenarios", []):
        scenario_id = row.get("id")
        require(bool(scenario_id), "f6_final_scenario_has_id")
        require(scenario_id not in scenario_map, f"f6_final_unique_{scenario_id}")
        scenario_map[scenario_id] = row
        raw_counts.update(row.get("assessments", {}).values())

    require(len(scenario_map) == 14, "f6_final_14_scenarios")
    require(dict(raw_counts) == EXPECTED_RAW_COUNTS, "f6_final_raw_counts_preserved")
    require(audit.get("summary", {}).get("total_assessments") == 140, "f6_final_raw_total_140")
    require(audit_source.get("raw_summary") == EXPECTED_RAW_COUNTS, "f6_final_declared_raw_summary_exact")

    closed_p0 = {
        row.get("id")
        for row in p0.get("scenarios", [])
        if row.get("status") == "closed"
    }
    require(len(closed_p0) == 14, "f6_final_source_p0_14_closed")
    require(closed_p0 == set(scenario_map), "f6_final_source_p0_matches_audit")

    audit_slices = {row.get("id"): row for row in audit.get("priority_slices", [])}
    final_slices = {row.get("id"): row for row in final.get("blocking_slices", [])}
    require(set(audit_slices) == set(EXPECTED_SLICES), "f6_final_audit_slices_f6_01_to_05")
    require(set(final_slices) == set(EXPECTED_SLICES), "f6_final_declared_slices_f6_01_to_05")

    blocking_pairs = set()
    for slice_id, expected in EXPECTED_SLICES.items():
        declared = final_slices[slice_id]
        audit_slice = audit_slices[slice_id]
        declared_scenarios = set(declared.get("scenarios", []))
        declared_categories = set(declared.get("categories", []))
        require(declared_scenarios == expected["scenarios"], f"{slice_id}_scenarios_exact")
        require(set(audit_slice.get("scope", [])) == expected["scenarios"], f"{slice_id}_audit_scope_exact")
        require(declared_categories == expected["categories"], f"{slice_id}_categories_exact")
        require(set(declared.get("proof_runs", [])) == expected["proof_runs"], f"{slice_id}_proof_runs_exact")
        blocking_pairs |= pairs(declared_scenarios, declared_categories)

    require(len(blocking_pairs) == 34, "f6_final_release_blocking_pair_count_34")

    uncovered_blocking = []
    for scenario_id, category in sorted(blocking_pairs):
        status = scenario_map[scenario_id]["assessments"][category]
        if status != "covered":
            uncovered_blocking.append((scenario_id, category, status))
    require(not uncovered_blocking, "f6_final_zero_uncovered_release_blocking_pairs")

    all_pairs = {
        (scenario_id, category)
        for scenario_id, row in scenario_map.items()
        for category in row.get("assessments", {})
    }
    require(len(all_pairs) == 140, "f6_final_all_pair_count_140")
    non_blocking_pairs = all_pairs - blocking_pairs
    require(len(non_blocking_pairs) == 106, "f6_final_non_blocking_pair_count_106")

    non_blocking_counts = Counter(
        scenario_map[scenario_id]["assessments"][category]
        for scenario_id, category in non_blocking_pairs
    )
    require(dict(non_blocking_counts) == EXPECTED_NON_BLOCKING_COUNTS, "f6_final_non_blocking_status_counts_exact")

    raw_gap_pairs = {
        pair
        for pair in all_pairs
        if scenario_map[pair[0]]["assessments"][pair[1]] == "gap"
    }
    require(len(raw_gap_pairs) == 26, "f6_final_raw_gap_count_26")
    require(not (raw_gap_pairs & blocking_pairs), "f6_final_no_release_blocking_gap")

    declared_gap_pairs = set()
    dispositions = final.get("non_blocking_gap_dispositions", [])
    for row in dispositions:
        scenario_id = row.get("scenario")
        categories = row.get("categories", [])
        require(row.get("reason_code") == "outside_explicit_f6_priority_slice", f"f6_final_gap_reason_{scenario_id}")
        require(bool(row.get("reason")), f"f6_final_gap_reason_text_{scenario_id}")
        for category in categories:
            pair = (scenario_id, category)
            require(pair not in declared_gap_pairs, f"f6_final_gap_pair_unique_{scenario_id}_{category}")
            declared_gap_pairs.add(pair)

    require(declared_gap_pairs == raw_gap_pairs, "f6_final_all_26_raw_gaps_explicitly_disposed")
    require(declared_gap_pairs <= non_blocking_pairs, "f6_final_gap_dispositions_non_blocking_only")

    summary = final.get("summary", {})
    require(summary.get("total_assessments") == 140, "f6_final_summary_total_140")
    require(summary.get("release_blocking_assessments") == 34, "f6_final_summary_blocking_34")
    require(summary.get("release_blocking_covered") == 34, "f6_final_summary_blocking_covered_34")
    require(summary.get("release_blocking_uncovered") == 0, "f6_final_summary_blocking_uncovered_0")
    require(summary.get("informational_non_blocking_assessments") == 106, "f6_final_summary_non_blocking_106")
    require(summary.get("informational_statuses") == EXPECTED_NON_BLOCKING_COUNTS, "f6_final_summary_non_blocking_counts")

    policy = final.get("policy", {})
    require(policy.get("raw_audit_preserved") is True, "f6_final_policy_preserves_raw_audit")
    require(bool(policy.get("hard_exit")), "f6_final_policy_has_hard_exit")
    require(bool(policy.get("non_blocking_rule")), "f6_final_policy_has_non_blocking_rule")
    require(bool(policy.get("gap_disposition_rule")), "f6_final_policy_has_gap_disposition_rule")
    require(bool(policy.get("no_status_rewrite")), "f6_final_policy_has_no_status_rewrite")

    decision = final.get("decision", {})
    require(decision.get("phase_6_hard_exit") == "satisfied", "f6_final_hard_exit_satisfied")
    require(decision.get("release_blocking_gap_count") == 0, "f6_final_release_blocking_gap_count_zero")
    require(decision.get("formal_status_after_merge") == "closed", "f6_final_status_after_merge_closed")

    print(f"F6_FINAL_RAW_COVERED={raw_counts['covered']}")
    print(f"F6_FINAL_RAW_PARTIAL={raw_counts['partial']}")
    print(f"F6_FINAL_RAW_GAP={raw_counts['gap']}")
    print(f"F6_FINAL_RAW_NA={raw_counts['na']}")
    print("F6_FINAL_RELEASE_BLOCKING_ASSESSMENTS=34")
    print("F6_FINAL_RELEASE_BLOCKING_COVERED=34")
    print("F6_FINAL_RELEASE_BLOCKING_UNCOVERED=0")
    print("F6_FINAL_INFORMATIONAL_NON_BLOCKING=106")
    print("F6_FINAL_EXPLICIT_NON_BLOCKING_GAPS=26")
    print("F6_PHASE_6_FORMAL_CLOSURE_GREEN")


if __name__ == "__main__":
    main()

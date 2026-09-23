#!/usr/bin/env python3
"""Fail-closed S/M/L classifier for Rezzerv pull-request candidates."""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "quality/ci/change_risk_policy.json"


def die(message: str) -> None:
    raise SystemExit(f"FAIL F7-RISK: {message}")


def req(condition: bool, message: str) -> None:
    if not condition:
        die(message)


def load_policy(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        die(f"invalid policy JSON {path}: {type(exc).__name__}: {exc}")
    req(isinstance(data, dict), "policy root must be an object")
    req(data.get("schema_version") == 1, "schema_version must be 1")
    req(data.get("policy_id") == "F7-RISK-01", "policy_id must be F7-RISK-01")
    levels = data.get("level_order")
    req(levels == ["S", "M", "L"], "level_order must be S,M,L")
    req(data.get("default_level") == "L", "default_level must fail closed to L")
    req(data.get("missing_provisional_level") == "L", "missing provisional level must fail closed to L")
    rules = data.get("path_rules")
    req(isinstance(rules, list) and rules, "path_rules missing")
    for row in rules:
        req(row.get("level") in levels, f"invalid rule level: {row}")
        req(isinstance(row.get("reason"), str) and row["reason"], f"rule reason missing: {row}")
        patterns = row.get("patterns")
        req(isinstance(patterns, list) and patterns, f"rule patterns missing: {row}")
        req(all(isinstance(p, str) and p for p in patterns), f"invalid pattern in {row}")
    gates = data.get("required_gates")
    req(isinstance(gates, dict) and set(gates) == set(levels), "required_gates must define S/M/L")
    governance = data.get("governance") or {}
    req(governance.get("preliminary_before_implementation") is True, "preliminary classification must be mandatory")
    req(governance.get("final_from_complete_candidate_delta") is True, "final classification must use complete candidate delta")
    req(governance.get("final_level_is_maximum_of_preliminary_and_delta") is True, "final level must be max(preliminary, delta)")
    req(governance.get("automatic_downgrade_forbidden") is True, "automatic downgrade must be forbidden")
    req(governance.get("unknown_paths_fail_closed_to") == "L", "unknown paths must fail closed to L")
    bundle = data.get("version_only_bundle") or {}
    req(bundle.get("level") == "S", "version-only bundle must be S")
    files = bundle.get("files")
    req(isinstance(files, list) and "frontend/package.json" in files and "VERSION.txt" in files, "version-only bundle incomplete")
    carry = data.get("version_only_carry_forward") or {}
    req(carry.get("enabled") is True, "version-only carry-forward must be enabled")
    req(carry.get("require_direct_parent") is True, "carry-forward must require direct parent")
    req(carry.get("require_exact_bundle") is True, "carry-forward must require exact version bundle")
    req(carry.get("require_patch_increment") == 1, "carry-forward must require one patch increment")
    req(carry.get("require_same_pull_request") is True, "carry-forward must require same PR")
    req(carry.get("require_same_base_sha") is True, "carry-forward must require same PR base")
    req(carry.get("require_same_branch") is True, "carry-forward must require same branch")
    req(carry.get("require_prior_success") is True, "carry-forward must require prior green evidence")
    req(carry.get("preserve_complete_candidate_risk_level") is True, "carry-forward must preserve complete candidate risk")
    req(carry.get("full_regression_exact_candidate_not_carried_forward") is True, "F7 Full exact candidate must remain current-SHA evidence")
    return data


def validate_integration() -> None:
    required = [
        ROOT / ".github/workflows/change-risk-classification.yml",
        ROOT / ".github/workflows/f7-pr-fast-regression-gate.yml",
        ROOT / ".github/workflows/f7-full-regression-gate.yml",
        ROOT / "quality/ci/f7_full_regression_gate.json",
        ROOT / "AGENTS.md",
        ROOT / "docs/project/CHANGE-RISK-AND-TEST-LEVELS.md",
        ROOT / "docs/project/README.md",
        ROOT / "scripts/ci/version_only_carry_forward.py",
    ]
    for path in required:
        req(path.is_file(), f"missing risk-policy integration file: {path.relative_to(ROOT)}")

    standalone = required[0].read_text(encoding="utf-8")
    fast = required[1].read_text(encoding="utf-8")
    full = required[2].read_text(encoding="utf-8")
    full_config = json.loads(required[3].read_text(encoding="utf-8"))
    agents = required[4].read_text(encoding="utf-8")
    policy_doc = required[5].read_text(encoding="utf-8")
    project_index = required[6].read_text(encoding="utf-8")

    req("scripts/ci/classify_change_risk.py" in standalone, "standalone classification workflow lost classifier")
    req("scripts/ci/classify_change_risk.py" in fast, "F7 Fast lost risk classifier")
    req("--risk-level" in fast and "steps.risk.outputs.final_level" in fast, "F7 Fast lost S cheap-only gate selection")
    req("scripts/ci/classify_change_risk.py" in full, "F7 Full lost risk classifier")
    req("steps.risk.outputs.final_level == 'L'" in full, "F7 Full lost L-only heavy dispatch guard")
    req("F7_FULL_HEAVY_AUTHORITIES_NOT_REQUIRED_GREEN" in full, "F7 Full lost S/M bypass evidence")
    req("F7_FULL_AUTHORITY_COUNT=21" in full, "F7 Full lost current twenty-one-authority contract")
    req(full_config.get("required_workflow_count") == 21, "F7 Full config lost twenty-one-authority inventory")
    reuse = full_config.get("reuse_contract") or {}
    req(reuse.get("exact_candidate_sha") is True, "F7 Full exact-SHA reuse contract lost")
    req(reuse.get("attach_matching_in_progress") is True, "F7 Full attach/reuse contract lost")
    req("TEST_LEVEL_PROVISIONAL:" in agents, "AGENTS lost preliminary classification contract")
    req("Automatisch afschalen is verboden" in policy_doc, "policy documentation lost no-downgrade rule")
    req("21 authorities" in policy_doc, "policy documentation lost current Full Regression authority count")
    req("CHANGE-RISK-AND-TEST-LEVELS.md" in project_index, "project index lost mandatory S/M/L policy")


def git(*args: str) -> str:
    process = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    if process.returncode:
        die(f"git {' '.join(args)}: {process.stderr.strip()}")
    return process.stdout


def rank(policy: dict, level: str) -> int:
    try:
        return policy["level_order"].index(level)
    except ValueError:
        die(f"unknown level: {level}")


def max_level(policy: dict, *levels: str) -> str:
    return max(levels, key=lambda level: rank(policy, level))


def path_level(policy: dict, path: str) -> tuple[str, list[str]]:
    matched: list[tuple[str, str, str]] = []
    for rule in policy["path_rules"]:
        for pattern in rule["patterns"]:
            if fnmatch.fnmatchcase(path, pattern):
                matched.append((rule["level"], rule["reason"], pattern))
    if not matched:
        return policy["default_level"], ["unknown_path_fail_closed"]
    level = max((row[0] for row in matched), key=lambda item: rank(policy, item))
    reasons = [f"{reason}:{pattern}" for candidate, reason, pattern in matched if candidate == level]
    return level, reasons


def read_json_at(sha: str, path: str) -> dict | None:
    process = subprocess.run(["git", "show", f"{sha}:{path}"], cwd=ROOT, text=True, capture_output=True)
    if process.returncode:
        return None
    try:
        data = json.loads(process.stdout)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def is_json_version_only(base_sha: str, head_sha: str, path: str) -> bool:
    before = read_json_at(base_sha, path)
    after = read_json_at(head_sha, path)
    if before is None or after is None:
        return False
    before = dict(before)
    after = dict(after)
    before.pop("version", None)
    after.pop("version", None)
    return before == after


def is_version_only_bundle(policy: dict, changed: list[str], base_sha: str, head_sha: str) -> bool:
    if not changed:
        return False
    bundle = policy["version_only_bundle"]
    allowed = set(bundle["files"])
    if not set(changed).issubset(allowed):
        return False
    for path in bundle.get("json_version_only_files", []):
        if path in changed and not is_json_version_only(base_sha, head_sha, path):
            return False
    return True


def provisional_from_body(policy: dict, body: str) -> str | None:
    marker = re.escape(policy["provisional_marker"])
    match = re.search(rf"(?im)^\s*{marker}\s*([SML])\s*$", body or "")
    return match.group(1).upper() if match else None


def write_output(name: str, value: str) -> None:
    target = os.getenv("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def classify_paths(policy: dict, paths: list[str], provisional: str) -> dict:
    rows = []
    delta = "S"
    for path in paths:
        level, reasons = path_level(policy, path)
        delta = max_level(policy, delta, level)
        rows.append({"path": path, "level": level, "reasons": reasons})
    if not paths:
        delta = "S"
    final = max_level(policy, provisional, delta)
    return {"delta_level": delta, "provisional_level": provisional, "final_level": final, "files": rows}


def cmd_validate(args: argparse.Namespace) -> int:
    policy = load_policy(Path(args.policy))
    validate_integration()
    print(f"CHANGE_RISK_POLICY={policy['policy_id']}")
    print("PASS change_risk_fail_closed_default_L")
    print("PASS change_risk_no_automatic_downgrade")
    print("PASS change_risk_required_gates_S_M_L")
    print("PASS change_risk_version_only_carry_forward_policy")
    print("PASS change_risk_workflow_integration_locked")
    print("PASS change_risk_agents_contract_locked")
    print("CHANGE_RISK_POLICY_GREEN")
    return 0


def cmd_self_test(args: argparse.Namespace) -> int:
    policy = load_policy(Path(args.policy))
    cases = [
        (["docs/project/example.md"], "S", "S"),
        (["frontend/src/features/example.jsx"], "S", "M"),
        (["backend/app/main.py"], "S", "L"),
        ([".github/workflows/example.yml"], "S", "L"),
        (["docs/project/example.md"], "L", "L"),
        (["new/unknown/file.xyz"], "S", "L"),
    ]
    for paths, provisional, expected in cases:
        actual = classify_paths(policy, paths, provisional)["final_level"]
        req(actual == expected, f"self-test {paths} provisional={provisional}: expected {expected}, got {actual}")
    print("PASS change_risk_S_documentation")
    print("PASS change_risk_M_frontend_application")
    print("PASS change_risk_L_backend_core")
    print("PASS change_risk_L_ci_orchestration")
    print("PASS change_risk_preliminary_L_cannot_downgrade")
    print("PASS change_risk_unknown_path_fails_closed_L")
    print("CHANGE_RISK_SELF_TEST_GREEN")
    return 0


def cmd_classify(args: argparse.Namespace) -> int:
    policy = load_policy(Path(args.policy))
    levels = policy["level_order"]
    req(args.base_sha and args.head_sha and args.base_sha != args.head_sha, "base/head SHA must be distinct")
    git("cat-file", "-e", f"{args.base_sha}^{{commit}}")
    git("cat-file", "-e", f"{args.head_sha}^{{commit}}")
    changed = [line for line in git("diff", "--name-only", "--diff-filter=ACMRD", args.base_sha, args.head_sha).splitlines() if line]

    provisional = args.provisional_level
    if not provisional and args.pr_body_env:
        provisional = provisional_from_body(policy, os.getenv(args.pr_body_env, ""))
    if not provisional:
        provisional = policy["missing_provisional_level"]
    req(provisional in levels, f"invalid provisional level: {provisional}")

    version_only = is_version_only_bundle(policy, changed, args.base_sha, args.head_sha)
    if version_only:
        delta = policy["version_only_bundle"]["level"]
        rows = [{"path": path, "level": "S", "reasons": ["version_only_bundle"]} for path in changed]
    else:
        result = classify_paths(policy, changed, "S")
        delta = result["delta_level"]
        rows = result["files"]

    final = max_level(policy, provisional, delta)
    evidence = {
        "policy_id": policy["policy_id"],
        "base_sha": args.base_sha,
        "head_sha": args.head_sha,
        "changed_files": changed,
        "version_only_bundle": version_only,
        "provisional_level": provisional,
        "delta_level": delta,
        "final_level": final,
        "automatic_downgrade": False,
        "required_gates": policy["required_gates"][final],
        "files": rows,
    }
    Path(args.evidence).write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    print(f"CHANGE_RISK_CHANGED_COUNT={len(changed)}")
    print(f"CHANGE_RISK_PROVISIONAL_LEVEL={provisional}")
    print(f"CHANGE_RISK_DELTA_LEVEL={delta}")
    print(f"CHANGE_RISK_FINAL_LEVEL={final}")
    print(f"CHANGE_RISK_VERSION_ONLY={'true' if version_only else 'false'}")
    print(f"CHANGE_RISK_FULL_REQUIRED={'true' if final == 'L' else 'false'}")
    for row in rows:
        print(f"CHANGE_RISK_FILE level={row['level']} path={row['path']}")
    print("CHANGE_RISK_CLASSIFICATION_GREEN")

    write_output("provisional_level", provisional)
    write_output("delta_level", delta)
    write_output("final_level", final)
    write_output("full_required", "true" if final == "L" else "false")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate-policy")
    validate.set_defaults(func=cmd_validate)

    self_test = sub.add_parser("self-test")
    self_test.set_defaults(func=cmd_self_test)

    classify = sub.add_parser("classify")
    classify.add_argument("--base-sha", required=True)
    classify.add_argument("--head-sha", required=True)
    classify.add_argument("--provisional-level", choices=["S", "M", "L"])
    classify.add_argument("--pr-body-env")
    classify.add_argument("--evidence", default="change-risk-evidence.json")
    classify.set_defaults(func=cmd_classify)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

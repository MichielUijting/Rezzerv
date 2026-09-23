#!/usr/bin/env python3
"""Fail-closed incremental planner for PR253 full frontend regression.

GitHub pull_request path filters are evaluated over the whole PR, so a workflow
may be scheduled again after a tiny follow-up commit. This planner uses the
previous-head->new-head delta only after proving a green PR253 run exists on the
previous head for the same PR/base/branch.

Modes:
- full: run the existing full Docker + Playwright regression;
- contracts: rerun only changed top-level *.contract.mjs tests;
- reuse: no frontend test changed; reuse the previous green PR253 evidence.

Any unknown or runtime-sensitive delta falls back to full.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
from pathlib import Path

from version_only_carry_forward import prior_success_run

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATTERN = "frontend/tests/*.contract.mjs"
SAFE_IRRELEVANT_PATTERNS = ("docs/**", "*.md")


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def _emit(name: str, value: str) -> None:
    print(f"FRONTEND_INCREMENTAL_{name.upper()}={value}")
    output = os.getenv("GITHUB_OUTPUT", "").strip()
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def _matches(path: str, pattern: str) -> bool:
    if fnmatch.fnmatchcase(path, pattern):
        return True
    if pattern.endswith("/**") and path.startswith(pattern[:-3]):
        return True
    return False


def extract_pull_request_paths(workflow_path: Path) -> list[str]:
    lines = workflow_path.read_text(encoding="utf-8").splitlines()
    in_pull_request = False
    pull_indent = -1
    in_paths = False
    paths_indent = -1
    patterns: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        if stripped.startswith("pull_request:"):
            in_pull_request = True
            pull_indent = indent
            in_paths = False
            continue
        if in_pull_request and indent <= pull_indent and not stripped.startswith("pull_request:"):
            break
        if in_pull_request and stripped == "paths:":
            in_paths = True
            paths_indent = indent
            continue
        if in_paths:
            if indent <= paths_indent:
                in_paths = False
                continue
            if stripped.startswith("-"):
                value = stripped[1:].strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                    value = value[1:-1]
                if value:
                    patterns.append(value)
    return patterns


def _is_top_level_contract(path: str) -> bool:
    if not _matches(path, CONTRACT_PATTERN):
        return False
    relative = path.removeprefix("frontend/tests/")
    return "/" not in relative and relative.endswith(".contract.mjs")


def classify_incremental_files(changed: list[str], workflow_patterns: list[str]) -> tuple[str, list[str], str]:
    full_matches = [
        path for path in changed
        if any(_matches(path, pattern) for pattern in workflow_patterns)
    ]
    if full_matches:
        return "full", [], f"workflow_dependency_changed:{full_matches[0]}"

    contracts = sorted(path for path in changed if _is_top_level_contract(path))
    unknown = [
        path for path in changed
        if path not in contracts
        and not any(_matches(path, pattern) for pattern in SAFE_IRRELEVANT_PATTERNS)
    ]
    if unknown:
        return "full", [], f"unmapped_incremental_path:{unknown[0]}"
    if contracts:
        return "contracts", contracts, "changed_contract_tests_only"
    return "reuse", [], "incremental_delta_irrelevant_to_pr253"


def _ensure_commit(sha: str) -> bool:
    if not sha:
        return False
    probe = _run(["git", "cat-file", "-e", f"{sha}^{{commit}}"])
    if probe.returncode == 0:
        return True
    fetched = _run(["git", "fetch", "--no-tags", "--depth=1", "origin", sha])
    return fetched.returncode == 0 and _run(["git", "cat-file", "-e", f"{sha}^{{commit}}"]).returncode == 0


def _full(reason: str, evidence_path: str = "") -> int:
    evidence = {"mode": "full", "reason": reason, "contract_files": []}
    if evidence_path:
        Path(evidence_path).write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    _emit("mode", "full")
    _emit("contract_files", "")
    _emit("source_sha", "")
    _emit("source_run_id", "")
    _emit("reason", reason)
    print("FRONTEND_INCREMENTAL_PLAN_GREEN")
    return 0


def cmd_workflow(args: argparse.Namespace) -> int:
    event_name = os.getenv("GITHUB_EVENT_NAME", "").strip()
    event_path = Path(args.event)
    if event_name != "pull_request" or not event_path.is_file():
        return _full("non_pull_request_or_missing_event", args.evidence)

    try:
        event = json.loads(event_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _full(f"event_invalid:{type(exc).__name__}", args.evidence)

    action = str(event.get("action") or "").strip()
    if action != "synchronize":
        return _full(f"action_{action or 'unknown'}_must_run", args.evidence)

    pr = event.get("pull_request") or {}
    before = str(event.get("before") or "").strip()
    after = str(event.get("after") or (pr.get("head") or {}).get("sha") or "").strip()
    base_sha = str((pr.get("base") or {}).get("sha") or "").strip()
    branch = str((pr.get("head") or {}).get("ref") or "").strip()
    pr_number = str(pr.get("number") or event.get("number") or "").strip()
    if not before or not after or before == after:
        return _full("before_after_unavailable", args.evidence)
    if not _ensure_commit(before) or not _ensure_commit(after):
        return _full("incremental_commit_unavailable", args.evidence)
    ancestry = _run(["git", "merge-base", "--is-ancestor", before, after])
    if ancestry.returncode != 0:
        return _full("previous_head_not_ancestor", args.evidence)

    workflow_path = ROOT / args.workflow_file
    if not workflow_path.is_file():
        return _full("workflow_file_missing", args.evidence)
    patterns = extract_pull_request_paths(workflow_path)
    if not patterns or any(pattern.startswith("!") for pattern in patterns):
        return _full("workflow_paths_invalid", args.evidence)

    diff = _run(["git", "diff", "--name-only", "--diff-filter=ACMRD", before, after])
    if diff.returncode != 0:
        return _full("incremental_diff_failed", args.evidence)
    changed = [line.strip() for line in diff.stdout.splitlines() if line.strip()]
    for path in changed:
        print(f"FRONTEND_INCREMENTAL_CHANGED={path}")

    token = os.getenv("GITHUB_TOKEN", "").strip()
    source_run = prior_success_run(
        args.repo,
        args.workflow_file,
        before,
        pr_number,
        base_sha,
        branch,
        token,
    ) if token and pr_number and base_sha and branch else None
    if not source_run:
        return _full("prior_green_pr253_missing", args.evidence)

    mode, contracts, reason = classify_incremental_files(changed, patterns)
    evidence = {
        "mode": mode,
        "reason": reason,
        "source_sha": before,
        "source_run_id": source_run.get("id"),
        "source_run_url": source_run.get("html_url"),
        "candidate_sha": after,
        "pr_number": pr_number,
        "base_sha": base_sha,
        "branch": branch,
        "changed_files": changed,
        "contract_files": contracts,
    }
    if args.evidence:
        Path(args.evidence).write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    contract_relative = [path.removeprefix("frontend/") for path in contracts]
    _emit("mode", mode)
    _emit("contract_files", ",".join(contract_relative))
    _emit("source_sha", before)
    _emit("source_run_id", str(source_run.get("id") or ""))
    _emit("reason", reason)
    print(f"FRONTEND_INCREMENTAL_SOURCE_RUN={source_run.get('id')}")
    print("FRONTEND_INCREMENTAL_PLAN_GREEN")
    return 0


def cmd_self_test(_: argparse.Namespace) -> int:
    patterns = ["frontend/src/**", "frontend/tests/e2e/**", "frontend/package.json"]
    assert classify_incremental_files(["frontend/tests/mobile-ui-conformity.contract.mjs"], patterns)[0] == "contracts"
    assert classify_incremental_files(["docs/note.md"], patterns)[0] == "reuse"
    assert classify_incremental_files(["frontend/src/App.jsx"], patterns)[0] == "full"
    assert classify_incremental_files(["frontend/tests/unknown.txt"], patterns)[0] == "full"
    assert classify_incremental_files(
        ["frontend/tests/mobile-ui-conformity.contract.mjs", "docs/note.md"],
        patterns,
    )[0] == "contracts"
    print("FRONTEND_INCREMENTAL_PLAN_SELF_TEST_GREEN")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    workflow = sub.add_parser("workflow")
    workflow.add_argument("--repo", required=True)
    workflow.add_argument("--workflow-file", required=True)
    workflow.add_argument("--event", default=os.getenv("GITHUB_EVENT_PATH", ""))
    workflow.add_argument("--evidence", default="")
    workflow.set_defaults(func=cmd_workflow)

    self_test = sub.add_parser("self-test")
    self_test.set_defaults(func=cmd_self_test)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

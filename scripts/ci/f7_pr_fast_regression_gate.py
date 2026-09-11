#!/usr/bin/env python3
"""Plan and aggregate the F7-02 PR Fast Regression gate.

The gate deliberately reuses the existing TP-CI shared-stack manifests.  It
selects clusters from the complete pull-request delta, validates the fallback
policy, and (for PRs targeting main) waits for the selected shared workflows to
finish successfully on the exact same candidate SHA.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_CLUSTER_IDS = ["TP-CI-02", "TP-CI-03", "TP-CI-04", "TP-CI-05", "TP-CI-07"]
FAILED_CONCLUSIONS = {
    "action_required",
    "cancelled",
    "failure",
    "startup_failure",
    "timed_out",
}


def fail(message: str) -> None:
    raise SystemExit(f"FAIL F7-02: {message}")


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid JSON {path.relative_to(ROOT)}: {type(exc).__name__}")
    require(isinstance(data, dict), f"JSON root must be object: {path.relative_to(ROOT)}")
    return data


def load_config(path: str) -> dict[str, Any]:
    target = ROOT / path
    require(target.is_file(), f"gate config missing: {path}")
    data = _load_json(target)
    require(data.get("schema_version") == 1, "schema_version must be 1")
    require(data.get("gate_id") == "F7-02", "gate_id must be F7-02")
    require(data.get("target_base") == "main", "target_base must be main")
    return data


def _matches(path: str, pattern: str) -> bool:
    if fnmatch.fnmatchcase(path, pattern):
        return True
    if pattern.endswith("/**") and path.startswith(pattern[:-3]):
        return True
    return False


def _manifest_patterns(manifest: str) -> list[str]:
    path = ROOT / manifest
    require(path.is_file(), f"manifest missing: {manifest}")
    data = _load_json(path)
    authorities = data.get("authorities")
    require(isinstance(authorities, dict) and authorities, f"manifest has no authorities: {manifest}")
    patterns: list[str] = []
    for name, authority in authorities.items():
        require(isinstance(authority, dict), f"invalid authority {name}: {manifest}")
        values = authority.get("paths")
        require(isinstance(values, list) and values, f"authority paths missing for {name}: {manifest}")
        for value in values:
            require(isinstance(value, str) and value and not value.startswith("!"), f"invalid path pattern for {name}: {value!r}")
            if value not in patterns:
                patterns.append(value)
    return patterns


def _workflow_trigger_is_manual_only(text: str) -> bool:
    return "\n  workflow_dispatch:\n" in text and "\n  pull_request:" not in text


def validate_config(config: dict[str, Any]) -> None:
    clusters = config.get("clusters")
    require(isinstance(clusters, list) and len(clusters) == 5, "exactly five shared clusters are required")
    ids = [cluster.get("id") for cluster in clusters if isinstance(cluster, dict)]
    require(ids == EXPECTED_CLUSTER_IDS, f"cluster order/coverage drift: {ids}")

    seen_workflows: set[str] = set()
    seen_manifests: set[str] = set()
    for cluster in clusters:
        cid = cluster["id"]
        workflow = cluster.get("workflow_file")
        manifest = cluster.get("manifest")
        require(isinstance(workflow, str) and workflow.startswith(".github/workflows/"), f"invalid workflow for {cid}")
        require(isinstance(manifest, str) and manifest.startswith("quality/ci/"), f"invalid manifest for {cid}")
        require(workflow not in seen_workflows, f"duplicate workflow mapping: {workflow}")
        require(manifest not in seen_manifests, f"duplicate manifest mapping: {manifest}")
        seen_workflows.add(workflow)
        seen_manifests.add(manifest)

        workflow_path = ROOT / workflow
        require(workflow_path.is_file(), f"shared workflow missing: {workflow}")
        workflow_text = workflow_path.read_text(encoding="utf-8")
        require("pull_request:" in workflow_text, f"shared workflow lost pull_request trigger: {workflow}")
        require("workflow_dispatch:" in workflow_text, f"shared workflow lost manual fallback: {workflow}")
        require("github.event.pull_request.head.sha || github.sha" in workflow_text, f"shared workflow lost exact candidate checkout: {workflow}")
        require("scripts/ci/shared_fullstack_plan.py" in workflow_text, f"shared workflow lost shared planner: {workflow}")
        _manifest_patterns(manifest)

    validators = config.get("cheap_validators")
    require(isinstance(validators, list) and validators, "cheap_validators missing")
    for validator in validators:
        require(isinstance(validator, str) and (ROOT / validator).is_file(), f"cheap validator missing: {validator}")

    governance = config.get("fallback_governance")
    require(isinstance(governance, dict), "fallback_governance missing")
    manual = governance.get("manual_only_workflows")
    require(isinstance(manual, list) and len(manual) == 14, "expected fourteen manual fallback workflows")
    for workflow in manual:
        require(isinstance(workflow, str), "manual fallback path must be string")
        target = ROOT / workflow
        require(target.is_file(), f"manual fallback missing: {workflow}")
        text = target.read_text(encoding="utf-8")
        require(_workflow_trigger_is_manual_only(text), f"fallback must remain workflow_dispatch-only: {workflow}")

    removed = governance.get("stale_references_removed")
    require(isinstance(removed, list) and len(removed) == 2, "expected two removed stale Kassa references")
    tp02_workflow = (ROOT / ".github/workflows/tp-ci-02-kassa-shared-stack-postgresql-validation.yml").read_text(encoding="utf-8")
    tp02_manifest = (ROOT / "quality/ci/tp_ci_02_kassa_shared_stack_paths.json").read_text(encoding="utf-8")
    for stale in removed:
        require(not (ROOT / stale).exists(), f"deleted fallback unexpectedly exists: {stale}")
        require(stale not in tp02_workflow, f"stale fallback still referenced by TP-CI-02 workflow: {stale}")
        require(stale not in tp02_manifest, f"stale fallback still referenced by TP-CI-02 manifest: {stale}")

    require(governance.get("duplicate_pr_fallbacks") == [], "duplicate automatic PR fallbacks must remain empty")
    print("PASS f7_02_fallback_governance_closed")
    print("F7_02_SHARED_CLUSTERS=5")
    print("F7_02_MANUAL_FALLBACKS=14")
    print("F7_02_STALE_REFERENCES=0")
    print("F7_02_DUPLICATE_PR_FALLBACKS=0")


def _run_git(args: list[str]) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        fail(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _changed_files(base_sha: str, head_sha: str) -> list[str]:
    require(base_sha and head_sha and base_sha != head_sha, "base/head SHA unavailable or identical")
    _run_git(["cat-file", "-e", f"{base_sha}^{{commit}}"])
    _run_git(["cat-file", "-e", f"{head_sha}^{{commit}}"])
    output = _run_git(["diff", "--name-only", "--diff-filter=ACMRD", base_sha, head_sha])
    return [line.strip() for line in output.splitlines() if line.strip()]


def _write_output(name: str, value: str) -> None:
    output = os.getenv("GITHUB_OUTPUT", "").strip()
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def command_validate(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    validate_config(config)
    print("F7_02_PR_FAST_CONFIG_GREEN")
    return 0


def command_plan(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    validate_config(config)
    changed = _changed_files(args.base_sha, args.head_sha)
    mode = "live" if args.base_ref == config["target_base"] else "preview"

    planned: list[dict[str, Any]] = []
    for cluster in config["clusters"]:
        patterns = _manifest_patterns(cluster["manifest"])
        matched = [path for path in changed if any(_matches(path, pattern) for pattern in patterns)]
        planned.append(
            {
                "id": cluster["id"],
                "workflow_file": cluster["workflow_file"],
                "manifest": cluster["manifest"],
                "selected": bool(matched),
                "matched_paths": matched,
            }
        )

    selected = [cluster for cluster in planned if cluster["selected"]]
    evidence = {
        "gate_id": "F7-02",
        "mode": mode,
        "base_ref": args.base_ref,
        "base_sha": args.base_sha,
        "candidate_sha": args.head_sha,
        "changed_files": changed,
        "clusters": planned,
        "expected_cluster_count": len(selected),
        "aggregate_runs": [],
        "status": "planned",
    }
    target = Path(args.evidence)
    target.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    print(f"F7_PR_FAST_MODE={mode}")
    print(f"F7_PR_FAST_CHANGED_COUNT={len(changed)}")
    for path in changed:
        print(f"F7_PR_FAST_CHANGED={path}")
    for cluster in planned:
        print(f"F7_PR_FAST_CLUSTER_{cluster['id']}={'selected' if cluster['selected'] else 'skipped'}")
        for path in cluster["matched_paths"]:
            print(f"F7_PR_FAST_MATCH_{cluster['id']}={path}")
    print(f"F7_PR_FAST_EXPECTED_COUNT={len(selected)}")
    _write_output("mode", mode)
    _write_output("expected_count", str(len(selected)))
    return 0


def _api_json(url: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "rezzerv-f7-pr-fast-gate",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        fail(f"GitHub Actions API HTTP {exc.code}: {body[:500]}")
    except Exception as exc:
        fail(f"GitHub Actions API error: {type(exc).__name__}: {exc}")
    require(isinstance(data, dict), "GitHub Actions API response is not an object")
    return data


def _candidate_run(repo: str, workflow_file: str, candidate_sha: str, token: str) -> dict[str, Any] | None:
    workflow_id = urllib.parse.quote(Path(workflow_file).name, safe="")
    query = urllib.parse.urlencode(
        {
            "event": "pull_request",
            "head_sha": candidate_sha,
            "per_page": 20,
        }
    )
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_id}/runs?{query}"
    data = _api_json(url, token)
    runs = data.get("workflow_runs")
    require(isinstance(runs, list), f"workflow_runs missing for {workflow_file}")
    matching = [run for run in runs if run.get("head_sha") == candidate_sha and run.get("event") == "pull_request"]
    if not matching:
        return None
    matching.sort(key=lambda run: str(run.get("created_at") or ""), reverse=True)
    return matching[0]


def command_wait(args: argparse.Namespace) -> int:
    evidence_path = Path(args.evidence)
    require(evidence_path.is_file(), f"evidence file missing: {args.evidence}")
    evidence = _load_json(evidence_path)
    require(evidence.get("candidate_sha") == args.head_sha, "evidence candidate SHA mismatch")

    selected = [cluster for cluster in evidence.get("clusters", []) if cluster.get("selected")]
    if evidence.get("mode") != "live":
        evidence["status"] = "preview_green"
        evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(f"F7_PR_FAST_PREVIEW_EXPECTED_COUNT={len(selected)}")
        print("F7_PR_FAST_STACKED_PREVIEW_GREEN")
        return 0

    token = os.getenv("GITHUB_TOKEN", "").strip()
    require(token, "GITHUB_TOKEN is required for live aggregation")
    config = load_config(args.config)
    timeout_seconds = int(config.get("timeout_seconds", 7200))
    poll_seconds = int(config.get("poll_seconds", 15))
    require(1 <= poll_seconds <= 60, "poll_seconds out of range")
    require(60 <= timeout_seconds <= 10800, "timeout_seconds out of range")

    deadline = time.monotonic() + timeout_seconds
    resolved: dict[str, dict[str, Any]] = {}
    while True:
        pending: list[str] = []
        for cluster in selected:
            cid = cluster["id"]
            if cid in resolved:
                continue
            run = _candidate_run(args.repo, cluster["workflow_file"], args.head_sha, token)
            if run is None:
                pending.append(f"{cid}:missing")
                continue
            status = str(run.get("status") or "")
            conclusion = run.get("conclusion")
            run_id = run.get("id")
            print(f"F7_PR_FAST_RUN {cid} run={run_id} status={status} conclusion={conclusion}")
            if status != "completed":
                pending.append(f"{cid}:{status or 'unknown'}")
                continue
            if conclusion == "success":
                resolved[cid] = {
                    "id": cid,
                    "workflow_file": cluster["workflow_file"],
                    "run_id": run_id,
                    "conclusion": conclusion,
                    "head_sha": run.get("head_sha"),
                    "html_url": run.get("html_url"),
                }
                continue
            if conclusion in FAILED_CONCLUSIONS or conclusion not in {"success"}:
                fail(f"selected cluster {cid} completed non-success: run={run_id} conclusion={conclusion}")

        if len(resolved) == len(selected):
            break
        if time.monotonic() >= deadline:
            fail(f"timeout waiting for selected clusters: {', '.join(pending)}")
        print(f"F7_PR_FAST_WAITING={','.join(pending)}")
        time.sleep(poll_seconds)

    evidence["aggregate_runs"] = [resolved[cluster["id"]] for cluster in selected]
    evidence["status"] = "green"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"F7_PR_FAST_AGGREGATED_COUNT={len(resolved)}")
    print("F7_PR_FAST_REGRESSION_GATE_GREEN")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate-config")
    validate.add_argument("--config", default="quality/ci/f7_pr_fast_regression_gate.json")
    validate.set_defaults(func=command_validate)

    plan = sub.add_parser("plan")
    plan.add_argument("--config", default="quality/ci/f7_pr_fast_regression_gate.json")
    plan.add_argument("--base-sha", required=True)
    plan.add_argument("--head-sha", required=True)
    plan.add_argument("--base-ref", required=True)
    plan.add_argument("--evidence", default="f7-pr-fast-regression-evidence.json")
    plan.set_defaults(func=command_plan)

    wait = sub.add_parser("wait")
    wait.add_argument("--config", default="quality/ci/f7_pr_fast_regression_gate.json")
    wait.add_argument("--head-sha", required=True)
    wait.add_argument("--repo", required=True)
    wait.add_argument("--evidence", default="f7-pr-fast-regression-evidence.json")
    wait.set_defaults(func=command_wait)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

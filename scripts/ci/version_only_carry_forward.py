#!/usr/bin/env python3
"""Fail-closed carry-forward proof for a canonical final version-only commit."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "quality/ci/change_risk_policy.json"
RELEASE_RE = re.compile(r"^Rezzerv-MVP-v(\d+)\.(\d+)\.(\d+)$")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)


def _emit(name: str, value: str) -> None:
    print(f"CARRY_FORWARD_{name.upper()}={value}")
    target = os.getenv("GITHUB_OUTPUT", "").strip()
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(f"{name.lower()}={value}\n")


def _ensure_commit(root: Path, sha: str) -> bool:
    if not sha:
        return False
    probe = _git(root, "cat-file", "-e", f"{sha}^{{commit}}")
    if probe.returncode == 0:
        return True
    fetch = _git(root, "fetch", "--no-tags", "--depth=1", "origin", sha)
    return fetch.returncode == 0 and _git(root, "cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def load_policy(path: Path = DEFAULT_POLICY) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("policy_id") != "F7-RISK-01":
        raise ValueError("unexpected risk policy")
    return data


def _show(root: Path, sha: str, path: str) -> str | None:
    proc = _git(root, "show", f"{sha}:{path}")
    return proc.stdout if proc.returncode == 0 else None


def _json_at(root: Path, sha: str, path: str) -> dict | None:
    raw = _show(root, sha, path)
    if raw is None:
        return None
    try:
        value = json.loads(raw)
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _release_tuple(value: str) -> tuple[int, int, int] | None:
    match = RELEASE_RE.fullmatch(str(value or "").strip())
    if not match:
        return None
    return tuple(int(match.group(index)) for index in (1, 2, 3))


def _bundle_at(root: Path, sha: str) -> dict | None:
    primary = (_show(root, sha, "VERSION.txt") or "").strip()
    parsed = _release_tuple(primary)
    if not parsed:
        return None
    backend = (_show(root, sha, "backend/VERSION.txt") or "").strip()
    if backend != primary:
        return None
    for path in ("version.json", "frontend/version.json", "frontend/public/version.json"):
        payload = _json_at(root, sha, path)
        if payload is None or str(payload.get("version") or "").strip() != primary:
            return None
    package = _json_at(root, sha, "frontend/package.json")
    if package is None:
        return None
    package_version = str(package.get("version") or "").strip()
    expected_package = f"{parsed[0]}.{parsed[1]}.{parsed[2]}"
    if package_version != expected_package:
        return None
    return {"release": primary, "tuple": parsed, "package_version": package_version}


def _json_version_only(root: Path, before: str, after: str, path: str) -> bool:
    left = _json_at(root, before, path)
    right = _json_at(root, after, path)
    if left is None or right is None:
        return False
    left = dict(left)
    right = dict(right)
    left.pop("version", None)
    right.pop("version", None)
    return left == right


def canonical_version_only_delta(
    root: Path,
    policy: dict,
    before_sha: str,
    after_sha: str,
) -> dict:
    result = {
        "safe": False,
        "reason": "unknown",
        "source_sha": before_sha or "",
        "candidate_sha": after_sha or "",
        "changed_files": [],
    }
    if not before_sha or not after_sha or before_sha == after_sha:
        result["reason"] = "missing_or_equal_sha"
        return result
    if not _ensure_commit(root, before_sha) or not _ensure_commit(root, after_sha):
        result["reason"] = "commit_unavailable"
        return result

    carry = policy.get("version_only_carry_forward") or {}
    bundle = policy.get("version_only_bundle") or {}
    allowed = list(bundle.get("files") or [])
    if not carry.get("enabled") or not allowed:
        result["reason"] = "policy_disabled_or_incomplete"
        return result

    if carry.get("require_direct_parent"):
        parent = _git(root, "rev-parse", f"{after_sha}^").stdout.strip()
        if parent != before_sha:
            result["reason"] = "not_direct_parent"
            return result

    diff = _git(root, "diff", "--name-only", "--diff-filter=ACMRD", before_sha, after_sha)
    if diff.returncode != 0:
        result["reason"] = "git_diff_failed"
        return result
    changed = [line.strip() for line in diff.stdout.splitlines() if line.strip()]
    result["changed_files"] = changed
    if carry.get("require_exact_bundle"):
        if set(changed) != set(allowed):
            result["reason"] = "not_exact_version_bundle"
            return result
    elif not changed or not set(changed).issubset(set(allowed)):
        result["reason"] = "non_version_path_changed"
        return result

    for path in bundle.get("json_version_only_files") or []:
        if path in changed and not _json_version_only(root, before_sha, after_sha, path):
            result["reason"] = f"json_non_version_change:{path}"
            return result

    source = _bundle_at(root, before_sha)
    candidate = _bundle_at(root, after_sha)
    if source is None or candidate is None:
        result["reason"] = "version_bundle_not_synchronized"
        return result

    s_major, s_minor, s_patch = source["tuple"]
    c_major, c_minor, c_patch = candidate["tuple"]
    required_increment = int(carry.get("require_patch_increment", 1))
    if (c_major, c_minor) != (s_major, s_minor) or c_patch != s_patch + required_increment:
        result["reason"] = "not_exact_patch_increment"
        return result

    result.update({
        "safe": True,
        "reason": "canonical_version_only",
        "source_version": source["release"],
        "candidate_version": candidate["release"],
    })
    return result


def _same_pr_base_branch(run: dict, pr_number: str, base_sha: str, branch: str) -> bool:
    if str(run.get("head_branch") or "") != branch:
        return False
    try:
        number = int(pr_number)
    except (TypeError, ValueError):
        return False
    for pr in run.get("pull_requests") or []:
        if pr.get("number") != number:
            continue
        if str((pr.get("base") or {}).get("sha") or "") == base_sha:
            return True
    return False


def prior_success_run(
    repo: str,
    workflow_file: str,
    source_sha: str,
    pr_number: str,
    base_sha: str,
    branch: str,
    token: str,
) -> dict | None:
    workflow_id = urllib.parse.quote(Path(workflow_file).name, safe="")
    query = urllib.parse.urlencode({"event": "pull_request", "head_sha": source_sha, "per_page": 50})
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_id}/runs?{query}"
    request = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "rezzerv-version-only-carry-forward",
    })
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except Exception as exc:
        print(f"CARRY_FORWARD_API_FAIL={type(exc).__name__}:{exc}")
        return None
    runs = [
        run for run in payload.get("workflow_runs", [])
        if run.get("head_sha") == source_sha
        and run.get("event") == "pull_request"
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
        and _same_pr_base_branch(run, pr_number, base_sha, branch)
    ]
    runs.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    return runs[0] if runs else None


def _write_evidence(path: str, payload: dict) -> None:
    if path:
        Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def cmd_detect(args: argparse.Namespace) -> int:
    policy = load_policy(Path(args.policy))
    result = canonical_version_only_delta(ROOT, policy, args.before_sha, args.after_sha)
    _write_evidence(args.evidence, result)
    _emit("safe", "true" if result["safe"] else "false")
    _emit("source_sha", result.get("source_sha", "") if result["safe"] else "")
    _emit("candidate_sha", result.get("candidate_sha", ""))
    _emit("reason", result.get("reason", ""))
    print("VERSION_ONLY_CARRY_FORWARD_DETECT_GREEN")
    return 0


def cmd_workflow(args: argparse.Namespace) -> int:
    evidence = {"reuse": False, "reason": "not_pull_request_synchronize"}
    event_path = Path(args.event)
    if os.getenv("GITHUB_EVENT_NAME", "") != "pull_request" or not event_path.is_file():
        _write_evidence(args.evidence, evidence)
        _emit("reuse", "false")
        _emit("source_sha", "")
        _emit("source_run_id", "")
        print("VERSION_ONLY_CARRY_FORWARD_WORKFLOW_GREEN")
        return 0

    event = json.loads(event_path.read_text(encoding="utf-8"))
    if str(event.get("action") or "") != "synchronize":
        _write_evidence(args.evidence, evidence)
        _emit("reuse", "false")
        _emit("source_sha", "")
        _emit("source_run_id", "")
        print("VERSION_ONLY_CARRY_FORWARD_WORKFLOW_GREEN")
        return 0

    pr = event.get("pull_request") or {}
    before = str(event.get("before") or "").strip()
    after = str(event.get("after") or (pr.get("head") or {}).get("sha") or "").strip()
    base_sha = str((pr.get("base") or {}).get("sha") or "").strip()
    branch = str((pr.get("head") or {}).get("ref") or "").strip()
    pr_number = str(pr.get("number") or event.get("number") or "").strip()
    policy = load_policy(Path(args.policy))
    delta = canonical_version_only_delta(ROOT, policy, before, after)
    evidence = {**delta, "reuse": False, "workflow_file": args.workflow_file}
    if delta["safe"]:
        token = os.getenv("GITHUB_TOKEN", "").strip()
        source_run = prior_success_run(
            args.repo,
            args.workflow_file,
            before,
            pr_number,
            base_sha,
            branch,
            token,
        ) if token else None
        if source_run:
            evidence.update({
                "reuse": True,
                "reason": "canonical_version_only_prior_green",
                "source_run_id": source_run.get("id"),
                "source_run_url": source_run.get("html_url"),
                "pr_number": pr_number,
                "base_sha": base_sha,
                "branch": branch,
            })
        else:
            evidence["reason"] = "canonical_version_only_without_prior_green"

    _write_evidence(args.evidence, evidence)
    _emit("reuse", "true" if evidence["reuse"] else "false")
    _emit("source_sha", evidence.get("source_sha", "") if evidence["reuse"] else "")
    _emit("source_run_id", str(evidence.get("source_run_id") or ""))
    _emit("reason", evidence.get("reason", ""))
    if evidence["reuse"]:
        print(f"VERSION_ONLY_CARRY_FORWARD_REUSED_RUN={evidence['source_run_id']}")
    print("VERSION_ONLY_CARRY_FORWARD_WORKFLOW_GREEN")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    sub = parser.add_subparsers(dest="command", required=True)

    detect = sub.add_parser("detect")
    detect.add_argument("--before-sha", required=True)
    detect.add_argument("--after-sha", required=True)
    detect.add_argument("--evidence", default="")
    detect.set_defaults(func=cmd_detect)

    workflow = sub.add_parser("workflow")
    workflow.add_argument("--repo", required=True)
    workflow.add_argument("--workflow-file", required=True)
    workflow.add_argument("--event", default=os.getenv("GITHUB_EVENT_PATH", ""))
    workflow.add_argument("--evidence", default="")
    workflow.set_defaults(func=cmd_workflow)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

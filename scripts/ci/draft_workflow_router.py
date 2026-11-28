#!/usr/bin/env python3
"""Fail-closed Draft CI router for Inhuis.

Routed workflows keep their normal pull_request path contract for Ready candidates,
but during Draft synchronize cycles they are dispatched only when the latest delta
touches their declared paths or when the same workflow was red on the previous head.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROUTED_MARKER = "# draft-ci-router: routed"
WORKFLOW_DIR = Path(".github/workflows")
CANONICAL_VERSION_FILES = {
    "VERSION.txt",
    "backend/VERSION.txt",
    "version.json",
    "frontend/version.json",
    "frontend/public/version.json",
    "frontend/package.json",
}


def run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def changed_files(old_sha: str, new_sha: str) -> list[str]:
    if not old_sha or not new_sha or old_sha == new_sha:
        return []
    output = run_git("diff", "--name-only", old_sha, new_sha)
    return [line.strip() for line in output.splitlines() if line.strip()]


def is_canonical_version_only_delta(files: list[str]) -> bool:
    return set(files) == CANONICAL_VERSION_FILES


def workflow_name(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip().strip("'\"") or fallback
    return fallback


def extract_pull_request_paths(text: str) -> list[str]:
    lines = text.splitlines()
    pr_index = None
    for index, line in enumerate(lines):
        if line == "  pull_request:":
            pr_index = index
            break
    if pr_index is None:
        return []

    paths_index = None
    for index in range(pr_index + 1, len(lines)):
        line = lines[index]
        if line.startswith("  ") and not line.startswith("    "):
            break
        if line == "    paths:":
            paths_index = index
            break
    if paths_index is None:
        return []

    paths: list[str] = []
    for index in range(paths_index + 1, len(lines)):
        line = lines[index]
        if not line.startswith("      "):
            break
        match = re.match(r"^\s*-\s+(.+?)\s*$", line)
        if not match:
            continue
        value = match.group(1).strip().strip("'\"")
        if value:
            paths.append(value)
    return paths


def glob_regex(pattern: str) -> re.Pattern[str]:
    pieces: list[str] = ["^"]
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if index + 1 < len(pattern) and pattern[index + 1] == "*":
                if index + 2 < len(pattern) and pattern[index + 2] == "/":
                    pieces.append("(?:.*/)?")
                    index += 3
                else:
                    pieces.append(".*")
                    index += 2
                continue
            pieces.append("[^/]*")
        elif char == "?":
            pieces.append("[^/]")
        else:
            pieces.append(re.escape(char))
        index += 1
    pieces.append("$")
    return re.compile("".join(pieces))


def path_matches(path: str, patterns: list[str]) -> bool:
    included = False
    has_positive = any(not pattern.startswith("!") for pattern in patterns)
    if not has_positive:
        included = True
    for raw_pattern in patterns:
        negative = raw_pattern.startswith("!")
        pattern = raw_pattern[1:] if negative else raw_pattern
        if glob_regex(pattern).match(path):
            included = not negative
    return included


def routed_workflows() -> list[dict[str, object]]:
    workflows: list[dict[str, object]] = []
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        if ROUTED_MARKER not in text:
            continue
        paths = extract_pull_request_paths(text)
        if not paths:
            raise RuntimeError(f"{path}: routed workflow mist pull_request.paths")
        if "  workflow_dispatch:" not in text:
            raise RuntimeError(f"{path}: routed workflow mist workflow_dispatch")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if "github.event.pull_request" in line and "||" not in line:
                raise RuntimeError(
                    f"{path}:{line_number}: routed workflow gebruikt pull_request-context zonder workflow_dispatch-fallback"
                )
        workflows.append(
            {
                "path": path.as_posix(),
                "file": path.name,
                "name": workflow_name(text, path.name),
                "paths": paths,
            }
        )
    return workflows


def api_json(repo: str, endpoint: str, token: str) -> dict:
    url = f"https://api.github.com/repos/{repo}/{endpoint.lstrip('/')}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "inhuis-draft-ci-router",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def api_post(repo: str, endpoint: str, token: str, payload: dict | None = None) -> None:
    url = f"https://api.github.com/repos/{repo}/{endpoint.lstrip('/')}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8") if payload is not None else b"",
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "inhuis-draft-ci-router",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status not in (201, 202, 204):
                raise RuntimeError(f"dispatch gaf HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"dispatch faalde: HTTP {exc.code}: {detail}") from exc


ACTIVE_STATUSES = {"queued", "in_progress", "waiting", "requested", "pending"}
RETRY_CONCLUSIONS = {"failure", "cancelled", "timed_out", "action_required", "startup_failure", "stale"}


def runs_for_sha(repo: str, sha: str, token: str) -> list[dict]:
    if not sha:
        return []
    runs = []
    for page in range(1, 11):
        payload = api_json(repo, f"actions/runs?head_sha={urllib.parse.quote(sha)}&per_page=100&page={page}", token)
        batch = payload.get("workflow_runs")
        if not isinstance(batch, list):
            raise RuntimeError("invalid workflow run inventory")
        runs.extend(batch)
        if len(batch) < 100:
            return runs
    raise RuntimeError("workflow run inventory exceeds safe pagination limit")


def latest_runs_by_name(repo: str, sha: str, token: str) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for run in runs_for_sha(repo, sha, token):
        name = str(run.get("name") or "")
        if name and name not in latest:
            latest[name] = run
    return latest


def is_obsolete_router_run(run: dict, *, repo: str, branch: str, old_sha: str,
                           new_sha: str, workflow: dict) -> bool:
    # Only cancel router-dispatched runs, never manual, PR, push or release runs.
    # A matching replacement must already be visible on the current SHA.
    return bool(
        old_sha and old_sha != new_sha and branch not in {"main", "master"}
        and run.get("head_sha") == old_sha
        and run.get("head_branch") == branch
        and (run.get("head_repository") or {}).get("full_name") == repo
        and run.get("event") == "workflow_dispatch"
        and (run.get("actor") or {}).get("login") == "github-actions[bot]"
        and run.get("status") in ACTIVE_STATUSES
        and run.get("path") == workflow["path"]
        and run.get("name") == workflow["name"]
        and isinstance(run.get("id"), int)
    )


def current_draft(repo: str, token: str, number: int, branch: str, sha: str) -> bool:
    pr = api_json(repo, f"pulls/{number}", token)
    head = pr.get("head") or {}
    return bool(pr.get("state") == "open" and pr.get("draft") is True
                and head.get("sha") == sha and head.get("ref") == branch
                and (head.get("repo") or {}).get("full_name") == repo)


def cancel_superseded(repo: str, token: str, number: int, branch: str, old_sha: str,
                      new_sha: str, plan: dict) -> list[int]:
    if not old_sha or old_sha == new_sha or not current_draft(repo, token, number, branch, new_sha):
        return []
    # Prove the previous head is an ancestor, not a force-pushed or unrelated commit.
    if api_json(repo, f"compare/{old_sha}...{new_sha}", token).get("status") != "ahead":
        return []
    # A branch shared by multiple open PRs is ambiguous: do not cancel anything.
    owner = repo.split("/", 1)[0]
    query = urllib.parse.urlencode({"state": "open", "head": f"{owner}:{branch}", "per_page": 100})
    open_prs = api_json(repo, f"pulls?{query}", token)
    if not isinstance(open_prs, list) or len(open_prs) != 1 or open_prs[0].get("number") != number:
        return []
    candidates = {str(item["name"]): item for item in routed_workflows()}
    old_runs = [run for run in runs_for_sha(repo, old_sha, token)
                if (workflow := candidates.get(str(run.get("name") or "")))
                and is_obsolete_router_run(run, repo=repo, branch=branch,
                    old_sha=old_sha, new_sha=new_sha, workflow=workflow)]
    if not old_runs:
        return []
    # GitHub dispatch is asynchronous. Wait only for replacement evidence for
    # eligible obsolete runs; timeout preserves the old run, never cancels blind.
    replacements = {}
    wanted = {str(run["name"]) for run in old_runs}
    for attempt in range(7):
        if not current_draft(repo, token, number, branch, new_sha):
            return []
        replacements = latest_runs_by_name(repo, new_sha, token)
        if wanted.issubset(replacements) or attempt == 6:
            break
        time.sleep(5)
    cancelled = []
    for run in old_runs:
        name = str(run.get("name") or "")
        workflow = candidates.get(name)
        replacement = replacements.get(name, {})
        if not workflow or not is_obsolete_router_run(run, repo=repo, branch=branch,
                old_sha=old_sha, new_sha=new_sha, workflow=workflow):
            continue
        if (replacement.get("head_sha") != new_sha or replacement.get("head_branch") != branch
                or (replacement.get("head_repository") or {}).get("full_name") != repo
                or replacement.get("path") != workflow["path"]
                or not (replacement.get("status") in ACTIVE_STATUSES
                        or replacement.get("conclusion") == "success")):
            continue
        if not current_draft(repo, token, number, branch, new_sha):
            break
        fresh = api_json(repo, f"actions/runs/{run['id']}", token)
        if not is_obsolete_router_run(fresh, repo=repo, branch=branch, old_sha=old_sha,
                                     new_sha=new_sha, workflow=workflow):
            continue
        # Re-read the replacement immediately before cancellation; stale evidence
        # must never authorize cancellation of an older still-useful run.
        replacement_id = replacement.get("id")
        if not isinstance(replacement_id, int) or replacement_id == run["id"]:
            continue
        live = api_json(repo, f"actions/runs/{replacement_id}", token)
        if (live.get("head_sha") != new_sha or live.get("head_branch") != branch
                or (live.get("head_repository") or {}).get("full_name") != repo
                or live.get("path") != workflow["path"]
                or live.get("name") != name
                or not (live.get("status") in ACTIVE_STATUSES
                        or (live.get("status") == "completed" and live.get("conclusion") == "success"))):
            continue
        if not current_draft(repo, token, number, branch, new_sha):
            break
        api_post(repo, f"actions/runs/{run['id']}/cancel", token)
        cancelled.append(run["id"])
    return cancelled


def build_plan(
    *,
    repo: str,
    token: str,
    action: str,
    draft: bool,
    base_sha: str,
    before_sha: str,
    head_sha: str,
) -> dict:
    workflows = routed_workflows()
    by_name = {str(item["name"]): item for item in workflows}

    if action == "synchronize" and draft and before_sha and before_sha != "0" * 40:
        comparison_base = before_sha
        comparison_mode = "latest-delta"
    elif action == "converted_to_draft":
        comparison_base = head_sha
        comparison_mode = "no-delta"
    else:
        comparison_base = base_sha
        comparison_mode = "full-pr"

    files = changed_files(comparison_base, head_sha)
    version_only_delta = is_canonical_version_only_delta(files)
    selected: dict[str, dict] = {}

    if not version_only_delta:
        for workflow in workflows:
            patterns = list(workflow["paths"])
            if any(path_matches(path, patterns) for path in files):
                selected[str(workflow["name"])] = workflow

    previous_failed: list[str] = []
    if action == "synchronize" and before_sha and before_sha != "0" * 40:
        previous_runs = latest_runs_by_name(repo, before_sha, token)
        for name, run in previous_runs.items():
            if name not in by_name:
                continue
            if (run.get("status") in ACTIVE_STATUSES or
                    (run.get("status") == "completed" and run.get("conclusion") in RETRY_CONCLUSIONS)):
                selected[name] = by_name[name]
                previous_failed.append(name)

    current_runs = latest_runs_by_name(repo, head_sha, token)
    dispatch_targets: list[dict] = []
    skipped_existing: list[dict] = []
    for name in sorted(selected):
        workflow = selected[name]
        existing = current_runs.get(name)
        if existing and (
            existing.get("status") in ACTIVE_STATUSES
            or (existing.get("status") == "completed" and existing.get("conclusion") == "success")
        ):
            skipped_existing.append(
                {
                    "name": name,
                    "run_id": existing.get("id"),
                    "status": existing.get("status"),
                    "conclusion": existing.get("conclusion"),
                }
            )
            continue
        dispatch_targets.append(workflow)

    return {
        "schema_version": 1,
        "action": action,
        "draft": draft,
        "comparison_mode": comparison_mode,
        "comparison_base_sha": comparison_base,
        "head_sha": head_sha,
        "changed_files": files,
        "canonical_version_only_delta": version_only_delta,
        "previous_failed_workflows": sorted(previous_failed),
        "selected_workflows": [str(item["name"]) for item in dispatch_targets],
        "dispatch_targets": dispatch_targets,
        "skipped_existing": skipped_existing,
        "routed_workflow_count": len(workflows),
    }


def write_outputs(plan: dict) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"target_count={len(plan['dispatch_targets'])}\n")
        handle.write(f"comparison_mode={plan['comparison_mode']}\n")


def self_test() -> None:
    assert glob_regex("frontend/src/**").match("frontend/src/a/b.jsx")
    assert not glob_regex("frontend/src/*").match("frontend/src/a/b.jsx")
    assert glob_regex("*.md").match("README.md")
    assert not glob_regex("*.md").match("docs/README.md")
    assert path_matches("frontend/src/a.jsx", ["frontend/src/**"])
    assert path_matches("docs/a.md", ["docs/**", "!docs/private/**"])
    assert not path_matches("docs/private/a.md", ["docs/**", "!docs/private/**"])
    assert is_canonical_version_only_delta(sorted(CANONICAL_VERSION_FILES))
    assert not is_canonical_version_only_delta(["frontend/package.json"])
    assert not is_canonical_version_only_delta(sorted(CANONICAL_VERSION_FILES | {"README.md"}))

    sample = """name: Demo
on:
  workflow_dispatch:
  pull_request:
    types:
      - ready_for_review
    paths:
      - 'frontend/src/**'
      - '.github/workflows/demo.yml'

jobs:
  demo:
    runs-on: ubuntu-latest
"""
    assert extract_pull_request_paths(sample) == [
        "frontend/src/**",
        ".github/workflows/demo.yml",
    ]

    safe_dispatch_line = "ref: ${{ github.event.pull_request.head.sha || github.sha }}"
    unsafe_dispatch_line = "ref: ${{ github.event.pull_request.head.sha }}"
    assert "github.event.pull_request" in safe_dispatch_line and "||" in safe_dispatch_line
    assert "github.event.pull_request" in unsafe_dispatch_line and "||" not in unsafe_dispatch_line
    assert path_matches("backend/tests/test_unpacking.py", ["backend/tests/**/*unpacking*"])
    assert path_matches("backend/tests/nested/test_unpacking.py", ["backend/tests/**/*unpacking*"])
    workflow = {"path": ".github/workflows/demo.yml", "name": "Demo"}
    run = {"id": 123, "head_sha": "old", "head_branch": "task", "head_repository": {"full_name": "owner/repo"},
           "event": "workflow_dispatch", "actor": {"login": "github-actions[bot]"}, "status": "queued",
           "path": workflow["path"], "name": "Demo"}
    scope = dict(repo="owner/repo", branch="task", old_sha="old", new_sha="new", workflow=workflow)
    assert is_obsolete_router_run(run, **scope)
    for field, value in (("head_sha", "new"), ("head_branch", "other"), ("event", "push"),
                         ("actor", {"login": "human"}), ("status", "completed"), ("path", "other"),
                         ("head_repository", {"full_name": "other/repo"})):
        assert not is_obsolete_router_run(dict(run, **{field: value}), **scope)
    assert not is_obsolete_router_run(run, **dict(scope, branch="main"))
    # Exercise the actual planner without network calls or production mutations.
    from unittest.mock import patch
    def fixture(name, paths):
        return {"name": name, "path": f".github/workflows/{name}.yml",
                "file": f"{name}.yml", "paths": paths}
    inventory = [fixture("changed", ["backend/tests/a.py"]),
                 fixture("green", ["frontend/**"]),
                 fixture("red", ["docs/**"]),
                 fixture("duplicate", ["backend/tests/a.py"]),
                 fixture("active", ["elsewhere/**"])]
    previous = {"green": {"status": "completed", "conclusion": "success"},
                "red": {"status": "completed", "conclusion": "failure"},
                "active": {"status": "in_progress"}}
    current = {"duplicate": {"status": "queued", "id": 1234}}
    module = sys.modules[__name__]
    with patch.object(module, "routed_workflows", return_value=inventory), \
         patch.object(module, "changed_files", return_value=["backend/tests/a.py"]), \
         patch.object(module, "latest_runs_by_name", side_effect=[previous, current]):
        plan = build_plan(repo="owner/repo", token="test", action="synchronize",
                          draft=True, base_sha="base", before_sha="old", head_sha="new")
    assert plan["comparison_mode"] == "latest-delta"
    assert set(plan["selected_workflows"]) == {"changed", "red", "active"}, plan
    assert [item["name"] for item in plan["skipped_existing"]] == ["duplicate"], plan
    replacement = dict(run, head_sha="new", id=456)
    with patch.object(module, "current_draft", return_value=True), \
         patch.object(module, "routed_workflows", return_value=[workflow]), \
         patch.object(module, "latest_runs_by_name", return_value={"Demo": replacement}), \
         patch.object(module, "runs_for_sha", return_value=[run]), \
         patch.object(module, "api_json", side_effect=[{"status": "ahead"}, [{"number": 1}], run, replacement]), \
         patch.object(module, "api_post") as post:
        assert cancel_superseded("owner/repo", "test", 1, "task", "old", "new", {}) == [123]
        post.assert_called_once_with("owner/repo", "actions/runs/123/cancel", "test")
    with patch.object(module, "current_draft", return_value=True), \
         patch.object(module, "routed_workflows", return_value=[workflow]), \
         patch.object(module, "latest_runs_by_name", return_value={}), \
         patch.object(time, "sleep"), \
         patch.object(module, "api_json", side_effect=[{"status": "ahead"}, [{"number": 1}]]), \
         patch.object(module, "runs_for_sha", return_value=[run]), \
         patch.object(module, "api_post") as post:
        assert cancel_superseded("owner/repo", "test", 1, "task", "old", "new", {}) == []
        post.assert_not_called()
    with patch.object(module, "current_draft", return_value=True), \
         patch.object(module, "routed_workflows", return_value=[workflow]), \
         patch.object(module, "latest_runs_by_name", side_effect=[{}, {"Demo": replacement}]), \
         patch.object(module, "runs_for_sha", return_value=[run]), \
         patch.object(module, "api_json", side_effect=[{"status": "ahead"}, [{"number": 1}], run, replacement]), \
         patch.object(time, "sleep") as wait, \
         patch.object(module, "api_post") as post:
        assert cancel_superseded("owner/repo", "test", 1, "task", "old", "new", {}) == [123]
        wait.assert_called_once_with(5)
        post.assert_called_once_with("owner/repo", "actions/runs/123/cancel", "test")
    for responses in ([{"status": "diverged"}],
                      [{"status": "ahead"}, [{"number": 1}, {"number": 2}]],
                      [{"status": "ahead"}, [{"number": 2}]]):
        with patch.object(module, "current_draft", return_value=True), \
             patch.object(module, "api_json", side_effect=responses), \
             patch.object(module, "api_post") as post:
            assert cancel_superseded("owner/repo", "test", 1, "task", "old", "new", {}) == []
            post.assert_not_called()
    for invalid in (dict(replacement, status="completed", conclusion="failure"),
                    dict(replacement, head_sha="other"),
                    dict(replacement, head_branch="other")):
        with patch.object(module, "current_draft", return_value=True), \
             patch.object(module, "routed_workflows", return_value=[workflow]), \
             patch.object(module, "latest_runs_by_name", return_value={"Demo": replacement}), \
             patch.object(module, "runs_for_sha", return_value=[run]), \
             patch.object(module, "api_json", side_effect=[{"status": "ahead"}, [{"number": 1}], run, invalid]), \
             patch.object(module, "api_post") as post:
            assert cancel_superseded("owner/repo", "test", 1, "task", "old", "new", {}) == []
            post.assert_not_called()
    print("DRAFT_CI_ROUTER_PLANNER_AND_CANCEL_CONTRACT_GREEN")
    print("DRAFT_CI_ROUTER_SELF_TEST_GREEN")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("self-test")

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--repo", required=True)
    run_parser.add_argument("--action", required=True)
    run_parser.add_argument("--draft", required=True)
    run_parser.add_argument("--base-sha", required=True)
    run_parser.add_argument("--before-sha", default="")
    run_parser.add_argument("--head-sha", required=True)
    run_parser.add_argument("--head-ref", required=True)
    run_parser.add_argument("--pr-number", type=int, default=0)
    run_parser.add_argument("--evidence", default="draft-ci-router-plan.json")

    args = parser.parse_args()
    if args.command == "self-test":
        self_test()
        return 0

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("GITHUB_TOKEN ontbreekt")

    draft = str(args.draft).strip().lower() == "true"
    plan = build_plan(
        repo=args.repo,
        token=token,
        action=args.action,
        draft=draft,
        base_sha=args.base_sha,
        before_sha=args.before_sha,
        head_sha=args.head_sha,
    )
    Path(args.evidence).write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"ROUTER_COMPARISON_MODE={plan['comparison_mode']}")
    print(f"ROUTER_CHANGED_FILE_COUNT={len(plan['changed_files'])}")
    print(f"ROUTER_CANONICAL_VERSION_ONLY_DELTA={'true' if plan['canonical_version_only_delta'] else 'false'}")
    print(f"ROUTER_ROUTED_WORKFLOW_COUNT={plan['routed_workflow_count']}")
    print(f"ROUTER_TARGET_COUNT={len(plan['dispatch_targets'])}")
    for item in plan["dispatch_targets"]:
        print(f"ROUTER_TARGET={item['file']}")
    for item in plan["skipped_existing"]:
        print(f"ROUTER_REUSE_EXISTING={item['name']}:{item['status']}:{item.get('conclusion')}")

    for item in plan["dispatch_targets"]:
        if draft and args.pr_number and not current_draft(args.repo, token, args.pr_number, args.head_ref, args.head_sha):
            raise RuntimeError("Draft candidate changed before dispatch")
        existing = latest_runs_by_name(args.repo, args.head_sha, token).get(str(item["name"]), {})
        if existing.get("status") in ACTIVE_STATUSES or existing.get("conclusion") == "success":
            print(f"ROUTER_REUSE_LIVE={item['file']}")
            continue
        file_name = str(item["file"])
        api_post(
            args.repo,
            f"actions/workflows/{urllib.parse.quote(file_name)}/dispatches",
            token,
            {"ref": args.head_ref},
        )
        print(f"ROUTER_DISPATCHED={file_name}")

    if draft and args.action == "synchronize" and args.pr_number:
        plan["cancelled_obsolete_runs"] = cancel_superseded(args.repo, token, args.pr_number, args.head_ref, args.before_sha, args.head_sha, plan)
        Path(args.evidence).write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"ROUTER_CANCELLED_OBSOLETE={len(plan['cancelled_obsolete_runs'])}")
    write_outputs(plan)
    print("DRAFT_CI_ROUTER_GREEN")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"DRAFT_CI_ROUTER_ERROR={exc}", file=sys.stderr)
        raise

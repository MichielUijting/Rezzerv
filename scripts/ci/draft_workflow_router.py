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
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROUTED_MARKER = "# draft-ci-router: routed"
WORKFLOW_DIR = Path(".github/workflows")


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


def api_post(repo: str, endpoint: str, token: str, payload: dict) -> None:
    url = f"https://api.github.com/repos/{repo}/{endpoint.lstrip('/')}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
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
            if response.status not in (201, 204):
                raise RuntimeError(f"dispatch gaf HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"dispatch faalde: HTTP {exc.code}: {detail}") from exc


def latest_runs_by_name(repo: str, sha: str, token: str) -> dict[str, dict]:
    if not sha:
        return {}
    payload = api_json(repo, f"actions/runs?head_sha={urllib.parse.quote(sha)}&per_page=100", token)
    latest: dict[str, dict] = {}
    for run in payload.get("workflow_runs", []):
        name = str(run.get("name") or "")
        if name and name not in latest:
            latest[name] = run
    return latest


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

    if action == "synchronize" and draft and before_sha:
        comparison_base = before_sha
        comparison_mode = "latest-delta"
    elif action == "converted_to_draft":
        comparison_base = head_sha
        comparison_mode = "no-delta"
    else:
        comparison_base = base_sha
        comparison_mode = "full-pr"

    files = changed_files(comparison_base, head_sha)
    selected: dict[str, dict] = {}

    for workflow in workflows:
        patterns = list(workflow["paths"])
        if any(path_matches(path, patterns) for path in files):
            selected[str(workflow["name"])] = workflow

    previous_failed: list[str] = []
    if action == "synchronize" and before_sha:
        previous_runs = latest_runs_by_name(repo, before_sha, token)
        for name, run in previous_runs.items():
            if name not in by_name:
                continue
            if run.get("status") == "completed" and run.get("conclusion") == "failure":
                selected[name] = by_name[name]
                previous_failed.append(name)

    current_runs = latest_runs_by_name(repo, head_sha, token)
    dispatch_targets: list[dict] = []
    skipped_existing: list[dict] = []
    for name in sorted(selected):
        workflow = selected[name]
        existing = current_runs.get(name)
        if existing and (
            existing.get("status") in {"queued", "in_progress"}
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
    print(f"ROUTER_ROUTED_WORKFLOW_COUNT={plan['routed_workflow_count']}")
    print(f"ROUTER_TARGET_COUNT={len(plan['dispatch_targets'])}")
    for item in plan["dispatch_targets"]:
        print(f"ROUTER_TARGET={item['file']}")
    for item in plan["skipped_existing"]:
        print(f"ROUTER_REUSE_EXISTING={item['name']}:{item['status']}:{item.get('conclusion')}")

    for item in plan["dispatch_targets"]:
        file_name = str(item["file"])
        api_post(
            args.repo,
            f"actions/workflows/{urllib.parse.quote(file_name)}/dispatches",
            token,
            {"ref": args.head_ref},
        )
        print(f"ROUTER_DISPATCHED={file_name}")

    write_outputs(plan)
    print("DRAFT_CI_ROUTER_GREEN")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"DRAFT_CI_ROUTER_ERROR={exc}", file=sys.stderr)
        raise

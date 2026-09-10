#!/usr/bin/env python3
"""Fail-open PR delta gate for expensive GitHub Actions jobs.

GitHub's pull_request.path filters are evaluated against the full PR diff. That means
an expensive workflow is scheduled again on every synchronize event as long as any
file anywhere in the PR still matches its paths list, even when the latest push only
changed unrelated documentation or audit metadata.

This helper preserves the first/opened run and workflow_dispatch behavior, but on a
pull_request synchronize event it compares the previous PR head with the new head and
checks only that pushed delta against the workflow's own pull_request.paths patterns.
If the event payload is incomplete, the git comparison cannot be made, or the workflow
uses path negation, it deliberately fails open and requests the expensive job.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def _emit(name: str, value: str) -> None:
    print(f"{name}={value}")
    output = os.getenv("GITHUB_OUTPUT", "").strip()
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"{name.lower()}={value}\n")


def _fail_open(reason: str) -> int:
    print(f"CI_DELTA_FAIL_OPEN={reason}")
    _emit("RUN", "true")
    _emit("MATCH_COUNT", "0")
    return 0


def _extract_pull_request_paths(workflow_path: Path) -> list[str]:
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


def _matches(path: str, pattern: str) -> bool:
    # fnmatch treats '/' as an ordinary character and is therefore at least as broad
    # as the path matching we need here. A broad match can only make us run more,
    # never skip a relevant expensive job.
    if fnmatch.fnmatchcase(path, pattern):
        return True
    # GitHub's foo/** convention also covers the directory itself; normalize a
    # trailing '/**' to a prefix check for conservative compatibility.
    if pattern.endswith("/**") and path.startswith(pattern[:-3]):
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--event", default=os.getenv("GITHUB_EVENT_PATH", ""))
    args = parser.parse_args()

    workflow_path = Path(args.workflow)
    if not workflow_path.is_file():
        return _fail_open(f"workflow_missing:{workflow_path}")

    event_name = os.getenv("GITHUB_EVENT_NAME", "").strip()
    if event_name != "pull_request":
        print(f"CI_DELTA_EVENT={event_name or 'unknown'}")
        return _fail_open("non_pull_request_event")

    if not args.event or not Path(args.event).is_file():
        return _fail_open("event_payload_missing")

    try:
        event = json.loads(Path(args.event).read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - CI fail-open safety path
        return _fail_open(f"event_payload_invalid:{type(exc).__name__}")

    action = str(event.get("action") or "").strip()
    print(f"CI_DELTA_ACTION={action or 'unknown'}")
    if action != "synchronize":
        return _fail_open(f"action_{action or 'unknown'}_must_run")

    before = str(event.get("before") or "").strip()
    after = str(event.get("after") or event.get("pull_request", {}).get("head", {}).get("sha") or "").strip()
    if not before or not after or before == after:
        return _fail_open("before_after_unavailable")

    patterns = _extract_pull_request_paths(workflow_path)
    if not patterns:
        return _fail_open("no_paths_found")
    if any(pattern.startswith("!") for pattern in patterns):
        return _fail_open("negative_path_pattern")

    # actions/checkout generally has the new head only. Fetch the old head cheaply;
    # failure remains safe because we then run the expensive job.
    probe = _run(["git", "cat-file", "-e", f"{before}^{{commit}}"])
    if probe.returncode != 0:
        fetched = _run(["git", "fetch", "--no-tags", "--depth=1", "origin", before])
        if fetched.returncode != 0:
            print(fetched.stderr.strip())
            return _fail_open("before_fetch_failed")

    diff = _run(["git", "diff", "--name-only", "--diff-filter=ACMR", before, after])
    if diff.returncode != 0:
        print(diff.stderr.strip())
        return _fail_open("git_diff_failed")

    changed = [line.strip() for line in diff.stdout.splitlines() if line.strip()]
    matched = [path for path in changed if any(_matches(path, pattern) for pattern in patterns)]

    print(f"CI_DELTA_BEFORE={before}")
    print(f"CI_DELTA_AFTER={after}")
    print(f"CI_DELTA_CHANGED_COUNT={len(changed)}")
    for path in changed:
        print(f"CI_DELTA_CHANGED={path}")
    for path in matched:
        print(f"CI_DELTA_MATCH={path}")

    _emit("RUN", "true" if matched else "false")
    _emit("MATCH_COUNT", str(len(matched)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

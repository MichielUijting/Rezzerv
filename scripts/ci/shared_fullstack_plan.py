#!/usr/bin/env python3
"""Plan which authorities need a shared full-stack runner.

For pull_request synchronize events this compares the complete candidate delta
(base SHA -> current head SHA) against authority-specific path patterns. This
ensures every selected authority is re-proven on the exact candidate consumed by
F7 PR Fast Regression. Open/reopened/manual runs remain fail-open and run the
requested authorities. Any uncertainty schedules all authorities rather than
risking a false skip.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
from pathlib import Path


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def _emit(name: str, value: str) -> None:
    print(f"{name.upper()}={value}")
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


def _emit_plan(plan: dict[str, bool], reason: str) -> int:
    print(f"SHARED_FULLSTACK_PLAN_REASON={reason}")
    for name, run in plan.items():
        _emit(name, "true" if run else "false")
    _emit("any", "true" if any(plan.values()) else "false")
    return 0


def _fail_open(authorities: list[str], reason: str) -> int:
    print(f"SHARED_FULLSTACK_FAIL_OPEN={reason}")
    return _emit_plan({name: True for name in authorities}, reason)


def _parse_fallback_authorities(raw: str) -> list[str]:
    values = [part.strip() for part in raw.split(",") if part.strip()]
    return values or ["p0_kassa", "f6_kassa"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--event", default=os.getenv("GITHUB_EVENT_PATH", ""))
    parser.add_argument("--manual-authority", default=os.getenv("INPUT_AUTHORITY", "both"))
    parser.add_argument("--fallback-authorities", default="p0_kassa,f6_kassa")
    args = parser.parse_args()

    fallback = _parse_fallback_authorities(args.fallback_authorities)
    manifest_path = Path(args.manifest)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        authorities_cfg = manifest["authorities"]
        authorities = list(authorities_cfg)
        if not authorities:
            raise ValueError("empty authorities")
        for name in authorities:
            paths = authorities_cfg[name].get("paths")
            if not isinstance(paths, list) or not paths:
                raise ValueError(f"invalid paths for {name}")
    except Exception as exc:
        return _fail_open(fallback, f"manifest_invalid:{type(exc).__name__}")

    event_name = os.getenv("GITHUB_EVENT_NAME", "").strip()
    if event_name == "workflow_dispatch":
        requested = (args.manual_authority or "both").strip().lower()
        if requested == "both":
            return _emit_plan({name: True for name in authorities}, "manual_both")
        selected = requested.replace("-", "_")
        if selected not in authorities:
            return _fail_open(authorities, f"manual_unknown:{requested}")
        return _emit_plan({name: name == selected for name in authorities}, f"manual_{selected}")

    if event_name != "pull_request":
        return _fail_open(authorities, f"event_{event_name or 'unknown'}")

    if not args.event or not Path(args.event).is_file():
        return _fail_open(authorities, "event_payload_missing")
    try:
        event = json.loads(Path(args.event).read_text(encoding="utf-8"))
    except Exception as exc:
        return _fail_open(authorities, f"event_payload_invalid:{type(exc).__name__}")

    action = str(event.get("action") or "").strip()
    print(f"SHARED_FULLSTACK_ACTION={action or 'unknown'}")
    if action != "synchronize":
        return _fail_open(authorities, f"action_{action or 'unknown'}_must_run")

    pull_request = event.get("pull_request") or {}
    base_sha = str((pull_request.get("base") or {}).get("sha") or "").strip()
    head_sha = str((pull_request.get("head") or {}).get("sha") or event.get("after") or "").strip()
    if not base_sha or not head_sha or base_sha == head_sha:
        return _fail_open(authorities, "candidate_base_head_unavailable")

    probe = _run(["git", "cat-file", "-e", f"{base_sha}^{{commit}}"])
    if probe.returncode != 0:
        fetched = _run(["git", "fetch", "--no-tags", "--depth=1", "origin", base_sha])
        if fetched.returncode != 0:
            print(fetched.stderr.strip())
            return _fail_open(authorities, "candidate_base_fetch_failed")

    diff = _run(["git", "diff", "--name-only", "--diff-filter=ACMRD", base_sha, head_sha])
    if diff.returncode != 0:
        print(diff.stderr.strip())
        return _fail_open(authorities, "candidate_git_diff_failed")

    changed = [line.strip() for line in diff.stdout.splitlines() if line.strip()]
    print(f"SHARED_FULLSTACK_CANDIDATE_BASE={base_sha}")
    print(f"SHARED_FULLSTACK_CANDIDATE_HEAD={head_sha}")
    print(f"SHARED_FULLSTACK_CHANGED_COUNT={len(changed)}")
    for path in changed:
        print(f"SHARED_FULLSTACK_CHANGED={path}")

    plan: dict[str, bool] = {}
    for name in authorities:
        patterns = [str(value) for value in authorities_cfg[name]["paths"]]
        if any(pattern.startswith("!") for pattern in patterns):
            return _fail_open(authorities, f"negative_pattern:{name}")
        matched = [path for path in changed if any(_matches(path, pattern) for pattern in patterns)]
        for path in matched:
            print(f"SHARED_FULLSTACK_MATCH_{name.upper()}={path}")
        plan[name] = bool(matched)

    return _emit_plan(plan, "synchronize_candidate")


if __name__ == "__main__":
    raise SystemExit(main())

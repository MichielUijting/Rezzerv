#!/usr/bin/env python3
"""Plan shared full-stack authorities with fail-closed incremental carry-forward.

The complete base->head PR delta still determines which authorities are relevant.
On pull_request synchronize events, a previously green run from the same
PR/base/branch may be carried forward per authority when the latest
previous-head->new-head delta does not touch that authority's declared paths.

Any uncertainty (missing prior green evidence, missing commits, negative patterns,
or an unmapped sensitive incremental path) falls back to rerunning the authority.
F7 Full exact-candidate evidence is intentionally outside this planner.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
from pathlib import Path

from version_only_carry_forward import canonical_version_only_delta, load_policy, prior_success_run

SENSITIVE_INCREMENTAL_PATTERNS = (
    "backend/**",
    "frontend/src/**",
    "frontend/tests/e2e/**",
    "frontend/playwright*.js",
    "frontend/package.json",
    "frontend/package-lock.json",
    "docker/**",
    "docker-compose*.yml",
    "quality/acceptance/**",
    "quality/ci/**",
    "scripts/acceptance/**",
    "scripts/ci/**",
    ".github/workflows/**",
)


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


def _matches_any(path: str, patterns: list[str] | tuple[str, ...]) -> bool:
    return any(_matches(path, pattern) for pattern in patterns)


def _ensure_commit(sha: str) -> bool:
    if not sha:
        return False
    probe = _run(["git", "cat-file", "-e", f"{sha}^{{commit}}"])
    if probe.returncode == 0:
        return True
    fetched = _run(["git", "fetch", "--no-tags", "--depth=1", "origin", sha])
    return fetched.returncode == 0 and _run(["git", "cat-file", "-e", f"{sha}^{{commit}}"]).returncode == 0


def _changed_files(before: str, after: str) -> list[str] | None:
    if not _ensure_commit(before) or not _ensure_commit(after):
        return None
    diff = _run(["git", "diff", "--name-only", "--diff-filter=ACMRD", before, after])
    if diff.returncode != 0:
        print(diff.stderr.strip())
        return None
    return [line.strip() for line in diff.stdout.splitlines() if line.strip()]


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


def _authority_patterns(authorities_cfg: dict) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for name, cfg in authorities_cfg.items():
        patterns = [str(value) for value in cfg.get("paths") or []]
        if not patterns or any(pattern.startswith("!") for pattern in patterns):
            raise ValueError(f"invalid_paths:{name}")
        result[name] = patterns
    return result


def select_authority_plan(
    authorities_cfg: dict,
    complete_changed: list[str],
    incremental_changed: list[str] | None = None,
    prior_green: bool = False,
) -> tuple[dict[str, bool], list[str], list[str]]:
    """Return (plan, carried_authorities, unmapped_sensitive_paths)."""
    patterns_by_authority = _authority_patterns(authorities_cfg)
    complete_plan = {
        name: any(_matches_any(path, patterns) for path in complete_changed)
        for name, patterns in patterns_by_authority.items()
    }
    all_patterns = [pattern for patterns in patterns_by_authority.values() for pattern in patterns]
    complete_unmapped_sensitive = [
        path
        for path in complete_changed
        if _matches_any(path, SENSITIVE_INCREMENTAL_PATTERNS)
        and not _matches_any(path, all_patterns)
    ]
    if complete_unmapped_sensitive:
        return {name: True for name in authorities_cfg}, [], complete_unmapped_sensitive

    if not prior_green or incremental_changed is None:
        return complete_plan, [], []

    unmapped_sensitive = [
        path
        for path in incremental_changed
        if _matches_any(path, SENSITIVE_INCREMENTAL_PATTERNS)
        and not _matches_any(path, all_patterns)
    ]
    if unmapped_sensitive:
        return {name: True for name in authorities_cfg}, [], unmapped_sensitive

    plan: dict[str, bool] = {}
    carried: list[str] = []
    for name, patterns in patterns_by_authority.items():
        if not complete_plan[name]:
            plan[name] = False
            continue
        incremental_match = any(_matches_any(path, patterns) for path in incremental_changed)
        plan[name] = incremental_match
        if not incremental_match:
            carried.append(name)
    return plan, carried, []


def _workflow_file_from_ref(repo: str) -> str:
    workflow_ref = os.getenv("GITHUB_WORKFLOW_REF", "")
    marker = f"{repo}/"
    if repo and marker in workflow_ref:
        return workflow_ref.split(marker, 1)[1].split("@", 1)[0]
    return ""


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
        _authority_patterns(authorities_cfg)
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
    previous_sha = str(event.get("before") or "").strip()
    branch = str((pull_request.get("head") or {}).get("ref") or "").strip()
    pr_number = str(pull_request.get("number") or event.get("number") or "").strip()
    if not base_sha or not head_sha or base_sha == head_sha:
        return _fail_open(authorities, "candidate_base_head_unavailable")

    complete_changed = _changed_files(base_sha, head_sha)
    if complete_changed is None:
        return _fail_open(authorities, "candidate_git_diff_failed")
    print(f"SHARED_FULLSTACK_CANDIDATE_BASE={base_sha}")
    print(f"SHARED_FULLSTACK_CANDIDATE_HEAD={head_sha}")
    print(f"SHARED_FULLSTACK_CHANGED_COUNT={len(complete_changed)}")
    for path in complete_changed:
        print(f"SHARED_FULLSTACK_CHANGED={path}")

    try:
        complete_plan, _, _ = select_authority_plan(authorities_cfg, complete_changed)
    except Exception as exc:
        return _fail_open(authorities, f"candidate_plan_invalid:{type(exc).__name__}")

    if not previous_sha or previous_sha == head_sha:
        return _emit_plan(complete_plan, "synchronize_complete_candidate_no_previous_head")

    incremental_changed = _changed_files(previous_sha, head_sha)
    if incremental_changed is None:
        return _emit_plan(complete_plan, "synchronize_complete_candidate_incremental_diff_unavailable")
    print(f"SHARED_FULLSTACK_INCREMENTAL_BEFORE={previous_sha}")
    print(f"SHARED_FULLSTACK_INCREMENTAL_AFTER={head_sha}")
    print(f"SHARED_FULLSTACK_INCREMENTAL_CHANGED_COUNT={len(incremental_changed)}")
    for path in incremental_changed:
        print(f"SHARED_FULLSTACK_INCREMENTAL_CHANGED={path}")

    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    token = os.getenv("GITHUB_TOKEN", "").strip()
    workflow_file = _workflow_file_from_ref(repo)
    prior = None
    if repo and token and workflow_file and pr_number and branch:
        prior = prior_success_run(
            repo,
            workflow_file,
            previous_sha,
            pr_number,
            base_sha,
            branch,
            token,
        )

    # Preserve the stricter canonical version-only proof as the fastest special case.
    try:
        carry = canonical_version_only_delta(
            Path(__file__).resolve().parents[2],
            load_policy(),
            previous_sha,
            head_sha,
        )
    except Exception as exc:
        print(f"SHARED_FULLSTACK_VERSION_CARRY_FAIL_OPEN={type(exc).__name__}:{exc}")
        carry = {"safe": False}
    if carry.get("safe") and prior:
        print(f"SHARED_FULLSTACK_CARRY_FORWARD_SOURCE={previous_sha}")
        print(f"SHARED_FULLSTACK_CARRY_FORWARD_RUN={prior.get('id')}")
        for name, required in complete_plan.items():
            if required:
                print(f"SHARED_FULLSTACK_CARRIED_AUTHORITY={name}")
        return _emit_plan({name: False for name in authorities}, "canonical_version_only_carry_forward")

    if not prior:
        print("SHARED_FULLSTACK_INCREMENTAL_CARRY_FORWARD=false")
        return _emit_plan(complete_plan, "synchronize_complete_candidate_prior_green_missing")

    try:
        plan, carried, unmapped = select_authority_plan(
            authorities_cfg,
            complete_changed,
            incremental_changed,
            prior_green=True,
        )
    except Exception as exc:
        return _emit_plan(complete_plan, f"synchronize_complete_candidate_incremental_error_{type(exc).__name__}")

    if unmapped:
        for path in unmapped:
            print(f"SHARED_FULLSTACK_UNMAPPED_SENSITIVE={path}")
        return _emit_plan(complete_plan, "synchronize_complete_candidate_unmapped_sensitive_delta")

    print("SHARED_FULLSTACK_INCREMENTAL_CARRY_FORWARD=true")
    print(f"SHARED_FULLSTACK_CARRY_FORWARD_SOURCE={previous_sha}")
    print(f"SHARED_FULLSTACK_CARRY_FORWARD_RUN={prior.get('id')}")
    for name in carried:
        print(f"SHARED_FULLSTACK_CARRIED_AUTHORITY={name}")
    for name, run in plan.items():
        if run:
            print(f"SHARED_FULLSTACK_RERUN_AUTHORITY={name}")
    return _emit_plan(plan, "synchronize_incremental_prior_green")


if __name__ == "__main__":
    raise SystemExit(main())

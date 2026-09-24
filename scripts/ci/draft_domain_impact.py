#!/usr/bin/env python3
"""Fail-closed Draft domain-impact planner for expensive PR authorities."""
from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import os
import subprocess
from pathlib import Path

from version_only_carry_forward import prior_success_run

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "quality/ci/draft_domain_impact_policy.json"
MIGRATION_PREFIX = "backend/alembic/versions/"


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)


def emit(name: str, value: str) -> None:
    print(f"{name.upper()}={value}")
    output = os.getenv("GITHUB_OUTPUT", "").strip()
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"{name.lower()}={value}\n")


def load_policy(path: Path = DEFAULT_POLICY) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("policy_id") != "CI-DRAFT-IMPACT-01":
        raise ValueError("invalid draft domain-impact policy identity")
    allowed = data.get("allowed_domains")
    if not isinstance(allowed, list) or not allowed or len(allowed) != len(set(allowed)):
        raise ValueError("invalid allowed_domains")
    workflows = data.get("workflow_domains")
    if not isinstance(workflows, dict) or not workflows:
        raise ValueError("workflow_domains missing")
    if any(domain not in allowed for domain in workflows.values()):
        raise ValueError("workflow domain outside allowed_domains")
    return data


def ensure_commit(sha: str) -> bool:
    if not sha:
        return False
    if run(["git", "cat-file", "-e", f"{sha}^{{commit}}"]).returncode == 0:
        return True
    fetched = run(["git", "fetch", "--no-tags", "--depth=1", "origin", sha])
    return fetched.returncode == 0 and run(["git", "cat-file", "-e", f"{sha}^{{commit}}"]).returncode == 0


def changed_files(base: str, head: str, *, name_status: bool = False) -> list[str] | None:
    if not ensure_commit(base) or not ensure_commit(head):
        return None
    args = ["git", "diff", "--name-status" if name_status else "--name-only", "--diff-filter=ACMRD", base, head]
    result = run(args)
    if result.returncode != 0:
        print(result.stderr.strip())
        return None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def match(path: str, pattern: str) -> bool:
    if fnmatch.fnmatchcase(path, pattern):
        return True
    return pattern.endswith("/**") and path.startswith(pattern[:-3])


def workflow_paths(workflow: Path) -> list[str]:
    lines = workflow.read_text(encoding="utf-8").splitlines()
    in_pr = False
    pr_indent = -1
    in_paths = False
    paths_indent = -1
    patterns: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        if stripped.startswith("pull_request:"):
            in_pr = True
            pr_indent = indent
            in_paths = False
            continue
        if in_pr and indent <= pr_indent and not stripped.startswith("pull_request:"):
            break
        if in_pr and stripped == "paths:":
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
    if not patterns or any(pattern.startswith("!") for pattern in patterns):
        raise ValueError("invalid workflow pull_request.paths")
    return patterns


def migration_domains(path: str, policy: dict) -> set[str] | None:
    target = ROOT / path
    if not target.is_file():
        return None
    try:
        tree = ast.parse(target.read_text(encoding="utf-8"), filename=path)
    except Exception:
        return None
    constant = policy["migration_metadata_constant"]
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == constant for target in targets):
            continue
        value_node = node.value
        try:
            value = ast.literal_eval(value_node)
        except Exception:
            return None
        if not isinstance(value, (tuple, list, set)) or not value:
            return None
        domains = {str(item).strip() for item in value if str(item).strip()}
        allowed = set(policy["allowed_domains"])
        if not domains or not domains <= allowed:
            return None
        return domains
    return None


def relevant(path: str, patterns: list[str], domain: str, policy: dict) -> tuple[bool, str]:
    if path.startswith(MIGRATION_PREFIX) and path.endswith(".py"):
        domains = migration_domains(path, policy)
        if domains is None:
            return True, "migration_metadata_unknown_fail_closed"
        if policy["shared_domain"] in domains or domain in domains:
            return True, "migration_impacts_domain"
        return False, "migration_other_domain"
    direct_patterns = [pattern for pattern in patterns if pattern != "backend/alembic/**"]
    return any(match(path, pattern) for pattern in direct_patterns), "direct_workflow_path"


def relevance(paths: list[str], patterns: list[str], domain: str, policy: dict) -> tuple[bool, list[tuple[str, str]]]:
    hits: list[tuple[str, str]] = []
    for path in paths:
        is_relevant, reason = relevant(path, patterns, domain, policy)
        if is_relevant:
            hits.append((path, reason))
    return bool(hits), hits


def fail_open(reason: str) -> int:
    print(f"DRAFT_DOMAIN_IMPACT_FAIL_OPEN={reason}")
    emit("run_heavy", "true")
    emit("reason", reason)
    print("DRAFT_DOMAIN_IMPACT_GREEN")
    return 0


def plan(args: argparse.Namespace) -> int:
    try:
        policy = load_policy(Path(args.policy))
    except Exception as exc:
        return fail_open(f"policy_invalid:{type(exc).__name__}")

    expected_domain = (policy.get("workflow_domains") or {}).get(args.workflow)
    if expected_domain != args.domain:
        return fail_open("workflow_domain_mapping_mismatch")
    if args.domain not in policy["allowed_domains"]:
        return fail_open("unknown_domain")

    event_name = os.getenv("GITHUB_EVENT_NAME", "").strip()
    if event_name != "pull_request":
        emit("run_heavy", "true")
        emit("reason", f"event_{event_name or 'unknown'}")
        print("DRAFT_DOMAIN_IMPACT_GREEN")
        return 0

    event_path = Path(args.event)
    if not event_path.is_file():
        return fail_open("event_payload_missing")
    try:
        event = json.loads(event_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return fail_open(f"event_payload_invalid:{type(exc).__name__}")

    pr = event.get("pull_request") or {}
    if not bool(pr.get("draft", False)):
        emit("run_heavy", "true")
        emit("reason", "non_draft_candidate")
        print("DRAFT_DOMAIN_IMPACT_GREEN")
        return 0

    base = str((pr.get("base") or {}).get("sha") or "").strip()
    head = str((pr.get("head") or {}).get("sha") or event.get("after") or "").strip()
    previous = str(event.get("before") or "").strip()
    action = str(event.get("action") or "").strip()
    branch = str((pr.get("head") or {}).get("ref") or "").strip()
    pr_number = str(pr.get("number") or event.get("number") or "").strip()
    if not base or not head:
        return fail_open("candidate_identity_missing")

    try:
        patterns = workflow_paths(ROOT / args.workflow)
    except Exception as exc:
        return fail_open(f"workflow_paths_invalid:{type(exc).__name__}")

    complete = changed_files(base, head)
    if complete is None:
        return fail_open("complete_delta_unavailable")
    complete_relevant, complete_hits = relevance(complete, patterns, args.domain, policy)
    for path, why in complete_hits:
        print(f"DRAFT_DOMAIN_COMPLETE_HIT={path}:{why}")

    if action != "synchronize":
        emit("run_heavy", "true" if complete_relevant else "false")
        emit("reason", "draft_complete_relevant" if complete_relevant else "draft_complete_irrelevant")
        print("DRAFT_DOMAIN_IMPACT_GREEN")
        return 0

    if not previous or previous == head:
        return fail_open("previous_head_missing")

    incremental = changed_files(previous, head)
    if incremental is None:
        return fail_open("incremental_delta_unavailable")
    incremental_relevant, incremental_hits = relevance(incremental, patterns, args.domain, policy)
    for path, why in incremental_hits:
        print(f"DRAFT_DOMAIN_INCREMENTAL_HIT={path}:{why}")

    if incremental_relevant:
        emit("run_heavy", "true")
        emit("reason", "draft_incremental_relevant")
        print("DRAFT_DOMAIN_IMPACT_GREEN")
        return 0

    if not complete_relevant:
        emit("run_heavy", "false")
        emit("reason", "draft_domain_not_in_candidate")
        print("DRAFT_DOMAIN_IMPACT_GREEN")
        return 0

    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    token = os.getenv("GITHUB_TOKEN", "").strip()
    prior = None
    if repo and token and pr_number and branch:
        prior = prior_success_run(repo, args.workflow, previous, pr_number, base, branch, token)
    if prior:
        print(f"DRAFT_DOMAIN_CARRY_FORWARD_SOURCE={previous}")
        print(f"DRAFT_DOMAIN_CARRY_FORWARD_RUN={prior.get('id')}")
        emit("run_heavy", "false")
        emit("reason", "draft_incremental_irrelevant_prior_green")
        print("DRAFT_DOMAIN_IMPACT_GREEN")
        return 0

    return fail_open("prior_green_missing_for_relevant_candidate")


def validate_migrations(args: argparse.Namespace) -> int:
    try:
        policy = load_policy(Path(args.policy))
    except Exception as exc:
        raise SystemExit(f"FAIL migration impact policy: {type(exc).__name__}: {exc}")
    rows = changed_files(args.base_sha, args.head_sha, name_status=True)
    if rows is None:
        raise SystemExit("FAIL migration impact metadata: candidate delta unavailable")
    checked = 0
    for row in rows:
        parts = row.split("\t")
        path = parts[-1].strip()
        if not (path.startswith(MIGRATION_PREFIX) and path.endswith(".py")):
            continue
        if not (ROOT / path).is_file():
            raise SystemExit(f"FAIL migration impact metadata: deleted/renamed migration requires review: {path}")
        domains = migration_domains(path, policy)
        if domains is None:
            raise SystemExit(
                f"FAIL migration impact metadata: {path} must declare "
                f"{policy['migration_metadata_constant']} with one or more allowed domains"
            )
        checked += 1
        print(f"MIGRATION_IMPACT_METADATA={path}:{','.join(sorted(domains))}")
    print(f"MIGRATION_IMPACT_METADATA_COUNT={checked}")
    print("MIGRATION_IMPACT_METADATA_GREEN")
    return 0


def self_test() -> int:
    policy = load_policy()
    sample = "CI_IMPACT_DOMAINS = ('inventory', 'receipt')\n"
    tree = ast.parse(sample)
    node = tree.body[0]
    assert isinstance(node, ast.Assign)
    assert ast.literal_eval(node.value) == ("inventory", "receipt")
    assert match("backend/app/services/x.py", "backend/app/services/**")
    assert not match("frontend/src/x.jsx", "backend/app/**")
    assert policy["workflow_domains"][".github/workflows/support-message-api-validation.yml"] == "support"
    print("DRAFT_DOMAIN_IMPACT_SELFTEST_GREEN")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    sub = parser.add_subparsers(dest="command", required=True)

    plan_parser = sub.add_parser("plan")
    plan_parser.add_argument("--domain", required=True)
    plan_parser.add_argument("--workflow", required=True)
    plan_parser.add_argument("--event", default=os.getenv("GITHUB_EVENT_PATH", ""))

    validate_parser = sub.add_parser("validate-migrations")
    validate_parser.add_argument("--base-sha", required=True)
    validate_parser.add_argument("--head-sha", required=True)

    sub.add_parser("self-test")
    args = parser.parse_args()
    if args.command == "plan":
        return plan(args)
    if args.command == "validate-migrations":
        return validate_migrations(args)
    return self_test()


if __name__ == "__main__":
    raise SystemExit(main())

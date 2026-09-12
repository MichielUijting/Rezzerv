#!/usr/bin/env python3
"""F7-REL-01 Release Acceptance dispatcher and exact-candidate aggregate gate."""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_ROLES = {
    "package_build",
    "acceptance_and_migration_startup",
    "zero_residual",
    "backup_restore_startup_integrity",
}
EXPECTED_CAPABILITIES = {
    "package_build",
    "postgresql_migration_startup",
    "zero_residual",
    "acceptance_results",
    "backup_restore_integrity",
}
BAD = {"action_required", "cancelled", "failure", "startup_failure", "timed_out"}


def die(message: str) -> None:
    raise SystemExit(f"FAIL F7-REL-01: {message}")


def req(condition: bool, message: str) -> None:
    if not condition:
        die(message)


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        die(f"invalid JSON {path}: {type(exc).__name__}")
    req(isinstance(data, dict), f"JSON root must be object: {path}")
    return data


def load_config(path: str) -> dict:
    data = load_json(ROOT / path)
    req(data.get("schema_version") == 1, "schema_version must be 1")
    req(data.get("gate_id") == "F7-REL-01", "gate_id must be F7-REL-01")
    req(data.get("target_base") == "main", "target_base must be main")
    return data


def validate_config(cfg: dict) -> None:
    authorities = cfg.get("authorities")
    req(isinstance(authorities, list) and len(authorities) == 4, "expected four release authorities")
    req(cfg.get("required_authority_count") == 4, "required_authority_count drift")

    ids: list[str] = []
    roles: set[str] = set()
    for row in authorities:
        aid = row.get("id")
        workflow = row.get("workflow_file")
        inputs = row.get("inputs")
        role = row.get("role")
        req(isinstance(aid, str) and aid, "authority id missing")
        req(isinstance(workflow, str) and workflow.startswith(".github/workflows/"), f"invalid workflow file: {workflow}")
        req(isinstance(inputs, dict), f"inputs must be object: {aid}")
        req(isinstance(role, str) and role, f"role missing: {aid}")
        target = ROOT / workflow
        req(target.is_file(), f"missing workflow: {workflow}")
        req("workflow_dispatch:" in target.read_text(encoding="utf-8"), f"workflow lost workflow_dispatch: {workflow}")
        ids.append(aid)
        roles.add(role)

    req(len(ids) == len(set(ids)), "authority ids must be unique")
    req(roles == EXPECTED_ROLES, f"release authority role drift: {sorted(roles)}")

    capabilities = cfg.get("required_release_capabilities")
    req(isinstance(capabilities, dict), "required_release_capabilities missing")
    req(set(capabilities) == EXPECTED_CAPABILITIES, "release capability set drift")
    known_ids = set(ids)
    for capability, mapped in capabilities.items():
        req(isinstance(mapped, list) and mapped, f"capability lacks authority: {capability}")
        req(all(item in known_ids for item in mapped), f"capability references unknown authority: {capability}")

    transitive = cfg.get("transitive_contracts") or {}
    full_path = transitive.get("full_regression_config")
    req(full_path == "quality/ci/f7_full_regression_gate.json", "Full Regression contract path drift")
    full = load_json(ROOT / full_path)
    req(full.get("gate_id") == "F7-03", "Full Regression gate id drift")
    scenario = transitive.get("required_full_regression_scenario")
    req(scenario == "P0-MIGRATION-STARTUP", "required migration/startup scenario drift")
    expected = transitive.get("required_full_regression_authorities")
    actual = (full.get("p0_scenario_authorities") or {}).get(scenario)
    req(actual == expected == ["P0-MIGRATION-FOUNDATION", "P0-RUNTIME-STARTUP"], "Full Regression migration/startup authorities drift")

    po_policy = str(cfg.get("po_acceptance_policy") or "")
    req("F7-REL-02" in po_policy and "Phase 8/9" in po_policy, "PO acceptance boundary missing")

    print("PASS f7_rel_01_four_release_authorities_registered")
    print("PASS f7_rel_01_release_capabilities_complete")
    print("PASS f7_rel_01_full_regression_binds_migration_startup")
    print("PASS f7_rel_01_po_acceptance_boundary_explicit")
    print("F7_REL_01_CONFIG_GREEN")


def api_request(method: str, url: str, token: str, payload: dict | None = None) -> dict | None:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "rezzerv-f7-release-acceptance-gate",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
    except Exception as exc:
        die(f"GitHub Actions API error {method} {url}: {type(exc).__name__}: {exc}")


def workflow_endpoint(repo: str, workflow_file: str) -> str:
    workflow_id = urllib.parse.quote(Path(workflow_file).name, safe="")
    return f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_id}"


def render_inputs(raw: dict, candidate_ref: str, candidate_sha: str) -> dict:
    values: dict[str, str] = {}
    for key, value in raw.items():
        rendered = str(value)
        rendered = rendered.replace("$CANDIDATE_REF", candidate_ref)
        rendered = rendered.replace("$CANDIDATE_SHA", candidate_sha)
        values[str(key)] = rendered
    return values


def cmd_validate(args: argparse.Namespace) -> int:
    validate_config(load_config(args.config))
    return 0


def cmd_dispatch(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    validate_config(cfg)
    req(bool(args.repo), "repo missing")
    req(bool(args.ref), "candidate ref missing")
    req(bool(args.sha), "candidate SHA missing")
    token = os.getenv("GITHUB_TOKEN", "")
    req(bool(token), "GITHUB_TOKEN missing")

    started = datetime.now(timezone.utc)
    evidence = {
        "gate_id": "F7-REL-01",
        "candidate_ref": args.ref,
        "candidate_sha": args.sha,
        "dispatch_started_at": started.isoformat().replace("+00:00", "Z"),
        "authorities": [],
        "status": "dispatching",
    }
    for row in cfg["authorities"]:
        workflow = row["workflow_file"]
        inputs = render_inputs(row.get("inputs") or {}, args.ref, args.sha)
        payload: dict[str, object] = {"ref": args.ref}
        if inputs:
            payload["inputs"] = inputs
        api_request("POST", workflow_endpoint(args.repo, workflow) + "/dispatches", token, payload)
        evidence["authorities"].append({
            "id": row["id"],
            "role": row["role"],
            "workflow_file": workflow,
            "requested_inputs": inputs,
            "status": "dispatched",
        })
        print(f"F7_REL_01_DISPATCHED={row['id']}:{Path(workflow).name}")

    evidence["status"] = "dispatched"
    Path(args.evidence).write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"F7_REL_01_DISPATCHED_COUNT={len(evidence['authorities'])}")
    print("F7_REL_01_DISPATCH_GREEN")
    return 0


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def latest_run(repo: str, workflow_file: str, ref: str, sha: str, not_before: datetime, token: str) -> dict | None:
    endpoint = workflow_endpoint(repo, workflow_file) + "/runs"
    query = urllib.parse.urlencode({"event": "workflow_dispatch", "branch": ref, "per_page": 30})
    data = api_request("GET", endpoint + "?" + query, token) or {}
    candidates = []
    for run in data.get("workflow_runs", []):
        if run.get("event") != "workflow_dispatch":
            continue
        if run.get("head_sha") != sha:
            continue
        created = str(run.get("created_at") or "")
        if not created or parse_time(created) < not_before:
            continue
        candidates.append(run)
    candidates.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    return candidates[0] if candidates else None


def cmd_wait(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    validate_config(cfg)
    token = os.getenv("GITHUB_TOKEN", "")
    req(bool(token), "GITHUB_TOKEN missing")
    evidence_path = Path(args.evidence)
    evidence = load_json(evidence_path)
    req(evidence.get("candidate_sha") == args.sha, "evidence candidate SHA mismatch")
    req(evidence.get("candidate_ref") == args.ref, "evidence candidate ref mismatch")

    started = parse_time(str(evidence.get("dispatch_started_at"))) - timedelta(seconds=30)
    deadline = time.monotonic() + int(cfg.get("timeout_seconds", 21600))
    poll = int(cfg.get("poll_seconds", 20))
    resolved: dict[str, dict] = {}

    while len(resolved) < len(cfg["authorities"]):
        waiting: list[str] = []
        for row in cfg["authorities"]:
            aid = row["id"]
            if aid in resolved:
                continue
            run = latest_run(args.repo, row["workflow_file"], args.ref, args.sha, started, token)
            if not run:
                waiting.append(f"{aid}:missing")
                continue
            status = str(run.get("status") or "")
            conclusion = run.get("conclusion")
            print(f"F7_REL_01_RUN {aid} run={run.get('id')} status={status} conclusion={conclusion}")
            if status != "completed":
                waiting.append(f"{aid}:{status}")
                continue
            if conclusion != "success":
                if conclusion in BAD or conclusion:
                    die(f"{aid} completed non-success: run={run.get('id')} conclusion={conclusion}")
                waiting.append(f"{aid}:no-conclusion")
                continue
            resolved[aid] = {
                "id": aid,
                "role": row["role"],
                "workflow_file": row["workflow_file"],
                "run_id": run.get("id"),
                "head_sha": run.get("head_sha"),
                "conclusion": conclusion,
                "html_url": run.get("html_url"),
            }

        if len(resolved) == len(cfg["authorities"]):
            break
        if time.monotonic() >= deadline:
            die("timeout waiting for " + ",".join(waiting))
        print("F7_REL_01_WAITING=" + ",".join(waiting))
        time.sleep(poll)

    evidence["aggregate_runs"] = [resolved[row["id"]] for row in cfg["authorities"]]
    evidence["release_capabilities"] = cfg["required_release_capabilities"]
    evidence["po_acceptance_state"] = "external_dependency_F7_REL_02"
    evidence["status"] = "green"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"F7_REL_01_AGGREGATED_COUNT={len(resolved)}")
    print("F7_REL_01_RELEASE_ACCEPTANCE_GATE_GREEN")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    validate = sub.add_parser("validate-config")
    validate.add_argument("--config", default="quality/ci/f7_release_acceptance_gate.json")
    validate.set_defaults(func=cmd_validate)

    dispatch = sub.add_parser("dispatch")
    dispatch.add_argument("--config", default="quality/ci/f7_release_acceptance_gate.json")
    dispatch.add_argument("--repo", required=True)
    dispatch.add_argument("--ref", required=True)
    dispatch.add_argument("--sha", required=True)
    dispatch.add_argument("--evidence", default="f7-release-acceptance-evidence.json")
    dispatch.set_defaults(func=cmd_dispatch)

    wait = sub.add_parser("wait")
    wait.add_argument("--config", default="quality/ci/f7_release_acceptance_gate.json")
    wait.add_argument("--repo", required=True)
    wait.add_argument("--ref", required=True)
    wait.add_argument("--sha", required=True)
    wait.add_argument("--evidence", default="f7-release-acceptance-evidence.json")
    wait.set_defaults(func=cmd_wait)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

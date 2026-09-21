#!/usr/bin/env python3
"""F7-03 Full Regression dispatcher and exact-candidate aggregate gate."""
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
EXPECTED_P0 = {
    "P0-ACCOUNT-SESSION",
    "P0-ONBOARDING",
    "P0-HOUSEHOLD-MEMBERSHIP",
    "P0-AUTHORIZATION-ISOLATION",
    "P0-SETTINGS-PROJECTION",
    "P0-LOCATIONS-POLICY",
    "P0-RECEIPT-INVENTORY-ALMOSTOUT",
    "P0-KASSA-REVIEW",
    "P0-UNPACKING",
    "P0-INVENTORY",
    "P0-ALMOST-OUT",
    "P0-ARTICLE-IDENTITY",
    "P0-PLATFORM-AUTHORITY",
    "P0-MIGRATION-STARTUP",
}
BAD = {"action_required", "cancelled", "failure", "startup_failure", "timed_out"}
REUSE_EVENTS = {"pull_request", "workflow_dispatch"}
EXPECTED_WORKFLOW_COUNT = 21
EXPECTED_SERIAL_SHARED = {"TP-CI-02"}
EXPECTED_REPLACED_SHARED = {"TP-CI-03", "TP-CI-04", "TP-CI-05", "TP-CI-07"}
EXPECTED_PARALLEL_STANDALONE = {
    "P0-ACCOUNT-SESSION",
    "P0-AUTHORIZATION-ISOLATION",
    "P0-INVENTORY",
    "P0-ALMOST-OUT",
    "F6-INVENTORY",
    "P0-RECEIPT-INVENTORY",
    "P0-RECEIPT-LOCATIONS-OFF",
    "P0-RECEIPT-IDEMPOTENCY",
    "P0-RECEIPT-NONPHYSICAL",
    "F6-RECEIPT",
    "P0-ONBOARDING",
    "P0-ARTICLE-IDENTITY",
    "P0-PLATFORM-AUTHORITY",
    "P0-UNPACKING",
}


def die(message: str) -> None:
    raise SystemExit(f"FAIL F7-03: {message}")


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
    req(data.get("schema_version") == 2, "schema_version must be 2")
    req(data.get("gate_id") == "F7-03", "gate_id must be F7-03")
    req(data.get("target_base") == "main", "target_base must be main")
    return data


def validate_config(cfg: dict) -> None:
    workflows = cfg.get("workflows")
    req(isinstance(workflows, list) and len(workflows) == EXPECTED_WORKFLOW_COUNT, f"expected {EXPECTED_WORKFLOW_COUNT} Full Regression workflows")
    ids = [row.get("id") for row in workflows]
    req(len(ids) == len(set(ids)), "workflow ids must be unique")
    req(cfg.get("required_workflow_count") == EXPECTED_WORKFLOW_COUNT, "required_workflow_count drift")
    req(cfg.get("full_frontend_workflow_id") in ids, "full frontend workflow is not registered")

    profile = cfg.get("execution_profile")
    req(isinstance(profile, dict), "execution_profile missing")
    req(profile.get("mode") == "f7_parallel_standalone", "execution profile mode drift")
    req(set(profile.get("serial_shared_workflows") or []) == EXPECTED_SERIAL_SHARED, "serial shared workflow profile drift")
    req(set(profile.get("replaced_shared_workflows") or []) == EXPECTED_REPLACED_SHARED, "replaced shared workflow profile drift")
    req(set(profile.get("parallel_standalone_authorities") or []) == EXPECTED_PARALLEL_STANDALONE, "parallel standalone authority profile drift")
    req(EXPECTED_SERIAL_SHARED.issubset(set(ids)), "serial shared Kassa workflow missing")
    req(EXPECTED_REPLACED_SHARED.isdisjoint(set(ids)), "replaced shared workflows must not run in F7 parallel profile")
    req(EXPECTED_PARALLEL_STANDALONE.issubset(set(ids)), "parallel standalone authority missing")

    reuse = cfg.get("reuse_contract")
    req(isinstance(reuse, dict), "reuse_contract missing")
    req(reuse.get("exact_candidate_sha") is True, "reuse must require exact candidate SHA")
    req(reuse.get("same_pr_and_base_for_pull_request") is True, "PR reuse must require same PR and base")
    req(reuse.get("same_branch_for_workflow_dispatch") is True, "dispatch reuse must require same branch")
    req(reuse.get("attach_matching_in_progress") is True, "reuse must attach matching in-progress runs")
    events = reuse.get("allowed_events")
    req(isinstance(events, list) and set(events) == REUSE_EVENTS, "reuse allowed_events drift")

    for row in workflows:
        wid = row.get("id")
        workflow = row.get("workflow_file")
        inputs = row.get("inputs")
        steps = row.get("reuse_required_success_steps")
        req(isinstance(wid, str) and wid, "workflow id missing")
        req(isinstance(workflow, str) and workflow.startswith(".github/workflows/"), f"invalid workflow file: {workflow}")
        req(isinstance(inputs, dict), f"inputs must be object: {wid}")
        req(isinstance(steps, list) and all(isinstance(step, str) and step for step in steps), f"invalid reuse steps: {wid}")
        if inputs:
            req(bool(steps), f"parameterized workflow requires explicit reuse coverage steps: {wid}")
        target = ROOT / workflow
        req(target.is_file(), f"missing workflow: {workflow}")
        text = target.read_text(encoding="utf-8")
        req("workflow_dispatch:" in text, f"workflow lost workflow_dispatch: {workflow}")
        for step in steps:
            req(f"- name: {step}" in text, f"reuse coverage step drift {wid}: {step}")

    scenario_map = cfg.get("p0_scenario_authorities")
    req(isinstance(scenario_map, dict), "p0_scenario_authorities missing")
    req(set(scenario_map) == EXPECTED_P0, "P0 scenario coverage drift")
    req(cfg.get("required_p0_scenario_count") == 14, "required_p0_scenario_count drift")
    valid_ids = set(ids)
    for scenario, authorities in scenario_map.items():
        req(isinstance(authorities, list) and authorities, f"scenario lacks authority: {scenario}")
        req(all(authority in valid_ids for authority in authorities), f"scenario references unknown authority: {scenario}")

    print("PASS f7_03_exact_14_p0_scenarios_mapped")
    print(f"PASS f7_03_full_regression_workflow_inventory_registered count={EXPECTED_WORKFLOW_COUNT}")
    print("PASS f7_03_full_frontend_regression_registered")
    print("PASS f7_03_exact_sha_reuse_contract_closed")
    print("F7_03_FULL_REGRESSION_CONFIG_GREEN")


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
            "User-Agent": "rezzerv-f7-full-regression-gate",
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


def run_jobs(repo: str, run_id: int, token: str) -> list[dict]:
    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100"
    data = api_request("GET", url, token) or {}
    jobs = data.get("jobs")
    return jobs if isinstance(jobs, list) else []


def successful_step_names(jobs: list[dict]) -> set[str]:
    result: set[str] = set()
    for job in jobs:
        for step in job.get("steps") or []:
            if step.get("conclusion") == "success" and step.get("name"):
                result.add(str(step["name"]))
    return result


def run_matches_pr_context(run: dict, pr_number: str, base_sha: str) -> bool:
    if not pr_number or not base_sha:
        return False
    try:
        expected_number = int(pr_number)
    except ValueError:
        return False
    for pr in run.get("pull_requests") or []:
        if pr.get("number") != expected_number:
            continue
        base = pr.get("base") or {}
        if base.get("sha") == base_sha:
            return True
    return False


def run_matches_reuse_identity(run: dict, ref: str, sha: str, pr_number: str, base_sha: str) -> bool:
    if run.get("head_sha") != sha:
        return False
    event = str(run.get("event") or "")
    if event not in REUSE_EVENTS:
        return False
    if str(run.get("head_branch") or "") != ref:
        return False
    if event == "pull_request":
        return run_matches_pr_context(run, pr_number, base_sha)
    return True


def run_has_required_coverage(row: dict, jobs: list[dict]) -> bool:
    required = set(row.get("reuse_required_success_steps") or [])
    if not required:
        return True
    return required.issubset(successful_step_names(jobs))


def run_has_planned_coverage(row: dict, jobs: list[dict]) -> bool:
    required = set(row.get("reuse_required_success_steps") or [])
    if not required:
        return True
    states: dict[str, tuple[str, str | None]] = {}
    for job in jobs:
        for step in job.get("steps") or []:
            name = step.get("name")
            if name:
                states[str(name)] = (str(step.get("status") or ""), step.get("conclusion"))
    if not required.issubset(states):
        return False
    for name in required:
        status, conclusion = states[name]
        if conclusion in BAD or conclusion == "skipped":
            return False
        if status not in {"queued", "in_progress", "completed", "pending"}:
            return False
    return True


def existing_reusable_run(
    repo: str,
    row: dict,
    ref: str,
    sha: str,
    pr_number: str,
    base_sha: str,
    token: str,
) -> tuple[str | None, dict | None]:
    endpoint = workflow_endpoint(repo, row["workflow_file"]) + "/runs"
    query = urllib.parse.urlencode({"head_sha": sha, "per_page": 100})
    data = api_request("GET", endpoint + "?" + query, token) or {}
    completed: list[dict] = []
    inflight: list[dict] = []
    for run in data.get("workflow_runs", []):
        if not run_matches_reuse_identity(run, ref, sha, pr_number, base_sha):
            continue
        status = str(run.get("status") or "")
        conclusion = run.get("conclusion")
        jobs = run_jobs(repo, int(run.get("id")), token)
        if status == "completed" and conclusion == "success" and run_has_required_coverage(row, jobs):
            completed.append(run)
        elif status in {"queued", "in_progress"} and run_has_planned_coverage(row, jobs):
            inflight.append(run)
    completed.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    inflight.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    if completed:
        return "reused", completed[0]
    if inflight:
        return "attached", inflight[0]
    return None, None


def reusable_success_run(
    repo: str,
    row: dict,
    ref: str,
    sha: str,
    pr_number: str,
    base_sha: str,
    token: str,
) -> dict | None:
    mode, run = existing_reusable_run(repo, row, ref, sha, pr_number, base_sha, token)
    return run if mode == "reused" else None


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
        "gate_id": "F7-03",
        "candidate_ref": args.ref,
        "candidate_sha": args.sha,
        "base_sha": args.base_sha or "",
        "pr_number": args.pr_number or "",
        "dispatch_started_at": started.isoformat().replace("+00:00", "Z"),
        "workflows": [],
        "status": "dispatching",
    }
    reused_count = 0
    attached_count = 0
    dispatched_count = 0
    for row in cfg["workflows"]:
        workflow = row["workflow_file"]
        reuse_mode, existing = existing_reusable_run(
            args.repo,
            row,
            args.ref,
            args.sha,
            args.pr_number or "",
            args.base_sha or "",
            token,
        )
        if existing:
            if reuse_mode == "reused":
                reused_count += 1
            elif reuse_mode == "attached":
                attached_count += 1
            else:
                die(f"unexpected reuse mode: {reuse_mode}")
            evidence["workflows"].append({
                "id": row["id"],
                "workflow_file": workflow,
                "requested_inputs": row.get("inputs") or {},
                "status": reuse_mode,
                "run_id": existing.get("id"),
                "event": existing.get("event"),
                "head_sha": existing.get("head_sha"),
                "head_branch": existing.get("head_branch"),
                "conclusion": existing.get("conclusion"),
                "html_url": existing.get("html_url"),
            })
            print(f"F7_FULL_{reuse_mode.upper()}={row['id']}:run={existing.get('id')}:{existing.get('event')}")
            continue

        payload = {"ref": args.ref}
        if row.get("inputs"):
            payload["inputs"] = row["inputs"]
        url = workflow_endpoint(args.repo, workflow) + "/dispatches"
        api_request("POST", url, token, payload)
        dispatched_count += 1
        evidence["workflows"].append({
            "id": row["id"],
            "workflow_file": workflow,
            "requested_inputs": row.get("inputs") or {},
            "status": "dispatched",
            "dispatched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        })
        print(f"F7_FULL_DISPATCHED={row['id']}:{Path(workflow).name}")

    req(reused_count + attached_count + dispatched_count == len(cfg["workflows"]), "reuse/attach/dispatch accounting mismatch")
    evidence["status"] = "dispatched"
    evidence["reused_count"] = reused_count
    evidence["attached_count"] = attached_count
    evidence["dispatched_count"] = dispatched_count
    Path(args.evidence).write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"F7_FULL_AUTHORITY_COUNT={len(cfg['workflows'])}")
    print(f"F7_FULL_REUSED_COUNT={reused_count}")
    print(f"F7_FULL_ATTACHED_COUNT={attached_count}")
    print(f"F7_FULL_DISPATCHED_COUNT={dispatched_count}")
    print("F7_FULL_REUSE_DISPATCH_GREEN")
    return 0

def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def latest_dispatched_run(repo: str, workflow_file: str, ref: str, sha: str, not_before: datetime, token: str) -> dict | None:
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
        if not created:
            continue
        if parse_time(created) < not_before:
            continue
        candidates.append(run)
    candidates.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    return candidates[0] if candidates else None


def verify_reused_run(repo: str, row: dict, item: dict, ref: str, sha: str, pr_number: str, base_sha: str, token: str) -> dict:
    run_id = item.get("run_id")
    req(isinstance(run_id, int), f"reused run id missing: {row['id']}")
    run = api_request("GET", f"https://api.github.com/repos/{repo}/actions/runs/{run_id}", token) or {}
    req(run.get("status") == "completed" and run.get("conclusion") == "success", f"reused run no longer green: {row['id']}")
    req(run_matches_reuse_identity(run, ref, sha, pr_number, base_sha), f"reused run identity mismatch: {row['id']}")
    jobs = run_jobs(repo, run_id, token)
    req(run_has_required_coverage(row, jobs), f"reused run coverage mismatch: {row['id']}")
    return run


def cmd_wait(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    validate_config(cfg)
    token = os.getenv("GITHUB_TOKEN", "")
    req(bool(token), "GITHUB_TOKEN missing")
    evidence_path = Path(args.evidence)
    evidence = load_json(evidence_path)
    req(evidence.get("candidate_sha") == args.sha, "evidence candidate SHA mismatch")
    req(evidence.get("candidate_ref") == args.ref, "evidence candidate ref mismatch")
    req(str(evidence.get("base_sha") or "") == str(args.base_sha or ""), "evidence base SHA mismatch")
    req(str(evidence.get("pr_number") or "") == str(args.pr_number or ""), "evidence PR number mismatch")

    cfg_by_id = {row["id"]: row for row in cfg["workflows"]}
    evidence_by_id = {row.get("id"): row for row in evidence.get("workflows", [])}
    req(set(evidence_by_id) == set(cfg_by_id), "evidence workflow inventory mismatch")

    resolved: dict[str, dict] = {}
    for wid, item in evidence_by_id.items():
        if item.get("status") != "reused":
            continue
        row = cfg_by_id[wid]
        run = verify_reused_run(
            args.repo,
            row,
            item,
            args.ref,
            args.sha,
            args.pr_number or "",
            args.base_sha or "",
            token,
        )
        resolved[wid] = {
            "id": wid,
            "workflow_file": row["workflow_file"],
            "run_id": run.get("id"),
            "head_sha": run.get("head_sha"),
            "conclusion": run.get("conclusion"),
            "html_url": run.get("html_url"),
            "source": "reused",
            "event": run.get("event"),
        }
        print(f"F7_FULL_REUSE_CONFIRMED {wid} run={run.get('id')}")

    deadline = time.monotonic() + int(cfg.get("timeout_seconds", 14400))
    poll = int(cfg.get("poll_seconds", 20))

    while len(resolved) < len(cfg["workflows"]):
        waiting: list[str] = []
        for row in cfg["workflows"]:
            wid = row["id"]
            if wid in resolved:
                continue
            item = evidence_by_id[wid]
            if item.get("status") == "attached":
                run_id = item.get("run_id")
                req(isinstance(run_id, int), f"attached run id missing: {wid}")
                run = api_request("GET", f"https://api.github.com/repos/{args.repo}/actions/runs/{run_id}", token) or {}
                req(run_matches_reuse_identity(run, args.ref, args.sha, args.pr_number or "", args.base_sha or ""), f"attached run identity mismatch: {wid}")
                status = str(run.get("status") or "")
                conclusion = run.get("conclusion")
                print(f"F7_FULL_ATTACHED_RUN {wid} run={run_id} status={status} conclusion={conclusion}")
                if status != "completed":
                    waiting.append(f"{wid}:{status or 'pending'}")
                    continue
                if conclusion != "success":
                    die(f"{wid} attached run completed non-success: run={run_id} conclusion={conclusion}")
                jobs = run_jobs(args.repo, run_id, token)
                req(run_has_required_coverage(row, jobs), f"attached run coverage mismatch: {wid}")
                resolved[wid] = {
                    "id": wid,
                    "workflow_file": row["workflow_file"],
                    "run_id": run_id,
                    "head_sha": run.get("head_sha"),
                    "conclusion": conclusion,
                    "html_url": run.get("html_url"),
                    "source": "attached",
                    "event": run.get("event"),
                }
                continue

            req(item.get("status") == "dispatched", f"unexpected evidence status for {wid}: {item.get('status')}")
            dispatched_at = str(item.get("dispatched_at") or evidence.get("dispatch_started_at") or "")
            req(bool(dispatched_at), f"dispatch timestamp missing: {wid}")
            not_before = parse_time(dispatched_at) - timedelta(seconds=30)
            run = latest_dispatched_run(args.repo, row["workflow_file"], args.ref, args.sha, not_before, token)
            if not run:
                waiting.append(f"{wid}:missing")
                continue
            status = str(run.get("status") or "")
            conclusion = run.get("conclusion")
            print(f"F7_FULL_RUN {wid} run={run.get('id')} status={status} conclusion={conclusion}")
            if status != "completed":
                waiting.append(f"{wid}:{status}")
                continue
            if conclusion != "success":
                if conclusion in BAD or conclusion:
                    die(f"{wid} completed non-success: run={run.get('id')} conclusion={conclusion}")
                waiting.append(f"{wid}:no-conclusion")
                continue
            jobs = run_jobs(args.repo, int(run.get("id")), token)
            req(run_has_required_coverage(row, jobs), f"dispatched run coverage mismatch: {wid}")
            resolved[wid] = {
                "id": wid,
                "workflow_file": row["workflow_file"],
                "run_id": run.get("id"),
                "head_sha": run.get("head_sha"),
                "conclusion": conclusion,
                "html_url": run.get("html_url"),
                "source": "dispatched",
                "event": run.get("event"),
            }

        if len(resolved) == len(cfg["workflows"]):
            break
        if time.monotonic() >= deadline:
            die("timeout waiting for " + ",".join(waiting))
        print("F7_FULL_WAITING=" + ",".join(waiting))
        time.sleep(poll)

    evidence["aggregate_runs"] = [resolved[row["id"]] for row in cfg["workflows"]]
    evidence["status"] = "green"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"F7_FULL_AGGREGATED_COUNT={len(resolved)}")
    print(f"F7_FULL_AGGREGATED_REUSED_COUNT={sum(1 for item in resolved.values() if item['source'] == 'reused')}")
    print(f"F7_FULL_AGGREGATED_ATTACHED_COUNT={sum(1 for item in resolved.values() if item['source'] == 'attached')}")
    print(f"F7_FULL_AGGREGATED_DISPATCHED_COUNT={sum(1 for item in resolved.values() if item['source'] == 'dispatched')}")
    print("F7_FULL_REGRESSION_GATE_GREEN")
    return 0

def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    validate = sub.add_parser("validate-config")
    validate.add_argument("--config", default="quality/ci/f7_full_regression_gate.json")
    validate.set_defaults(func=cmd_validate)

    dispatch = sub.add_parser("dispatch")
    dispatch.add_argument("--config", default="quality/ci/f7_full_regression_gate.json")
    dispatch.add_argument("--repo", required=True)
    dispatch.add_argument("--ref", required=True)
    dispatch.add_argument("--sha", required=True)
    dispatch.add_argument("--base-sha", default="")
    dispatch.add_argument("--pr-number", default="")
    dispatch.add_argument("--evidence", default="f7-full-regression-evidence.json")
    dispatch.set_defaults(func=cmd_dispatch)

    wait = sub.add_parser("wait")
    wait.add_argument("--config", default="quality/ci/f7_full_regression_gate.json")
    wait.add_argument("--repo", required=True)
    wait.add_argument("--ref", required=True)
    wait.add_argument("--sha", required=True)
    wait.add_argument("--base-sha", default="")
    wait.add_argument("--pr-number", default="")
    wait.add_argument("--evidence", default="f7-full-regression-evidence.json")
    wait.set_defaults(func=cmd_wait)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

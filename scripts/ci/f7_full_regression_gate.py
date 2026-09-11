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
    req(data.get("schema_version") == 1, "schema_version must be 1")
    req(data.get("gate_id") == "F7-03", "gate_id must be F7-03")
    req(data.get("target_base") == "main", "target_base must be main")
    return data


def validate_config(cfg: dict) -> None:
    workflows = cfg.get("workflows")
    req(isinstance(workflows, list) and len(workflows) == 11, "expected eleven Full Regression workflows")
    ids = [row.get("id") for row in workflows]
    req(len(ids) == len(set(ids)), "workflow ids must be unique")
    req(cfg.get("required_workflow_count") == 11, "required_workflow_count drift")
    req(cfg.get("full_frontend_workflow_id") in ids, "full frontend workflow is not registered")

    for row in workflows:
        wid = row.get("id")
        workflow = row.get("workflow_file")
        inputs = row.get("inputs")
        req(isinstance(wid, str) and wid, "workflow id missing")
        req(isinstance(workflow, str) and workflow.startswith(".github/workflows/"), f"invalid workflow file: {workflow}")
        req(isinstance(inputs, dict), f"inputs must be object: {wid}")
        target = ROOT / workflow
        req(target.is_file(), f"missing workflow: {workflow}")
        text = target.read_text(encoding="utf-8")
        req("workflow_dispatch:" in text, f"workflow lost workflow_dispatch: {workflow}")

    scenario_map = cfg.get("p0_scenario_authorities")
    req(isinstance(scenario_map, dict), "p0_scenario_authorities missing")
    req(set(scenario_map) == EXPECTED_P0, "P0 scenario coverage drift")
    req(cfg.get("required_p0_scenario_count") == 14, "required_p0_scenario_count drift")
    valid_ids = set(ids)
    for scenario, authorities in scenario_map.items():
        req(isinstance(authorities, list) and authorities, f"scenario lacks authority: {scenario}")
        req(all(authority in valid_ids for authority in authorities), f"scenario references unknown authority: {scenario}")

    print("PASS f7_03_exact_14_p0_scenarios_mapped")
    print("PASS f7_03_eleven_full_regression_workflows_registered")
    print("PASS f7_03_full_frontend_regression_registered")
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
        "dispatch_started_at": started.isoformat().replace("+00:00", "Z"),
        "workflows": [],
        "status": "dispatching",
    }
    for row in cfg["workflows"]:
        workflow = row["workflow_file"]
        payload = {"ref": args.ref}
        if row.get("inputs"):
            payload["inputs"] = row["inputs"]
        url = workflow_endpoint(args.repo, workflow) + "/dispatches"
        api_request("POST", url, token, payload)
        evidence["workflows"].append({
            "id": row["id"],
            "workflow_file": workflow,
            "requested_inputs": row.get("inputs") or {},
            "status": "dispatched",
        })
        print(f"F7_FULL_DISPATCHED={row['id']}:{Path(workflow).name}")

    evidence["status"] = "dispatched"
    Path(args.evidence).write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"F7_FULL_DISPATCHED_COUNT={len(evidence['workflows'])}")
    print("F7_FULL_DISPATCH_GREEN")
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
        if not created:
            continue
        if parse_time(created) < not_before:
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
    deadline = time.monotonic() + int(cfg.get("timeout_seconds", 14400))
    poll = int(cfg.get("poll_seconds", 20))
    resolved: dict[str, dict] = {}

    while len(resolved) < len(cfg["workflows"]):
        waiting: list[str] = []
        for row in cfg["workflows"]:
            wid = row["id"]
            if wid in resolved:
                continue
            run = latest_run(args.repo, row["workflow_file"], args.ref, args.sha, started, token)
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
            resolved[wid] = {
                "id": wid,
                "workflow_file": row["workflow_file"],
                "run_id": run.get("id"),
                "head_sha": run.get("head_sha"),
                "conclusion": conclusion,
                "html_url": run.get("html_url"),
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
    dispatch.add_argument("--evidence", default="f7-full-regression-evidence.json")
    dispatch.set_defaults(func=cmd_dispatch)

    wait = sub.add_parser("wait")
    wait.add_argument("--config", default="quality/ci/f7_full_regression_gate.json")
    wait.add_argument("--repo", required=True)
    wait.add_argument("--ref", required=True)
    wait.add_argument("--sha", required=True)
    wait.add_argument("--evidence", default="f7-full-regression-evidence.json")
    wait.set_defaults(func=cmd_wait)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

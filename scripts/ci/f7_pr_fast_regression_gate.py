#!/usr/bin/env python3
"""F7-02 PR Fast Regression planner and exact-SHA aggregate gate."""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLUSTERS = ["TP-CI-02", "TP-CI-03", "TP-CI-04", "TP-CI-05", "TP-CI-07"]
BAD = {"action_required", "cancelled", "failure", "startup_failure", "timed_out"}


def die(msg: str) -> None:
    raise SystemExit(f"FAIL F7-02: {msg}")


def req(ok: bool, msg: str) -> None:
    if not ok:
        die(msg)


def jload(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        die(f"invalid JSON {path}: {type(exc).__name__}")
    req(isinstance(data, dict), f"JSON root must be object: {path}")
    return data


def config(path: str) -> dict:
    data = jload(ROOT / path)
    req(data.get("schema_version") == 1 and data.get("gate_id") == "F7-02", "invalid gate contract")
    req(data.get("target_base") == "main", "target_base must be main")
    return data


def patterns(manifest: str) -> list[str]:
    data = jload(ROOT / manifest)
    auth = data.get("authorities")
    req(isinstance(auth, dict) and auth, f"invalid manifest: {manifest}")
    result: list[str] = []
    for name, value in auth.items():
        paths = value.get("paths") if isinstance(value, dict) else None
        req(isinstance(paths, list) and paths, f"missing paths: {manifest}:{name}")
        for pattern in paths:
            req(isinstance(pattern, str) and pattern and not pattern.startswith("!"), f"invalid pattern: {pattern!r}")
            if pattern not in result:
                result.append(pattern)
    return result


def matches(path: str, pattern: str) -> bool:
    return fnmatch.fnmatchcase(path, pattern) or (pattern.endswith("/**") and path.startswith(pattern[:-3]))


def validate(cfg: dict) -> None:
    clusters = cfg.get("clusters")
    req(isinstance(clusters, list) and [c.get("id") for c in clusters] == CLUSTERS, "five-cluster map drift")
    for cluster in clusters:
        workflow = cluster["workflow_file"]
        manifest = cluster["manifest"]
        req((ROOT / workflow).is_file(), f"missing shared workflow: {workflow}")
        text = (ROOT / workflow).read_text(encoding="utf-8")
        req("pull_request:" in text and "workflow_dispatch:" in text, f"trigger contract drift: {workflow}")
        req("github.event.pull_request.head.sha || github.sha" in text, f"candidate checkout drift: {workflow}")
        req("scripts/ci/shared_fullstack_plan.py" in text, f"shared planner drift: {workflow}")
        patterns(manifest)

    for validator in cfg.get("cheap_validators", []):
        req((ROOT / validator).is_file(), f"missing cheap validator: {validator}")

    gov = cfg.get("fallback_governance")
    req(isinstance(gov, dict), "fallback_governance missing")
    manual = gov.get("manual_only_workflows")
    req(isinstance(manual, list) and len(manual) == 14, "expected fourteen manual fallbacks")
    for workflow in manual:
        text = (ROOT / workflow).read_text(encoding="utf-8")
        req("\n  workflow_dispatch:\n" in text, f"manual fallback lost dispatch: {workflow}")
        req("\n  pull_request:" not in text, f"manual fallback regained PR trigger: {workflow}")

    stale = gov.get("known_stale_references")
    req(isinstance(stale, list) and len(stale) == 2, "expected two known stale references")
    tp02w = (ROOT / ".github/workflows/tp-ci-02-kassa-shared-stack-postgresql-validation.yml").read_text(encoding="utf-8")
    tp02m = (ROOT / "quality/ci/tp_ci_02_kassa_shared_stack_paths.json").read_text(encoding="utf-8")
    for path in stale:
        req(not (ROOT / path).exists(), f"stale fallback unexpectedly exists: {path}")
        req(path in tp02w and path in tp02m, f"known stale reference drift: {path}")
    req(gov.get("duplicate_pr_fallbacks") == [], "duplicate PR fallbacks must be empty")

    print("PASS f7_02_fallback_governance_closed")
    print("F7_02_SHARED_CLUSTERS=5")
    print("F7_02_MANUAL_FALLBACKS=14")
    print("F7_02_KNOWN_STALE_REFERENCES=2")
    print("F7_02_DUPLICATE_PR_FALLBACKS=0")


def git(*args: str) -> str:
    p = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    if p.returncode:
        die(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout.strip()


def output(name: str, value: str) -> None:
    target = os.getenv("GITHUB_OUTPUT", "")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def cmd_validate(args: argparse.Namespace) -> int:
    validate(config(args.config))
    print("F7_02_PR_FAST_CONFIG_GREEN")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    cfg = config(args.config)
    validate(cfg)
    req(args.base_sha and args.head_sha and args.base_sha != args.head_sha, "invalid base/head SHA")
    git("cat-file", "-e", f"{args.base_sha}^{{commit}}")
    git("cat-file", "-e", f"{args.head_sha}^{{commit}}")
    changed = [x for x in git("diff", "--name-only", "--diff-filter=ACMRD", args.base_sha, args.head_sha).splitlines() if x]
    planned = []
    for cluster in cfg["clusters"]:
        matched = [p for p in changed if any(matches(p, pat) for pat in patterns(cluster["manifest"]))]
        planned.append({**cluster, "selected": bool(matched), "matched_paths": matched})
    selected = [c for c in planned if c["selected"]]
    mode = "live" if args.base_ref == cfg["target_base"] else "preview"
    evidence = {
        "gate_id": "F7-02",
        "mode": mode,
        "base_ref": args.base_ref,
        "base_sha": args.base_sha,
        "candidate_sha": args.head_sha,
        "changed_files": changed,
        "clusters": planned,
        "expected_cluster_count": len(selected),
        "aggregate_runs": [],
        "status": "planned",
    }
    Path(args.evidence).write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"F7_PR_FAST_MODE={mode}")
    print(f"F7_PR_FAST_CHANGED_COUNT={len(changed)}")
    for cluster in planned:
        print(f"F7_PR_FAST_CLUSTER_{cluster['id']}={'selected' if cluster['selected'] else 'skipped'}")
        for path in cluster["matched_paths"]:
            print(f"F7_PR_FAST_MATCH_{cluster['id']}={path}")
    print(f"F7_PR_FAST_EXPECTED_COUNT={len(selected)}")
    output("mode", mode)
    output("expected_count", str(len(selected)))
    return 0


def api(repo: str, workflow: str, sha: str, token: str) -> dict | None:
    workflow_id = urllib.parse.quote(Path(workflow).name, safe="")
    query = urllib.parse.urlencode({"event": "pull_request", "head_sha": sha, "per_page": 20})
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_id}/runs?{query}"
    request = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "rezzerv-f7-pr-fast-gate",
    })
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
    except Exception as exc:
        die(f"Actions API error for {workflow}: {type(exc).__name__}: {exc}")
    runs = [r for r in data.get("workflow_runs", []) if r.get("head_sha") == sha and r.get("event") == "pull_request"]
    runs.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return runs[0] if runs else None


def cmd_wait(args: argparse.Namespace) -> int:
    path = Path(args.evidence)
    ev = jload(path)
    req(ev.get("candidate_sha") == args.head_sha, "evidence SHA mismatch")
    selected = [c for c in ev.get("clusters", []) if c.get("selected")]
    if ev.get("mode") != "live":
        ev["status"] = "preview_green"
        path.write_text(json.dumps(ev, indent=2) + "\n", encoding="utf-8")
        print(f"F7_PR_FAST_PREVIEW_EXPECTED_COUNT={len(selected)}")
        print("F7_PR_FAST_STACKED_PREVIEW_GREEN")
        return 0

    cfg = config(args.config)
    token = os.getenv("GITHUB_TOKEN", "")
    req(bool(token), "GITHUB_TOKEN missing")
    deadline = time.monotonic() + int(cfg.get("timeout_seconds", 7200))
    poll = int(cfg.get("poll_seconds", 15))
    resolved: dict[str, dict] = {}
    while len(resolved) < len(selected):
        pending = []
        for cluster in selected:
            cid = cluster["id"]
            if cid in resolved:
                continue
            run = api(args.repo, cluster["workflow_file"], args.head_sha, token)
            if not run:
                pending.append(f"{cid}:missing")
                continue
            status, conclusion = run.get("status"), run.get("conclusion")
            print(f"F7_PR_FAST_RUN {cid} run={run.get('id')} status={status} conclusion={conclusion}")
            if status != "completed":
                pending.append(f"{cid}:{status}")
            elif conclusion == "success":
                resolved[cid] = {
                    "id": cid,
                    "workflow_file": cluster["workflow_file"],
                    "run_id": run.get("id"),
                    "conclusion": conclusion,
                    "head_sha": run.get("head_sha"),
                    "html_url": run.get("html_url"),
                }
            elif conclusion in BAD or conclusion != "success":
                die(f"{cid} completed non-success: run={run.get('id')} conclusion={conclusion}")
        if len(resolved) == len(selected):
            break
        if time.monotonic() >= deadline:
            die(f"timeout waiting for: {','.join(pending)}")
        print(f"F7_PR_FAST_WAITING={','.join(pending)}")
        time.sleep(poll)

    ev["aggregate_runs"] = [resolved[c["id"]] for c in selected]
    ev["status"] = "green"
    path.write_text(json.dumps(ev, indent=2) + "\n", encoding="utf-8")
    print(f"F7_PR_FAST_AGGREGATED_COUNT={len(resolved)}")
    print("F7_PR_FAST_REGRESSION_GATE_GREEN")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate-config")
    v.add_argument("--config", default="quality/ci/f7_pr_fast_regression_gate.json")
    v.set_defaults(func=cmd_validate)
    p = sub.add_parser("plan")
    p.add_argument("--config", default="quality/ci/f7_pr_fast_regression_gate.json")
    p.add_argument("--base-sha", required=True)
    p.add_argument("--head-sha", required=True)
    p.add_argument("--base-ref", required=True)
    p.add_argument("--evidence", default="f7-pr-fast-regression-evidence.json")
    p.set_defaults(func=cmd_plan)
    w = sub.add_parser("wait")
    w.add_argument("--config", default="quality/ci/f7_pr_fast_regression_gate.json")
    w.add_argument("--head-sha", required=True)
    w.add_argument("--repo", required=True)
    w.add_argument("--evidence", default="f7-pr-fast-regression-evidence.json")
    w.set_defaults(func=cmd_wait)
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

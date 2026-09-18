#!/usr/bin/env python3
"""Fail-closed contract checks for F7-03 exact-candidate evidence reuse."""
from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("f7_full_regression_gate.py")
spec = importlib.util.spec_from_file_location("f7_full_regression_gate", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

SHA = "a" * 40
BASE = "b" * 40
REF = "codex/example"
ROW = {
    "id": "TP-CI-05",
    "workflow_file": ".github/workflows/tp-ci-05-receipt-shared-stack-postgresql-validation.yml",
    "reuse_required_success_steps": ["Run A", "Run B", "Enforce"],
}

pr_run = {
    "id": 101,
    "event": "pull_request",
    "head_sha": SHA,
    "head_branch": REF,
    "status": "completed",
    "conclusion": "success",
    "created_at": "2026-09-18T10:00:00Z",
    "pull_requests": [{"number": 457, "base": {"sha": BASE}}],
}
assert module.run_matches_reuse_identity(pr_run, REF, SHA, "457", BASE)
assert not module.run_matches_reuse_identity(pr_run, REF, SHA, "457", "c" * 40)
assert not module.run_matches_reuse_identity(pr_run, REF, "d" * 40, "457", BASE)
assert not module.run_matches_reuse_identity(pr_run, "codex/other", SHA, "457", BASE)

manual_run = {
    "id": 102,
    "event": "workflow_dispatch",
    "head_sha": SHA,
    "head_branch": REF,
    "status": "completed",
    "conclusion": "success",
}
assert module.run_matches_reuse_identity(manual_run, REF, SHA, "", "")
assert not module.run_matches_reuse_identity(manual_run, "codex/other", SHA, "", "")

full_jobs = [{"steps": [
    {"name": "Run A", "conclusion": "success"},
    {"name": "Run B", "conclusion": "success"},
    {"name": "Enforce", "conclusion": "success"},
]}]
partial_jobs = [{"steps": [
    {"name": "Run A", "conclusion": "success"},
    {"name": "Run B", "conclusion": "skipped"},
    {"name": "Enforce", "conclusion": "success"},
]}]
assert module.run_has_required_coverage(ROW, full_jobs)
assert not module.run_has_required_coverage(ROW, partial_jobs)
assert module.run_has_required_coverage({**ROW, "reuse_required_success_steps": []}, [])

inflight_jobs = [{"steps": [
    {"name": "Run A", "status": "completed", "conclusion": "success"},
    {"name": "Run B", "status": "in_progress", "conclusion": None},
    {"name": "Enforce", "status": "pending", "conclusion": None},
]}]
inflight_partial_jobs = [{"steps": [
    {"name": "Run A", "status": "completed", "conclusion": "success"},
    {"name": "Enforce", "status": "pending", "conclusion": None},
]}]
assert module.run_has_planned_coverage(ROW, inflight_jobs)
assert not module.run_has_planned_coverage(ROW, inflight_partial_jobs)

original_api = module.api_request
original_jobs = module.run_jobs
try:
    def fake_api(method: str, url: str, token: str, payload=None):
        assert method == "GET"
        return {"workflow_runs": [pr_run]}

    module.api_request = fake_api
    module.run_jobs = lambda repo, run_id, token: full_jobs
    assert module.reusable_success_run("owner/repo", ROW, REF, SHA, "457", BASE, "token") == pr_run

    module.run_jobs = lambda repo, run_id, token: partial_jobs
    assert module.reusable_success_run("owner/repo", ROW, REF, SHA, "457", BASE, "token") is None

    inflight_run = {**pr_run, "id": 103, "status": "in_progress", "conclusion": None}
    module.api_request = lambda method, url, token, payload=None: {"workflow_runs": [inflight_run]}
    module.run_jobs = lambda repo, run_id, token: inflight_jobs
    mode, run = module.existing_reusable_run("owner/repo", ROW, REF, SHA, "457", BASE, "token")
    assert mode == "attached" and run == inflight_run

    module.run_jobs = lambda repo, run_id, token: inflight_partial_jobs
    mode, run = module.existing_reusable_run("owner/repo", ROW, REF, SHA, "457", BASE, "token")
    assert mode is None and run is None
finally:
    module.api_request = original_api
    module.run_jobs = original_jobs

print("F7_03_EXACT_SHA_REUSE_SELFTEST_GREEN")

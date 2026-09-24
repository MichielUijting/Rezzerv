#!/usr/bin/env python3
"""Fail-closed static contract for the first Draft CI fast-loop optimizations."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CANCEL_REQUIRED = (
    ".github/workflows/support-message-api-validation.yml",
    ".github/workflows/support-message-foundation-validation.yml",
    ".github/workflows/gpc-catalog-validation.yml",
    ".github/workflows/gpc-translation-validation.yml",
    ".github/workflows/household-invitation-foundation-validation.yml",
    ".github/workflows/household-invitation-delivery-validation.yml",
    ".github/workflows/household-invitation-acceptance-validation.yml",
    ".github/workflows/postgresql-migration-foundation-validation.yml",
    ".github/workflows/postgresql-data-migration-validation.yml",
    ".github/workflows/postgresql-runtime-startup-schema-authority.yml",
    ".github/workflows/receipt-lifecycle-foundation.yml",
)

RELEASE_WORKFLOW = ROOT / ".github/workflows/release-version-sync-validation.yml"
IMPACT_POLICY = ROOT / "quality/ci/draft_domain_impact_policy.json"
IMPACT_PLANNER = ROOT / "scripts/ci/draft_domain_impact.py"
PR_GROUP_MARKER = "${{ github.event.pull_request.number || github.ref }}"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL CI fast-loop foundation: {message}")


def main() -> int:
    for relative in CANCEL_REQUIRED:
        path = ROOT / relative
        require(path.is_file(), f"missing workflow {relative}")
        text = path.read_text(encoding="utf-8")
        require("pull_request:" in text, f"{relative} lost pull_request trigger")
        require("concurrency:" in text, f"{relative} missing concurrency")
        require(PR_GROUP_MARKER in text, f"{relative} concurrency is not PR-scoped")
        require("cancel-in-progress: true" in text, f"{relative} does not cancel stale runs")

    policy = __import__("json").loads(IMPACT_POLICY.read_text(encoding="utf-8"))
    require(policy.get("policy_id") == "CI-DRAFT-IMPACT-01", "draft impact policy identity drift")
    mapped = policy.get("workflow_domains") or {}
    require(len(mapped) == 8, "draft impact workflow mapping count drift")
    require(IMPACT_PLANNER.is_file(), "draft impact planner missing")
    for relative, domain in mapped.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        require("ready_for_review" in text, f"{relative} must rerun for Ready candidate")
        require("impact-plan:" in text, f"{relative} missing impact planner job")
        require(f"--domain {domain}" in text, f"{relative} domain planner drift")
        require("needs: impact-plan" in text, f"{relative} heavy job is not planner-gated")
        require("if: needs.impact-plan.outputs.run_heavy == 'true'" in text, f"{relative} heavy job gate missing")

    release = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    require("ready_for_review" in release, "release version check must rerun when Draft becomes Ready")
    require("PR_DRAFT: ${{ github.event.pull_request.draft }}" in release, "release version check lost Draft signal")
    require(
        "Draft PR: patchversie wordt pas voor de definitieve kandidaat vóór Ready afgedwongen." in release,
        "release version check no longer defers bump enforcement during Draft",
    )
    require(
        "if ($env:GITHUB_EVENT_NAME -eq 'pull_request' -and $env:PR_DRAFT -eq 'true')" in release,
        "release version Draft guard missing",
    )

    print(f"CI_FAST_LOOP_CANCEL_WORKFLOWS={len(CANCEL_REQUIRED)}")
    print(f"CI_FAST_LOOP_IMPACT_WORKFLOWS={len(mapped)}")
    print("CI_FAST_LOOP_MIGRATION_METADATA=required")
    print("CI_FAST_LOOP_DRAFT_VERSION_DEFERRED=true")
    print("CI_FAST_LOOP_READY_VERSION_ENFORCED=true")
    print("CI_FAST_LOOP_FOUNDATION_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

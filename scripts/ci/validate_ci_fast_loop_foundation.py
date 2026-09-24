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
    print("CI_FAST_LOOP_DRAFT_VERSION_DEFERRED=true")
    print("CI_FAST_LOOP_READY_VERSION_ENFORCED=true")
    print("CI_FAST_LOOP_FOUNDATION_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

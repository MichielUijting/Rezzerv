#!/usr/bin/env python3
"""Fail-closed contract for owner-comment PO test artifact delivery."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
workflow = (ROOT / ".github/workflows/po-test-script-validation.yml").read_text(encoding="utf-8")
governance = (ROOT / "docs/project/PO-TEST-SCRIPT-GOVERNANCE.md").read_text(encoding="utf-8")

assert "  issue_comment:\n    types: [created]" in workflow
assert "  workflow_dispatch:" in workflow  # existing manual route is retained
assert "github.event.issue.pull_request != null" in workflow
assert "startsWith(github.event.comment.body, '/inhuis-po-test ')" in workflow
assert "if ($env:COMMENT_AUTHOR -ine $env:REPOSITORY_OWNER)" in workflow
assert "if ($lines.Count -lt 2 -or $lines[0] -cnotmatch '^/inhuis-po-test ([0-9a-f]{40})$')" in workflow
assert "if ($pr.state -ne 'open')" in workflow
assert "if ($pr.head.repo.full_name -ne $env:GITHUB_REPOSITORY)" in workflow
assert "$pr.head.ref -cnotmatch '^codex/" in workflow
assert "if ($pr.head.sha -cne $env:EXPECTED_SHA)" in workflow
assert "if ($LASTEXITCODE -ne 0) { throw 'Exact PO batch artifact verification failed' }" in workflow
assert "--verify-only" in workflow
assert "windows-latest" in workflow
assert "permissions:\n  contents: read\n  pull-requests: read" in workflow
assert "path: po-test-artifact/*" in workflow
assert "evidence.json" in workflow
assert "issue_comment" in governance
print("PO_TEST_COMMENT_DELIVERY_CONTRACT_GREEN")

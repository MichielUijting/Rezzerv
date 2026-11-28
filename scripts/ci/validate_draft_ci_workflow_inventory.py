#!/usr/bin/env python3
"""Fail-closed inventory contract for the Draft CI router (PR #734)."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

WORKFLOW_DIR = Path(".github/workflows")
VALID_CATEGORIES = {
    "already_routed",
    "migrated_in_pr734",
    "mandatory_direct",
    "other_exception",
}

def trigger_section(text: str, trigger: str) -> list[str]:
    lines = text.splitlines()
    heading = "  " + trigger + ":"
    try:
        start = lines.index(heading)
    except ValueError:
        return []
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line and not line[0].isspace():
            break
        if line.startswith("  ") and not line.startswith("    "):
            break
        end += 1
    return lines[start + 1:end]

def pr_paths(text: str) -> list[str]:
    section = trigger_section(text, "pull_request")
    for index, line in enumerate(section):
        if line == "    paths:":
            paths = []
            for following in section[index + 1:]:
                if not following.startswith("      - "):
                    break
                paths.append(following.strip()[2:].strip().strip("'\""))
            return paths
    return []

def validate(manifest_path: Path) -> dict[str, int]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("unsupported inventory schema")
    entries = data.get("workflows")
    if not isinstance(entries, list):
        raise ValueError("missing workflows array")
    actual = {path.name for path in WORKFLOW_DIR.glob("*.yml")}
    actual.update(path.name for path in WORKFLOW_DIR.glob("*.yaml"))
    names = [entry.get("file") for entry in entries]
    if len(names) != len(set(names)) or set(names) != actual:
        raise ValueError(f"inventory coverage mismatch: missing={sorted(actual - set(names))}, extra={sorted(set(names) - actual)}")
    if data.get("workflow_count") != len(actual):
        raise ValueError("workflow_count does not match directory")
    counts = {name: 0 for name in VALID_CATEGORIES}
    for entry in entries:
        name = entry["file"]
        category = entry.get("category")
        if category not in VALID_CATEGORIES:
            raise ValueError(f"{name}: unknown category {category}")
        text = (WORKFLOW_DIR / name).read_text(encoding="utf-8")
        is_routed = bool(re.search(r"(?m)^# draft-ci-router: routed$", text))
        has_dispatch = bool(re.search(r"(?m)^  workflow_dispatch:", text))
        has_pr = bool(re.search(r"(?m)^  pull_request:", text))
        if category in ("already_routed", "migrated_in_pr734"):
            if not is_routed or not has_dispatch or not has_pr or not pr_paths(text):
                raise ValueError(f"{name}: routed marker, dispatch, PR trigger or paths missing")
            if "ready_for_review" not in "\n".join(trigger_section(text, "pull_request")):
                raise ValueError(f"{name}: Ready event missing from PR trigger")
            for line in text.splitlines():
                if "github.event.pull_request" in line and "||" not in line:
                    raise ValueError(f"{name}: unsafe PR-only context in workflow_dispatch")
        else:
            if is_routed:
                raise ValueError(f"{name}: exception marked as routed")
            if not entry.get("reason"):
                raise ValueError(f"{name}: undocumented exception")
            if category == "mandatory_direct" and not has_pr:
                raise ValueError(f"{name}: direct PR gate has no PR trigger")
            if category == "other_exception":
                kind = entry.get("exception_kind")
                if kind == "manual_dispatch_only":
                    if not has_dispatch or has_pr:
                        raise ValueError(f"{name}: not manual dispatch only")
                elif kind == "reusable_release_authority":
                    if not has_dispatch or not re.search(r"(?m)^  workflow_call:", text) or has_pr:
                        raise ValueError(f"{name}: not a reusable-only authority")
                elif kind == "self_change_diagnostic":
                    if not has_dispatch or pr_paths(text) != [".github/workflows/" + name]:
                        raise ValueError(f"{name}: diagnostic path changed")
                else:
                    raise ValueError(f"{name}: unknown exception kind {kind}")
        counts[category] += 1
    if counts != data.get("counts"):
        raise ValueError(f"inventory totals mismatch: {counts} != {data.get('counts')}")
    return counts

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("quality/ci/draft_ci_workflow_inventory.json"))
    args = parser.parse_args()
    counts = validate(args.manifest)
    print("DRAFT_CI_WORKFLOW_INVENTORY_TOTAL=" + str(sum(counts.values())))
    for name in sorted(counts):
        print("DRAFT_CI_WORKFLOW_INVENTORY_" + name.upper() + "=" + str(counts[name]))
    print("DRAFT_CI_WORKFLOW_INVENTORY_GREEN")

if __name__ == "__main__":
    main()

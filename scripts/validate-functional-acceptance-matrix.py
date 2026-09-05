#!/usr/bin/env python3
"""Validate the Rezzerv Functional Acceptance Matrix.

Normal mode validates the matrix contract and reports coverage gaps without
pretending the current product is release-ready.  --strict-release additionally
turns unresolved P0 release gaps into failures.  The strict mode is intentionally
not used as a required gate until roadmap phase 9.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "quality" / "acceptance" / "functional_acceptance_matrix.json"
EXPECTED_LAYERS = {"L1", "L2", "L3", "L4"}
ALLOWED_PRIORITIES = {"P0", "P1", "P2"}
ALLOWED_STATUSES = {"covered", "partial", "gap", "na"}
ALLOWED_AUDIT_STATUSES = {"inventory", "verified"}
ALLOWED_RUNTIME_LABELS = {
    "sqlite-test-only",
    "postgresql-service",
    "postgresql-api",
    "postgresql-fullstack",
}
POSTGRESQL_LABELS = {
    "postgresql-service",
    "postgresql-api",
    "postgresql-fullstack",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "matrix",
        nargs="?",
        type=Path,
        default=DEFAULT_MATRIX,
        help="Path to functional_acceptance_matrix.json",
    )
    parser.add_argument(
        "--strict-release",
        action="store_true",
        help="Fail when a P0 scenario is not release-ready across its required layers.",
    )
    return parser.parse_args()


def add_error(errors: list[str], scenario_id: str, message: str) -> None:
    errors.append(f"{scenario_id}: {message}")


def validate_matrix(data: dict, strict_release: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if data.get("schema_version") != 1:
        errors.append("matrix: schema_version must be 1")

    declared_statuses = set(data.get("allowed_statuses", []))
    if declared_statuses != ALLOWED_STATUSES:
        errors.append(
            "matrix: allowed_statuses must be exactly " + ", ".join(sorted(ALLOWED_STATUSES))
        )

    declared_runtime = set(data.get("runtime_labels", []))
    if declared_runtime != ALLOWED_RUNTIME_LABELS:
        errors.append(
            "matrix: runtime_labels must be exactly "
            + ", ".join(sorted(ALLOWED_RUNTIME_LABELS))
        )

    declared_audit = set(data.get("audit_statuses", []))
    if declared_audit != ALLOWED_AUDIT_STATUSES:
        errors.append(
            "matrix: audit_statuses must be exactly "
            + ", ".join(sorted(ALLOWED_AUDIT_STATUSES))
        )

    scenarios = data.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        errors.append("matrix: scenarios must be a non-empty list")
        return errors, warnings

    seen_ids: set[str] = set()
    required_fields = {
        "id",
        "domain",
        "chain",
        "priority",
        "runtime_labels",
        "variants",
        "manual_po_acceptance",
        "audit_status",
        "layers",
        "gap",
    }

    for scenario in scenarios:
        if not isinstance(scenario, dict):
            errors.append("matrix: each scenario must be an object")
            continue

        scenario_id = str(scenario.get("id", "<missing-id>"))
        missing = sorted(required_fields - set(scenario))
        if missing:
            add_error(errors, scenario_id, f"missing required fields: {', '.join(missing)}")

        if scenario_id in seen_ids:
            add_error(errors, scenario_id, "duplicate id")
        seen_ids.add(scenario_id)

        priority = scenario.get("priority")
        if priority not in ALLOWED_PRIORITIES:
            add_error(errors, scenario_id, f"invalid priority {priority!r}")
        elif not scenario_id.startswith(f"{priority}-"):
            add_error(errors, scenario_id, "id must start with its priority and '-' ")

        audit_status = scenario.get("audit_status")
        if audit_status not in ALLOWED_AUDIT_STATUSES:
            add_error(errors, scenario_id, f"invalid audit_status {audit_status!r}")

        runtime_labels = scenario.get("runtime_labels")
        if not isinstance(runtime_labels, list) or not runtime_labels:
            add_error(errors, scenario_id, "runtime_labels must be a non-empty list")
            runtime_labels = []
        unknown_runtime = set(runtime_labels) - ALLOWED_RUNTIME_LABELS
        if unknown_runtime:
            add_error(
                errors,
                scenario_id,
                "unknown runtime label(s): " + ", ".join(sorted(unknown_runtime)),
            )

        if priority == "P0" and not (set(runtime_labels) & POSTGRESQL_LABELS):
            add_error(errors, scenario_id, "P0 must include a PostgreSQL runtime label")

        variants = scenario.get("variants")
        if not isinstance(variants, list) or not variants:
            add_error(errors, scenario_id, "variants must be a non-empty list")

        if not isinstance(scenario.get("manual_po_acceptance"), bool):
            add_error(errors, scenario_id, "manual_po_acceptance must be boolean")

        gap = scenario.get("gap")
        if not isinstance(gap, str) or not gap.strip():
            add_error(errors, scenario_id, "gap must explain the current remaining work")

        layers = scenario.get("layers")
        if not isinstance(layers, dict):
            add_error(errors, scenario_id, "layers must be an object")
            continue
        if set(layers) != EXPECTED_LAYERS:
            add_error(errors, scenario_id, "layers must contain exactly L1, L2, L3 and L4")
            continue

        for layer_name, layer in layers.items():
            if not isinstance(layer, dict):
                add_error(errors, scenario_id, f"{layer_name} must be an object")
                continue
            status = layer.get("status")
            evidence = layer.get("evidence")
            if status not in ALLOWED_STATUSES:
                add_error(errors, scenario_id, f"{layer_name} has invalid status {status!r}")
            if not isinstance(evidence, list) or any(
                not isinstance(item, str) or not item.strip() for item in evidence
            ):
                add_error(errors, scenario_id, f"{layer_name}.evidence must be a list of paths")
                evidence = []
            if status == "covered" and not evidence:
                add_error(errors, scenario_id, f"{layer_name} cannot be covered without evidence")
            if status == "gap" and evidence:
                warnings.append(
                    f"{scenario_id}: {layer_name} is gap but still lists evidence; verify classification"
                )

        if priority == "P0":
            p0_unresolved = [
                layer_name
                for layer_name in ("L2", "L3", "L4")
                if layers[layer_name].get("status") not in {"covered", "na"}
            ]
            if p0_unresolved:
                message = "P0 unresolved layers: " + ", ".join(p0_unresolved)
                if strict_release:
                    add_error(errors, scenario_id, message)
                else:
                    warnings.append(f"{scenario_id}: {message}")

    return errors, warnings


def coverage_summary(data: dict) -> str:
    counter: Counter[tuple[str, str]] = Counter()
    for scenario in data.get("scenarios", []):
        priority = scenario.get("priority", "?")
        for layer_name, layer in scenario.get("layers", {}).items():
            counter[(priority, f"{layer_name}:{layer.get('status', '?')}")] += 1

    p0 = [scenario for scenario in data.get("scenarios", []) if scenario.get("priority") == "P0"]
    p0_release_ready = 0
    for scenario in p0:
        layers = scenario.get("layers", {})
        if all(
            layers.get(layer_name, {}).get("status") in {"covered", "na"}
            for layer_name in ("L2", "L3", "L4")
        ):
            p0_release_ready += 1

    statuses = Counter(
        layer.get("status", "?")
        for scenario in data.get("scenarios", [])
        for layer in scenario.get("layers", {}).values()
    )
    return (
        f"scenarios={len(data.get('scenarios', []))} "
        f"p0={len(p0)} p0_release_ready={p0_release_ready} "
        f"covered={statuses['covered']} partial={statuses['partial']} "
        f"gap={statuses['gap']} na={statuses['na']}"
    )


def main() -> int:
    args = parse_args()
    matrix_path = args.matrix if args.matrix.is_absolute() else (ROOT / args.matrix)
    if not matrix_path.exists():
        print(f"[ERROR] Matrix not found: {matrix_path}")
        return 2

    try:
        data = json.loads(matrix_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[ERROR] Cannot read matrix: {exc}")
        return 2

    if not isinstance(data, dict):
        print("[ERROR] Matrix root must be an object")
        return 2

    errors, warnings = validate_matrix(data, args.strict_release)

    print("REZZERV_FUNCTIONAL_ACCEPTANCE_MATRIX")
    print(f"mode={'strict-release' if args.strict_release else 'structural'}")
    print(coverage_summary(data))

    for warning in warnings:
        print(f"[WARN] {warning}")
    for error in errors:
        print(f"[ERROR] {error}")

    if errors:
        print("FUNCTIONAL_ACCEPTANCE_MATRIX_RED")
        return 1

    print("FUNCTIONAL_ACCEPTANCE_MATRIX_GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())

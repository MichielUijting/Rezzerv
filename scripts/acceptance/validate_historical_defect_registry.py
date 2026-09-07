from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "quality" / "regression" / "historical_defect_registry.json"

REQUIRED_KEYS = {
    "boolean-runtime-portability",
    "postgresql-json-serialization",
    "receipt-worker-fail-closed-status",
    "receipt-source-runtime-wiring",
    "quantity-unbounded-decimals",
    "historical-quantity-restoration",
    "household-location-policy",
    "locationless-unpacking",
    "unclassified-unpacking-choice",
    "household-article-canonical-identity",
    "history-postgresql-null-sorting",
    "locationless-history-events",
    "conditional-locations-tab",
    "standard-api-error-feedback",
}


def main() -> int:
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert payload.get("schema_version") == 1, payload.get("schema_version")
    assert payload.get("phase") == "F5-historical-regression-foundation", payload.get("phase")

    statuses = set(payload.get("status_values") or [])
    assert statuses == {"pending_audit", "candidate", "partial", "covered", "gap"}, statuses

    classes = payload.get("defect_classes")
    assert isinstance(classes, list) and len(classes) == 14, len(classes or [])

    ids = [str(item.get("id") or "") for item in classes]
    keys = [str(item.get("key") or "") for item in classes]
    assert len(ids) == len(set(ids)), ids
    assert len(keys) == len(set(keys)), keys
    assert set(keys) == REQUIRED_KEYS, sorted(REQUIRED_KEYS - set(keys))

    for item in classes:
        status = str(item.get("status") or "")
        assert status in statuses, item
        evidence = item.get("evidence") or []
        assert isinstance(evidence, list), item
        if status in {"candidate", "partial", "covered"}:
            assert evidence, f"{item['key']} heeft status {status} zonder evidence"
            for relative_path in evidence:
                path = ROOT / str(relative_path)
                assert path.is_file(), f"Evidencepad ontbreekt voor {item['key']}: {relative_path}"

    boolean_entry = next(item for item in classes if item["key"] == "boolean-runtime-portability")
    assert boolean_entry["status"] == "covered", boolean_entry
    assert len(boolean_entry.get("acceptance") or []) >= 5, boolean_entry

    json_entry = next(item for item in classes if item["key"] == "postgresql-json-serialization")
    assert json_entry["status"] == "covered", json_entry
    assert len(json_entry.get("acceptance") or []) >= 5, json_entry

    worker_entry = next(item for item in classes if item["key"] == "receipt-worker-fail-closed-status")
    assert worker_entry["status"] in {"candidate", "covered"}, worker_entry
    assert len(worker_entry.get("acceptance") or []) >= 6, worker_entry

    source_entry = next(item for item in classes if item["key"] == "receipt-source-runtime-wiring")
    assert source_entry["status"] in {"candidate", "covered"}, source_entry
    assert len(source_entry.get("acceptance") or []) >= 6, source_entry

    quantity_entry = next(item for item in classes if item["key"] == "quantity-unbounded-decimals")
    assert quantity_entry["status"] in {"candidate", "covered"}, quantity_entry
    assert len(quantity_entry.get("acceptance") or []) >= 6, quantity_entry

    restoration_entry = next(item for item in classes if item["key"] == "historical-quantity-restoration")
    assert restoration_entry["status"] in {"candidate", "covered"}, restoration_entry
    assert len(restoration_entry.get("acceptance") or []) >= 6, restoration_entry

    print("PASS historical_defect_registry_has_exact_14_required_classes")
    print("PASS historical_defect_registry_statuses_are_conservative")
    print("PASS historical_defect_registry_evidence_paths_exist")
    print("PASS boolean_runtime_portability_has_explicit_acceptance_and_evidence")
    print("PASS postgresql_json_serialization_has_explicit_acceptance_and_evidence")
    print("PASS receipt_worker_fail_closed_has_explicit_acceptance_and_evidence")
    print("PASS receipt_source_runtime_wiring_has_explicit_acceptance_and_evidence")
    print("PASS quantity_unbounded_decimals_has_explicit_acceptance_and_evidence")
    print("PASS historical_quantity_restoration_has_explicit_acceptance_and_evidence")
    print("F5_HISTORICAL_DEFECT_REGISTRY_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

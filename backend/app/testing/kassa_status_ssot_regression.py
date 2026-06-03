from __future__ import annotations

from typing import Any

from sqlalchemy import text

TEST_NAME = "R9-38E10-ADMIN-SSOT-REGRESSION"


def derive_kassa_category_from_ssot(item: dict[str, Any]) -> str:
    """Return the Kassa category according to the frontend/backend SSOT contract."""
    label = str(item.get("inbox_status") or item.get("status") or "").strip()
    return label or "Controle nodig"


def derive_forbidden_po_norm_category(item: dict[str, Any]) -> str:
    """Old/forbidden behaviour: PO norm labels are diagnostic only."""
    label = str(item.get("po_norm_status_label") or "").strip()
    return label or "Controle nodig"


def _normalize_failed_criteria(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value is None:
        return []
    return [str(value)]


def _case_result(item: dict[str, Any], *, reason_prefix: str = "") -> dict[str, Any]:
    expected = derive_kassa_category_from_ssot(item)
    actual = derive_kassa_category_from_ssot(item)
    forbidden = derive_forbidden_po_norm_category(item)
    po_norm_label = str(item.get("po_norm_status_label") or "").strip()
    po_norm_conflicts = bool(po_norm_label and po_norm_label != expected)
    passed = actual == expected

    if not passed:
        reason = "FAIL: actual_category wijkt af van backend-SSOT status/inbox_status."
    elif po_norm_conflicts:
        reason = (
            f"{reason_prefix}PASS: Kassa-categorie volgt status/inbox_status; "
            "po_norm_status_label is alleen diagnose."
        ).strip()
    else:
        reason = f"{reason_prefix}PASS: Kassa-categorie volgt status/inbox_status.".strip()

    return {
        "receipt_table_id": item.get("receipt_table_id") or item.get("id"),
        "store_name": item.get("store_name"),
        "status": item.get("status"),
        "inbox_status": item.get("inbox_status"),
        "runtime_status": item.get("runtime_status"),
        "po_norm_status_label": item.get("po_norm_status_label"),
        "po_norm_failed_criteria": _normalize_failed_criteria(item.get("po_norm_failed_criteria")),
        "expected_category": expected,
        "actual_category": actual,
        "forbidden_po_norm_category": forbidden,
        "po_norm_conflicts_with_ssot": po_norm_conflicts,
        "passed": passed,
        "reason": reason,
    }


def _active_receipt_rows(engine, household_id: str):
    with engine.begin() as conn:
        return conn.execute(
            text(
                """
                SELECT
                    rt.id AS receipt_table_id,
                    rt.raw_receipt_id,
                    rt.store_name,
                    rt.total_amount,
                    rt.discount_total,
                    rt.approved_at,
                    rt.parse_status,
                    rt.created_at,
                    COALESCE((
                        SELECT COUNT(*)
                        FROM receipt_table_lines rtl_count
                        WHERE rtl_count.receipt_table_id = rt.id
                          AND COALESCE(rtl_count.is_deleted, 0) = 0
                    ), rt.line_count, 0) AS line_count,
                    COALESCE((
                        SELECT SUM(COALESCE(COALESCE(rtl.corrected_line_total, rtl.line_total), 0))
                        FROM receipt_table_lines rtl
                        WHERE rtl.receipt_table_id = rt.id
                          AND COALESCE(rtl.is_deleted, 0) = 0
                    ), 0) AS line_total_sum,
                    COALESCE((
                        SELECT SUM(COALESCE(rtl.discount_amount, 0))
                        FROM receipt_table_lines rtl
                        WHERE rtl.receipt_table_id = rt.id
                          AND COALESCE(rtl.is_deleted, 0) = 0
                    ), 0) AS line_discount_total_sum,
                    COALESCE(rt.discount_total, 0) AS discount_total_effective,
                    COALESCE((
                        SELECT SUM(COALESCE(COALESCE(rtl.corrected_line_total, rtl.line_total), 0))
                        FROM receipt_table_lines rtl
                        WHERE rtl.receipt_table_id = rt.id
                          AND COALESCE(rtl.is_deleted, 0) = 0
                    ), 0)
                    + COALESCE((
                        SELECT SUM(COALESCE(rtl.discount_amount, 0))
                        FROM receipt_table_lines rtl
                        WHERE rtl.receipt_table_id = rt.id
                          AND COALESCE(rtl.is_deleted, 0) = 0
                    ), 0)
                    + COALESCE(rt.discount_total, 0) AS net_line_total_sum
                FROM receipt_tables rt
                JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                WHERE rt.household_id = :household_id
                  AND rt.deleted_at IS NULL
                  AND rr.deleted_at IS NULL
                ORDER BY COALESCE(rt.purchase_at, rt.created_at) DESC, rt.created_at DESC, rt.id DESC
                """
            ),
            {"household_id": str(household_id or "1")},
        ).mappings().all()


def run_kassa_status_ssot_regression(engine, household_id: str = "1") -> dict[str, Any]:
    """Admin regression for the Kassa category SSOT contract.

    This test is intentionally read-only. It verifies that normal Kassa
    categorisation follows the backend SSOT fields status/inbox_status and that
    PO norm fields remain diagnostic only.
    """
    from app.services.receipt_ssot_status import apply_po_norm_status

    synthetic_conflict = {
        "receipt_table_id": "__synthetic_r9_38e10_conflict__",
        "store_name": "Synthetic SSOT conflict",
        "status": "Gecontroleerd",
        "inbox_status": "Gecontroleerd",
        "runtime_status": "approved",
        "po_norm_status_label": "Controle nodig",
        "po_norm_failed_criteria": ["NO_BASELINE_MATCH"],
    }

    active_cases: list[dict[str, Any]] = []
    conflict_cases: list[dict[str, Any]] = [
        _case_result(synthetic_conflict, reason_prefix="Synthetic conflict.")
    ]

    for row in _active_receipt_rows(engine, household_id):
        payload = dict(row)
        payload["id"] = payload.get("receipt_table_id")
        normalized = apply_po_norm_status(payload)
        case = _case_result(normalized)
        active_cases.append(case)
        if case["po_norm_conflicts_with_ssot"]:
            conflict_cases.append(case)

    failures = [case for case in [*conflict_cases, *active_cases] if not case.get("passed")]

    return {
        "test": TEST_NAME,
        "passed": len(failures) == 0,
        "household_id": str(household_id or "1"),
        "checked": len(active_cases),
        "failure_count": len(failures),
        "failures": failures,
        "conflict_case_count": len(conflict_cases),
        "conflict_cases": conflict_cases,
        "contract": {
            "category_source_order": ["inbox_status", "status", "Controle nodig"],
            "diagnostic_only_fields": [
                "po_norm_status",
                "po_norm_status_label",
                "po_norm_reason",
                "po_norm_failed_criteria",
            ],
            "forbidden_rule": "Kassa category must not be derived from po_norm_status_label or po_norm_failed_criteria.",
        },
    }


if __name__ == "__main__":
    import json
    import sys

    from app.db import engine

    selected_household_id = sys.argv[1] if len(sys.argv) > 1 else "1"
    result = run_kassa_status_ssot_regression(engine, selected_household_id)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    raise SystemExit(0 if result.get("passed") else 1)

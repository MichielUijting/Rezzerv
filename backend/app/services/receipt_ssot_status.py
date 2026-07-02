"""
Technical Design Reference:
- TD Section: TD-04 Status en SSOT
- Module Role: Map production PO norm status to API/UI fields
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: receipt payload content only
- Reads Data: none
- Writes Data: none
- Status Authority: yes
- Refactor Status: cleanup
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def _safe_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _amount_equals(left: Any, right: Any, tolerance: Decimal = Decimal("0.01")) -> bool:
    left_dec = _safe_decimal(left)
    right_dec = _safe_decimal(right)
    if left_dec is None or right_dec is None:
        return False
    return abs(left_dec - right_dec) <= tolerance


def _normalize_status_label(label: Any) -> str:
    """Normalize active Kassa status labels.

    The active Kassa contract exposes only Gecontroleerd or Controle nodig.
    """
    normalized = str(label or "").strip()
    if normalized == "Gecontroleerd":
        return "Gecontroleerd"
    return "Controle nodig"


def _status_code(label: str) -> str:
    return "controlled" if _normalize_status_label(label) == "Gecontroleerd" else "review"


def _line_count(payload: dict[str, Any]) -> int:
    value = payload.get("line_count")
    if value is None and isinstance(payload.get("lines"), list):
        value = len([
            line for line in payload.get("lines") or []
            if isinstance(line, dict) and int(line.get("is_deleted") or 0) == 0
        ])
    try:
        return int(value or 0)
    except Exception:
        return 0


def _line_discount_total(payload: dict[str, Any]) -> Decimal:
    lines = payload.get("lines")
    if isinstance(lines, list):
        total = Decimal("0")
        for line in lines:
            if not isinstance(line, dict) or int(line.get("is_deleted") or 0):
                continue
            value = _safe_decimal(line.get("discount_amount"))
            if value is not None:
                total += value
        return total

    value = _safe_decimal(payload.get("line_discount_sum"))
    return value if value is not None else Decimal("0")


def _receipt_discount_total(payload: dict[str, Any]) -> Decimal:
    value = _safe_decimal(payload.get("discount_total"))
    return value if value is not None else Decimal("0")


def _line_total_from_lines(payload: dict[str, Any]) -> Decimal | None:
    lines = payload.get("lines")
    if not isinstance(lines, list):
        return None

    total = Decimal("0")
    seen = False
    for line in lines:
        if not isinstance(line, dict) or int(line.get("is_deleted") or 0):
            continue
        value = _safe_decimal(
            line.get("display_line_total")
            if line.get("display_line_total") is not None
            else line.get("corrected_line_total")
            if line.get("corrected_line_total") is not None
            else line.get("line_total")
        )
        if value is None:
            continue
        total += value
        seen = True
    return total if seen else None


def _net_line_total(payload: dict[str, Any]) -> Decimal | None:
    line_total = _line_total_from_lines(payload)

    if line_total is None:
        line_total = _safe_decimal(payload.get("line_total_sum"))

    if line_total is not None:
        return line_total + _line_discount_total(payload) + _receipt_discount_total(payload)

    return _safe_decimal(payload.get("net_line_total_sum"))


def _production_status_item(payload: dict[str, Any]) -> dict[str, Any]:
    """Determine production Kassa status from receipt content only.

    The 14-receipt baseline is regression fixture data. Baseline membership is
    not a production criterion and must never create NO_BASELINE_MATCH.
    """
    failed: list[str] = []

    store_name = str(payload.get("store_name") or payload.get("store_branch") or "").strip()
    if not store_name:
        failed.append("STORE_NAME_MISSING")

    total_amount = _safe_decimal(payload.get("total_amount"))
    if total_amount is None:
        failed.append("TOTAL_AMOUNT_MISSING")

    line_count = _line_count(payload)
    if line_count <= 0:
        failed.append("NO_ARTICLE_LINES")

    net_line_sum = _net_line_total(payload)
    if total_amount is not None and line_count > 0:
        if net_line_sum is None:
            failed.append("LINE_SUM_MISSING")
        elif not _amount_equals(net_line_sum, total_amount):
            failed.append("LINE_SUM_TOTAL_MISMATCH")

    label = "Gecontroleerd" if not failed else "Controle nodig"

    if not failed:
        reason = (
            "Gecontroleerd: winkel, totaalbedrag en som van artikelregels "
            "voldoen aan productieve Kassa-statuscriteria."
        )
    else:
        labels = {
            "STORE_NAME_MISSING": "winkelnaam ontbreekt",
            "TOTAL_AMOUNT_MISSING": "totaalbedrag ontbreekt",
            "NO_ARTICLE_LINES": "geen artikelregels gevonden",
            "LINE_SUM_MISSING": "som van artikelregels ontbreekt",
            "LINE_SUM_TOTAL_MISMATCH": "som van artikelregels sluit niet aan op kassabontotaal",
        }
        reason = "Controle nodig: " + "; ".join(labels.get(code, code) for code in failed)

    return {
        "po_norm_status": _status_code(label),
        "po_norm_status_label": label,
        "po_norm_failed_criteria": failed,
        "po_norm_reason": reason,
    }


def load_po_norm_status_items() -> dict[str, dict[str, Any]]:
    """Compatibility shim.

    Production status is computed per receipt payload in apply_po_norm_status.
    The regression baseline is intentionally not loaded here.
    """
    return {}


def apply_po_norm_status(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply the SSOT status contract to a receipt payload for Kassa.

    Parser status fields may exist in storage as diagnostics, but they are not
    allowed to drive Kassa categorisation. The 14-receipt regression baseline is
    also not allowed to drive production categorisation.
    """
    if not isinstance(payload, dict):
        return payload

    item = _production_status_item(payload)
    label = _normalize_status_label(item.get("po_norm_status_label"))
    status_code = _status_code(label)

    payload.pop("parse_status", None)
    payload.pop("actual_parse_status", None)
    payload.pop("actual_status_label", None)

    payload["po_norm_status"] = status_code
    payload["po_norm_status_label"] = label
    payload["po_norm_failed_criteria"] = item.get("po_norm_failed_criteria") or []
    payload["po_norm_reason"] = item.get("po_norm_reason")
    payload["inbox_status"] = label
    payload["status"] = label

    if any(key in payload for key in ("parse_status", "actual_parse_status", "actual_status_label")):
        raise RuntimeError("INVALID STATUS SOURCE")
    return payload

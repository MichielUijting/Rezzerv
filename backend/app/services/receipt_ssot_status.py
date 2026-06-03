
from __future__ import annotations
def _r9_38d6_decimal(value):
    from decimal import Decimal
    try:
        if value is None or value == "":
            return Decimal("0.00")
        return Decimal(str(value))
    except Exception:
        return Decimal("0.00")


def _r9_38d6_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _r9_38d6_runtime_status_override(receipt_payload: dict) -> dict:
    """R9-38D6: runtime status is not controlled by baseline NO_BASELINE_MATCH.

    The PO baseline remains available for regression diagnostics, but a new
    real receipt that parses cleanly must show as Gecontroleerd when:
    - parse_status is approved OR approved_at is filled;
    - net line total matches total_amount;
    - the only PO failure is NO_BASELINE_MATCH.
    """
    if not isinstance(receipt_payload, dict):
        return receipt_payload

    failed = set(str(x) for x in _r9_38d6_list(receipt_payload.get("po_norm_failed_criteria")))
    only_no_baseline_match = bool(failed) and failed.issubset({"NO_BASELINE_MATCH"})

    parse_status = str(receipt_payload.get("parse_status") or "").lower()
    approved_at = receipt_payload.get("approved_at")
    approved_like = parse_status == "approved" or bool(approved_at)

    total = _r9_38d6_decimal(receipt_payload.get("total_amount"))

    # R9-38E4: runtime status must use the full SSOT net formula:
    # sum(line_total) + sum(discount_amount) + discount_total_effective.
    line_sum = _r9_38d6_decimal(receipt_payload.get("line_total_sum"))
    line_discount_sum = _r9_38d6_decimal(
        receipt_payload.get("line_discount_total_sum")
        if receipt_payload.get("line_discount_total_sum") is not None
        else receipt_payload.get("line_discount_sum")
    )
    discount_effective = _r9_38d6_decimal(receipt_payload.get("discount_total_effective"))
    net = line_sum + line_discount_sum + discount_effective

    receipt_payload["net_line_total_sum"] = float(net.quantize(_r9_38d6_decimal("0.01")))

    totals_match = abs(net - total) <= _r9_38d6_decimal("0.02")

    if only_no_baseline_match and approved_like and totals_match:
        receipt_payload["inbox_status"] = "Gecontroleerd"
        receipt_payload["status"] = "Gecontroleerd"
        receipt_payload["runtime_status"] = "approved"
        receipt_payload["runtime_status_label"] = "Gecontroleerd"
        receipt_payload["runtime_status_source"] = "parser"
        receipt_payload["po_norm_status_is_diagnostic_only"] = True

    return receipt_payload



import logging
import time
from typing import Any

from app.db import engine
from app.services.receipt_status_baseline_service_v4 import validate_receipt_status_baseline

LOGGER = logging.getLogger(__name__)
_CACHE: dict[str, Any] = {"loaded_at": 0.0, "items": {}}
_CACHE_TTL_SECONDS = 1.0


def _normalize_status_label(label: Any) -> str:
    """Normalize legacy receipt status labels for the active Kassa UI.

    Historical parser/status diagnostics may still contain manual/Handmatig.
    The active Kassa contract exposes only Gecontroleerd or Controle nodig.
    """
    normalized = str(label or "").strip()
    if normalized in {"", "Handmatig", "manual"}:
        return "Controle nodig"
    return normalized


def _status_code(label: str) -> str:
    normalized_label = _normalize_status_label(label)
    if normalized_label == "Gecontroleerd":
        return "controlled"
    return "review"


def load_po_norm_status_items() -> dict[str, dict[str, Any]]:
    now = time.monotonic()
    cached_items = _CACHE.get("items") or {}
    if cached_items and (now - float(_CACHE.get("loaded_at") or 0.0)) < _CACHE_TTL_SECONDS:
        return dict(cached_items)

    items: dict[str, dict[str, Any]] = {}
    try:
        with engine.connect() as conn:
            validation = validate_receipt_status_baseline(conn)
        for item in validation.get("details", []) or []:
            receipt_table_id = str(item.get("receipt_table_id") or "").strip()
            if not receipt_table_id:
                continue
            label = _normalize_status_label(item.get("po_norm_status_label") or "Controle nodig")
            items[receipt_table_id] = {
                "po_norm_status": _status_code(label),
                "po_norm_status_label": label,
                "po_norm_failed_criteria": item.get("failed_criteria") or [],
                "po_norm_reason": item.get("reason"),
            }
    except Exception as exc:
        LOGGER.warning("po_norm_status_items_load_failed error=%s", exc)

    _CACHE["loaded_at"] = now
    _CACHE["items"] = items
    return items


def apply_po_norm_status(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply the SSOT status contract to a receipt payload for Kassa.

    Parser status fields are allowed to exist in storage as diagnostics, but they
    are not allowed to drive Kassa categorisation. This function removes them
    from the Kassa payload and exposes only the baseline-derived status fields.
    """
    if not isinstance(payload, dict):
        return _r9_38d6_runtime_status_override(payload)

    receipt_table_id = str(payload.get("id") or payload.get("receipt_table_id") or "").strip()
    item = load_po_norm_status_items().get(receipt_table_id) if receipt_table_id else None
    if not item:
        item = {
            "po_norm_status": "review",
            "po_norm_status_label": "Controle nodig",
            "po_norm_failed_criteria": ["NO_BASELINE_MATCH"],
            "po_norm_reason": "Controle nodig: geen baseline-match gevonden voor deze actieve kassabon.",
        }

    label = _normalize_status_label(item.get("po_norm_status_label"))
    status_code = _status_code(label)

    payload.pop("parse_status", None)
    payload.pop("actual_parse_status", None)
    payload.pop("actual_status_label", None)
    payload["po_norm_status"] = status_code
    payload["po_norm_status_label"] = label
    payload["po_norm_failed_criteria"] = item.get("po_norm_failed_criteria") or []
    payload["po_norm_reason"] = item.get("po_norm_reason")

    # R9-38E4b:
    # PO/baseline status is diagnostic for new receipts.
    # It must not override runtime status when the parser approved the receipt
    # and the full net formula closes.
    payload["inbox_status"] = label
    payload["status"] = label
    payload = _r9_38d6_runtime_status_override(payload)

    if any(key in payload for key in ("parse_status", "actual_parse_status", "actual_status_label")):
        raise RuntimeError("INVALID STATUS SOURCE")
    return _r9_38d6_runtime_status_override(payload)

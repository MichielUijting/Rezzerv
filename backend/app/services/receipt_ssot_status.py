from __future__ import annotations

import logging
import time
from typing import Any

from app.db import engine
from app.services.receipt_status_baseline_service_v4 import validate_receipt_status_baseline

LOGGER = logging.getLogger(__name__)
_CACHE: dict[str, Any] = {"loaded_at": 0.0, "items": {}}
_CACHE_TTL_SECONDS = 1.0


def _status_code(label: str) -> str:
    if label == "Gecontroleerd":
        return "controlled"
    if label == "Handmatig":
        return "manual"
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
            label = str(item.get("po_norm_status_label") or "Controle nodig")
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
        return payload

    receipt_table_id = str(payload.get("id") or payload.get("receipt_table_id") or "").strip()
    item = load_po_norm_status_items().get(receipt_table_id) if receipt_table_id else None
    if not item:
        item = {
            "po_norm_status": "review",
            "po_norm_status_label": "Controle nodig",
            "po_norm_failed_criteria": ["NO_BASELINE_MATCH"],
            "po_norm_reason": "Controle nodig: geen baseline-match gevonden voor deze actieve kassabon.",
        }

    payload.pop("parse_status", None)
    payload.pop("actual_parse_status", None)
    payload.pop("actual_status_label", None)
    payload["po_norm_status"] = item["po_norm_status"]
    payload["po_norm_status_label"] = item["po_norm_status_label"]
    payload["po_norm_failed_criteria"] = item.get("po_norm_failed_criteria") or []
    payload["po_norm_reason"] = item.get("po_norm_reason")
    payload["inbox_status"] = item["po_norm_status_label"]
    payload["status"] = item["po_norm_status_label"]

    if any(key in payload for key in ("parse_status", "actual_parse_status", "actual_status_label")):
        raise RuntimeError("INVALID STATUS SOURCE")
    return payload

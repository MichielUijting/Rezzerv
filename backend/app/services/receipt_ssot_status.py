from __future__ import annotations

import logging
from typing import Any

from app.db import engine
from app.services.receipt_status_baseline_service_v4 import validate_receipt_status_baseline

LOGGER = logging.getLogger(__name__)
VALID_PO_LABELS = {"Gecontroleerd", "Controle nodig", "Handmatig"}


def _status_code(label: str) -> str:
    if label == "Gecontroleerd":
        return "controlled"
    if label == "Handmatig":
        return "manual"
    return "review"


def _household_id_from_payload(payload: dict[str, Any]) -> str | None:
    household_id = str(payload.get("household_id") or "").strip()
    return household_id or None


def load_po_norm_status_items(household_id: str | None = None) -> dict[str, dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    with engine.connect() as conn:
        validation = validate_receipt_status_baseline(conn, household_id=household_id)
    for item in validation.get("details", []) or []:
        receipt_table_id = str(item.get("receipt_table_id") or "").strip()
        if not receipt_table_id:
            continue
        label = str(item.get("po_norm_status_label") or "Controle nodig").strip()
        if label not in VALID_PO_LABELS:
            label = "Controle nodig"
        items[receipt_table_id] = {
            "po_norm_status": _status_code(label),
            "po_norm_status_label": label,
            "po_norm_failed_criteria": item.get("failed_criteria") or [],
            "po_norm_reason": item.get("reason"),
            "po_norm_policy_source": "receipt_status_baseline_service_v4.py",
        }
    return items


def apply_po_norm_status(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return payload

    receipt_table_id = str(payload.get("id") or payload.get("receipt_table_id") or "").strip()
    item = load_po_norm_status_items(_household_id_from_payload(payload)).get(receipt_table_id) if receipt_table_id else None
    if not item:
        item = {
            "po_norm_status": "review",
            "po_norm_status_label": "Controle nodig",
            "po_norm_failed_criteria": ["NO_BASELINE_MATCH"],
            "po_norm_reason": "Controle nodig: geen baseline-match gevonden voor deze actieve kassabon.",
            "po_norm_policy_source": "receipt_status_baseline_service_v4.py",
        }

    for key in (
        "parse_status",
        "actual_parse_status",
        "actual_status_label",
        "technical_parse_status",
        "technical_parse_status_label",
        "backend_status",
        "backend_status_label",
    ):
        payload.pop(key, None)

    payload["po_norm_status"] = item["po_norm_status"]
    payload["po_norm_status_label"] = item["po_norm_status_label"]
    payload["po_norm_failed_criteria"] = item.get("po_norm_failed_criteria") or []
    payload["po_norm_reason"] = item.get("po_norm_reason")
    payload["po_norm_policy_source"] = item.get("po_norm_policy_source") or "receipt_status_baseline_service_v4.py"
    payload["inbox_status"] = item["po_norm_status_label"]
    payload["status"] = item["po_norm_status_label"]
    return payload

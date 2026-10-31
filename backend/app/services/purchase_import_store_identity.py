"""Authoritative store name from purchase-import batch metadata.

This source-only value must be shared by overview, OFF search and confirmation.
Never infer a store from product brand or user-supplied link payload.
"""
from __future__ import annotations

import json
from typing import Any


def retailer_from_purchase_import_payload(raw_payload: Any) -> str:
    if not raw_payload:
        return ""
    try:
        payload = json.loads(raw_payload) if isinstance(raw_payload, (str, bytes, bytearray)) else raw_payload
    except (TypeError, ValueError):
        return ""
    if not isinstance(payload, dict):
        return ""

    metadata = payload.get("batch_metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    for value in (
        metadata.get("store_name"),
        metadata.get("store_label"),
        payload.get("store_name"),
        payload.get("store_label"),
        payload.get("retailer_code"),
        payload.get("retailer"),
    ):
        normalized = str(value or "").strip()
        if normalized and normalized.lower() not in {"-", "import", "onbekend", "unknown"}:
            return normalized
    return ""

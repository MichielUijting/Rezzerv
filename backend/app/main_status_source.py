"""FastAPI entrypoint that uses database parse_status as Kassa status source.

This keeps app.main intact but patches the status presentation function before
serving requests. Uvicorn loads this module instead of app.main directly.
"""

from __future__ import annotations

from typing import Any

from app import main as _main


def map_parse_status_to_inbox_status(receipt: dict[str, Any] | None) -> str:
    status = str((receipt or {}).get("parse_status") or "").strip().lower()
    if status in {"approved", "parsed", "approved_override"}:
        return "Gecontroleerd"
    if status in {"review_needed", "partial"}:
        return "Controle nodig"
    return "Handmatig"


# list_receipts() resolves derive_unpack_receipt_status from app.main globals at
# request time. Replacing it here makes /api/receipts expose the stored DB status
# as the visible Kassa inbox status.
_main.derive_unpack_receipt_status = map_parse_status_to_inbox_status

app = _main.app

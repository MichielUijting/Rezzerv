"""Rezzerv application package bootstrap.

Patch Kassa status presentation so /api/receipts uses receipt_tables.parse_status
as the single source of truth for the visible inbox status.
"""

from __future__ import annotations

import sys
import threading
import time
from typing import Any


def _map_parse_status_to_inbox_status(receipt: dict[str, Any]) -> str:
    status = str((receipt or {}).get("parse_status") or "").strip().lower()
    if status in {"approved", "parsed"}:
        return "Gecontroleerd"
    if status in {"review_needed", "partial"}:
        return "Controle nodig"
    return "Handmatig"


def _install_parse_status_inbox_mapping() -> None:
    for _ in range(200):
        main_module = sys.modules.get("app.main")
        if main_module is not None and hasattr(main_module, "derive_unpack_receipt_status"):
            try:
                main_module.derive_unpack_receipt_status = _map_parse_status_to_inbox_status
            except Exception:
                pass
            return
        time.sleep(0.05)


try:
    threading.Thread(target=_install_parse_status_inbox_mapping, daemon=True).start()
except Exception:
    pass

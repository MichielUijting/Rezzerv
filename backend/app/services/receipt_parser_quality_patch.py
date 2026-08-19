"""
Technical Design Reference:
- TD Section: TD-05 Datastore en services
- Module Role: Backend application module
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

from __future__ import annotations

import threading
import time
from typing import Any

_LAST_INGEST_DEBUG_CAPTURE: dict[str, Any] = {}
_RECOVERY_INSTALL_LOCK = threading.Lock()
_RECOVERY_INSTALLED = False


def get_latest_ingest_debug_capture() -> dict[str, Any]:
    return dict(_LAST_INGEST_DEBUG_CAPTURE)


def _run_stale_receipt_recovery_when_ready(module: Any) -> None:
    for _ in range(600):
        if (
            hasattr(module, "engine")
            and hasattr(module, "RECEIPT_STORAGE_ROOT")
            and hasattr(module, "reparse_suspicious_receipts")
            and hasattr(module, "list_receipts")
        ):
            try:
                from app.services.receipt_stale_recovery_service import (
                    run_safe_stale_receipt_recovery,
                )

                report = run_safe_stale_receipt_recovery(
                    module.engine,
                    module.RECEIPT_STORAGE_ROOT,
                    limit=1000,
                )
                print(f"Safe stale receipt recovery: {report}", flush=True)
            except Exception as exc:
                # Recovery is deliberately isolated from API availability. The
                # release stays usable and the failure remains visible in logs.
                print(f"Safe stale receipt recovery failed: {exc}", flush=True)
            return
        time.sleep(0.1)
    print("Safe stale receipt recovery skipped: receipt schema did not become ready", flush=True)


def install_parser_quality_patch(module: Any, *_: Any) -> bool:
    global _RECOVERY_INSTALLED
    with _RECOVERY_INSTALL_LOCK:
        if _RECOVERY_INSTALLED:
            return True
        _RECOVERY_INSTALLED = True
    threading.Thread(
        target=_run_stale_receipt_recovery_when_ready,
        args=(module,),
        daemon=True,
        name="rezzerv-stale-receipt-recovery",
    ).start()
    return True

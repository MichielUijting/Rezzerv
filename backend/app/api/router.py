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

import os
from pathlib import Path

from fastapi import APIRouter

from app.db import engine
from app.api.article_group_routes import router as article_group_router
from app.api.barcode_routes import router as barcode_router
from app.api.day_article_routes import router as day_article_router
from app.api.loyalty_stamp_routes import router as loyalty_stamp_router
from app.api.support_message_routes import router as support_message_router
from app.api.routes.debug import router as debug_router
from app.api.routes.receipt_db_snapshot import router as receipt_db_snapshot_router
from app.api.routes.kassa_regression_routes import router as kassa_regression_router
from app.api.routes.kassa_smoke_routes import router as kassa_smoke_router
from app.services import receipt_parser_quality_patch
from app.services import receipt_loyalty_line_patch
from app.services import receipt_g1_merge
from app.services.receipt_stale_recovery_service import run_safe_stale_receipt_recovery

api_router = APIRouter()
api_router.include_router(article_group_router)
api_router.include_router(barcode_router)
api_router.include_router(day_article_router)
api_router.include_router(loyalty_stamp_router)
api_router.include_router(support_message_router)
api_router.include_router(debug_router)
api_router.include_router(receipt_db_snapshot_router)
api_router.include_router(kassa_regression_router)
api_router.include_router(kassa_smoke_router)


@api_router.on_event("startup")
def recover_stale_kassa_results_before_serving_requests() -> None:
    """Complete the one-time v01.12.110 recovery before accepting user writes.

    Running this as a startup event closes the race between candidate selection
    and a user correction. Empty/fresh databases complete immediately; upgraded
    databases may take longer once while OCR reparses safe stale receipts.
    """
    receipt_storage_root = Path(
        os.getenv("RECEIPT_STORAGE_ROOT", "/app/data/receipts/raw")
    )
    raw_limit = str(os.getenv("REZZERV_STALE_RECEIPT_RECOVERY_LIMIT", "1000") or "1000").strip()
    try:
        limit = int(raw_limit)
    except ValueError:
        limit = 1000
    report = run_safe_stale_receipt_recovery(
        engine,
        receipt_storage_root,
        limit=limit,
    )
    print(f"Safe stale receipt recovery startup result: {report}", flush=True)

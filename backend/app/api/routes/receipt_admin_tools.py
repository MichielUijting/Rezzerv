from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/admin/receipts", tags=["admin"])


@router.get("/cleanup-health")
def cleanup_health():
    return {"status": "ok"}

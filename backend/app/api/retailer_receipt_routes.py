"""
Technical Design Reference:
- TD Section: TD-02 Backend API-laag
- Module Role: Household-scoped API for structured digital retailer receipts
- Runtime Type: production
- Used By: API router
- Depends On: retailer receipt import service
- Reads Data: yes
- Writes Data: yes
- Status Authority: no
- Refactor Status: keep
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from app.db import engine
from app.integrations.retailer_receipts import (
    SUPPORTED_RETAILER_PROVIDERS,
    RetailerReceiptEnvelope,
)
from app.services.household_context_adapter import household_context_from_runtime_context
from app.services.retailer_receipt_import_service import import_retailer_receipt

router = APIRouter(prefix="/api/receipts/retailers", tags=["receipts-retailers"])

RECEIPT_STORAGE_ROOT = Path(os.getenv("RECEIPT_STORAGE_ROOT", "/app/data/receipts/raw"))


def _authorized_household_id(authorization: str | None) -> str:
    # Reuse the canonical receipt/household authorization policy.
    from app.main import require_household_context

    runtime_context = require_household_context(authorization)
    household_context = household_context_from_runtime_context(runtime_context)
    return household_context.active_household_id


@router.get("/providers")
def list_retailer_receipt_providers(
    authorization: Optional[str] = Header(None),
):
    _authorized_household_id(authorization)
    return {
        "providers": [
            {
                "code": code,
                "supports_structured_import": True,
                "account_connection": "not_configured",
            }
            for code in SUPPORTED_RETAILER_PROVIDERS
        ],
        "credential_storage": False,
    }


@router.post("/import")
def import_structured_retailer_receipt(
    payload: RetailerReceiptEnvelope,
    authorization: Optional[str] = Header(None),
):
    household_id = _authorized_household_id(authorization)
    try:
        return import_retailer_receipt(
            engine,
            RECEIPT_STORAGE_ROOT,
            household_id=household_id,
            envelope=payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

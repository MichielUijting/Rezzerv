"""Household-scoped API for structured digital retailer receipts."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.db import engine
from app.api.receipt_ah_oauth_proxy_routes import (
    build_ah_oauth_launch_url,
    create_ah_oauth_flow,
)
from app.integrations.retailer_receipts import (
    SUPPORTED_RETAILER_PROVIDERS,
    RetailerReceiptEnvelope,
)
from app.services.ah_receipt_sync_service import (
    connect_ah_account,
    count_pending_ah_receipts,
    disconnect_ah_account,
    sync_ah_receipts,
)
from app.services.household_context_adapter import household_context_from_runtime_context
from app.services.retailer_account_secure_store import ah_session_status
from app.services.retailer_receipt_import_service import import_retailer_receipt

router = APIRouter(prefix="/api/receipts/retailers", tags=["receipts-retailers"])

RECEIPT_STORAGE_ROOT = Path(os.getenv("RECEIPT_STORAGE_ROOT", "/app/data/receipts/raw"))


class AHConnectRequest(BaseModel):
    code_or_redirect: str = Field(min_length=1, max_length=4096)


class AHSyncRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)


def _authorized_household_id(authorization: str | None) -> str:
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
                "account_connection": (
                    "persistent_encrypted" if code == "ah"
                    else "browser_assisted" if code == "lidl"
                    else "not_configured"
                ),
            }
            for code in SUPPORTED_RETAILER_PROVIDERS
        ],
        "credential_storage": True,
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


@router.get("/ah/connect")
def start_ah_account_connection(
    request: Request,
    return_to: str | None = Query(default=None, max_length=2048),
    authorization: Optional[str] = Header(None),
):
    household_id = _authorized_household_id(authorization)
    flow = create_ah_oauth_flow(
        request,
        household_id=household_id,
        return_to=return_to,
    )
    return {
        **ah_session_status(engine, household_id),
        "login_url": build_ah_oauth_launch_url(flow),
        "redirect_uri": "automatic",
        "expires_at": flow.expires_at.isoformat(),
        "instructions": (
            "Open de AH-login en rond de aanmelding af. "
            "Inhuis ontvangt de AH-callback automatisch en slaat de koppeling versleuteld op."
        ),
    }


@router.post("/ah/connect")
def complete_ah_account_connection(
    payload: AHConnectRequest,
    authorization: Optional[str] = Header(None),
):
    household_id = _authorized_household_id(authorization)
    try:
        return connect_ah_account(
            engine,
            household_id=household_id,
            code_or_redirect=payload.code_or_redirect,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Albert Heijn-login kon niet worden voltooid") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/ah/status")
def get_ah_account_status(
    authorization: Optional[str] = Header(None),
):
    household_id = _authorized_household_id(authorization)
    return ah_session_status(engine, household_id)


@router.delete("/ah/connect")
def remove_ah_account_connection(
    authorization: Optional[str] = Header(None),
):
    household_id = _authorized_household_id(authorization)
    return disconnect_ah_account(engine, household_id=household_id)


@router.get("/pending-summary")
def get_retailer_pending_receipt_summary(
    authorization: Optional[str] = Header(None),
):
    household_id = _authorized_household_id(authorization)
    try:
        ah = count_pending_ah_receipts(
            engine,
            household_id=household_id,
            limit=100,
        )
    except (httpx.HTTPError, ValueError):
        status = ah_session_status(engine, household_id)
        ah = {
            "provider": "ah",
            "connected": bool(status.get("connected")),
            "count_available": False,
            "pending_downloads": None,
            "receipts_found": None,
        }

    return {
        "pending_downloads": ah.get("pending_downloads"),
        "count_available": bool(ah.get("count_available")),
        "providers": [ah],
        "coverage": "persistent_retailer_connections",
        "browser_assisted_providers": ["lidl", "jumbo"],
    }


@router.post("/ah/sync")
def sync_ah_account_receipts(
    payload: AHSyncRequest,
    authorization: Optional[str] = Header(None),
):
    household_id = _authorized_household_id(authorization)
    try:
        return sync_ah_receipts(
            engine,
            RECEIPT_STORAGE_ROOT,
            household_id=household_id,
            limit=payload.limit,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Albert Heijn-bonnen konden niet worden opgehaald") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

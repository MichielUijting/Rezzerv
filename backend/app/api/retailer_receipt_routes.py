"""Household-scoped API for structured digital retailer receipts."""

from __future__ import annotations

import os
from pathlib import Path
from datetime import date
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
from app.integrations.picnic_auth_protocol import PicnicAuthClient, PicnicAuthError
from app.integrations.picnic_http_transport import PicnicHttpTransport
from app.integrations.picnic_readonly_probe import PicnicReadOnlyProbe, PicnicReadOnlyContractError
from app.services.picnic_account_secure_store import (
    picnic_status, save_picnic_auth, get_picnic_auth, delete_picnic_auth, reserve_picnic_sms_request,
)

from app.services.retailer_receipt_import_service import import_retailer_receipt
from app.services.lidl_import_window_service import get_window, save_window, complete_import
from app.api.household_profile_routes import _context_and_membership
from app.services.authorization_foundation_service import evaluate_household_permission

router = APIRouter(prefix="/api/receipts/retailers", tags=["receipts-retailers"])

RECEIPT_STORAGE_ROOT = Path(os.getenv("RETAILER_RECEIPT_STORAGE_ROOT", "/app/data/retailer-receipts/raw"))


class LidlImportWindowRequest(BaseModel):
    from_date: date | None = None
    to_date: date | None = None


@router.get("/lidl/import-window")
def get_lidl_import_window():
    with engine.connect() as conn:
        context, membership_id = _context_and_membership(conn)
        decision = evaluate_household_permission(
            conn, household_id=str(context.active_household_id),
            membership_id=membership_id, permission_key="household_settings.manage",
        )
    return {**get_window(engine, str(context.active_household_id)), "can_manage": bool(decision.allowed)}


@router.put("/lidl/import-window")
def update_lidl_import_window(payload: LidlImportWindowRequest):
    with engine.connect() as conn:
        context, membership_id = _context_and_membership(conn)
        decision = evaluate_household_permission(
            conn, household_id=str(context.active_household_id),
            membership_id=membership_id, permission_key="household_settings.manage",
        )
        if not decision.allowed:
            raise HTTPException(status_code=403, detail="Alleen een bevoegde beheerder kan de Lidl-importperiode wijzigen.")
    try:
        return {**save_window(engine, str(context.active_household_id), payload.from_date, payload.to_date), "can_manage": True}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class LidlImportCompleteRequest(BaseModel):
    from_date: date
    to_date: date
    last_imported_date: date | None = None


@router.post("/lidl/complete")
def complete_lidl_import(payload: LidlImportCompleteRequest, authorization: Optional[str] = Header(None)):
    household_id = _authorized_household_id(authorization)
    try:
        return complete_import(
            engine, household_id,
            payload.last_imported_date, payload.from_date, payload.to_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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



class PicnicLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class PicnicSmsRequest(BaseModel):
    code: str = Field(min_length=4, max_length=10)


@router.get("/picnic/status")
def get_picnic_account_status(authorization: Optional[str] = Header(None)):
    household_id = _authorized_household_id(authorization)
    return picnic_status(engine, household_id)


@router.post("/picnic/connect")
def connect_picnic_account(
    payload: PicnicLoginRequest,
    authorization: Optional[str] = Header(None),
):
    household_id = _authorized_household_id(authorization)
    transport = PicnicHttpTransport()
    try:
        result = PicnicAuthClient(transport.send).login(payload.username, payload.password)
        save_picnic_auth(engine, household_id, result.auth_key, pending_2fa=result.requires_2fa)
        return picnic_status(engine, household_id)
    except PicnicAuthError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    finally:
        transport.close()


@router.post("/picnic/request-sms")
def request_picnic_sms(authorization: Optional[str] = Header(None)):
    household_id = _authorized_household_id(authorization)
    try:
        reserved_token = reserve_picnic_sms_request(engine, household_id)
    except ValueError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from None
    transport = PicnicHttpTransport()
    try:
        PicnicAuthClient(transport.send).request_sms(reserved_token)
        return {"verification_required": True, "sms_requested": True}
    except PicnicAuthError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    finally:
        transport.close()


@router.post("/picnic/verify-sms")
def verify_picnic_sms(
    payload: PicnicSmsRequest,
    authorization: Optional[str] = Header(None),
):
    household_id = _authorized_household_id(authorization)
    auth = get_picnic_auth(engine, household_id)
    if not auth or not auth["pending_2fa"]:
        raise HTTPException(status_code=409, detail="Geen Picnic-sms-verificatie actief.")
    transport = PicnicHttpTransport()
    try:
        verified_key = PicnicAuthClient(transport.send).verify_sms(auth["auth_key"], payload.code)
        save_picnic_auth(engine, household_id, verified_key, pending_2fa=False)
        return picnic_status(engine, household_id)
    except PicnicAuthError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    finally:
        transport.close()


@router.delete("/picnic/connect")
def disconnect_picnic_account(authorization: Optional[str] = Header(None)):
    household_id = _authorized_household_id(authorization)
    delete_picnic_auth(engine, household_id)
    return picnic_status(engine, household_id)


@router.get("/picnic/deliveries")
def list_picnic_deliveries(authorization: Optional[str] = Header(None)):
    household_id = _authorized_household_id(authorization)
    auth = get_picnic_auth(engine, household_id)
    if not auth or auth["pending_2fa"]:
        raise HTTPException(status_code=409, detail="Picnic-account is niet geverifieerd.")
    transport = PicnicHttpTransport()
    try:
        probe = PicnicReadOnlyProbe(lambda method, path, data: transport.send(method, path, data, auth["auth_key"])[0])
        delivery_rows = probe.list_deliveries()
        return {
            "provider": "picnic",
            "count": len(delivery_rows),
            "deliveries": delivery_rows,
            "read_only": True,
            "receipt_import_enabled": False,
        }
    except (PicnicAuthError, PicnicReadOnlyContractError):
        raise HTTPException(status_code=502, detail="Picnic-bezorggeschiedenis kon niet veilig worden opgehaald.") from None
    finally:
        transport.close()


@router.get("/picnic/deliveries/{delivery_id}")
def preview_picnic_delivery(delivery_id: str, authorization: Optional[str] = Header(None)):
    household_id = _authorized_household_id(authorization)
    auth = get_picnic_auth(engine, household_id)
    if not auth or auth["pending_2fa"]:
        raise HTTPException(status_code=409, detail="Picnic-account is niet geverifieerd.")
    transport = PicnicHttpTransport()
    try:
        probe = PicnicReadOnlyProbe(lambda method, path, data: transport.send(method, path, data, auth["auth_key"])[0])
        return probe.get_delivery_preview(delivery_id)
    except (PicnicAuthError, PicnicReadOnlyContractError):
        raise HTTPException(status_code=502, detail="Picnic-bezorging kon niet veilig worden opgehaald.") from None
    finally:
        transport.close()


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

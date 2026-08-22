from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.services.household_context_adapter import household_context_from_runtime_context
from app.services.session_request_context import require_platform_permission_from_session
from app.services.support_message_service import (
    RECIPIENT_ALL_ADMINS,
    RECIPIENT_SINGLE_ADMIN,
    RECIPIENT_SUPERUSER,
    SupportMessageError,
    add_support_message,
    add_support_recipient,
    create_support_thread,
    export_support_threads_csv,
    list_support_messages,
    list_support_threads,
    set_support_thread_status,
)

router = APIRouter(tags=["support-messages"])


class HouseholdThreadCreateRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=250)
    message: str = Field(min_length=1, max_length=10000)
    screen_name: str = Field(min_length=1, max_length=200)
    route: str | None = None
    app_version: str | None = None


class PlatformThreadCreateRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=250)
    message: str = Field(min_length=1, max_length=10000)
    household_id: str
    recipient_type: str
    admin_user_ids: list[str] = Field(default_factory=list)
    reply_allowed: bool = True
    screen_name: str = "Superuser Meldingen"
    route: str | None = "/superuser/meldingen"
    app_version: str | None = None


class SupportReplyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)


class SupportStatusRequest(BaseModel):
    status: str


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "items"):
        return dict(value.items())
    return {
        "user_id": getattr(value, "user_id", None),
        "email": getattr(value, "email", None),
        "name": getattr(value, "name", None),
        "role": getattr(value, "role", None),
    }


def _main_module():
    from app import main as main_module
    return main_module


def _household_actor(authorization: str | None) -> dict[str, Any]:
    main_module = _main_module()
    runtime = _mapping(main_module.require_household_context(authorization))
    context = household_context_from_runtime_context(runtime)
    role = str(runtime.get("role") or runtime.get("display_role") or "").strip().lower()
    return {
        "user_id": str(runtime.get("user_id") or runtime.get("email") or ""),
        "name": str(runtime.get("name") or runtime.get("display_name") or runtime.get("email") or "Rezzerv-gebruiker"),
        "role": role or "household.member",
        "household_id": str(context.active_household_id),
    }


def _platform_actor(authorization: str | None, permission_key: str) -> dict[str, Any]:
    context = require_platform_permission_from_session(permission_key, authorization)
    return {
        "user_id": context.user_id,
        "name": context.email or "Platformgebruiker",
        "role": str(context.role or "platform.user"),
    }


def _thread_header(conn, thread_id: str, *, household_id: str | None = None, is_superuser: bool = False):
    row = conn.execute(text("""
        SELECT id, thread_number, household_id, created_by_user_id, created_by_name,
               subject, origin_screen_name, origin_route, origin_app_version,
               status, reply_allowed, recipient_type, created_at, updated_at, closed_at
        FROM support_threads
        WHERE id = :id
        LIMIT 1
    """), {"id": str(thread_id)}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Melding niet gevonden")
    if not is_superuser and str(row["household_id"] or "") != str(household_id or ""):
        raise HTTPException(status_code=404, detail="Melding niet gevonden")
    return dict(row)


def _rows_with_last_sender(conn, rows):
    enriched = []
    for row in rows:
        item = dict(row)
        item["last_sender_user_id"] = conn.execute(text("""
            SELECT sender_user_id
            FROM support_messages
            WHERE thread_id = :thread_id
            ORDER BY created_at DESC, id DESC
            LIMIT 1
        """), {"thread_id": str(item["id"])}).scalar() or ""
        enriched.append(item)
    return enriched


def _delete_thread(conn, thread_id: str) -> None:
    conn.execute(text("DELETE FROM support_recipients WHERE thread_id = :thread_id"), {"thread_id": str(thread_id)})
    conn.execute(text("DELETE FROM support_messages WHERE thread_id = :thread_id"), {"thread_id": str(thread_id)})
    result = conn.execute(text("DELETE FROM support_threads WHERE id = :thread_id"), {"thread_id": str(thread_id)})
    if result.rowcount != 1:
        raise HTTPException(status_code=404, detail="Melding niet gevonden")


def _support_error(exc: SupportMessageError):
    message = str(exc)
    status_code = 404 if "niet gevonden" in message.lower() else 403 if "niet toegestaan" in message.lower() or "behoort niet" in message.lower() else 400
    raise HTTPException(status_code=status_code, detail=message)


@router.post("/api/support/threads", status_code=201)
def create_household_support_thread(payload: HouseholdThreadCreateRequest, authorization: str | None = Header(None)):
    actor = _household_actor(authorization)
    try:
        with _main_module().engine.begin() as conn:
            result = create_support_thread(
                conn,
                created_by_user_id=actor["user_id"],
                created_by_name=actor["name"],
                sender_role=actor["role"],
                subject=payload.subject,
                message_text=payload.message,
                origin_screen_name=payload.screen_name,
                origin_route=payload.route,
                origin_app_version=payload.app_version,
                household_id=actor["household_id"],
                recipient_type=RECIPIENT_SUPERUSER,
                reply_allowed=True,
            )
        return result.__dict__
    except SupportMessageError as exc:
        _support_error(exc)


@router.get("/api/support/threads")
def get_household_support_threads(status: str | None = Query(None), authorization: str | None = Header(None)):
    actor = _household_actor(authorization)
    try:
        with _main_module().engine.begin() as conn:
            rows = list_support_threads(conn, household_id=actor["household_id"], status=status)
            own_rows = [row for row in rows if str(row["created_by_user_id"] or "") == actor["user_id"]]
            return {"items": _rows_with_last_sender(conn, own_rows)}
    except SupportMessageError as exc:
        _support_error(exc)


@router.get("/api/support/threads/{thread_id}")
def get_household_support_thread(thread_id: str, authorization: str | None = Header(None)):
    actor = _household_actor(authorization)
    try:
        with _main_module().engine.begin() as conn:
            header = _thread_header(conn, thread_id, household_id=actor["household_id"])
            if str(header["created_by_user_id"] or "") != actor["user_id"]:
                raise HTTPException(status_code=404, detail="Melding niet gevonden")
            messages = list_support_messages(conn, thread_id=thread_id, household_id=actor["household_id"])
        return {"thread": header, "messages": [dict(row) for row in messages]}
    except SupportMessageError as exc:
        _support_error(exc)


@router.post("/api/support/threads/{thread_id}/messages", status_code=201)
def reply_household_support_thread(thread_id: str, payload: SupportReplyRequest, authorization: str | None = Header(None)):
    actor = _household_actor(authorization)
    try:
        with _main_module().engine.begin() as conn:
            header = _thread_header(conn, thread_id, household_id=actor["household_id"])
            if str(header["created_by_user_id"] or "") != actor["user_id"]:
                raise HTTPException(status_code=404, detail="Melding niet gevonden")
            message_id = add_support_message(
                conn,
                thread_id=thread_id,
                sender_user_id=actor["user_id"],
                sender_name=actor["name"],
                sender_role=actor["role"],
                message_text=payload.message,
                is_superuser=False,
                household_id=actor["household_id"],
            )
        return {"message_id": message_id}
    except SupportMessageError as exc:
        _support_error(exc)


@router.delete("/api/support/threads/{thread_id}")
def delete_household_support_thread(thread_id: str, authorization: str | None = Header(None)):
    actor = _household_actor(authorization)
    with _main_module().engine.begin() as conn:
        header = _thread_header(conn, thread_id, household_id=actor["household_id"])
        if str(header["created_by_user_id"] or "") != actor["user_id"]:
            raise HTTPException(status_code=403, detail="Je mag alleen je eigen melding verwijderen")
        _delete_thread(conn, thread_id)
    return {"thread_id": thread_id, "deleted": True}


@router.get("/api/platform/support/threads")
def get_platform_support_threads(status: str | None = Query(None), household_id: str | None = Query(None), authorization: str | None = Header(None)):
    _platform_actor(authorization, "platform.support_access.read")
    try:
        with _main_module().engine.begin() as conn:
            rows = list_support_threads(conn, household_id=household_id, status=status)
            return {"items": _rows_with_last_sender(conn, rows)}
    except SupportMessageError as exc:
        _support_error(exc)


@router.get("/api/platform/support/threads/{thread_id}")
def get_platform_support_thread(thread_id: str, authorization: str | None = Header(None)):
    _platform_actor(authorization, "platform.support_access.read")
    try:
        with _main_module().engine.begin() as conn:
            header = _thread_header(conn, thread_id, is_superuser=True)
            messages = list_support_messages(conn, thread_id=thread_id, is_superuser=True)
        return {"thread": header, "messages": [dict(row) for row in messages]}
    except SupportMessageError as exc:
        _support_error(exc)


@router.post("/api/platform/support/threads", status_code=201)
def create_platform_support_thread(payload: PlatformThreadCreateRequest, authorization: str | None = Header(None)):
    actor = _platform_actor(authorization, "platform.support_access.mutate")
    if payload.recipient_type not in {RECIPIENT_SINGLE_ADMIN, RECIPIENT_ALL_ADMINS}:
        raise HTTPException(status_code=400, detail="Ontvangertype moet één of alle huishoudadmins zijn")
    recipients = sorted({str(value).strip() for value in payload.admin_user_ids if str(value).strip()})
    if payload.recipient_type == RECIPIENT_SINGLE_ADMIN and len(recipients) != 1:
        raise HTTPException(status_code=400, detail="Selecteer exact één huishoudadmin")
    if payload.recipient_type == RECIPIENT_ALL_ADMINS and not recipients:
        raise HTTPException(status_code=400, detail="Er zijn geen huishoudadmins als ontvanger opgegeven")
    try:
        with _main_module().engine.begin() as conn:
            result = create_support_thread(
                conn,
                created_by_user_id=actor["user_id"],
                created_by_name=actor["name"],
                sender_role=actor["role"],
                subject=payload.subject,
                message_text=payload.message,
                origin_screen_name=payload.screen_name,
                origin_route=payload.route,
                origin_app_version=payload.app_version,
                household_id=payload.household_id,
                recipient_type=payload.recipient_type,
                reply_allowed=payload.reply_allowed,
            )
            for admin_user_id in recipients:
                add_support_recipient(conn, thread_id=result.thread_id, household_id=payload.household_id, admin_user_id=admin_user_id)
        return {**result.__dict__, "recipient_count": len(recipients)}
    except SupportMessageError as exc:
        _support_error(exc)


@router.post("/api/platform/support/threads/{thread_id}/messages", status_code=201)
def reply_platform_support_thread(thread_id: str, payload: SupportReplyRequest, authorization: str | None = Header(None)):
    actor = _platform_actor(authorization, "platform.support_access.mutate")
    try:
        with _main_module().engine.begin() as conn:
            message_id = add_support_message(
                conn,
                thread_id=thread_id,
                sender_user_id=actor["user_id"],
                sender_name=actor["name"],
                sender_role=actor["role"],
                message_text=payload.message,
                is_superuser=True,
            )
        return {"message_id": message_id}
    except SupportMessageError as exc:
        _support_error(exc)


@router.patch("/api/platform/support/threads/{thread_id}/status")
def update_platform_support_thread_status(thread_id: str, payload: SupportStatusRequest, authorization: str | None = Header(None)):
    _platform_actor(authorization, "platform.support_access.mutate")
    try:
        with _main_module().engine.begin() as conn:
            set_support_thread_status(conn, thread_id=thread_id, status=payload.status)
        return {"thread_id": thread_id, "status": payload.status}
    except SupportMessageError as exc:
        _support_error(exc)


@router.delete("/api/platform/support/threads/{thread_id}")
def delete_platform_support_thread(thread_id: str, authorization: str | None = Header(None)):
    _platform_actor(authorization, "platform.support_access.mutate")
    with _main_module().engine.begin() as conn:
        _thread_header(conn, thread_id, is_superuser=True)
        _delete_thread(conn, thread_id)
    return {"thread_id": thread_id, "deleted": True}


@router.get("/api/platform/support/export.csv")
def export_platform_support_threads(status: str | None = Query(None), authorization: str | None = Header(None)):
    _platform_actor(authorization, "platform.support_access.read")
    try:
        with _main_module().engine.begin() as conn:
            csv_text = export_support_threads_csv(conn, status=status)
        return Response(
            content=csv_text,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=rezzerv-meldingen.csv"},
        )
    except SupportMessageError as exc:
        _support_error(exc)

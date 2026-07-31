from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.services.authorization_foundation_service import (
    ensure_authorization_foundation,
    is_frontteam_member,
    set_frontteam_membership,
    write_authorization_audit,
)
from app.services.frontteam_support_scope_service import (
    assert_support_household_allowed,
    resolve_support_household_scope,
)
from app.services.household_context_adapter import household_context_from_runtime_context
from app.services.platform_actor_service import (
    PlatformActor,
    SUPERGEBRUIKER_EMAIL,
    resolve_platform_actor,
)
from app.services.support_message_service import (
    RECIPIENT_ALL_ADMINS,
    RECIPIENT_SINGLE_ADMIN,
    RECIPIENT_SUPERUSER,
    SupportMessageError,
    add_support_message,
    add_support_recipient,
    create_support_thread,
    list_support_messages,
    list_support_threads,
    set_support_thread_status,
)

router = APIRouter(tags=["meldingen-en-autorisatie"])


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
    screen_name: str = "Supergebruiker Meldingen"
    route: str | None = "/supergebruiker/meldingen"
    app_version: str | None = None


class SupportReplyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)


class SupportStatusRequest(BaseModel):
    status: str


class FrontteamRequest(BaseModel):
    frontteam: bool


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


def _household_actor(authorization: str | None, requested_household_id: str | None = None) -> dict[str, Any]:
    main_module = _main_module()
    runtime = _mapping(main_module.require_household_context(authorization))
    context = household_context_from_runtime_context(runtime)
    email = str(runtime.get("email") or runtime.get("user_id") or "").strip().lower()
    household_id = str(requested_household_id or context.active_household_id or "").strip()
    if not email or not household_id:
        raise HTTPException(status_code=403, detail="Actief huishouden ontbreekt")

    with main_module.engine.begin() as conn:
        membership = conn.execute(text("""
            SELECT role
            FROM household_memberships
            WHERE household_id = :household_id
              AND lower(user_email) = :email
            LIMIT 1
        """), {"household_id": household_id, "email": email}).mappings().first()

    if not membership:
        raise HTTPException(status_code=403, detail="Geen lidmaatschap van het actieve huishouden")
    persisted_role = str(membership.get("role") or "").strip().lower()
    role_mapping = {
        "owner": "Eigenaar", "eigenaar": "Eigenaar", "admin": "Eigenaar",
        "member": "Lid", "lid": "Lid",
        "viewer": "Kijker", "kijker": "Kijker",
    }
    nederlandse_rol = role_mapping.get(persisted_role)
    if nederlandse_rol not in {"Eigenaar", "Lid"}:
        raise HTTPException(status_code=403, detail="Alleen een Eigenaar of Lid kan meldingen sturen en beantwoorden")

    return {
        "user_id": str(runtime.get("user_id") or email),
        "email": email,
        "name": str(runtime.get("name") or runtime.get("display_name") or email),
        "role": nederlandse_rol,
        "household_id": household_id,
    }


def _platform_actor(authorization: str | None, permission_key: str) -> PlatformActor:
    main_module = _main_module()
    runtime_user = _mapping(main_module.get_current_user_from_authorization(authorization))
    with main_module.engine.begin() as conn:
        return resolve_platform_actor(conn, runtime_user=runtime_user, permission_key=permission_key)


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


def _list_household_threads(conn, *, household_id: str, status: str | None = None):
    params: dict[str, Any] = {"household_id": str(household_id)}
    status_clause = ""
    if status:
        params["status"] = status
        status_clause = " AND t.status = :status"
    return conn.execute(text(f"""
        SELECT
            t.id, t.thread_number, t.household_id, t.created_by_user_id,
            t.created_by_name, t.subject, t.origin_screen_name, t.origin_route,
            t.origin_app_version, t.status, t.reply_allowed, t.recipient_type,
            t.created_at, t.updated_at, t.closed_at,
            COUNT(m.id) AS message_count,
            MAX(m.created_at) AS last_message_at
        FROM support_threads t
        LEFT JOIN support_messages m ON m.thread_id = t.id
        WHERE t.household_id = :household_id
          {status_clause}
        GROUP BY t.id
        ORDER BY t.updated_at DESC, t.thread_number DESC
    """), params).mappings().all()


def _platform_threads(conn, *, actor: PlatformActor, household_id: str | None, status: str | None):
    scope = resolve_support_household_scope(conn, actor=actor)
    if scope.unrestricted:
        return list_support_threads(conn, household_id=household_id, status=status)
    if household_id:
        assert_support_household_allowed(conn, actor=actor, household_id=household_id)
        return list_support_threads(conn, household_id=household_id, status=status)

    rows = []
    for allowed_household_id in scope.household_ids:
        rows.extend(list_support_threads(conn, household_id=allowed_household_id, status=status))
    return sorted(
        rows,
        key=lambda row: (str(row["updated_at"] or ""), str(row["thread_number"] or "")),
        reverse=True,
    )


def _platform_thread_header(conn, *, actor: PlatformActor, thread_id: str) -> dict[str, Any]:
    header = _thread_header(conn, thread_id, is_superuser=True)
    assert_support_household_allowed(conn, actor=actor, household_id=header.get("household_id"))
    return header


def _platform_export_csv(conn, *, actor: PlatformActor, status: str | None) -> str:
    rows = _platform_threads(conn, actor=actor, household_id=None, status=status)
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow([
        "Meldingsnummer", "Status", "Onderwerp", "Huishouden", "Naam Admin",
        "Scherm", "Route", "Applicatieversie", "Aangemaakt op", "Laatst gewijzigd",
        "Aantal berichten", "Reageren toegestaan", "Gesloten op",
    ])
    for row in rows:
        writer.writerow([
            row["thread_number"], row["status"], row["subject"], row["household_id"] or "",
            row["created_by_name"], row["origin_screen_name"], row["origin_route"] or "",
            row["origin_app_version"] or "", row["created_at"], row["updated_at"],
            row["message_count"], "Ja" if row["reply_allowed"] else "Nee", row["closed_at"] or "",
        ])
    return output.getvalue()


def _support_error(exc: SupportMessageError):
    message = str(exc)
    status_code = 404 if "niet gevonden" in message.lower() else 403 if "niet toegestaan" in message.lower() or "behoort niet" in message.lower() else 400
    raise HTTPException(status_code=status_code, detail=message)


def _household_header(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


@router.post("/api/support/threads", status_code=201)
def create_household_support_thread(payload: HouseholdThreadCreateRequest, authorization: str | None = Header(None), x_rezzerv_household_id: str | None = Header(None, alias="X-Rezzerv-Household-ID")):
    actor = _household_actor(authorization, _household_header(x_rezzerv_household_id))
    try:
        with _main_module().engine.begin() as conn:
            result = create_support_thread(
                conn,
                created_by_user_id=actor["email"], created_by_name=actor["name"], sender_role=actor["role"],
                subject=payload.subject, message_text=payload.message, origin_screen_name=payload.screen_name,
                origin_route=payload.route, origin_app_version=payload.app_version,
                household_id=actor["household_id"], recipient_type=RECIPIENT_SUPERUSER, reply_allowed=True,
            )
        return result.__dict__
    except SupportMessageError as exc:
        _support_error(exc)


@router.get("/api/support/threads")
def get_household_support_threads(status: str | None = Query(None), authorization: str | None = Header(None), x_rezzerv_household_id: str | None = Header(None, alias="X-Rezzerv-Household-ID")):
    actor = _household_actor(authorization, _household_header(x_rezzerv_household_id))
    with _main_module().engine.begin() as conn:
        rows = _list_household_threads(conn, household_id=actor["household_id"], status=status)
    return {"items": [dict(row) for row in rows]}


@router.get("/api/support/threads/{thread_id}")
def get_household_support_thread(thread_id: str, authorization: str | None = Header(None), x_rezzerv_household_id: str | None = Header(None, alias="X-Rezzerv-Household-ID")):
    actor = _household_actor(authorization, _household_header(x_rezzerv_household_id))
    with _main_module().engine.begin() as conn:
        header = _thread_header(conn, thread_id, household_id=actor["household_id"])
        messages = list_support_messages(conn, thread_id=thread_id, household_id=actor["household_id"])
    return {"thread": header, "messages": [dict(row) for row in messages]}


@router.post("/api/support/threads/{thread_id}/messages", status_code=201)
def reply_household_support_thread(thread_id: str, payload: SupportReplyRequest, authorization: str | None = Header(None), x_rezzerv_household_id: str | None = Header(None, alias="X-Rezzerv-Household-ID")):
    actor = _household_actor(authorization, _household_header(x_rezzerv_household_id))
    try:
        with _main_module().engine.begin() as conn:
            _thread_header(conn, thread_id, household_id=actor["household_id"])
            message_id = add_support_message(conn, thread_id=thread_id, sender_user_id=actor["email"], sender_name=actor["name"], sender_role=actor["role"], message_text=payload.message, is_superuser=False, household_id=actor["household_id"])
        return {"message_id": message_id}
    except SupportMessageError as exc:
        _support_error(exc)


@router.patch("/api/support/threads/{thread_id}/status")
def update_household_support_thread_status(thread_id: str, payload: SupportStatusRequest, authorization: str | None = Header(None), x_rezzerv_household_id: str | None = Header(None, alias="X-Rezzerv-Household-ID")):
    actor = _household_actor(authorization, _household_header(x_rezzerv_household_id))
    try:
        with _main_module().engine.begin() as conn:
            _thread_header(conn, thread_id, household_id=actor["household_id"])
            set_support_thread_status(conn, thread_id=thread_id, status=payload.status)
        return {"thread_id": thread_id, "status": payload.status}
    except SupportMessageError as exc:
        _support_error(exc)


@router.get("/api/platform/support/threads")
def get_platform_support_threads(status: str | None = Query(None), household_id: str | None = Query(None), authorization: str | None = Header(None)):
    actor = _platform_actor(authorization, "platform.support_access.read")
    with _main_module().engine.begin() as conn:
        rows = _platform_threads(conn, actor=actor, household_id=household_id, status=status)
    return {"items": [dict(row) for row in rows]}


@router.get("/api/platform/support/threads/{thread_id}")
def get_platform_support_thread(thread_id: str, authorization: str | None = Header(None)):
    actor = _platform_actor(authorization, "platform.support_access.read")
    with _main_module().engine.begin() as conn:
        header = _platform_thread_header(conn, actor=actor, thread_id=thread_id)
        messages = list_support_messages(conn, thread_id=thread_id, is_superuser=True)
    return {"thread": header, "messages": [dict(row) for row in messages]}


@router.post("/api/platform/support/threads", status_code=201)
def create_platform_support_thread(payload: PlatformThreadCreateRequest, authorization: str | None = Header(None)):
    actor = _platform_actor(authorization, "platform.support_access.mutate")
    if payload.recipient_type not in {RECIPIENT_SINGLE_ADMIN, RECIPIENT_ALL_ADMINS}:
        raise HTTPException(status_code=400, detail="Ontvangertype moet één of alle Eigenaars zijn")
    recipients = sorted({str(value).strip().lower() for value in payload.admin_user_ids if str(value).strip()})
    if payload.recipient_type == RECIPIENT_SINGLE_ADMIN and len(recipients) != 1:
        raise HTTPException(status_code=400, detail="Selecteer exact één Eigenaar")
    if payload.recipient_type == RECIPIENT_ALL_ADMINS and not recipients:
        raise HTTPException(status_code=400, detail="Er zijn geen Eigenaars als ontvanger opgegeven")
    try:
        with _main_module().engine.begin() as conn:
            assert_support_household_allowed(conn, actor=actor, household_id=payload.household_id)
            result = create_support_thread(conn, created_by_user_id=actor.user_id, created_by_name=actor.name, sender_role=actor.role, subject=payload.subject, message_text=payload.message, origin_screen_name=payload.screen_name, origin_route=payload.route, origin_app_version=payload.app_version, household_id=payload.household_id, recipient_type=payload.recipient_type, reply_allowed=payload.reply_allowed)
            for user_id in recipients:
                add_support_recipient(conn, thread_id=result.thread_id, household_id=payload.household_id, admin_user_id=user_id)
        return {**result.__dict__, "recipient_count": len(recipients)}
    except SupportMessageError as exc:
        _support_error(exc)


@router.post("/api/platform/support/threads/{thread_id}/messages", status_code=201)
def reply_platform_support_thread(thread_id: str, payload: SupportReplyRequest, authorization: str | None = Header(None)):
    actor = _platform_actor(authorization, "platform.support_access.mutate")
    try:
        with _main_module().engine.begin() as conn:
            _platform_thread_header(conn, actor=actor, thread_id=thread_id)
            message_id = add_support_message(conn, thread_id=thread_id, sender_user_id=actor.user_id, sender_name=actor.name, sender_role=actor.role, message_text=payload.message, is_superuser=True)
        return {"message_id": message_id}
    except SupportMessageError as exc:
        _support_error(exc)


@router.patch("/api/platform/support/threads/{thread_id}/status")
def update_platform_support_thread_status(thread_id: str, payload: SupportStatusRequest, authorization: str | None = Header(None)):
    actor = _platform_actor(authorization, "platform.support_access.mutate")
    try:
        with _main_module().engine.begin() as conn:
            _platform_thread_header(conn, actor=actor, thread_id=thread_id)
            set_support_thread_status(conn, thread_id=thread_id, status=payload.status)
        return {"thread_id": thread_id, "status": payload.status}
    except SupportMessageError as exc:
        _support_error(exc)


@router.get("/api/platform/support/export.csv")
def export_platform_support_threads(status: str | None = Query(None), authorization: str | None = Header(None)):
    actor = _platform_actor(authorization, "platform.support_access.read")
    with _main_module().engine.begin() as conn:
        csv_text = _platform_export_csv(conn, actor=actor, status=status)
    return Response(content=csv_text, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=rezzerv-meldingen.csv"})


@router.get("/api/platform/gebruikers")
def list_rezzerv_users(authorization: str | None = Header(None)):
    _platform_actor(authorization, "platform.users.view")
    with _main_module().engine.begin() as conn:
        ensure_authorization_foundation(conn)
        rows = conn.execute(text("""
            SELECT lower(hm.user_email) AS gebruiker,
                   GROUP_CONCAT(DISTINCT hm.household_id) AS huishoudens,
                   GROUP_CONCAT(DISTINCT CASE
                       WHEN lower(hm.role) IN ('owner', 'eigenaar', 'admin') THEN 'Eigenaar'
                       WHEN lower(hm.role) IN ('viewer', 'kijker') THEN 'Kijker'
                       ELSE 'Lid'
                   END) AS huishoudrollen
            FROM household_memberships hm
            GROUP BY lower(hm.user_email)
            ORDER BY lower(hm.user_email)
        """)).mappings().all()
        items = []
        for row in rows:
            user_id = str(row["gebruiker"])
            items.append({
                "gebruiker": user_id,
                "huishoudens": str(row["huishoudens"] or "").split(",") if row["huishoudens"] else [],
                "huishoudrollen": str(row["huishoudrollen"] or "").split(",") if row["huishoudrollen"] else [],
                "frontteam": is_frontteam_member(conn, user_id=user_id),
                "supergebruiker": user_id == SUPERGEBRUIKER_EMAIL,
            })
    return {"items": items}


@router.put("/api/platform/gebruikers/{user_id}/frontteam")
def update_frontteam(user_id: str, payload: FrontteamRequest, authorization: str | None = Header(None)):
    actor = _platform_actor(authorization, "platform.frontteam.manage")
    normalized = str(user_id or "").strip().lower()
    if not normalized:
        raise HTTPException(status_code=400, detail="Gebruiker ontbreekt")
    if normalized == SUPERGEBRUIKER_EMAIL and not payload.frontteam:
        raise HTTPException(status_code=400, detail="De Supergebruiker blijft altijd lid van Frontteam")
    with _main_module().engine.begin() as conn:
        previous = is_frontteam_member(conn, user_id=normalized)
        set_frontteam_membership(conn, user_id=normalized, active=payload.frontteam)
        write_authorization_audit(conn, actor_user_id=actor.user_id, actor_type="Supergebruiker", action="Frontteam gewijzigd", object_type="Rezzerv-gebruiker", object_id=normalized, old_value={"Frontteam": previous}, new_value={"Frontteam": payload.frontteam})
    return {"gebruiker": normalized, "frontteam": payload.frontteam}

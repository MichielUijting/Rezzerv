from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import inspect, text

from app.services.authorization_foundation_service import evaluate_platform_permission
from app.services.support_message_service import (
    RECIPIENT_SINGLE_ADMIN,
    SupportMessageError,
    add_support_recipient,
    create_support_thread,
)

router = APIRouter(tags=["support-broadcasts"])


class PlatformBroadcastRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=250)
    message: str = Field(min_length=1, max_length=10000)
    reply_allowed: bool = True
    app_version: str | None = None


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


def _platform_actor(authorization: str | None) -> dict[str, str]:
    main_module = _main_module()
    actor = _mapping(main_module.require_platform_admin_user(authorization))
    user_id = str(actor.get("user_id") or actor.get("id") or actor.get("email") or "").strip()
    email = str(actor.get("email") or "").strip().lower()
    if not user_id:
        raise HTTPException(status_code=403, detail="Platformgebruiker heeft geen bruikbaar gebruikers-ID")
    with main_module.engine.begin() as conn:
        decision = evaluate_platform_permission(
            conn,
            user_id=user_id,
            permission_key="platform.support_access.mutate",
        )
    if not decision.allowed:
        raise HTTPException(status_code=403, detail="Alleen de superuser mag een melding aan alle leden sturen")
    return {
        "user_id": user_id,
        "email": email,
        "name": str(actor.get("name") or actor.get("display_name") or actor.get("email") or "Platform-superuser"),
        "role": str(actor.get("role") or "platform.superuser"),
    }


def _first(columns: set[str], candidates: tuple[str, ...]) -> str | None:
    return next((candidate for candidate in candidates if candidate in columns), None)


def _resolve_app_user_id(conn, *, email: str) -> str:
    inspector = inspect(conn)
    if "app_users" not in inspector.get_table_names():
        return email
    columns = {str(column["name"]) for column in inspector.get_columns("app_users")}
    id_column = _first(columns, ("id", "user_id"))
    email_column = _first(columns, ("email", "user_email"))
    if not id_column or not email_column:
        return email
    row = conn.execute(
        text(f"SELECT {id_column} AS user_id FROM app_users WHERE LOWER({email_column}) = :email LIMIT 1"),
        {"email": email.lower()},
    ).mappings().first()
    return str(row["user_id"]) if row and row.get("user_id") is not None else email


def _active_member_targets(conn, *, actor_user_id: str, actor_email: str) -> list[tuple[str, str, str]]:
    inspector = inspect(conn)
    if "household_memberships" not in inspector.get_table_names():
        return []
    columns = {str(column["name"]) for column in inspector.get_columns("household_memberships")}
    user_column = _first(columns, ("user_id", "member_user_id", "user_email", "email"))
    household_column = _first(columns, ("household_id", "huishouden_id"))
    active_column = _first(columns, ("active", "is_active"))
    status_column = _first(columns, ("status", "membership_status"))
    if not user_column or not household_column:
        return []

    rows = conn.execute(text("SELECT * FROM household_memberships")).mappings().all()
    targets: set[tuple[str, str, str]] = set()
    for row in rows:
        raw_user = str(row.get(user_column) or "").strip()
        household_id = str(row.get(household_column) or "").strip()
        if not raw_user or not household_id or household_id == "0":
            continue
        if active_column and not bool(row.get(active_column)):
            continue
        if status_column and str(row.get(status_column) or "active").strip().lower() not in {
            "active", "actief", "accepted", "geaccepteerd",
        }:
            continue

        if "email" in user_column:
            email = raw_user.lower()
            user_id = _resolve_app_user_id(conn, email=email)
        else:
            user_id = raw_user
            email = ""

        if user_id == actor_user_id or (actor_email and email == actor_email):
            continue
        targets.add((user_id, household_id, email or user_id))

    return sorted(targets, key=lambda item: (item[1], item[2]))


@router.post("/api/platform/support/broadcast", status_code=201)
def create_platform_support_broadcast(
    payload: PlatformBroadcastRequest,
    authorization: str | None = Header(None),
):
    actor = _platform_actor(authorization)
    main_module = _main_module()
    created_threads: list[str] = []
    try:
        with main_module.engine.begin() as conn:
            targets = _active_member_targets(
                conn,
                actor_user_id=actor["user_id"],
                actor_email=actor["email"],
            )
            if not targets:
                raise HTTPException(status_code=409, detail="Er zijn geen actieve leden als ontvanger gevonden")

            for target_user_id, household_id, target_name in targets:
                result = create_support_thread(
                    conn,
                    created_by_user_id=target_user_id,
                    created_by_name=target_name,
                    sender_role=actor["role"],
                    subject=payload.subject,
                    message_text=payload.message,
                    origin_screen_name="Superuser / Meldingen",
                    origin_route="/superuser/meldingen",
                    origin_app_version=payload.app_version,
                    household_id=household_id,
                    recipient_type=RECIPIENT_SINGLE_ADMIN,
                    reply_allowed=payload.reply_allowed,
                )
                conn.execute(text("""
                    UPDATE support_messages
                    SET sender_user_id = :sender_user_id,
                        sender_name = :sender_name,
                        sender_role = :sender_role
                    WHERE thread_id = :thread_id
                """), {
                    "sender_user_id": actor["user_id"],
                    "sender_name": actor["name"],
                    "sender_role": actor["role"],
                    "thread_id": result.thread_id,
                })
                add_support_recipient(
                    conn,
                    thread_id=result.thread_id,
                    household_id=household_id,
                    admin_user_id=target_user_id,
                )
                created_threads.append(result.thread_id)

        return {
            "recipient_count": len(created_threads),
            "thread_ids": created_threads,
            "status": "Open",
        }
    except SupportMessageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

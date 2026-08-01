"""Cookie-based authentication endpoints for the server-side session model.

The router is deliberately isolated from the legacy Authorization-token paths.
It can be mounted by the application entrypoint once the legacy login route is
removed, preventing two competing `/api/auth/login` implementations.
"""

from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.services.server_session_service import (
    DEFAULT_SESSION_TTL,
    SESSION_COOKIE_NAME,
    create_server_session,
    public_session_payload,
    resolve_server_session,
    revoke_server_session,
)


class SessionLoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if not normalized or "@" not in normalized:
            raise ValueError("Geldig e-mailadres is verplicht")
        return normalized


class SessionApiConfiguration(BaseModel):
    cookie_secure: bool = True
    cookie_samesite: str = "lax"
    cookie_path: str = "/"

    @field_validator("cookie_samesite")
    @classmethod
    def validate_samesite(cls, value: str) -> str:
        normalized = str(value or "lax").strip().lower()
        if normalized not in {"lax", "strict"}:
            raise ValueError("SameSite moet lax of strict zijn")
        return normalized


def session_api_configuration_from_environment() -> SessionApiConfiguration:
    environment = str(os.getenv("REZZERV_ENV", "production") or "production").strip().lower()
    explicit_secure = os.getenv("REZZERV_SESSION_COOKIE_SECURE")
    if explicit_secure is None:
        cookie_secure = environment not in {"local", "development", "test"}
    else:
        cookie_secure = explicit_secure.strip().lower() in {"1", "true", "yes", "on"}
    return SessionApiConfiguration(
        cookie_secure=cookie_secure,
        cookie_samesite=str(os.getenv("REZZERV_SESSION_COOKIE_SAMESITE", "lax") or "lax"),
    )


def _set_session_cookie(response: Response, raw_session_id: str, configuration: SessionApiConfiguration) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_session_id,
        max_age=int(DEFAULT_SESSION_TTL.total_seconds()),
        httponly=True,
        secure=configuration.cookie_secure,
        samesite=configuration.cookie_samesite,
        path=configuration.cookie_path,
    )


def _clear_session_cookie(response: Response, configuration: SessionApiConfiguration) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=configuration.cookie_secure,
        samesite=configuration.cookie_samesite,
        path=configuration.cookie_path,
    )


def _verify_password(stored_password: Any, supplied_password: str) -> bool:
    """Compatibility verifier for the current Rezzerv user registry.

    Current `app_users.password` values are plaintext compatibility data. The
    comparison is constant-time. Password hashing remains a separate security
    migration and is not silently mixed into this session tranche.
    """

    stored = str(stored_password or "")
    supplied = str(supplied_password or "")
    return bool(stored) and hmac.compare_digest(stored, supplied)


def _resolve_login_identity(conn, email: str, password: str) -> dict[str, str]:
    rows = conn.execute(
        text(
            """
            SELECT
                u.id AS user_id,
                u.email,
                u.password,
                hm.household_id,
                hm.role
            FROM app_users u
            JOIN household_memberships hm ON hm.user_id = u.id
            WHERE lower(trim(u.email)) = :email
            ORDER BY
                CASE WHEN lower(trim(hm.role)) = 'owner' THEN 0 ELSE 1 END,
                hm.household_id ASC
            """
        ),
        {"email": email},
    ).mappings().all()

    if not rows:
        raise HTTPException(status_code=401, detail="Ongeldige inloggegevens")
    first = rows[0]
    if not _verify_password(first.get("password"), password):
        raise HTTPException(status_code=401, detail="Ongeldige inloggegevens")

    household_id = str(first.get("household_id") or "").strip()
    if not household_id or household_id == "0":
        raise HTTPException(status_code=403, detail="Geen geldig actief huishouden beschikbaar")

    return {
        "user_id": str(first.get("user_id") or ""),
        "email": str(first.get("email") or ""),
        "active_household_id": household_id,
        "role": str(first.get("role") or "").strip().lower(),
    }


def create_server_session_router(
    engine: Engine,
    configuration: SessionApiConfiguration | None = None,
) -> APIRouter:
    configuration = configuration or session_api_configuration_from_environment()
    router = APIRouter()

    @router.post("/api/auth/login")
    def login(payload: SessionLoginRequest, response: Response):
        with engine.begin() as conn:
            identity = _resolve_login_identity(conn, payload.email, payload.password)
            raw_session_id, context = create_server_session(
                conn,
                user_id=identity["user_id"],
                active_household_id=identity["active_household_id"],
                replace_existing=True,
            )
        _set_session_cookie(response, raw_session_id, configuration)
        return public_session_payload(context)

    @router.get("/api/session")
    def get_session(request: Request):
        raw_session_id = request.cookies.get(SESSION_COOKIE_NAME)
        with engine.begin() as conn:
            context = resolve_server_session(conn, raw_session_id)
        return public_session_payload(context)

    @router.post("/api/auth/logout", status_code=204)
    def logout(request: Request, response: Response):
        raw_session_id = request.cookies.get(SESSION_COOKIE_NAME)
        with engine.begin() as conn:
            revoke_server_session(conn, raw_session_id)
        _clear_session_cookie(response, configuration)
        response.status_code = 204
        return response

    return router

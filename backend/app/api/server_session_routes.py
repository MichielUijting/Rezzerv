"""Cookie-based authentication endpoints for the server-side session model."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, field_validator
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.services.consumer_account_provisioning import (
    ConsumerAccountExistsError,
    provision_new_consumer_account,
)
from app.services.password_service import verify_password
from app.services.server_session_service import (
    DEFAULT_SESSION_TTL,
    SESSION_COOKIE_NAME,
    create_none_server_session,
    create_server_session,
    create_system_server_session,
    membership_active_condition,
    membership_id_expression,
    membership_user_join_condition,
    public_session_payload,
    resolve_server_session,
    revoke_server_session,
)
from app.services.authorization_foundation_service import (
    resolve_active_platform_role_keys,
)
from app.services.authorization_membership_service import (
    canonical_role_to_runtime_role,
    resolve_effective_household_role,
)
from app.services.frontteam_household_provisioning import (
    FRONTTEAM_HOUSEHOLD_ID,
    FRONTTEAM_PLATFORM_ROLE,
    ensure_frontteam_household_for_session_runtime,
)
from app.services.system_superuser_session_provisioning import (
    SUPERGEBRUIKER_EMAIL,
    SUPERGEBRUIKER_HUISHOUDEN_ID,
)

REGRESSION_TEST_ADMIN_EMAIL = "test-admin@rezzerv.local"
SYSTEM_PLATFORM_ROLES = frozenset({"platform.superuser", "platform.ip_owner"})


def _normalize_email(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized or "@" not in normalized:
        raise ValueError("Geldig e-mailadres is verplicht")
    return normalized


class SessionLoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _normalize_email(value)


class SessionRegisterRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _normalize_email(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        supplied = str(value or "")
        if len(supplied) < 10:
            raise ValueError("Wachtwoord moet minimaal 10 tekens bevatten")
        if len(supplied) > 256:
            raise ValueError("Wachtwoord mag maximaal 256 tekens bevatten")
        return supplied


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


def _test_household_zero_enabled() -> bool:
    return str(
        os.getenv("REZZERV_PROVISION_TEST_HOUSEHOLD_ZERO", "false") or "false"
    ).strip().lower() in {"1", "true", "yes", "on"}


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


def _resolve_login_identity(conn, email: str, password: str) -> dict[str, Any]:
    user_columns = {
        str(column.get("name") or "")
        for column in inspect(conn).get_columns("app_users")
    }
    password_hash_expression = (
        "password_hash" if "password_hash" in user_columns else "NULL"
    )
    accounts = conn.execute(text(f"""
        SELECT id AS user_id, email, password,
               {password_hash_expression} AS password_hash
        FROM app_users
        WHERE lower(trim(email)) = :email
        LIMIT 2
    """), {"email": email}).mappings().all()
    if len(accounts) != 1:
        raise HTTPException(status_code=401, detail="Ongeldige inloggegevens")
    account = accounts[0]
    if not verify_password(
        account.get("password"),
        password,
        stored_password_hash=account.get("password_hash"),
    ):
        raise HTTPException(status_code=401, detail="Ongeldige inloggegevens")

    # Keep the dedicated Frontteam household projection idempotently in sync.
    # This never grants the platform role; it only projects roles that are
    # already active in the server-side authorization registry.
    ensure_frontteam_household_for_session_runtime(conn)

    user_id = str(account.get("user_id") or "")
    resolved_email = str(account.get("email") or "").strip().lower()
    platform_roles = resolve_active_platform_role_keys(conn, user_id)
    system_roles = frozenset(platform_roles & SYSTEM_PLATFORM_ROLES)
    is_platform_admin = "platform.platform_admin" in platform_roles
    is_frontteam = FRONTTEAM_PLATFORM_ROLE in platform_roles

    # The historical e-mail address identifies the reserved Superuser account,
    # but only the active server-side role grants its system context.
    if (
        resolved_email == SUPERGEBRUIKER_EMAIL
        and "platform.superuser" not in platform_roles
    ):
        raise HTTPException(
            status_code=403,
            detail="Geen geldige accountcontext beschikbaar.",
        )
    if system_roles and is_frontteam:
        raise HTTPException(
            status_code=403,
            detail="Geen geldige accountcontext beschikbaar.",
        )
    if is_platform_admin and (system_roles or is_frontteam):
        raise HTTPException(
            status_code=403,
            detail="Geen geldige accountcontext beschikbaar.",
        )
    if system_roles:
        return {
            "user_id": user_id,
            "email": str(account.get("email") or ""),
            "active_household_id": SUPERGEBRUIKER_HUISHOUDEN_ID,
            "role": "owner",
            "platform_system_context": True,
        }

    join_condition = membership_user_join_condition(conn)
    active_condition = membership_active_condition(conn)
    membership_id_sql = membership_id_expression(conn)

    if is_frontteam:
        frontteam_membership = conn.execute(
            text(
                f"""
                SELECT
                    u.id AS user_id,
                    u.email,
                    {membership_id_sql} AS membership_id,
                    hm.household_id,
                    hm.role
                FROM app_users u
                JOIN household_memberships hm ON {join_condition}
                WHERE u.id = :user_id
                  AND hm.household_id = :household_id
                  AND {active_condition}
                LIMIT 1
                """
            ),
            {"user_id": user_id, "household_id": FRONTTEAM_HOUSEHOLD_ID},
        ).mappings().first()
        if not frontteam_membership:
            raise HTTPException(
                status_code=403,
                detail="Geen geldige accountcontext beschikbaar.",
            )
        role_key = resolve_effective_household_role(
            conn,
            household_id=FRONTTEAM_HOUSEHOLD_ID,
            membership_id=str(frontteam_membership.get("membership_id") or ""),
            legacy_role=frontteam_membership.get("role"),
        )
        runtime_role = canonical_role_to_runtime_role(role_key or "")
        if runtime_role != "admin":
            raise HTTPException(
                status_code=403,
                detail="Geen geldige accountcontext beschikbaar.",
            )
        return {
            "user_id": user_id,
            "email": str(account.get("email") or ""),
            "active_household_id": FRONTTEAM_HOUSEHOLD_ID,
            "role": "admin",
            "platform_system_context": False,
        }

    if is_platform_admin:
        return {
            "user_id": user_id,
            "email": str(account.get("email") or ""),
            "active_household_id": None,
            "role": None,
            "platform_system_context": False,
        }

    rows = conn.execute(
        text(
            f"""
            SELECT
                u.id AS user_id,
                u.email,
                {membership_id_sql} AS membership_id,
                hm.household_id,
                hm.role
            FROM app_users u
            JOIN household_memberships hm ON {join_condition}
            WHERE u.id = :user_id
              AND hm.household_id <> :frontteam_household_id
              AND {active_condition}
            ORDER BY hm.household_id ASC
            """
        ),
        {"user_id": user_id, "frontteam_household_id": FRONTTEAM_HOUSEHOLD_ID},
    ).mappings().all()
    resolved_rows = []
    for row in rows:
        role_key = resolve_effective_household_role(
            conn,
            household_id=str(row.get("household_id") or ""),
            membership_id=str(row.get("membership_id") or ""),
            legacy_role=row.get("role"),
        )
        runtime_role = canonical_role_to_runtime_role(role_key or "")
        if runtime_role:
            resolved_rows.append({**dict(row), "effective_role": runtime_role})
    if not resolved_rows:
        raise HTTPException(
            status_code=403,
            detail="Geen geldige accountcontext beschikbaar.",
        )
    resolved_rows.sort(
        key=lambda row: (
            0 if row["effective_role"] in {"admin", "owner"} else 1,
            str(row.get("household_id") or ""),
        )
    )
    first = resolved_rows[0]
    household_id = str(first.get("household_id") or "").strip()
    resolved_email = str(first.get("email") or "").strip().lower()
    role = str(first.get("effective_role") or "").strip().lower()
    if not household_id:
        raise HTTPException(
            status_code=403,
            detail="Geen geldige accountcontext beschikbaar.",
        )

    is_regression_test_admin = (
        _test_household_zero_enabled()
        and resolved_email == REGRESSION_TEST_ADMIN_EMAIL
        and role == "owner"
    )
    if (
        household_id == SUPERGEBRUIKER_HUISHOUDEN_ID
        and not is_regression_test_admin
    ):
        raise HTTPException(
            status_code=403,
            detail="Geen geldige accountcontext beschikbaar.",
        )

    return {
        "user_id": str(first.get("user_id") or ""),
        "email": str(first.get("email") or ""),
        "active_household_id": household_id,
        "role": role,
        "platform_system_context": False,
    }


def create_server_session_router(
    engine: Engine,
    configuration: SessionApiConfiguration | None = None,
) -> APIRouter:
    configuration = configuration or session_api_configuration_from_environment()
    router = APIRouter()

    @router.post("/api/auth/register", status_code=201)
    def register(payload: SessionRegisterRequest, response: Response):
        try:
            with engine.begin() as conn:
                account = provision_new_consumer_account(
                    conn,
                    email=payload.email,
                    password=payload.password,
                )
                raw_session_id, context = create_server_session(
                    conn,
                    user_id=account.user_id,
                    active_household_id=account.household_id,
                    replace_existing=True,
                )
        except ConsumerAccountExistsError as exc:
            raise HTTPException(
                status_code=409,
                detail="Er bestaat al een account met dit e-mailadres.",
            ) from exc
        _set_session_cookie(response, raw_session_id, configuration)
        return public_session_payload(context)

    @router.post("/api/auth/login")
    def login(payload: SessionLoginRequest, response: Response):
        with engine.begin() as conn:
            identity = _resolve_login_identity(conn, payload.email, payload.password)
            if identity.get("platform_system_context"):
                raw_session_id, context = create_system_server_session(
                    conn,
                    user_id=identity["user_id"],
                    replace_existing=True,
                )
            elif identity["active_household_id"] is None:
                raw_session_id, context = create_none_server_session(
                    conn,
                    user_id=identity["user_id"],
                    replace_existing=True,
                )
            else:
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

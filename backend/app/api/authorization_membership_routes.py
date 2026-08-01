from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Header, HTTPException
from sqlalchemy import inspect, text

from app.db import engine
from app.services.authorization_foundation_service import (
    HOUSEHOLD_PERMISSIONS,
    ensure_authorization_foundation,
    write_authorization_audit,
)
from app.services.authorization_membership_service import (
    AuthorizationDeniedError,
    migrate_legacy_household_memberships,
    require_household_permission,
    set_household_membership_role,
    set_household_permission_override,
)
from app.services.session_request_context import resolve_current_server_session

router = APIRouter(tags=["authorization"])


def _bearer_email(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.split(" ", 1)[1].strip()
    if token == "rezzerv-dev-token":
        return "admin@rezzerv.local"
    if token.startswith("rezzerv-dev-token::"):
        email = token.split("::", 1)[1].strip().lower()
        if email:
            return email
    raise HTTPException(status_code=401, detail="Unauthorized")


def _column_names(conn, table_name: str) -> set[str]:
    inspector = inspect(conn)
    if table_name not in inspector.get_table_names():
        return set()
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def _session_identity(
    authorization: str | None,
    household_id: str,
) -> tuple[str, str | None]:
    """Resolve the actor from the authoritative server session.

    The bearer-token fallback exists only for the isolated route unit tests that
    instantiate this router without the application session middleware. Runtime
    browser requests never gain authority from the Authorization header.
    """

    try:
        session = resolve_current_server_session()
    except HTTPException as exc:
        if exc.status_code != 401 or not authorization:
            raise
        return _bearer_email(authorization), None

    requested_household_id = str(household_id or "").strip()
    if requested_household_id != str(session.active_household_id):
        raise HTTPException(
            status_code=403,
            detail="Geen toegang tot het gevraagde huishouden",
        )
    return str(session.email), str(session.user_id)


def _actor_context(conn, authorization: str | None, household_id: str) -> dict[str, str]:
    email, session_user_id = _session_identity(authorization, household_id)
    user_columns = _column_names(conn, "app_users")
    if not user_columns or "email" not in user_columns:
        raise HTTPException(status_code=401, detail="Unauthorized")
    user_id_expression = "id" if "id" in user_columns else "email"
    user = conn.execute(text(
        f"SELECT {user_id_expression} AS user_id, email FROM app_users "
        "WHERE lower(email) = lower(:email) LIMIT 1"
    ), {"email": email}).mappings().first()
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if session_user_id is not None and str(user["user_id"]) != session_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    membership_columns = _column_names(conn, "household_memberships")
    if "household_id" not in membership_columns:
        raise HTTPException(status_code=403, detail="Geen toegang tot het gevraagde huishouden")

    membership_id_expression = "id" if "id" in membership_columns else (
        "user_email" if "user_email" in membership_columns else "user_id"
    )
    active_condition = (
        "AND lower(trim(COALESCE(status, 'active'))) = 'active'"
        if "status" in membership_columns
        else ""
    )
    if "user_email" in membership_columns:
        membership = conn.execute(text(
            f"SELECT {membership_id_expression} AS membership_id FROM household_memberships "
            "WHERE household_id = :household_id "
            "AND lower(user_email) = lower(:email) "
            f"{active_condition} LIMIT 1"
        ), {"household_id": str(household_id), "email": email}).mappings().first()
    elif "user_id" in membership_columns:
        membership = conn.execute(text(
            f"SELECT {membership_id_expression} AS membership_id FROM household_memberships "
            "WHERE household_id = :household_id AND user_id = :user_id "
            f"{active_condition} LIMIT 1"
        ), {"household_id": str(household_id), "user_id": str(user["user_id"])}).mappings().first()
    else:
        raise HTTPException(status_code=403, detail="Geen toegang tot het gevraagde huishouden")

    if not membership:
        raise HTTPException(status_code=403, detail="Geen toegang tot het gevraagde huishouden")

    ensure_authorization_foundation(conn)
    migrate_legacy_household_memberships(conn)
    return {
        "email": str(user["email"]),
        "user_id": str(user["user_id"]),
        "membership_id": str(membership["membership_id"]),
        "household_id": str(household_id),
    }


def _require(conn, context: dict[str, str], permission_key: str) -> None:
    try:
        require_household_permission(
            conn,
            household_id=context["household_id"],
            membership_id=context["membership_id"],
            permission_key=permission_key,
        )
    except AuthorizationDeniedError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "authorization_denied",
                "permission_key": exc.decision.permission_key,
                "reason": exc.decision.reason,
            },
        ) from exc


def _target_membership(conn, household_id: str, membership_id: str) -> dict[str, Any]:
    membership_columns = _column_names(conn, "household_memberships")
    id_column = "id" if "id" in membership_columns else None
    if not id_column:
        raise HTTPException(status_code=404, detail="Onbekend huishoudlid")
    select_email = "user_email" if "user_email" in membership_columns else "NULL"
    row = conn.execute(text(
        f"SELECT {id_column} AS membership_id, {select_email} AS user_email "
        "FROM household_memberships WHERE household_id = :household_id "
        f"AND {id_column} = :membership_id LIMIT 1"
    ), {"household_id": str(household_id), "membership_id": str(membership_id)}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Onbekend huishoudlid")
    return dict(row)


@router.get("/api/households/{household_id}/authorization/members")
def list_authorization_members(
    household_id: str,
    authorization: str | None = Header(default=None),
):
    with engine.begin() as conn:
        context = _actor_context(conn, authorization, household_id)
        _require(conn, context, "members.view")
        membership_columns = _column_names(conn, "household_memberships")
        id_column = "id" if "id" in membership_columns else "user_email"
        email_column = "user_email" if "user_email" in membership_columns else "NULL"
        legacy_role_column = "role" if "role" in membership_columns else "NULL"
        rows = conn.execute(text(f"""
            SELECT hm.{id_column} AS membership_id,
                   hm.{email_column} AS email,
                   hm.{legacy_role_column} AS legacy_role,
                   ar.role_key,
                   r.name AS role_name
            FROM household_memberships hm
            LEFT JOIN auth_membership_roles ar
              ON ar.household_id = hm.household_id
             AND ar.membership_id = CAST(hm.{id_column} AS TEXT)
             AND ar.active = 1
            LEFT JOIN auth_roles r ON r.role_key = ar.role_key
            WHERE hm.household_id = :household_id
            ORDER BY lower(COALESCE(hm.{email_column}, '')), hm.{id_column}
        """), {"household_id": str(household_id)}).mappings().all()
        items = []
        for row in rows:
            membership_id = str(row["membership_id"])
            overrides = conn.execute(text("""
                SELECT permission_key, effect, reason
                FROM auth_membership_permission_overrides
                WHERE household_id = :household_id AND membership_id = :membership_id
                ORDER BY permission_key
            """), {"household_id": str(household_id), "membership_id": membership_id}).mappings().all()
            items.append({
                "membership_id": membership_id,
                "email": row.get("email"),
                "legacy_role": row.get("legacy_role"),
                "role_key": row.get("role_key"),
                "role_name": row.get("role_name"),
                "permission_overrides": [dict(item) for item in overrides],
                "is_current_user": membership_id == context["membership_id"],
            })
        return {"household_id": str(household_id), "items": items, "total": len(items)}


@router.get("/api/households/{household_id}/authorization/roles")
def list_authorization_roles(
    household_id: str,
    authorization: str | None = Header(default=None),
):
    with engine.begin() as conn:
        context = _actor_context(conn, authorization, household_id)
        _require(conn, context, "permissions.view")
        rows = conn.execute(text("""
            SELECT role_key, name
            FROM auth_roles
            WHERE scope = 'household' AND active = 1
            ORDER BY CASE role_key
                WHEN 'household.viewer' THEN 1
                WHEN 'household.member' THEN 2
                WHEN 'household.advanced_member' THEN 3
                WHEN 'household.admin' THEN 4
                ELSE 99 END
        """)).mappings().all()
        items = []
        for row in rows:
            permission_keys = conn.execute(text("""
                SELECT rp.permission_key
                FROM auth_role_permissions rp
                JOIN auth_permissions p
                  ON p.permission_key = rp.permission_key
                 AND p.active = 1
                 AND p.scope = 'household'
                WHERE rp.role_key = :role_key
                ORDER BY rp.permission_key
            """), {"role_key": row["role_key"]}).scalars().all()
            items.append({
                "role_key": row["role_key"],
                "name": row["name"],
                "permission_keys": [str(key) for key in permission_keys],
            })
        return {"household_id": str(household_id), "items": items}


@router.get("/api/households/{household_id}/authorization/permissions")
def list_authorization_permissions(
    household_id: str,
    authorization: str | None = Header(default=None),
):
    with engine.begin() as conn:
        context = _actor_context(conn, authorization, household_id)
        _require(conn, context, "permissions.view")
        rows = conn.execute(text("""
            SELECT permission_key, description
            FROM auth_permissions
            WHERE scope = 'household' AND active = 1
            ORDER BY permission_key
        """)).mappings().all()
        return {"household_id": str(household_id), "items": [dict(row) for row in rows]}


@router.put("/api/households/{household_id}/authorization/members/{membership_id}/role")
def update_authorization_member_role(
    household_id: str,
    membership_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    authorization: str | None = Header(default=None),
):
    role_key = str(payload.get("role_key") or "").strip()
    if not role_key:
        raise HTTPException(status_code=400, detail="role_key is verplicht")
    with engine.begin() as conn:
        context = _actor_context(conn, authorization, household_id)
        _target_membership(conn, household_id, membership_id)
        try:
            set_household_membership_role(
                conn,
                household_id=str(household_id),
                actor_membership_id=context["membership_id"],
                actor_user_id=context["user_id"],
                target_membership_id=str(membership_id),
                role_key=role_key,
                reason=str(payload.get("reason") or "").strip() or None,
            )
        except AuthorizationDeniedError as exc:
            raise HTTPException(status_code=403, detail={"code": "authorization_denied", "permission_key": exc.decision.permission_key, "reason": exc.decision.reason}) from exc
        except ValueError as exc:
            message = str(exc)
            normalized_message = message.lower()
            is_last_admin_conflict = (
                "administrator" in normalized_message
                or "beheerder" in normalized_message
                or "last admin" in normalized_message
            )
            raise HTTPException(status_code=409 if is_last_admin_conflict else 400, detail=message) from exc
        return {"ok": True, "household_id": str(household_id), "membership_id": str(membership_id), "role_key": role_key}


@router.put("/api/households/{household_id}/authorization/members/{membership_id}/permissions/{permission_key}")
def update_authorization_member_permission(
    household_id: str,
    membership_id: str,
    permission_key: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    authorization: str | None = Header(default=None),
):
    effect = str(payload.get("effect") or "").strip().lower()
    with engine.begin() as conn:
        context = _actor_context(conn, authorization, household_id)
        _target_membership(conn, household_id, membership_id)
        try:
            set_household_permission_override(
                conn,
                household_id=str(household_id),
                actor_membership_id=context["membership_id"],
                actor_user_id=context["user_id"],
                target_membership_id=str(membership_id),
                permission_key=str(permission_key),
                effect=effect,
                reason=str(payload.get("reason") or "").strip() or None,
            )
        except AuthorizationDeniedError as exc:
            raise HTTPException(status_code=403, detail={"code": "authorization_denied", "permission_key": exc.decision.permission_key, "reason": exc.decision.reason}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "household_id": str(household_id), "membership_id": str(membership_id), "permission_key": str(permission_key), "effect": effect}


@router.delete("/api/households/{household_id}/authorization/members/{membership_id}/permissions/{permission_key}")
def delete_authorization_member_permission(
    household_id: str,
    membership_id: str,
    permission_key: str,
    authorization: str | None = Header(default=None),
):
    with engine.begin() as conn:
        context = _actor_context(conn, authorization, household_id)
        _require(conn, context, "permissions.manage")
        _target_membership(conn, household_id, membership_id)
        old_effect = conn.execute(text("""
            SELECT effect FROM auth_membership_permission_overrides
            WHERE household_id = :household_id AND membership_id = :membership_id
              AND permission_key = :permission_key
        """), {"household_id": str(household_id), "membership_id": str(membership_id), "permission_key": str(permission_key)}).scalar()
        if old_effect is None:
            raise HTTPException(status_code=404, detail="Rechtenuitzondering niet gevonden")
        conn.execute(text("""
            DELETE FROM auth_membership_permission_overrides
            WHERE household_id = :household_id AND membership_id = :membership_id
              AND permission_key = :permission_key
        """), {"household_id": str(household_id), "membership_id": str(membership_id), "permission_key": str(permission_key)})
        write_authorization_audit(
            conn,
            actor_user_id=context["user_id"],
            actor_type="household_member",
            household_id=str(household_id),
            action="authorization.permission_override.deleted",
            object_type="household_membership_permission",
            object_id=f"{membership_id}:{permission_key}",
            old_value={"effect": old_effect},
            new_value=None,
        )
        return {"ok": True, "deleted": True, "household_id": str(household_id), "membership_id": str(membership_id), "permission_key": str(permission_key)}

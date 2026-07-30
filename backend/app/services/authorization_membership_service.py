from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import inspect, text

from app.services.authorization_foundation_service import (
    AuthorizationDecision,
    assert_last_household_admin_remains,
    ensure_authorization_foundation,
    evaluate_household_permission,
    write_authorization_audit,
)


class AuthorizationDeniedError(PermissionError):
    def __init__(self, decision: AuthorizationDecision):
        super().__init__(f"Permission denied: {decision.permission_key} ({decision.reason})")
        self.decision = decision


@dataclass(frozen=True)
class LegacyMembershipMigrationResult:
    scanned: int
    created: int
    preserved: int
    skipped: int


def require_household_permission(
    conn,
    *,
    household_id: str,
    membership_id: str,
    permission_key: str,
) -> AuthorizationDecision:
    decision = evaluate_household_permission(
        conn,
        household_id=str(household_id),
        membership_id=str(membership_id),
        permission_key=permission_key,
    )
    if not decision.allowed:
        raise AuthorizationDeniedError(decision)
    return decision


def _table_columns(conn, table_name: str) -> set[str]:
    inspector = inspect(conn)
    if table_name not in inspector.get_table_names():
        return set()
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def _first_available(columns: set[str], candidates: tuple[str, ...]) -> str | None:
    return next((name for name in candidates if name in columns), None)


def _legacy_role_key(row: dict[str, Any], role_column: str | None, admin_column: str | None) -> str:
    if admin_column and bool(row.get(admin_column)):
        return "household.admin"
    role_value = str(row.get(role_column) or "").strip().lower() if role_column else ""
    if role_value in {"admin", "administrator", "beheerder", "owner", "eigenaar", "household.admin"}:
        return "household.admin"
    if role_value in {"viewer", "lezer", "read", "readonly", "household.viewer"}:
        return "household.viewer"
    if role_value in {"advanced", "advanced_member", "gevorderd", "household.advanced_member"}:
        return "household.advanced_member"
    return "household.member"


def migrate_legacy_household_memberships(conn) -> LegacyMembershipMigrationResult:
    """Koppel bestaande lidmaatschappen additief aan autorisatierollen.

    Bestaande expliciete autorisatierollen worden nooit overschreven. De migratie
    ondersteunt de historisch voorkomende kolomnamen en slaat onvolledige rijen over.
    """
    ensure_authorization_foundation(conn)
    columns = _table_columns(conn, "household_memberships")
    if not columns:
        return LegacyMembershipMigrationResult(0, 0, 0, 0)

    membership_column = _first_available(columns, ("id", "membership_id"))
    household_column = _first_available(columns, ("household_id", "huishouden_id"))
    role_column = _first_available(columns, ("role", "rol", "role_key", "membership_role"))
    admin_column = _first_available(columns, ("is_admin", "is_owner", "beheerder"))
    status_column = _first_available(columns, ("status", "membership_status"))
    active_column = _first_available(columns, ("active", "is_active"))

    if not membership_column or not household_column:
        return LegacyMembershipMigrationResult(0, 0, 0, 0)

    rows = conn.execute(text("SELECT * FROM household_memberships")).mappings().all()
    created = preserved = skipped = 0
    for raw_row in rows:
        row = dict(raw_row)
        membership_id = row.get(membership_column)
        household_id = row.get(household_column)
        if membership_id is None or household_id is None:
            skipped += 1
            continue
        if active_column and not bool(row.get(active_column)):
            skipped += 1
            continue
        if status_column and str(row.get(status_column) or "active").strip().lower() not in {
            "active", "actief", "accepted", "geaccepteerd",
        }:
            skipped += 1
            continue

        existing = conn.execute(text("""
            SELECT role_key FROM auth_membership_roles
            WHERE household_id = :household_id AND membership_id = :membership_id
            LIMIT 1
        """), {
            "household_id": str(household_id),
            "membership_id": str(membership_id),
        }).scalar()
        if existing:
            preserved += 1
            continue

        role_key = _legacy_role_key(row, role_column, admin_column)
        conn.execute(text("""
            INSERT INTO auth_membership_roles(
                household_id, membership_id, role_key, active
            ) VALUES (
                :household_id, :membership_id, :role_key, 1
            )
        """), {
            "household_id": str(household_id),
            "membership_id": str(membership_id),
            "role_key": role_key,
        })
        created += 1

    return LegacyMembershipMigrationResult(len(rows), created, preserved, skipped)


def set_household_membership_role(
    conn,
    *,
    household_id: str,
    actor_membership_id: str,
    actor_user_id: str,
    target_membership_id: str,
    role_key: str,
    reason: str | None = None,
) -> None:
    require_household_permission(
        conn,
        household_id=household_id,
        membership_id=actor_membership_id,
        permission_key="members.manage",
    )
    allowed_roles = {
        "household.viewer",
        "household.member",
        "household.advanced_member",
        "household.admin",
    }
    if role_key not in allowed_roles:
        raise ValueError("Unknown or non-household role")

    old_role = conn.execute(text("""
        SELECT role_key FROM auth_membership_roles
        WHERE household_id = :household_id
          AND membership_id = :membership_id
          AND active = 1
        LIMIT 1
    """), {
        "household_id": str(household_id),
        "membership_id": str(target_membership_id),
    }).scalar()

    if old_role == "household.admin" and role_key != "household.admin":
        assert_last_household_admin_remains(
            conn,
            household_id=str(household_id),
            membership_id_to_remove=str(target_membership_id),
        )

    conn.execute(text("""
        INSERT INTO auth_membership_roles(
            household_id, membership_id, role_key, active, updated_at
        ) VALUES (
            :household_id, :membership_id, :role_key, 1, CURRENT_TIMESTAMP
        )
        ON CONFLICT(household_id, membership_id) DO UPDATE SET
            role_key = excluded.role_key,
            active = 1,
            updated_at = CURRENT_TIMESTAMP
    """), {
        "household_id": str(household_id),
        "membership_id": str(target_membership_id),
        "role_key": role_key,
    })
    write_authorization_audit(
        conn,
        actor_user_id=str(actor_user_id),
        actor_type="household_member",
        household_id=str(household_id),
        action="authorization.membership_role.updated",
        object_type="household_membership",
        object_id=str(target_membership_id),
        old_value={"role_key": old_role},
        new_value={"role_key": role_key},
        reason=reason,
    )


def set_household_permission_override(
    conn,
    *,
    household_id: str,
    actor_membership_id: str,
    actor_user_id: str,
    target_membership_id: str,
    permission_key: str,
    effect: str,
    reason: str | None = None,
) -> None:
    require_household_permission(
        conn,
        household_id=household_id,
        membership_id=actor_membership_id,
        permission_key="permissions.manage",
    )
    if effect not in {"allow", "deny"}:
        raise ValueError("effect must be allow or deny")
    if permission_key.startswith("platform."):
        raise ValueError("Platform permissions cannot be assigned in household scope")

    old_effect = conn.execute(text("""
        SELECT effect FROM auth_membership_permission_overrides
        WHERE household_id = :household_id
          AND membership_id = :membership_id
          AND permission_key = :permission_key
        LIMIT 1
    """), {
        "household_id": str(household_id),
        "membership_id": str(target_membership_id),
        "permission_key": permission_key,
    }).scalar()

    conn.execute(text("""
        INSERT INTO auth_membership_permission_overrides(
            household_id, membership_id, permission_key, effect, reason, updated_at
        ) VALUES (
            :household_id, :membership_id, :permission_key, :effect, :reason, CURRENT_TIMESTAMP
        )
        ON CONFLICT(household_id, membership_id, permission_key) DO UPDATE SET
            effect = excluded.effect,
            reason = excluded.reason,
            updated_at = CURRENT_TIMESTAMP
    """), {
        "household_id": str(household_id),
        "membership_id": str(target_membership_id),
        "permission_key": permission_key,
        "effect": effect,
        "reason": reason,
    })
    write_authorization_audit(
        conn,
        actor_user_id=str(actor_user_id),
        actor_type="household_member",
        household_id=str(household_id),
        action="authorization.permission_override.updated",
        object_type="household_membership_permission",
        object_id=f"{target_membership_id}:{permission_key}",
        old_value={"effect": old_effect},
        new_value={"effect": effect},
        reason=reason,
    )

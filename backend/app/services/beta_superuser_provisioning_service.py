from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import inspect, text

from app.services.authorization_foundation_service import (
    ensure_authorization_foundation,
    evaluate_household_permission,
    evaluate_platform_permission,
    write_authorization_audit,
)


class BetaSuperuserProvisioningError(RuntimeError):
    pass


@dataclass(frozen=True)
class BetaSuperuserProvisioningResult:
    user_id: str
    email: str
    household_id: str
    membership_id: str
    household_role_created_or_updated: bool
    platform_role_created_or_updated: bool


def _columns(conn, table_name: str) -> set[str]:
    inspector = inspect(conn)
    if table_name not in inspector.get_table_names():
        return set()
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def _pick(columns: set[str], *candidates: str) -> str | None:
    return next((candidate for candidate in candidates if candidate in columns), None)


def _resolve_user(conn, email: str) -> tuple[str, str]:
    columns = _columns(conn, "app_users")
    id_column = _pick(columns, "id", "user_id")
    email_column = _pick(columns, "email", "email_address", "user_email")
    if not id_column or not email_column:
        raise BetaSuperuserProvisioningError("app_users heeft geen bruikbare id- en e-mailkolom")

    row = conn.execute(text(
        f"SELECT {id_column} AS user_id, {email_column} AS email "
        f"FROM app_users WHERE lower({email_column}) = lower(:email) LIMIT 1"
    ), {"email": email.strip()}).mappings().first()
    if not row:
        raise BetaSuperuserProvisioningError(f"Gebruiker niet gevonden: {email}")
    return str(row["user_id"]), str(row["email"])


def _resolve_membership(conn, *, user_id: str, email: str, household_id: str | None) -> tuple[str, str]:
    columns = _columns(conn, "household_memberships")
    membership_column = _pick(columns, "id", "membership_id")
    household_column = _pick(columns, "household_id", "huishouden_id")
    user_column = _pick(columns, "user_id", "app_user_id")
    email_column = _pick(columns, "email", "user_email", "member_email")
    active_column = _pick(columns, "active", "is_active")
    status_column = _pick(columns, "status", "membership_status")
    if not membership_column or not household_column or (not user_column and not email_column):
        raise BetaSuperuserProvisioningError("household_memberships heeft geen bruikbare lidmaatschapskolommen")

    predicates = []
    params = {"user_id": user_id, "email": email}
    if user_column:
        predicates.append(f"CAST({user_column} AS TEXT) = :user_id")
    if email_column:
        predicates.append(f"lower({email_column}) = lower(:email)")
    where = "(" + " OR ".join(predicates) + ")"
    if household_id is not None:
        where += f" AND CAST({household_column} AS TEXT) = :household_id"
        params["household_id"] = str(household_id)
    if active_column:
        where += f" AND COALESCE({active_column}, 1) = 1"
    if status_column:
        where += f" AND lower(COALESCE({status_column}, 'active')) IN ('active', 'actief', 'accepted', 'geaccepteerd')"

    rows = conn.execute(text(
        f"SELECT {membership_column} AS membership_id, {household_column} AS household_id "
        f"FROM household_memberships WHERE {where} ORDER BY {household_column}"
    ), params).mappings().all()
    if not rows:
        raise BetaSuperuserProvisioningError("Geen actief huishoudlidmaatschap gevonden voor het beta-account")
    if household_id is None and len(rows) != 1:
        raise BetaSuperuserProvisioningError(
            "Het beta-account heeft meerdere huishoudens; geef --household-id expliciet op"
        )
    return str(rows[0]["membership_id"]), str(rows[0]["household_id"])


def provision_po_beta_superuser(
    conn,
    *,
    email: str,
    household_id: str | None = None,
    actor_user_id: str = "system:po-beta-provisioning",
    reason: str = "Expliciete PO-bètatoegang",
) -> BetaSuperuserProvisioningResult:
    normalized_email = str(email or "").strip()
    if not normalized_email or "@" not in normalized_email:
        raise BetaSuperuserProvisioningError("Een geldige account-e-mail is verplicht")

    ensure_authorization_foundation(conn)
    user_id, stored_email = _resolve_user(conn, normalized_email)
    membership_id, resolved_household_id = _resolve_membership(
        conn,
        user_id=user_id,
        email=stored_email,
        household_id=household_id,
    )

    old_household_role = conn.execute(text("""
        SELECT role_key FROM auth_membership_roles
        WHERE household_id = :household_id AND membership_id = :membership_id
        LIMIT 1
    """), {
        "household_id": resolved_household_id,
        "membership_id": membership_id,
    }).scalar()
    household_changed = old_household_role != "household.admin"
    conn.execute(text("""
        INSERT INTO auth_membership_roles(household_id, membership_id, role_key, active, updated_at)
        VALUES (:household_id, :membership_id, 'household.admin', 1, CURRENT_TIMESTAMP)
        ON CONFLICT(household_id, membership_id) DO UPDATE SET
            role_key = 'household.admin', active = 1, updated_at = CURRENT_TIMESTAMP
    """), {"household_id": resolved_household_id, "membership_id": membership_id})

    old_platform_active = conn.execute(text("""
        SELECT active FROM auth_platform_user_roles
        WHERE user_id = :user_id AND role_key = 'platform.superuser'
        LIMIT 1
    """), {"user_id": user_id}).scalar()
    platform_changed = old_platform_active != 1
    conn.execute(text("""
        INSERT INTO auth_platform_user_roles(user_id, role_key, active, updated_at)
        VALUES (:user_id, 'platform.superuser', 1, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id, role_key) DO UPDATE SET
            active = 1, updated_at = CURRENT_TIMESTAMP
    """), {"user_id": user_id})

    if household_changed:
        write_authorization_audit(
            conn,
            actor_user_id=actor_user_id,
            actor_type="system_operator",
            household_id=resolved_household_id,
            action="authorization.po_beta.household_admin.provisioned",
            object_type="household_membership",
            object_id=membership_id,
            old_value={"role_key": old_household_role},
            new_value={"role_key": "household.admin"},
            reason=reason,
        )
    if platform_changed:
        write_authorization_audit(
            conn,
            actor_user_id=actor_user_id,
            actor_type="system_operator",
            action="authorization.po_beta.platform_superuser.provisioned",
            object_type="app_user",
            object_id=user_id,
            old_value={"active": old_platform_active},
            new_value={"role_key": "platform.superuser", "active": 1},
            reason=reason,
        )

    household_decision = evaluate_household_permission(
        conn,
        household_id=resolved_household_id,
        membership_id=membership_id,
        permission_key="permissions.manage",
    )
    platform_decision = evaluate_platform_permission(
        conn,
        user_id=user_id,
        permission_key="platform.permissions.manage",
    )
    if not household_decision.allowed or not platform_decision.allowed:
        raise BetaSuperuserProvisioningError("Provisioning kon niet end-to-end worden geverifieerd")

    return BetaSuperuserProvisioningResult(
        user_id=user_id,
        email=stored_email,
        household_id=resolved_household_id,
        membership_id=membership_id,
        household_role_created_or_updated=household_changed,
        platform_role_created_or_updated=platform_changed,
    )

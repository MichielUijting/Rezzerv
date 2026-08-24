from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from app.services.authorization_foundation_service import ensure_authorization_foundation, write_authorization_audit
from app.services.authorization_membership_service import create_canonical_membership_role
from app.services.household_invitation_service import (
    INVITATION_ROLE_KEY,
    InvitationConflictError,
    InvitationNotFoundError,
    hash_invitation_token,
    resolve_pending_invitation_token,
    utc_now,
)
from app.services.household_invitation_target_policy import assert_household_invitation_target_allowed
from app.services.password_service import hash_password
from app.services.system_superuser_session_provisioning import SUPERGEBRUIKER_EMAIL


class InvitationEmailMismatchError(PermissionError):
    pass


class InvitationAccountExistsError(ValueError):
    pass


class InvitationMembershipConflictError(ValueError):
    pass


@dataclass(frozen=True)
class InvitationAcceptanceResult:
    invitation_id: str
    household_id: str
    household_name: str
    user_id: str
    email: str
    membership_id: str


def _normalize_email(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized or "@" not in normalized:
        raise ValueError("Geldig e-mailadres is verplicht")
    local, _, domain = normalized.partition("@")
    if not local or not domain or "." not in domain:
        raise ValueError("Geldig e-mailadres is verplicht")
    return normalized


def _columns(conn: Connection, table_name: str) -> set[str]:
    inspector = inspect(conn)
    if table_name not in inspector.get_table_names():
        return set()
    return {
        str(column.get("name") or "").strip()
        for column in inspector.get_columns(table_name)
    }


def _pick(columns: set[str], *candidates: str) -> str | None:
    return next((candidate for candidate in candidates if candidate in columns), None)


def _mask_email(email: str) -> str:
    normalized = _normalize_email(email)
    local, _, domain = normalized.partition("@")
    if len(local) <= 2:
        masked_local = local[0] + "*" * max(1, len(local) - 1)
    else:
        masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
    return f"{masked_local}@{domain}"


def _household_name(conn: Connection, household_id: str) -> str:
    columns = _columns(conn, "household_registry")
    id_column = _pick(columns, "id", "household_id")
    name_column = _pick(columns, "naam", "name")
    if not id_column or not name_column:
        raise RuntimeError("household_registry mist de vereiste kolommen")
    row = conn.execute(
        text(
            f"SELECT {name_column} AS household_name FROM household_registry "
            f"WHERE CAST({id_column} AS TEXT) = :household_id LIMIT 1"
        ),
        {"household_id": str(household_id)},
    ).mappings().first()
    if not row:
        raise InvitationConflictError("Uitgenodigd huishouden bestaat niet meer")
    return str(row.get("household_name") or "").strip() or "Huishouden"


def _account_by_email(conn: Connection, email: str):
    columns = _columns(conn, "app_users")
    id_column = _pick(columns, "id", "user_id")
    email_column = _pick(columns, "email", "user_email")
    if not id_column or not email_column:
        raise RuntimeError("app_users mist de vereiste accountkolommen")
    return conn.execute(
        text(
            f"SELECT {id_column} AS user_id, {email_column} AS email "
            f"FROM app_users WHERE lower(trim({email_column})) = :email LIMIT 2"
        ),
        {"email": _normalize_email(email)},
    ).mappings().all()


def preview_household_invitation(conn: Connection, *, raw_token: str) -> dict[str, object]:
    invitation = resolve_pending_invitation_token(conn, raw_token=raw_token)
    invitee_email = _normalize_email(str(invitation.get("invitee_email") or ""))
    assert_household_invitation_target_allowed(conn, invitee_email)
    household_id = str(invitation.get("household_id") or "").strip()
    accounts = _account_by_email(conn, invitee_email)
    if len(accounts) > 1:
        raise InvitationConflictError("Uitnodiging kan niet veilig aan een account worden gekoppeld")
    return {
        "status": "pending",
        "household_name": _household_name(conn, household_id),
        "invitee_email_masked": _mask_email(invitee_email),
        "account_exists": len(accounts) == 1,
        "expires_at": invitation.get("expires_at"),
    }


def provision_invited_consumer_account(
    conn: Connection,
    *,
    email: str,
    password: str,
) -> dict[str, str]:
    normalized_email = _normalize_email(email)
    if normalized_email == SUPERGEBRUIKER_EMAIL:
        raise InvitationAccountExistsError("Account is niet beschikbaar")
    assert_household_invitation_target_allowed(conn, normalized_email)
    ensure_authorization_foundation(conn)

    existing = _account_by_email(conn, normalized_email)
    if existing:
        raise InvitationAccountExistsError("Er bestaat al een account met dit e-mailadres")

    user_columns = _columns(conn, "app_users")
    user_id_column = _pick(user_columns, "id", "user_id")
    user_email_column = _pick(user_columns, "email", "user_email")
    user_password_column = _pick(user_columns, "password")
    if not user_id_column or not user_email_column or not user_password_column:
        raise RuntimeError("app_users mist de vereiste accountkolommen")

    encoded_password = hash_password(password)
    user_id = str(uuid.uuid4())
    insert_columns = [user_id_column, user_email_column, user_password_column]
    insert_values = [":user_id", ":email", ":password"]
    params: dict[str, object] = {
        "user_id": user_id,
        "email": normalized_email,
        "password": encoded_password,
    }
    if "password_hash" in user_columns:
        insert_columns.append("password_hash")
        insert_values.append(":password_hash")
        params["password_hash"] = encoded_password
    if "account_status" in user_columns:
        insert_columns.append("account_status")
        insert_values.append("'active'")
    if "created_at" in user_columns:
        insert_columns.append("created_at")
        insert_values.append("CURRENT_TIMESTAMP")
    if "updated_at" in user_columns:
        insert_columns.append("updated_at")
        insert_values.append("CURRENT_TIMESTAMP")

    conn.execute(
        text(
            f"INSERT INTO app_users ({', '.join(insert_columns)}) "
            f"VALUES ({', '.join(insert_values)})"
        ),
        params,
    )
    return {"user_id": user_id, "email": normalized_email}


def _existing_membership(
    conn: Connection,
    *,
    household_id: str,
    user_id: str,
    email: str,
):
    columns = _columns(conn, "household_memberships")
    household_column = _pick(columns, "household_id")
    membership_id_column = _pick(columns, "id", "membership_id")
    if not household_column or not membership_id_column:
        raise RuntimeError("household_memberships mist de vereiste kolommen")

    predicates = []
    params: dict[str, object] = {"household_id": str(household_id)}
    if "user_id" in columns:
        predicates.append("CAST(user_id AS TEXT) = :user_id")
        params["user_id"] = str(user_id)
    if "user_email" in columns:
        predicates.append("lower(trim(user_email)) = :email")
        params["email"] = _normalize_email(email)
    if not predicates:
        raise RuntimeError("household_memberships mist gebruikersidentiteit")

    return conn.execute(
        text(
            f"SELECT {membership_id_column} AS membership_id FROM household_memberships "
            f"WHERE {household_column} = :household_id "
            f"AND ({' OR '.join(predicates)}) LIMIT 1"
        ),
        params,
    ).mappings().first()


def _insert_member_membership(
    conn: Connection,
    *,
    household_id: str,
    user_id: str,
    email: str,
) -> str:
    columns = _columns(conn, "household_memberships")
    membership_id_column = _pick(columns, "id", "membership_id")
    household_column = _pick(columns, "household_id")
    role_column = _pick(columns, "role", "rol")
    if not membership_id_column or not household_column or not role_column:
        raise RuntimeError("household_memberships mist de vereiste lidmaatschapskolommen")
    if "user_id" not in columns and "user_email" not in columns:
        raise RuntimeError("household_memberships mist gebruikersidentiteit")

    membership_id = str(uuid.uuid4())
    insert_columns = [membership_id_column, household_column, role_column]
    insert_values = [":membership_id", ":household_id", "'member'"]
    params: dict[str, object] = {
        "membership_id": membership_id,
        "household_id": str(household_id),
        "user_id": str(user_id),
        "email": _normalize_email(email),
    }
    if "user_id" in columns:
        insert_columns.append("user_id")
        insert_values.append(":user_id")
    if "user_email" in columns:
        insert_columns.append("user_email")
        insert_values.append(":email")
    if "status" in columns:
        insert_columns.append("status")
        insert_values.append("'active'")
    if "active" in columns:
        insert_columns.append("active")
        insert_values.append("1")
    if "created_at" in columns:
        insert_columns.append("created_at")
        insert_values.append("CURRENT_TIMESTAMP")
    if "updated_at" in columns:
        insert_columns.append("updated_at")
        insert_values.append("CURRENT_TIMESTAMP")

    conn.execute(
        text(
            f"INSERT INTO household_memberships ({', '.join(insert_columns)}) "
            f"VALUES ({', '.join(insert_values)})"
        ),
        params,
    )
    role_key = create_canonical_membership_role(
        conn,
        household_id=str(household_id),
        membership_id=membership_id,
        legacy_role="member",
    )
    if role_key != INVITATION_ROLE_KEY:
        raise RuntimeError("Uitgenodigd lid kreeg geen canonieke Lid-rol")
    return membership_id


def accept_household_invitation(
    conn: Connection,
    *,
    raw_token: str,
    user_id: str,
    email: str,
    now: datetime | None = None,
) -> InvitationAcceptanceResult:
    normalized_user_id = str(user_id or "").strip()
    normalized_email = _normalize_email(email)
    if not normalized_user_id:
        raise ValueError("Gebruiker ontbreekt")

    invitation = resolve_pending_invitation_token(conn, raw_token=raw_token, now=now)
    invitee_email = _normalize_email(str(invitation.get("invitee_email") or ""))
    if invitee_email != normalized_email:
        raise InvitationEmailMismatchError("Deze uitnodiging hoort bij een ander e-mailadres")
    assert_household_invitation_target_allowed(conn, normalized_email)

    accounts = _account_by_email(conn, normalized_email)
    if len(accounts) != 1 or str(accounts[0].get("user_id") or "") != normalized_user_id:
        raise InvitationEmailMismatchError("Deze uitnodiging hoort bij een ander account")

    household_id = str(invitation.get("household_id") or "").strip()
    invitation_id = str(invitation.get("id") or "").strip()
    if not household_id or not invitation_id:
        raise InvitationNotFoundError("Uitnodiging niet gevonden")
    if _existing_membership(
        conn,
        household_id=household_id,
        user_id=normalized_user_id,
        email=normalized_email,
    ):
        raise InvitationMembershipConflictError("Dit account is al aan dit huishouden gekoppeld")

    accepted_at = (now or utc_now()).astimezone(timezone.utc).isoformat()
    token_hash = hash_invitation_token(raw_token)
    claimed = conn.execute(
        text(
            """
            UPDATE household_invitations
            SET status = 'accepted',
                accepted_by_user_id = :user_id,
                accepted_at = :accepted_at,
                updated_at = :accepted_at
            WHERE id = :invitation_id
              AND household_id = :household_id
              AND token_hash = :token_hash
              AND status = 'pending'
            """
        ),
        {
            "user_id": normalized_user_id,
            "accepted_at": accepted_at,
            "invitation_id": invitation_id,
            "household_id": household_id,
            "token_hash": token_hash,
        },
    )
    if int(claimed.rowcount or 0) != 1:
        raise InvitationConflictError("Uitnodiging is niet meer geldig")

    membership_id = _insert_member_membership(
        conn,
        household_id=household_id,
        user_id=normalized_user_id,
        email=normalized_email,
    )
    household_name = _household_name(conn, household_id)
    write_authorization_audit(
        conn,
        actor_user_id=normalized_user_id,
        actor_type="household_member",
        household_id=household_id,
        action="household.invitation.accepted",
        object_type="household_invitation",
        object_id=invitation_id,
        new_value={
            "status": "accepted",
            "membership_id": membership_id,
            "role_key": INVITATION_ROLE_KEY,
        },
        reason="household_invitation_acceptance",
    )
    return InvitationAcceptanceResult(
        invitation_id=invitation_id,
        household_id=household_id,
        household_name=household_name,
        user_id=normalized_user_id,
        email=normalized_email,
        membership_id=membership_id,
    )

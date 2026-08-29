from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import uuid

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from app.services.authorization_foundation_service import write_authorization_audit

INVITATION_ROLE_KEY = "household.member"
INVITATION_STATUS_PENDING = "pending"
INVITATION_STATUS_ACCEPTED = "accepted"
INVITATION_STATUS_REVOKED = "revoked"
INVITATION_STATUS_EXPIRED = "expired"
INVITATION_STATUSES = frozenset(
    {
        INVITATION_STATUS_PENDING,
        INVITATION_STATUS_ACCEPTED,
        INVITATION_STATUS_REVOKED,
        INVITATION_STATUS_EXPIRED,
    }
)
DEFAULT_INVITATION_TTL = timedelta(days=7)

_INVITATION_TABLE = "household_invitations"
_REQUIRED_LIFECYCLE_COLUMNS = {
    "id",
    "household_id",
    "invitee_email",
    "role_key",
    "token_hash",
    "status",
    "expires_at",
    "created_by_user_id",
    "accepted_by_user_id",
    "created_at",
    "updated_at",
    "accepted_at",
    "revoked_at",
}
_REQUIRED_INDEXES = {
    "idx_household_invitations_one_pending": ("household_id", "invitee_email"),
    "idx_household_invitations_household_status": ("household_id", "status", "created_at"),
    "idx_household_invitations_expiry": ("status", "expires_at"),
}


class InvitationConflictError(ValueError):
    pass


class InvitationNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class InvitationCreationResult:
    invitation: dict[str, object]
    raw_token: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return normalized.astimezone(timezone.utc).isoformat()


def _public_timestamp(value: object) -> object:
    if isinstance(value, datetime):
        return _iso(value)
    return value


def _normalize_email(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized or "@" not in normalized:
        raise ValueError("Geldig e-mailadres is verplicht")
    local, _, domain = normalized.partition("@")
    if not local or not domain or "." not in domain:
        raise ValueError("Geldig e-mailadres is verplicht")
    return normalized


def new_invitation_token() -> str:
    # 32 random bytes = 256 bits of entropy. Only the digest is persisted.
    return secrets.token_urlsafe(32)


def hash_invitation_token(raw_token: str) -> str:
    normalized = str(raw_token or "").strip()
    if not normalized:
        raise ValueError("Uitnodigingstoken ontbreekt")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def ensure_household_invitation_foundation(conn: Connection) -> None:
    """Validate the Alembic-owned household invitation lifecycle schema."""
    inspector = inspect(conn)
    if not inspector.has_table(_INVITATION_TABLE):
        raise RuntimeError(
            "Canonical uitnodigingsschema mist household_invitations. "
            "Voer Alembic migrations uit met MIGRATION_DATABASE_URL."
        )
    columns = {
        str(column.get("name") or "")
        for column in inspector.get_columns(_INVITATION_TABLE)
    }
    missing = _REQUIRED_LIFECYCLE_COLUMNS - columns
    if missing:
        raise RuntimeError(
            "Canonical uitnodigingsschema wijkt af: "
            f"household_invitations mist {sorted(missing)}. Voer Alembic migrations uit."
        )
    primary_key = tuple(
        inspector.get_pk_constraint(_INVITATION_TABLE).get("constrained_columns") or ()
    )
    if primary_key != ("id",):
        raise RuntimeError(
            f"Canonical household_invitations primary key wijkt af: {primary_key!r}"
        )
    indexes = {
        str(index.get("name") or ""): index
        for index in inspector.get_indexes(_INVITATION_TABLE)
    }
    for index_name, expected_columns in _REQUIRED_INDEXES.items():
        index = indexes.get(index_name)
        actual_columns = tuple((index or {}).get("column_names") or ())
        if index is None or actual_columns != expected_columns:
            raise RuntimeError(
                f"Canonical invitation index {index_name} wijkt af: "
                f"expected={expected_columns!r} actual={actual_columns!r}"
            )
    if not bool(indexes["idx_household_invitations_one_pending"].get("unique")):
        raise RuntimeError("Canonical pending invitation index moet uniek zijn")


def _membership_exists(conn: Connection, household_id: str, invitee_email: str) -> bool:
    inspector = inspect(conn)
    if "household_memberships" not in inspector.get_table_names():
        return False
    columns = {
        str(column.get("name") or "").strip().lower()
        for column in inspector.get_columns("household_memberships")
    }
    if "household_id" not in columns:
        return False
    if "user_email" in columns:
        row = conn.execute(
            text(
                """
                SELECT 1
                FROM household_memberships
                WHERE household_id = :household_id
                  AND lower(trim(user_email)) = :invitee_email
                LIMIT 1
                """
            ),
            {"household_id": str(household_id), "invitee_email": invitee_email},
        ).first()
        return bool(row)
    if "user_id" in columns and "app_users" in inspector.get_table_names():
        user_columns = {
            str(column.get("name") or "").strip().lower()
            for column in inspector.get_columns("app_users")
        }
        if "id" in user_columns and "email" in user_columns:
            row = conn.execute(
                text(
                    """
                    SELECT 1
                    FROM household_memberships hm
                    JOIN app_users u ON u.id = hm.user_id
                    WHERE hm.household_id = :household_id
                      AND lower(trim(u.email)) = :invitee_email
                    LIMIT 1
                    """
                ),
                {"household_id": str(household_id), "invitee_email": invitee_email},
            ).first()
            return bool(row)
    return False


def _expire_pending_invitations(
    conn: Connection,
    *,
    household_id: str | None = None,
    now: datetime | None = None,
) -> int:
    current = _iso(now or utc_now())
    params: dict[str, object] = {"now": current}
    household_filter = ""
    if household_id is not None:
        household_filter = " AND household_id = :household_id"
        params["household_id"] = str(household_id)
    result = conn.execute(
        text(
            "UPDATE household_invitations "
            "SET status = 'expired', updated_at = :now "
            "WHERE status = 'pending' AND expires_at <= :now"
            + household_filter
        ),
        params,
    )
    return int(result.rowcount or 0)


def _public_invitation(row) -> dict[str, object]:
    data = dict(row)
    # token_hash is deliberately never part of a public/service-list projection.
    data.pop("token_hash", None)
    return {
        "id": str(data.get("id") or ""),
        "household_id": str(data.get("household_id") or ""),
        "invitee_email": str(data.get("invitee_email") or ""),
        "role_key": str(data.get("role_key") or INVITATION_ROLE_KEY),
        "status": str(data.get("status") or ""),
        "expires_at": _public_timestamp(data.get("expires_at")),
        "created_by_user_id": str(data.get("created_by_user_id") or ""),
        "accepted_by_user_id": data.get("accepted_by_user_id"),
        "created_at": _public_timestamp(data.get("created_at")),
        "updated_at": _public_timestamp(data.get("updated_at")),
        "accepted_at": _public_timestamp(data.get("accepted_at")),
        "revoked_at": _public_timestamp(data.get("revoked_at")),
    }


def _invitation_row(conn: Connection, invitation_id: str, household_id: str):
    return conn.execute(
        text(
            """
            SELECT *
            FROM household_invitations
            WHERE id = :invitation_id
              AND household_id = :household_id
            LIMIT 1
            """
        ),
        {"invitation_id": str(invitation_id), "household_id": str(household_id)},
    ).mappings().first()


def create_household_invitation(
    conn: Connection,
    *,
    household_id: str,
    invitee_email: str,
    created_by_user_id: str,
    now: datetime | None = None,
    ttl: timedelta = DEFAULT_INVITATION_TTL,
) -> InvitationCreationResult:
    ensure_household_invitation_foundation(conn)
    normalized_household_id = str(household_id or "").strip()
    normalized_actor = str(created_by_user_id or "").strip()
    normalized_email = _normalize_email(invitee_email)
    if not normalized_household_id:
        raise ValueError("Huishouden ontbreekt")
    if not normalized_actor:
        raise ValueError("Actor ontbreekt")
    if ttl <= timedelta(0):
        raise ValueError("Uitnodigingsduur moet positief zijn")

    current = now or utc_now()
    _expire_pending_invitations(
        conn,
        household_id=normalized_household_id,
        now=current,
    )
    if _membership_exists(conn, normalized_household_id, normalized_email):
        raise InvitationConflictError("Gebruiker is al gekoppeld aan dit huishouden")
    pending = conn.execute(
        text(
            """
            SELECT id
            FROM household_invitations
            WHERE household_id = :household_id
              AND invitee_email = :invitee_email
              AND status = 'pending'
            LIMIT 1
            """
        ),
        {"household_id": normalized_household_id, "invitee_email": normalized_email},
    ).first()
    if pending:
        raise InvitationConflictError("Er staat al een uitnodiging open voor dit e-mailadres")

    invitation_id = str(uuid.uuid4())
    raw_token = new_invitation_token()
    token_hash = hash_invitation_token(raw_token)
    created_at = _iso(current)
    expires_at = _iso(current + ttl)
    conn.execute(
        text(
            """
            INSERT INTO household_invitations(
                id, household_id, invitee_email, role_key, token_hash, status,
                expires_at, created_by_user_id, accepted_by_user_id,
                created_at, updated_at, accepted_at, revoked_at
            ) VALUES (
                :id, :household_id, :invitee_email, :role_key, :token_hash, 'pending',
                :expires_at, :created_by_user_id, NULL,
                :created_at, :updated_at, NULL, NULL
            )
            """
        ),
        {
            "id": invitation_id,
            "household_id": normalized_household_id,
            "invitee_email": normalized_email,
            "role_key": INVITATION_ROLE_KEY,
            "token_hash": token_hash,
            "expires_at": expires_at,
            "created_by_user_id": normalized_actor,
            "created_at": created_at,
            "updated_at": created_at,
        },
    )
    write_authorization_audit(
        conn,
        actor_user_id=normalized_actor,
        actor_type="household_member",
        household_id=normalized_household_id,
        action="household.invitation.created",
        object_type="household_invitation",
        object_id=invitation_id,
        new_value={
            "invitee_email": normalized_email,
            "role_key": INVITATION_ROLE_KEY,
            "status": INVITATION_STATUS_PENDING,
            "expires_at": expires_at,
        },
    )
    row = _invitation_row(conn, invitation_id, normalized_household_id)
    if not row:
        raise RuntimeError("Uitnodiging kon niet worden teruggelezen")
    return InvitationCreationResult(
        invitation=_public_invitation(row),
        raw_token=raw_token,
    )


def list_household_invitations(
    conn: Connection,
    *,
    household_id: str,
    now: datetime | None = None,
) -> list[dict[str, object]]:
    ensure_household_invitation_foundation(conn)
    normalized_household_id = str(household_id or "").strip()
    if not normalized_household_id:
        raise ValueError("Huishouden ontbreekt")
    _expire_pending_invitations(
        conn,
        household_id=normalized_household_id,
        now=now,
    )
    rows = conn.execute(
        text(
            """
            SELECT *
            FROM household_invitations
            WHERE household_id = :household_id
            ORDER BY created_at DESC, id DESC
            """
        ),
        {"household_id": normalized_household_id},
    ).mappings().all()
    return [_public_invitation(row) for row in rows]


def revoke_household_invitation(
    conn: Connection,
    *,
    household_id: str,
    invitation_id: str,
    actor_user_id: str,
    now: datetime | None = None,
) -> dict[str, object]:
    ensure_household_invitation_foundation(conn)
    normalized_household_id = str(household_id or "").strip()
    normalized_invitation_id = str(invitation_id or "").strip()
    normalized_actor = str(actor_user_id or "").strip()
    if not normalized_household_id or not normalized_invitation_id:
        raise InvitationNotFoundError("Uitnodiging niet gevonden")
    if not normalized_actor:
        raise ValueError("Actor ontbreekt")
    current = now or utc_now()
    _expire_pending_invitations(
        conn,
        household_id=normalized_household_id,
        now=current,
    )
    row = _invitation_row(conn, normalized_invitation_id, normalized_household_id)
    if not row:
        raise InvitationNotFoundError("Uitnodiging niet gevonden")
    old_public = _public_invitation(row)
    if str(row.get("status") or "") != INVITATION_STATUS_PENDING:
        raise InvitationConflictError(
            f"Alleen een open uitnodiging kan worden ingetrokken; huidige status is {row.get('status')}"
        )
    revoked_at = _iso(current)
    conn.execute(
        text(
            """
            UPDATE household_invitations
            SET status = 'revoked', revoked_at = :revoked_at, updated_at = :revoked_at
            WHERE id = :invitation_id
              AND household_id = :household_id
              AND status = 'pending'
            """
        ),
        {
            "revoked_at": revoked_at,
            "invitation_id": normalized_invitation_id,
            "household_id": normalized_household_id,
        },
    )
    updated = _invitation_row(conn, normalized_invitation_id, normalized_household_id)
    if not updated or str(updated.get("status") or "") != INVITATION_STATUS_REVOKED:
        raise InvitationConflictError("Uitnodiging kon niet veilig worden ingetrokken")
    public = _public_invitation(updated)
    write_authorization_audit(
        conn,
        actor_user_id=normalized_actor,
        actor_type="household_member",
        household_id=normalized_household_id,
        action="household.invitation.revoked",
        object_type="household_invitation",
        object_id=normalized_invitation_id,
        old_value={"status": old_public["status"]},
        new_value={"status": public["status"], "revoked_at": public["revoked_at"]},
    )
    return public


def resolve_pending_invitation_token(
    conn: Connection,
    *,
    raw_token: str,
    now: datetime | None = None,
) -> dict[str, object]:
    """Resolve a token for the later acceptance slice without exposing its digest."""

    ensure_household_invitation_foundation(conn)
    token_hash = hash_invitation_token(raw_token)
    row = conn.execute(
        text(
            """
            SELECT *
            FROM household_invitations
            WHERE token_hash = :token_hash
            LIMIT 1
            """
        ),
        {"token_hash": token_hash},
    ).mappings().first()
    if not row:
        raise InvitationNotFoundError("Uitnodiging niet gevonden")
    _expire_pending_invitations(
        conn,
        household_id=str(row.get("household_id") or ""),
        now=now,
    )
    refreshed = _invitation_row(
        conn,
        str(row.get("id") or ""),
        str(row.get("household_id") or ""),
    )
    if not refreshed:
        raise InvitationNotFoundError("Uitnodiging niet gevonden")
    if str(refreshed.get("status") or "") != INVITATION_STATUS_PENDING:
        raise InvitationConflictError("Uitnodiging is niet meer geldig")
    return _public_invitation(refreshed)

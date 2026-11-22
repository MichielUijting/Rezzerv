"""Fail-closed deletion of a regular Inhuis account, preserving shared households.

The caller owns the transaction. Unknown identity references abort the deletion.
"""
from __future__ import annotations

from typing import Any
from pathlib import Path
import hashlib
import os

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from app.services.authorization_foundation_service import resolve_active_platform_role_keys
from app.services.authorization_membership_service import resolve_effective_household_role
from app.services.household_reset_service import reset_household_data
from app.services.consumer_account_file_deletion_service import HouseholdFileStage, AccountFileDeletionConflict
from app.services.password_service import verify_password

CONFIRMATION = "VERWIJDER MIJN ACCOUNT"
DELETED_IDENTITY = "verwijderde-gebruiker"


class AccountDeletionConflictError(RuntimeError):
    pass


class AccountDeletionPasswordError(ValueError):
    pass


def _columns(conn: Connection, table: str) -> set[str]:
    inspector = inspect(conn)
    if not inspector.has_table(table):
        return set()
    return {str(c["name"]) for c in inspector.get_columns(table)}


def _required_columns(conn: Connection, table: str, needed: set[str]) -> set[str]:
    columns = _columns(conn, table)
    if not needed.issubset(columns):
        raise AccountDeletionConflictError(
            f"Accountverwijdering gestopt: {table} mist vereiste kolommen."
        )
    return columns


def _account(conn: Connection, user_id: str, *, lock: bool) -> dict[str, Any]:
    cols = _required_columns(conn, "app_users", {"id", "email", "password", "created_at"})
    hash_sql = "password_hash" if "password_hash" in cols else "NULL"
    locking = " FOR UPDATE" if lock and conn.dialect.name == "postgresql" else ""
    row = conn.execute(text(f"""
        SELECT id, email, password, {hash_sql} AS password_hash
        FROM app_users WHERE id=:user_id{locking}
    """), {"user_id": user_id}).mappings().first()
    if row is None:
        raise AccountDeletionConflictError("Het account bestaat niet meer.")
    return dict(row)


def _memberships(conn: Connection, uid: str, email: str) -> list[dict[str, Any]]:
    # Canonical PostgreSQL membership rows identify the account by email;
    # the optional legacy user_id column is NOT part of the schema contract.
    columns = _required_columns(
        conn, "household_memberships", {"id", "household_id", "role", "user_email"}
    )
    user_id_sql = "user_id" if "user_id" in columns else "NULL"
    identity_predicate = (
        "CAST(user_id AS TEXT)=:uid OR lower(trim(user_email))=:email"
        if "user_id" in columns else "lower(trim(user_email))=:email"
    )
    rows = conn.execute(text(f"""
        SELECT id, household_id, role, {user_id_sql} AS user_id, user_email
        FROM household_memberships
        WHERE {identity_predicate}
        ORDER BY CAST(household_id AS TEXT), CAST(id AS TEXT)
    """), {"uid": uid, "email": email}).mappings().all()
    for row in rows:
        if str(row["user_id"] or "").strip() not in {"", uid} or str(row["user_email"] or "").strip().lower() != email:
            raise AccountDeletionConflictError("Lidmaatschap heeft conflicterende gebruikersidentiteit.")
    if len({str(row["household_id"]) for row in rows}) != len(rows):
        raise AccountDeletionConflictError("Dubbel huishoudlidmaatschap gevonden.")
    return [dict(row) for row in rows]


def _remaining(conn: Connection, household_id: str, email: str) -> list[dict[str, Any]]:
    _required_columns(conn, "app_users", {"id", "email", "created_at"})
    cols = _required_columns(conn, "household_memberships", {"id", "household_id", "role", "user_email"})
    active = " AND lower(trim(COALESCE(hm.status, 'active')))='active'" if "status" in cols else ""
    optional_user_join = (
        " AND (hm.user_id IS NULL OR trim(CAST(hm.user_id AS TEXT))='' "
        "OR CAST(u.id AS TEXT)=CAST(hm.user_id AS TEXT))"
        if "user_id" in cols else ""
    )
    rows = conn.execute(text(f"""
        SELECT hm.id AS membership_id, u.id AS user_id, u.created_at AS account_created_at
        FROM household_memberships hm
        JOIN app_users u ON lower(trim(u.email))=lower(trim(hm.user_email))
                        {optional_user_join}
        WHERE CAST(hm.household_id AS TEXT)=:hid
          AND lower(trim(hm.user_email))<>:email {active}
        ORDER BY u.created_at ASC NULLS LAST, CAST(u.id AS TEXT), CAST(hm.id AS TEXT)
    """), {"hid": household_id, "email": email}).mappings().all()
    other_count = int(conn.execute(text("""
        SELECT COUNT(*) FROM household_memberships
        WHERE CAST(household_id AS TEXT)=:hid
          AND (user_email IS NULL OR lower(trim(user_email))<>:email)
    """), {"hid": household_id, "email": email}).scalar() or 0)
    if other_count != len(rows):
        raise AccountDeletionConflictError(
            "Niet alle overige leden zijn eenduidig actief; de huishoudgegevens blijven beschermd."
        )
    if any(row.get("account_created_at") is None for row in rows):
        raise AccountDeletionConflictError("Aanmaakdatum van een overblijvende gebruiker ontbreekt.")
    if len({str(row["user_id"]) for row in rows}) != len(rows):
        raise AccountDeletionConflictError("Een huishouden heeft dubbele lidmaatschappen.")
    return [dict(row) for row in rows]


def deletion_preview(conn: Connection, *, user_id: str) -> dict[str, Any]:
    uid = str(user_id or "").strip()
    user = _account(conn, uid, lock=False)
    if resolve_active_platform_role_keys(conn, uid):
        raise AccountDeletionConflictError(
            "Een account met een actieve platformrol kan niet via Mijn account worden verwijderd."
        )
    members = _memberships(conn, uid, str(user["email"]).strip().lower())
    plans: list[dict[str, Any]] = []
    for member in members:
        hid = str(member["household_id"])
        if not hid or hid == "0":
            raise AccountDeletionConflictError("Systeemhuishoudens zijn uitgesloten.")
        registry = conn.execute(text("""
            SELECT id, context_type FROM household_registry
            WHERE CAST(id AS TEXT)=:hid
        """), {"hid": hid}).mappings().first()
        if not registry or str(registry.get("context_type") or "regular").lower() != "regular":
            raise AccountDeletionConflictError("Geen geldig regulier huishouden gevonden.")
        remaining = _remaining(conn, hid, str(user["email"]).strip().lower())
        role = resolve_effective_household_role(
            conn, household_id=hid, membership_id=str(member["id"]), legacy_role=member["role"]
        )
        if role not in {"household.admin", "household.member", "household.viewer", "household.advanced_member"}:
            raise AccountDeletionConflictError("Onbekende huishoudrol; verwijderen gestopt.")
        oldest = remaining[0] if remaining and role == "household.admin" else None
        plans.append({
            "household_id": hid,
            "membership_id": str(member["id"]),
            "delete_household": not remaining,
            "remaining_members": len(remaining),
            "successor_membership_id": str(oldest["membership_id"]) if oldest else None,
        })
    return {
        "account_will_be_deleted": True,
        "households_to_delete": sum(bool(p["delete_household"]) for p in plans),
        "households_to_keep": sum(not p["delete_household"] for p in plans),
        "households": plans,
    }


def _promote_successor(conn: Connection, hid: str, membership_id: str | None) -> None:
    if not membership_id:
        return
    params = {"hid": hid, "mid": membership_id}
    conn.execute(text("""
        INSERT INTO auth_membership_roles(household_id, membership_id, role_key, active, updated_at)
        VALUES (:hid, :mid, 'household.admin', TRUE, CURRENT_TIMESTAMP)
        ON CONFLICT(household_id, membership_id) DO UPDATE SET
            role_key='household.admin', active=TRUE, updated_at=CURRENT_TIMESTAMP
    """), params)
    count = conn.execute(text("""
        UPDATE household_memberships SET role='admin'
        WHERE CAST(household_id AS TEXT)=:hid AND CAST(id AS TEXT)=:mid
    """), params).rowcount
    if count != 1 or resolve_effective_household_role(
        conn, household_id=hid, membership_id=membership_id, legacy_role="admin"
    ) != "household.admin":
        raise AccountDeletionConflictError("Overdracht van Beheerder is niet geslaagd.")


def _guard_sole_household_files(conn: Connection, hid: str) -> None:
    """Fail closed if any persisted receipt content would outlive the account."""
    if not hid or Path(hid).name != hid or hid in {".", "..", "0"}:
        raise AccountDeletionConflictError("Ongeldige huishoudenidentiteit bij bestandscontrole.")
    receipt_root = Path(os.getenv("RECEIPT_STORAGE_ROOT", "/app/data/receipts/raw"))
    dirs = (receipt_root / hid, receipt_root.parent / "sources" / hid)
    for directory in dirs:
        try:
            if directory.exists() and any(path.is_file() for path in directory.rglob("*")):
                raise AccountDeletionConflictError(
                    "Dit huishouden bevat nog kassabon- of bronbestanden; volledige "
                    "bestandsverwijdering moet eerst veilig worden afgehandeld."
                )
        except OSError as exc:
            raise AccountDeletionConflictError(
                "Bestandsopslag kon niet volledig worden gecontroleerd; verwijderen gestopt."
            ) from exc
    # Unknown paths in the receipts table are also unsafe even when not on disk.
    raw_cols = _columns(conn, "raw_receipts")
    if {"household_id", "storage_path"}.issubset(raw_cols):
        if conn.execute(text("""
            SELECT 1 FROM raw_receipts
            WHERE CAST(household_id AS TEXT)=:hid
              AND storage_path IS NOT NULL AND trim(storage_path)<>''
            LIMIT 1
        """), {"hid": hid}).first():
            raise AccountDeletionConflictError(
                "Dit huishouden bevat nog fysieke kassabonbestanden; volledige verwijdering "
                "is nog niet veilig ondersteund. Er is niets verwijderd."
            )



def _delete_sole_household(conn: Connection, hid: str, *, staged_files: frozenset[str]) -> None:
    if hid not in staged_files:
        _guard_sole_household_files(conn, hid)
    reset_household_data(conn, hid, confirmation=f"RESET {hid}")
    conn.execute(text("""
        UPDATE server_sessions SET active_household_id=NULL
        WHERE CAST(active_household_id AS TEXT)=:hid
    """), {"hid": hid})
    conn.execute(text(
        "DELETE FROM auth_membership_permission_overrides WHERE CAST(household_id AS TEXT)=:hid"
    ), {"hid": hid})
    for table in ("auth_membership_roles", "household_memberships"):
        conn.execute(text(f"DELETE FROM {table} WHERE CAST(household_id AS TEXT)=:hid"), {"hid": hid})
    if conn.execute(text("DELETE FROM household_registry WHERE CAST(id AS TEXT)=:hid"), {"hid": hid}).rowcount != 1:
        raise AccountDeletionConflictError("Huishoudidentiteit kon niet worden verwijderd.")
    if _columns(conn, "households"):
        conn.execute(text("DELETE FROM households WHERE CAST(id AS TEXT)=:hid"), {"hid": hid})


def _purge_personal_references(conn: Connection, uid: str, email: str) -> None:
    """Delete per-user rows, detach shared objects, fail on unrecognized user links."""
    tables = set(inspect(conn).get_table_names())
    processed: dict[str, set[str]] = {}
    quote = conn.dialect.identifier_preparer.quote

    def change(table: str, column: str, action: str, name_column: str | None = None) -> None:
        if table not in tables or column not in _columns(conn, table):
            return
        processed.setdefault(table, set()).add(column)
        qt, qc = quote(table), quote(column)
        params = {"uid": uid, "deleted": DELETED_IDENTITY}
        if action == "delete":
            sql = f"DELETE FROM {qt} WHERE CAST({qc} AS TEXT)=:uid"
        elif action == "unlink":
            col_info = next(c for c in inspect(conn).get_columns(table) if c["name"] == column)
            if not col_info["nullable"]:
                raise AccountDeletionConflictError(f"{table}.{column} kan niet veilig worden ontkoppeld.")
            sql = f"UPDATE {qt} SET {qc}=NULL WHERE CAST({qc} AS TEXT)=:uid"
        else:
            sql = f"UPDATE {qt} SET {qc}=:deleted WHERE CAST({qc} AS TEXT)=:uid"
        conn.execute(text(sql), params)
        if name_column and name_column in _columns(conn, table):
            conn.execute(text(
                f"UPDATE {qt} SET {quote(name_column)}='Verwijderde gebruiker' WHERE {qc}=:deleted"
            ), params)

    # Requests for unknown/legacy addresses may have a null user_id, but
    # still retain a deterministic hash of this account's email address.
    if "account_password_reset_tokens" in tables:
        conn.execute(text("""
            DELETE FROM account_password_reset_tokens
            WHERE request_email_hash=:email_hash
        """), {"email_hash": hashlib.sha256(email.encode("utf-8")).hexdigest()})

    for table, column in (
        ("account_password_reset_tokens", "user_id"),
        ("server_sessions", "user_id"),
        ("auth_platform_user_roles", "user_id"),
        ("frontteam_memberships", "user_id"),
        ("auth_support_access_grants", "support_user_id"),
        ("support_recipients", "admin_user_id"),
        ("household_notifications", "recipient_user_id"),
        ("actor_object_attributions", "actor_user_id"),
    ):
        change(table, column, "delete")
    change("household_residents", "linked_user_id", "unlink")
    change("support_threads", "created_by_user_id", "redact", "created_by_name")
    change("support_messages", "sender_user_id", "redact", "sender_name")
    change("household_invitations", "created_by_user_id", "redact")
    change("household_invitations", "accepted_by_user_id", "redact")
    change("household_invitations", "last_delivery_actor_user_id", "redact")
    change("auth_audit_log", "actor_user_id", "redact")

    if "household_invitations" in tables:
        conn.execute(text(
            "DELETE FROM household_invitations WHERE lower(trim(invitee_email))=:email"
        ), {"email": email})
        processed.setdefault("household_invitations", set()).add("invitee_email")
    if "auth_audit_log" in tables:
        cols = _columns(conn, "auth_audit_log")
        if "object_id" in cols:
            conn.execute(text("""
                UPDATE auth_audit_log SET object_id=:deleted
                WHERE CAST(object_id AS TEXT)=:uid OR lower(trim(CAST(object_id AS TEXT)))=:email
            """), {"deleted": DELETED_IDENTITY, "uid": uid, "email": email})
        for col in ("old_value", "new_value", "reason", "ticket_reference"):
            if col in cols:
                value = "'{}'" if col in {"old_value", "new_value"} else "NULL"
                conn.execute(text(
                    f"UPDATE auth_audit_log SET {quote(col)}={value} WHERE actor_user_id=:deleted"
                ), {"deleted": DELETED_IDENTITY})

    for table in sorted(tables - {"app_users", "household_memberships"}):
        for col in _columns(conn, table):
            if col in processed.get(table, set()):
                continue
            if col == "user_id" or col.endswith("_user_id"):
                found = conn.execute(text(
                    f"SELECT 1 FROM {quote(table)} WHERE CAST({quote(col)} AS TEXT)=:uid LIMIT 1"
                ), {"uid": uid}).first()
                if found:
                    raise AccountDeletionConflictError(
                        f"{table}.{col} verwijst nog naar dit account; niets is verwijderd."
                    )


def delete_consumer_account(
    conn: Connection, *, user_id: str, current_password: str, confirmation: str,
    file_stage: HouseholdFileStage | None = None,
) -> dict[str, int | bool]:
    if confirmation != CONFIRMATION:
        raise AccountDeletionConflictError(f"Typ ter bevestiging exact: {CONFIRMATION}")
    if conn.dialect.name != "postgresql":
        raise AccountDeletionConflictError("Accountverwijdering vereist PostgreSQL.")
    uid = str(user_id or "").strip()
    user = _account(conn, uid, lock=True)
    if not verify_password(user["password"], current_password, stored_password_hash=user["password_hash"]):
        raise AccountDeletionPasswordError("Het huidige wachtwoord is onjuist.")
    plan = deletion_preview(conn, user_id=uid)
    email = str(user["email"]).strip().lower()

    # Lock all households and re-check before any mutation (supports multiple households).
    for item in plan["households"]:
        conn.execute(text(
            "SELECT id FROM household_registry WHERE id=:hid FOR UPDATE"
        ), {"hid": item["household_id"]}).one()
    if deletion_preview(conn, user_id=uid) != plan:
        raise AccountDeletionConflictError("Huishoudleden veranderden tijdens het verzoek.")

    sole_ids = [str(item["household_id"]) for item in plan["households"] if item["delete_household"]]
    if file_stage is not None:
        file_stage.stage(conn, sole_ids)
    staged_files = file_stage.household_ids if file_stage is not None else frozenset()
    for item in plan["households"]:
        hid, mid = item["household_id"], item["membership_id"]
        if item["delete_household"]:
            _delete_sole_household(conn, hid, staged_files=staged_files)
        else:
            _promote_successor(conn, hid, item["successor_membership_id"])
            for table in ("auth_membership_permission_overrides", "auth_membership_roles"):
                conn.execute(text(
                    f"DELETE FROM {table} WHERE household_id=:hid AND membership_id=:mid"
                ), {"hid": hid, "mid": mid})
            if conn.execute(text("""
                DELETE FROM household_memberships WHERE household_id=:hid AND id=:mid
            """), {"hid": hid, "mid": mid}).rowcount != 1:
                raise AccountDeletionConflictError("Lidmaatschap kon niet worden verwijderd.")
    _purge_personal_references(conn, uid, email)
    member_cols = _required_columns(conn, "household_memberships", {"user_email"})
    member_predicate = ("CAST(user_id AS TEXT)=:uid OR " if "user_id" in member_cols else "") + "lower(trim(user_email))=:email"
    if conn.execute(text(f"""
        SELECT 1 FROM household_memberships
        WHERE {member_predicate} LIMIT 1
    """), {"uid": uid, "email": email}).first():
        raise AccountDeletionConflictError("Er zijn nog lidmaatschappen aan dit account gekoppeld.")
    if conn.execute(text("DELETE FROM app_users WHERE id=:uid"), {"uid": uid}).rowcount != 1:
        raise AccountDeletionConflictError("Account kon niet worden verwijderd.")
    return {
        "deleted": True,
        "households_deleted": plan["households_to_delete"],
        "households_preserved": plan["households_to_keep"],
        "admins_transferred": sum(bool(p["successor_membership_id"]) for p in plan["households"]),
    }

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import inspect, text


STATUS_OPEN = "Open"
STATUS_IN_PROGRESS = "In behandeling"
STATUS_CLOSED = "Gesloten"
ALLOWED_STATUSES = frozenset({STATUS_OPEN, STATUS_IN_PROGRESS, STATUS_CLOSED})

RECIPIENT_SUPERUSER = "superuser"
RECIPIENT_SINGLE_ADMIN = "single_household_admin"
RECIPIENT_ALL_ADMINS = "all_household_admins"
ALLOWED_RECIPIENT_TYPES = frozenset({
    RECIPIENT_SUPERUSER,
    RECIPIENT_SINGLE_ADMIN,
    RECIPIENT_ALL_ADMINS,
})

_SUPPORT_REQUIRED_COLUMNS = {
    "support_threads": {
        "id", "thread_number", "household_id", "created_by_user_id",
        "created_by_name", "subject", "origin_screen_name", "origin_route",
        "origin_app_version", "status", "reply_allowed", "recipient_type",
        "created_at", "updated_at", "closed_at",
    },
    "support_messages": {
        "id", "thread_id", "sender_user_id", "sender_name", "sender_role",
        "message_text", "created_at",
    },
    "support_recipients": {
        "id", "thread_id", "household_id", "admin_user_id", "read_at", "created_at",
    },
}
_SUPPORT_REQUIRED_INDEXES = {
    "support_threads": {
        "idx_support_threads_household_updated": ("household_id", "updated_at"),
        "idx_support_threads_status_updated": ("status", "updated_at"),
    },
    "support_messages": {
        "idx_support_messages_thread_created": ("thread_id", "created_at"),
    },
    "support_recipients": {
        "idx_support_recipients_admin": ("admin_user_id", "read_at"),
    },
}
_POSTGRES_TIMESTAMP_COLUMNS = {
    "support_threads": ("created_at", "updated_at", "closed_at"),
    "support_messages": ("created_at",),
    "support_recipients": ("read_at", "created_at"),
}


class SupportMessageError(RuntimeError):
    pass


@dataclass(frozen=True)
class SupportThreadResult:
    thread_id: str
    thread_number: str
    status: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_required(value: str | None, label: str, *, maximum: int) -> str:
    normalized = " ".join(str(value or "").strip().split())
    if not normalized:
        raise SupportMessageError(f"{label} is verplicht")
    if len(normalized) > maximum:
        raise SupportMessageError(f"{label} is langer dan {maximum} tekens")
    return normalized


def _clean_message(value: str | None) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise SupportMessageError("Bericht is verplicht")
    if len(normalized) > 10000:
        raise SupportMessageError("Bericht is langer dan 10000 tekens")
    return normalized


def _has_unique(inspector, table_name: str, expected: tuple[str, ...]) -> bool:
    unique_sets = {
        tuple(item.get("column_names") or ())
        for item in inspector.get_unique_constraints(table_name)
    }
    unique_sets.update(
        tuple(item.get("column_names") or ())
        for item in inspector.get_indexes(table_name)
        if bool(item.get("unique"))
    )
    return expected in unique_sets


def ensure_support_message_foundation(conn) -> None:
    """Validate the Alembic-owned support persistence schema without DDL."""

    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    missing_tables = sorted(set(_SUPPORT_REQUIRED_COLUMNS) - tables)
    if missing_tables:
        raise RuntimeError(
            "Canonical support persistence schema ontbreekt: " + ", ".join(missing_tables)
        )

    column_maps = {}
    for table_name, required_columns in _SUPPORT_REQUIRED_COLUMNS.items():
        columns = {
            str(column.get("name") or ""): column
            for column in inspector.get_columns(table_name)
        }
        column_maps[table_name] = columns
        missing_columns = sorted(required_columns - set(columns))
        if missing_columns:
            raise RuntimeError(
                f"{table_name} schema drift; ontbrekende kolommen: "
                + ", ".join(missing_columns)
            )
        primary_key = tuple(
            inspector.get_pk_constraint(table_name).get("constrained_columns") or ()
        )
        if primary_key != ("id",):
            raise RuntimeError(
                f"{table_name} schema drift; onjuiste primary key: {primary_key!r}"
            )

    if not _has_unique(inspector, "support_threads", ("thread_number",)):
        raise RuntimeError("support_threads.thread_number moet uniek zijn")
    if not _has_unique(
        inspector,
        "support_recipients",
        ("thread_id", "household_id", "admin_user_id"),
    ):
        raise RuntimeError("support_recipients mist canonical recipient uniqueness")

    for table_name, expected_indexes in _SUPPORT_REQUIRED_INDEXES.items():
        indexes = {
            str(index.get("name") or ""): index
            for index in inspector.get_indexes(table_name)
        }
        for index_name, expected_columns in expected_indexes.items():
            index = indexes.get(index_name)
            actual_columns = tuple((index or {}).get("column_names") or ())
            if index is None or bool(index.get("unique")) or actual_columns != expected_columns:
                raise RuntimeError(
                    f"Canonical support index {index_name} wijkt af: "
                    f"expected={expected_columns!r} actual={actual_columns!r}"
                )

    if conn.dialect.name == "postgresql":
        if not isinstance(column_maps["support_threads"]["reply_allowed"]["type"], sa.Boolean):
            raise RuntimeError("support_threads.reply_allowed moet PostgreSQL BOOLEAN zijn")
        for table_name, timestamp_columns in _POSTGRES_TIMESTAMP_COLUMNS.items():
            for column_name in timestamp_columns:
                column_type = column_maps[table_name][column_name]["type"]
                if not isinstance(column_type, sa.DateTime) or not bool(
                    getattr(column_type, "timezone", False)
                ):
                    raise RuntimeError(
                        f"{table_name}.{column_name} moet PostgreSQL TIMESTAMPTZ zijn"
                    )


def _next_thread_number(conn) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"M-{today}-"
    last_number = conn.execute(text("""
        SELECT thread_number
        FROM support_threads
        WHERE thread_number LIKE :prefix
        ORDER BY thread_number DESC
        LIMIT 1
    """), {"prefix": f"{prefix}%"}).scalar()
    sequence = int(str(last_number).rsplit("-", 1)[-1]) + 1 if last_number else 1
    return f"{prefix}{sequence:04d}"


def create_support_thread(
    conn,
    *,
    created_by_user_id: str,
    created_by_name: str,
    sender_role: str,
    subject: str,
    message_text: str,
    origin_screen_name: str,
    household_id: str | None,
    recipient_type: str = RECIPIENT_SUPERUSER,
    reply_allowed: bool = True,
    origin_route: str | None = None,
    origin_app_version: str | None = None,
) -> SupportThreadResult:
    ensure_support_message_foundation(conn)
    user_id = _clean_required(created_by_user_id, "Gebruikers-ID", maximum=200)
    name = _clean_required(created_by_name, "Naam", maximum=200)
    role = _clean_required(sender_role, "Rol", maximum=100)
    clean_subject = _clean_required(subject, "Onderwerp", maximum=250)
    clean_screen = _clean_required(origin_screen_name, "Schermnaam", maximum=200)
    clean_message = _clean_message(message_text)
    if recipient_type not in ALLOWED_RECIPIENT_TYPES:
        raise SupportMessageError("Onbekend ontvangertype")
    if recipient_type == RECIPIENT_SUPERUSER and household_id is None:
        raise SupportMessageError("Een huishoudmelding vereist een huishouden")

    thread_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    thread_number = _next_thread_number(conn)
    now = _now_iso()
    conn.execute(text("""
        INSERT INTO support_threads(
            id, thread_number, household_id, created_by_user_id, created_by_name,
            subject, origin_screen_name, origin_route, origin_app_version,
            status, reply_allowed, recipient_type, created_at, updated_at
        ) VALUES (
            :id, :thread_number, :household_id, :created_by_user_id, :created_by_name,
            :subject, :origin_screen_name, :origin_route, :origin_app_version,
            :status, :reply_allowed, :recipient_type, :created_at, :updated_at
        )
    """), {
        "id": thread_id,
        "thread_number": thread_number,
        "household_id": str(household_id) if household_id is not None else None,
        "created_by_user_id": user_id,
        "created_by_name": name,
        "subject": clean_subject,
        "origin_screen_name": clean_screen,
        "origin_route": str(origin_route or "").strip() or None,
        "origin_app_version": str(origin_app_version or "").strip() or None,
        "status": STATUS_OPEN,
        "reply_allowed": bool(reply_allowed),
        "recipient_type": recipient_type,
        "created_at": now,
        "updated_at": now,
    })
    conn.execute(text("""
        INSERT INTO support_messages(
            id, thread_id, sender_user_id, sender_name, sender_role, message_text, created_at
        ) VALUES (
            :id, :thread_id, :sender_user_id, :sender_name, :sender_role, :message_text, :created_at
        )
    """), {
        "id": message_id,
        "thread_id": thread_id,
        "sender_user_id": user_id,
        "sender_name": name,
        "sender_role": role,
        "message_text": clean_message,
        "created_at": now,
    })
    return SupportThreadResult(thread_id, thread_number, STATUS_OPEN)


def add_support_message(
    conn,
    *,
    thread_id: str,
    sender_user_id: str,
    sender_name: str,
    sender_role: str,
    message_text: str,
    is_superuser: bool,
    household_id: str | None = None,
) -> str:
    ensure_support_message_foundation(conn)
    thread = conn.execute(text("""
        SELECT id, household_id, reply_allowed
        FROM support_threads
        WHERE id = :thread_id
        LIMIT 1
    """), {"thread_id": str(thread_id)}).mappings().first()
    if not thread:
        raise SupportMessageError("Melding niet gevonden")
    if not is_superuser:
        if str(thread["household_id"] or "") != str(household_id or ""):
            raise SupportMessageError("Melding behoort niet tot het actieve huishouden")
        if not bool(thread["reply_allowed"]):
            raise SupportMessageError("Reageren op deze melding is niet toegestaan")

    message_id = str(uuid.uuid4())
    now = _now_iso()
    conn.execute(text("""
        INSERT INTO support_messages(
            id, thread_id, sender_user_id, sender_name, sender_role, message_text, created_at
        ) VALUES (
            :id, :thread_id, :sender_user_id, :sender_name, :sender_role, :message_text, :created_at
        )
    """), {
        "id": message_id,
        "thread_id": str(thread_id),
        "sender_user_id": _clean_required(sender_user_id, "Gebruikers-ID", maximum=200),
        "sender_name": _clean_required(sender_name, "Naam", maximum=200),
        "sender_role": _clean_required(sender_role, "Rol", maximum=100),
        "message_text": _clean_message(message_text),
        "created_at": now,
    })
    conn.execute(text("UPDATE support_threads SET updated_at = :updated_at WHERE id = :id"), {
        "updated_at": now,
        "id": str(thread_id),
    })
    return message_id


def set_support_thread_status(conn, *, thread_id: str, status: str) -> None:
    ensure_support_message_foundation(conn)
    if status not in ALLOWED_STATUSES:
        raise SupportMessageError("Onbekende status")
    now = _now_iso()
    result = conn.execute(text("""
        UPDATE support_threads
        SET status = :status,
            updated_at = :updated_at,
            closed_at = CASE WHEN :status = 'Gesloten' THEN :updated_at ELSE NULL END
        WHERE id = :thread_id
    """), {"status": status, "updated_at": now, "thread_id": str(thread_id)})
    if result.rowcount != 1:
        raise SupportMessageError("Melding niet gevonden")


def add_support_recipient(conn, *, thread_id: str, household_id: str, admin_user_id: str) -> None:
    ensure_support_message_foundation(conn)
    now = _now_iso()
    conn.execute(text("""
        INSERT INTO support_recipients(id, thread_id, household_id, admin_user_id, created_at)
        VALUES (:id, :thread_id, :household_id, :admin_user_id, :created_at)
        ON CONFLICT(thread_id, household_id, admin_user_id) DO NOTHING
    """), {
        "id": str(uuid.uuid4()),
        "thread_id": str(thread_id),
        "household_id": str(household_id),
        "admin_user_id": str(admin_user_id),
        "created_at": now,
    })


def list_support_threads(conn, *, household_id: str | None = None, status: str | None = None):
    ensure_support_message_foundation(conn)
    clauses = []
    params = {}
    if household_id is not None:
        clauses.append("t.household_id = :household_id")
        params["household_id"] = str(household_id)
    if status is not None:
        if status not in ALLOWED_STATUSES:
            raise SupportMessageError("Onbekende status")
        clauses.append("t.status = :status")
        params["status"] = status
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
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
        {where}
        GROUP BY t.id
        ORDER BY t.updated_at DESC, t.thread_number DESC
    """), params).mappings().all()


def list_support_messages(conn, *, thread_id: str, household_id: str | None = None, is_superuser: bool = False):
    ensure_support_message_foundation(conn)
    thread = conn.execute(text("SELECT household_id FROM support_threads WHERE id = :id"), {
        "id": str(thread_id),
    }).mappings().first()
    if not thread:
        raise SupportMessageError("Melding niet gevonden")
    if not is_superuser and str(thread["household_id"] or "") != str(household_id or ""):
        raise SupportMessageError("Melding behoort niet tot het actieve huishouden")
    return conn.execute(text("""
        SELECT id, thread_id, sender_user_id, sender_name, sender_role, message_text, created_at
        FROM support_messages
        WHERE thread_id = :thread_id
        ORDER BY created_at, id
    """), {"thread_id": str(thread_id)}).mappings().all()


def export_support_threads_csv(conn, *, status: str | None = None) -> str:
    rows = list_support_threads(conn, status=status)
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

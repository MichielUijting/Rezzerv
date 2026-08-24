from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import html
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from app.services.authorization_foundation_service import write_authorization_audit
from app.services.email_config_service import (
    RESEND_API_BASE_URL,
    RESEND_API_KEY,
    REZZERV_APP_BASE_URL,
    REZZERV_EMAIL_ENABLED,
    REZZERV_NOTIFICATION_FROM_EMAIL,
    REZZERV_NOTIFICATION_FROM_NAME,
)
from app.services.household_invitation_service import (
    DEFAULT_INVITATION_TTL,
    INVITATION_STATUS_PENDING,
    InvitationConflictError,
    InvitationNotFoundError,
    ensure_household_invitation_foundation,
    hash_invitation_token,
    list_household_invitations,
    new_invitation_token,
    utc_now,
)

DELIVERY_STATUS_NOT_SENT = "not_sent"
DELIVERY_STATUS_SENT = "sent"
DELIVERY_STATUS_FAILED = "failed"
DELIVERY_STATUS_DISABLED = "disabled"
DELIVERY_STATUS_CONFIG_INVALID = "config_invalid"
DELIVERY_STATUSES = frozenset(
    {
        DELIVERY_STATUS_NOT_SENT,
        DELIVERY_STATUS_SENT,
        DELIVERY_STATUS_FAILED,
        DELIVERY_STATUS_DISABLED,
        DELIVERY_STATUS_CONFIG_INVALID,
    }
)


@dataclass(frozen=True)
class InvitationEmailConfiguration:
    enabled: bool
    api_key: str
    api_base_url: str
    from_email: str
    from_name: str
    app_base_url: str


@dataclass(frozen=True)
class InvitationDeliveryResult:
    status: str
    message: str
    provider_message_id: str | None = None

    def public_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "message": self.message,
            "provider_message_id": self.provider_message_id,
        }


class InvitationDeliveryTransportError(RuntimeError):
    pass


InvitationEmailTransport = Callable[[dict[str, object], InvitationEmailConfiguration], str | None]


def default_invitation_email_configuration() -> InvitationEmailConfiguration:
    return InvitationEmailConfiguration(
        enabled=bool(REZZERV_EMAIL_ENABLED),
        api_key=str(RESEND_API_KEY or "").strip(),
        api_base_url=str(RESEND_API_BASE_URL or "").rstrip("/"),
        from_email=str(REZZERV_NOTIFICATION_FROM_EMAIL or "").strip(),
        from_name=str(REZZERV_NOTIFICATION_FROM_NAME or "Rezzerv").strip() or "Rezzerv",
        app_base_url=str(REZZERV_APP_BASE_URL or "").rstrip("/"),
    )


def _iso(value: datetime) -> str:
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return normalized.astimezone(timezone.utc).isoformat()


def ensure_household_invitation_delivery_foundation(conn: Connection) -> None:
    """Add I.3 delivery metadata without rewriting the I.1 lifecycle table."""

    ensure_household_invitation_foundation(conn)
    columns = {
        str(column.get("name") or "").strip().lower()
        for column in inspect(conn).get_columns("household_invitations")
    }
    additions = (
        ("delivery_status", "TEXT NOT NULL DEFAULT 'not_sent'"),
        ("delivery_attempt_count", "INTEGER NOT NULL DEFAULT 0"),
        ("last_delivery_attempt_at", "TEXT"),
        ("last_delivered_at", "TEXT"),
        ("last_delivery_error", "TEXT"),
        ("delivery_provider_message_id", "TEXT"),
        ("last_delivery_actor_user_id", "TEXT"),
    )
    for column_name, definition in additions:
        if column_name not in columns:
            conn.execute(text(f"ALTER TABLE household_invitations ADD COLUMN {column_name} {definition}"))
            columns.add(column_name)


def _configuration_problem(configuration: InvitationEmailConfiguration) -> tuple[str | None, str | None]:
    if not configuration.enabled:
        return DELIVERY_STATUS_DISABLED, "Uitnodigingsmail is uitgeschakeld."
    api_key = str(configuration.api_key or "").strip()
    if not api_key or api_key.upper().startswith("PASTE_"):
        return DELIVERY_STATUS_CONFIG_INVALID, "Uitnodigingsmail niet verzonden: Resend API-sleutel ontbreekt."
    from_email = str(configuration.from_email or "").strip().lower()
    if "@" not in from_email or from_email.endswith(".local"):
        return DELIVERY_STATUS_CONFIG_INVALID, "Uitnodigingsmail niet verzonden: afzenderadres is niet bruikbaar voor Resend."
    app_base_url = str(configuration.app_base_url or "").strip()
    if not app_base_url.startswith(("https://", "http://")):
        return DELIVERY_STATUS_CONFIG_INVALID, "Uitnodigingsmail niet verzonden: app-url ontbreekt of is ongeldig."
    if app_base_url.startswith(("http://localhost", "https://localhost", "http://127.0.0.1", "https://127.0.0.1")):
        return DELIVERY_STATUS_CONFIG_INVALID, "Uitnodigingsmail niet verzonden: app-url verwijst nog naar localhost."
    return None, None


def _default_resend_transport(
    payload: dict[str, object],
    configuration: InvitationEmailConfiguration,
) -> str | None:
    endpoint = f"{configuration.api_base_url.rstrip('/')}/emails"
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {configuration.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15.0) as response:
            body = response.read().decode("utf-8", errors="replace")
            parsed = json.loads(body or "{}") if body else {}
            provider_id = str(parsed.get("id") or "").strip() if isinstance(parsed, dict) else ""
            return provider_id or None
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
            parsed = json.loads(body or "{}")
            detail = str(
                parsed.get("message")
                or parsed.get("error")
                or parsed.get("detail")
                or "Resend heeft de uitnodigingsmail geweigerd."
            ).strip()
        except Exception:
            detail = "Resend heeft de uitnodigingsmail geweigerd."
        raise InvitationDeliveryTransportError(
            f"Resend antwoordde met HTTP {exc.code}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise InvitationDeliveryTransportError("Resend is momenteel niet bereikbaar.") from exc


def build_invitation_email_payload(
    *,
    recipient_email: str,
    household_name: str,
    raw_token: str,
    expires_at: str,
    configuration: InvitationEmailConfiguration,
) -> dict[str, object]:
    normalized_email = str(recipient_email or "").strip().lower()
    normalized_household_name = str(household_name or "").strip() or "je huishouden"
    token = str(raw_token or "").strip()
    if not normalized_email or not token:
        raise ValueError("Ontvanger en uitnodigingstoken zijn verplicht")
    invitation_url = (
        f"{configuration.app_base_url.rstrip('/')}/uitnodiging/"
        f"{urllib.parse.quote(token, safe='')}"
    )
    subject = f"Je bent uitgenodigd voor {normalized_household_name}"
    text_body = "\n".join(
        [
            "Je bent uitgenodigd voor Inhuis.",
            f"Huishouden: {normalized_household_name}",
            "Rol: Lid",
            "",
            "Accepteer de uitnodiging via deze veilige link:",
            invitation_url,
            "",
            f"Deze uitnodiging is geldig tot {expires_at} en kan eerder worden ingetrokken of vervangen.",
            "Heb je al een account? Log in met het uitgenodigde e-mailadres. Anders kun je via de link een account maken.",
            "",
            "Inhuis vraagt nooit om een wachtwoord per e-mail.",
        ]
    )
    safe_household = html.escape(normalized_household_name)
    safe_url = html.escape(invitation_url, quote=True)
    safe_expires = html.escape(str(expires_at or ""))
    html_body = (
        "<p>Je bent uitgenodigd voor <strong>Inhuis</strong>.</p>"
        f"<p>Huishouden: <strong>{safe_household}</strong><br>Rol: <strong>Lid</strong></p>"
        f'<p><a href="{safe_url}">Uitnodiging accepteren</a></p>'
        f"<p>Deze uitnodiging is geldig tot {safe_expires} en kan eerder worden ingetrokken of vervangen.</p>"
        "<p>Heb je al een account? Log in met het uitgenodigde e-mailadres. Anders kun je via de link een account maken.</p>"
        "<p>Inhuis vraagt nooit om een wachtwoord per e-mail.</p>"
    )
    from_value = str(configuration.from_email or "").strip()
    if configuration.from_name:
        from_value = f"{configuration.from_name} <{from_value}>"
    return {
        "from": from_value,
        "to": [normalized_email],
        "subject": subject,
        "html": html_body,
        "text": text_body,
    }


def _redact_token(value: object, raw_token: str) -> str:
    message = str(value or "").strip()
    token = str(raw_token or "").strip()
    if not token:
        return message
    encoded = urllib.parse.quote(token, safe="")
    return message.replace(token, "[redacted]").replace(encoded, "[redacted]")


def send_household_invitation_email(
    *,
    recipient_email: str,
    household_name: str,
    raw_token: str,
    expires_at: str,
    configuration: InvitationEmailConfiguration | None = None,
    transport: InvitationEmailTransport | None = None,
) -> InvitationDeliveryResult:
    config = configuration or default_invitation_email_configuration()
    problem_status, problem_message = _configuration_problem(config)
    if problem_status:
        return InvitationDeliveryResult(problem_status, str(problem_message or "Uitnodigingsmail niet verzonden."))
    payload = build_invitation_email_payload(
        recipient_email=recipient_email,
        household_name=household_name,
        raw_token=raw_token,
        expires_at=expires_at,
        configuration=config,
    )
    sender = transport or _default_resend_transport
    try:
        provider_message_id = sender(payload, config)
    except InvitationDeliveryTransportError as exc:
        return InvitationDeliveryResult(
            DELIVERY_STATUS_FAILED,
            _redact_token(exc, raw_token) or "Uitnodigingsmail niet verzonden.",
        )
    except Exception:
        return InvitationDeliveryResult(
            DELIVERY_STATUS_FAILED,
            "Uitnodigingsmail niet verzonden door een onverwachte transportfout.",
        )
    return InvitationDeliveryResult(
        DELIVERY_STATUS_SENT,
        f"Uitnodigingsmail verzonden naar {str(recipient_email or '').strip().lower()}.",
        str(provider_message_id).strip() if provider_message_id else None,
    )


def _household_name(conn: Connection, household_id: str) -> str:
    row = conn.execute(
        text("SELECT naam FROM household_registry WHERE id = :household_id LIMIT 1"),
        {"household_id": str(household_id)},
    ).mappings().first()
    return str(row.get("naam") or "").strip() if row else ""


def _stored_invitation_row(conn: Connection, household_id: str, invitation_id: str):
    return conn.execute(
        text(
            """
            SELECT * FROM household_invitations
            WHERE id = :invitation_id AND household_id = :household_id
            LIMIT 1
            """
        ),
        {"invitation_id": str(invitation_id), "household_id": str(household_id)},
    ).mappings().first()


def _delivery_metadata(row) -> dict[str, object]:
    return {
        "delivery_status": str(row.get("delivery_status") or DELIVERY_STATUS_NOT_SENT),
        "delivery_attempt_count": int(row.get("delivery_attempt_count") or 0),
        "last_delivery_attempt_at": row.get("last_delivery_attempt_at"),
        "last_delivered_at": row.get("last_delivered_at"),
        "last_delivery_error": row.get("last_delivery_error"),
        "delivery_provider_message_id": row.get("delivery_provider_message_id"),
        "last_delivery_actor_user_id": row.get("last_delivery_actor_user_id"),
    }


def get_household_invitation_with_delivery(
    conn: Connection,
    *,
    household_id: str,
    invitation_id: str,
    now: datetime | None = None,
) -> dict[str, object]:
    ensure_household_invitation_delivery_foundation(conn)
    items = list_household_invitations(conn, household_id=household_id, now=now)
    invitation = next((item for item in items if str(item.get("id")) == str(invitation_id)), None)
    if not invitation:
        raise InvitationNotFoundError("Uitnodiging niet gevonden")
    row = _stored_invitation_row(conn, household_id, invitation_id)
    if not row:
        raise InvitationNotFoundError("Uitnodiging niet gevonden")
    return {**invitation, **_delivery_metadata(row)}


def list_household_invitations_with_delivery(
    conn: Connection,
    *,
    household_id: str,
    now: datetime | None = None,
) -> list[dict[str, object]]:
    ensure_household_invitation_delivery_foundation(conn)
    items = list_household_invitations(conn, household_id=household_id, now=now)
    enriched: list[dict[str, object]] = []
    for invitation in items:
        row = _stored_invitation_row(conn, household_id, str(invitation.get("id") or ""))
        enriched.append({**invitation, **(_delivery_metadata(row) if row else {})})
    return enriched


def _record_delivery_attempt(
    conn: Connection,
    *,
    household_id: str,
    invitation_id: str,
    actor_user_id: str,
    result: InvitationDeliveryResult,
    attempted_at: str,
) -> None:
    sent = result.status == DELIVERY_STATUS_SENT
    conn.execute(
        text(
            """
            UPDATE household_invitations
            SET delivery_status = :delivery_status,
                delivery_attempt_count = COALESCE(delivery_attempt_count, 0) + 1,
                last_delivery_attempt_at = :attempted_at,
                last_delivered_at = CASE WHEN :sent = 1 THEN :attempted_at ELSE last_delivered_at END,
                last_delivery_error = CASE WHEN :sent = 1 THEN NULL ELSE :delivery_error END,
                delivery_provider_message_id = CASE
                    WHEN :sent = 1 THEN :provider_message_id
                    ELSE delivery_provider_message_id
                END,
                last_delivery_actor_user_id = :actor_user_id,
                updated_at = :attempted_at
            WHERE id = :invitation_id AND household_id = :household_id
            """
        ),
        {
            "delivery_status": result.status,
            "attempted_at": attempted_at,
            "sent": 1 if sent else 0,
            "delivery_error": None if sent else result.message,
            "provider_message_id": result.provider_message_id,
            "actor_user_id": str(actor_user_id),
            "invitation_id": str(invitation_id),
            "household_id": str(household_id),
        },
    )
    write_authorization_audit(
        conn,
        actor_user_id=str(actor_user_id),
        actor_type="household_member",
        household_id=str(household_id),
        action="household.invitation.delivery_attempted",
        object_type="household_invitation",
        object_id=str(invitation_id),
        new_value={
            "delivery_status": result.status,
            "provider_message_id": result.provider_message_id,
        },
    )


def deliver_created_household_invitation(
    conn: Connection,
    *,
    household_id: str,
    invitation_id: str,
    raw_token: str,
    actor_user_id: str,
    configuration: InvitationEmailConfiguration | None = None,
    transport: InvitationEmailTransport | None = None,
    now: datetime | None = None,
) -> InvitationDeliveryResult:
    ensure_household_invitation_delivery_foundation(conn)
    invitation = get_household_invitation_with_delivery(
        conn,
        household_id=household_id,
        invitation_id=invitation_id,
        now=now,
    )
    if invitation["status"] != INVITATION_STATUS_PENDING:
        raise InvitationConflictError("Alleen een open uitnodiging kan worden verzonden")
    result = send_household_invitation_email(
        recipient_email=str(invitation["invitee_email"]),
        household_name=_household_name(conn, household_id),
        raw_token=raw_token,
        expires_at=str(invitation["expires_at"] or ""),
        configuration=configuration,
        transport=transport,
    )
    attempted_at = _iso(now or utc_now())
    _record_delivery_attempt(
        conn,
        household_id=household_id,
        invitation_id=invitation_id,
        actor_user_id=actor_user_id,
        result=result,
        attempted_at=attempted_at,
    )
    return result


def resend_household_invitation(
    conn: Connection,
    *,
    household_id: str,
    invitation_id: str,
    actor_user_id: str,
    configuration: InvitationEmailConfiguration | None = None,
    transport: InvitationEmailTransport | None = None,
    now: datetime | None = None,
) -> tuple[dict[str, object], InvitationDeliveryResult]:
    ensure_household_invitation_delivery_foundation(conn)
    current_time = now or utc_now()
    invitation = get_household_invitation_with_delivery(
        conn,
        household_id=household_id,
        invitation_id=invitation_id,
        now=current_time,
    )
    if invitation["status"] != INVITATION_STATUS_PENDING:
        raise InvitationConflictError(
            f"Alleen een open uitnodiging kan opnieuw worden verzonden; huidige status is {invitation['status']}"
        )
    stored = _stored_invitation_row(conn, household_id, invitation_id)
    if not stored:
        raise InvitationNotFoundError("Uitnodiging niet gevonden")

    new_raw_token = new_invitation_token()
    new_token_hash = hash_invitation_token(new_raw_token)
    new_expires_at = _iso(current_time + DEFAULT_INVITATION_TTL)
    result = send_household_invitation_email(
        recipient_email=str(invitation["invitee_email"]),
        household_name=_household_name(conn, household_id),
        raw_token=new_raw_token,
        expires_at=new_expires_at,
        configuration=configuration,
        transport=transport,
    )
    attempted_at = _iso(current_time)
    if result.status == DELIVERY_STATUS_SENT:
        update = conn.execute(
            text(
                """
                UPDATE household_invitations
                SET token_hash = :new_token_hash,
                    expires_at = :new_expires_at,
                    updated_at = :attempted_at
                WHERE id = :invitation_id
                  AND household_id = :household_id
                  AND status = 'pending'
                  AND token_hash = :old_token_hash
                """
            ),
            {
                "new_token_hash": new_token_hash,
                "new_expires_at": new_expires_at,
                "attempted_at": attempted_at,
                "invitation_id": str(invitation_id),
                "household_id": str(household_id),
                "old_token_hash": str(stored.get("token_hash") or ""),
            },
        )
        if int(update.rowcount or 0) != 1:
            raise InvitationConflictError("Uitnodiging wijzigde tijdens opnieuw verzenden")
        write_authorization_audit(
            conn,
            actor_user_id=str(actor_user_id),
            actor_type="household_member",
            household_id=str(household_id),
            action="household.invitation.token_rotated",
            object_type="household_invitation",
            object_id=str(invitation_id),
            old_value={"expires_at": invitation.get("expires_at")},
            new_value={"expires_at": new_expires_at},
        )

    _record_delivery_attempt(
        conn,
        household_id=household_id,
        invitation_id=invitation_id,
        actor_user_id=actor_user_id,
        result=result,
        attempted_at=attempted_at,
    )
    refreshed = get_household_invitation_with_delivery(
        conn,
        household_id=household_id,
        invitation_id=invitation_id,
        now=current_time,
    )
    return refreshed, result

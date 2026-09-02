from __future__ import annotations

from dataclasses import dataclass
import html
import json
import logging
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.services.email_config_service import (
    RESEND_API_BASE_URL,
    RESEND_API_KEY,
    REZZERV_APP_BASE_URL,
    REZZERV_NOTIFICATION_FROM_EMAIL,
    REZZERV_NOTIFICATION_FROM_NAME,
    outbound_email_delivery_enabled,
    outbound_email_sender_ready,
    resend_api_key_ready,
)


logger = logging.getLogger(__name__)

_PASSWORD_RESET_SUBJECT = "Stel je Inhuis-wachtwoord opnieuw in"
_PASSWORD_CHANGED_SUBJECT = "Je Inhuis-wachtwoord is gewijzigd"


@dataclass(frozen=True)
class PasswordResetDeliveryResult:
    sent: bool
    status: str


def _redact(value: Any, *secrets: str) -> str:
    message = str(value or "")
    for secret in secrets:
        normalized = str(secret or "")
        if not normalized:
            continue
        message = message.replace(normalized, "[REDACTED]")
        encoded = quote(normalized, safe="")
        if encoded:
            message = message.replace(encoded, "[REDACTED]")
    return message


def _sender_value() -> str:
    name = str(REZZERV_NOTIFICATION_FROM_NAME or "Rezzerv").strip() or "Rezzerv"
    address = str(REZZERV_NOTIFICATION_FROM_EMAIL or "").strip()
    return f"{name} <{address}>"


def _post_resend_message(*, recipient: str, subject: str, text_body: str, html_body: str) -> PasswordResetDeliveryResult:
    if not outbound_email_delivery_enabled():
        return PasswordResetDeliveryResult(sent=False, status="disabled")
    if not resend_api_key_ready():
        return PasswordResetDeliveryResult(sent=False, status="api_key_unavailable")
    sender_ready, _reason = outbound_email_sender_ready()
    if not sender_ready:
        return PasswordResetDeliveryResult(sent=False, status="sender_unavailable")

    payload = json.dumps(
        {
            "from": _sender_value(),
            "to": [str(recipient or "").strip()],
            "subject": subject,
            "text": text_body,
            "html": html_body,
        }
    ).encode("utf-8")
    request = Request(
        f"{RESEND_API_BASE_URL}/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "Rezzerv-Backend/Password-Recovery",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            status_code = int(getattr(response, "status", 200) or 200)
            if 200 <= status_code < 300:
                return PasswordResetDeliveryResult(sent=True, status="sent")
            logger.warning("Password-recovery e-mail delivery failed with HTTP %s", status_code)
            return PasswordResetDeliveryResult(sent=False, status="provider_rejected")
    except HTTPError as exc:
        logger.warning("Password-recovery e-mail delivery failed with HTTP %s", int(exc.code or 0))
        return PasswordResetDeliveryResult(sent=False, status="provider_rejected")
    except URLError:
        logger.warning("Password-recovery e-mail delivery failed because the provider was unreachable")
        return PasswordResetDeliveryResult(sent=False, status="provider_unreachable")
    except Exception as exc:  # pragma: no cover - defensive transport boundary
        logger.warning(
            "Password-recovery e-mail delivery failed: %s",
            _redact(type(exc).__name__),
        )
        return PasswordResetDeliveryResult(sent=False, status="delivery_error")


def build_password_reset_url(raw_token: str) -> str:
    token = str(raw_token or "").strip()
    if not token:
        raise ValueError("Password-reset token ontbreekt")
    return f"{REZZERV_APP_BASE_URL}/wachtwoord-herstellen#token={quote(token, safe='')}"


def deliver_password_reset_email(*, email: str, raw_token: str) -> PasswordResetDeliveryResult:
    """Deliver a single-use reset link without ever logging or persisting the raw token here."""
    reset_url = build_password_reset_url(raw_token)
    text_body = (
        "We hebben een verzoek ontvangen om het wachtwoord van je Inhuis-account opnieuw in te stellen.\n\n"
        "Open de onderstaande link om een nieuw wachtwoord te kiezen:\n"
        f"{reset_url}\n\n"
        "Deze link is 30 minuten geldig en kan één keer worden gebruikt.\n"
        "Heb je dit niet aangevraagd? Dan hoef je niets te doen. Je huidige wachtwoord blijft ongewijzigd."
    )
    escaped_url = html.escape(reset_url, quote=True)
    html_body = (
        "<p>We hebben een verzoek ontvangen om het wachtwoord van je Inhuis-account opnieuw in te stellen.</p>"
        f'<p><a href="{escaped_url}">Wachtwoord opnieuw instellen</a></p>'
        "<p>Deze link is 30 minuten geldig en kan één keer worden gebruikt.</p>"
        "<p>Heb je dit niet aangevraagd? Dan hoef je niets te doen. Je huidige wachtwoord blijft ongewijzigd.</p>"
    )
    result = _post_resend_message(
        recipient=email,
        subject=_PASSWORD_RESET_SUBJECT,
        text_body=text_body,
        html_body=html_body,
    )
    # Never include reset_url/raw_token in logging, including error paths.
    if not result.sent:
        logger.info("Password-recovery e-mail was not delivered; status=%s", result.status)
    return result


def deliver_password_changed_email(*, email: str) -> PasswordResetDeliveryResult:
    text_body = (
        "Het wachtwoord van je Inhuis-account is gewijzigd.\n\n"
        "Alle bestaande sessies zijn beëindigd. Log opnieuw in met je nieuwe wachtwoord.\n\n"
        "Heb je deze wijziging niet uitgevoerd? Neem dan direct contact op met ondersteuning."
    )
    html_body = (
        "<p>Het wachtwoord van je Inhuis-account is gewijzigd.</p>"
        "<p>Alle bestaande sessies zijn beëindigd. Log opnieuw in met je nieuwe wachtwoord.</p>"
        "<p>Heb je deze wijziging niet uitgevoerd? Neem dan direct contact op met ondersteuning.</p>"
    )
    return _post_resend_message(
        recipient=email,
        subject=_PASSWORD_CHANGED_SUBJECT,
        text_body=text_body,
        html_body=html_body,
    )

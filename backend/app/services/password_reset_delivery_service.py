from __future__ import annotations

from dataclasses import dataclass
import html
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from app.services.email_config_service import (
    RESEND_API_BASE_URL,
    RESEND_API_KEY,
    REZZERV_APP_BASE_URL,
    REZZERV_EMAIL_ENABLED,
    REZZERV_NOTIFICATION_FROM_EMAIL,
    REZZERV_NOTIFICATION_FROM_NAME,
)


@dataclass(frozen=True)
class PasswordResetEmailConfiguration:
    enabled: bool
    api_key: str
    api_base_url: str
    from_email: str
    from_name: str
    app_base_url: str


@dataclass(frozen=True)
class PasswordResetDeliveryResult:
    sent: bool
    message: str
    provider_message_id: str | None = None


PasswordResetEmailTransport = Callable[
    [dict[str, object], PasswordResetEmailConfiguration],
    str | None,
]


def default_password_reset_email_configuration() -> PasswordResetEmailConfiguration:
    return PasswordResetEmailConfiguration(
        enabled=bool(REZZERV_EMAIL_ENABLED),
        api_key=str(RESEND_API_KEY or "").strip(),
        api_base_url=str(RESEND_API_BASE_URL or "").rstrip("/"),
        from_email=str(REZZERV_NOTIFICATION_FROM_EMAIL or "").strip(),
        from_name=str(REZZERV_NOTIFICATION_FROM_NAME or "Rezzerv").strip() or "Rezzerv",
        app_base_url=str(REZZERV_APP_BASE_URL or "").rstrip("/"),
    )


def _configuration_problem(configuration: PasswordResetEmailConfiguration) -> str | None:
    if not configuration.enabled:
        return "E-mailverzending is uitgeschakeld."
    api_key = str(configuration.api_key or "").strip()
    if not api_key or api_key.upper().startswith("PASTE_"):
        return "Resend API-sleutel ontbreekt."
    from_email = str(configuration.from_email or "").strip().lower()
    if "@" not in from_email or from_email.endswith(".local"):
        return "Afzenderadres is niet bruikbaar voor Resend."
    app_base_url = str(configuration.app_base_url or "").strip()
    if not app_base_url.startswith("https://"):
        return "Wachtwoordherstel vereist een publieke HTTPS app-url."
    return None


def _default_resend_transport(
    payload: dict[str, object],
    configuration: PasswordResetEmailConfiguration,
) -> str | None:
    request = urllib.request.Request(
        f"{configuration.api_base_url.rstrip('/')}/emails",
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
        raise RuntimeError(f"Resend weigerde het verzoek met HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("Resend is momenteel niet bereikbaar.") from exc


def _from_value(configuration: PasswordResetEmailConfiguration) -> str:
    value = str(configuration.from_email or "").strip()
    return f"{configuration.from_name} <{value}>" if configuration.from_name else value


def _redact_token(message: object, raw_token: str) -> str:
    result = str(message or "").strip()
    token = str(raw_token or "").strip()
    if not token:
        return result
    encoded = urllib.parse.quote(token, safe="")
    return result.replace(token, "[redacted]").replace(encoded, "[redacted]")


def build_password_reset_email_payload(
    *,
    recipient_email: str,
    raw_token: str,
    configuration: PasswordResetEmailConfiguration,
) -> dict[str, object]:
    token = str(raw_token or "").strip()
    if not token:
        raise ValueError("Reset-token ontbreekt")
    reset_url = (
        f"{configuration.app_base_url.rstrip('/')}/wachtwoord-herstellen"
        f"#token={urllib.parse.quote(token, safe='')}"
    )
    safe_url = html.escape(reset_url, quote=True)
    text_body = "\n".join(
        [
            "We hebben een verzoek ontvangen om het wachtwoord van je Inhuis-account opnieuw in te stellen.",
            "",
            "Kies via deze beveiligde link een nieuw wachtwoord:",
            reset_url,
            "",
            "Deze link is 30 minuten geldig en kan één keer worden gebruikt.",
            "Heb je dit niet aangevraagd? Dan hoef je niets te doen; je huidige wachtwoord blijft ongewijzigd.",
            "",
            "Inhuis vraagt nooit om je wachtwoord per e-mail.",
        ]
    )
    html_body = (
        "<p>We hebben een verzoek ontvangen om het wachtwoord van je <strong>Inhuis</strong>-account opnieuw in te stellen.</p>"
        f'<p><a href="{safe_url}">Wachtwoord opnieuw instellen</a></p>'
        "<p>Deze link is 30 minuten geldig en kan één keer worden gebruikt.</p>"
        "<p>Heb je dit niet aangevraagd? Dan hoef je niets te doen; je huidige wachtwoord blijft ongewijzigd.</p>"
        "<p>Inhuis vraagt nooit om je wachtwoord per e-mail.</p>"
    )
    return {
        "from": _from_value(configuration),
        "to": [str(recipient_email or "").strip().lower()],
        "subject": "Stel je Inhuis-wachtwoord opnieuw in",
        "html": html_body,
        "text": text_body,
    }


def build_password_changed_email_payload(
    *,
    recipient_email: str,
    configuration: PasswordResetEmailConfiguration,
) -> dict[str, object]:
    text_body = "\n".join(
        [
            "Het wachtwoord van je Inhuis-account is gewijzigd.",
            "Alle bestaande sessies zijn beëindigd.",
            "",
            "Heb je dit niet zelf gedaan? Neem dan direct contact op met Inhuis-support.",
        ]
    )
    html_body = (
        "<p>Het wachtwoord van je <strong>Inhuis</strong>-account is gewijzigd.</p>"
        "<p>Alle bestaande sessies zijn beëindigd.</p>"
        "<p>Heb je dit niet zelf gedaan? Neem dan direct contact op met Inhuis-support.</p>"
    )
    return {
        "from": _from_value(configuration),
        "to": [str(recipient_email or "").strip().lower()],
        "subject": "Je Inhuis-wachtwoord is gewijzigd",
        "html": html_body,
        "text": text_body,
    }


def _send_payload(
    payload: dict[str, object],
    configuration: PasswordResetEmailConfiguration,
    transport: PasswordResetEmailTransport | None,
    *,
    raw_token: str = "",
) -> PasswordResetDeliveryResult:
    problem = _configuration_problem(configuration)
    if problem:
        return PasswordResetDeliveryResult(False, problem)
    sender = transport or _default_resend_transport
    try:
        provider_id = sender(payload, configuration)
    except Exception as exc:
        return PasswordResetDeliveryResult(
            False,
            _redact_token(exc, raw_token) or "E-mailverzending is mislukt.",
        )
    return PasswordResetDeliveryResult(
        True,
        "E-mail verzonden.",
        str(provider_id).strip() if provider_id else None,
    )


def send_password_reset_email(
    *,
    recipient_email: str,
    raw_token: str,
    configuration: PasswordResetEmailConfiguration | None = None,
    transport: PasswordResetEmailTransport | None = None,
) -> PasswordResetDeliveryResult:
    config = configuration or default_password_reset_email_configuration()
    payload = build_password_reset_email_payload(
        recipient_email=recipient_email,
        raw_token=raw_token,
        configuration=config,
    )
    return _send_payload(payload, config, transport, raw_token=raw_token)


def send_password_changed_email(
    *,
    recipient_email: str,
    configuration: PasswordResetEmailConfiguration | None = None,
    transport: PasswordResetEmailTransport | None = None,
) -> PasswordResetDeliveryResult:
    config = configuration or default_password_reset_email_configuration()
    payload = build_password_changed_email_payload(
        recipient_email=recipient_email,
        configuration=config,
    )
    return _send_payload(payload, config, transport)

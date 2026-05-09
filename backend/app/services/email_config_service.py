from __future__ import annotations

import hmac
import os
from typing import Any


GMAIL_OAUTH_CLIENT_ID = os.getenv('REZZERV_GMAIL_CLIENT_ID', '').strip()
GMAIL_OAUTH_CLIENT_SECRET = os.getenv('REZZERV_GMAIL_CLIENT_SECRET', '').strip()
GMAIL_OAUTH_REDIRECT_URI = os.getenv('REZZERV_GMAIL_REDIRECT_URI', '').strip()
GMAIL_OAUTH_SCOPES = tuple(
    scope.strip()
    for scope in os.getenv(
        'REZZERV_GMAIL_SCOPES',
        'https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.labels',
    ).split()
    if scope.strip()
)
GMAIL_STATE_SECRET = (os.getenv('REZZERV_GMAIL_STATE_SECRET', 'rezzerv-gmail-dev-secret') or 'rezzerv-gmail-dev-secret').encode('utf-8')
GMAIL_DEFAULT_LABEL_NAME = os.getenv('REZZERV_GMAIL_LABEL_NAME', 'Rezzerv/Bonnen').strip() or 'Rezzerv/Bonnen'
GMAIL_SYNC_BATCH_SIZE = max(1, min(int(os.getenv('REZZERV_GMAIL_SYNC_BATCH_SIZE', '25') or '25'), 100))
RECEIPT_EMAIL_DOMAIN = (os.getenv('REZZERV_RECEIPT_EMAIL_DOMAIN', 'rezzerv.local') or 'rezzerv.local').strip() or 'rezzerv.local'
RESEND_API_KEY = (os.getenv('REZZERV_RESEND_API_KEY', '') or '').strip()
RESEND_API_BASE_URL = (os.getenv('REZZERV_RESEND_API_BASE_URL', 'https://api.resend.com') or 'https://api.resend.com').rstrip('/')
REZZERV_NOTIFICATION_FROM_EMAIL = (os.getenv('REZZERV_NOTIFICATION_FROM_EMAIL', '') or '').strip()
REZZERV_NOTIFICATION_FROM_NAME = (os.getenv('REZZERV_NOTIFICATION_FROM_NAME', 'Rezzerv') or 'Rezzerv').strip() or 'Rezzerv'
REZZERV_APP_BASE_URL = (os.getenv('REZZERV_APP_BASE_URL', 'http://localhost:5174') or 'http://localhost:5174').rstrip('/')
REZZERV_EMAIL_ENABLED = str(os.getenv('REZZERV_EMAIL_ENABLED', 'false') or 'false').strip().lower() in {'1', 'true', 'yes', 'on'}


def mask_secret(value: Any, visible_suffix: int = 4) -> str:
    secret = str(value or '').strip()
    if not secret:
        return 'ontbreekt'
    if len(secret) <= visible_suffix:
        return '*' * len(secret)
    return ('*' * max(0, len(secret) - visible_suffix)) + secret[-visible_suffix:]


def normalize_api_error_message(value: Any, fallback: str = 'Verzoek mislukt') -> str:
    if value is None:
        return fallback
    message = str(value).strip()
    return message or fallback


def outbound_email_delivery_enabled() -> bool:
    return bool(REZZERV_EMAIL_ENABLED)


def resend_api_key_ready() -> bool:
    key = str(RESEND_API_KEY or '').strip()
    return bool(key) and not key.upper().startswith('PASTE_')


def outbound_email_sender_ready() -> tuple[bool, str]:
    from_email = str(REZZERV_NOTIFICATION_FROM_EMAIL or '').strip().lower()
    if not from_email:
        return False, 'afzenderadres ontbreekt'
    if '@' not in from_email:
        return False, 'afzenderadres is ongeldig'
    if from_email.endswith('.local'):
        return False, 'afzenderadres gebruikt nog een .local-domein en is daarom niet bruikbaar voor Resend'
    return True, ''


def build_outbound_email_configuration_warnings() -> list[str]:
    warnings: list[str] = []
    from_email = str(REZZERV_NOTIFICATION_FROM_EMAIL or '').strip().lower()
    app_base_url = str(REZZERV_APP_BASE_URL or '').strip()
    if not from_email or '@' not in from_email:
        warnings.append('afzenderadres ontbreekt of is ongeldig')
    elif from_email.endswith('.local'):
        warnings.append('afzenderadres gebruikt nog een .local-domein en is meestal niet bruikbaar voor Resend')
    if app_base_url.startswith('http://localhost'):
        warnings.append('app-url verwijst nog naar localhost')
    return warnings


def build_outbound_email_configuration_summary() -> str:
    warnings = build_outbound_email_configuration_warnings()
    email_state = 'ingeschakeld' if outbound_email_delivery_enabled() else 'uitgeschakeld'
    key_state = 'aanwezig' if resend_api_key_ready() else 'ontbreekt of placeholder'
    summary_parts = [
        f'e-mail: {email_state}',
        f'API-sleutel: {key_state} ({mask_secret(RESEND_API_KEY)})',
        f"afzender: {REZZERV_NOTIFICATION_FROM_EMAIL or '(niet ingesteld)'}",
        f'api: {RESEND_API_BASE_URL}/emails',
        f'app-url: {REZZERV_APP_BASE_URL}/login',
    ]
    if warnings:
        summary_parts.append('waarschuwingen: ' + '; '.join(warnings))
    return 'Configuratie: ' + ' | '.join(summary_parts)


def build_resend_error_message(status_code: int, reason: Any, external_detail: Any = None, headers: Any = None) -> str:
    normalized_detail = normalize_api_error_message(external_detail, 'Onbekende fout vanuit Resend.')
    request_id = ''
    cf_ray = ''
    server_header = ''
    if headers is not None:
        try:
            request_id = str(headers.get('x-request-id') or headers.get('X-Request-Id') or '').strip()
        except Exception:
            request_id = ''
        try:
            cf_ray = str(headers.get('cf-ray') or headers.get('CF-RAY') or '').strip()
        except Exception:
            cf_ray = ''
        try:
            server_header = str(headers.get('server') or headers.get('Server') or '').strip()
        except Exception:
            server_header = ''
    reason_text = str(reason or "").strip()
    detail_parts = [
        'Uitnodigingsmail niet verzonden.',
        f'Resend antwoordde met HTTP {status_code} {reason_text}.' if reason_text else f'Resend antwoordde met HTTP {status_code}.',
        f'Externe melding: {normalized_detail}',
        build_outbound_email_configuration_summary(),
    ]
    if request_id:
        detail_parts.append(f'Resend request-id: {request_id}')
    if cf_ray:
        detail_parts.append(f'Cloudflare-ray: {cf_ray}')
    if server_header:
        detail_parts.append(f'Server: {server_header}')
    if "browser's signature" in normalized_detail.lower():
        detail_parts.append('Diagnosehint: Resend of een tussenliggende beveiligingslaag blokkeert dit verzoek als verdacht browser/signature-verkeer. Controleer of het afzenderadres een geverifieerd domein gebruikt, of de API-sleutel in de backend-container actief is, en of firewall, proxy, VPN, adblocker of browserbeveiliging verkeer naar api.resend.com wijzigt.')
    return ' '.join(part for part in detail_parts if part)

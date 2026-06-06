"""
Technical Design Reference:
- TD Section: TD-05 Datastore en services
- Module Role: Backend application module
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request

from app.services.email_config_service import (
    GMAIL_DEFAULT_LABEL_NAME,
    GMAIL_OAUTH_CLIENT_ID,
    GMAIL_OAUTH_CLIENT_SECRET,
    GMAIL_OAUTH_REDIRECT_URI,
    GMAIL_OAUTH_SCOPES,
    GMAIL_STATE_SECRET,
)


def gmail_is_configured() -> bool:
    return bool(GMAIL_OAUTH_CLIENT_ID and GMAIL_OAUTH_CLIENT_SECRET)


def resolve_gmail_redirect_uri(request: Request | None = None) -> str:
    if GMAIL_OAUTH_REDIRECT_URI:
        return GMAIL_OAUTH_REDIRECT_URI
    if request is None:
        raise HTTPException(status_code=503, detail='De Gmail redirect-URI is nog niet geconfigureerd.')
    return f"{str(request.base_url).rstrip('/')}/api/receipts/gmail/callback"


def sign_gmail_state(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    signature = hmac.new(GMAIL_STATE_SECRET, serialized, hashlib.sha256).hexdigest()
    return f"{signature}.{serialized.decode('utf-8')}"


def verify_gmail_state(state_token: str) -> dict[str, Any]:
    token = str(state_token or '').strip()
    if not token or '.' not in token:
        raise HTTPException(status_code=400, detail='Ongeldige Gmail-state ontvangen.')
    signature, serialized_text = token.split('.', 1)
    try:
        serialized = serialized_text.encode('utf-8')
        payload = json.loads(serialized_text)
    except Exception as exc:
        raise HTTPException(status_code=400, detail='Gmail-state kon niet worden gelezen.') from exc
    expected_signature = hmac.new(GMAIL_STATE_SECRET, serialized, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=400, detail='Gmail-state is ongeldig of verlopen.')
    try:
        if str(payload.get('provider') or '') != 'gmail':
            raise ValueError('provider mismatch')
    except Exception as exc:
        raise HTTPException(status_code=400, detail='Gmail-state bevat ongeldige gegevens.') from exc
    return payload


def gmail_datetime_from_timestamp(value: Any) -> str | None:
    if value in (None, ''):
        return None
    try:
        numeric_value = float(value)
    except Exception:
        return None
    if numeric_value > 100000000000:
        numeric_value = numeric_value / 1000.0
    try:
        return datetime.fromtimestamp(numeric_value, tz=timezone.utc).isoformat()
    except Exception:
        return None


def parse_gmail_token_expiry(expires_in: Any) -> str | None:
    try:
        seconds = int(expires_in or 0)
    except Exception:
        seconds = 0
    if seconds <= 0:
        return None
    return (datetime.now(timezone.utc) + timedelta(seconds=max(0, seconds - 60))).isoformat()


def get_gmail_default_label_name() -> str:
    return GMAIL_DEFAULT_LABEL_NAME


def get_gmail_oauth_scopes() -> tuple[str, ...]:
    return GMAIL_OAUTH_SCOPES

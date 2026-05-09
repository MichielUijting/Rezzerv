from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Optional

from fastapi import HTTPException

from app.services.email_config_service import (
    GMAIL_DEFAULT_LABEL_NAME,
    GMAIL_OAUTH_CLIENT_ID,
    GMAIL_OAUTH_CLIENT_SECRET,
    GMAIL_SYNC_BATCH_SIZE,
    normalize_api_error_message,
)
from app.services.receipt_gmail_helper_service import (
    gmail_datetime_from_timestamp,
    parse_gmail_token_expiry,
)

_engine = None
_logger = None
_text = None
_upsert_receipt_gmail_account: Callable[..., dict[str, Any]] | None = None
_get_receipt_gmail_account: Callable[..., dict[str, Any]] | None = None
_store_gmail_import_result: Callable[..., Any] | None = None
_import_email_receipt_payload: Callable[..., dict[str, Any]] | None = None
_has_processed_gmail_message: Callable[..., bool] | None = None
_ensure_household_gmail_source: Callable[..., dict[str, Any]] | None = None


def configure_gmail_sync_service(
    *,
    engine,
    logger,
    text,
    upsert_receipt_gmail_account: Callable[..., dict[str, Any]],
    get_receipt_gmail_account: Callable[..., dict[str, Any]],
    store_gmail_import_result: Callable[..., Any],
    import_email_receipt_payload: Callable[..., dict[str, Any]],
    has_processed_gmail_message: Callable[..., bool],
    ensure_household_gmail_source: Callable[..., dict[str, Any]],
) -> None:
    global _engine
    global _logger
    global _text
    global _upsert_receipt_gmail_account
    global _get_receipt_gmail_account
    global _store_gmail_import_result
    global _import_email_receipt_payload
    global _has_processed_gmail_message
    global _ensure_household_gmail_source

    _engine = engine
    _logger = logger
    _text = text
    _upsert_receipt_gmail_account = upsert_receipt_gmail_account
    _get_receipt_gmail_account = get_receipt_gmail_account
    _store_gmail_import_result = store_gmail_import_result
    _import_email_receipt_payload = import_email_receipt_payload
    _has_processed_gmail_message = has_processed_gmail_message
    _ensure_household_gmail_source = ensure_household_gmail_source


def _require_configured():
    if (
        _logger is None
        or _upsert_receipt_gmail_account is None
        or _get_receipt_gmail_account is None
        or _store_gmail_import_result is None
        or _import_email_receipt_payload is None
        or _has_processed_gmail_message is None
        or _ensure_household_gmail_source is None
    ):
        raise RuntimeError('gmail_sync_service is niet geconfigureerd')



def gmail_json_request(url: str, method: str = 'GET', *, headers: Optional[dict[str, str]] = None, data: Any = None, timeout: float = 30.0) -> dict[str, Any]:
    request_headers = {'Accept': 'application/json', **(headers or {})}
    payload = None
    if data is not None:
        payload = json.dumps(data).encode('utf-8')
        request_headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(url, data=payload, headers=request_headers, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode('utf-8')
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = None
        try:
            detail_body = exc.read().decode('utf-8')
            detail = json.loads(detail_body) if detail_body else None
        except Exception:
            detail = None
        raise HTTPException(status_code=502, detail=f'Gmail-API fout: {normalize_api_error_message(detail, exc.reason)}') from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=f'Gmail-API is niet bereikbaar: {exc.reason}') from exc



def gmail_form_request(url: str, data: dict[str, Any]) -> dict[str, Any]:
    encoded = urllib.parse.urlencode(data).encode('utf-8')
    request = urllib.request.Request(
        url,
        data=encoded,
        headers={'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=30.0) as response:
            body = response.read().decode('utf-8')
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = None
        try:
            detail_body = exc.read().decode('utf-8')
            detail = json.loads(detail_body) if detail_body else None
        except Exception:
            detail = None
        raise HTTPException(status_code=502, detail=f'Gmail OAuth fout: {normalize_api_error_message(detail, exc.reason)}') from exc



def exchange_gmail_code_for_tokens(code: str, redirect_uri: str) -> dict[str, Any]:
    return gmail_form_request(
        'https://oauth2.googleapis.com/token',
        {
            'client_id': GMAIL_OAUTH_CLIENT_ID,
            'client_secret': GMAIL_OAUTH_CLIENT_SECRET,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri,
        },
    )

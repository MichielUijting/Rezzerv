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


def _require_configured() -> None:
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


def refresh_gmail_access_token(account: dict[str, Any]) -> dict[str, Any]:
    _require_configured()
    refresh_token = str(account.get('refresh_token') or '').strip()
    if not refresh_token:
        raise HTTPException(status_code=400, detail='Deze Gmail-koppeling heeft geen refresh-token. Koppel Gmail opnieuw.')
    tokens = gmail_form_request(
        'https://oauth2.googleapis.com/token',
        {
            'client_id': GMAIL_OAUTH_CLIENT_ID,
            'client_secret': GMAIL_OAUTH_CLIENT_SECRET,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token',
        },
    )
    return _upsert_receipt_gmail_account(
        account['household_id'],
        {
            'access_token': tokens.get('access_token'),
            'token_expires_at': parse_gmail_token_expiry(tokens.get('expires_in')),
            'sync_status': 'connected',
            'last_error': None,
        },
    )


def get_valid_gmail_access_token(account: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    token = str(account.get('access_token') or '').strip()
    expires_at = gmail_datetime_from_timestamp(account.get('token_expires_at'))
    expired = True
    if expires_at:
        try:
            from datetime import datetime, timezone
            expires_dt = datetime.fromisoformat(str(expires_at).replace('Z', '+00:00'))
            if expires_dt.tzinfo is None:
                expires_dt = expires_dt.replace(tzinfo=timezone.utc)
            expired = expires_dt <= datetime.now(timezone.utc)
        except Exception:
            expired = True
    if token and not expired:
        return token, account
    refreshed = refresh_gmail_access_token(account)
    refreshed_token = str(refreshed.get('access_token') or '').strip()
    if not refreshed_token:
        raise HTTPException(status_code=400, detail='De Gmail access-token ontbreekt na verversen. Koppel Gmail opnieuw.')
    return refreshed_token, refreshed


def gmail_api_request(account: dict[str, Any], path: str, *, method: str = 'GET', params: Optional[dict[str, Any]] = None, data: Any = None, retry_on_unauthorized: bool = True) -> tuple[dict[str, Any], dict[str, Any]]:
    token, current_account = get_valid_gmail_access_token(account)
    url = f"https://gmail.googleapis.com/gmail/v1/{path.lstrip('/')}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params, doseq=True)}"
    try:
        response = gmail_json_request(url, method=method, headers={'Authorization': f'Bearer {token}'}, data=data)
        return response, current_account
    except HTTPException as exc:
        if retry_on_unauthorized and exc.status_code == 502 and '401' in str(exc.detail):
            refreshed = refresh_gmail_access_token(current_account)
            return gmail_api_request(refreshed, path, method=method, params=params, data=data, retry_on_unauthorized=False)
        raise


def gmail_get_profile(account: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    return gmail_api_request(account, 'users/me/profile')


def ensure_gmail_label(account: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    _require_configured()
    label_name = str(account.get('label_name') or GMAIL_DEFAULT_LABEL_NAME).strip() or GMAIL_DEFAULT_LABEL_NAME
    labels_payload, current_account = gmail_api_request(account, 'users/me/labels')
    for label in labels_payload.get('labels') or []:
        if str(label.get('name') or '').strip() == label_name:
            label_id = str(label.get('id') or '').strip()
            updated = _upsert_receipt_gmail_account(current_account['household_id'], {'label_name': label_name, 'label_id': label_id})
            return label_id, updated
    created_label, updated_account = gmail_api_request(
        current_account,
        'users/me/labels',
        method='POST',
        data={'name': label_name, 'labelListVisibility': 'labelShow', 'messageListVisibility': 'show'},
    )
    label_id = str(created_label.get('id') or '').strip()
    if not label_id:
        raise HTTPException(status_code=502, detail='Gmail-label kon niet worden aangemaakt.')
    updated = _upsert_receipt_gmail_account(updated_account['household_id'], {'label_name': label_name, 'label_id': label_id})
    return label_id, updated


def decode_gmail_raw_message(raw_value: str) -> bytes:
    value = str(raw_value or '').strip()
    if not value:
        raise ValueError('De Gmail-API gaf geen ruwe e-mailinhoud terug.')
    padding = '=' * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(f'{value}{padding}'.encode('ascii'))
    except Exception as exc:
        raise ValueError('De Gmail-API gaf ongeldige e-mailinhoud terug.') from exc


def sync_gmail_receipts(household_id: str) -> dict[str, Any]:
    _require_configured()
    effective_household_id = str(household_id or '1').strip() or '1'
    account = _get_receipt_gmail_account(effective_household_id, create_if_missing=True)
    if not GMAIL_OAUTH_CLIENT_ID or not GMAIL_OAUTH_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail='De Gmail-koppeling is nog niet geconfigureerd in Rezzerv.')
    if not str(account.get('refresh_token') or '').strip():
        raise HTTPException(status_code=400, detail='Gmail is nog niet gekoppeld voor dit huishouden.')

    label_id, account = ensure_gmail_label(account)
    messages_payload, account = gmail_api_request(
        account,
        'users/me/messages',
        params={'labelIds': [label_id], 'maxResults': GMAIL_SYNC_BATCH_SIZE},
    )
    messages = messages_payload.get('messages') or []
    imported = []
    skipped = []
    failed = []

    for message_item in messages:
        gmail_message_id = str(message_item.get('id') or '').strip()
        if not gmail_message_id:
            continue
        if _has_processed_gmail_message(effective_household_id, gmail_message_id):
            skipped.append({'gmail_message_id': gmail_message_id, 'reason': 'already_processed'})
            continue
        try:
            gmail_message_payload, account = gmail_api_request(
                account,
                f'users/me/messages/{urllib.parse.quote(gmail_message_id)}',
                params={'format': 'raw'},
            )
            email_bytes = decode_gmail_raw_message(str(gmail_message_payload.get('raw') or ''))
            result = _import_email_receipt_payload(
                effective_household_id,
                email_bytes,
                fallback_filename=f'gmail-{gmail_message_id}.eml',
                source_id=account.get('source_id'),
            )
            _store_gmail_import_result(
                effective_household_id,
                gmail_message_id,
                {
                    'gmail_thread_id': gmail_message_payload.get('threadId'),
                    'gmail_history_id': gmail_message_payload.get('historyId'),
                    'gmail_internal_date': gmail_datetime_from_timestamp(gmail_message_payload.get('internalDate')),
                    'import_status': 'imported',
                    'raw_receipt_id': result.get('raw_receipt_id'),
                    'receipt_table_id': result.get('receipt_table_id'),
                    'error_message': None,
                },
            )
            imported.append({'gmail_message_id': gmail_message_id, 'result': result})
        except Exception as exc:
            error_message = normalize_api_error_message(str(exc) or 'Gmail-bericht kon niet worden geïmporteerd')
            _store_gmail_import_result(
                effective_household_id,
                gmail_message_id,
                {
                    'gmail_thread_id': message_item.get('threadId'),
                    'gmail_history_id': message_item.get('historyId'),
                    'gmail_internal_date': gmail_datetime_from_timestamp(message_item.get('internalDate')),
                    'import_status': 'failed',
                    'raw_receipt_id': None,
                    'receipt_table_id': None,
                    'error_message': error_message,
                },
            )
            failed.append({'gmail_message_id': gmail_message_id, 'error': error_message})

    _upsert_receipt_gmail_account(
        effective_household_id,
        {
            'label_name': account.get('label_name') or GMAIL_DEFAULT_LABEL_NAME,
            'label_id': label_id,
            'sync_status': 'connected',
            'last_error': None if not failed else failed[-1].get('error'),
        },
    )
    return {
        'household_id': effective_household_id,
        'label_id': label_id,
        'label_name': account.get('label_name') or GMAIL_DEFAULT_LABEL_NAME,
        'scanned': len(messages),
        'imported_count': len(imported),
        'skipped_count': len(skipped),
        'failed_count': len(failed),
        'imported': imported,
        'skipped': skipped,
        'failed': failed,
    }

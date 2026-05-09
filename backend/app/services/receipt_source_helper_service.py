from __future__ import annotations

import re
from typing import Any, Callable

from fastapi import HTTPException

from app.services.email_config_service import RECEIPT_EMAIL_DOMAIN

_engine = None
_text = None
_normalize_household_id: Callable[[Any], str] | None = None
_serialize_receipt_source: Callable[[Any], dict[str, Any]] | None = None


def configure_receipt_source_helper_service(
    *,
    engine,
    text,
    normalize_household_id: Callable[[Any], str],
    serialize_receipt_source: Callable[[Any], dict[str, Any]],
) -> None:
    """Configure dependencies supplied by main.py.

    This keeps source-helper extraction non-functional: the SQL, table names,
    source IDs and returned payloads remain equivalent while avoiding imports
    from app.main.
    """
    global _engine
    global _text
    global _normalize_household_id
    global _serialize_receipt_source

    _engine = engine
    _text = text
    _normalize_household_id = normalize_household_id
    _serialize_receipt_source = serialize_receipt_source


def _require_configured() -> tuple[object, Callable, Callable[[Any], str], Callable[[Any], dict[str, Any]]]:
    if _engine is None or _text is None or _normalize_household_id is None or _serialize_receipt_source is None:
        raise RuntimeError('Receipt source helper service is niet geconfigureerd')
    return _engine, _text, _normalize_household_id, _serialize_receipt_source


def is_public_receipt_email_domain(domain: str) -> bool:
    normalized = str(domain or '').strip().lower()
    if not normalized:
        return False
    if normalized in {'localhost', 'rezzerv.local'}:
        return False
    if normalized.endswith('.local'):
        return False
    if normalized.endswith('.test'):
        return False
    return '.' in normalized


def build_household_email_address(household_id: str) -> str:
    _, _, normalize_household_id, _ = _require_configured()
    normalized_household_id = re.sub(r'[^a-zA-Z0-9_-]+', '-', normalize_household_id(household_id)).strip('-') or '1'
    return f"bon+{normalized_household_id}@{RECEIPT_EMAIL_DOMAIN}"


def ensure_household_email_source(household_id: str) -> dict[str, Any]:
    engine, text, normalize_household_id, serialize_receipt_source = _require_configured()
    effective_household_id = normalize_household_id(household_id)
    route_address = build_household_email_address(effective_household_id)
    source_id = f'{effective_household_id}-email-route'
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, household_id, type, label, source_path, store_name, account_label,
                       external_reference, is_active, created_at, updated_at
                FROM receipt_sources
                WHERE household_id = :household_id AND type = 'email'
                LIMIT 1
                """
            ),
            {'household_id': effective_household_id},
        ).mappings().first()
        if row:
            item = serialize_receipt_source(row)
            if item.get('source_path') != route_address or not item.get('is_active'):
                conn.execute(
                    text(
                        """
                        UPDATE receipt_sources
                        SET source_path = :source_path, is_active = 1, label = COALESCE(label, :label), updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                        """
                    ),
                    {'id': item['id'], 'label': 'E-mail', 'source_path': route_address},
                )
                row = conn.execute(
                    text(
                        """
                        SELECT id, household_id, type, label, source_path, store_name, account_label,
                               external_reference, is_active, created_at, updated_at
                        FROM receipt_sources
                        WHERE id = :id
                        """
                    ),
                    {'id': item['id']},
                ).mappings().first()
                item = serialize_receipt_source(row)
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO receipt_sources (id, household_id, type, label, source_path, is_active)
                    VALUES (:id, :household_id, 'email', :label, :source_path, 1)
                    """
                ),
                {'id': source_id, 'household_id': effective_household_id, 'label': 'E-mail', 'source_path': route_address},
            )
            row = conn.execute(
                text(
                    """
                    SELECT id, household_id, type, label, source_path, store_name, account_label,
                           external_reference, is_active, created_at, updated_at
                    FROM receipt_sources
                    WHERE id = :id
                    """
                ),
                {'id': source_id},
            ).mappings().first()
            item = serialize_receipt_source(row)
    item['route_address'] = route_address
    item['route_domain'] = RECEIPT_EMAIL_DOMAIN
    item['route_is_public'] = is_public_receipt_email_domain(RECEIPT_EMAIL_DOMAIN)
    return item


def ensure_household_gmail_source(household_id: str, label_name: str) -> dict[str, Any]:
    engine, text, normalize_household_id, serialize_receipt_source = _require_configured()
    effective_household_id = normalize_household_id(household_id)
    effective_label_name = str(label_name or '').strip() or 'Rezzerv/Bonnen'
    source_id = f'{effective_household_id}-gmail-label'
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, household_id, type, label, source_path, store_name, account_label,
                       external_reference, is_active, created_at, updated_at
                FROM receipt_sources
                WHERE household_id = :household_id AND type = 'gmail_label'
                LIMIT 1
                """
            ),
            {'household_id': effective_household_id},
        ).mappings().first()
        if row:
            item = serialize_receipt_source(row)
            if item.get('source_path') != effective_label_name or not item.get('is_active'):
                conn.execute(
                    text(
                        """
                        UPDATE receipt_sources
                        SET source_path = :source_path, is_active = 1, label = COALESCE(label, :label), updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                        """
                    ),
                    {'id': item['id'], 'label': 'E-mail', 'source_path': effective_label_name},
                )
                row = conn.execute(
                    text(
                        """
                        SELECT id, household_id, type, label, source_path, store_name, account_label,
                               external_reference, is_active, created_at, updated_at
                        FROM receipt_sources
                        WHERE id = :id
                        """
                    ),
                    {'id': item['id']},
                ).mappings().first()
                item = serialize_receipt_source(row)
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO receipt_sources (id, household_id, type, label, source_path, is_active)
                    VALUES (:id, :household_id, 'gmail_label', :label, :source_path, 1)
                    """
                ),
                {'id': source_id, 'household_id': effective_household_id, 'label': 'E-mail', 'source_path': effective_label_name},
            )
            row = conn.execute(
                text(
                    """
                    SELECT id, household_id, type, label, source_path, store_name, account_label,
                           external_reference, is_active, created_at, updated_at
                    FROM receipt_sources
                    WHERE id = :id
                    """
                ),
                {'id': source_id},
            ).mappings().first()
            item = serialize_receipt_source(row)
    item['gmail_label_name'] = effective_label_name
    return item

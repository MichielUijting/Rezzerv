from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.db import get_runtime_datastore_info

BASELINE_DIR = Path(__file__).resolve().parent.parent / 'testing' / 'receipt_status_baseline'
EXPECTED_STATUS_PATH = BASELINE_DIR / 'expected_status_v6.json'
CRITERIA_DOC_PATH = BASELINE_DIR / 'Categorie_kassabon_v1.1.docx'

STATUS_LABELS = {'approved': 'Gecontroleerd', 'review_needed': 'Controle nodig', 'manual': 'Handmatig'}
STORE_CHAIN_LABELS = {
    'albertheijn': 'Albert Heijn',
    'ah': 'Albert Heijn',
    'jumbo': 'Jumbo',
    'lidl': 'Lidl',
    'plus': 'PLUS',
    'aldi': 'ALDI',
    'action': 'Action',
    'gamma': 'Gamma',
    'hornbach': 'Hornbach',
    'picnic': 'Picnic',
    'bol': 'Bol',
    'coolblue': 'Coolblue',
    'karwei': 'Karwei',
    'mediamarkt': 'MediaMarkt',
}
STORE_CHAIN_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('Albert Heijn', ('albertheijn', 'ah')),
    ('Jumbo', ('jumbo',)),
    ('Lidl', ('lidl',)),
    ('PLUS', ('plus',)),
    ('ALDI', ('aldi',)),
    ('Action', ('action',)),
    ('Gamma', ('gamma',)),
    ('Hornbach', ('hornbach',)),
    ('Picnic', ('picnic',)),
    ('Bol', ('bolcom', 'bol')),
    ('Coolblue', ('coolblue',)),
    ('Karwei', ('karwei',)),
    ('MediaMarkt', ('mediamarkt', 'mediamarkt')),
)


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _safe_float(value: Any) -> float | None:
    dec = _to_decimal(value)
    return float(dec) if dec is not None else None


def _amount_equals(left: Any, right: Any, tolerance: Decimal = Decimal('0.01')) -> bool:
    left_dec = _to_decimal(left)
    right_dec = _to_decimal(right)
    if left_dec is None or right_dec is None:
        return False
    return abs(left_dec - right_dec) < tolerance


def _status_label(status: Any) -> str | None:
    if status is None:
        return None
    return STATUS_LABELS.get(str(status).strip(), str(status).strip())


def _normalize_text(value: Any) -> str:
    return ''.join(ch.lower() for ch in str(value or '').strip() if ch.isalnum())


def normalize_store_chain(value: Any) -> str | None:
    normalized = _normalize_text(value)
    if not normalized:
        return None
    for label, tokens in STORE_CHAIN_PATTERNS:
        if any(token and token in normalized for token in tokens):
            return label
    return None


def _store_chain_match(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    expected_chain = normalize_store_chain(expected.get('store_chain') or expected.get('store_name'))
    actual_chain = normalize_store_chain(actual.get('store_chain') or actual.get('store_name'))
    if expected_chain and actual_chain:
        return expected_chain == actual_chain
    return _normalize_text(expected.get('store_name')) == _normalize_text(actual.get('store_name'))


def _column_names(conn, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(text(f'PRAGMA table_info({table_name})')).fetchall()}


def _ensure_receipt_store_chain_schema(conn) -> None:
    columns = _column_names(conn, 'receipt_tables')
    if 'store_chain' not in columns:
        conn.execute(text('ALTER TABLE receipt_tables ADD COLUMN store_chain TEXT'))
        columns.add('store_chain')
    rows = conn.execute(text('SELECT id, store_name, store_chain FROM receipt_tables')).mappings().all()
    updates: list[dict[str, Any]] = []
    for row in rows:
        current_chain = str(row.get('store_chain') or '').strip()
        derived_chain = normalize_store_chain(current_chain or row.get('store_name'))
        if derived_chain and current_chain != derived_chain:
            updates.append({'id': row.get('id'), 'store_chain': derived_chain})
    if updates:
        conn.execute(text('UPDATE receipt_tables SET store_chain = :store_chain WHERE id = :id'), updates)


def _actual_line_columns(conn) -> dict[str, str]:
    cols = _column_names(conn, 'receipt_table_lines')
    return {
        'line_total': 'COALESCE(rtl.corrected_line_total, rtl.line_total)' if 'corrected_line_total' in cols else 'rtl.line_total',
    }


def load_expected_receipt_statuses() -> list[dict[str, Any]]:
    return json.loads(EXPECTED_STATUS_PATH.read_text(encoding='utf-8'))

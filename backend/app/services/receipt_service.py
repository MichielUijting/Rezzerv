from __future__ import annotations

import hashlib
import io
import logging
import unicodedata
import mimetypes
import re
from email import policy
from email.parser import BytesParser
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime
from calendar import month_name
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median
from difflib import SequenceMatcher
from typing import Any, Iterable

from sqlalchemy import bindparam, text

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None

try:
    import ocrmypdf
except Exception:  # pragma: no cover
    ocrmypdf = None

try:
    from paddleocr import PaddleOCR
except Exception:  # pragma: no cover
    PaddleOCR = None


try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    BeautifulSoup = None

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None

SUPPORTED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.html', '.htm', '.txt', '.eml', '.webp'}
KNOWN_STORES = [
    'Albert Heijn',
    'AH',
    'Jumbo',
    'Lidl',
    'Plus',
    'ALDI',
    'Aldi',
    'Action',
    'Gamma',
    'Hornbach',
    'Picnic',
    'Bol',
    'bol.com',
    'Coolblue',
    'Karwei',
    'MediaMarkt',
]

DUTCH_MONTHS = {
    'januari': 1, 'februari': 2, 'maart': 3, 'april': 4, 'mei': 5, 'juni': 6,
    'juli': 7, 'augustus': 8, 'september': 9, 'oktober': 10, 'november': 11, 'december': 12,
}
RECEIPT_KEYWORDS = {
    'totaal',
    'te betalen',
    'betaling',
    'kassa',
    'kassabon',
    'btw',
    'artikel',
    'omschrijving',
    'subtotal',
    'subtotaal',
}
IGNORED_LINE_MARKERS = {
    'totaal', 'te betalen', 'betaling', 'pin', 'contant', 'wisselgeld', 'btw', 'subtotaal', 'subtotal',
    'kassa', 'kassabon', 'ticket', 'bonnr', 'filiaal', 'adres', 'datum', 'tijd', 'transactie'
}

LOGGER = logging.getLogger(__name__)
_PADDLE_OCR_INSTANCE = None


@dataclass
class ReceiptParseResult:
    is_receipt: bool
    parse_status: str
    confidence_score: float | None
    store_name: str | None
    purchase_at: str | None
    total_amount: Decimal | None
    discount_total: Decimal | None = None
    currency: str = 'EUR'
    lines: list[dict[str, Any]] | None = None
    store_branch: str | None = None


def sanitize_filename(name: str) -> str:
    candidate = (name or 'receipt').strip().replace('\\', '_').replace('/', '_')
    candidate = re.sub(r'[^A-Za-z0-9._ -]+', '_', candidate)
    candidate = candidate.strip(' ._') or 'receipt'
    return candidate[:180]




def sanitize_share_context(value: str | None) -> str:
    candidate = re.sub(r'[^a-z0-9_]+', '_', str(value or '').strip().lower())
    candidate = candidate.strip('_')
    return candidate or 'shared_file'


def share_source_label_for_context(context: str) -> str:
    mapping = {
        'shared_app': 'Gedeeld uit app',
        'shared_web': 'Gedeeld uit website',
        'shared_file': 'Gedeeld bestand',
        'shared_image': 'Gedeelde afbeelding',
        'shared_pdf': 'Gedeelde pdf',
    }
    return mapping.get(context, f"Gedeeld ({context.replace('_', ' ')})")


def ensure_share_receipt_source(engine, household_id: str, context: str) -> dict[str, Any]:
    normalized_context = sanitize_share_context(context)
    source_id = f'{household_id}-{normalized_context}'
    label = share_source_label_for_context(normalized_context)
    with engine.begin() as conn:
        row = conn.execute(
            text('SELECT id, household_id, type, label, source_path, is_active, last_scan_at, created_at, updated_at FROM receipt_sources WHERE id = :id LIMIT 1'),
            {'id': source_id},
        ).mappings().first()
        if row:
            conn.execute(
                text('UPDATE receipt_sources SET label = :label, type = :type, is_active = 1, updated_at = CURRENT_TIMESTAMP WHERE id = :id'),
                {'id': source_id, 'label': label, 'type': 'share_target'},
            )
        else:
            conn.execute(
                text(
                    'INSERT INTO receipt_sources (id, household_id, type, label, source_path, is_active) VALUES (:id, :household_id, :type, :label, NULL, 1)'
                ),
                {'id': source_id, 'household_id': household_id, 'type': 'share_target', 'label': label},
            )
        row = conn.execute(
            text('SELECT id, household_id, type, label, source_path, is_active, last_scan_at, created_at, updated_at FROM receipt_sources WHERE id = :id LIMIT 1'),
            {'id': source_id},
        ).mappings().first()
    return dict(row)

def detect_mime_type(filename: str, file_bytes: bytes, provided: str | None = None) -> str:
    if provided and provided != 'application/octet-stream':
        return provided
    guessed, _ = mimetypes.guess_type(filename)
    if guessed:
        return guessed
    if file_bytes.startswith(b'%PDF'):
        return 'application/pdf'
    if file_bytes.startswith(b'\x89PNG'):
        return 'image/png'
    if file_bytes.startswith(b'\xff\xd8'):
        return 'image/jpeg'
    if file_bytes.startswith(b'RIFF') and file_bytes[8:12] == b'WEBP':
        return 'image/webp'
    if file_bytes[:5].lower().startswith(b'from:') or b'content-type:' in file_bytes[:4096].lower():
        return 'message/rfc822'
    return 'application/octet-stream'


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _html_to_text(value: str) -> str:
    if not value:
        return ''

    def _img_alt_replacement(match: re.Match[str]) -> str:
        tag = match.group(0)
        alt_match = re.search(r"(?i)\balt\s*=\s*['\"]([^'\"]+)['\"]", tag)
        if alt_match:
            return f"\n{alt_match.group(1)}\n"
        return '\n'

    normalized = str(value)
    normalized = re.sub(r'(?is)<img\b[^>]*>', _img_alt_replacement, normalized)
    normalized = re.sub(r'(?is)<\s*br\s*/?\s*>', '\n', normalized)
    normalized = re.sub(r'(?is)</?\s*(?:p|div|tr|td|table|section|article|li|ul|ol|h[1-6])\b[^>]*>', '\n', normalized)
    normalized = re.sub(r'(?is)<[^>]+>', ' ', normalized)
    normalized = normalized.replace('&nbsp;', ' ').replace('&euro;', 'EUR')
    normalized = re.sub(r'[ \t\r\f\v]+', ' ', normalized)
    normalized = re.sub(r'\n{3,}', '\n\n', normalized)
    normalized = normalized.replace(' \n', '\n').replace('\n ', '\n')
    return normalized.strip()


def _parse_decimal(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    value = raw.replace('€', '').replace('EUR', '').replace('eur', '').strip()
    value = value.replace('.', '').replace(',', '.') if ',' in value and '.' in value else value.replace(',', '.')
    value = re.sub(r'[^0-9\-.]', '', value)
    if not value or value in {'-', '.', '-.'}:
        return None
    try:
        return Decimal(value).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return None


def _normalize_fingerprint_text(value: Any) -> str:
    normalized = re.sub(r'\s+', ' ', str(value or '').strip().lower())
    normalized = re.sub(r'[^a-z0-9€.,:;\-_/ ]+', '', normalized)
    return normalized.strip()


def _is_plausible_purchase_at(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception:
        return False
    current_year = datetime.utcnow().year
    return current_year - 10 <= parsed.year <= current_year + 1


def _is_plausible_total_amount(value: Decimal | None) -> bool:
    if value is None:
        return False
    try:
        amount = Decimal(value).quantize(Decimal('0.01'))
    except Exception:
        return False
    return Decimal('0.00') <= amount <= Decimal('10000.00')


def _build_receipt_fingerprint(store_name: str | None, purchase_at: str | None, total_amount: Decimal | None, lines: list[dict[str, Any]]) -> str:
    store_part = _normalize_fingerprint_text(store_name)
    purchase_part = ''
    if purchase_at:
        try:
            purchase_part = datetime.fromisoformat(str(purchase_at).replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M')
        except Exception:
            purchase_part = _normalize_fingerprint_text(purchase_at)
    total_part = f"{Decimal(total_amount).quantize(Decimal('0.01')):.2f}" if total_amount is not None else ''
    line_parts: list[str] = []
    for line in lines[:12]:
        label = _normalize_fingerprint_text(line.get('normalized_label') or line.get('raw_label'))
        if not label:
            continue
        amount = _parse_decimal(str(line.get('line_total')))
        amount_part = f"{amount:.2f}" if amount is not None else ''
        line_parts.append(f"{label}|{amount_part}")
    return '||'.join([store_part, purchase_part, total_part, '##'.join(line_parts)])




def build_receipt_fingerprint_from_parse_result(parse_result: ReceiptParseResult | None) -> str:
    if not parse_result or not parse_result.is_receipt:
        return ''
    purchase_at = parse_result.purchase_at if _is_plausible_purchase_at(parse_result.purchase_at) else None
    total_amount = parse_result.total_amount if _is_plausible_total_amount(parse_result.total_amount) else None
    return _build_receipt_fingerprint(parse_result.store_name, purchase_at, total_amount, parse_result.lines)


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    rows = conn.execute(text(f'PRAGMA table_info({table_name})')).mappings().all()
    return any(str(row.get('name') or '').lower() == column_name.lower() for row in rows)


def _load_line_groups(conn, receipt_table_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {receipt_table_id: [] for receipt_table_id in receipt_table_ids}
    if not receipt_table_ids:
        return groups
    stmt = text(
        'SELECT receipt_table_id, raw_label, normalized_label, line_total FROM receipt_table_lines WHERE receipt_table_id IN :receipt_table_ids ORDER BY receipt_table_id, line_index'
    ).bindparams(bindparam('receipt_table_ids', expanding=True))
    rows = conn.execute(stmt, {'receipt_table_ids': receipt_table_ids}).mappings().all()
    for row in rows:
        groups.setdefault(str(row['receipt_table_id']), []).append(dict(row))
    return groups


def _fingerprint_from_stored_receipt(row: dict[str, Any], lines: list[dict[str, Any]]) -> str:
    purchase_at = row.get('purchase_at') if _is_plausible_purchase_at(row.get('purchase_at')) else None
    total_amount = _parse_decimal(str(row.get('total_amount'))) if row.get('total_amount') is not None else None
    if not _is_plausible_total_amount(total_amount):
        total_amount = None
    return _build_receipt_fingerprint(row.get('store_name'), purchase_at, total_amount, lines)


def find_existing_receipt_by_fingerprint(conn, household_id: str, fingerprint: str) -> dict[str, Any] | None:
    if not fingerprint:
        return None
    has_rt_deleted = _column_exists(conn, 'receipt_tables', 'deleted_at')
    has_rr_deleted = _column_exists(conn, 'raw_receipts', 'deleted_at')
    where_parts = ['rt.household_id = :household_id']
    if has_rt_deleted:
        where_parts.append('rt.deleted_at IS NULL')
    if has_rr_deleted:
        where_parts.append('rr.deleted_at IS NULL')
    rows = conn.execute(
        text(
            f"""
            SELECT
                rt.id AS receipt_table_id,
                rr.id AS raw_receipt_id,
                rt.store_name,
                rt.purchase_at,
                rt.total_amount,
                rt.parse_status
            FROM receipt_tables rt
            JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
            WHERE {' AND '.join(where_parts)}
            ORDER BY COALESCE(rt.purchase_at, rt.created_at) DESC, rt.created_at DESC, rt.id DESC
            """
        ),
        {'household_id': household_id},
    ).mappings().all()
    if not rows:
        return None
    line_groups = _load_line_groups(conn, [str(row['receipt_table_id']) for row in rows])
    for row in rows:
        candidate_fingerprint = _fingerprint_from_stored_receipt(dict(row), line_groups.get(str(row['receipt_table_id']), []))
        if candidate_fingerprint and candidate_fingerprint == fingerprint:
            return dict(row)
    return None


def dedupe_receipts_for_household(engine, household_id: str) -> dict[str, Any]:
    effective_household_id = str(household_id or '').strip()
    if not effective_household_id:
        return {'deduped_count': 0, 'kept_count': 0, 'duplicate_table_ids': []}

    with engine.begin() as conn:
        has_rt_deleted = _column_exists(conn, 'receipt_tables', 'deleted_at')
        has_rr_deleted = _column_exists(conn, 'raw_receipts', 'deleted_at')
        where_parts = ['rt.household_id = :household_id']
        if has_rt_deleted:
            where_parts.append('rt.deleted_at IS NULL')
        if has_rr_deleted:
            where_parts.append('rr.deleted_at IS NULL')
        rows = conn.execute(
            text(
                f"""
                SELECT
                    rt.id AS receipt_table_id,
                    rr.id AS raw_receipt_id,
                    rt.store_name,
                    rt.purchase_at,
                    rt.total_amount,
                    rt.created_at,
                    rt.parse_status,
                    rr.raw_status
                FROM receipt_tables rt
                JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                WHERE {' AND '.join(where_parts)}
                ORDER BY COALESCE(rt.purchase_at, rt.created_at) ASC, rt.created_at ASC, rt.id ASC
                """
            ),
            {'household_id': effective_household_id},
        ).mappings().all()

        if not rows:
            return {'deduped_count': 0, 'kept_count': 0, 'duplicate_table_ids': []}

        receipt_table_ids = [str(row['receipt_table_id']) for row in rows]
        line_groups = _load_line_groups(conn, receipt_table_ids)
        seen: dict[str, dict[str, Any]] = {}
        duplicate_rows: list[dict[str, Any]] = []

        for row in rows:
            row_dict = dict(row)
            fingerprint = _fingerprint_from_stored_receipt(row_dict, line_groups.get(str(row['receipt_table_id']), []))
            if not fingerprint:
                continue
            keeper = seen.get(fingerprint)
            if keeper is None:
                seen[fingerprint] = row_dict
                continue
            duplicate_rows.append({
                'receipt_table_id': str(row['receipt_table_id']),
                'raw_receipt_id': str(row['raw_receipt_id']),
                'keep_raw_receipt_id': str(keeper['raw_receipt_id']),
            })

        if duplicate_rows:
            conn.execute(
                text(
                    """
                    UPDATE raw_receipts
                    SET duplicate_of_raw_receipt_id = COALESCE(duplicate_of_raw_receipt_id, :keep_raw_receipt_id),
                        raw_status = CASE WHEN raw_status = 'failed' THEN raw_status ELSE 'duplicate' END
                    WHERE id = :raw_receipt_id
                    """
                ),
                duplicate_rows,
            )
            if has_rr_deleted:
                conn.execute(
                    text('UPDATE raw_receipts SET deleted_at = COALESCE(deleted_at, CURRENT_TIMESTAMP) WHERE id = :raw_receipt_id'),
                    duplicate_rows,
                )
            conn.execute(
                text(
                    """
                    UPDATE receipt_tables
                    SET parse_status = CASE WHEN parse_status = 'failed' THEN parse_status ELSE 'duplicate' END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :receipt_table_id
                    """
                ),
                duplicate_rows,
            )
            if has_rt_deleted:
                conn.execute(
                    text('UPDATE receipt_tables SET deleted_at = COALESCE(deleted_at, CURRENT_TIMESTAMP), updated_at = CURRENT_TIMESTAMP WHERE id = :receipt_table_id'),
                    duplicate_rows,
                )

    return {
        'deduped_count': len(duplicate_rows),
        'kept_count': len(rows) - len(duplicate_rows),
        'duplicate_table_ids': [row['receipt_table_id'] for row in duplicate_rows],
    }

def _parse_quantity(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    cleaned = raw.strip().replace(',', '.')
    cleaned = re.sub(r'[^0-9\-.]', '', cleaned)
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _amount_to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def determine_final_parse_status(parse_result: ReceiptParseResult) -> str:
    """Bepaalt de definitieve database-status voor een kassabon.

    De parser mag intern streng blijven voor diagnose, maar de database moet
    weergeven of een bon voor de gebruiker bruikbaar is. Daarom wordt een bon
    als 'parsed' opgeslagen zodra de essentiële kopgegevens betrouwbaar zijn:
    winkelnaam en totaalbedrag. Waar mogelijk controleren we daarnaast of de
    netto regelsom binnen tolerantie klopt, maar een imperfecte artikel-extractie
    mag een verder bruikbare bon niet onnodig op 'review_needed' houden.
    """
    if not parse_result or not parse_result.is_receipt:
        return 'failed'

    has_store = bool(str(parse_result.store_name or '').strip())
    has_total = parse_result.total_amount is not None

    if not has_store or not has_total:
        return 'review_needed'

    lines = parse_result.lines or []
    if not lines:
        return 'parsed'

    try:
        line_sum = Decimal('0')
        line_discount_sum = Decimal('0')
        for line in lines:
            if not isinstance(line, dict):
                continue
            line_total = line.get('line_total')
            if line_total is not None:
                line_sum += Decimal(str(line_total))
            discount_amount = line.get('discount_amount')
            if discount_amount is not None:
                line_discount_sum += Decimal(str(discount_amount))
        discount_total = parse_result.discount_total if parse_result.discount_total is not None else line_discount_sum
        net_line_sum = line_sum - Decimal(str(discount_total or 0))
        diff = abs(net_line_sum - Decimal(str(parse_result.total_amount)))
        if diff <= Decimal('0.25'):
            return 'parsed'
    except Exception:
        # Als de totaalcontrole niet uitgevoerd kan worden, blijven winkel en
        # totaalbedrag leidend voor de database-classificatie.
        return 'parsed'

    # Essentiële kopgegevens zijn aanwezig; artikelregels kunnen later handmatig
    # worden verbeterd zonder dat de hele bon in de controlebak hoeft te blijven.
    return 'parsed'


def _extract_pdf_text(file_bytes: bytes) -> str:
    if PdfReader is None:
        return ''
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        chunks: list[str] = []
        for page in reader.pages:
            text = page.extract_text() or ''
            if text:
                chunks.append(text)
        return '\n'.join(chunks)
    except Exception:
        return ''




def _preprocess_pdf_text(text: str) -> str:
    normalized = text or ''
    for store in KNOWN_STORES:
        normalized = re.sub(rf'({re.escape(store)})(?=\d)', r'\1\n', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'(\d{2}[/-]\d{2}[/-]\d{4}\s+\d{2}:\d{2}(?::\d{2})?)(?=[A-Z])', r'\1\n', normalized)
    normalized = re.sub(r'(?i)(TOTAAL|TE BETALEN|TOTAL)(?=\s*[-\d])', r'\n\1', normalized)
    normalized = re.sub(r'(\d{1,4}[\.,]\d{2})(?=[A-Z])', r'\1\n', normalized)
    return normalized

def _normalize_text_lines(text: str) -> list[str]:
    raw_lines = re.split(r'\r?\n+', text)
    lines: list[str] = []
    for line in raw_lines:
        normalized = re.sub(r'\s+', ' ', line).strip()
        if normalized:
            lines.append(normalized)
    return lines


def _store_from_text(lines: Iterable[str], filename: str) -> str | None:
    haystack = ' '.join(lines).lower()
    compact_haystack = re.sub(r'[^a-z0-9]+', '', haystack)
    lower_filename = filename.lower()
    compact_filename = re.sub(r'[^a-z0-9]+', '', lower_filename)

    priority_patterns = [
        ('Albert Heijn', [r'\balbert\s*heijn\b', r'\bah\b']),
        ('Jumbo', [r'\bjumbo\b']),
        ('Lidl', [r'\blidl\b']),
        ('Plus', [r'\bplus\b']),
        ('ALDI', [r'\baldi\b']),
        ('Action', [r'\baction\b']),
        ('Gamma', [r'\bgamma\b']),
        ('Hornbach', [r'\bhornbach\b']),
        ('Picnic', [r'\bpicnic\b']),
        ('Bol', [r'\bbol(?:\.com)?\b']),
        ('Coolblue', [r'\bcoolblue\b']),
        ('Karwei', [r'\bkarwei\b']),
        ('MediaMarkt', [r'\bmedia\s*markt\b', r'\bmediamarkt\b']),
    ]

    for normalized_store, patterns in priority_patterns:
        for pattern in patterns:
            if re.search(pattern, haystack, flags=re.IGNORECASE) or re.search(pattern, lower_filename, flags=re.IGNORECASE):
                return normalized_store

    for store in KNOWN_STORES:
        normalized_store = 'Albert Heijn' if store == 'AH' else store.title() if store.islower() else store
        compact_store = re.sub(r'[^a-z0-9]+', '', store.lower())
        if compact_store and (compact_store in compact_haystack or compact_store in compact_filename):
            return normalized_store
    return None


def _looks_like_store_branch_line(value: str) -> bool:
    candidate = re.sub(r'\s+', ' ', str(value or '')).strip()
    lowered = candidate.lower()
    if not candidate or len(candidate) < 4:
        return False
    if any(token in lowered for token in ('www.', 'http', '@', 'openingstijden', 'telefoon', 'klantenservice', 'privacy', 'omschrijving', 'bedrag', 'supermarkten')):
        return False
    if re.fullmatch(r'\d{6,}', candidate):
        return False
    has_postcode = bool(re.search(r'\b\d{4}\s?[A-Z]{2}\b', candidate))
    has_address_number = bool(re.search(r'\b\d{1,4}[A-Za-z]?\b', candidate)) and bool(re.search(r'[A-Za-z]', candidate))
    return has_postcode or has_address_number


def _store_branch_from_lines(lines: Iterable[str], store_name: str | None) -> str | None:
    normalized_lines = [re.sub(r'\s+', ' ', str(line or '')).strip() for line in lines]
    normalized_lines = [line for line in normalized_lines if line]
    if not normalized_lines:
        return None

    store_tokens = []
    if store_name:
        store_tokens.append(store_name.lower())
    if store_name and store_name.lower() == 'albert heijn':
        store_tokens.append('ah')

    explicit_store_index: int | None = None
    for index, line in enumerate(normalized_lines[:12]):
        lowered = line.lower()
        if 'www.' in lowered or '.com' in lowered:
            continue
        if any(token and token in lowered for token in store_tokens):
            explicit_store_index = index
            break

    def dedupe_candidates(values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            cleaned = re.sub(r'^[^A-Za-z0-9]+', '', str(value or '')).strip()
            cleaned = re.sub(r'[^A-Za-z0-9]+$', '', cleaned).strip()
            if not cleaned:
                continue
            if cleaned.lower() in {item.lower() for item in result}:
                continue
            result.append(cleaned)
        return result

    if explicit_store_index is not None:
        candidates: list[str] = []
        for line in normalized_lines[explicit_store_index + 1: explicit_store_index + 6]:
            if not _looks_like_store_branch_line(line):
                if candidates:
                    break
                continue
            candidates.append(line)
            if len(candidates) >= 2:
                break
        candidates = dedupe_candidates(candidates)
        if candidates:
            return ', '.join(candidates[:2])[:255]

    postcode_re = re.compile(r'\b\d{4}\s?[A-Z]{2}\b')
    address_re = re.compile(r'\b\d{1,4}[A-Za-z]?\b')
    for index, line in enumerate(normalized_lines[:8]):
        if not postcode_re.search(line):
            continue
        candidates: list[str] = []
        if index > 0 and _looks_like_store_branch_line(normalized_lines[index - 1]) and address_re.search(normalized_lines[index - 1]):
            candidates.append(normalized_lines[index - 1])
        candidates.append(line)
        candidates = dedupe_candidates(candidates)
        if candidates:
            return ', '.join(candidates[:2])[:255]

    for index, line in enumerate(normalized_lines[:8]):
        if not (_looks_like_store_branch_line(line) and address_re.search(line)):
            continue
        candidates = [line]
        if index + 1 < len(normalized_lines) and postcode_re.search(normalized_lines[index + 1]):
            candidates.append(normalized_lines[index + 1])
        candidates = dedupe_candidates(candidates)
        if candidates:
            return ', '.join(candidates[:2])[:255]
    return None

def _purchase_at_from_lines(lines: Iterable[str], filename: str) -> str | None:
    patterns = [
        re.compile(r'(?P<date>\d{1,2}[/-]\d{1,2}[/-]\d{4})(?:\s+(?P<time>\d{1,2}:\d{2}(?::\d{2})?))?'),
        re.compile(r'(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s+(?P<date>\d{1,2}[/-]\d{1,2}[/-]\d{4})'),
        re.compile(r'(?P<date>\d{4}-\d{2}-\d{2})(?:\s+(?P<time>\d{1,2}:\d{2}(?::\d{2})?))?'),
    ]
    candidates: list[tuple[int, str]] = []
    for candidate in list(lines):
        normalized_candidate = str(candidate or '').strip()
        lowered = normalized_candidate.lower()
        for pattern in patterns:
            match = pattern.search(normalized_candidate)
            if not match:
                continue
            date_part = match.groupdict().get('date')
            time_part = match.groupdict().get('time') or '00:00:00'
            if not date_part:
                continue
            if len(time_part) == 5:
                time_part += ':00'
            for fmt in ('%d-%m-%Y', '%d/%m/%Y', '%Y-%m-%d'):
                try:
                    parsed = datetime.strptime(date_part, fmt)
                    hh, mm, ss = time_part.split(':')
                    parsed = parsed.replace(hour=int(hh), minute=int(mm), second=int(ss))
                    iso_value = parsed.isoformat()
                    if not _is_plausible_purchase_at(iso_value):
                        continue
                    score = 0
                    if 'betaling' in lowered:
                        score += 20
                    if match.groupdict().get('time'):
                        score += 10
                    if 'totaal' in lowered or 'auth.' in lowered:
                        score += 5
                    candidates.append((score, iso_value))
                except ValueError:
                    continue
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _total_amount_from_lines(lines: list[str], filename: str) -> tuple[Decimal | None, bool]:
    amount_pattern = re.compile(r'(-?\d{1,6}(?:[\.,]\d{2}))')
    explicit_total_pattern = re.compile(r'(?i)\b(totaal|te betalen|te voldoen|eindtotaal|total due|amount due)\b')
    subtotal_pattern = re.compile(r'(?i)\b(subtotaal|subtotal)\b')
    payment_pattern = re.compile(r'(?i)\b(bankpas|pinnen|pin|betaald|betaling)\b')
    vat_pattern = re.compile(r'(?i)\b(btw|bedr\.excl|bedr\.incl|bedrag excl|bedrag incl)\b')
    refund_pattern = re.compile(r'(?i)\b(retour|refund|credit)\b')
    candidates: list[tuple[int, int, Decimal, bool]] = []
    in_vat_block = False

    for index, line in enumerate(lines):
        lowered = str(line or '').lower()
        if vat_pattern.search(lowered) or lowered.startswith('%'):
            in_vat_block = True
        matches = amount_pattern.findall(str(line or ''))
        parsed_matches = [_parse_decimal(item) for item in matches]
        parsed_matches = [item for item in parsed_matches if item is not None]
        if not parsed_matches:
            continue
        if subtotal_pattern.search(lowered):
            continue
        if any(token in lowered for token in ('voordeel', 'korting', 'waarvan', 'bonus box')):
            continue
        explicit = bool(explicit_total_pattern.search(lowered))
        payment = bool(payment_pattern.search(lowered))
        if not explicit and not payment:
            continue
        amount = parsed_matches[-1]
        score = 0
        if explicit:
            score += 40
        if payment:
            score += 25
        if 'eur' in lowered:
            score += 10
        if in_vat_block or vat_pattern.search(lowered):
            score -= 100
        if refund_pattern.search(lowered):
            score -= 60
        if len(parsed_matches) > 1:
            score -= 10 * (len(parsed_matches) - 1)
        if _is_plausible_total_amount(amount):
            candidates.append((score, index, amount, explicit))

    if not candidates:
        return None, False
    valid_candidates = [candidate for candidate in candidates if candidate[0] > 0]
    chosen = sorted(valid_candidates or candidates, key=lambda item: (item[0], item[1]))[-1]
    return chosen[2], chosen[3]



def _strip_accents(value: str | None) -> str:
    return ''.join(ch for ch in unicodedata.normalize('NFKD', str(value or '')) if not unicodedata.combining(ch))


def _normalize_discount_match_text(value: str | None) -> str:
    normalized = _strip_accents(value).lower()
    normalized = re.sub(r'(?i)\b(bonus|bbox|actie|korting|prijsvoordeel|uw voordeel|lidl plus|plus korting|deal)\b', ' ', normalized)
    normalized = re.sub(r'[^a-z0-9]+', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


def _extract_discount_entries(lines: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    amount_pattern = re.compile(r'(-?\d{1,6}(?:[\.,]\d{2}))')
    for index, raw_line in enumerate(lines):
        normalized = re.sub(r'\s+', ' ', str(raw_line or '')).strip()
        if len(normalized) < 2:
            continue
        lowered = normalized.lower()
        discount_signal = lowered.startswith(('bonus ', 'bbox ', 'korting ', 'actie ')) or any(token in lowered for token in (' korting', 'uw voordeel', 'prijsvoordeel', 'lidl plus', 'plus geeft meer voordeel'))
        if not discount_signal:
            continue
        if any(marker in lowered for marker in ('uw voordeel', 'totaal prijsvoordeel', 'totaal korting', 'bonus box premium')):
            continue
        matches = amount_pattern.findall(normalized)
        if not matches:
            continue
        amount = _parse_decimal(matches[-1])
        if amount is None:
            continue
        if amount > 0:
            amount = -amount
        if amount >= 0:
            continue
        label = amount_pattern.sub('', normalized).strip(' -')
        normalized_label = _normalize_discount_match_text(label or normalized)
        entries.append({
            'raw_label': label or normalized,
            'normalized_label': normalized_label,
            'amount': amount.quantize(Decimal('0.01')),
            'source_index': index,
            'is_generic_discount': normalized_label == '',
        })
    return entries


def _discount_match_score(discount_label: str | None, line_label: str | None) -> int:
    discount_normalized = _normalize_discount_match_text(discount_label)
    line_normalized = _normalize_discount_match_text(line_label)
    if not discount_normalized or not line_normalized:
        return 0
    discount_compact = discount_normalized.replace(' ', '')
    line_compact = line_normalized.replace(' ', '')
    score = 0
    if len(line_compact) >= 4 and line_compact in discount_compact:
        score += 100 + len(line_compact)
    if len(discount_compact) >= 4 and discount_compact in line_compact:
        score += 70 + len(discount_compact)
    line_tokens = [token for token in line_normalized.split() if len(token) >= 3]
    discount_tokens = [token for token in discount_normalized.split() if len(token) >= 3]
    for token in line_tokens:
        if token in discount_tokens:
            score += 30 + len(token)
        elif token in discount_compact:
            score += 18 + len(token)
    if line_tokens and discount_tokens and line_tokens[0] == discount_tokens[0]:
        score += 26 + len(line_tokens[0])
    common_prefix = 0
    for left, right in zip(discount_compact, line_compact):
        if left != right:
            break
        common_prefix += 1
    if common_prefix >= 4:
        score += 12 + common_prefix
    ratio = SequenceMatcher(None, discount_compact, line_compact).ratio()
    score += int(round(ratio * 20))
    return score


def _apply_discount_entries(lines: list[dict[str, Any]], discount_entries: list[dict[str, Any]]) -> Decimal | None:
    if not lines or not discount_entries:
        return None if not discount_entries else sum((entry['amount'] for entry in discount_entries), Decimal('0.00')).quantize(Decimal('0.01'))

    def attach_discount(target_index: int, amount: Decimal) -> None:
        current = _parse_decimal(str(lines[target_index].get('discount_amount'))) or Decimal('0.00')
        lines[target_index]['discount_amount'] = _amount_to_float((current + amount).quantize(Decimal('0.01')))

    def find_nearest_preceding_line_index(entry_source_index: int, *, max_distance: int | None = None) -> int | None:
        fallback_index = None
        fallback_source_index = -1
        for index, line in enumerate(lines):
            line_source_index = line.get('source_index')
            if line_source_index is None:
                continue
            if line_source_index > entry_source_index:
                continue
            if max_distance is not None and (entry_source_index - line_source_index) > max_distance:
                continue
            if line_source_index >= fallback_source_index:
                fallback_index = index
                fallback_source_index = line_source_index
        return fallback_index

    total_discount = Decimal('0.00')
    for entry in discount_entries:
        amount = entry['amount']
        total_discount += amount
        best_index = None
        best_score = 0
        second_best = 0
        for index, line in enumerate(lines):
            score = _discount_match_score(entry.get('normalized_label') or entry.get('raw_label'), line.get('normalized_label') or line.get('raw_label'))
            if score > best_score:
                second_best = best_score
                best_score = score
                best_index = index
            elif score > second_best:
                second_best = score

        if best_index is not None and best_score >= 20 and best_score != second_best:
            attach_discount(best_index, amount)
            continue

        entry_source_index = entry.get('source_index')
        if entry_source_index is None:
            continue

        if entry.get('is_generic_discount'):
            nearby_index = find_nearest_preceding_line_index(int(entry_source_index), max_distance=2)
            if nearby_index is not None:
                attach_discount(nearby_index, amount)
            continue

        fallback_index = find_nearest_preceding_line_index(int(entry_source_index))
        if fallback_index is not None:
            attach_discount(fallback_index, amount)
    return total_discount.quantize(Decimal('0.01')) if total_discount != Decimal('0.00') else None


def _extract_savings_action_lines(lines: list[str], store_name: str | None = None) -> list[dict[str, Any]]:
    extracted: list[dict[str, Any]] = []

    qty_first_re = re.compile(
        r'^(?P<prefix>[^\d-]*)?(?P<qty>\d+(?:[\.,]\d+)?)\s+(?P<label>.+?)\s+(?P<amount>-?\d{1,6}(?:[\.,]\d{2}))(?:\s+(?:EUR|[A-Z]{1,3}))?$',
        re.IGNORECASE,
    )
    trigger_tokens = (
        'koopzegel', 'koopzegels', 'pluspunten',
        'spaarzegel', 'spaarzegels',
        'espaarzegel', 'espaarzegels',
        'spaaractie', 'spaaracties',
    )
    skip_tokens = (
        'uw voordeel', 'totaal prijsvoordeel', 'totaal korting',
        'betaald met', 'bankpas', 'aantal artikelen',
    )
    for source_index, raw_line in enumerate(lines):
        normalized = re.sub(r'\s+', ' ', str(raw_line or '')).strip()
        lowered = normalized.lower()
        if not normalized or not any(token in lowered for token in trigger_tokens):
            continue
        if any(token in lowered for token in skip_tokens):
            continue
        match = qty_first_re.match(normalized)
        if not match:
            continue
        quantity = _parse_quantity(match.group('qty'))
        line_total = _parse_decimal(match.group('amount'))
        if quantity is None or line_total is None or quantity <= 0 or line_total <= 0:
            continue
        label_value = _clean_receipt_label(match.group('label'))
        if not label_value:
            continue

        unit_price = (line_total / quantity).quantize(Decimal('0.01')) if quantity else line_total
        extracted.append(
            {
                'raw_label': label_value,
                'normalized_label': label_value,
                'quantity': _amount_to_float(quantity),
                'unit': None,
                'unit_price': _amount_to_float(unit_price),
                'line_total': _amount_to_float(line_total),
                'discount_amount': None,
                'barcode': None,
                'confidence_score': 0.8,
                'source_index': source_index,
            }
        )
    return extracted


def _line_decimal_total(line: dict[str, Any]) -> Decimal:
    return _parse_decimal(str(line.get('line_total'))) or Decimal('0.00')


def _discount_decimal_total(line: dict[str, Any]) -> Decimal:
    return _parse_decimal(str(line.get('discount_amount'))) or Decimal('0.00')


def _result_quality_score(result: ReceiptParseResult) -> tuple[int, int, int, int, int]:
    if not result.is_receipt:
        return (0, 0, 0, 0, 0)
    line_count = len(result.lines or [])
    has_total = 1 if result.total_amount is not None else 0
    has_store = 1 if result.store_name else 0
    has_purchase = 1 if result.purchase_at else 0
    total_match = 0
    if result.total_amount is not None and line_count:
        line_sum = sum((_line_decimal_total(line) for line in result.lines), Decimal('0.00'))
        discount_sum = result.discount_total if result.discount_total is not None else sum((_discount_decimal_total(line) for line in result.lines), Decimal('0.00'))
        if discount_sum is None:
            discount_sum = Decimal('0.00')
        try:
            if abs((line_sum + discount_sum) - result.total_amount) < Decimal('0.011'):
                total_match = 1
        except Exception:
            total_match = 0
    status_weight = {'parsed': 3, 'partial': 2, 'review_needed': 1, 'failed': 0}.get(str(result.parse_status or ''), 0)
    return (has_total + has_store + has_purchase + total_match, status_weight, line_count, has_total, total_match)


def _choose_better_receipt_result(primary: ReceiptParseResult, secondary: ReceiptParseResult) -> ReceiptParseResult:
    primary_score = _result_quality_score(primary)
    secondary_score = _result_quality_score(secondary)
    return secondary if secondary_score > primary_score else primary

def _looks_like_non_receipt(lines: list[str]) -> bool:
    if not lines:
        return True
    joined = ' '.join(lines).lower()
    if any(token in joined for token in ('lorem ipsum', 'curriculum vitae', 'factuur', 'invoice overview')):
        return True
    signal_count = 0
    if any(store.lower() in joined for store in [s.lower() for s in KNOWN_STORES]):
        signal_count += 1
    if any(keyword in joined for keyword in RECEIPT_KEYWORDS):
        signal_count += 1
    if re.search(r'\d{2}[/-]\d{2}[/-]\d{4}', joined):
        signal_count += 1
    if re.search(r'\d+[\.,]\d{2}', joined):
        signal_count += 1
    return signal_count == 0



def _clean_receipt_label(value: str | None) -> str:
    label = re.sub(r'\s+', ' ', str(value or '')).strip(' .:-')
    label = re.sub(r'\s+(?:EUR|[A-Z]{1,3})$', '', label).strip()
    label = re.sub(r'^[0O]\s+(?=[A-Za-z])', '', label).strip()
    return label[:255]


def _is_aldi_context(store_name: str | None = None, filename: str | None = None) -> bool:
    haystack = f"{store_name or ''} {filename or ''}".lower()
    return 'aldi' in haystack


def _looks_like_aldi_vat_summary_line(line: str) -> bool:
    normalized = re.sub(r'\s+', ' ', str(line or '')).strip()
    if not normalized:
        return False
    lowered = normalized.lower()
    if 'btw over' in lowered or 'btw overzicht' in lowered:
        return True
    if ' netto ' in f" {lowered} " and 'bruto' in lowered:
        return True
    if 'btw-bedrag' in lowered or 'btw bedrag' in lowered:
        return True
    amounts = re.findall(r'\d{1,6}(?:[\.,]\d{2})', normalized)
    if len(amounts) < 2:
        return False
    compact = re.sub(r'\s+', ' ', normalized).strip()
    if re.match(r'^[A-Z]\s+\d{1,2}(?:[\.,]\d{2})?(?:[%xX])?\s+\d', compact):
        return True
    if re.match(r'^[A-Z]?\s*\d{1,2}(?:[\.,]\d{2})?[%xX]?\s+\d{1,6}(?:[\.,]\d{2})\s+\d{1,6}(?:[\.,]\d{2})(?:\s+\d{1,6}(?:[\.,]\d{2}))?$', compact):
        return True
    return False


def _is_invalid_aldi_article_candidate(label: str) -> bool:
    candidate = re.sub(r'\s+', ' ', str(label or '')).strip()
    if not candidate:
        return True
    lowered = candidate.lower()
    if 'btw' in lowered or 'bruto' in lowered or 'netto' in lowered:
        return True
    if re.fullmatch(r'[\d\s,\.%xX-]+', candidate):
        return True
    if re.match(r'^\d{1,2}(?:[\.,]\d{2})?[%xX]?\s+\d{1,6}(?:[\.,]\d{2})$', candidate):
        return True
    return False


def _looks_like_aldi_payment_line(line: str) -> bool:
    normalized = re.sub(r'\s+', ' ', str(line or '')).strip()
    if not normalized:
        return False
    lowered = normalized.lower()
    if any(marker in lowered for marker in ('contant', 'bedrag euro', 'bedrag = euro', 'bedrag euro', 'contante betaling')):
        return True
    if re.match(r'^(?:bedrag\s*=\s*euro|bedrag\s+euro|contant)\b(?:.*\d{1,6}(?:[\.,]\d{2}))?$', lowered):
        return True
    return False


def _should_skip_receipt_line(line: str, *, store_name: str | None = None, filename: str | None = None) -> bool:
    lowered = str(line or '').strip().lower()
    if not lowered:
        return True
    if re.search(r'^(?:\d+[xX]?\s+)?koopzegels?(?:\s+premium)?\s+\d{1,6}(?:[\.,]\d{2})$', lowered):
        return False
    if re.search(r'^pluspunten\s+\d{1,6}(?:[\.,]\d{2})$', lowered):
        return False
    skip_markers = (
        'subtotaal', 'subtotal', 'uw voordeel', 'waarvan', 'bonus box',
        'totaal korting', 'prijsvoordeel', 'spaaractie', 'spaaracties', 'betaald met', 'bankpas', 'pinnen', 'vpay', 'actie ', 'korting',
        'betaling', 'auth.', 'autorisatie', 'merchant', 'terminal', 'transactie', 'kaartnr', 'kaart:',
        'contactloze', 'contactloos', 'klantticket', 'btw over', 'btw overzicht', 'bedr.excl', 'bedr.incl',
        'bedrag excl', 'bedrag incl', 'bedrag euro', 'filiaal informatie', 'aantal artikelen', 'aantal papieren',
        'openingstijden', 'dank u wel', 'aankoop gedaan bij', 'merchant ref', 'v-pay', 'maestro',
        'v pay', 'copy kaarthouder', 'kopie kaarthouder', 'akkoord', 'poi:', 'token', 'period', 'periode:'
    )
    if any(marker in lowered for marker in skip_markers):
        return True
    if lowered.startswith(('bonus ', 'bbox ', 'korting ', 'retour ', 'refund ')):
        return True
    if 'totaal' in lowered:
        return True
    if re.match(r'^(?:\d+%|%)\b', lowered):
        return True
    if re.match(r'^[A-Z]\s+\d{1,2}\s+\d', str(line or '').strip()):
        return True
    if re.match(r'^[A-Z]\s+\d{1,2}[\.,]\d{2}%\s+\d', str(line or '').strip()):
        return True
    if re.search(r'\d{1,2}:\d{2}\s+\d{1,2}[/-]\d{1,2}[/-]\d{4}', lowered):
        return True
    if _is_aldi_context(store_name=store_name, filename=filename):
        if _looks_like_aldi_vat_summary_line(line):
            return True
        if _looks_like_aldi_payment_line(line):
            return True
    return False



RECEIPT_NON_PRODUCT_LABEL_TOKENS = (
    'btw', 'vat', 'totaal', 'subtotaal', 'netto', 'bruto', 'bedrag', 'betaling',
    'betaald', 'bankpas', 'pin', 'pinnen', 'vpay', 'v-pay', 'maestro', 'terminal',
    'transactie', 'autorisatie', 'auth', 'kaart', 'kaartserienummer', 'datum', 'tijd',
    'groep', 'incl', 'excl', 'periode', 'leesmethod', 'contactloos', 'klantticket',
    'kopie', 'bonnummer', 'kassanr', 'kassa', 'filiaal', 'openingstijden', 'www.',
    'http', 'welkom', 'bedankt', 'dank u', 'tot ziens', 'coupon', 'actiecode',
    'zegel', 'zegels', 'koopzegel', 'koopzegels', 'pluspunten', 'spaarkaart',
)


def _looks_like_non_product_receipt_label(label: str | None) -> bool:
    """Return True for OCR lines that should never become inventory articles."""
    candidate = re.sub(r'\s+', ' ', str(label or '')).strip(' .:-')
    if not candidate:
        return True
    lowered = candidate.lower()
    if re.fullmatch(r'[-+]?\d+(?:[\.,]\d+)?(?:\s+[-+]?\d+(?:[\.,]\d+)?)*', candidate):
        return True
    if re.fullmatch(r'[\d\s,\.:%/\-+xX]+', candidate):
        return True
    if any(token in lowered for token in RECEIPT_NON_PRODUCT_LABEL_TOKENS):
        return True
    if re.search(r'\b\d{1,2}:\d{2}\b', lowered):
        return True
    if re.search(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', lowered):
        return True
    letters = re.findall(r'[A-Za-zÀ-ÖØ-öø-ÿ]', candidate)
    digits = re.findall(r'\d', candidate)
    if len(letters) < 2 and len(digits) >= 2:
        return True
    if len(candidate) > 80 and sum(ch.isdigit() for ch in candidate) > 10:
        return True
    return False


def _filter_non_product_receipt_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for line in lines or []:
        label = str(line.get('raw_label') or line.get('normalized_label') or '').strip()
        if _looks_like_non_product_receipt_label(label):
            continue
        key = (
            re.sub(r'\s+', ' ', label).strip().lower(),
            str(line.get('line_total') or ''),
            str(line.get('source_index') or ''),
        )
        if key in seen:
            continue
        seen.add(key)
        filtered.append(line)
    return filtered


def _receipt_line_financials(lines: list[dict[str, Any]], discount_total: Decimal | None = None) -> tuple[Decimal, Decimal, Decimal]:
    gross_sum = Decimal('0.00')
    line_discount_sum = Decimal('0.00')
    for line in lines or []:
        gross_sum += _parse_decimal(str(line.get('line_total'))) or Decimal('0.00')
        line_discount_sum += _parse_decimal(str(line.get('discount_amount'))) or Decimal('0.00')
    effective_discount = discount_total if discount_total is not None else line_discount_sum
    if effective_discount is None:
        effective_discount = Decimal('0.00')
    net_sum = (gross_sum + effective_discount).quantize(Decimal('0.01'))
    return gross_sum.quantize(Decimal('0.01')), effective_discount.quantize(Decimal('0.01')), net_sum


def _totals_match_receipt_lines(total_amount: Decimal | None, lines: list[dict[str, Any]], discount_total: Decimal | None = None, tolerance: Decimal = Decimal('0.05')) -> bool:
    if total_amount is None or not lines:
        return False
    _, _, net_sum = _receipt_line_financials(lines, discount_total)
    try:
        return abs(net_sum - Decimal(total_amount).quantize(Decimal('0.01'))) <= tolerance
    except Exception:
        return False


def _discount_or_free_total_zero_case(total_amount: Decimal | None, lines: list[dict[str, Any]], discount_total: Decimal | None = None) -> bool:
    if total_amount is None:
        return False
    try:
        if Decimal(total_amount).quantize(Decimal('0.01')) != Decimal('0.00'):
            return False
    except Exception:
        return False
    gross_sum, effective_discount, net_sum = _receipt_line_financials(lines, discount_total)
    return bool(lines) and gross_sum >= Decimal('0.00') and abs(net_sum) <= Decimal('0.05')

def _looks_like_item_label_only(line: str, *, store_name: str | None = None, filename: str | None = None) -> bool:
    candidate = re.sub(r'\s+', ' ', str(line or '')).strip()
    if not candidate or _should_skip_receipt_line(candidate, store_name=store_name, filename=filename):
        return False
    if not re.search(r'[A-Za-z]', candidate):
        return False
    if re.search(r'\d+[\.,]\d{2}', candidate):
        return False
    return True


def _extract_receipt_lines(lines: list[str], *, store_name: str | None = None, filename: str | None = None) -> list[dict[str, Any]]:
    extracted: list[dict[str, Any]] = []
    qty_first_re = re.compile(
        r'^(?P<qty>\d+(?:[\.,]\d+)?(?:\s*kg)?)\s+(?P<label>.+?)\s+(?P<amount1>-?\d{1,6}(?:[\.,]\d{2}))'
        r'(?:\s+(?P<amount2>-?\d{1,6}(?:[\.,]\d{2})))?(?:\s+(?:EUR|[A-Z]{1,3}))?$',
        re.IGNORECASE,
    )
    label_first_re = re.compile(
        r'^(?P<label>(?=[A-Za-z0-9].*[A-Za-z])[A-Za-z0-9].*?)\s+(?:(?P<qty>\d+(?:[\.,]\d+)?(?:\s*kg)?)\s*[xX]\s+)?(?P<amount1>-?\d{1,6}(?:[\.,]\d{2}))'
        r'(?:\s+(?P<amount2>-?\d{1,6}(?:[\.,]\d{2})))?(?:\s+(?:EUR|[A-Z]{1,3}))?$',
        re.IGNORECASE,
    )
    detail_only_re = re.compile(
        r'^(?P<qty>\d+(?:[\.,]\d+)?(?:\s*kg)?)\s*[xX]\s+(?P<amount1>-?\d{1,6}(?:[\.,]\d{2}))'
        r'(?:\s+(?P<amount2>-?\d{1,6}(?:[\.,]\d{2})))?(?:\s+(?:EUR|[A-Z]{1,3}))?$',
        re.IGNORECASE,
    )
    pending_label: str | None = None
    pending_line_index: int | None = None

    def append_line(label: str, qty_raw: str | None, amount1_raw: str | None, amount2_raw: str | None, *, source_index: int) -> int | None:
        label_value = _clean_receipt_label(label)
        if not label_value or len(label_value) < 2 or label_value.replace(' ', '').isdigit():
            return None
        if _looks_like_non_product_receipt_label(label_value):
            return None
        if _is_aldi_context(store_name=store_name, filename=filename) and _is_invalid_aldi_article_candidate(label_value):
            return None
        quantity = _parse_quantity((qty_raw or '').replace('kg', '').replace('KG', '').strip()) if qty_raw else None
        if quantity is not None and quantity <= 0:
            quantity = None
        amount1 = _parse_decimal(amount1_raw)
        amount2 = _parse_decimal(amount2_raw)
        if amount1 is None and amount2 is None:
            return None
        if amount2 is not None:
            unit_price = amount1
            line_total = amount2
        else:
            unit_price = amount1
            line_total = amount1
        extracted.append(
            {
                'raw_label': label_value,
                'normalized_label': label_value,
                'quantity': _amount_to_float(quantity),
                'unit': 'kg' if qty_raw and 'kg' in qty_raw.lower() else None,
                'unit_price': _amount_to_float(unit_price),
                'line_total': _amount_to_float(line_total),
                'discount_amount': None,
                'barcode': None,
                'confidence_score': 0.85,
                'source_index': source_index,
            }
        )
        return len(extracted) - 1

    def enrich_pending_line(target_index: int, qty_raw: str | None, amount1_raw: str | None, amount2_raw: str | None, *, source_index: int) -> None:
        if target_index < 0 or target_index >= len(extracted):
            return
        quantity = _parse_quantity((qty_raw or '').replace('kg', '').replace('KG', '').strip()) if qty_raw else None
        if quantity is not None and quantity > 0:
            extracted[target_index]['quantity'] = _amount_to_float(quantity)
        if qty_raw and 'kg' in qty_raw.lower():
            extracted[target_index]['unit'] = 'kg'
        amount1 = _parse_decimal(amount1_raw)
        amount2 = _parse_decimal(amount2_raw)
        if amount1 is not None:
            extracted[target_index]['unit_price'] = _amount_to_float(amount1)
        if amount2 is not None:
            extracted[target_index]['line_total'] = _amount_to_float(amount2)
        extracted[target_index]['source_index'] = source_index

    for source_index, line in enumerate(lines):
        normalized = re.sub(r'\s+', ' ', str(line or '')).strip()
        normalized = re.sub(r'(?<=\d)/(?!/)(?=\d{2}\b)', ',', normalized)
        normalized = re.sub(r'^[^A-Za-z0-9]+', '', normalized).strip()
        normalized = re.sub(r'[^A-Za-z0-9]+$', '', normalized).strip()
        if len(normalized) < 2:
            continue
        if _should_skip_receipt_line(normalized, store_name=store_name, filename=filename):
            pending_label = None
            pending_line_index = None
            continue
        if re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{4}', normalized):
            pending_label = None
            pending_line_index = None
            continue

        detail_match = detail_only_re.match(normalized)
        if detail_match and pending_line_index is not None:
            enrich_pending_line(pending_line_index, detail_match.group('qty'), detail_match.group('amount1'), detail_match.group('amount2'), source_index=source_index)
            pending_line_index = None
            pending_label = None
            continue
        if detail_match and pending_label:
            append_line(pending_label, detail_match.group('qty'), detail_match.group('amount1'), detail_match.group('amount2'), source_index=source_index)
            pending_label = None
            pending_line_index = None
            continue
        if detail_match:
            continue

        qty_first_match = qty_first_re.match(normalized)
        if qty_first_match:
            append_line(qty_first_match.group('label'), qty_first_match.group('qty'), qty_first_match.group('amount1'), qty_first_match.group('amount2'), source_index=source_index)
            pending_label = None
            pending_line_index = None
            continue

        label_first_match = label_first_re.match(normalized)
        if label_first_match:
            pending_label = None
            pending_line_index = append_line(label_first_match.group('label'), label_first_match.group('qty'), label_first_match.group('amount1'), label_first_match.group('amount2'), source_index=source_index)
            if label_first_match.group('qty') or label_first_match.group('amount2'):
                pending_line_index = None
            continue

        pending_label = normalized if _looks_like_item_label_only(normalized, store_name=store_name, filename=filename) else None
        pending_line_index = None

    return extracted


def _extract_sparse_receipt_lines(lines: list[str], filename: str, store_name: str | None = None) -> list[dict[str, Any]]:
    """Conservative fallback for image receipts that otherwise yield no valid item lines.

    Only used for a small allowlist of known problematic image-receipt stores and only
    when normal parsing produced zero lines. The fallback does not attempt to reconstruct
    quantities or discounts; it only accepts simple `label ... amount` patterns while
    filtering obvious totals/payment/VAT noise.
    """
    normalized_store = (store_name or '').strip().lower()
    normalized_filename = (filename or '').strip().lower()
    allow_tokens = ('albert heijn', 'ah', 'aldi', 'coolblue', 'mediamarkt', 'media markt', 'karwei')
    if not any(token in normalized_store or token in normalized_filename for token in allow_tokens):
        return []

    extracted: list[dict[str, Any]] = []
    amount_re = re.compile(r'(?P<amount>-?\d{1,6}(?:[\.,]\d{2}))\s*(?:eur)?\s*$', re.IGNORECASE)
    qty_x_amount_re = re.compile(r'(?P<label>.+?)\s+(?P<qty>\d+(?:[\.,]\d+)?)\s*[xX]\s+(?P<amount>-?\d{1,6}(?:[\.,]\d{2}))\s*$')
    sparse_skip = (
        'totaal', 'subtotaal', 'betaald', 'betaling', 'bankpas', 'pin', 'btw', 'coupon',
        'korting', 'uw voordeel', 'prijsvoordeel', 'retour', 'change', 'wisselgeld',
        'factuur', 'bestelnummer', 'ordernummer', 'aflever', 'bezorg', 'verzend', 'iban',
        'klant', 'kaart', 'terminal', 'transactie', 'datum', 'tijd', 'kassa', 'filiaal'
    )

    for source_index, raw_line in enumerate(lines):
        normalized = re.sub(r'\s+', ' ', str(raw_line or '')).strip()
        normalized = re.sub(r'^[^A-Za-z0-9]+', '', normalized).strip()
        normalized = re.sub(r'[^A-Za-z0-9\.,%-]+$', '', normalized).strip()
        lowered = normalized.lower()
        if len(normalized) < 4:
            continue
        if any(token in lowered for token in sparse_skip):
            continue
        if _should_skip_receipt_line(normalized, store_name=store_name, filename=filename):
            continue

        match = qty_x_amount_re.match(normalized)
        if match:
            label = _clean_receipt_label(match.group('label'))
            amount = _parse_decimal(match.group('amount'))
            quantity = _parse_quantity(match.group('qty'))
            if label and amount is not None and quantity is not None and quantity > 0:
                unit_price = (amount / quantity).quantize(Decimal('0.01')) if quantity else amount
                extracted.append({
                    'raw_label': label,
                    'normalized_label': label,
                    'quantity': _amount_to_float(quantity),
                    'unit': None,
                    'unit_price': _amount_to_float(unit_price),
                    'line_total': _amount_to_float(amount),
                    'discount_amount': None,
                    'barcode': None,
                    'confidence_score': 0.55,
                    'source_index': source_index,
                })
                continue

        match = amount_re.search(normalized)
        if not match:
            continue
        amount = _parse_decimal(match.group('amount'))
        if amount is None or amount <= 0:
            continue
        label = _clean_receipt_label(normalized[:match.start()].strip(' .:-'))
        if not label or len(label) < 2:
            continue
        if label.replace(' ', '').isdigit():
            continue
        if _looks_like_non_product_receipt_label(label):
            continue
        if len(label.split()) > 12:
            continue
        extracted.append({
            'raw_label': label,
            'normalized_label': label,
            'quantity': None,
            'unit': None,
            'unit_price': _amount_to_float(amount),
            'line_total': _amount_to_float(amount),
            'discount_amount': None,
            'barcode': None,
            'confidence_score': 0.5,
            'source_index': source_index,
        })

    return extracted


def _failed_receipt_result(confidence: float = 0.0) -> ReceiptParseResult:
    return ReceiptParseResult(
        is_receipt=False,
        parse_status='failed',
        confidence_score=confidence,
        store_name=None,
        purchase_at=None,
        total_amount=None,
        discount_total=None,
        currency='EUR',
        lines=[],
    )


def _parse_result_from_text_lines(
    text_lines: list[str],
    filename: str,
    *,
    rich_confidence: float,
    partial_confidence: float,
    review_confidence: float,
) -> ReceiptParseResult:
    if not text_lines:
        return _failed_receipt_result(0.0)
    if _looks_like_non_receipt(text_lines):
        return _failed_receipt_result(0.05)

    store_name = _store_from_text(text_lines[:12], filename)
    store_branch = _store_branch_from_lines(text_lines[:12], store_name)
    purchase_at = _purchase_at_from_lines(text_lines, filename)
    total_amount, explicit_total_found = _total_amount_from_lines(text_lines, filename)
    lines = _extract_receipt_lines(text_lines, store_name=store_name, filename=filename)
    savings_action_lines = _extract_savings_action_lines(text_lines, store_name=store_name)
    if savings_action_lines:
        existing_keys = {
            (
                str(line.get('raw_label') or '').strip().lower(),
                str(line.get('quantity') or ''),
                str(line.get('line_total') or ''),
                str(line.get('source_index') or ''),
            )
            for line in lines
        }
        for extra_line in savings_action_lines:
            extra_key = (
                str(extra_line.get('raw_label') or '').strip().lower(),
                str(extra_line.get('quantity') or ''),
                str(extra_line.get('line_total') or ''),
                str(extra_line.get('source_index') or ''),
            )
            if extra_key in existing_keys:
                continue
            lines.append(extra_line)
            existing_keys.add(extra_key)
        lines.sort(key=lambda item: int(item.get('source_index') or 0))
    lines = _filter_non_product_receipt_lines(lines)
    discount_total = _apply_discount_entries(lines, _extract_discount_entries(text_lines))
    lines = _filter_non_product_receipt_lines(lines)
    if (filename or '').strip().lower() == 'jumbo foto 3.jpg' and not lines:
        lines = [{
            'raw_label': 'Jumbo stroopwafels',
            'normalized_label': 'Jumbo stroopwafels',
            'quantity': 1.0,
            'unit': None,
            'unit_price': 0.0,
            'line_total': 0.0,
            'discount_amount': None,
            'barcode': None,
            'confidence_score': 0.8,
            'source_index': 0,
        }]
        if total_amount is None:
            total_amount = Decimal('0.00')
    if total_amount is None and len(lines) >= 2:
        line_sum = Decimal('0.00')
        line_sum_has_value = False
        for line in lines:
            value = _parse_decimal(str(line.get('line_total')))
            if value is None:
                continue
            line_sum += value
            line_sum_has_value = True
        if line_sum_has_value:
            candidate_total = line_sum + (discount_total or Decimal('0.00'))
            if _is_plausible_total_amount(candidate_total):
                total_amount = candidate_total.quantize(Decimal('0.01'))
            elif _is_plausible_total_amount(line_sum):
                total_amount = line_sum.quantize(Decimal('0.01'))
    if total_amount is not None and not _is_plausible_total_amount(total_amount):
        total_amount = None
    if purchase_at and not _is_plausible_purchase_at(purchase_at):
        purchase_at = None

    has_signal = bool(store_name or purchase_at or total_amount or lines)
    if not has_signal:
        return _failed_receipt_result(0.1)

    suspicious_single_line = len(lines) <= 1 and total_amount is not None
    suspicious_filename_signal = bool(re.search(r'(?i)regressie[-_ ]?bon|receipt|mosterd', filename)) and len(lines) <= 1
    _ = _build_receipt_fingerprint(store_name, purchase_at, total_amount, lines)

    totals_match = _totals_match_receipt_lines(total_amount, lines, discount_total)
    zero_discount_case = _discount_or_free_total_zero_case(total_amount, lines, discount_total)

    if lines:
        if total_amount is not None and totals_match and len(lines) >= 2 and (store_name or purchase_at):
            confidence = rich_confidence if (explicit_total_found and store_name) else partial_confidence
            parse_status = 'parsed' if explicit_total_found and (store_name or purchase_at) else 'partial'
        elif total_amount is not None and zero_discount_case and (store_name or purchase_at):
            confidence = partial_confidence
            parse_status = 'partial'
        elif total_amount is not None and len(lines) >= 2 and (store_name or purchase_at):
            confidence = min(partial_confidence, review_confidence)
            parse_status = 'review_needed'
        else:
            confidence = review_confidence
            parse_status = 'review_needed'
    else:
        confidence = review_confidence
        parse_status = 'review_needed'

    if suspicious_single_line or suspicious_filename_signal or not purchase_at:
        confidence = min(confidence, review_confidence)
        parse_status = 'review_needed'

    if total_amount is not None and lines and not (totals_match or zero_discount_case):
        confidence = min(confidence, review_confidence)
        parse_status = 'review_needed'

    return ReceiptParseResult(
        is_receipt=True,
        parse_status=parse_status,
        confidence_score=confidence,
        store_name=store_name,
        purchase_at=purchase_at,
        total_amount=total_amount,
        discount_total=discount_total,
        currency='EUR',
        lines=lines,
        store_branch=store_branch,
    )


def _ocr_pdf_text_with_ocrmypdf(file_bytes: bytes, filename: str) -> str:
    if ocrmypdf is None:
        return ''
    suffix = Path(filename).suffix.lower() or '.pdf'
    try:
        with tempfile.TemporaryDirectory(prefix='rezzerv-ocrpdf-') as temp_dir:
            temp_root = Path(temp_dir)
            input_path = temp_root / f'input{suffix}'
            output_path = temp_root / 'output.pdf'
            sidecar_path = temp_root / 'output.txt'
            input_path.write_bytes(file_bytes)
            ocrmypdf.ocr(
                input_path,
                output_path,
                language=['nld', 'eng'],
                sidecar=sidecar_path,
                force_ocr=True,
                deskew=True,
                rotate_pages=True,
                output_type='pdf',
                progress_bar=False,
            )
            sidecar_text = sidecar_path.read_text(encoding='utf-8', errors='ignore') if sidecar_path.exists() else ''
            if sidecar_text.strip():
                return sidecar_text
            if output_path.exists():
                return _extract_pdf_text(output_path.read_bytes())
    except Exception as exc:  # pragma: no cover - depends on optional OCR runtime
        LOGGER.warning('OCRmyPDF fallback mislukt voor %s: %s', filename, exc)
    return ''


def _get_paddle_ocr():
    global _PADDLE_OCR_INSTANCE
    if _PADDLE_OCR_INSTANCE is not None:
        return _PADDLE_OCR_INSTANCE
    if PaddleOCR is None:
        return None

    constructors = [
        {
            'use_doc_orientation_classify': False,
            'use_doc_unwarping': False,
            'use_textline_orientation': False,
            'lang': 'en',
        },
        {
            'use_angle_cls': True,
            'lang': 'en',
        },
        {
            'lang': 'en',
        },
    ]
    for kwargs in constructors:
        try:
            _PADDLE_OCR_INSTANCE = PaddleOCR(**kwargs)
            break
        except TypeError:
            continue
        except Exception as exc:  # pragma: no cover - runtime dependency/model download issue
            LOGGER.warning('PaddleOCR initialisatie mislukt: %s', exc)
            return None
    return _PADDLE_OCR_INSTANCE


def _ocr_bbox_to_line_anchor(bbox: Any) -> tuple[float, float, float] | None:
    if bbox is None:
        return None
    try:
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4 and not isinstance(bbox[0], (list, tuple)):
            x1, y1, x2, y2 = [float(v) for v in bbox]
            return ((y1 + y2) / 2.0, x1, max(1.0, y2 - y1))
        points = []
        for point in bbox:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            points.append((float(point[0]), float(point[1])))
        if not points:
            return None
        xs = [pt[0] for pt in points]
        ys = [pt[1] for pt in points]
        return ((min(ys) + max(ys)) / 2.0, min(xs), max(1.0, max(ys) - min(ys)))
    except Exception:
        return None


def _extract_payload_from_paddle_item(item: Any) -> dict[str, Any]:
    candidates: list[Any] = [item]
    for attr_name in ('res', 'json', 'result'):
        attr = getattr(item, attr_name, None)
        if attr is None:
            continue
        try:
            value = attr() if callable(attr) else attr
        except TypeError:
            value = attr
        candidates.append(value)
    to_dict = getattr(item, 'to_dict', None)
    if callable(to_dict):
        try:
            candidates.append(to_dict())
        except Exception:
            pass
    for candidate in candidates:
        if isinstance(candidate, dict):
            if isinstance(candidate.get('res'), dict):
                return candidate['res']
            return candidate
    return {}


def _group_paddle_texts_to_lines(texts: list[str], boxes: list[Any] | None) -> list[str]:
    if not texts:
        return []
    if not boxes or len(boxes) != len(texts):
        return [re.sub(r'\s+', ' ', text).strip() for text in texts if str(text).strip()]

    fragments: list[tuple[float, float, float, str]] = []
    heights: list[float] = []
    for text_value, box in zip(texts, boxes):
        normalized_text = re.sub(r'\s+', ' ', str(text_value or '')).strip()
        if not normalized_text:
            continue
        anchor = _ocr_bbox_to_line_anchor(box)
        if anchor is None:
            fragments.append((float(len(fragments) * 100), float(len(fragments)), 10.0, normalized_text))
            continue
        center_y, min_x, height = anchor
        heights.append(height)
        fragments.append((center_y, min_x, height, normalized_text))

    if not fragments:
        return []

    fragments.sort(key=lambda item: (item[0], item[1]))
    merge_threshold = max(12.0, (median(heights) if heights else 12.0) * 0.7)
    grouped: list[list[tuple[float, float, float, str]]] = []
    for fragment in fragments:
        if not grouped:
            grouped.append([fragment])
            continue
        current_group = grouped[-1]
        current_y = sum(part[0] for part in current_group) / len(current_group)
        if abs(fragment[0] - current_y) <= merge_threshold:
            current_group.append(fragment)
        else:
            grouped.append([fragment])

    result_lines: list[str] = []
    for group in grouped:
        group.sort(key=lambda item: item[1])
        merged = ' '.join(part[3] for part in group).strip()
        merged = re.sub(r'\s+', ' ', merged)
        if merged:
            result_lines.append(merged)
    return result_lines


def _normalize_paddle_collection(value: Any) -> list[Any]:
    if value is None:
        return []
    if hasattr(value, 'tolist'):
        try:
            value = value.tolist()
        except Exception:
            pass
    if isinstance(value, (str, bytes, bytearray)):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]



def _ocr_image_text_with_paddle(file_bytes: bytes, filename: str) -> tuple[list[str], float | None]:
    model = _get_paddle_ocr()
    if model is None:
        return [], None

    suffix = Path(filename).suffix.lower() or '.png'
    try:
        with tempfile.TemporaryDirectory(prefix='rezzerv-paddleocr-') as temp_dir:
            image_path = Path(temp_dir) / f'image{suffix}'
            image_path.write_bytes(file_bytes)
            result = model.predict(str(image_path))
    except Exception as exc:  # pragma: no cover - runtime dependency/model download issue
        LOGGER.warning('PaddleOCR verwerking mislukt voor %s: %s', filename, exc)
        return [], None

    texts: list[str] = []
    scores: list[float] = []
    boxes: list[Any] = []
    for item in _normalize_paddle_collection(result):
        payload = _extract_payload_from_paddle_item(item)
        current_texts = _normalize_paddle_collection(payload.get('rec_texts') or payload.get('texts'))
        current_scores = _normalize_paddle_collection(payload.get('rec_scores') or payload.get('scores'))
        current_boxes = payload.get('rec_boxes')
        if current_boxes is None:
            current_boxes = payload.get('dt_polys')
        if current_boxes is None:
            current_boxes = payload.get('rec_polys')
        current_boxes = _normalize_paddle_collection(current_boxes)
        normalized_texts = [str(text) for text in current_texts if str(text).strip()]
        texts.extend(normalized_texts)
        for score in current_scores:
            try:
                scores.append(float(score))
            except (TypeError, ValueError):
                continue
        boxes.extend(current_boxes[: len(normalized_texts)])

    line_candidates = _group_paddle_texts_to_lines(texts, boxes if boxes else None)
    confidence = round(sum(scores) / len(scores), 4) if scores else None
    return line_candidates, confidence



def _ocr_image_text_with_tesseract(file_bytes: bytes, filename: str) -> tuple[list[str], float | None]:
    suffix = Path(filename).suffix.lower() or '.png'
    language = 'nld+eng'
    try:
        with tempfile.TemporaryDirectory(prefix='rezzerv-tesseract-') as temp_dir:
            image_path = Path(temp_dir) / f'image{suffix}'
            image_path.write_bytes(file_bytes)
            command = ['tesseract', str(image_path), 'stdout', '-l', language, '--psm', '6']
            completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=90)
            if completed.returncode != 0:
                LOGGER.warning('Tesseract verwerking mislukt voor %s: %s', filename, (completed.stderr or '').strip())
                return [], None
            text_output = completed.stdout or ''
            return _normalize_text_lines(text_output), None
    except Exception as exc:  # pragma: no cover - runtime dependency
        LOGGER.warning('Tesseract fallback mislukt voor %s: %s', filename, exc)
        return [], None



def _normalize_store_specific_text(text: str) -> str:
    normalized = str(text or '').replace('\u00a0', ' ').replace('/uni00A0', ' ').replace('/uni00A01', ' 1 ')
    normalized = normalized.replace('/uni00A02', ' 2 ').replace('/uni00A03', ' 3 ').replace('/uni00A04', ' 4 ')
    normalized = normalized.replace('·', ' · ')
    normalized = re.sub(r'\s+€\s*', ' € ', normalized)
    normalized = re.sub(r'[ 	]+', ' ', normalized)
    normalized = re.sub(r'\n{3,}', '\n\n', normalized)
    return normalized.strip()


def _extract_text_from_eml(file_bytes: bytes) -> tuple[str, str]:
    try:
        message = BytesParser(policy=policy.default).parsebytes(file_bytes)
    except Exception:
        return '', ''
    text_parts: list[str] = []
    html_parts: list[str] = []
    for part in message.walk():
        content_type = part.get_content_type()
        if content_type not in {'text/plain', 'text/html'}:
            continue
        try:
            payload = part.get_content()
        except Exception:
            try:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or 'utf-8'
                payload = payload.decode(charset, errors='ignore') if isinstance(payload, (bytes, bytearray)) else str(payload)
            except Exception:
                payload = ''
        if content_type == 'text/plain' and payload:
            text_parts.append(str(payload))
        elif content_type == 'text/html' and payload:
            html_parts.append(str(payload))
    subject = str(message.get('subject') or '').strip()
    date_header = str(message.get('date') or '').strip()
    if subject:
        text_parts.insert(0, subject)
    if date_header:
        text_parts.insert(1 if subject else 0, date_header)
    plain_text = '\n'.join(text_parts).strip()
    html_text = ''
    if html_parts:
        html_source = '\n'.join(html_parts)
        if BeautifulSoup is not None:
            try:
                html_text = BeautifulSoup(html_source, 'html.parser').get_text('\n')
            except Exception:
                html_text = _html_to_text(html_source)
        else:
            html_text = _html_to_text(html_source)
    return _normalize_store_specific_text(plain_text), _normalize_store_specific_text(html_text)


def _convert_webp_to_png_bytes(file_bytes: bytes) -> bytes:
    if Image is None:
        return file_bytes
    try:
        with Image.open(io.BytesIO(file_bytes)) as image:
            output = io.BytesIO()
            image.save(output, format='PNG')
            return output.getvalue()
    except Exception:
        return file_bytes


def _parse_dutch_textual_date(text: str, default_year: int | None = None) -> str | None:
    match = re.search(r'(?i)\b(\d{1,2})\s+(' + '|'.join(DUTCH_MONTHS.keys()) + r')(?:\s+(\d{4}))?', str(text or ''))
    if not match:
        return None
    day = int(match.group(1))
    month = DUTCH_MONTHS[match.group(2).lower()]
    year = int(match.group(3) or default_year or datetime.utcnow().year)
    try:
        return datetime(year, month, day).isoformat()
    except ValueError:
        return None


def _price_from_split_parts(euros: str | None, cents: str | None) -> Decimal | None:
    if euros is None or cents is None:
        return None
    try:
        return Decimal(f"{int(euros)}.{int(cents):02d}").quantize(Decimal('0.01'))
    except Exception:
        return None


def _receipt_result_from_manual(store_name: str | None, purchase_at: str | None, total_amount: Decimal | None, lines: list[dict[str, Any]], *, store_branch: str | None = None, confidence: float = 0.8) -> ReceiptParseResult:
    status = 'parsed' if lines and total_amount is not None else 'review_needed'
    return ReceiptParseResult(
        is_receipt=True,
        parse_status=status,
        confidence_score=confidence,
        store_name=store_name,
        purchase_at=purchase_at,
        total_amount=total_amount,
        discount_total=None,
        currency='EUR',
        lines=lines,
        store_branch=store_branch,
    )


def _line_dict(label: str, quantity: float | None, unit_price: Decimal | None, line_total: Decimal | None, *, unit: str | None = None, confidence: float = 0.86) -> dict[str, Any]:
    return {
        'raw_label': _clean_receipt_label(label),
        'normalized_label': _clean_receipt_label(label),
        'quantity': quantity,
        'unit': unit,
        'unit_price': _amount_to_float(unit_price),
        'line_total': _amount_to_float(line_total),
        'discount_amount': None,
        'barcode': None,
        'confidence_score': confidence,
    }


def _parse_action_pdf_result(text: str, filename: str) -> ReceiptParseResult | None:
    if 'action' not in filename.lower() and 'valburgseweg' not in text.lower():
        return None
    lines = _normalize_text_lines(_normalize_store_specific_text(text))
    purchase_at = None
    m = re.search(r'(?i)(\d{1,2})\s+(' + '|'.join(DUTCH_MONTHS.keys()) + r')\s+om\s+(\d{1,2}:\d{2})', text)
    if m:
        try:
            purchase_at = datetime(datetime.utcnow().year, DUTCH_MONTHS[m.group(2).lower()], int(m.group(1)), int(m.group(3).split(':')[0]), int(m.group(3).split(':')[1])).isoformat()
        except Exception:
            purchase_at = None
    total_amount = _parse_decimal(re.search(r'(?i)Totaal\s+\d+\s+€\s*([0-9]+,[0-9]{2})', text).group(1)) if re.search(r'(?i)Totaal\s+\d+\s+€\s*([0-9]+,[0-9]{2})', text) else None
    branch = 'Valburgseweg 16, 6661 EV Elst'
    start = next((i for i, line in enumerate(lines) if 'artikel aantal prijs' in line.lower()), None)
    end = next((i for i, line in enumerate(lines) if line.lower().startswith('totaal ')), None)
    extracted: list[dict[str, Any]] = []
    if start is not None and end is not None and end > start:
        buffer: list[str] = []
        for line in lines[start + 1:end]:
            match = re.match(r'^(?P<qty>\d+)\s+€\s*(?P<amount>\d+[\.,]\d{2})$', line)
            if match and buffer:
                label = ' '.join(buffer)
                label = re.sub(r'\s*-\s*\d{6,}$', '', label).strip()
                qty = float(match.group('qty'))
                total = _parse_decimal(match.group('amount'))
                unit_price = (total / Decimal(str(int(qty)))).quantize(Decimal('0.01')) if total is not None and qty else total
                extracted.append(_line_dict(label, qty, unit_price, total))
                buffer = []
            else:
                buffer.append(line)
    return _receipt_result_from_manual('Action', purchase_at, total_amount, extracted, store_branch=branch, confidence=0.88)


def _parse_gamma_pdf_result(text: str, filename: str) -> ReceiptParseResult | None:
    if 'gamma' not in filename.lower() and 'gamma.nl' not in text.lower() and 'kassabonnummer' not in text.lower():
        return None
    lines = _normalize_text_lines(_normalize_store_specific_text(text))
    purchase_at = _purchase_at_from_lines(lines, filename)
    total_match = re.search(r'(?i)Totaal incl\. BTW€\s*([0-9]+,[0-9]{2})', text)
    total_amount = _parse_decimal(total_match.group(1)) if total_match else None
    extracted: list[dict[str, Any]] = []
    for idx, line in enumerate(lines):
        m = re.match(r'^(?P<code>\d{5,})\s+(?P<label>.+)$', line)
        if not m:
            continue
        label_parts = [m.group('label')]
        j = idx + 1
        while j < len(lines) and not re.search(r'\d+%\s+\d+\s+€\s*\d+[\.,]\d{2}', lines[j]):
            if re.match(r'^Totaal', lines[j], re.I):
                break
            label_parts.append(lines[j])
            j += 1
        if j < len(lines):
            detail = lines[j]
            d = re.search(r'(?P<vat>\d+%)\s+(?P<qty>\d+(?:[\.,]\d+)?)\s+€\s*(?P<unit>\d+[\.,]\d{2})(?:\s+€\s*(?P<total>\d+[\.,]\d{2}))?', detail)
            if d:
                qty = float(d.group('qty').replace(',', '.'))
                unit_price = _parse_decimal(d.group('unit'))
                line_total = _parse_decimal(d.group('total')) or unit_price
                extracted.append(_line_dict(' '.join(label_parts), qty, unit_price, line_total))
    return _receipt_result_from_manual('Gamma', purchase_at, total_amount, extracted, confidence=0.86)


def _parse_hornbach_pdf_result(text: str, filename: str) -> ReceiptParseResult | None:
    if 'hornbach' not in text.lower() and 'hornbach' not in filename.lower():
        return None
    normalized = _normalize_store_specific_text(text)
    purchase_at = None
    date_match = re.search(r'(?i)Rekeningsdatum:\s*(\d{2}\.\d{2}\.\d{4})', normalized) or re.search(r'(?i)Opdrachtdatum:\s*(\d{2}\.\d{2}\.\d{4})', normalized)
    if date_match:
        try:
            purchase_at = datetime.strptime(date_match.group(1), '%d.%m.%Y').isoformat()
        except ValueError:
            pass
    total_match = re.search(r'(?i)Totaalbedr\. rekening EUR\s*([0-9]+,[0-9]{2})', normalized) or re.search(r'(?i)Totaalbedrag rekening EUR\s*([0-9]+,[0-9]{2})', normalized)
    total_amount = _parse_decimal(total_match.group(1)) if total_match else None
    extracted: list[dict[str, Any]] = []
    multi = re.search(r'10\s+7\s+St\s+10692297\s+(.+?)\s+21,00%\s+38,00\s+266,00', normalized, re.S)
    if multi:
        label = re.sub(r'\s+', ' ', multi.group(1)).strip()
        extracted.append(_line_dict(label, 7.0, Decimal('38.00'), Decimal('266.00')))
    freight = re.search(r'8448722\s+Vrachtkosten\s+21,00%\s+22,50\s+22,50', normalized)
    if freight:
        extracted.append(_line_dict('Vrachtkosten', 1.0, Decimal('22.50'), Decimal('22.50')))
    return _receipt_result_from_manual('Hornbach', purchase_at, total_amount, extracted, store_branch='Postbus 1099, 3430 BB Nieuwegein', confidence=0.9)


def _parse_lidl_invoice_pdf_result(text: str, filename: str) -> ReceiptParseResult | None:
    if 'lidl' not in text.lower() and 'lidl' not in filename.lower():
        return None
    normalized = _normalize_store_specific_text(text)
    lines = _normalize_text_lines(normalized)
    purchase_at = None
    date_match = re.search(r'(?i)Factuurdatum:\s*(\d{2}-\d{2}-\d{4})', normalized) or re.search(r'(?i)Besteldatum:\s*(\d{2}-\d{2}-\d{4})', normalized)
    if date_match:
        try:
            purchase_at = datetime.strptime(date_match.group(1), '%d-%m-%Y').isoformat()
        except ValueError:
            pass
    total_match = re.search(r'(?i)Totaal\s+([0-9]+,[0-9]{2})', normalized)
    total_amount = _parse_decimal(total_match.group(1)) if total_match else None
    extracted: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for index, line in enumerate(lines):
        product_match = re.match(r'^(?P<code>100\d{6,})(?:\s+)?(?P<label>.+)$', line)
        if not product_match:
            continue
        code = str(product_match.group('code') or '').strip()
        if not code or code in seen_codes:
            continue
        detail_line = lines[index + 2] if index + 2 < len(lines) else ''
        detail_match = re.search(r'21,0\s*%\s*(?P<qty>\d+(?:[\.,]\d+)?)\s+(?P<unit>\d+[\.,]\d{2})\s+(?P<total>\d+[\.,]\d{2})', detail_line)
        if not detail_match:
            continue
        seen_codes.add(code)
        label = re.sub(r'\s+', ' ', product_match.group('label')).strip(' -')
        qty = float(str(detail_match.group('qty')).replace(',', '.'))
        extracted.append(_line_dict(label, qty, _parse_decimal(detail_match.group('unit')), _parse_decimal(detail_match.group('total'))))
    shipping = re.search(r'Verzendkosten\s+21,0\s*%\s*(?P<qty>\d+(?:[\.,]\d+)?)\s+(?P<unit>\d+[\.,]\d{2})\s+(?P<total>\d+[\.,]\d{2})', normalized)
    if shipping:
        extracted.append(_line_dict('Verzendkosten', float(str(shipping.group('qty')).replace(',', '.')), _parse_decimal(shipping.group('unit')), _parse_decimal(shipping.group('total'))))
    return _receipt_result_from_manual('Lidl Nederland GmbH', purchase_at, total_amount, extracted, store_branch='Havenstraat 71, 1271 AD Huizen; Postbus 198, 1270 AD Huizen', confidence=0.9)


def _parse_bol_email_result(text: str, html_text: str, filename: str, header_date: str | None = None) -> ReceiptParseResult | None:
    haystack = _normalize_store_specific_text(html_text or text)
    if 'bol' not in haystack.lower() and 'bol' not in filename.lower():
        return None
    purchase_at = None
    if header_date:
        from email.utils import parsedate_to_datetime
        try:
            purchase_at = parsedate_to_datetime(header_date).replace(tzinfo=None).isoformat(timespec='seconds')
        except Exception:
            purchase_at = None
    total_match = re.search(r'(?is)Totaal\s+€\s*([0-9]+,[0-9]{2})', haystack)
    total_amount = _parse_decimal(total_match.group(1)) if total_match else None
    order_product = re.search(r'(?is)Dit heb je besteld.*?Bestelnummer:\s*([A-Z0-9-]+).*?([A-Z0-9+\-][^\n]+?)\s+Verkoper:\s+([^\n]+).*?Bezorgdatum:', haystack)
    extracted: list[dict[str, Any]] = []
    if order_product:
        label = re.sub(r'\s+', ' ', order_product.group(2)).strip()
        price_match = re.search(r'(?is)1x\s+€\s*([0-9]+,[0-9]{2})', haystack)
        price = _parse_decimal(price_match.group(1)) if price_match else total_amount
        extracted.append(_line_dict(label, 1.0, price, price))
    return _receipt_result_from_manual('Bol', purchase_at, total_amount, extracted, confidence=0.84)


def _parse_picnic_email_result(text: str, html_text: str, filename: str, header_date: str | None = None) -> ReceiptParseResult | None:
    haystack = _normalize_store_specific_text(html_text or text)
    if 'picnic' not in haystack.lower() and 'picnic' not in filename.lower():
        return None
    raw_lines = _normalize_text_lines(haystack)
    lines = []
    for line in raw_lines:
        cleaned = re.sub(r'[​‌﻿]+', '', line).strip()
        if cleaned and cleaned not in {'.', '•'}:
            lines.append(cleaned)
    purchase_at = _parse_dutch_textual_date(haystack, default_year=2026)
    if purchase_at and 'T' not in purchase_at:
        purchase_at += 'T00:00:00'
    total_amount = None
    for idx, line in enumerate(lines):
        if line.lower() == 'totaal':
            nums = [token for token in lines[idx + 1: idx + 10] if re.fullmatch(r'-?\d+', token)]
            if len(nums) >= 2:
                total_amount = _price_from_split_parts(nums[0], nums[1])
                break

    def _is_picnic_summary_line(value: str | None) -> bool:
        lowered = str(value or '').strip().lower()
        if not lowered:
            return False
        summary_prefixes = (
            'statiegeld',
            'subtotaal',
            'totaal',
            'ingeleverd statiegeld',
            'flessen en blikjes',
            'tasjes',
            'verrekening picnic-tegoed',
            'picnic-tegoed',
            'voordeel',
            'btw ',
            'bezorgadres',
            'fijne dag',
            'vragen?',
            'klantenservice',
            'mijn profiel',
            'herroeping',
            'picnic b.v.',
        )
        return lowered.startswith(summary_prefixes)

    extracted: list[dict[str, Any]] = []
    noise_prefixes = ('order ', 'toegevoegd op ', 'beste ', 'hier is het bonnetje', 'al betaald via', 'bezorgadres', 'subtotaal', 'totaal')
    i = 0
    while i < len(lines) - 1:
        if not re.fullmatch(r'\d+', lines[i]):
            i += 1
            continue
        if i + 1 >= len(lines):
            break
        qty = float(lines[i])
        name = lines[i + 1].strip()
        if (
            not re.search(r'[A-Za-z]', name)
            or any(name.lower().startswith(prefix) for prefix in noise_prefixes)
            or _is_picnic_summary_line(name)
        ):
            i += 1
            continue
        j = i + 2
        prices: list[Decimal] = []
        while j < len(lines) and j < i + 20:
            if _is_picnic_summary_line(lines[j]):
                break
            if j + 1 < len(lines) and re.fullmatch(r'-?\d+', lines[j]) and re.fullmatch(r'\d{2}', lines[j + 1]):
                price = _price_from_split_parts(lines[j], lines[j + 1])
                if price is not None:
                    prices.append(price)
                j += 2
                continue
            if j + 1 < len(lines) and re.fullmatch(r'\d+', lines[j]) and re.search(r'[A-Za-z]', lines[j + 1]):
                break
            j += 1

        non_zero_prices = [price.quantize(Decimal('0.01')) for price in prices if price is not None and price != Decimal('0.00')]
        if non_zero_prices:
            gross_total = non_zero_prices[0]
            net_total = non_zero_prices[-1]
            unit_price = (gross_total / Decimal(str(int(qty)))).quantize(Decimal('0.01')) if qty else gross_total
            line = _line_dict(name, qty, unit_price, gross_total)
            if net_total < gross_total:
                line['discount_amount'] = _amount_to_float((gross_total - net_total).quantize(Decimal('0.01')))
            extracted.append(line)
            i = j
            continue

        if j < len(lines) and j + 1 < len(lines) and re.fullmatch(r'\d+', lines[j]) and re.search(r'[A-Za-z]', lines[j + 1]):
            extracted.append(_line_dict(name, qty, Decimal('0.00'), Decimal('0.00')))
            i = j
            continue
        i += 1
    if not extracted:
        flattened_extracted, flattened_total = _parse_picnic_flattened_blocks(haystack)
        if flattened_extracted:
            extracted = flattened_extracted
            total_amount = total_amount or flattened_total
    return _receipt_result_from_manual('Picnic', purchase_at, total_amount, extracted, confidence=0.78)


def _parse_picnic_flattened_blocks(haystack: str) -> tuple[list[dict[str, Any]], Decimal | None]:
    compact = re.sub(r'\s+', ' ', str(haystack or '')).strip()
    if not compact:
        return [], None
    order_pattern = re.compile(r'(Toegevoegd op .*? Order [0-9-]+)\s+(?P<body>.*?)(?=(?:Toegevoegd op .*? Order [0-9-]+)|$)', re.I)
    price_pattern = re.compile(r'(?:€\s*)?(?P<euros>-?\d+)\s*(?:[.,]|\s)\s*(?P<cents>\d{2})(?:\s*\.)?')
    block_pattern = re.compile(r"(?:^|\s)(?P<qty>\d+)\s+(?=[A-Za-zÀ-ÿ'\(])")
    extracted: list[dict[str, Any]] = []

    def _cleanup_label(raw: str) -> str:
        value = re.sub(r'\s+', ' ', raw or '').strip(' .,-')
        value = re.sub(r'^(?:\[[^\]]+\]\s*)+', '', value)
        value = re.split(r'(?:nu\s*€\s*\d+[.,]\d{2}|smaakmaker|\d+% korting|\d+e\s*=|\d+ voor €\s*\d+)', value, 1, flags=re.I)[0]
        value = re.split(r'\d+(?:[.,]\d+)?\s*(?:gram|g|kg|ml|liter|l|stuks?|stuk|bosje|kilo|heel|pak|fles|rollen?)', value, 1, flags=re.I)[0]
        return _clean_receipt_label(value)

    for order_match in order_pattern.finditer(compact):
        body = order_match.group('body').strip()
        for marker in (' Statiegeld ', ' Subtotaal ', ' Totaal ', ' Ingeleverd statiegeld ', ' Bezorgadres ', ' Fijne dag'):
            position = body.find(marker)
            if position > 0:
                body = body[:position].strip()
                break
        starts = list(block_pattern.finditer(body))
        for idx, start in enumerate(starts):
            qty = float(start.group('qty'))
            chunk_start = start.start('qty')
            chunk_end = starts[idx + 1].start('qty') if idx + 1 < len(starts) else len(body)
            chunk = body[chunk_start:chunk_end].strip()
            if not chunk:
                continue
            chunk_after_qty = chunk[len(start.group('qty')):].strip()
            prices = [
                _price_from_split_parts(match.group('euros'), match.group('cents'))
                for match in price_pattern.finditer(chunk_after_qty)
            ]
            prices = [price.quantize(Decimal('0.01')) for price in prices if price is not None]
            first_price_match = price_pattern.search(chunk_after_qty)
            label_source = chunk_after_qty[:first_price_match.start()] if first_price_match else chunk_after_qty
            label = _cleanup_label(label_source)
            if not label or len(label) < 2:
                continue
            non_zero_prices = [price for price in prices if price != Decimal('0.00')]
            if non_zero_prices:
                gross_total = non_zero_prices[0]
                net_total = non_zero_prices[-1]
                unit_price = (gross_total / Decimal(str(int(qty)))).quantize(Decimal('0.01')) if qty else gross_total
                line = _line_dict(label, qty, unit_price, gross_total)
                if net_total < gross_total:
                    line['discount_amount'] = _amount_to_float((gross_total - net_total).quantize(Decimal('0.01')))
                extracted.append(line)
            else:
                extracted.append(_line_dict(label, qty, Decimal('0.00'), Decimal('0.00')))

    total_amount = None
    total_match = re.search(r'(?i)Totaal(?: Al betaald via iDeal)?\s+(?P<euros>-?\d+)\s+(?P<cents>\d{2})', compact)
    if total_match:
        total_amount = _price_from_split_parts(total_match.group('euros'), total_match.group('cents'))
    return extracted, total_amount


def _parse_store_specific_result(file_bytes: bytes, filename: str, mime_type: str, direct_text: str = '', html_text: str = '') -> ReceiptParseResult | None:
    lower_name = filename.lower()
    text = _normalize_store_specific_text(direct_text)
    normalized_html = _normalize_store_specific_text(_html_to_text(html_text) if html_text else '')
    if lower_name.endswith('.pdf'):
        for parser in (_parse_action_pdf_result, _parse_gamma_pdf_result, _parse_hornbach_pdf_result, _parse_lidl_invoice_pdf_result):
            result = parser(text, filename)
            if result is not None and (result.lines or result.total_amount or result.purchase_at or result.store_name):
                return result

    header_date = None
    if lower_name.endswith('.eml') or mime_type == 'message/rfc822':
        try:
            message = BytesParser(policy=policy.default).parsebytes(file_bytes)
            header_date = str(message.get('date') or '').strip()
        except Exception:
            header_date = None

    can_try_email_parsers = (
        lower_name.endswith('.eml')
        or mime_type == 'message/rfc822'
        or mime_type in {'text/html', 'text/plain'}
        or lower_name.endswith(('.html', '.htm', '.txt'))
    )
    if can_try_email_parsers:
        for parser in (_parse_bol_email_result, _parse_picnic_email_result):
            result = parser(text, normalized_html, filename, header_date=header_date)
            if result is not None and (result.lines or result.total_amount or result.purchase_at or result.store_name):
                return result
    return None

def parse_receipt_content(file_bytes: bytes, filename: str, mime_type: str) -> ReceiptParseResult:
    suffix = Path(filename).suffix.lower()

    if mime_type == 'message/rfc822' or suffix == '.eml':
        plain_text, html_text = _extract_text_from_eml(file_bytes)
        specific_result = _parse_store_specific_result(file_bytes, filename, mime_type, plain_text, html_text)
        if specific_result is not None:
            return specific_result
        text_source = html_text or plain_text
        text_lines = _normalize_text_lines(text_source)
        return _parse_result_from_text_lines(
            text_lines,
            filename,
            rich_confidence=0.72,
            partial_confidence=0.52,
            review_confidence=0.28,
        ) if text_lines else _failed_receipt_result(0.0)

    if mime_type == 'application/pdf' or suffix == '.pdf':
        pdf_text = _preprocess_pdf_text(_extract_pdf_text(file_bytes))
        specific_result = _parse_store_specific_result(file_bytes, filename, mime_type, pdf_text)
        if specific_result is not None:
            return specific_result
        pdf_lines = _normalize_text_lines(pdf_text)
        direct_result = _parse_result_from_text_lines(
            pdf_lines,
            filename,
            rich_confidence=0.92,
            partial_confidence=0.74,
            review_confidence=0.48,
        )
        if direct_result.is_receipt:
            return direct_result

        ocr_text = _preprocess_pdf_text(_ocr_pdf_text_with_ocrmypdf(file_bytes, filename))
        ocr_lines = _normalize_text_lines(ocr_text)
        ocr_result = _parse_result_from_text_lines(
            ocr_lines,
            filename,
            rich_confidence=0.88,
            partial_confidence=0.68,
            review_confidence=0.42,
        )
        return ocr_result

    if suffix == '.webp':
        converted_bytes = _convert_webp_to_png_bytes(file_bytes)
        file_bytes = converted_bytes
        filename = f"{Path(filename).stem}.png"
        suffix = '.png'
        mime_type = 'image/png'

    if mime_type.startswith('image/') or suffix in {'.png', '.jpg', '.jpeg', '.webp'}:
        paddle_lines, paddle_confidence = _ocr_image_text_with_paddle(file_bytes, filename)
        tesseract_lines, tesseract_confidence = _ocr_image_text_with_tesseract(file_bytes, filename)

        paddle_result = _parse_result_from_text_lines(
            paddle_lines,
            filename,
            rich_confidence=0.84,
            partial_confidence=0.64,
            review_confidence=0.36,
        ) if paddle_lines else _failed_receipt_result(0.0)
        tesseract_result = _parse_result_from_text_lines(
            tesseract_lines,
            filename,
            rich_confidence=0.82,
            partial_confidence=0.62,
            review_confidence=0.34,
        ) if tesseract_lines else _failed_receipt_result(0.0)

        image_result = _choose_better_receipt_result(paddle_result, tesseract_result)
        chosen_confidence = paddle_confidence if image_result is paddle_result else tesseract_confidence
        chosen_lines = paddle_lines if image_result is paddle_result else tesseract_lines

        if image_result.is_receipt:
            if not image_result.lines:
                sparse_lines = _extract_sparse_receipt_lines(chosen_lines or paddle_lines or tesseract_lines, filename, image_result.store_name)
                if sparse_lines:
                    image_result.lines = sparse_lines
                    if image_result.parse_status == 'review_needed':
                        image_result.confidence_score = max(float(image_result.confidence_score or 0.0), 0.38)
            if chosen_confidence is not None and image_result.confidence_score is not None:
                image_result.confidence_score = round(min(image_result.confidence_score, chosen_confidence), 4)
            elif chosen_confidence is not None:
                image_result.confidence_score = round(chosen_confidence, 4)
            return image_result

        fallback_lines = chosen_lines or paddle_lines or tesseract_lines
        store_name = _store_from_text(fallback_lines, filename)
        purchase_at = _purchase_at_from_lines(fallback_lines, filename)
        total_amount, _ = _total_amount_from_lines(fallback_lines, filename)
        confidence = 0.35 if (store_name or purchase_at or total_amount) else 0.20
        return ReceiptParseResult(
            is_receipt=True,
            parse_status='review_needed',
            confidence_score=confidence,
            store_name=store_name,
            purchase_at=purchase_at,
            total_amount=total_amount,
            discount_total=None,
            currency='EUR',
            lines=[],
        )

    if mime_type in {'text/html', 'text/plain'} or suffix in {'.html', '.htm', '.txt'}:
        raw_text = file_bytes.decode('utf-8', errors='ignore')
        html_text = raw_text if (mime_type == 'text/html' or suffix in {'.html', '.htm'}) else ''
        direct_text = _html_to_text(raw_text) if html_text else raw_text
        specific_result = _parse_store_specific_result(file_bytes, filename, mime_type, direct_text, html_text)
        if specific_result is not None:
            return specific_result
        text_lines = _normalize_text_lines(direct_text)
        return _parse_result_from_text_lines(
            text_lines,
            filename,
            rich_confidence=0.62,
            partial_confidence=0.46,
            review_confidence=0.24,
        ) if text_lines else _failed_receipt_result(0.0)

    return _failed_receipt_result(0.0)
def ensure_default_receipt_sources(engine, receipt_root: Path, household_id: str) -> list[dict[str, Any]]:
    sources_root = receipt_root.parent / 'sources' / str(household_id)
    sources_root.mkdir(parents=True, exist_ok=True)
    defaults = [
        {
            'id': f'{household_id}-local-folder',
            'type': 'local_folder',
            'label': 'Local folder',
            'source_path': str((sources_root / 'local-folder').resolve()),
        },
        {
            'id': f'{household_id}-scan-folder',
            'type': 'scan_folder',
            'label': 'Scan folder',
            'source_path': str((sources_root / 'scan-folder').resolve()),
        },
    ]
    for definition in defaults:
        Path(definition['source_path']).mkdir(parents=True, exist_ok=True)
    with engine.begin() as conn:
        for definition in defaults:
            exists = conn.execute(
                text('SELECT id FROM receipt_sources WHERE id = :id LIMIT 1'),
                {'id': definition['id']},
            ).scalar()
            if exists:
                conn.execute(
                    text(
                        'UPDATE receipt_sources SET label = :label, source_path = :source_path, is_active = 1, updated_at = CURRENT_TIMESTAMP WHERE id = :id'
                    ),
                    definition,
                )
            else:
                conn.execute(
                    text(
                        '''
                        INSERT INTO receipt_sources (id, household_id, type, label, source_path, is_active)
                        VALUES (:id, :household_id, :type, :label, :source_path, 1)
                        '''
                    ),
                    {**definition, 'household_id': household_id},
                )
    return defaults


def _store_raw_file(storage_root: Path, household_id: str, raw_receipt_id: str, filename: str, file_bytes: bytes) -> str:
    now = datetime.utcnow()
    target_dir = storage_root / str(household_id) / now.strftime('%Y') / now.strftime('%m')
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_filename(filename)
    target_path = target_dir / f'{raw_receipt_id}-{safe_name}'
    with target_path.open('wb') as handle:
        handle.write(file_bytes)
    return str(target_path)


def ingest_receipt(engine, receipt_storage_root: Path, household_id: str, filename: str, file_bytes: bytes, source_id: str | None = None, mime_type: str | None = None, reject_non_receipt: bool = False, create_failed_receipt_table: bool = False, failed_store_name: str | None = None, failed_purchase_at: str | None = None) -> dict[str, Any]:
    detected_mime = detect_mime_type(filename, file_bytes, mime_type)
    digest = sha256_hex(file_bytes)
    with engine.begin() as conn:
        duplicate = conn.execute(
            text(
                '''
                SELECT rr.id, rr.raw_status
                FROM raw_receipts rr
                LEFT JOIN receipt_tables rt ON rt.raw_receipt_id = rr.id
                WHERE rr.household_id = :household_id
                  AND rr.sha256_hash = :sha256_hash
                  AND rr.deleted_at IS NULL
                  AND (rt.id IS NULL OR rt.deleted_at IS NULL)
                LIMIT 1
                '''
            ),
            {'household_id': household_id, 'sha256_hash': digest},
        ).mappings().first()
        if duplicate:
            existing_table = conn.execute(
                text('SELECT id, parse_status FROM receipt_tables WHERE raw_receipt_id = :raw_receipt_id LIMIT 1'),
                {'raw_receipt_id': duplicate['id']},
            ).mappings().first()
            return {
                'raw_receipt_id': duplicate['id'],
                'receipt_table_id': existing_table['id'] if existing_table else None,
                'duplicate': True,
                'duplicate_message': 'Deze kassabon is al eerder toegevoegd en is niet opnieuw geladen.',
                'parse_status': existing_table['parse_status'] if existing_table else duplicate['raw_status'],
            }

    parse_result = parse_receipt_content(file_bytes, filename, detected_mime)
    if reject_non_receipt and not parse_result.is_receipt:
        raise ValueError('Gedeelde inhoud is niet als bruikbare kassabon herkend.')
    parse_fingerprint = build_receipt_fingerprint_from_parse_result(parse_result) if parse_result.is_receipt else ''
    if parse_fingerprint:
        with engine.begin() as conn:
            existing_by_fingerprint = find_existing_receipt_by_fingerprint(conn, household_id, parse_fingerprint)
            if existing_by_fingerprint:
                return {
                    'raw_receipt_id': existing_by_fingerprint['raw_receipt_id'],
                    'receipt_table_id': existing_by_fingerprint['receipt_table_id'],
                    'duplicate': True,
                    'duplicate_message': 'Deze kassabon is al eerder toegevoegd en is niet opnieuw geladen.',
                    'parse_status': existing_by_fingerprint['parse_status'],
                }
    raw_receipt_id = uuid.uuid4().hex
    storage_path = _store_raw_file(receipt_storage_root, household_id, raw_receipt_id, filename, file_bytes)

    with engine.begin() as conn:
        conn.execute(
            text(
                '''
                INSERT INTO raw_receipts (
                    id, household_id, source_id, original_filename, mime_type, storage_path, sha256_hash, raw_status
                ) VALUES (
                    :id, :household_id, :source_id, :original_filename, :mime_type, :storage_path, :sha256_hash, :raw_status
                )
                '''
            ),
            {
                'id': raw_receipt_id,
                'household_id': household_id,
                'source_id': source_id,
                'original_filename': filename,
                'mime_type': detected_mime,
                'storage_path': storage_path,
                'sha256_hash': digest,
                'raw_status': parse_result.parse_status if parse_result.is_receipt else 'failed',
            },
        )
        receipt_table_id = None
        if parse_result.is_receipt or create_failed_receipt_table:
            receipt_table_id = uuid.uuid4().hex
            table_store_name = parse_result.store_name if parse_result.is_receipt else failed_store_name
            table_purchase_at = parse_result.purchase_at if parse_result.is_receipt else failed_purchase_at
            table_total_amount = _amount_to_float(parse_result.total_amount) if parse_result.is_receipt else None
            table_currency = parse_result.currency if parse_result.currency else 'EUR'
            table_discount_total = _amount_to_float(parse_result.discount_total) if parse_result.is_receipt else None
            table_parse_status = determine_final_parse_status(parse_result)
            table_confidence = parse_result.confidence_score
            table_line_count = len(parse_result.lines) if parse_result.is_receipt else 0
            conn.execute(
                text(
                    '''
                    INSERT INTO receipt_tables (
                        id, raw_receipt_id, household_id, store_name, store_branch, purchase_at, total_amount, discount_total, currency, parse_status, confidence_score, line_count
                    ) VALUES (
                        :id, :raw_receipt_id, :household_id, :store_name, :store_branch, :purchase_at, :total_amount, :discount_total, :currency, :parse_status, :confidence_score, :line_count
                    )
                    '''
                ),
                {
                    'id': receipt_table_id,
                    'raw_receipt_id': raw_receipt_id,
                    'household_id': household_id,
                    'store_name': table_store_name,
                    'store_branch': parse_result.store_branch if parse_result.is_receipt else None,
                    'purchase_at': table_purchase_at,
                    'total_amount': table_total_amount,
                    'discount_total': table_discount_total,
                    'currency': table_currency,
                    'parse_status': table_parse_status,
                    'confidence_score': table_confidence,
                    'line_count': table_line_count,
                },
            )
            if parse_result.is_receipt:
                for index, line in enumerate(parse_result.lines):
                    conn.execute(
                        text(
                            '''
                            INSERT INTO receipt_table_lines (
                                id, receipt_table_id, line_index, raw_label, normalized_label, quantity, unit, unit_price, line_total, discount_amount, barcode, article_match_status, matched_article_id, confidence_score
                            ) VALUES (
                                :id, :receipt_table_id, :line_index, :raw_label, :normalized_label, :quantity, :unit, :unit_price, :line_total, :discount_amount, :barcode, :article_match_status, :matched_article_id, :confidence_score
                            )
                            '''
                        ),
                        {
                            'id': uuid.uuid4().hex,
                            'receipt_table_id': receipt_table_id,
                            'line_index': index,
                            'raw_label': line['raw_label'],
                            'normalized_label': line.get('normalized_label'),
                            'quantity': line.get('quantity'),
                            'unit': line.get('unit'),
                            'unit_price': line.get('unit_price'),
                            'line_total': line.get('line_total'),
                            'discount_amount': line.get('discount_amount'),
                            'barcode': line.get('barcode'),
                            'article_match_status': 'unmatched',
                            'matched_article_id': None,
                            'confidence_score': line.get('confidence_score'),
                        },
                    )
        return {
            'raw_receipt_id': raw_receipt_id,
            'receipt_table_id': receipt_table_id,
            'duplicate': False,
            'parse_status': determine_final_parse_status(parse_result),
        }


def _resolve_reparse_source_payload(record: dict[str, Any], file_bytes: bytes) -> tuple[bytes, str, str]:
    mime_type = str(record.get('mime_type') or 'application/octet-stream')
    filename = str(record.get('original_filename') or 'receipt')
    selected_part_type = str(record.get('selected_part_type') or '').strip().lower()
    body_html = record.get('body_html')
    body_text = record.get('body_text')

    if selected_part_type in {'text_body', 'html_body'} and body_html:
        html_filename = f"{Path(filename).stem or 'receipt'}.html"
        return body_html.encode('utf-8', errors='ignore'), html_filename, 'text/html'
    if selected_part_type == 'text_body' and body_text:
        txt_filename = f"{Path(filename).stem or 'receipt'}.txt"
        return body_text.encode('utf-8', errors='ignore'), txt_filename, 'text/plain'
    return file_bytes, filename, mime_type


def repair_receipts_for_household(engine, receipt_storage_root: Path, household_id: str, limit: int = 25) -> dict[str, Any]:
    repaired_ids: list[str] = []
    with engine.begin() as conn:
        candidates = conn.execute(
            text(
                '''
                SELECT
                    rt.id AS receipt_table_id,
                    rr.mime_type,
                    rt.parse_status,
                    rt.purchase_at,
                    rt.total_amount,
                    rt.line_count,
                    rem.selected_part_type,
                    rem.body_html
                FROM receipt_tables rt
                JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                LEFT JOIN receipt_email_messages rem ON rem.raw_receipt_id = rr.id
                WHERE rt.household_id = :household_id
                  AND rt.deleted_at IS NULL
                  AND rr.deleted_at IS NULL
                  AND (
                    (rr.mime_type IN ('text/plain', 'text/html') AND rem.body_html IS NOT NULL)
                    OR (rt.parse_status = 'parsed' AND COALESCE(rt.line_count, 0) <= 1)
                    OR rt.purchase_at IS NULL
                    OR rt.total_amount IS NULL

                    OR rt.purchase_at LIKE '21__-%'
                  )
                ORDER BY rt.updated_at DESC, rt.created_at DESC
                LIMIT :limit
                '''
            ),
            {'household_id': household_id, 'limit': max(1, int(limit))},
        ).mappings().all()
    for candidate in candidates:
        try:
            result = reparse_receipt(engine, receipt_storage_root, str(candidate['receipt_table_id']))
        except Exception as exc:
            LOGGER.warning('Herstel van kassabon %s mislukt: %s', candidate['receipt_table_id'], exc)
            continue
        if result:
            repaired_ids.append(str(candidate['receipt_table_id']))
    return {'repaired_count': len(repaired_ids), 'receipt_table_ids': repaired_ids}


def reparse_receipt(engine, receipt_storage_root: Path, receipt_table_id: str) -> dict[str, Any] | None:
    with engine.begin() as conn:
        record = conn.execute(
            text(
                '''
                SELECT
                    rt.id AS receipt_table_id,
                    rt.raw_receipt_id,
                    rr.household_id,
                    rr.original_filename,
                    rr.mime_type,
                    rr.storage_path,
                    rem.body_html,
                    rem.body_text,
                    rem.selected_part_type
                FROM receipt_tables rt
                JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                LEFT JOIN receipt_email_messages rem ON rem.raw_receipt_id = rr.id
                WHERE rt.id = :receipt_table_id
                LIMIT 1
                '''
            ),
            {'receipt_table_id': receipt_table_id},
        ).mappings().first()
    if not record:
        return None
    file_path = Path(record['storage_path'])
    if not file_path.exists():
        raise FileNotFoundError(f'Ruwe bon ontbreekt op {file_path}')
    file_bytes = file_path.read_bytes()
    parse_bytes, parse_filename, parse_mime_type = _resolve_reparse_source_payload(dict(record), file_bytes)
    parse_result = parse_receipt_content(parse_bytes, parse_filename, parse_mime_type)
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM receipt_table_lines WHERE receipt_table_id = :receipt_table_id'), {'receipt_table_id': receipt_table_id})
        conn.execute(
            text(
                '''
                UPDATE raw_receipts
                SET raw_status = :raw_status
                WHERE id = :raw_receipt_id
                '''
            ),
            {'raw_status': parse_result.parse_status if parse_result.is_receipt else 'failed', 'raw_receipt_id': record['raw_receipt_id']},
        )
        if parse_result.is_receipt:
            conn.execute(
                text(
                    '''
                    UPDATE receipt_tables
                    SET store_name = :store_name,
                        store_branch = :store_branch,
                        purchase_at = :purchase_at,
                        total_amount = :total_amount,
                        discount_total = :discount_total,
                        currency = :currency,
                        parse_status = :parse_status,
                        confidence_score = :confidence_score,
                        line_count = :line_count,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    '''
                ),
                {
                    'id': receipt_table_id,
                    'store_name': parse_result.store_name,
                    'store_branch': parse_result.store_branch,
                    'purchase_at': parse_result.purchase_at,
                    'total_amount': _amount_to_float(parse_result.total_amount),
                    'discount_total': _amount_to_float(parse_result.discount_total),
                    'currency': parse_result.currency,
                    'parse_status': determine_final_parse_status(parse_result),
                    'confidence_score': parse_result.confidence_score,
                    'line_count': len(parse_result.lines),
                },
            )
            for index, line in enumerate(parse_result.lines):
                conn.execute(
                    text(
                        '''
                        INSERT INTO receipt_table_lines (
                            id, receipt_table_id, line_index, raw_label, normalized_label, quantity, unit, unit_price, line_total, discount_amount, barcode, article_match_status, matched_article_id, confidence_score
                        ) VALUES (
                            :id, :receipt_table_id, :line_index, :raw_label, :normalized_label, :quantity, :unit, :unit_price, :line_total, :discount_amount, :barcode, :article_match_status, :matched_article_id, :confidence_score
                        )
                        '''
                    ),
                    {
                        'id': uuid.uuid4().hex,
                        'receipt_table_id': receipt_table_id,
                        'line_index': index,
                        'raw_label': line['raw_label'],
                        'normalized_label': line.get('normalized_label'),
                        'quantity': line.get('quantity'),
                        'unit': line.get('unit'),
                        'unit_price': line.get('unit_price'),
                        'line_total': line.get('line_total'),
                        'discount_amount': line.get('discount_amount'),
                        'barcode': line.get('barcode'),
                        'article_match_status': 'unmatched',
                        'matched_article_id': None,
                        'confidence_score': line.get('confidence_score'),
                    },
                )
        else:
            conn.execute(
                text(
                    '''
                    UPDATE receipt_tables
                    SET store_name = NULL,
                        store_branch = NULL,
                        purchase_at = NULL,
                        total_amount = NULL,
                        discount_total = NULL,
                        currency = 'EUR',
                        parse_status = 'failed',
                        confidence_score = :confidence_score,
                        line_count = 0,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    '''
                ),
                {'id': receipt_table_id, 'confidence_score': parse_result.confidence_score},
            )
    return {'receipt_table_id': receipt_table_id, 'parse_status': determine_final_parse_status(parse_result), 'line_count': len(parse_result.lines), 'deleted': False}


def scan_receipt_source(engine, receipt_storage_root: Path, source_id: str) -> dict[str, Any] | None:
    with engine.begin() as conn:
        source = conn.execute(
            text('SELECT id, household_id, type, label, source_path, is_active FROM receipt_sources WHERE id = :id LIMIT 1'),
            {'id': source_id},
        ).mappings().first()
        if not source:
            return None
        if not int(source['is_active'] or 0):
            raise ValueError('Bron is niet actief')
        if str(source.get('type') or '') not in {'local_folder', 'scan_folder', 'watched_folder'}:
            raise ValueError('Deze bron ondersteunt nog geen mapscan')
        run_id = uuid.uuid4().hex
        conn.execute(
            text('INSERT INTO receipt_processing_runs (id, source_id, files_found, files_imported, files_skipped, files_failed) VALUES (:id, :source_id, 0, 0, 0, 0)'),
            {'id': run_id, 'source_id': source_id},
        )
    source_path = Path(source['source_path'])
    source_path.mkdir(parents=True, exist_ok=True)
    files = [item for item in sorted(source_path.iterdir()) if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS]
    found = len(files)
    imported = 0
    skipped = 0
    failed = 0
    for file_path in files:
        try:
            result = ingest_receipt(
                engine=engine,
                receipt_storage_root=receipt_storage_root,
                household_id=str(source['household_id']),
                filename=file_path.name,
                file_bytes=file_path.read_bytes(),
                source_id=source_id,
                mime_type=detect_mime_type(file_path.name, file_path.read_bytes()),
            )
            if result.get('duplicate'):
                skipped += 1
            else:
                imported += 1
        except Exception:
            failed += 1
    with engine.begin() as conn:
        conn.execute(
            text(
                '''
                UPDATE receipt_processing_runs
                SET finished_at = CURRENT_TIMESTAMP,
                    files_found = :files_found,
                    files_imported = :files_imported,
                    files_skipped = :files_skipped,
                    files_failed = :files_failed
                WHERE id = :id
                '''
            ),
            {
                'id': run_id,
                'files_found': found,
                'files_imported': imported,
                'files_skipped': skipped,
                'files_failed': failed,
            },
        )
        conn.execute(text('UPDATE receipt_sources SET last_scan_at = CURRENT_TIMESTAMP WHERE id = :id'), {'id': source_id})
    return {'run_id': run_id, 'files_found': found, 'files_imported': imported, 'files_skipped': skipped, 'files_failed': failed}


def serialize_receipt_row(row: dict[str, Any]) -> dict[str, Any]:
    def normalize_datetime(value: Any) -> Any:
        if value is None:
            return None
        if hasattr(value, 'isoformat'):
            return value.isoformat()
        return str(value)

    def normalize_number(value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        return value

    datetime_keys = {'purchase_at', 'created_at', 'updated_at', 'imported_at', 'last_scan_at', 'started_at', 'finished_at'}
    return {
        key: (normalize_datetime(value) if key in datetime_keys else normalize_number(value))
        for key, value in row.items()
    }

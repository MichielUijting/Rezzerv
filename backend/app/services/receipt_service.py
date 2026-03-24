from __future__ import annotations

import hashlib
import io
import logging
import unicodedata
import mimetypes
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime
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

SUPPORTED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.html', '.htm', '.txt'}
KNOWN_STORES = [
    'Albert Heijn',
    'AH',
    'Jumbo',
    'Lidl',
    'Plus',
    'ALDI',
    'Aldi',
]
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
    return 'application/octet-stream'


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _html_to_text(value: str) -> str:
    if not value:
        return ''
    normalized = re.sub(r'(?is)<\s*br\s*/?\s*>', '\n', value)
    normalized = re.sub(r'(?is)</\s*p\s*>', '\n', normalized)
    normalized = re.sub(r'(?is)<[^>]+>', ' ', normalized)
    normalized = normalized.replace('&nbsp;', ' ').replace('&euro;', 'EUR')
    normalized = re.sub(r'\s+', ' ', normalized)
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
    return Decimal('0.00') < amount <= Decimal('10000.00')


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
    for store in KNOWN_STORES:
        if store.lower() in haystack:
            return 'Albert Heijn' if store == 'AH' else store.title() if store.islower() else store
    lower_filename = filename.lower()
    for store in KNOWN_STORES:
        if store.lower() in lower_filename:
            return 'Albert Heijn' if store == 'AH' else store.title() if store.islower() else store
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
        if any(token in lowered for token in ('voordeel', 'korting', 'koopzegel', 'koopzegels', 'waarvan', 'bonus box')):
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
    seen_raw_lines: set[str] = set()
    amount_pattern = re.compile(r'(-?\d{1,6}(?:[\.,]\d{2}))')
    for index, raw_line in enumerate(lines):
        normalized = re.sub(r'\s+', ' ', str(raw_line or '')).strip()
        if len(normalized) < 2:
            continue
        lowered = normalized.lower()
        dedupe_key = re.sub(r'\s+', ' ', lowered)
        if dedupe_key in seen_raw_lines:
            continue
        discount_signal = lowered.startswith(('bonus ', 'bbox ', 'korting ', 'actie ')) or any(token in lowered for token in (' korting', 'uw voordeel', 'prijsvoordeel', 'lidl plus'))
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
        seen_raw_lines.add(dedupe_key)
        entries.append({
            'raw_label': label or normalized,
            'normalized_label': _normalize_discount_match_text(label or normalized),
            'amount': amount.quantize(Decimal('0.01')),
            'source_index': index,
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
    ratio = SequenceMatcher(None, discount_compact, line_compact).ratio()
    score += int(round(ratio * 20))
    return score


def _apply_discount_entries(lines: list[dict[str, Any]], discount_entries: list[dict[str, Any]]) -> Decimal | None:
    if not lines or not discount_entries:
        return None if not discount_entries else sum((entry['amount'] for entry in discount_entries), Decimal('0.00')).quantize(Decimal('0.01'))

    def attach_discount(target_index: int, amount: Decimal) -> None:
        current = _parse_decimal(str(lines[target_index].get('discount_amount'))) or Decimal('0.00')
        lines[target_index]['discount_amount'] = _amount_to_float((current + amount).quantize(Decimal('0.01')))

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

        fallback_index = None
        fallback_source_index = -1
        for index, line in enumerate(lines):
            line_source_index = line.get('source_index')
            if line_source_index is None:
                continue
            if line_source_index <= entry_source_index and line_source_index >= fallback_source_index:
                fallback_index = index
                fallback_source_index = line_source_index
        if fallback_index is not None:
            attach_discount(fallback_index, amount)
    return total_discount.quantize(Decimal('0.01')) if total_discount != Decimal('0.00') else None

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


def _should_skip_receipt_line(line: str) -> bool:
    lowered = str(line or '').strip().lower()
    if not lowered:
        return True
    skip_markers = (
        'subtotaal', 'subtotal', 'uw voordeel', 'waarvan', 'bonus box', 'koopzegel', 'koopzegels',
        'totaal korting', 'prijsvoordeel', 'spaaractie', 'spaaracties', 'betaald met', 'bankpas', 'pinnen', 'vpay', 'actie ', 'korting',
        'betaling', 'auth.', 'autorisatie', 'merchant', 'terminal', 'transactie', 'kaartnr', 'kaart:',
        'contactloze', 'contactloos', 'klantticket', 'btw over', 'btw overzicht', 'bedr.excl', 'bedr.incl',
        'bedrag excl', 'bedrag incl', 'filiaal informatie', 'aantal artikelen', 'aantal papieren',
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
    if re.search(r'\d{1,2}:\d{2}\s+\d{1,2}[/-]\d{1,2}[/-]\d{4}', lowered):
        return True
    return False


def _looks_like_item_label_only(line: str) -> bool:
    candidate = re.sub(r'\s+', ' ', str(line or '')).strip()
    if not candidate or _should_skip_receipt_line(candidate):
        return False
    if not re.search(r'[A-Za-z]', candidate):
        return False
    if re.search(r'\d+[\.,]\d{2}', candidate):
        return False
    return True


def _extract_receipt_lines(lines: list[str]) -> list[dict[str, Any]]:
    extracted: list[dict[str, Any]] = []
    qty_first_re = re.compile(
        r'^(?P<qty>\d+(?:[\.,]\d+)?(?:\s*kg)?)\s+(?P<label>.+?)\s+(?P<amount1>-?\d{1,6}(?:[\.,]\d{2}))'
        r'(?:\s+(?P<amount2>-?\d{1,6}(?:[\.,]\d{2})))?(?:\s+(?:EUR|[A-Z]{1,3}))?$',
        re.IGNORECASE,
    )
    label_first_re = re.compile(
        r'^(?P<label>[A-Za-z].*?)\s+(?:(?P<qty>\d+(?:[\.,]\d+)?(?:\s*kg)?)\s*[xX]\s+)?(?P<amount1>-?\d{1,6}(?:[\.,]\d{2}))'
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
        if _should_skip_receipt_line(normalized):
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

        pending_label = normalized if _looks_like_item_label_only(normalized) else None
        pending_line_index = None

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
    lines = _extract_receipt_lines(text_lines)
    discount_total = _apply_discount_entries(lines, _extract_discount_entries(text_lines))
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

    if lines:
        if explicit_total_found and total_amount is not None and len(lines) >= 2 and (store_name or purchase_at):
            confidence = rich_confidence if store_name else partial_confidence
            parse_status = 'parsed'
        elif total_amount is not None and len(lines) >= 2 and (store_name or purchase_at):
            confidence = partial_confidence
            parse_status = 'partial'
        else:
            confidence = review_confidence
            parse_status = 'review_needed'
    else:
        confidence = review_confidence
        parse_status = 'review_needed'

    if suspicious_single_line or suspicious_filename_signal or not purchase_at:
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

def parse_receipt_content(file_bytes: bytes, filename: str, mime_type: str) -> ReceiptParseResult:
    suffix = Path(filename).suffix.lower()

    if mime_type == 'application/pdf' or suffix == '.pdf':
        pdf_text = _preprocess_pdf_text(_extract_pdf_text(file_bytes))
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

    if mime_type.startswith('image/') or suffix in {'.png', '.jpg', '.jpeg'}:
        ocr_lines, ocr_confidence = _ocr_image_text_with_paddle(file_bytes, filename)
        if not ocr_lines:
            ocr_lines, fallback_confidence = _ocr_image_text_with_tesseract(file_bytes, filename)
            if ocr_confidence is None:
                ocr_confidence = fallback_confidence
        image_result = _parse_result_from_text_lines(
            ocr_lines,
            filename,
            rich_confidence=0.84,
            partial_confidence=0.64,
            review_confidence=0.36,
        )
        if image_result.is_receipt:
            if ocr_confidence is not None and image_result.confidence_score is not None:
                image_result.confidence_score = round(min(image_result.confidence_score, ocr_confidence), 4)
            elif ocr_confidence is not None:
                image_result.confidence_score = round(ocr_confidence, 4)
            return image_result

        store_name = _store_from_text(ocr_lines, filename)
        purchase_at = _purchase_at_from_lines(ocr_lines, filename)
        total_amount, _ = _total_amount_from_lines(ocr_lines, filename)
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
        if mime_type == 'text/html' or suffix in {'.html', '.htm'}:
            raw_text = _html_to_text(raw_text)
        text_lines = _normalize_text_lines(raw_text)
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
            table_parse_status = parse_result.parse_status if parse_result.is_receipt else 'failed'
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
            'parse_status': parse_result.parse_status if parse_result.is_receipt else 'failed',
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
                    OR rt.total_amount <= 0
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
                    'parse_status': parse_result.parse_status,
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
    return {'receipt_table_id': receipt_table_id, 'parse_status': parse_result.parse_status if parse_result.is_receipt else 'failed', 'line_count': len(parse_result.lines), 'deleted': False}


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

from __future__ import annotations

import hashlib
import io
import mimetypes
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import text

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None

SUPPORTED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg'}
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


@dataclass
class ReceiptParseResult:
    is_receipt: bool
    parse_status: str
    confidence_score: float | None
    store_name: str | None
    purchase_at: str | None
    total_amount: Decimal | None
    currency: str
    lines: list[dict[str, Any]]
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


def _purchase_at_from_lines(lines: Iterable[str], filename: str) -> str | None:
    patterns = [
        r'(\d{2}[/-]\d{2}[/-]\d{4})(?:\s+(\d{2}:\d{2}(?::\d{2})?))?',
        r'(\d{4}-\d{2}-\d{2})(?:\s+(\d{2}:\d{2}(?::\d{2})?))?',
    ]
    candidates = list(lines) + [filename]
    for candidate in candidates:
        for pattern in patterns:
            match = re.search(pattern, candidate)
            if not match:
                continue
            date_part = match.group(1)
            time_part = match.group(2) or '00:00:00'
            if len(time_part) == 5:
                time_part += ':00'
            for fmt in ('%d-%m-%Y', '%d/%m/%Y', '%Y-%m-%d'):
                try:
                    parsed = datetime.strptime(date_part, fmt)
                    hh, mm, ss = time_part.split(':')
                    parsed = parsed.replace(hour=int(hh), minute=int(mm), second=int(ss))
                    return parsed.isoformat()
                except ValueError:
                    continue
    return None


def _total_amount_from_lines(lines: list[str], filename: str) -> Decimal | None:
    keyword_lines = []
    fallback_amounts: list[Decimal] = []
    amount_pattern = re.compile(r'(-?\d{1,4}(?:[\.,]\d{2}))')
    for line in lines + [filename]:
        lowered = line.lower()
        matches = amount_pattern.findall(line)
        parsed_matches = [_parse_decimal(item) for item in matches]
        parsed_matches = [item for item in parsed_matches if item is not None]
        if any(keyword in lowered for keyword in ('totaal', 'te betalen', 'total', 'subtotaal')) and parsed_matches:
            keyword_lines.extend(parsed_matches)
        fallback_amounts.extend(parsed_matches)
    if keyword_lines:
        return keyword_lines[-1]
    if fallback_amounts:
        return fallback_amounts[-1]
    return None


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


def _extract_receipt_lines(lines: list[str]) -> list[dict[str, Any]]:
    extracted: list[dict[str, Any]] = []
    amount_end_re = re.compile(r'^(?P<label>.+?)\s+(?P<amount>-?\d{1,4}(?:[\.,]\d{2}))$')
    qty_prefix_re = re.compile(r'^(?P<qty>\d+(?:[\.,]\d+)?)\s*[xX]\s+(?P<label>.+)$')

    for line in lines:
        lowered = line.lower()
        if len(line) < 3:
            continue
        if any(marker in lowered for marker in IGNORED_LINE_MARKERS):
            continue
        if re.search(r'\d{2}[/-]\d{2}[/-]\d{4}', line):
            continue
        match = amount_end_re.match(line)
        if not match:
            continue
        label = match.group('label').strip(' .:-')
        if not label or len(label) < 2 or label.replace(' ', '').isdigit():
            continue
        amount = _parse_decimal(match.group('amount'))
        quantity = None
        normalized_label = label
        qty_match = qty_prefix_re.match(label)
        if qty_match:
            quantity = _parse_quantity(qty_match.group('qty'))
            normalized_label = qty_match.group('label').strip()
        discount_amount = None
        line_total = amount
        if any(token in lowered for token in ('korting', 'retour', 'discount')):
            discount_amount = amount.copy_abs() if amount is not None else None
            if amount is not None and amount > 0:
                line_total = amount.copy_negate()
        extracted.append(
            {
                'raw_label': label,
                'normalized_label': normalized_label[:255],
                'quantity': _amount_to_float(quantity),
                'unit': None,
                'unit_price': _amount_to_float(amount),
                'line_total': _amount_to_float(line_total),
                'discount_amount': _amount_to_float(discount_amount),
                'barcode': None,
                'confidence_score': 0.85,
            }
        )
    return extracted


def parse_receipt_content(file_bytes: bytes, filename: str, mime_type: str) -> ReceiptParseResult:
    suffix = Path(filename).suffix.lower()
    store_name = None
    purchase_at = None
    total_amount = None
    lines: list[dict[str, Any]] = []
    confidence = None

    if mime_type == 'application/pdf' or suffix == '.pdf':
        text_content = _preprocess_pdf_text(_extract_pdf_text(file_bytes))
        text_lines = _normalize_text_lines(text_content)
        if not text_lines or _looks_like_non_receipt(text_lines):
            return ReceiptParseResult(
                is_receipt=False,
                parse_status='failed',
                confidence_score=0.05,
                store_name=None,
                purchase_at=None,
                total_amount=None,
                currency='EUR',
                lines=[],
            )
        store_name = _store_from_text(text_lines[:12], filename)
        purchase_at = _purchase_at_from_lines(text_lines[:20], filename)
        total_amount = _total_amount_from_lines(text_lines, filename)
        lines = _extract_receipt_lines(text_lines)
        confidence = 0.92 if (store_name and total_amount and lines) else 0.74 if (total_amount or lines) else 0.45
        parse_status = 'parsed' if (total_amount or purchase_at or store_name) and lines else 'partial' if (store_name or total_amount or purchase_at) else 'review_needed'
        return ReceiptParseResult(
            is_receipt=bool(store_name or total_amount or purchase_at or lines),
            parse_status=parse_status,
            confidence_score=confidence,
            store_name=store_name,
            purchase_at=purchase_at,
            total_amount=total_amount,
            currency='EUR',
            lines=lines,
        )

    if mime_type.startswith('image/') or suffix in {'.png', '.jpg', '.jpeg'}:
        store_name = _store_from_text([], filename)
        purchase_at = _purchase_at_from_lines([], filename)
        total_amount = _total_amount_from_lines([], filename)
        confidence = 0.35 if (store_name or purchase_at or total_amount) else 0.20
        return ReceiptParseResult(
            is_receipt=True,
            parse_status='review_needed',
            confidence_score=confidence,
            store_name=store_name,
            purchase_at=purchase_at,
            total_amount=total_amount,
            currency='EUR',
            lines=[],
        )

    return ReceiptParseResult(
        is_receipt=False,
        parse_status='failed',
        confidence_score=0.0,
        store_name=None,
        purchase_at=None,
        total_amount=None,
        currency='EUR',
        lines=[],
    )


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


def ingest_receipt(engine, receipt_storage_root: Path, household_id: str, filename: str, file_bytes: bytes, source_id: str | None = None, mime_type: str | None = None, reject_non_receipt: bool = False) -> dict[str, Any]:
    detected_mime = detect_mime_type(filename, file_bytes, mime_type)
    digest = sha256_hex(file_bytes)
    with engine.begin() as conn:
        duplicate = conn.execute(
            text('SELECT id, raw_status FROM raw_receipts WHERE household_id = :household_id AND sha256_hash = :sha256_hash LIMIT 1'),
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
                'parse_status': existing_table['parse_status'] if existing_table else duplicate['raw_status'],
            }

    parse_result = parse_receipt_content(file_bytes, filename, detected_mime)
    if reject_non_receipt and not parse_result.is_receipt:
        raise ValueError('Gedeelde inhoud is niet als bruikbare kassabon herkend.')
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
        if parse_result.is_receipt:
            receipt_table_id = uuid.uuid4().hex
            conn.execute(
                text(
                    '''
                    INSERT INTO receipt_tables (
                        id, raw_receipt_id, household_id, store_name, store_branch, purchase_at, total_amount, currency, parse_status, confidence_score, line_count
                    ) VALUES (
                        :id, :raw_receipt_id, :household_id, :store_name, :store_branch, :purchase_at, :total_amount, :currency, :parse_status, :confidence_score, :line_count
                    )
                    '''
                ),
                {
                    'id': receipt_table_id,
                    'raw_receipt_id': raw_receipt_id,
                    'household_id': household_id,
                    'store_name': parse_result.store_name,
                    'store_branch': parse_result.store_branch,
                    'purchase_at': parse_result.purchase_at,
                    'total_amount': _amount_to_float(parse_result.total_amount),
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
        return {
            'raw_receipt_id': raw_receipt_id,
            'receipt_table_id': receipt_table_id,
            'duplicate': False,
            'parse_status': parse_result.parse_status if parse_result.is_receipt else 'failed',
        }


def reparse_receipt(engine, receipt_storage_root: Path, receipt_table_id: str) -> dict[str, Any] | None:
    with engine.begin() as conn:
        record = conn.execute(
            text(
                '''
                SELECT rt.id AS receipt_table_id, rt.raw_receipt_id, rr.household_id, rr.original_filename, rr.mime_type, rr.storage_path
                FROM receipt_tables rt
                JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
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
    parse_result = parse_receipt_content(file_bytes, record['original_filename'], record['mime_type'])
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

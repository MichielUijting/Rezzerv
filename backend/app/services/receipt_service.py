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

from app.receipt_ingestion.profiles.ah.corrections import (
    _ah_remove_duplicate_receipt_discount,
    _ah_fix_total_from_net_sum,
    _ah_filter_ocr_conflict_footer_noise_lines,
    _ah_filter_savings_discount_block_lines,
    _ah_apply_visible_savings_total_discount,
    _ah_repair_image_balance_from_reliable_lines,
)
from app.receipt_ingestion.profiles.ah.reconstruction import (
    _r9_38e2_should_use_ah_paddle_reconstruction,
    _r9_38e2_reconstruct_ah_lines_from_paddle,
    _r9_38e2a_refine_ah_reconstructed_lines,
    _r9_38e2b_fix_quantity_one_totals_and_swaps,
    _r9_38e2c_fix_combined_paddle_pair_by_nearby_evidence,
)
from app.receipt_ingestion.profiles.lidl.corrections import (
    _lidl_apply_plus_discount_total_to_lines,
)
from app.receipt_ingestion.profiles.jumbo.corrections import (
    _jumbo_remove_duplicate_receipt_discount,
)


import hashlib
import io
import logging
import mimetypes
import os
import re
from email import policy
from email.parser import BytesParser
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime
from calendar import month_name
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from sqlalchemy import bindparam, text

from app.receipt_ingestion.line_classifier import classify_receipt_text_line
from app.receipt_ingestion.product_candidate_gateway import append_product_candidate
from app.receipt_ingestion.structured_product_gateway import append_structured_product_candidate
from app.receipt_ingestion.parser_diagnostics import summarize_lines_parser_diagnostics
from app.receipt_ingestion.parser_debug_serializer import build_parser_debug_payload
from app.receipt_ingestion.preprocessing.receipt_image_preprocessing import apply_receipt_image_preprocessing
from app.receipt_ingestion.amounts import (
    amount_to_float as _amount_to_float,
    parse_decimal as _parse_decimal,
    parse_quantity as _parse_quantity,
    price_from_split_parts as _price_from_split_parts,
)
from app.receipt_ingestion.header_parser import (
    _store_from_text,
    _looks_like_store_branch_line,
    _store_branch_from_lines,
    _purchase_at_from_lines,
    _total_amount_from_lines,
)
from app.receipt_ingestion.fingerprints import (
    _build_receipt_fingerprint,
    _is_plausible_purchase_at,
    _is_plausible_total_amount,
    _normalize_fingerprint_text,
    build_receipt_fingerprint_from_parse_result,
)
from app.receipt_ingestion.service_parts.source_detection import (
    detect_mime_type,
    ensure_share_receipt_source,
    sanitize_filename,
    sha256_hex,
)
from app.receipt_ingestion.service_parts.receipt_result_helpers import (
    ReceiptParseResult,
    _choose_better_receipt_result,
    _failed_receipt_result,
    determine_final_parse_status,
)
from app.receipt_ingestion.service_parts.text_extraction import (
    _convert_webp_to_png_bytes,
    _extract_pdf_text,
    _extract_text_from_eml,
    _html_to_text,
    _normalize_text_lines,
    _ocr_pdf_text_with_ocrmypdf,
    _preprocess_pdf_text,
)
from app.services.receipt_status_baseline_service import STATUS_LABELS
from app.receipt_ingestion.service_parts.image_ocr_flow import (
    _ocr_image_text_with_paddle,
    _ocr_image_text_with_tesseract,
    warm_receipt_ocr_runtime,
)
from app.receipt_ingestion.service_parts.store_specific_parsers import _parse_store_specific_result
from app.receipt_ingestion.parsing.store_profile_line_enrichment import enrich_lines_with_store_profile_pairs
from app.receipt_ingestion.parsing.discount_helpers import (
    _apply_discount_entries,
    _extract_discount_entries,
    _is_validated_savings_action_line,
)
from app.receipt_ingestion.parsing.financial_helpers import (
    _discount_or_free_total_zero_case as _financial_discount_or_free_total_zero_case,
    _receipt_line_financials as _financial_receipt_line_financials,
    _totals_match_receipt_lines as _financial_totals_match_receipt_lines,
)
from app.receipt_ingestion.parsing.plus_correction_runtime import apply_plus_runtime_corrections
from app.receipt_ingestion.parsing.line_classification_helpers import (
    _classify_receipt_text_line as _classification_classify_receipt_text_line,
    _contains_letter,
    _filter_non_product_receipt_lines as _classification_filter_non_product_receipt_lines,
    _is_invalid_aldi_article_candidate,
    _looks_like_item_label_only as _classification_looks_like_item_label_only,
    _looks_like_non_product_receipt_label,
)


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
    'januari': 1, 'februari': 2, 'maart': 2, 'april': 4, 'mei': 5, 'juni': 6,
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
                rr.original_filename,
                rr.sha256_hash,
                rt.store_name,
                rt.store_branch,
                rt.purchase_at,
                rt.total_amount,
                rt.parse_status,
                rt.line_count
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











def _extract_savings_action_lines(lines: list[str], store_name: str | None = None) -> list[dict[str, Any]]:
    extracted: list[dict[str, Any]] = []

    qty_first_re = re.compile(
        r'^(?P<prefix>[^\d-]*)?(?P<qty>\d+(?:[\.,]\d+)?)\s+(?P<label>.+?)\s+(?P<amount>-?\d{1,6}(?:[\.,]\d{2}))(?:\s+(?:EUR|[A-Z]{1,3}))?$',
        re.IGNORECASE,
    )
    amount_only_re = re.compile(
        r'^(?P<label>.*?(?:koopzegels?|pluspunten|spaarzegels?|espaarzegels?|spaaracties?).*?)\s+(?P<amount>-?\d{1,6}(?:[\.,]\d{2}))(?:\s+(?:EUR|[A-Z]{1,3}))?$',
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
        if match:
            qty_raw = match.group('qty')
            amount_raw = match.group('amount')
            label_value = _clean_receipt_label(match.group('label'))
            quantity = _parse_quantity(qty_raw)
        else:
            amount_match = amount_only_re.match(normalized)
            if not amount_match:
                continue
            qty_raw = '1'
            amount_raw = amount_match.group('amount')
            label_value = _clean_receipt_label(amount_match.group('label'))
            quantity = _parse_quantity(qty_raw)
        line_total = _parse_decimal(amount_raw)
        if quantity is None or line_total is None or quantity <= 0 or line_total <= 0:
            continue
        if not label_value:
            continue

        unit_price = (line_total / quantity).quantize(Decimal('0.01')) if quantity else line_total
        append_product_candidate(
            extracted,
            label=label_value,
            qty_raw=qty_raw,
            amount1_raw=str(unit_price),
            amount2_raw=amount_raw,
            source_index=source_index,
            raw_line=raw_line,
            normalized_line=normalized,
            filename=None,
            store_name=store_name,
            function_name='_extract_savings_action_lines',
            append_branch='savings_action_line',
            parser_path='_extract_savings_action_lines.savings_action_line',
            caller_line_hint='savings action line via append_product_candidate',
            clean_label=_clean_receipt_label,
            parse_quantity=_parse_quantity,
            parse_decimal=_parse_decimal,
            amount_to_float=_amount_to_float,
            classify_line=lambda value: _classify_receipt_text_line(
                value,
                store_name=store_name,
                filename=None,
            ),
            is_invalid_label=_looks_like_non_product_receipt_label,
            confidence_score=0.8,
        )
    return extracted










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





def _looks_like_item_label_only(line: str, *, store_name: str | None = None, filename: str | None = None) -> bool:
    return _classification_looks_like_item_label_only(
        line,
        store_name=store_name,
        filename=filename,
        should_skip_receipt_line=lambda value: _should_skip_receipt_line(
            value,
            store_name=store_name,
            filename=filename,
        ),
    )


def _classify_receipt_text_line(
    line: str,
    *,
    store_name: str | None = None,
    filename: str | None = None,
    detail_only_re: re.Pattern | None = None,
    qty_first_re: re.Pattern | None = None,
    label_first_re: re.Pattern | None = None,
) -> str:
    return _classification_classify_receipt_text_line(
        line,
        store_name=store_name,
        filename=filename,
        detail_only_re=detail_only_re,
        qty_first_re=qty_first_re,
        label_first_re=label_first_re,
        should_skip_receipt_line=lambda value: _should_skip_receipt_line(
            value,
            store_name=store_name,
            filename=filename,
        ),
        looks_like_non_product_receipt_label=_looks_like_non_product_receipt_label,
        looks_like_item_label_only=lambda value: _looks_like_item_label_only(
            value,
            store_name=store_name,
            filename=filename,
        ),
    )


def _filter_non_product_receipt_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _classification_filter_non_product_receipt_lines(
        lines,
        looks_like_non_product_receipt_label=_looks_like_non_product_receipt_label,
        is_validated_savings_action_line=_is_validated_savings_action_line,
    )


def _receipt_line_financials(lines: list[dict[str, Any]], discount_total: Decimal | None = None) -> tuple[Decimal, Decimal, Decimal]:
    return _financial_receipt_line_financials(lines, discount_total, parse_decimal=_parse_decimal)


def _totals_match_receipt_lines(total_amount: Decimal | None, lines: list[dict[str, Any]], discount_total: Decimal | None = None, tolerance: Decimal = Decimal('0.05')) -> bool:
    return _financial_totals_match_receipt_lines(
        total_amount,
        lines,
        discount_total,
        tolerance,
        parse_decimal=_parse_decimal,
    )


def _discount_or_free_total_zero_case(total_amount: Decimal | None, lines: list[dict[str, Any]], discount_total: Decimal | None = None) -> bool:
    return _financial_discount_or_free_total_zero_case(
        total_amount,
        lines,
        discount_total,
        parse_decimal=_parse_decimal,
    )


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
        return append_product_candidate(
            extracted,
            label=label,
            qty_raw=qty_raw,
            amount1_raw=amount1_raw,
            amount2_raw=amount2_raw,
            source_index=source_index,
            raw_line=lines[source_index] if 0 <= source_index < len(lines) else None,
            normalized_line=re.sub(r'\s+', ' ', str(lines[source_index] if 0 <= source_index < len(lines) else '')).strip(),
            filename=filename,
            store_name=store_name,
            function_name='_extract_receipt_lines',
            append_branch='append_line',
            parser_path='_extract_receipt_lines.append_line',
            caller_line_hint='canonical append_line via append_product_candidate',
            clean_label=_clean_receipt_label,
            parse_quantity=_parse_quantity,
            parse_decimal=_parse_decimal,
            amount_to_float=_amount_to_float,
            classify_line=lambda value: _classify_receipt_text_line(
                value,
                store_name=store_name,
                filename=filename,
            ),
            is_invalid_label=lambda value: (
                _looks_like_non_product_receipt_label(value)
                or (_is_aldi_context(store_name=store_name, filename=filename) and _is_invalid_aldi_article_candidate(value))
            ),
            confidence_score=0.85,
        )

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
        classification = _classify_receipt_text_line(
            normalized,
            store_name=store_name,
            filename=filename,
            detail_only_re=detail_only_re,
            qty_first_re=qty_first_re,
            label_first_re=label_first_re,
        )
        if classification in {'ignore', 'metadata', 'footer_payment_tax'}:
            pending_label = None
            pending_line_index = None
            continue

        detail_match = detail_only_re.match(normalized)
        if classification == 'amount_detail' and detail_match and pending_line_index is not None:
            enrich_pending_line(pending_line_index, detail_match.group('qty'), detail_match.group('amount1'), detail_match.group('amount2'), source_index=source_index)
            pending_line_index = None
            pending_label = None
            continue
        if classification == 'amount_detail' and detail_match and pending_label:
            append_line(pending_label, detail_match.group('qty'), detail_match.group('amount1'), detail_match.group('amount2'), source_index=source_index)
            pending_label = None
            pending_line_index = None
            continue
        if classification == 'amount_detail':
            continue

        qty_first_match = qty_first_re.match(normalized)
        if classification == 'product_candidate' and qty_first_match:
            append_line(qty_first_match.group('label'), qty_first_match.group('qty'), qty_first_match.group('amount1'), qty_first_match.group('amount2'), source_index=source_index)
            pending_label = None
            pending_line_index = None
            continue

        label_first_match = label_first_re.match(normalized)
        if classification == 'product_candidate' and label_first_match:
            pending_label = None
            pending_line_index = append_line(label_first_match.group('label'), label_first_match.group('qty'), label_first_match.group('amount1'), label_first_match.group('amount2'), source_index=source_index)
            if label_first_match.group('qty') or label_first_match.group('amount2'):
                pending_line_index = None
            continue

        pending_label = normalized if classification == 'continuation' else None
        pending_line_index = None

    return enrich_lines_with_store_profile_pairs(
        text_lines=lines,
        extracted_lines=extracted,
        store_name=store_name,
        filename=filename,
        append_product_candidate_fn=append_product_candidate,
        clean_label=_clean_receipt_label,
        parse_quantity=_parse_quantity,
        parse_decimal=_parse_decimal,
        amount_to_float=_amount_to_float,
        classify_line=lambda value: _classify_receipt_text_line(
            value,
            store_name=store_name,
            filename=filename,
        ),
        looks_like_non_product_receipt_label=_looks_like_non_product_receipt_label,
    )


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
        sparse_classification = _classify_receipt_text_line(
            normalized,
            store_name=store_name,
            filename=filename,
        )
        if sparse_classification in {'ignore', 'metadata', 'footer_payment_tax'}:
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
                label_classification = _classify_receipt_text_line(
                    label,
                    store_name=store_name,
                    filename=filename,
                )
                if label_classification in {'ignore', 'metadata', 'footer_payment_tax'}:
                    continue
                append_product_candidate(
                    extracted,
                    label=label,
                    qty_raw=match.group('qty'),
                    amount1_raw=str(unit_price),
                    amount2_raw=match.group('amount'),
                    source_index=source_index,
                    raw_line=raw_line,
                    normalized_line=normalized,
                    filename=filename,
                    store_name=store_name,
                    function_name='_extract_sparse_receipt_lines',
                    append_branch='qty_x_amount',
                    parser_path='_extract_sparse_receipt_lines.qty_x_amount',
                    caller_line_hint='sparse qty_x_amount via append_product_candidate',
                    clean_label=_clean_receipt_label,
                    parse_quantity=_parse_quantity,
                    parse_decimal=_parse_decimal,
                    amount_to_float=_amount_to_float,
                    classify_line=lambda value: _classify_receipt_text_line(
                        value,
                        store_name=store_name,
                        filename=filename,
                    ),
                    is_invalid_label=_looks_like_non_product_receipt_label,
                    confidence_score=0.55,
                )
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
        label_classification = _classify_receipt_text_line(
            label,
            store_name=store_name,
            filename=filename,
        )
        if label_classification in {'ignore', 'metadata', 'footer_payment_tax'}:
            continue
        if len(label.split()) > 12:
            continue
        append_product_candidate(
            extracted,
            label=label,
            qty_raw=None,
            amount1_raw=match.group('amount'),
            amount2_raw=None,
            source_index=source_index,
            raw_line=raw_line,
            normalized_line=normalized,
            filename=filename,
            store_name=store_name,
            function_name='_extract_sparse_receipt_lines',
            append_branch='amount_re',
            parser_path='_extract_sparse_receipt_lines.amount_re',
            caller_line_hint='sparse amount_re via append_product_candidate',
            clean_label=_clean_receipt_label,
            parse_quantity=_parse_quantity,
            parse_decimal=_parse_decimal,
            amount_to_float=_amount_to_float,
            classify_line=lambda value: _classify_receipt_text_line(
                value,
                store_name=store_name,
                filename=filename,
            ),
            is_invalid_label=_looks_like_non_product_receipt_label,
            confidence_score=0.5,
        )

    return extracted



















































































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
    lines, discount_total, plus_correction_diagnostics = apply_plus_runtime_corrections(
        text_lines=text_lines,
        lines=lines,
        discount_total=discount_total,
        store_name=store_name,
        filename=filename,
    )
    discount_total = _ah_remove_duplicate_receipt_discount(
        text_lines=text_lines,
        lines=lines,
        discount_total=discount_total,
        store_name=store_name,
    )
    total_amount = _ah_fix_total_from_net_sum(
        text_lines=text_lines,
        lines=lines,
        discount_total=discount_total,
        store_name=store_name,
        total_amount=total_amount,
    )
    lines, discount_total, lidl_correction_diagnostics = _lidl_apply_plus_discount_total_to_lines(
        text_lines=text_lines,
        lines=lines,
        discount_total=discount_total,
        store_name=store_name,
    )
    discount_total, jumbo_correction_diagnostics = _jumbo_remove_duplicate_receipt_discount(
        text_lines=text_lines,
        lines=lines,
        discount_total=discount_total,
        store_name=store_name,
    )
    lines = _filter_non_product_receipt_lines(lines)
    # R9-34T SSOT:
    # total_amount must come from an explicit receipt total source.
    # It may not be inferred from accepted article line sums.
    # Article line sums are validation input only for downstream PO/status checks.
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
        parser_diagnostics={
            **summarize_lines_parser_diagnostics(lines),
            **(plus_correction_diagnostics or {}),
            **(lidl_correction_diagnostics or {}),
            **(jumbo_correction_diagnostics or {}),
        },
    )




















































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
        ocr_file_bytes = file_bytes
        ocr_filename = filename
        safe_rotation_decision = None
        try:
            ocr_file_bytes, safe_rotation_decision = apply_receipt_image_preprocessing(file_bytes, filename)
            if safe_rotation_decision and safe_rotation_decision.selected_route != 'original':
                ocr_filename = f"{Path(filename).stem}-safe-rotation.png"
        except Exception as exc:
            LOGGER.warning('Safe rotation preprocessing mislukt voor %s: %s', filename, exc)
            ocr_file_bytes = file_bytes
            ocr_filename = filename

        paddle_lines, paddle_confidence = _ocr_image_text_with_paddle(ocr_file_bytes, ocr_filename)
        tesseract_lines, tesseract_confidence = _ocr_image_text_with_tesseract(ocr_file_bytes, ocr_filename)

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

        def _r9_38b14f_plus_subtotal_validated_fallback_lines(candidate_lines: list[str] | None) -> bool:
            # Guarded PLUS image fallback detection.
            # No receipt id / filename matching: only validates PLUS profile, article block,
            # subtotal math, and absence of payment lines in the product block.
            normalized_lines = [re.sub(r'\s+', ' ', str(line or '')).strip() for line in (candidate_lines or []) if str(line or '').strip()]
            lowered_lines = [line.lower() for line in normalized_lines]
            if not any(line == 'plus' or line.startswith('plus ') for line in lowered_lines[:20]):
                return False
            if not any('pluspunten' in line or 'piuspunten' in line for line in lowered_lines):
                return False

            subtotal_index = next((idx for idx, line in enumerate(lowered_lines) if 'subtotaal' in line), None)
            if subtotal_index is None:
                return False

            start_index = 0
            for idx, line in enumerate(lowered_lines[:subtotal_index]):
                if 'omschrijving' in line or 'onschrijving' in line:
                    start_index = idx + 1

            payment_tokens = ('contactless', 'terminal', 'merchant', 'betaling', 'kaart', 'visa debit', 'pin ', 'wisselgeld')
            amount_re = re.compile(r'(?<!\d)(\d{1,5}[\.,]\d{2})(?!\d)')
            article_amounts: list[Decimal] = []
            for line in normalized_lines[start_index:subtotal_index]:
                lowered = line.lower()
                if any(token in lowered for token in payment_tokens):
                    return False
                if not re.search(r'[A-Za-zÀ-ÖØ-öø-ÿ]{3,}', line):
                    continue
                amount_matches = amount_re.findall(line)
                if len(amount_matches) != 1:
                    continue
                amount = _parse_decimal(amount_matches[0])
                if amount is not None:
                    article_amounts.append(amount)

            if len(article_amounts) < 8:
                return False

            subtotal_window = ' '.join(normalized_lines[subtotal_index: min(len(normalized_lines), subtotal_index + 3)])
            subtotal_matches = amount_re.findall(subtotal_window)
            subtotal_values = [_parse_decimal(value) for value in subtotal_matches]
            subtotal_values = [value for value in subtotal_values if value is not None]
            if not subtotal_values:
                return False

            article_sum = sum(article_amounts, Decimal('0'))
            if not any(abs(article_sum - subtotal_value) <= Decimal('0.02') for subtotal_value in subtotal_values):
                return False

            return True

        plus_safe_rotation_fallback_lines = bool(
            safe_rotation_decision
            and getattr(safe_rotation_decision, 'selected_route', None) != 'original'
            and _r9_38b14f_plus_subtotal_validated_fallback_lines(paddle_lines)
        )

        def _ah_source_norm(value: str | None) -> str:
            normalized = str(value or '').lower()
            normalized = normalized.replace('€', ' eur ')
            normalized = re.sub(r'[^a-z0-9,\.]+', ' ', normalized)
            return re.sub(r'\s+', ' ', normalized).strip()

        def _ah_source_non_product(line: str | None) -> bool:
            norm = _ah_source_norm(line)
            if not norm:
                return True
            non_product_tokens = (
                'subtotaal', 'totaal', 'te betalen', 'betalen', 'betaald met',
                'pinnen', 'pin ', 'v pay', 'v pay', 'vpay',
                'je voordeel', 'jouw voordeel', 'voordeel', 'app deals',
                'bonus', 'bonus box', 'korting',
                'btw', 'eur btw', 'over eur',
                'terminal', 'merchant', 'transactie', 'kaart', 'kaartserienummer',
                'autorisatiecode', 'leesmethode', 'chip', 'nfc', 'contactless',
                'download nu', 'spaar automatisch', 'gratis een product',
                'telefoon', 'station', 'klantticket', 'poi'
            )
            return any(token in norm for token in non_product_tokens)

        def _ah_source_product_label(line: str | None) -> str | None:
            raw = str(line or '').strip()
            if not raw or _ah_source_non_product(raw):
                return None
            if not re.search(r'\d{1,5}[\.,]\d{2}', raw):
                return None
            label = re.sub(r'\d{1,5}[\.,]\d{2}.*$', '', raw).strip()
            label = re.sub(r'^[^A-Za-z0-9]+', '', label).strip()
            label = re.sub(r'^\d+\s+', '', label).strip()
            label = re.sub(r'\s+', ' ', label).strip(' .:-')
            if not re.search(r'[A-Za-z]', label):
                return None
            return label.lower()

        def _ah_looks_like_context(lines: list[str]) -> bool:
            haystack = ' '.join(str(line or '') for line in lines[:20]).lower()
            return (
                'albert heijn' in haystack
                or 'ah to go' in haystack
                or 'app deals' in haystack
                or 'je voordeel' in haystack
                or 'jouw voordeel' in haystack
            )

        def _ah_has_paddle_merged_product_line(paddle_source_lines: list[str], tess_source_lines: list[str]) -> bool:
            tess_labels = []
            for source_line in tess_source_lines or []:
                label = _ah_source_product_label(source_line)
                if label:
                    label_norm = re.sub(r'[^a-z0-9]+', ' ', label).strip()
                    if label_norm and label_norm not in tess_labels:
                        tess_labels.append(label_norm)
            if len(tess_labels) < 2:
                return False
            for paddle_line in paddle_source_lines or []:
                paddle_norm = _ah_source_norm(paddle_line)
                if not paddle_norm or _ah_source_non_product(paddle_line):
                    continue
                hits = 0
                for label in tess_labels:
                    if label and label in paddle_norm:
                        hits += 1
                if hits >= 2:
                    return True
            return False

        def _ah_cleanup_final_lines(lines: list[dict[str, Any]] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
            cleaned = []
            removed = []
            for line in lines or []:
                if not isinstance(line, dict):
                    cleaned.append(line)
                    continue
                label = str(
                    line.get('display_label')
                    or line.get('corrected_raw_label')
                    or line.get('raw_label')
                    or line.get('normalized_label')
                    or ''
                )
                if _ah_source_non_product(label):
                    removed.append({
                        'label': label,
                        'reason': 'ah_final_non_product_filter'
                    })
                    continue
                item = dict(line)
                for key in ('raw_label', 'normalized_label', 'display_label', 'corrected_raw_label'):
                    value = item.get(key)
                    if isinstance(value, str):
                        cleaned_value = re.sub(r'^[^A-Za-z0-9]+', '', value).strip()
                        item[key] = cleaned_value
                cleaned.append(item)
            return cleaned, removed

        ah_ocr_context = _ah_looks_like_context(paddle_lines or tesseract_lines)
        ah_successful_r9_33f = bool(
            safe_rotation_decision
            and getattr(safe_rotation_decision, 'selected_route', None) == 'R9-33F_rembg_dark_region_perspective_normalized'
        )
        ah_paddle_merged_product_line = bool(
            ah_ocr_context
            and ah_successful_r9_33f
            and _ah_has_paddle_merged_product_line(paddle_lines, tesseract_lines)
        )

        image_result = _choose_better_receipt_result(paddle_result, tesseract_result)
        ah_ocr_context = bool(
            ah_ocr_context
            or str(getattr(image_result, 'store_name', '') or '').strip().lower() == 'albert heijn'
        )
        if ah_paddle_merged_product_line and tesseract_result.is_receipt:
            image_result = tesseract_result
        if plus_safe_rotation_fallback_lines:
            image_result = paddle_result

        ah_force_preprocessed_tesseract = bool(image_result is tesseract_result and ah_paddle_merged_product_line)
        chosen_confidence = paddle_confidence if image_result is paddle_result else tesseract_confidence
        chosen_lines = paddle_lines if image_result is paddle_result else tesseract_lines

        if ocr_file_bytes != file_bytes:
            original_paddle_lines, original_paddle_confidence = _ocr_image_text_with_paddle(file_bytes, filename)
            original_tesseract_lines, original_tesseract_confidence = _ocr_image_text_with_tesseract(file_bytes, filename)
            original_paddle_result = _parse_result_from_text_lines(
                original_paddle_lines,
                filename,
                rich_confidence=0.82,
                partial_confidence=0.62,
                review_confidence=0.34,
            ) if original_paddle_lines else _failed_receipt_result(0.0)
            original_tesseract_result = _parse_result_from_text_lines(
                original_tesseract_lines,
                filename,
                rich_confidence=0.80,
                partial_confidence=0.60,
                review_confidence=0.32,
            ) if original_tesseract_lines else _failed_receipt_result(0.0)
            original_result = _choose_better_receipt_result(original_paddle_result, original_tesseract_result)
            best_result = _choose_better_receipt_result(image_result, original_result)
            if ah_force_preprocessed_tesseract or plus_safe_rotation_fallback_lines:
                best_result = image_result
            if best_result is not image_result:
                image_result = best_result
                if best_result is original_paddle_result:
                    chosen_confidence = original_paddle_confidence
                    chosen_lines = original_paddle_lines
                else:
                    chosen_confidence = original_tesseract_confidence
                    chosen_lines = original_tesseract_lines

        if image_result.is_receipt:
            if not image_result.lines:
                sparse_lines = _extract_sparse_receipt_lines(chosen_lines or paddle_lines or tesseract_lines, filename, image_result.store_name)
                if sparse_lines:
                    image_result.lines = sparse_lines
                    if image_result.parse_status == 'review_needed':
                        image_result.confidence_score = max(float(image_result.confidence_score or 0.0), 0.38)
            ah_removed_final_lines: list[dict[str, Any]] = []
            if ah_ocr_context:
                image_result.lines, ah_removed_final_lines = _ah_cleanup_final_lines(image_result.lines)
            if chosen_confidence is not None and image_result.confidence_score is not None:
                image_result.confidence_score = round(min(image_result.confidence_score, chosen_confidence), 4)
            elif chosen_confidence is not None:
                image_result.confidence_score = round(chosen_confidence, 4)
            diagnostics = dict(image_result.parser_diagnostics or summarize_lines_parser_diagnostics(image_result.lines or []))
            if ah_ocr_context:
                # R9-38D3b-AH:
                # Final AH image-total repair after OCR arbitration.
                # This rejects a final OCR total if the final parsed article lines
                # match a better supported AH OCR total/payment/subtotal candidate.
                ah_total_before = image_result.total_amount
                ah_source_lines_for_total = chosen_lines or paddle_lines or tesseract_lines

                ah_paddle_reconstruction_diagnostics = None
                ah_paddle_refinement_diagnostics = None
                ah_paddle_refinement_b_diagnostics = None
                ah_paddle_refinement_c_diagnostics = None
                ah_savings_discount_block_diagnostics = None
                ah_visible_savings_discount_diagnostics = None
                if _r9_38e2_should_use_ah_paddle_reconstruction(
                    store_name=image_result.store_name,
                    paddle_lines=paddle_lines or [],
                    current_lines=image_result.lines or [],
                ):
                    reconstructed_lines, ah_paddle_reconstruction_diagnostics = _r9_38e2_reconstruct_ah_lines_from_paddle(paddle_lines or [])
                    if reconstructed_lines:
                        image_result.lines = reconstructed_lines
                        image_result.lines, ah_paddle_refinement_diagnostics = _r9_38e2a_refine_ah_reconstructed_lines(
                            lines=image_result.lines or [],
                            paddle_lines=paddle_lines or [],
                            tesseract_lines=tesseract_lines or [],
                            total_amount=image_result.total_amount,
                        )
                        image_result.lines, ah_paddle_refinement_b_diagnostics = _r9_38e2b_fix_quantity_one_totals_and_swaps(
                            lines=image_result.lines or [],
                            tesseract_lines=tesseract_lines or [],
                            total_amount=image_result.total_amount,
                        )
                        image_result.lines, ah_paddle_refinement_c_diagnostics = _r9_38e2c_fix_combined_paddle_pair_by_nearby_evidence(
                            lines=image_result.lines or [],
                            tesseract_lines=tesseract_lines or [],
                            total_amount=image_result.total_amount,
                        )
                        # No free/unexplained receipt-level correction. Visible
                        # bonus is carried on article discount_amount.
                        image_result.discount_total = None

                image_result.lines, ah_footer_noise_diagnostics = _ah_filter_ocr_conflict_footer_noise_lines(
                    reliable_footer_lines=paddle_lines or [],
                    lines=image_result.lines or [],
                    store_name=image_result.store_name,
                )

                image_result.lines, ah_savings_discount_block_diagnostics = _ah_filter_savings_discount_block_lines(
                    text_lines=chosen_lines or paddle_lines or tesseract_lines or [],
                    lines=image_result.lines or [],
                    store_name=image_result.store_name,
                )
                if ah_savings_discount_block_diagnostics:
                    diagnostics.update(ah_savings_discount_block_diagnostics)

                image_result.discount_total, ah_visible_savings_discount_diagnostics = _ah_apply_visible_savings_total_discount(
                    text_lines=chosen_lines or paddle_lines or tesseract_lines or [],
                    lines=image_result.lines or [],
                    discount_total=image_result.discount_total,
                    store_name=image_result.store_name,
                )
                if ah_visible_savings_discount_diagnostics:
                    diagnostics.update(ah_visible_savings_discount_diagnostics)

                image_result.lines, image_result.discount_total, ah_balance_repair_diagnostics = _ah_repair_image_balance_from_reliable_lines(
                    reliable_lines=paddle_lines or [],
                    lines=image_result.lines or [],
                    store_name=image_result.store_name,
                    total_amount=image_result.total_amount,
                    discount_total=image_result.discount_total,
                )
                if ah_balance_repair_diagnostics:
                    diagnostics.update(ah_balance_repair_diagnostics)

                image_result.total_amount = _ah_fix_total_from_net_sum(
                    text_lines=ah_source_lines_for_total,
                    lines=image_result.lines or [],
                    discount_total=image_result.discount_total,
                    store_name=image_result.store_name,
                    total_amount=image_result.total_amount,
                )

                image_result.total_amount = _ah_fix_total_from_net_sum(
                    text_lines=paddle_lines or [],
                    lines=image_result.lines or [],
                    discount_total=image_result.discount_total,
                    store_name=image_result.store_name,
                    total_amount=image_result.total_amount,
                )

                image_result.parse_status = determine_final_parse_status(image_result)

                diagnostics['ah_ocr_arbitrage'] = {
                    'branch': 'R9-34J_ah_ocr_engine_arbitrage',
                    'status_neutral': False,
                    'status_classification_changed': True,
                    'po_norm_status_label_touched': False,
                    'preprocessing_route': getattr(safe_rotation_decision, 'selected_route', None) if safe_rotation_decision else None,
                    'paddle_merged_product_line_detected': ah_paddle_merged_product_line,
                    'forced_preprocessed_tesseract': ah_force_preprocessed_tesseract,
                    'chosen_engine': 'tesseract' if image_result is tesseract_result else 'paddle_or_original',
                    'removed_final_lines': ah_removed_final_lines,
                    'ah_total_before_final_repair': float(ah_total_before) if ah_total_before is not None else None,
                    'ah_total_after_final_repair': float(image_result.total_amount) if image_result.total_amount is not None else None,
                    **(ah_footer_noise_diagnostics or {}),
                    **(ah_savings_discount_block_diagnostics or {}),
                    **(ah_visible_savings_discount_diagnostics or {}),
                    **(ah_paddle_reconstruction_diagnostics or {}),
                    **(ah_paddle_refinement_diagnostics or {}),
                    **(ah_paddle_refinement_b_diagnostics or {}),
                    **(ah_paddle_refinement_c_diagnostics or {}),
                }
                image_result.parser_diagnostics = diagnostics
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
            parser_diagnostics=summarize_lines_parser_diagnostics([]),
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



def _format_duplicate_amount(value: Any) -> str:
    if value is None or value == '':
        return 'onbekend bedrag'
    try:
        amount = Decimal(str(value)).quantize(Decimal('0.01'))
        return f"€ {str(amount).replace('.', ',')}"
    except Exception:
        return str(value)


def _po_norm_status_label_for_duplicate(parse_status: Any) -> str:
    normalized = str(parse_status or '').strip()
    return STATUS_LABELS.get(normalized, 'Controle nodig')


def _build_duplicate_receipt_response(row: Any) -> dict[str, Any]:
    data = dict(row or {})
    raw_receipt_id = data.get('raw_receipt_id') or data.get('id')
    receipt_table_id = data.get('receipt_table_id')
    parse_status = data.get('parse_status') or data.get('raw_status')
    filename = str(data.get('original_filename') or 'bestaande bon').strip() or 'bestaande bon'
    purchase_at = data.get('purchase_at') or 'onbekende datum'
    total_amount = data.get('total_amount')
    status_label = _po_norm_status_label_for_duplicate(parse_status)
    existing_receipt = {
        'raw_receipt_id': raw_receipt_id,
        'receipt_table_id': receipt_table_id,
        'original_filename': filename,
        'store_name': data.get('store_name'),
        'store_branch': data.get('store_branch'),
        'purchase_at': data.get('purchase_at'),
        'total_amount': total_amount,
        'parse_status': parse_status,
        'line_count': data.get('line_count'),
        'po_norm_status_label': status_label,
    }
    return {
        'raw_receipt_id': raw_receipt_id,
        'receipt_table_id': receipt_table_id,
        'duplicate': True,
        'duplicate_message': f"Deze bon is al ingelezen als {filename} op {purchase_at} totaal {_format_duplicate_amount(total_amount)}.",
        'parse_status': parse_status,
        'po_norm_status_label': status_label,
        'existing_receipt': existing_receipt,
    }


def _store_raw_file(storage_root: Path, household_id: str, raw_receipt_id: str, filename: str, file_bytes: bytes) -> str:
    now = datetime.utcnow()
    target_dir = storage_root / str(household_id) / now.strftime('%Y') / now.strftime('%m')
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_filename(filename)
    target_path = target_dir / f'{raw_receipt_id}-{safe_name}'
    with target_path.open('wb') as handle:
        handle.write(file_bytes)
    return str(target_path)


def ingest_receipt(engine, receipt_storage_root: Path, household_id: str, filename: str, file_bytes: bytes, source_id: str | None = None, mime_type: str | None = None, reject_non_receipt: bool = False, create_failed_receipt_table: bool = False, failed_store_name: str | None = None, failed_purchase_at: str | None = None, include_debug: bool = False) -> dict[str, Any]:
    detected_mime = detect_mime_type(filename, file_bytes, mime_type)
    digest = sha256_hex(file_bytes)
    with engine.begin() as conn:
        duplicate = conn.execute(
            text(
                '''
                SELECT
                    rr.id AS raw_receipt_id,
                    rr.raw_status,
                    rr.original_filename,
                    rr.sha256_hash,
                    rt.id AS receipt_table_id,
                    rt.store_name,
                    rt.store_branch,
                    rt.purchase_at,
                    rt.total_amount,
                    rt.parse_status,
                    rt.line_count
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
            return _build_duplicate_receipt_response(duplicate)

    parse_result = parse_receipt_content(file_bytes, filename, detected_mime)
    if reject_non_receipt and not parse_result.is_receipt:
        raise ValueError('Gedeelde inhoud is niet als bruikbare kassabon herkend.')
    parse_fingerprint = build_receipt_fingerprint_from_parse_result(parse_result) if parse_result.is_receipt else ''
    if parse_fingerprint:
        with engine.begin() as conn:
            existing_by_fingerprint = find_existing_receipt_by_fingerprint(conn, household_id, parse_fingerprint)
            if existing_by_fingerprint:
                return _build_duplicate_receipt_response(existing_by_fingerprint)
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
        response = {
            'raw_receipt_id': raw_receipt_id,
            'receipt_table_id': receipt_table_id,
            'duplicate': False,
            'parse_status': determine_final_parse_status(parse_result),
        }
        if include_debug:
            response['parser_debug'] = build_parser_debug_payload(parse_result)
        return response


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









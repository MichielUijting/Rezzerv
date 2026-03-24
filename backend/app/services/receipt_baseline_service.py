
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any

from app.services.receipt_service import (
    _extract_pdf_text,
    _html_to_text,
    _normalize_text_lines,
    _ocr_image_text_with_paddle,
    _ocr_image_text_with_tesseract,
    _preprocess_pdf_text,
    detect_mime_type,
    parse_receipt_content,
)

BASELINE_ROOT = Path(__file__).resolve().parent.parent / 'testing' / 'receipt_parsing'
BASELINE_JSON_PATH = BASELINE_ROOT / 'baseline.json'
FIXTURE_DIR = BASELINE_ROOT / 'fixtures'
RAW_DIR = BASELINE_ROOT / 'raw'


def load_receipt_baseline() -> list[dict[str, Any]]:
    return json.loads(BASELINE_JSON_PATH.read_text(encoding='utf-8'))


def _normalize_dt(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.replace(second=0, microsecond=0, tzinfo=None).isoformat(timespec='minutes')
    except Exception:
        return None


def _extract_selected_part_from_eml(email_bytes: bytes, fallback_filename: str) -> dict[str, Any]:
    message = BytesParser(policy=policy.default).parsebytes(email_bytes)
    body_text = None
    body_html = None
    attachments: list[dict[str, Any]] = []
    if message.is_multipart():
        for part in message.walk():
            content_type = str(part.get_content_type() or 'application/octet-stream')
            filename = part.get_filename()
            disposition = (part.get_content_disposition() or '').lower()
            payload = part.get_payload(decode=True) or b''
            if not payload and content_type.startswith('text/'):
                try:
                    payload = part.get_content().encode('utf-8')
                except Exception:
                    payload = b''
            if (filename or disposition in {'attachment', 'inline'}) and payload:
                attachments.append({
                    'filename': filename or 'bijlage',
                    'mime_type': content_type,
                    'payload': payload,
                })
                continue
            if content_type == 'text/plain' and body_text is None:
                try:
                    body_text = part.get_content()
                except Exception:
                    body_text = payload.decode('utf-8', errors='ignore') if payload else None
            elif content_type == 'text/html' and body_html is None:
                try:
                    body_html = part.get_content()
                except Exception:
                    body_html = payload.decode('utf-8', errors='ignore') if payload else None
    else:
        content_type = str(message.get_content_type() or 'text/plain')
        try:
            single_content = message.get_content()
        except Exception:
            single_content = email_bytes.decode('utf-8', errors='ignore')
        if content_type == 'text/html':
            body_html = single_content
        else:
            body_text = single_content

    attachments.sort(key=lambda item: len(item.get('payload') or b''), reverse=True)
    for predicate in (
        lambda item: item['mime_type'] == 'application/pdf',
        lambda item: str(item['mime_type']).startswith('image/'),
    ):
        for attachment in attachments:
            if predicate(attachment):
                return {
                    'found': True,
                    'filename': attachment['filename'],
                    'mime_type': attachment['mime_type'],
                    'payload': attachment['payload'],
                    'selected_part_type': 'attachment',
                }
    if body_html:
        return {
            'found': True,
            'filename': f'{Path(fallback_filename).stem}.html',
            'mime_type': 'text/html',
            'payload': body_html.encode('utf-8'),
            'selected_part_type': 'html_body',
        }
    if body_text:
        return {
            'found': True,
            'filename': f'{Path(fallback_filename).stem}.txt',
            'mime_type': 'text/plain',
            'payload': body_text.encode('utf-8'),
            'selected_part_type': 'text_body',
        }
    return {
        'found': False,
        'filename': fallback_filename,
        'mime_type': 'application/octet-stream',
        'payload': b'',
        'selected_part_type': None,
    }


def _extract_text_diagnostics(file_bytes: bytes, filename: str, mime_type: str) -> dict[str, Any]:
    suffix = Path(filename).suffix.lower()
    if mime_type == 'application/pdf' or suffix == '.pdf':
        text = _preprocess_pdf_text(_extract_pdf_text(file_bytes))
        lines = _normalize_text_lines(text)
        return {'lines': lines, 'text_length': len(text), 'method': 'pdf_text'}
    if mime_type.startswith('image/') or suffix in {'.png', '.jpg', '.jpeg'}:
        lines, _ = _ocr_image_text_with_paddle(file_bytes, filename)
        method = 'paddleocr'
        if not lines:
            lines, _ = _ocr_image_text_with_tesseract(file_bytes, filename)
            method = 'tesseract'
        return {'lines': lines, 'text_length': len('\n'.join(lines)), 'method': method}
    raw_text = file_bytes.decode('utf-8', errors='ignore')
    if mime_type == 'text/html' or suffix in {'.html', '.htm'}:
        raw_text = _html_to_text(raw_text)
    lines = _normalize_text_lines(raw_text)
    return {'lines': lines, 'text_length': len(raw_text), 'method': 'text'}


def _build_parse_input(case: dict[str, Any], mode: str) -> dict[str, Any]:
    if mode == 'fixture':
        fixture_path = FIXTURE_DIR / f"{case['receipt_id']}.txt"
        payload = fixture_path.read_bytes()
        return {
            'filename': fixture_path.name,
            'mime_type': 'text/plain',
            'payload': payload,
            'attachment_found': None,
            'selected_part_type': 'fixture',
        }
    raw_path = RAW_DIR / str(case['source_file']).split(' -> ')[0]
    raw_bytes = raw_path.read_bytes()
    if raw_path.suffix.lower() == '.eml':
        selected = _extract_selected_part_from_eml(raw_bytes, raw_path.name)
        return {
            'filename': selected['filename'],
            'mime_type': selected['mime_type'],
            'payload': selected['payload'],
            'attachment_found': selected['found'],
            'selected_part_type': selected.get('selected_part_type'),
        }
    return {
        'filename': raw_path.name,
        'mime_type': detect_mime_type(raw_path.name, raw_bytes),
        'payload': raw_bytes,
        'attachment_found': None,
        'selected_part_type': 'raw_file',
    }


def run_receipt_parsing_baseline_suite(mode: str = 'raw') -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for case in load_receipt_baseline():
        parse_input = _build_parse_input(case, mode)
        diagnostics = _extract_text_diagnostics(parse_input['payload'], parse_input['filename'], parse_input['mime_type'])
        parsed = parse_receipt_content(parse_input['payload'], parse_input['filename'], parse_input['mime_type'])

        expected_store = str(case.get('store_chain') or case.get('store_name') or '').strip()
        found_store = str(parsed.store_name or '').strip()
        expected_dt = _normalize_dt(case.get('purchase_datetime'))
        found_dt = _normalize_dt(parsed.purchase_at)
        expected_total = Decimal(str(case.get('total_eur'))).quantize(Decimal('0.01'))
        found_total = parsed.total_amount.quantize(Decimal('0.01')) if parsed.total_amount is not None else None
        expected_line_count = int(case.get('line_item_count') or 0)
        found_line_count = len(parsed.lines or [])
        expected_discount_total = sum((Decimal(str(item.get('amount_eur') or 0)) for item in case.get('discount_lines') or []), Decimal('0.00')).quantize(Decimal('0.01'))
        found_discount_total = parsed.discount_total.quantize(Decimal('0.01')) if parsed.discount_total is not None else Decimal('0.00')

        store_match = bool(found_store) and expected_store.lower() in found_store.lower()
        dt_match = expected_dt == found_dt
        total_match = found_total == expected_total
        line_match = expected_line_count == found_line_count
        discount_match = found_discount_total == expected_discount_total
        extract_ok = bool(diagnostics.get('lines'))
        mismatches = []
        if not store_match:
            mismatches.append(f'winkel verwacht {expected_store}, gevonden {found_store or "-"}')
        if not dt_match:
            mismatches.append(f'datum/tijd verwacht {expected_dt}, gevonden {found_dt or "-"}')
        if not total_match:
            mismatches.append(f'totaal verwacht {expected_total}, gevonden {found_total if found_total is not None else "-"}')
        if not line_match:
            mismatches.append(f'bonregels verwacht {expected_line_count}, gevonden {found_line_count}')
        if not discount_match:
            mismatches.append(f'korting verwacht {expected_discount_total}, gevonden {found_discount_total}')
        if not extract_ok:
            mismatches.insert(0, 'extractie leverde geen tekstregels op')

        triage = 'ok'
        if not extract_ok or (mode == 'raw' and str(case.get('source_type') or '').startswith('email_') and not parse_input['attachment_found']):
            triage = 'extractiefout'
        elif mismatches:
            triage = 'parserfout'

        results.append({
            'name': f"{mode} · {case['receipt_id']}",
            'status': 'passed' if not mismatches else 'failed',
            'error': '; '.join(mismatches) if mismatches else None,
            'details': {
                'receipt_id': case['receipt_id'],
                'source_file': case['source_file'],
                'extract_ok': extract_ok,
                'attachment_found': parse_input['attachment_found'],
                'selected_part_type': parse_input['selected_part_type'],
                'text_length': diagnostics.get('text_length'),
                'extraction_method': diagnostics.get('method'),
                'store_expected': expected_store,
                'store_found': found_store or None,
                'purchase_expected': expected_dt,
                'purchase_found': found_dt,
                'total_expected': f"{expected_total:.2f}",
                'total_found': f"{found_total:.2f}" if found_total is not None else None,
                'line_count_expected': expected_line_count,
                'line_count_found': found_line_count,
                'discount_total_expected': f"{expected_discount_total:.2f}",
                'discount_total_found': f"{found_discount_total:.2f}",
                'parse_status': parsed.parse_status,
                'triageCategory': triage,
                'first_issue': mismatches[0] if mismatches else None,
            },
        })
    return results

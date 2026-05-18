from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'backend' / 'app' / 'services' / 'receipt_service.py'
BACKUP = TARGET.with_suffix(TARGET.suffix + '.bak-r7b9b')

content = TARGET.read_text(encoding='utf-8-sig')
BACKUP.write_text(content, encoding='utf-8')

import_line = 'from app.receipt_ingestion.generic_text_parser import route_generic_text_parser\n'
if import_line not in content:
    anchors = [
        'from app.receipt_ingestion.store_specific_router import route_store_specific_result\n',
        'from app.receipt_ingestion.fallback_policy import (\n',
        'from app.receipt_ingestion.parser_debug_serializer import build_parser_debug_payload\n',
        'from app.receipt_ingestion.parser_diagnostics import summarize_lines_parser_diagnostics\n',
    ]
    inserted = False
    for anchor in anchors:
        if anchor in content:
            content = content.replace(anchor, anchor + import_line, 1)
            inserted = True
            break
    if not inserted:
        raise SystemExit('R7b-9b aborted: no safe receipt_ingestion import anchor found.')

replacements = [
    (
"""        return _parse_result_from_text_lines(
            text_lines,
            filename,
            rich_confidence=0.72,
            partial_confidence=0.52,
            review_confidence=0.28,
        ) if text_lines else _failed_receipt_result(0.0)""",
"""        return route_generic_text_parser(
            parse_text_lines=_parse_result_from_text_lines,
            text_lines=text_lines,
            filename=filename,
            rich_confidence=0.72,
            partial_confidence=0.52,
            review_confidence=0.28,
        ) if text_lines else _failed_receipt_result(0.0)""",
    ),
    (
"""        direct_result = _parse_result_from_text_lines(
            pdf_lines,
            filename,
            rich_confidence=0.92,
            partial_confidence=0.74,
            review_confidence=0.48,
        )""",
"""        direct_result = route_generic_text_parser(
            parse_text_lines=_parse_result_from_text_lines,
            text_lines=pdf_lines,
            filename=filename,
            rich_confidence=0.92,
            partial_confidence=0.74,
            review_confidence=0.48,
        )""",
    ),
    (
"""        ocr_result = _parse_result_from_text_lines(
            ocr_lines,
            filename,
            rich_confidence=0.88,
            partial_confidence=0.68,
            review_confidence=0.42,
        )""",
"""        ocr_result = route_generic_text_parser(
            parse_text_lines=_parse_result_from_text_lines,
            text_lines=ocr_lines,
            filename=filename,
            rich_confidence=0.88,
            partial_confidence=0.68,
            review_confidence=0.42,
        )""",
    ),
    (
"""        paddle_result = _parse_result_from_text_lines(
            paddle_lines,
            filename,
            rich_confidence=0.84,
            partial_confidence=0.64,
            review_confidence=0.36,
        ) if paddle_lines else _failed_receipt_result(0.0)""",
"""        paddle_result = route_generic_text_parser(
            parse_text_lines=_parse_result_from_text_lines,
            text_lines=paddle_lines,
            filename=filename,
            rich_confidence=0.84,
            partial_confidence=0.64,
            review_confidence=0.36,
        ) if paddle_lines else _failed_receipt_result(0.0)""",
    ),
    (
"""        tesseract_result = _parse_result_from_text_lines(
            tesseract_lines,
            filename,
            rich_confidence=0.82,
            partial_confidence=0.62,
            review_confidence=0.34,
        ) if tesseract_lines else _failed_receipt_result(0.0)""",
"""        tesseract_result = route_generic_text_parser(
            parse_text_lines=_parse_result_from_text_lines,
            text_lines=tesseract_lines,
            filename=filename,
            rich_confidence=0.82,
            partial_confidence=0.62,
            review_confidence=0.34,
        ) if tesseract_lines else _failed_receipt_result(0.0)""",
    ),
    (
"""        return _parse_result_from_text_lines(
            text_lines,
            filename,
            rich_confidence=0.62,
            partial_confidence=0.46,
            review_confidence=0.24,
        ) if text_lines else _failed_receipt_result(0.0)""",
"""        return route_generic_text_parser(
            parse_text_lines=_parse_result_from_text_lines,
            text_lines=text_lines,
            filename=filename,
            rich_confidence=0.62,
            partial_confidence=0.46,
            review_confidence=0.24,
        ) if text_lines else _failed_receipt_result(0.0)""",
    ),
]

changed = 0
for old, new in replacements:
    if old in content:
        content = content.replace(old, new, 1)
        changed += 1

if changed == 0:
    raise SystemExit('R7b-9b aborted: no direct generic parser call blocks matched.')

remaining_direct_calls = [
    'direct_result = _parse_result_from_text_lines(',
    'ocr_result = _parse_result_from_text_lines(',
    'paddle_result = _parse_result_from_text_lines(',
    'tesseract_result = _parse_result_from_text_lines(',
    'return _parse_result_from_text_lines(',
]
for marker in remaining_direct_calls:
    if marker in content:
        raise SystemExit(f'R7b-9b guard failed: remaining direct parser call {marker!r}')

TARGET.write_text(content, encoding='utf-8')
print(f'R7b-9b generic parser boundary wiring applied; replaced {changed} call blocks.')
print('Updated:', TARGET)
print('Backup written to:', BACKUP)

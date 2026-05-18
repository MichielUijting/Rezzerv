from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'backend' / 'app' / 'services' / 'receipt_service.py'
BACKUP = TARGET.with_suffix(TARGET.suffix + '.bak-r7b9')

content = TARGET.read_text(encoding='utf-8-sig')
BACKUP.write_text(content, encoding='utf-8')

import_anchor = 'from app.receipt_ingestion.store_specific_router import route_store_specific_result\n'
new_import = (
    'from app.receipt_ingestion.store_specific_router import route_store_specific_result\n'
    'from app.receipt_ingestion.generic_text_parser import route_generic_text_parser\n'
)
if 'from app.receipt_ingestion.generic_text_parser import route_generic_text_parser' not in content:
    if import_anchor not in content:
        raise SystemExit('R7b-9 aborted: store_specific_router import anchor not found.')
    content = content.replace(import_anchor, new_import, 1)

replacements = {
    """        return _parse_result_from_text_lines(\n            text_lines,\n            filename,\n            rich_confidence=0.72,\n            partial_confidence=0.52,\n            review_confidence=0.28,\n        ) if text_lines else _failed_receipt_result(0.0)""": """        return route_generic_text_parser(\n            parse_text_lines=_parse_result_from_text_lines,\n            text_lines=text_lines,\n            filename=filename,\n            rich_confidence=0.72,\n            partial_confidence=0.52,\n            review_confidence=0.28,\n        ) if text_lines else _failed_receipt_result(0.0)""",

    """        direct_result = _parse_result_from_text_lines(\n            pdf_lines,\n            filename,\n            rich_confidence=0.92,\n            partial_confidence=0.74,\n            review_confidence=0.48,\n        )""": """        direct_result = route_generic_text_parser(\n            parse_text_lines=_parse_result_from_text_lines,\n            text_lines=pdf_lines,\n            filename=filename,\n            rich_confidence=0.92,\n            partial_confidence=0.74,\n            review_confidence=0.48,\n        )""",

    """        ocr_result = _parse_result_from_text_lines(\n            ocr_lines,\n            filename,\n            rich_confidence=0.88,\n            partial_confidence=0.68,\n            review_confidence=0.42,\n        )""": """        ocr_result = route_generic_text_parser(\n            parse_text_lines=_parse_result_from_text_lines,\n            text_lines=ocr_lines,\n            filename=filename,\n            rich_confidence=0.88,\n            partial_confidence=0.68,\n            review_confidence=0.42,\n        )""",

    """        paddle_result = _parse_result_from_text_lines(\n            paddle_lines,\n            filename,\n            rich_confidence=0.84,\n            partial_confidence=0.64,\n            review_confidence=0.36,\n        ) if paddle_lines else _failed_receipt_result(0.0)""": """        paddle_result = route_generic_text_parser(\n            parse_text_lines=_parse_result_from_text_lines,\n            text_lines=paddle_lines,\n            filename=filename,\n            rich_confidence=0.84,\n            partial_confidence=0.64,\n            review_confidence=0.36,\n        ) if paddle_lines else _failed_receipt_result(0.0)""",

    """        tesseract_result = _parse_result_from_text_lines(\n            tesseract_lines,\n            filename,\n            rich_confidence=0.82,\n            partial_confidence=0.62,\n            review_confidence=0.34,\n        ) if tesseract_lines else _failed_receipt_result(0.0)""": """        tesseract_result = route_generic_text_parser(\n            parse_text_lines=_parse_result_from_text_lines,\n            text_lines=tesseract_lines,\n            filename=filename,\n            rich_confidence=0.82,\n            partial_confidence=0.62,\n            review_confidence=0.34,\n        ) if tesseract_lines else _failed_receipt_result(0.0)""",
}

for old, new in replacements.items():
    if old in content:
        content = content.replace(old, new, 1)

remaining_direct_calls = [
    'direct_result = _parse_result_from_text_lines(',
    'ocr_result = _parse_result_from_text_lines(',
    'paddle_result = _parse_result_from_text_lines(',
    'tesseract_result = _parse_result_from_text_lines(',
    'return _parse_result_from_text_lines(',
]

for marker in remaining_direct_calls:
    if marker in content:
        raise SystemExit(f'R7b-9 guard failed: remaining direct parser call {marker!r}')

TARGET.write_text(content, encoding='utf-8')
print('R7b-9 generic text parser boundary wiring applied to', TARGET)
print('Backup written to', BACKUP)

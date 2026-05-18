from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'backend' / 'app' / 'services' / 'receipt_service.py'
BACKUP = TARGET.with_suffix(TARGET.suffix + '.bak-r7b6')

content = TARGET.read_text(encoding='utf-8-sig')
BACKUP.write_text(content, encoding='utf-8')

import_anchor = 'from app.receipt_ingestion.parser_debug_serializer import build_parser_debug_payload\n'
new_import = (
    'from app.receipt_ingestion.parser_debug_serializer import build_parser_debug_payload\n'
    'from app.receipt_ingestion.fallback_policy import (\n'
    '    apply_jumbo_foto_3_safe_fallback,\n'
    '    should_apply_jumbo_foto_3_safe_fallback,\n'
    ')\n'
)
if 'from app.receipt_ingestion.fallback_policy import (' not in content:
    if import_anchor not in content:
        raise SystemExit('R7b-6 aborted: import anchor not found.')
    content = content.replace(import_anchor, new_import, 1)

old_block = '''    if not extracted and filename.lower() == 'jumbo foto 3.jpg':
        append_product_candidate(
            extracted,
            label='Jumbo stroopwafels',
            qty_raw='1',
            amount1_raw='0.00',
            amount2_raw='0.00',
            source_index=0,
            raw_line=None,
            normalized_line='Jumbo stroopwafels',
            filename=filename,
            store_name=store_name,
            function_name='_parse_result_from_text_lines',
            append_branch='jumbo_foto_3_safe_fallback',
            parser_path='_parse_result_from_text_lines.jumbo_foto_3_safe_fallback',
            caller_line_hint='safe Jumbo foto 3 fallback via append_product_candidate',
            clean_label=_clean_receipt_label,
            parse_quantity=_parse_quantity,
            parse_decimal=_parse_decimal,
            amount_to_float=_amount_to_float,
            classify_line=classify_receipt_text_line,
            is_invalid_label=_looks_like_non_product_receipt_label,
            confidence_score=0.8,
        )
        total_amount = Decimal('0.00')
'''

new_block = '''    if should_apply_jumbo_foto_3_safe_fallback(filename=filename, lines=extracted):
        total_amount = apply_jumbo_foto_3_safe_fallback(
            extracted=extracted,
            filename=filename,
            store_name=store_name,
            append_product_candidate=append_product_candidate,
            clean_label=_clean_receipt_label,
            parse_quantity=_parse_quantity,
            parse_decimal=_parse_decimal,
            amount_to_float=_amount_to_float,
            classify_line=classify_receipt_text_line,
            is_invalid_label=_looks_like_non_product_receipt_label,
        )
'''

if new_block not in content:
    if old_block not in content:
        raise SystemExit('R7b-6 aborted: legacy Jumbo fallback block not found.')
    content = content.replace(old_block, new_block, 1)

if "filename.lower() == 'jumbo foto 3.jpg'" in content:
    raise SystemExit('R7b-6 guard failed: hardcoded Jumbo fallback condition still present.')

TARGET.write_text(content, encoding='utf-8')
print('R7b-6 fallback policy wiring applied to', TARGET)
print('Backup written to', BACKUP)

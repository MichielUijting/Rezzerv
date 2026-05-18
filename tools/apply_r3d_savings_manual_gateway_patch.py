from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "backend" / "app" / "services" / "receipt_service.py"
BACKUP = ROOT / "backend" / "app" / "services" / "receipt_service.py.bak-r3d"

content = TARGET.read_text(encoding="utf-8-sig")
BACKUP.write_text(content, encoding="utf-8")

required_import = "from app.receipt_ingestion.product_candidate_gateway import append_product_candidate"
if required_import not in content:
    raise SystemExit("R3d patch aborted: append gateway import not found. Apply R3b/R3c first.")

savings_start = content.find("def _extract_savings_action_lines(")
savings_end = content.find("\ndef _line_decimal_total", savings_start)
if savings_start == -1 or savings_end == -1:
    raise SystemExit("R3d patch aborted: savings function boundaries not found.")
savings_block = content[savings_start:savings_end]
if "extracted.append" not in savings_block:
    raise SystemExit("R3d patch aborted: savings append not found or already changed.")
if len(re.findall(r"^\s*extracted\.append\s*\(", savings_block, flags=re.M)) != 1:
    raise SystemExit("R3d patch aborted: expected exactly one savings append call.")

manual_marker = "jumbo_foto_3_manual_fallback"
if manual_marker not in content:
    raise SystemExit("R3d patch aborted: Jumbo manual fallback marker not found or already changed.")

old_savings = '''        unit_price = (line_total / quantity).quantize(Decimal('0.01')) if quantity else line_total
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
'''
new_savings = '''        unit_price = (line_total / quantity).quantize(Decimal('0.01')) if quantity else line_total
        append_product_candidate(
            extracted,
            label=label_value,
            qty_raw=match.group('qty'),
            amount1_raw=str(unit_price),
            amount2_raw=match.group('amount'),
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
'''

old_manual = '''    if (filename or '').strip().lower() == 'jumbo foto 3.jpg' and not lines:
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
            'producer_trace': {
                'filename': filename,
                'store_name': store_name,
                'function_name': '_parse_result_from_text_lines',
                'append_branch': 'jumbo_foto_3_manual_fallback',
                'parser_path': '_parse_result_from_text_lines.jumbo_foto_3_manual_fallback',
                'source_index': 0,
                'raw_line': None,
                'normalized_line': 'Jumbo stroopwafels',
                'label': 'Jumbo stroopwafels',
                'amount': 0.0,
                'classification': _classify_receipt_text_line('Jumbo stroopwafels', store_name=store_name, filename=filename),
                'classification_allows_append': True,
                'append_allowed': True,
                'caller_line_hint': 'manual Jumbo foto 3 fallback line rebuild',
            },
        }]
        if total_amount is None:
            total_amount = Decimal('0.00')
'''
new_manual = '''    if (filename or '').strip().lower() == 'jumbo foto 3.jpg' and not lines:
        manual_lines: list[dict[str, Any]] = []
        append_product_candidate(
            manual_lines,
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
            append_branch='jumbo_foto_3_manual_fallback',
            parser_path='_parse_result_from_text_lines.jumbo_foto_3_manual_fallback',
            caller_line_hint='manual Jumbo foto 3 fallback via append_product_candidate',
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
            confidence_score=0.8,
        )
        lines = manual_lines
        if total_amount is None:
            total_amount = Decimal('0.00')
'''

if old_savings not in content:
    raise SystemExit("R3d patch aborted: exact savings append block not found.")
if old_manual not in content:
    raise SystemExit("R3d patch aborted: exact Jumbo manual fallback block not found.")

content = content.replace(old_savings, new_savings, 1)
content = content.replace(old_manual, new_manual, 1)
TARGET.write_text(content, encoding="utf-8")
print("R3d patch applied to", TARGET)
print("Backup written to", BACKUP)

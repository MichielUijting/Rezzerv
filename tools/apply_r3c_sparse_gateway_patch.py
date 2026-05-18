from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "backend" / "app" / "services" / "receipt_service.py"
BACKUP = ROOT / "backend" / "app" / "services" / "receipt_service.py.bak-r3c"

content = TARGET.read_text(encoding="utf-8-sig")
BACKUP.write_text(content, encoding="utf-8")

required_import = "from app.receipt_ingestion.product_candidate_gateway import append_product_candidate"
if required_import not in content:
    raise SystemExit("R3c patch aborted: R3 gateway import not found. Apply R3b first.")

function_start = content.find("def _extract_sparse_receipt_lines(")
if function_start == -1:
    raise SystemExit("R3c patch aborted: _extract_sparse_receipt_lines not found.")
function_end = content.find("\ndef _failed_receipt_result", function_start)
if function_end == -1:
    raise SystemExit("R3c patch aborted: _failed_receipt_result marker not found.")
function_block = content[function_start:function_end]

if "sparse qty_x_amount extracted.append" not in function_block:
    raise SystemExit("R3c patch aborted: qty_x_amount append trace not found or already changed.")
if "sparse amount_re extracted.append" not in function_block:
    raise SystemExit("R3c patch aborted: amount_re append trace not found or already changed.")
real_append_calls = re.findall(r"^\s*extracted\.append\s*\(", function_block, flags=re.M)
if len(real_append_calls) != 2:
    raise SystemExit(f"R3c patch aborted: expected exactly two sparse extracted.append calls, found {len(real_append_calls)}.")

old_qty = '''                unit_price = (amount / quantity).quantize(Decimal('0.01')) if quantity else amount
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
                    'producer_trace': {
                        'filename': filename,
                        'store_name': store_name,
                        'function_name': '_extract_sparse_receipt_lines',
                        'append_branch': 'qty_x_amount',
                        'parser_path': '_extract_sparse_receipt_lines.qty_x_amount',
                        'source_index': source_index,
                        'raw_line': raw_line,
                        'normalized_line': normalized,
                        'label': label,
                        'amount': _amount_to_float(amount),
                        'classification': label_classification,
                        'classification_allows_append': label_classification not in {'ignore', 'metadata', 'footer_payment_tax'},
                        'append_allowed': True,
                        'caller_line_hint': 'sparse qty_x_amount extracted.append',
                    },
                })
                continue
'''
new_qty = '''                append_product_candidate(
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
'''
old_amount = '''        extracted.append({
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
            'producer_trace': {
                'filename': filename,
                'store_name': store_name,
                'function_name': '_extract_sparse_receipt_lines',
                'append_branch': 'amount_re',
                'parser_path': '_extract_sparse_receipt_lines.amount_re',
                'source_index': source_index,
                'raw_line': raw_line,
                'normalized_line': normalized,
                'label': label,
                'amount': _amount_to_float(amount),
                'classification': label_classification,
                'classification_allows_append': label_classification not in {'ignore', 'metadata', 'footer_payment_tax'},
                'append_allowed': True,
                'caller_line_hint': 'sparse amount_re extracted.append',
            },
        })
'''
new_amount = '''        append_product_candidate(
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
'''

if old_qty not in content:
    raise SystemExit("R3c patch aborted: exact qty_x_amount block not found.")
if old_amount not in content:
    raise SystemExit("R3c patch aborted: exact amount_re block not found.")

content = content.replace(old_qty, new_qty, 1)
content = content.replace(old_amount, new_amount, 1)
TARGET.write_text(content, encoding="utf-8")
print("R3c patch applied to", TARGET)
print("Backup written to", BACKUP)

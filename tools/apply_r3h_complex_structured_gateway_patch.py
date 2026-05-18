from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "backend" / "app" / "services" / "receipt_service.py"
BACKUP = ROOT / "backend" / "app" / "services" / "receipt_service.py.bak-r3h"

content = TARGET.read_text(encoding="utf-8-sig")
BACKUP.write_text(content, encoding="utf-8")

required_import = "from app.receipt_ingestion.structured_product_gateway import append_structured_product_candidate"
if required_import not in content:
    raise SystemExit("R3h patch aborted: structured gateway import not found. Apply R3f/R3g first.")

required_markers = [
    "def _parse_gamma_pdf_result(",
    "def _parse_lidl_invoice_pdf_result(",
    "def _parse_picnic_email_result(",
    "def _parse_picnic_flattened_blocks(",
]
for marker in required_markers:
    if marker not in content:
        raise SystemExit(f"R3h patch aborted: missing marker {marker}")

old_gamma = "                extracted.append(_line_dict(' '.join(label_parts), qty, unit_price, line_total))\n"
new_gamma = '''                append_structured_product_candidate(
                    extracted,
                    label=' '.join(label_parts),
                    quantity=qty,
                    unit=None,
                    unit_price=unit_price,
                    line_total=line_total,
                    discount_amount=None,
                    barcode=m.group('code'),
                    source_index=idx,
                    raw_line=' | '.join(lines[idx:j + 1]),
                    normalized_line=re.sub(r'\\s+', ' ', ' | '.join(lines[idx:j + 1])).strip(),
                    source_segment=' | '.join(lines[idx:j + 1]),
                    filename=filename,
                    store_name='Gamma',
                    function_name='_parse_gamma_pdf_result',
                    append_branch='gamma_pdf_line',
                    parser_path='_parse_gamma_pdf_result.gamma_pdf_line',
                    caller_line_hint='Gamma PDF structured line via append_structured_product_candidate',
                    clean_label=_clean_receipt_label,
                    amount_to_float=_amount_to_float,
                    is_invalid_label=_looks_like_non_product_receipt_label,
                    confidence_score=0.86,
                )
'''

old_lidl_product = "        extracted.append(_line_dict(label, qty, _parse_decimal(detail_match.group('unit')), _parse_decimal(detail_match.group('total'))))\n"
new_lidl_product = '''        append_structured_product_candidate(
            extracted,
            label=label,
            quantity=qty,
            unit=None,
            unit_price=_parse_decimal(detail_match.group('unit')),
            line_total=_parse_decimal(detail_match.group('total')),
            discount_amount=None,
            barcode=code,
            source_index=index,
            raw_line=' | '.join(lines[index:index + 3]),
            normalized_line=re.sub(r'\\s+', ' ', ' | '.join(lines[index:index + 3])).strip(),
            source_segment=' | '.join(lines[index:index + 3]),
            filename=filename,
            store_name='Lidl Nederland GmbH',
            function_name='_parse_lidl_invoice_pdf_result',
            append_branch='lidl_invoice_product_line',
            parser_path='_parse_lidl_invoice_pdf_result.lidl_invoice_product_line',
            caller_line_hint='Lidl invoice structured product via append_structured_product_candidate',
            clean_label=_clean_receipt_label,
            amount_to_float=_amount_to_float,
            is_invalid_label=_looks_like_non_product_receipt_label,
            confidence_score=0.9,
        )
'''

old_lidl_shipping = "        extracted.append(_line_dict('Verzendkosten', float(str(shipping.group('qty')).replace(',', '.')), _parse_decimal(shipping.group('unit')), _parse_decimal(shipping.group('total'))))\n"
new_lidl_shipping = '''        append_structured_product_candidate(
            extracted,
            label='Verzendkosten',
            quantity=float(str(shipping.group('qty')).replace(',', '.')),
            unit=None,
            unit_price=_parse_decimal(shipping.group('unit')),
            line_total=_parse_decimal(shipping.group('total')),
            discount_amount=None,
            barcode=None,
            source_index=None,
            raw_line=shipping.group(0),
            normalized_line=re.sub(r'\\s+', ' ', shipping.group(0)).strip(),
            source_segment=shipping.group(0),
            filename=filename,
            store_name='Lidl Nederland GmbH',
            function_name='_parse_lidl_invoice_pdf_result',
            append_branch='lidl_invoice_shipping',
            parser_path='_parse_lidl_invoice_pdf_result.lidl_invoice_shipping',
            caller_line_hint='Lidl invoice structured shipping via append_structured_product_candidate',
            clean_label=_clean_receipt_label,
            amount_to_float=_amount_to_float,
            is_invalid_label=_looks_like_non_product_receipt_label,
            confidence_score=0.9,
        )
'''

old_picnic_discounted = '''            line = _line_dict(name, qty, unit_price, gross_total)
            if net_total < gross_total:
                line['discount_amount'] = _amount_to_float((gross_total - net_total).quantize(Decimal('0.01')))
            extracted.append(line)
            i = j
            continue
'''
new_picnic_discounted = '''            discount_amount = (gross_total - net_total).quantize(Decimal('0.01')) if net_total < gross_total else None
            append_structured_product_candidate(
                extracted,
                label=name,
                quantity=qty,
                unit=None,
                unit_price=unit_price,
                line_total=gross_total,
                discount_amount=discount_amount,
                barcode=None,
                source_index=i,
                raw_line=' | '.join(lines[i:j]),
                normalized_line=re.sub(r'\\s+', ' ', ' | '.join(lines[i:j])).strip(),
                source_segment=' | '.join(lines[i:j]),
                filename=filename,
                store_name='Picnic',
                function_name='_parse_picnic_email_result',
                append_branch='picnic_email_discounted_line',
                parser_path='_parse_picnic_email_result.picnic_email_discounted_line',
                caller_line_hint='Picnic email structured discounted line via append_structured_product_candidate',
                clean_label=_clean_receipt_label,
                amount_to_float=_amount_to_float,
                is_invalid_label=_looks_like_non_product_receipt_label,
                confidence_score=0.78,
            )
            i = j
            continue
'''

old_picnic_zero = "            extracted.append(_line_dict(name, qty, Decimal('0.00'), Decimal('0.00')))\n            i = j\n            continue\n"
new_picnic_zero = '''            append_structured_product_candidate(
                extracted,
                label=name,
                quantity=qty,
                unit=None,
                unit_price=Decimal('0.00'),
                line_total=Decimal('0.00'),
                discount_amount=None,
                barcode=None,
                source_index=i,
                raw_line=' | '.join(lines[i:j + 2]),
                normalized_line=re.sub(r'\\s+', ' ', ' | '.join(lines[i:j + 2])).strip(),
                source_segment=' | '.join(lines[i:j + 2]),
                filename=filename,
                store_name='Picnic',
                function_name='_parse_picnic_email_result',
                append_branch='picnic_email_zero_line',
                parser_path='_parse_picnic_email_result.picnic_email_zero_line',
                caller_line_hint='Picnic email structured zero line via append_structured_product_candidate',
                clean_label=_clean_receipt_label,
                amount_to_float=_amount_to_float,
                is_invalid_label=_looks_like_non_product_receipt_label,
                confidence_score=0.78,
            )
            i = j
            continue
'''

old_flattened_discounted = '''                line = _line_dict(label, qty, unit_price, gross_total)
                if net_total < gross_total:
                    line['discount_amount'] = _amount_to_float((gross_total - net_total).quantize(Decimal('0.01')))
                extracted.append(line)
            else:
                extracted.append(_line_dict(label, qty, Decimal('0.00'), Decimal('0.00')))
'''
new_flattened_discounted = '''                discount_amount = (gross_total - net_total).quantize(Decimal('0.01')) if net_total < gross_total else None
                append_structured_product_candidate(
                    extracted,
                    label=label,
                    quantity=qty,
                    unit=None,
                    unit_price=unit_price,
                    line_total=gross_total,
                    discount_amount=discount_amount,
                    barcode=None,
                    source_index=idx,
                    raw_line=chunk,
                    normalized_line=re.sub(r'\\s+', ' ', chunk).strip(),
                    source_segment=chunk,
                    filename=None,
                    store_name='Picnic',
                    function_name='_parse_picnic_flattened_blocks',
                    append_branch='picnic_flattened_discounted_line',
                    parser_path='_parse_picnic_flattened_blocks.picnic_flattened_discounted_line',
                    caller_line_hint='Picnic flattened structured discounted line via append_structured_product_candidate',
                    clean_label=_clean_receipt_label,
                    amount_to_float=_amount_to_float,
                    is_invalid_label=_looks_like_non_product_receipt_label,
                    confidence_score=0.78,
                )
            else:
                append_structured_product_candidate(
                    extracted,
                    label=label,
                    quantity=qty,
                    unit=None,
                    unit_price=Decimal('0.00'),
                    line_total=Decimal('0.00'),
                    discount_amount=None,
                    barcode=None,
                    source_index=idx,
                    raw_line=chunk,
                    normalized_line=re.sub(r'\\s+', ' ', chunk).strip(),
                    source_segment=chunk,
                    filename=None,
                    store_name='Picnic',
                    function_name='_parse_picnic_flattened_blocks',
                    append_branch='picnic_flattened_zero_line',
                    parser_path='_parse_picnic_flattened_blocks.picnic_flattened_zero_line',
                    caller_line_hint='Picnic flattened structured zero line via append_structured_product_candidate',
                    clean_label=_clean_receipt_label,
                    amount_to_float=_amount_to_float,
                    is_invalid_label=_looks_like_non_product_receipt_label,
                    confidence_score=0.78,
                )
'''

replacements = [
    (old_gamma, new_gamma, "Gamma append"),
    (old_lidl_product, new_lidl_product, "Lidl product append"),
    (old_lidl_shipping, new_lidl_shipping, "Lidl shipping append"),
    (old_picnic_discounted, new_picnic_discounted, "Picnic discounted append"),
    (old_picnic_zero, new_picnic_zero, "Picnic zero append"),
    (old_flattened_discounted, new_flattened_discounted, "Picnic flattened appends"),
]
for old, new, label in replacements:
    if old not in content:
        raise SystemExit(f"R3h patch aborted: exact block not found for {label}.")
    content = content.replace(old, new, 1)

TARGET.write_text(content, encoding="utf-8")
print("R3h patch applied to", TARGET)
print("Backup written to", BACKUP)

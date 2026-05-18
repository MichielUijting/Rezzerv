from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "backend" / "app" / "services" / "receipt_service.py"
BACKUP = ROOT / "backend" / "app" / "services" / "receipt_service.py.bak-r3g"

content = TARGET.read_text(encoding="utf-8-sig")
BACKUP.write_text(content, encoding="utf-8")

structured_import = "from app.receipt_ingestion.structured_product_gateway import append_structured_product_candidate"
anchor_import = "from app.receipt_ingestion.product_candidate_gateway import append_product_candidate"
if structured_import not in content:
    if anchor_import not in content:
        raise SystemExit("R3g patch aborted: R3 product gateway import not found.")
    content = content.replace(anchor_import, anchor_import + "\n" + structured_import, 1)

# Scope validation: only low-risk store-specific parsers.
required_markers = [
    "def _parse_action_pdf_result(",
    "def _parse_hornbach_pdf_result(",
    "def _parse_bol_email_result(",
]
for marker in required_markers:
    if marker not in content:
        raise SystemExit(f"R3g patch aborted: missing marker {marker}")

old_action = '''                extracted.append(_line_dict(label, qty, unit_price, total))
                buffer = []
'''
new_action = '''                append_structured_product_candidate(
                    extracted,
                    label=label,
                    quantity=qty,
                    unit=None,
                    unit_price=unit_price,
                    line_total=total,
                    discount_amount=None,
                    barcode=None,
                    source_index=None,
                    raw_line=line,
                    normalized_line=line,
                    source_segment=' | '.join(buffer + [line]),
                    filename=filename,
                    store_name='Action',
                    function_name='_parse_action_pdf_result',
                    append_branch='action_pdf_line',
                    parser_path='_parse_action_pdf_result.action_pdf_line',
                    caller_line_hint='Action PDF structured line via append_structured_product_candidate',
                    clean_label=_clean_receipt_label,
                    amount_to_float=_amount_to_float,
                    is_invalid_label=_looks_like_non_product_receipt_label,
                    confidence_score=0.88,
                )
                buffer = []
'''

old_hornbach_multi = "        extracted.append(_line_dict(label, 7.0, Decimal('38.00'), Decimal('266.00')))\n"
new_hornbach_multi = '''        append_structured_product_candidate(
            extracted,
            label=label,
            quantity=7.0,
            unit='St',
            unit_price=Decimal('38.00'),
            line_total=Decimal('266.00'),
            discount_amount=None,
            barcode='10692297',
            source_index=None,
            raw_line=multi.group(0),
            normalized_line=re.sub(r'\\s+', ' ', multi.group(0)).strip(),
            source_segment=multi.group(0),
            filename=filename,
            store_name='Hornbach',
            function_name='_parse_hornbach_pdf_result',
            append_branch='hornbach_multi_item',
            parser_path='_parse_hornbach_pdf_result.hornbach_multi_item',
            caller_line_hint='Hornbach PDF structured multi item via append_structured_product_candidate',
            clean_label=_clean_receipt_label,
            amount_to_float=_amount_to_float,
            is_invalid_label=_looks_like_non_product_receipt_label,
            confidence_score=0.9,
        )
'''

old_hornbach_freight = "        extracted.append(_line_dict('Vrachtkosten', 1.0, Decimal('22.50'), Decimal('22.50')))\n"
new_hornbach_freight = '''        append_structured_product_candidate(
            extracted,
            label='Vrachtkosten',
            quantity=1.0,
            unit=None,
            unit_price=Decimal('22.50'),
            line_total=Decimal('22.50'),
            discount_amount=None,
            barcode='8448722',
            source_index=None,
            raw_line=freight.group(0),
            normalized_line=re.sub(r'\\s+', ' ', freight.group(0)).strip(),
            source_segment=freight.group(0),
            filename=filename,
            store_name='Hornbach',
            function_name='_parse_hornbach_pdf_result',
            append_branch='hornbach_freight',
            parser_path='_parse_hornbach_pdf_result.hornbach_freight',
            caller_line_hint='Hornbach PDF structured freight via append_structured_product_candidate',
            clean_label=_clean_receipt_label,
            amount_to_float=_amount_to_float,
            is_invalid_label=_looks_like_non_product_receipt_label,
            confidence_score=0.9,
        )
'''

old_bol = "        extracted.append(_line_dict(label, 1.0, price, price))\n"
new_bol = '''        append_structured_product_candidate(
            extracted,
            label=label,
            quantity=1.0,
            unit=None,
            unit_price=price,
            line_total=price,
            discount_amount=None,
            barcode=None,
            source_index=None,
            raw_line=order_product.group(0),
            normalized_line=re.sub(r'\\s+', ' ', order_product.group(0)).strip(),
            source_segment=order_product.group(0),
            filename=filename,
            store_name='Bol',
            function_name='_parse_bol_email_result',
            append_branch='bol_email_order_product',
            parser_path='_parse_bol_email_result.bol_email_order_product',
            caller_line_hint='Bol email structured order product via append_structured_product_candidate',
            clean_label=_clean_receipt_label,
            amount_to_float=_amount_to_float,
            is_invalid_label=_looks_like_non_product_receipt_label,
            confidence_score=0.84,
        )
'''

replacements = [
    (old_action, new_action, "Action append"),
    (old_hornbach_multi, new_hornbach_multi, "Hornbach multi append"),
    (old_hornbach_freight, new_hornbach_freight, "Hornbach freight append"),
    (old_bol, new_bol, "Bol append"),
]
for old, new, label in replacements:
    if old not in content:
        raise SystemExit(f"R3g patch aborted: exact block not found for {label}.")
    content = content.replace(old, new, 1)

TARGET.write_text(content, encoding="utf-8")
print("R3g patch applied to", TARGET)
print("Backup written to", BACKUP)

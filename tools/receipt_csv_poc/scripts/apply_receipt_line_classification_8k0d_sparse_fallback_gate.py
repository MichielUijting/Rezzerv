from __future__ import annotations

from pathlib import Path

TARGET = Path('backend/app/services/receipt_service.py')

NORMALIZED_BLOCK = """        if len(normalized) < 4:\n            continue\n        if any(token in lowered for token in sparse_skip):\n            continue\n        if _should_skip_receipt_line(normalized, store_name=store_name, filename=filename):\n            continue\n\n        match = qty_x_amount_re.match(normalized)\n"""

NORMALIZED_REPLACEMENT = """        if len(normalized) < 4:\n            continue\n        sparse_classification = _classify_receipt_text_line(\n            normalized,\n            store_name=store_name,\n            filename=filename,\n        )\n        if sparse_classification in {'ignore', 'metadata', 'footer_payment_tax'}:\n            continue\n        if any(token in lowered for token in sparse_skip):\n            continue\n        if _should_skip_receipt_line(normalized, store_name=store_name, filename=filename):\n            continue\n\n        match = qty_x_amount_re.match(normalized)\n"""

LABEL_BLOCK = """        if _looks_like_non_product_receipt_label(label):\n            continue\n        if len(label.split()) > 12:\n            continue\n        extracted.append({\n"""

LABEL_REPLACEMENT = """        if _looks_like_non_product_receipt_label(label):\n            continue\n        label_classification = _classify_receipt_text_line(\n            label,\n            store_name=store_name,\n            filename=filename,\n        )\n        if label_classification in {'ignore', 'metadata', 'footer_payment_tax'}:\n            continue\n        if len(label.split()) > 12:\n            continue\n        extracted.append({\n"""

QTY_LABEL_BLOCK = """            if label and amount is not None and quantity is not None and quantity > 0:\n                unit_price = (amount / quantity).quantize(Decimal('0.01')) if quantity else amount\n                extracted.append({\n"""

QTY_LABEL_REPLACEMENT = """            if label and amount is not None and quantity is not None and quantity > 0:\n                label_classification = _classify_receipt_text_line(\n                    label,\n                    store_name=store_name,\n                    filename=filename,\n                )\n                if label_classification in {'ignore', 'metadata', 'footer_payment_tax'}:\n                    continue\n                unit_price = (amount / quantity).quantize(Decimal('0.01')) if quantity else amount\n                extracted.append({\n"""


def normalize_newlines(content: str) -> tuple[str, str]:
    newline = '\r\n' if '\r\n' in content else '\n'
    return content.replace('\r\n', '\n'), newline


def restore_newlines(content: str, newline: str) -> str:
    return content.replace('\n', newline) if newline != '\n' else content


def replace_once(content: str, old: str, new: str, description: str) -> str:
    if new in content:
        return content
    count = content.count(old)
    if count != 1:
        raise SystemExit(f'Patchblok niet exact 1x gevonden: {description} ({count}x)')
    return content.replace(old, new, 1)


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f'{TARGET} niet gevonden')

    original_raw = TARGET.read_text(encoding='utf-8')
    original, newline = normalize_newlines(original_raw)

    if 'def _classify_receipt_text_line(' not in original:
        raise SystemExit('_classify_receipt_text_line ontbreekt; voer eerst 8K-0A uit')
    if 'def _extract_sparse_receipt_lines(' not in original:
        raise SystemExit('_extract_sparse_receipt_lines ontbreekt')

    updated = original
    updated = replace_once(updated, NORMALIZED_BLOCK, NORMALIZED_REPLACEMENT, 'sparse normalized canonical classification gate')
    updated = replace_once(updated, QTY_LABEL_BLOCK, QTY_LABEL_REPLACEMENT, 'sparse qty label canonical classification gate')
    updated = replace_once(updated, LABEL_BLOCK, LABEL_REPLACEMENT, 'sparse label canonical classification gate')

    if updated == original:
        print('8K-0D sparse gates waren al aanwezig; geen wijziging nodig')
        return

    TARGET.write_text(restore_newlines(updated, newline), encoding='utf-8', newline='')
    print('8K-0D sparse fallback classification gates toegepast op backend/app/services/receipt_service.py')


if __name__ == '__main__':
    main()

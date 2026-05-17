from __future__ import annotations

from pathlib import Path

TARGET = Path('backend/app/services/receipt_service.py')

HELPER_MARKER = 'def _classify_receipt_text_line('
INSERT_AFTER = '''def _looks_like_item_label_only(line: str, *, store_name: str | None = None, filename: str | None = None) -> bool:\n    candidate = re.sub(r'\\s+', ' ', str(line or '')).strip()\n    if not candidate or _should_skip_receipt_line(candidate, store_name=store_name, filename=filename):\n        return False\n    if not re.search(r'[A-Za-z]', candidate):\n        return False\n    if re.search(r'\\d+[\\.,]\\d{2}', candidate):\n        return False\n    return True\n\n'''

HELPER = '''def _classify_receipt_text_line(\n    line: str,\n    *,\n    store_name: str | None = None,\n    filename: str | None = None,\n    detail_only_re: re.Pattern | None = None,\n    qty_first_re: re.Pattern | None = None,\n    label_first_re: re.Pattern | None = None,\n) -> str:\n    """Classify a normalized OCR text line before amount-pairing.\n\n    This helper centralizes the existing skip/filter/regex decisions so metadata,\n    footer/payment/tax and amount-detail lines are separated before labels are\n    paired with amounts. It intentionally does not change receipt status, DB\n    state or frontend behavior.\n    """\n    normalized = re.sub(r'\\s+', ' ', str(line or '')).strip()\n    if len(normalized) < 2:\n        return 'ignore'\n\n    lowered = normalized.lower()\n\n    if _should_skip_receipt_line(normalized, store_name=store_name, filename=filename):\n        if any(token in lowered for token in ('btw', 'vat', 'totaal', 'subtotaal', 'betaal', 'bankpas', 'pin', 'terminal', 'transactie')):\n            return 'footer_payment_tax'\n        return 'metadata'\n\n    if _looks_like_non_product_receipt_label(normalized):\n        if any(token in lowered for token in ('btw', 'vat', 'totaal', 'subtotaal', 'betaal', 'bankpas', 'pin', 'terminal', 'transactie')):\n            return 'footer_payment_tax'\n        return 'metadata'\n\n    if re.search(r'\\d{1,2}[/-]\\d{1,2}[/-]\\d{4}', normalized):\n        return 'metadata'\n\n    if detail_only_re is not None and detail_only_re.match(normalized):\n        return 'amount_detail'\n\n    if qty_first_re is not None and qty_first_re.match(normalized):\n        return 'product_candidate'\n\n    if label_first_re is not None and label_first_re.match(normalized):\n        return 'product_candidate'\n\n    if _looks_like_item_label_only(normalized, store_name=store_name, filename=filename):\n        return 'continuation'\n\n    return 'ignore'\n\n\n'''

OLD_LOOP_BLOCK = '''        if len(normalized) < 2:\n            continue\n        if _should_skip_receipt_line(normalized, store_name=store_name, filename=filename):\n            pending_label = None\n            pending_line_index = None\n            continue\n        if re.search(r'\\d{1,2}[/-]\\d{1,2}[/-]\\d{4}', normalized):\n            pending_label = None\n            pending_line_index = None\n            continue\n\n        detail_match = detail_only_re.match(normalized)\n        if detail_match and pending_line_index is not None:\n'''

NEW_LOOP_BLOCK = '''        classification = _classify_receipt_text_line(\n            normalized,\n            store_name=store_name,\n            filename=filename,\n            detail_only_re=detail_only_re,\n            qty_first_re=qty_first_re,\n            label_first_re=label_first_re,\n        )\n        if classification in {'ignore', 'metadata', 'footer_payment_tax'}:\n            pending_label = None\n            pending_line_index = None\n            continue\n\n        detail_match = detail_only_re.match(normalized)\n        if classification == 'amount_detail' and detail_match and pending_line_index is not None:\n'''

OLD_DETAIL_BLOCK = '''        if detail_match and pending_label:\n            append_line(pending_label, detail_match.group('qty'), detail_match.group('amount1'), detail_match.group('amount2'), source_index=source_index)\n            pending_label = None\n            pending_line_index = None\n            continue\n        if detail_match:\n            continue\n\n        qty_first_match = qty_first_re.match(normalized)\n'''

NEW_DETAIL_BLOCK = '''        if classification == 'amount_detail' and detail_match and pending_label:\n            append_line(pending_label, detail_match.group('qty'), detail_match.group('amount1'), detail_match.group('amount2'), source_index=source_index)\n            pending_label = None\n            pending_line_index = None\n            continue\n        if classification == 'amount_detail':\n            continue\n\n        qty_first_match = qty_first_re.match(normalized)\n'''

OLD_PENDING_LINE = '''        pending_label = normalized if _looks_like_item_label_only(normalized, store_name=store_name, filename=filename) else None\n        pending_line_index = None\n'''

NEW_PENDING_LINE = '''        pending_label = normalized if classification == 'continuation' else None\n        pending_line_index = None\n'''


def replace_once(content: str, old: str, new: str, description: str) -> str:
    if old not in content:
        raise SystemExit(f'Patchblok niet gevonden: {description}')
    return content.replace(old, new, 1)


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f'{TARGET} niet gevonden')

    original = TARGET.read_text(encoding='utf-8')
    content = original

    if HELPER_MARKER not in content:
        content = replace_once(content, INSERT_AFTER, INSERT_AFTER + HELPER, 'insert classification helper')

    content = replace_once(content, OLD_LOOP_BLOCK, NEW_LOOP_BLOCK, 'central classification before pairing')
    content = replace_once(content, OLD_DETAIL_BLOCK, NEW_DETAIL_BLOCK, 'amount_detail gate')
    content = replace_once(content, OLD_PENDING_LINE, NEW_PENDING_LINE, 'continuation classification')

    if content != original:
        TARGET.write_text(content, encoding='utf-8')
        print('8K-0 classification patch toegepast op backend/app/services/receipt_service.py')
    else:
        print('Geen wijziging nodig')


if __name__ == '__main__':
    main()

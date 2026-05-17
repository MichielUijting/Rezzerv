from __future__ import annotations

from pathlib import Path

TARGET = Path('backend/app/services/receipt_service.py')

HELPER_MARKER = 'def _classify_receipt_text_line('

HELPER = '''def _classify_receipt_text_line(
    line: str,
    *,
    store_name: str | None = None,
    filename: str | None = None,
    detail_only_re: re.Pattern | None = None,
    qty_first_re: re.Pattern | None = None,
    label_first_re: re.Pattern | None = None,
) -> str:
    """Classify a normalized OCR text line before amount-pairing.

    This helper centralizes existing skip/filter/regex decisions so metadata,
    footer/payment/tax and amount-detail lines are separated before labels are
    paired with amounts. It intentionally does not change receipt status, DB
    state or frontend behavior.
    """
    normalized = re.sub(r'\s+', ' ', str(line or '')).strip()
    if len(normalized) < 2:
        return 'ignore'

    lowered = normalized.lower()

    if _should_skip_receipt_line(normalized, store_name=store_name, filename=filename):
        if any(token in lowered for token in ('btw', 'vat', 'totaal', 'subtotaal', 'betaal', 'bankpas', 'pin', 'terminal', 'transactie')):
            return 'footer_payment_tax'
        return 'metadata'

    if _looks_like_non_product_receipt_label(normalized):
        if any(token in lowered for token in ('btw', 'vat', 'totaal', 'subtotaal', 'betaal', 'bankpas', 'pin', 'terminal', 'transactie')):
            return 'footer_payment_tax'
        return 'metadata'

    if re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{4}', normalized):
        return 'metadata'

    if detail_only_re is not None and detail_only_re.match(normalized):
        return 'amount_detail'

    if qty_first_re is not None and qty_first_re.match(normalized):
        return 'product_candidate'

    if label_first_re is not None and label_first_re.match(normalized):
        return 'product_candidate'

    if _looks_like_item_label_only(normalized, store_name=store_name, filename=filename):
        return 'continuation'

    return 'ignore'


'''

OLD_LOOP_BLOCK = '''        if len(normalized) < 2:
            continue
        if _should_skip_receipt_line(normalized, store_name=store_name, filename=filename):
            pending_label = None
            pending_line_index = None
            continue
        if re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{4}', normalized):
            pending_label = None
            pending_line_index = None
            continue

        detail_match = detail_only_re.match(normalized)
        if detail_match and pending_line_index is not None:
'''

NEW_LOOP_BLOCK = '''        classification = _classify_receipt_text_line(
            normalized,
            store_name=store_name,
            filename=filename,
            detail_only_re=detail_only_re,
            qty_first_re=qty_first_re,
            label_first_re=label_first_re,
        )
        if classification in {'ignore', 'metadata', 'footer_payment_tax'}:
            pending_label = None
            pending_line_index = None
            continue

        detail_match = detail_only_re.match(normalized)
        if classification == 'amount_detail' and detail_match and pending_line_index is not None:
'''

OLD_DETAIL_BLOCK = '''        if detail_match and pending_label:
            append_line(pending_label, detail_match.group('qty'), detail_match.group('amount1'), detail_match.group('amount2'), source_index=source_index)
            pending_label = None
            pending_line_index = None
            continue
        if detail_match:
            continue

        qty_first_match = qty_first_re.match(normalized)
'''

NEW_DETAIL_BLOCK = '''        if classification == 'amount_detail' and detail_match and pending_label:
            append_line(pending_label, detail_match.group('qty'), detail_match.group('amount1'), detail_match.group('amount2'), source_index=source_index)
            pending_label = None
            pending_line_index = None
            continue
        if classification == 'amount_detail':
            continue

        qty_first_match = qty_first_re.match(normalized)
'''

OLD_PENDING_LINE = '''        pending_label = normalized if _looks_like_item_label_only(normalized, store_name=store_name, filename=filename) else None
        pending_line_index = None
'''

NEW_PENDING_LINE = '''        pending_label = normalized if classification == 'continuation' else None
        pending_line_index = None
'''


def normalize_newlines(content: str) -> tuple[str, str]:
    newline = '\r\n' if '\r\n' in content else '\n'
    return content.replace('\r\n', '\n'), newline


def restore_newlines(content: str, newline: str) -> str:
    return content.replace('\n', newline) if newline != '\n' else content


def replace_once(content: str, old: str, new: str, description: str) -> str:
    count = content.count(old)
    if count != 1:
        raise SystemExit(f'Patchblok niet exact 1x gevonden: {description} ({count}x)')
    return content.replace(old, new, 1)


def insert_helper(content: str) -> str:
    if HELPER_MARKER in content:
        return content
    marker = '''def _extract_receipt_lines(lines: list[str], *, store_name: str | None = None, filename: str | None = None) -> list[dict[str, Any]]:
'''
    if marker not in content:
        raise SystemExit('Insertmarker voor _extract_receipt_lines niet gevonden')
    return content.replace(marker, HELPER + marker, 1)


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f'{TARGET} niet gevonden')

    original_raw = TARGET.read_text(encoding='utf-8')
    original, newline = normalize_newlines(original_raw)
    content = original

    content = insert_helper(content)
    content = replace_once(content, OLD_LOOP_BLOCK, NEW_LOOP_BLOCK, 'central classification before pairing')
    content = replace_once(content, OLD_DETAIL_BLOCK, NEW_DETAIL_BLOCK, 'amount_detail gate')
    content = replace_once(content, OLD_PENDING_LINE, NEW_PENDING_LINE, 'continuation classification')

    if content == original:
        print('Geen wijziging nodig')
        return

    TARGET.write_text(restore_newlines(content, newline), encoding='utf-8', newline='')
    print('8K-0 classification patch toegepast op backend/app/services/receipt_service.py')


if __name__ == '__main__':
    main()

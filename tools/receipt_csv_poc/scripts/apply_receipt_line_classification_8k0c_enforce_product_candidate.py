from __future__ import annotations

from pathlib import Path

TARGET = Path('backend/app/services/receipt_service.py')

REPLACEMENTS = [
    (
        "        if qty_first_match:\n",
        "        if classification == 'product_candidate' and qty_first_match:\n",
        'qty_first product_candidate gate',
    ),
    (
        "        if label_first_match:\n",
        "        if classification == 'product_candidate' and label_first_match:\n",
        'label_first product_candidate gate',
    ),
]


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
    if '# 8K-0B proven false-positive guards' not in original:
        raise SystemExit('8K-0B guards ontbreken; voer eerst 8K-0B uit')

    updated = original
    for old, new, description in REPLACEMENTS:
        updated = replace_once(updated, old, new, description)

    if updated == original:
        print('8K-0C gates waren al aanwezig; geen wijziging nodig')
        return

    TARGET.write_text(restore_newlines(updated, newline), encoding='utf-8', newline='')
    print('8K-0C product_candidate gates toegepast op backend/app/services/receipt_service.py')


if __name__ == '__main__':
    main()

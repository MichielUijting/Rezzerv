from __future__ import annotations

from pathlib import Path

TARGET = Path('backend/app/services/receipt_service.py')
MARKER = "    lowered = normalized.lower()\n\n"
GUARD_MARKER = "# 8K-0B proven false-positive guards"

GUARDS = '''    # 8K-0B proven false-positive guards: keep metadata/footer lines out before amount-pairing.
    upper_compact = normalized.upper().replace(',', '.')
    if re.fullmatch(r'(?:ZA|ZO|ZON)\\s+\\d{1,2}\\.\\d{2}', upper_compact):
        return 'metadata'
    if re.match(r'^[A-Z]\\s+\\d{1,2}[,.]\\d{2}%\\b', normalized.upper()):
        return 'footer_payment_tax'
    if any(day in lowered for day in ('maandag', 'dinsdag', 'woensdag', 'woernsdag', 'donderdag', 'vrijdag', 'zaterdag', 'zondag')) and ('t/m' in lowered or ' tot ' in lowered):
        return 'metadata'
    if re.fullmatch(r'\\d{1,4}[.]\\d{2}', normalized) or re.fullmatch(r'\\d{1,4},\\d{2}', normalized):
        return 'footer_payment_tax'
    if re.search(r'\\bzegels?\\b|\\bzege1s\\b|\\bpluspunten\\b', lowered) and re.search(r'\\d{1,2}:\\d{2}|\\d{3,}', normalized):
        return 'footer_payment_tax'

'''


def normalize_newlines(content: str) -> tuple[str, str]:
    newline = '\r\n' if '\r\n' in content else '\n'
    return content.replace('\r\n', '\n'), newline


def restore_newlines(content: str, newline: str) -> str:
    return content.replace('\n', newline) if newline != '\n' else content


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f'{TARGET} niet gevonden')

    original_raw = TARGET.read_text(encoding='utf-8')
    original, newline = normalize_newlines(original_raw)

    if 'def _classify_receipt_text_line(' not in original:
        raise SystemExit('_classify_receipt_text_line ontbreekt; voer eerst 8K-0A uit')

    if GUARD_MARKER in original:
        print('8K-0B guards waren al aanwezig; geen wijziging nodig')
        return

    occurrences = original.count(MARKER)
    if occurrences != 1:
        raise SystemExit(f'Verwachtte marker exact 1x, gevonden: {occurrences}x')

    updated = original.replace(MARKER, MARKER + GUARDS, 1)
    TARGET.write_text(restore_newlines(updated, newline), encoding='utf-8', newline='')
    print('8K-0B false-positive guards toegepast op backend/app/services/receipt_service.py')


if __name__ == '__main__':
    main()

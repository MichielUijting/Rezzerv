from __future__ import annotations

from app.services.receipt_line_classifier import classify_receipt_line


def run() -> dict[str, str]:
    cases = {
        'Bananen 1,99': 'ITEM',
        'Kaas jong belegen': 'ITEM_LABEL',
        '3 x 0,99 2,97': 'DETAIL',
        'SUBTOTAAL 14,36': 'META',
        'TOTAAL 14,36': 'META',
        'PIN 14,36': 'META',
        'Datum: 20-03-2026 16:27': 'META',
        'Korting -0,19': 'DISCOUNT',
        'Koopzegel digitaal 5,10': 'LOYALTY',
        'PLUSPUNTEN 12': 'LOYALTY',
    }
    mismatches: dict[str, str] = {}
    for line, expected in cases.items():
        actual = classify_receipt_line(line)
        if actual != expected:
            mismatches[line] = f'{actual} != {expected}'
    if mismatches:
        raise AssertionError(mismatches)
    return {'status': 'ok', 'checked_cases': str(len(cases))}


if __name__ == '__main__':
    print(run())

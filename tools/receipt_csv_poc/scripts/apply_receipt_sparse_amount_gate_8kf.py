from __future__ import annotations

from pathlib import Path

TARGET = Path('backend/app/services/receipt_service.py')

AMOUNT_BRANCH_REQUIRED = """        label_classification = _classify_receipt_text_line(
            label,
            store_name=store_name,
            filename=filename,
        )
        if label_classification in {'ignore', 'metadata', 'footer_payment_tax'}:
            continue
        if len(label.split()) > 12:
            continue
        extracted.append({
"""

FULL_LINE_GATE_REQUIRED = """        sparse_classification = _classify_receipt_text_line(
            normalized,
            store_name=store_name,
            filename=filename,
        )
        if sparse_classification in {'ignore', 'metadata', 'footer_payment_tax'}:
            continue
"""

TRACE_REQUIRED = """                'parser_path': '_extract_sparse_receipt_lines.amount_re',
"""


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f'{TARGET} niet gevonden')
    content = TARGET.read_text(encoding='utf-8')
    missing: list[str] = []
    if AMOUNT_BRANCH_REQUIRED not in content:
        missing.append('amount_re label_classification gate vóór extracted.append')
    if FULL_LINE_GATE_REQUIRED not in content:
        missing.append('sparse full-line classification gate vóór sparse parsing')
    if TRACE_REQUIRED not in content:
        missing.append('amount_re producer_trace parser_path')
    if missing:
        raise SystemExit('8K-F NIET akkoord; ontbreekt: ' + ', '.join(missing))
    print('8K-F akkoord: sparse amount append heeft classification gate vóór append en producer_trace blijft aanwezig')


if __name__ == '__main__':
    main()

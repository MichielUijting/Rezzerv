from __future__ import annotations

import json

from app.receipt_ingestion.parsing.line_classification_helpers import (
    RECEIPT_NON_PRODUCT_LABEL_TOKENS,
    _looks_like_non_product_receipt_label,
)

PROBE_LABELS = [
    'Contactless',
    'contactloos',
    'Merchant',
    'Terminal',
    'PAR',
    'NFC Chip',
    'Kaart',
    'Transactie',
    'Autorisatiecode',
]


def main() -> int:
    report = {
        'test': 'R9-38A14 read-only non-product/payment guard probe',
        'read_only': True,
        'database_write_intent': False,
        'tokens': list(RECEIPT_NON_PRODUCT_LABEL_TOKENS),
        'probe_results': [
            {
                'label': label,
                'looks_like_non_product_receipt_label': _looks_like_non_product_receipt_label(label),
            }
            for label in PROBE_LABELS
        ],
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

from __future__ import annotations

from pathlib import Path

TARGET = Path('backend/app/services/external_receipt_item_read_service.py')

IMPORT_ANCHOR = "from app.db import engine\n"
IMPORT_INSERT = "from app.db import engine\nfrom app.receipt_ingestion.spaarzegels_terms import is_spaarzegels_flow_excluded\n"

HELPER_ANCHOR = "def _contains(value: Any, expected: str) -> bool:\n    needle = _clean(expected).lower()\n    return not needle or needle in _clean(value).lower()\n\n\n"
HELPER_INSERT = "def _contains(value: Any, expected: str) -> bool:\n    needle = _clean(expected).lower()\n    return not needle or needle in _clean(value).lower()\n\n\ndef _receipt_item_text(item: dict[str, Any]) -> str:\n    return ' '.join(\n        _clean(value).lower()\n        for value in (\n            item.get('receipt_line_text'),\n            item.get('raw_label'),\n            item.get('normalized_label'),\n            item.get('candidate_name'),\n        )\n        if _clean(value)\n    )\n\n\ndef _is_excluded_receipt_item(item: dict[str, Any]) -> bool:\n    if 'verzendkosten' in _receipt_item_text(item):\n        return True\n    if is_spaarzegels_flow_excluded(item):\n        return True\n    return is_spaarzegels_flow_excluded({\n        'line_type': item.get('line_type'),\n        'is_spaarzegels': item.get('is_spaarzegels'),\n        'exclude_from_inventory': item.get('exclude_from_inventory'),\n        'external_matching_allowed': item.get('external_matching_allowed'),\n        'receipt_line_text': item.get('receipt_line_text'),\n        'raw_label': item.get('raw_label') or item.get('candidate_name'),\n        'normalized_label': item.get('normalized_label') or item.get('candidate_name'),\n        'line_total': item.get('line_total') or item.get('price'),\n        'unit_price': item.get('unit_price'),\n        'price': item.get('price'),\n        'quantity_label': item.get('quantity_label'),\n    })\n\n\n"

FULL_ANCHOR = "        all_items = [dict(item) for item in payload.get(\"items\") or []]\n"
FULL_INSERT = "        all_items = [\n            dict(item)\n            for item in payload.get(\"items\") or []\n            if not _is_excluded_receipt_item(dict(item))\n        ]\n"

LIGHT_ANCHOR = "        lightweight_items = _m2c2i_fix7b_dedupe_top_receipt_items(placeholders)\n"
LIGHT_INSERT = "        lightweight_items = [\n            item\n            for item in _m2c2i_fix7b_dedupe_top_receipt_items(placeholders)\n            if not _is_excluded_receipt_item(item)\n        ]\n"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: verwacht exact 1 treffer, gevonden {count}')
    return source.replace(old, new, 1)


def main() -> None:
    source = TARGET.read_text(encoding='utf-8')

    if 'def _is_excluded_receipt_item(' in source:
        print('RECEIPT_PAGINATION_EXCLUSION_FIX_ALREADY_APPLIED')
        return

    source = replace_once(source, IMPORT_ANCHOR, IMPORT_INSERT, 'import')
    source = replace_once(source, HELPER_ANCHOR, HELPER_INSERT, 'helpers')
    source = replace_once(source, FULL_ANCHOR, FULL_INSERT, 'full projection')
    source = replace_once(source, LIGHT_ANCHOR, LIGHT_INSERT, 'lightweight projection')

    TARGET.write_text(source, encoding='utf-8', newline='\n')
    print('RECEIPT_PAGINATION_EXCLUSION_FIX_APPLIED')


if __name__ == '__main__':
    main()

from __future__ import annotations

from pathlib import Path

TARGET = Path('backend/tests/test_off_product_type_link_contract_selftest.py')

OLD_COLUMNS = """                candidate_source_name, candidate_source_product_code,
                score, candidate_status, is_user_confirmed,
"""
NEW_COLUMNS = """                candidate_source_name, candidate_source_product_code,
                source_name, source_product_code,
                score, candidate_status, is_user_confirmed,
"""

OLD_VALUES = """                'contract_selftest', :gtin,
                1.0, 'candidate', 0,
"""
NEW_VALUES = """                'contract_selftest', :gtin,
                'contract_selftest', :gtin,
                1.0, 'candidate', 0,
"""


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: verwacht exact 1 treffer, gevonden {count}')
    return source.replace(old, new, 1)


def main() -> None:
    source = TARGET.read_text(encoding='utf-8-sig')
    if 'source_name, source_product_code' in source:
        print('OFF_CONTRACT_CANDIDATE_SCHEMA_FIX_ALREADY_APPLIED')
        return
    source = replace_once(source, OLD_COLUMNS, NEW_COLUMNS, 'kolommen')
    source = replace_once(source, OLD_VALUES, NEW_VALUES, 'waarden')
    TARGET.write_text(source, encoding='utf-8', newline='\n')
    print('OFF_CONTRACT_CANDIDATE_SCHEMA_FIX_APPLIED')


if __name__ == '__main__':
    main()

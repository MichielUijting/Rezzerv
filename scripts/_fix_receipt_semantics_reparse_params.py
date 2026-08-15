from pathlib import Path

root = Path(__file__).resolve().parents[1]
service_path = root / 'backend/app/services/receipt_service.py'
s = service_path.read_text(encoding='utf-8')

anchor = """                        'matched_article_id': None,
                        'confidence_score': line.get('confidence_score'),
                    },
                )
        else:
"""
replacement = """                        'matched_article_id': None,
                        'confidence_score': line.get('confidence_score'),
                        'line_role': semantics['line_role'],
                        'inventory_eligible': 1 if semantics['inventory_eligible'] else 0,
                    },
                )
        else:
"""
if anchor not in s:
    raise SystemExit('reparse parameter-map anchor not found')
s = s.replace(anchor, replacement, 1)
service_path.write_text(s, encoding='utf-8')

test_path = root / 'backend/tests/test_receipt_inventory_eligibility.py'
t = test_path.read_text(encoding='utf-8')
old = """    assert source.count('semantics = derive_receipt_line_semantics(line, store_name=parse_result.store_name)') == 2
    assert source.count('ensure_receipt_line_semantics_schema(conn)') >= 2
"""
new = """    assert source.count('semantics = derive_receipt_line_semantics(line, store_name=parse_result.store_name)') == 2
    assert source.count("'line_role': semantics['line_role']") == 2
    assert source.count("'inventory_eligible': 1 if semantics['inventory_eligible'] else 0") == 2
    assert source.count('ensure_receipt_line_semantics_schema(conn)') >= 2
"""
if old not in t:
    raise SystemExit('persistence test anchor not found')
t = t.replace(old, new, 1)
test_path.write_text(t, encoding='utf-8')
print('REPARSE_SEMANTIC_PARAMS_FIXED')

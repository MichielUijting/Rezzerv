from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / 'backend/app/services/receipt_service.py'
text = path.read_text(encoding='utf-8')

old = """            if parse_result.is_receipt:
                for index, line in enumerate(parse_result.lines):
                    logical_line_key = resolve_reimport_logical_line_key(reimport_lineage, index, line) or uuid.uuid4().hex
"""
new = """            if parse_result.is_receipt:
                ensure_receipt_line_semantics_schema(conn)
                for index, line in enumerate(parse_result.lines):
                    semantics = derive_receipt_line_semantics(line, store_name=parse_result.store_name)
                    logical_line_key = resolve_reimport_logical_line_key(reimport_lineage, index, line) or uuid.uuid4().hex
"""
if old not in text:
    raise SystemExit('primary ingest loop anchor not found')
text = text.replace(old, new, 1)
path.write_text(text, encoding='utf-8')

# Strengthen permanent regression test with a source-level persistence contract.
test_path = root / 'backend/tests/test_receipt_inventory_eligibility.py'
test = test_path.read_text(encoding='utf-8')
append = '''\n\ndef test_receipt_service_persists_semantics_on_both_ingest_paths():\n    from pathlib import Path\n\n    source = (Path(__file__).resolve().parents[1] / 'app/services/receipt_service.py').read_text(encoding='utf-8')\n    assert source.count('INSERT INTO receipt_table_lines') == 2\n    assert source.count('line_role, inventory_eligible') == 2\n    assert source.count('semantics = derive_receipt_line_semantics(line, store_name=parse_result.store_name)') == 2\n    assert source.count('ensure_receipt_line_semantics_schema(conn)') >= 2\n'''
if 'test_receipt_service_persists_semantics_on_both_ingest_paths' not in test:
    test += append
test_path.write_text(test, encoding='utf-8')
print('PRIMARY_INGEST_SEMANTICS_FIXED')

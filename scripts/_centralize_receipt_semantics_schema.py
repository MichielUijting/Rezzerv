from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]

# main.py: put semantic columns in the existing central receipt-line schema evolution.
p = root / 'backend/app/main.py'
s = p.read_text(encoding='utf-8')
old = """        line_additions = {
            'corrected_raw_label': 'TEXT',
"""
new = """        line_additions = {
            'line_role': 'TEXT',
            'inventory_eligible': 'INTEGER',
            'corrected_raw_label': 'TEXT',
"""
if old not in s:
    raise SystemExit('central line_additions anchor not found')
s = s.replace(old, new, 1)

s = s.replace(
    "from app.receipt_ingestion.receipt_line_semantics import (\n    ensure_receipt_line_semantics_schema,\n    derive_receipt_line_semantics,\n)\n",
    "from app.receipt_ingestion.receipt_line_semantics import derive_receipt_line_semantics\n",
    1,
)
s = s.replace("    ensure_receipt_line_semantics_schema(conn)\n\n", "", 1)
p.write_text(s, encoding='utf-8')

# semantics module: remove duplicate/lazy schema authority.
p = root / 'backend/app/receipt_ingestion/receipt_line_semantics.py'
s = p.read_text(encoding='utf-8')
s = s.replace('from sqlalchemy import text\n\n', '', 1)
s, count = re.subn(
    r"\n\ndef ensure_receipt_line_semantics_schema\(conn\) -> None:.*?(?=\n\ndef _semantic_text)",
    '',
    s,
    count=1,
    flags=re.S,
)
if count != 1:
    raise SystemExit('duplicate semantic schema helper not found')
p.write_text(s, encoding='utf-8')

# receipt_service: use the central startup schema authority only.
p = root / 'backend/app/services/receipt_service.py'
s = p.read_text(encoding='utf-8')
s = s.replace(
    "from app.receipt_ingestion.receipt_line_semantics import (\n    ensure_receipt_line_semantics_schema,\n    derive_receipt_line_semantics,\n)\n",
    "from app.receipt_ingestion.receipt_line_semantics import derive_receipt_line_semantics\n",
    1,
)
s = s.replace('                ensure_receipt_line_semantics_schema(conn)\n', '', 1)
s = s.replace('            ensure_receipt_line_semantics_schema(conn)\n', '', 1)
p.write_text(s, encoding='utf-8')

# tests: replace helper-specific schema test with the active central schema contract.
p = root / 'backend/tests/test_receipt_inventory_eligibility.py'
s = p.read_text(encoding='utf-8')
s = s.replace('from sqlalchemy import create_engine, text\n\n', '', 1)
s = s.replace(
    "from app.receipt_ingestion.receipt_line_semantics import (\n    derive_receipt_line_semantics,\n    ensure_receipt_line_semantics_schema,\n)\n",
    "from app.receipt_ingestion.receipt_line_semantics import derive_receipt_line_semantics\n",
    1,
)
s, count = re.subn(
    r"\n\ndef test_schema_columns_are_active_and_idempotent\(\):.*?(?=\n\ndef test_receipt_service_persists_semantics_on_both_ingest_paths)",
    "\n\ndef test_semantic_columns_live_in_central_receipt_schema_evolution():\n"
    "    from pathlib import Path\n\n"
    "    source = (Path(__file__).resolve().parents[1] / 'app/main.py').read_text(encoding='utf-8')\n"
    "    start = source.index('line_additions = {')\n"
    "    block = source[start:start + 1200]\n"
    "    assert \"'line_role': 'TEXT'\" in block\n"
    "    assert \"'inventory_eligible': 'INTEGER'\" in block\n",
    s,
    count=1,
    flags=re.S,
)
if count != 1:
    raise SystemExit('old schema unit test not found')
s = s.replace("    assert source.count('ensure_receipt_line_semantics_schema(conn)') >= 2\n", "")
p.write_text(s, encoding='utf-8')

# Hard audit: there must be exactly one schema authority for these semantic columns.
combined = '\n'.join(
    (root / rel).read_text(encoding='utf-8')
    for rel in (
        'backend/app/main.py',
        'backend/app/receipt_ingestion/receipt_line_semantics.py',
        'backend/app/services/receipt_service.py',
    )
)
if 'ensure_receipt_line_semantics_schema' in combined:
    raise SystemExit('duplicate semantic schema authority still present')

print('CENTRAL_SCHEMA_INTEGRATION_APPLIED')

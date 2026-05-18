from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'backend' / 'app' / 'main.py'
BACKUP = ROOT / 'backend' / 'app' / 'main.py.bak-r5c'

content = TARGET.read_text(encoding='utf-8-sig')
BACKUP.write_text(content, encoding='utf-8')

signature_anchor = """async def upload_receipt(
    household_id: str,
    file: UploadFile = File(...),
"""

replacement_signature = """async def upload_receipt(
    household_id: str,
    debug: int = Query(default=0),
    file: UploadFile = File(...),
"""

if replacement_signature not in content:
    if signature_anchor not in content:
        raise SystemExit('R5c patch aborted: upload_receipt signature anchor not found.')
    content = content.replace(signature_anchor, replacement_signature, 1)

call_anchor = """        failed_store_name=failed_store_name,
        failed_purchase_at=failed_purchase_at,
    )
"""

call_replacement = """        failed_store_name=failed_store_name,
        failed_purchase_at=failed_purchase_at,
        include_debug=bool(debug),
    )
"""

if "include_debug=bool(debug)" not in content:
    if call_anchor not in content:
        raise SystemExit('R5c patch aborted: ingest_receipt call anchor not found.')
    content = content.replace(call_anchor, call_replacement, 1)

TARGET.write_text(content, encoding='utf-8')
print('R5c patch applied to', TARGET)
print('Backup written to', BACKUP)

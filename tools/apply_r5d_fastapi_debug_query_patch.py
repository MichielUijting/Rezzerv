from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'backend' / 'app' / 'main.py'
BACKUP = ROOT / 'backend' / 'app' / 'main.py.bak-r5d'

content = TARGET.read_text(encoding='utf-8-sig')
BACKUP.write_text(content, encoding='utf-8')

signature_anchor = """async def upload_receipt_files(
    household_id: str,
    files: list[UploadFile] = File(...),
"""

signature_replacement = """async def upload_receipt_files(
    household_id: str,
    debug: int = Query(default=0),
    files: list[UploadFile] = File(...),
"""

if signature_replacement not in content:
    if signature_anchor not in content:
        raise SystemExit('R5d patch aborted: upload_receipt_files signature not found.')
    content = content.replace(signature_anchor, signature_replacement, 1)

call_anchor = """                failed_store_name=failed_store_name,
                failed_purchase_at=failed_purchase_at,
            )
"""

call_replacement = """                failed_store_name=failed_store_name,
                failed_purchase_at=failed_purchase_at,
                include_debug=bool(debug),
            )
"""

if "include_debug=bool(debug)" not in content:
    if call_anchor not in content:
        raise SystemExit('R5d patch aborted: import_uploaded_receipt_payload call not found.')
    content = content.replace(call_anchor, call_replacement, 1)

TARGET.write_text(content, encoding='utf-8')
print('R5d FastAPI debug query patch applied to', TARGET)
print('Backup written to', BACKUP)

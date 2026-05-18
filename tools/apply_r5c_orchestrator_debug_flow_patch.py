from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'backend' / 'app' / 'main.py'
BACKUP = ROOT / 'backend' / 'app' / 'main.py.bak-r5c-flow'

content = TARGET.read_text(encoding='utf-8-sig')
BACKUP.write_text(content, encoding='utf-8')

old_signature = """def import_uploaded_receipt_payload(
    household_id: str,
    filename: str,
    file_bytes: bytes,
    source_id: str | None = None,
    mime_type: str | None = None,
    reject_non_receipt: bool = False,
    create_failed_receipt_table: bool = False,
    failed_store_name: str | None = None,
    failed_purchase_at: str | None = None,
) -> dict[str, Any]:"""

new_signature = """def import_uploaded_receipt_payload(
    household_id: str,
    filename: str,
    file_bytes: bytes,
    source_id: str | None = None,
    mime_type: str | None = None,
    reject_non_receipt: bool = False,
    create_failed_receipt_table: bool = False,
    failed_store_name: str | None = None,
    failed_purchase_at: str | None = None,
    include_debug: bool = False,
) -> dict[str, Any]:"""

if new_signature not in content:
    if old_signature not in content:
        raise SystemExit('R5c flow patch aborted: import_uploaded_receipt_payload signature not found.')
    content = content.replace(old_signature, new_signature, 1)

recursive_anchor = """                    create_failed_receipt_table=create_failed_receipt_table,
                    failed_store_name=failed_store_name,
                    failed_purchase_at=failed_purchase_at,
                )
"""

recursive_replacement = """                    create_failed_receipt_table=create_failed_receipt_table,
                    failed_store_name=failed_store_name,
                    failed_purchase_at=failed_purchase_at,
                    include_debug=include_debug,
                )
"""

if recursive_replacement not in content:
    if recursive_anchor not in content:
        raise SystemExit('R5c flow patch aborted: recursive import anchor not found.')
    content = content.replace(recursive_anchor, recursive_replacement, 1)

ingest_anchor = """        create_failed_receipt_table=create_failed_receipt_table,
        failed_store_name=failed_store_name,
        failed_purchase_at=failed_purchase_at,
    )
"""

ingest_replacement = """        create_failed_receipt_table=create_failed_receipt_table,
        failed_store_name=failed_store_name,
        failed_purchase_at=failed_purchase_at,
        include_debug=include_debug,
    )
"""

if ingest_replacement not in content:
    if ingest_anchor not in content:
        raise SystemExit('R5c flow patch aborted: ingest_receipt anchor not found.')
    content = content.replace(ingest_anchor, ingest_replacement, 1)

TARGET.write_text(content, encoding='utf-8')
print('R5c orchestrator flow patch applied to', TARGET)
print('Backup written to', BACKUP)

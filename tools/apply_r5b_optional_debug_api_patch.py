from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'backend' / 'app' / 'main.py'
BACKUP = ROOT / 'backend' / 'app' / 'main.py.bak-r5b'

content = TARGET.read_text(encoding='utf-8-sig')
BACKUP.write_text(content, encoding='utf-8')

serializer_import = 'from app.receipt_ingestion.parser_debug_serializer import build_parser_debug_payload'
anchor_import = 'from app.services.receipt_service import dedupe_receipts_for_household, ensure_default_receipt_sources, ensure_share_receipt_source, ingest_receipt, parse_receipt_content, repair_receipts_for_household, reparse_receipt, scan_receipt_source, serialize_receipt_row'
if serializer_import not in content:
    if anchor_import not in content:
        raise SystemExit('R5b patch aborted: receipt service import anchor not found.')
    content = content.replace(anchor_import, anchor_import + '\n' + serializer_import, 1)

TARGET.write_text(content, encoding='utf-8')
print('R5b preparation patch applied to', TARGET)
print('Backup written to', BACKUP)

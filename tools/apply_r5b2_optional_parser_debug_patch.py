from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'backend' / 'app' / 'services' / 'receipt_service.py'
BACKUP = ROOT / 'backend' / 'app' / 'services' / 'receipt_service.py.bak-r5b2'

content = TARGET.read_text(encoding='utf-8-sig')
BACKUP.write_text(content, encoding='utf-8')

import_anchor = 'from app.receipt_ingestion.parser_diagnostics import summarize_lines_parser_diagnostics'
serializer_import = 'from app.receipt_ingestion.parser_debug_serializer import build_parser_debug_payload'
if serializer_import not in content:
    if import_anchor not in content:
        raise SystemExit('R5b-2 patch aborted: diagnostics import anchor not found.')
    content = content.replace(import_anchor, import_anchor + '\n' + serializer_import, 1)

old_signature = """def ingest_receipt(engine, receipt_storage_root: Path, household_id: str, filename: str, file_bytes: bytes, source_id: str | None = None, mime_type: str | None = None, reject_non_receipt: bool = False, create_failed_receipt_table: bool = False, failed_store_name: str | None = None, failed_purchase_at: str | None = None) -> dict[str, Any]:"""
new_signature = """def ingest_receipt(engine, receipt_storage_root: Path, household_id: str, filename: str, file_bytes: bytes, source_id: str | None = None, mime_type: str | None = None, reject_non_receipt: bool = False, create_failed_receipt_table: bool = False, failed_store_name: str | None = None, failed_purchase_at: str | None = None, include_debug: bool = False) -> dict[str, Any]:"""
if new_signature not in content:
    if old_signature not in content:
        raise SystemExit('R5b-2 patch aborted: ingest_receipt signature not found.')
    content = content.replace(old_signature, new_signature, 1)

old_return = """        return {
            'raw_receipt_id': raw_receipt_id,
            'receipt_table_id': receipt_table_id,
            'duplicate': False,
            'parse_status': determine_final_parse_status(parse_result),
        }
"""
new_return = """        response = {
            'raw_receipt_id': raw_receipt_id,
            'receipt_table_id': receipt_table_id,
            'duplicate': False,
            'parse_status': determine_final_parse_status(parse_result),
        }
        if include_debug:
            response['parser_debug'] = build_parser_debug_payload(parse_result)
        return response
"""

if new_return in content:
    raise SystemExit('R5b-2 patch aborted: parser debug response already present.')
if old_return not in content:
    raise SystemExit('R5b-2 patch aborted: ingest_receipt return block not found.')

content = content.replace(old_return, new_return, 1)
TARGET.write_text(content, encoding='utf-8')
print('R5b-2 patch applied to', TARGET)
print('Backup written to', BACKUP)

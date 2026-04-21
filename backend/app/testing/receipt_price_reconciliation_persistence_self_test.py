from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / 'backend') not in sys.path:
    sys.path.insert(0, str(ROOT / 'backend'))

from app.services.receipt_service import ingest_receipt, reparse_receipt  # noqa: E402

TEST_RECEIPT = b'''ALDI\n12-04-2026 12:34\nBananen 1,41\nMelk 1,29\nBrood 1,20\nSUBTOTAAL 3,86\nTOTAAL 3,86\nPIN 3,86\n'''


def _create_minimal_receipt_schema(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text('''
            CREATE TABLE raw_receipts (
                id TEXT PRIMARY KEY,
                household_id TEXT,
                source_id TEXT,
                original_filename TEXT,
                mime_type TEXT,
                storage_path TEXT,
                sha256_hash TEXT,
                raw_status TEXT,
                deleted_at DATETIME,
                duplicate_of_raw_receipt_id TEXT
            )
        '''))
        conn.execute(text('''
            CREATE TABLE receipt_tables (
                id TEXT PRIMARY KEY,
                raw_receipt_id TEXT,
                household_id TEXT,
                store_name TEXT,
                store_branch TEXT,
                purchase_at TEXT,
                total_amount NUMERIC,
                discount_total NUMERIC,
                currency TEXT,
                parse_status TEXT,
                inbox_status TEXT,
                confidence_score NUMERIC,
                line_count INTEGER,
                deleted_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        '''))
        conn.execute(text('''
            CREATE TABLE receipt_table_lines (
                id TEXT PRIMARY KEY,
                receipt_table_id TEXT,
                line_index INTEGER,
                raw_label TEXT,
                corrected_raw_label TEXT,
                normalized_label TEXT,
                quantity NUMERIC,
                corrected_quantity NUMERIC,
                unit TEXT,
                corrected_unit TEXT,
                unit_price NUMERIC,
                corrected_unit_price NUMERIC,
                line_total NUMERIC,
                corrected_line_total NUMERIC,
                discount_amount NUMERIC,
                barcode TEXT,
                article_match_status TEXT,
                matched_article_id TEXT,
                matched_global_product_id TEXT,
                confidence_score NUMERIC,
                is_deleted INTEGER DEFAULT 0,
                is_validated INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        '''))
        conn.execute(text('''
            CREATE TABLE receipt_email_messages (
                raw_receipt_id TEXT PRIMARY KEY,
                body_html TEXT,
                body_text TEXT,
                selected_part_type TEXT,
                received_at TEXT,
                sender_email TEXT,
                subject TEXT
            )
        '''))
        conn.execute(text('CREATE INDEX idx_raw_receipts_household_hash ON raw_receipts(household_id, sha256_hash)'))
        conn.execute(text('CREATE INDEX idx_receipt_lines_receipt_lineindex ON receipt_table_lines(receipt_table_id, line_index)'))


def _fetch_lines(engine, receipt_table_id: str) -> list[dict]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                '''
                SELECT line_index, raw_label, unit_price, corrected_unit_price, line_total, corrected_line_total
                FROM receipt_table_lines
                WHERE receipt_table_id = :receipt_table_id
                ORDER BY line_index ASC
                '''
            ),
            {'receipt_table_id': receipt_table_id},
        ).mappings().all()
    return [dict(row) for row in rows]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix='rezzerv-recon-selftest-') as temp_dir:
        temp_root = Path(temp_dir)
        db_path = temp_root / 'rezzerv.db'
        engine = create_engine(f'sqlite:///{db_path}', future=True)
        _create_minimal_receipt_schema(engine)

        storage_root = temp_root / 'receipts'
        storage_root.mkdir(parents=True, exist_ok=True)

        ingest_result = ingest_receipt(
            engine,
            storage_root,
            'self-test-household',
            'receipt-reconciliation-trigger.txt',
            TEST_RECEIPT,
            mime_type='text/plain',
            create_failed_receipt_table=True,
        )
        receipt_table_id = str(ingest_result['receipt_table_id'])
        after_ingest = _fetch_lines(engine, receipt_table_id)

        reparse_result = reparse_receipt(engine, storage_root, receipt_table_id)
        after_reparse = _fetch_lines(engine, receipt_table_id)

        corrected_ingest = next((row for row in after_ingest if row.get('raw_label') == 'Melk'), None)
        corrected_reparse = next((row for row in after_reparse if row.get('raw_label') == 'Melk'), None)

        failures: list[str] = []
        if ingest_result.get('parse_status') != 'parsed':
            failures.append(f"ingest parse_status expected parsed got {ingest_result.get('parse_status')}")
        if not corrected_ingest or float(corrected_ingest.get('corrected_line_total') or 0) != 1.25:
            failures.append(f'ingest corrected_line_total missing or unexpected: {corrected_ingest}')
        if not corrected_ingest or float(corrected_ingest.get('line_total') or 0) != 1.29:
            failures.append(f'ingest raw line_total should remain original OCR value: {corrected_ingest}')
        if not corrected_reparse or float(corrected_reparse.get('corrected_line_total') or 0) != 1.25:
            failures.append(f'reparse corrected_line_total missing or unexpected: {corrected_reparse}')
        if not corrected_reparse or float(corrected_reparse.get('line_total') or 0) != 1.29:
            failures.append(f'reparse raw line_total should remain original OCR value: {corrected_reparse}')

        report = {
            'ingest_result': ingest_result,
            'reparse_result': reparse_result,
            'after_ingest': after_ingest,
            'after_reparse': after_reparse,
            'failed_count': len(failures),
            'failures': failures,
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())

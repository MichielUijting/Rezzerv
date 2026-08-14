from sqlalchemy import create_engine, text

from app.services.receipt_reimport_lineage_service import (
    get_prior_processed_line_fact,
    load_deleted_reimport_lineage,
    resolve_reimport_logical_line_key,
    was_prior_line_validated,
)


def _engine():
    engine = create_engine('sqlite+pysqlite:///:memory:', future=True)
    with engine.begin() as conn:
        conn.execute(text('''
            CREATE TABLE raw_receipts (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                sha256_hash TEXT NOT NULL,
                deleted_at DATETIME
            )
        '''))
        conn.execute(text('''
            CREATE TABLE receipt_tables (
                id TEXT PRIMARY KEY,
                raw_receipt_id TEXT NOT NULL,
                household_id TEXT NOT NULL,
                logical_receipt_key TEXT,
                workflow_state TEXT NOT NULL,
                approved_at DATETIME,
                deleted_at DATETIME,
                updated_at DATETIME
            )
        '''))
        conn.execute(text('''
            CREATE TABLE receipt_table_lines (
                id TEXT PRIMARY KEY,
                receipt_table_id TEXT NOT NULL,
                line_index INTEGER NOT NULL,
                raw_label TEXT,
                normalized_label TEXT,
                quantity NUMERIC,
                unit TEXT,
                unit_price NUMERIC,
                line_total NUMERIC,
                logical_line_key TEXT,
                is_validated INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME
            )
        '''))
        conn.execute(text('''
            CREATE TABLE purchase_import_batches (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                source_type TEXT,
                source_reference TEXT,
                import_status TEXT
            )
        '''))
        conn.execute(text('''
            CREATE TABLE purchase_import_lines (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                external_line_ref TEXT,
                processing_status TEXT,
                processed_at DATETIME,
                processed_event_id TEXT,
                created_at DATETIME
            )
        '''))
        conn.execute(text('''
            CREATE TABLE inventory_events (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                source_reference TEXT
            )
        '''))
    return engine


def _line(raw_label, normalized_label, quantity, unit, unit_price, line_total):
    return {
        'raw_label': raw_label,
        'normalized_label': normalized_label,
        'quantity': quantity,
        'unit': unit,
        'unit_price': unit_price,
        'line_total': line_total,
    }


def test_full_delete_then_reimport_preserves_processed_fact_and_pending_line():
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO raw_receipts VALUES ('raw-old','0','same-hash',CURRENT_TIMESTAMP)"))
        conn.execute(text('''
            INSERT INTO receipt_tables
              (id, raw_receipt_id, household_id, logical_receipt_key, workflow_state, approved_at, deleted_at, updated_at)
            VALUES
              ('receipt-old','raw-old','0','receipt-key','removed_reimport_allowed',NULL,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
        '''))
        conn.execute(text('''
            INSERT INTO receipt_table_lines
              (id, receipt_table_id, line_index, raw_label, normalized_label, quantity, unit, unit_price, line_total, logical_line_key, is_validated, created_at)
            VALUES
              ('line-processed','receipt-old',0,'MELK 1L','melk 1l',1,'stuk',1.25,1.25,'logical-processed',1,CURRENT_TIMESTAMP),
              ('line-pending','receipt-old',1,'BROOD','brood',1,'stuk',2.50,2.50,'logical-pending',1,CURRENT_TIMESTAMP)
        '''))
        conn.execute(text('''
            INSERT INTO purchase_import_batches
              (id, household_id, source_type, source_reference, import_status)
            VALUES ('batch-old','0','receipt','receipt:receipt-old','in_review')
        '''))
        conn.execute(text('''
            INSERT INTO purchase_import_lines
              (id, batch_id, external_line_ref, processing_status, processed_at, processed_event_id, created_at)
            VALUES
              ('pil-processed','batch-old','receipt-line:line-processed','processed',CURRENT_TIMESTAMP,'event-existing',CURRENT_TIMESTAMP),
              ('pil-pending','batch-old','receipt-line:line-pending','pending',NULL,NULL,CURRENT_TIMESTAMP)
        '''))
        conn.execute(text("INSERT INTO inventory_events VALUES ('event-existing','0','receipt:receipt-old')"))

        lineage = load_deleted_reimport_lineage(conn, '0', 'same-hash')
        assert lineage is not None
        assert lineage['logical_receipt_key'] == 'receipt-key'

        processed_line = _line('MELK 1L', 'melk 1l', 1, 'stuk', 1.25, 1.25)
        pending_line = _line('BROOD', 'brood', 1, 'stuk', 2.50, 2.50)

        assert resolve_reimport_logical_line_key(lineage, 0, processed_line) == 'logical-processed'
        assert resolve_reimport_logical_line_key(lineage, 1, pending_line) == 'logical-pending'
        assert was_prior_line_validated(lineage, 0, processed_line) is True
        assert was_prior_line_validated(lineage, 1, pending_line) is True

        processed_fact = get_prior_processed_line_fact(
            conn,
            'logical-processed',
            current_receipt_table_id='receipt-reimport',
        )
        pending_fact = get_prior_processed_line_fact(
            conn,
            'logical-pending',
            current_receipt_table_id='receipt-reimport',
        )

        assert processed_fact is not None
        assert processed_fact['processed_event_id'] == 'event-existing'
        assert processed_fact['processing_status'] == 'processed'
        assert pending_fact is None
        assert conn.execute(text("SELECT COUNT(*) FROM inventory_events WHERE id='event-existing'")).scalar_one() == 1


def test_changed_reimport_line_does_not_reuse_old_logical_line_identity():
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO raw_receipts VALUES ('raw-old','0','same-hash',CURRENT_TIMESTAMP)"))
        conn.execute(text('''
            INSERT INTO receipt_tables
              (id, raw_receipt_id, household_id, logical_receipt_key, workflow_state, approved_at, deleted_at, updated_at)
            VALUES
              ('receipt-old','raw-old','0','receipt-key','removed_reimport_allowed',NULL,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
        '''))
        conn.execute(text('''
            INSERT INTO receipt_table_lines
              (id, receipt_table_id, line_index, raw_label, normalized_label, quantity, unit, unit_price, line_total, logical_line_key, is_validated, created_at)
            VALUES
              ('line-old','receipt-old',0,'MELK 1L','melk 1l',1,'stuk',1.25,1.25,'logical-old',1,CURRENT_TIMESTAMP)
        '''))

        lineage = load_deleted_reimport_lineage(conn, '0', 'same-hash')
        changed_line = _line('MELK 2L', 'melk 2l', 2, 'stuk', 1.25, 2.50)

        assert resolve_reimport_logical_line_key(lineage, 0, changed_line) is None
        assert was_prior_line_validated(lineage, 0, changed_line) is False

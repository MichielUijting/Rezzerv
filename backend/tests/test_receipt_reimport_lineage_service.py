from sqlalchemy import create_engine, text

from app.services.receipt_reimport_lineage_service import (
    get_prior_processed_line_fact,
    load_deleted_reimport_lineage,
    resolve_reimport_logical_line_key,
    was_prior_line_validated,
)


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE raw_receipts (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                sha256_hash TEXT NOT NULL,
                deleted_at DATETIME
            )
        """))
        conn.execute(text("""
            CREATE TABLE receipt_tables (
                id TEXT PRIMARY KEY,
                raw_receipt_id TEXT NOT NULL,
                logical_receipt_key TEXT,
                workflow_state TEXT NOT NULL DEFAULT 'active',
                deleted_at DATETIME,
                updated_at DATETIME
            )
        """))
        conn.execute(text("""
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
        """))
        conn.execute(text("""
            CREATE TABLE purchase_import_batches (
                id TEXT PRIMARY KEY,
                source_type TEXT,
                source_reference TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE purchase_import_lines (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                external_line_ref TEXT,
                processing_status TEXT,
                processed_at DATETIME,
                processed_event_id TEXT,
                created_at DATETIME
            )
        """))
    return engine


def _seed_deleted_receipt(conn, *, workflow_state="removed_reimport_allowed", is_validated=0):
    conn.execute(text("INSERT INTO raw_receipts VALUES ('raw-old','0','abc',CURRENT_TIMESTAMP)"))
    conn.execute(text("""
        INSERT INTO receipt_tables
            (id, raw_receipt_id, logical_receipt_key, workflow_state, deleted_at, updated_at)
        VALUES
            ('receipt-old','raw-old','receipt-key',:workflow_state,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
    """), {"workflow_state": workflow_state})
    conn.execute(text("""
        INSERT INTO receipt_table_lines
            (id, receipt_table_id, line_index, raw_label, normalized_label, quantity, unit, unit_price, line_total, logical_line_key, is_validated, created_at)
        VALUES
            ('line-old','receipt-old',0,'Melk','melk',1,'liter',1.25,1.25,'line-key',:is_validated,CURRENT_TIMESTAMP)
    """), {"is_validated": int(bool(is_validated))})


def _matching_line():
    return {
        'raw_label': 'Melk',
        'normalized_label': 'melk',
        'quantity': 1,
        'unit': 'liter',
        'unit_price': 1.25,
        'line_total': 1.25,
    }


def test_reimport_lineage_reuses_exact_receipt_and_line_keys_only():
    engine = _engine()
    with engine.begin() as conn:
        _seed_deleted_receipt(conn)
        lineage = load_deleted_reimport_lineage(conn, '0', 'abc')

    assert lineage is not None
    assert lineage['receipt_table_id'] == 'receipt-old'
    assert lineage['logical_receipt_key'] == 'receipt-key'
    assert resolve_reimport_logical_line_key(lineage, 0, _matching_line()) == 'line-key'
    assert resolve_reimport_logical_line_key(
        lineage,
        0,
        {'raw_label': 'Melk', 'normalized_label': 'melk', 'quantity': 2, 'unit': 'liter', 'unit_price': 1.25, 'line_total': 2.50},
    ) is None


def test_prior_kassa_validation_is_preserved_for_exact_line_match():
    engine = _engine()
    with engine.begin() as conn:
        _seed_deleted_receipt(conn, is_validated=1)
        lineage = load_deleted_reimport_lineage(conn, '0', 'abc')

    assert resolve_reimport_logical_line_key(lineage, 0, _matching_line()) == 'line-key'
    assert was_prior_line_validated(lineage, 0, _matching_line()) is True


def test_unvalidated_prior_line_stays_unvalidated():
    engine = _engine()
    with engine.begin() as conn:
        _seed_deleted_receipt(conn, is_validated=0)
        lineage = load_deleted_reimport_lineage(conn, '0', 'abc')

    assert was_prior_line_validated(lineage, 0, _matching_line()) is False


def test_non_reimportable_deleted_receipt_is_not_lineage_source():
    engine = _engine()
    with engine.begin() as conn:
        _seed_deleted_receipt(conn, workflow_state='legacy_deleted')
        assert load_deleted_reimport_lineage(conn, '0', 'abc') is None


def test_prior_processed_line_fact_uses_existing_unpack_state():
    engine = _engine()
    with engine.begin() as conn:
        _seed_deleted_receipt(conn, is_validated=1)
        conn.execute(text("INSERT INTO purchase_import_batches VALUES ('batch-old','receipt','receipt:receipt-old')"))
        conn.execute(text("""
            INSERT INTO purchase_import_lines
                (id, batch_id, external_line_ref, processing_status, processed_at, processed_event_id, created_at)
            VALUES
                ('pil-old','batch-old','receipt-line:line-old','processed',CURRENT_TIMESTAMP,'event-old',CURRENT_TIMESTAMP)
        """))
        fact = get_prior_processed_line_fact(conn, 'line-key', current_receipt_table_id='receipt-new')

    assert fact is not None
    assert fact['purchase_import_line_id'] == 'pil-old'
    assert fact['processing_status'] == 'processed'
    assert fact['processed_event_id'] == 'event-old'


def test_approved_but_unprocessed_line_remains_pending_for_unpacking():
    engine = _engine()
    with engine.begin() as conn:
        _seed_deleted_receipt(conn, is_validated=1)
        conn.execute(text("INSERT INTO purchase_import_batches VALUES ('batch-old','receipt','receipt:receipt-old')"))
        conn.execute(text("""
            INSERT INTO purchase_import_lines
                (id, batch_id, external_line_ref, processing_status, processed_at, processed_event_id, created_at)
            VALUES
                ('pil-old','batch-old','receipt-line:line-old','pending',NULL,NULL,CURRENT_TIMESTAMP)
        """))
        lineage = load_deleted_reimport_lineage(conn, '0', 'abc')
        processed_fact = get_prior_processed_line_fact(conn, 'line-key', current_receipt_table_id='receipt-new')

    assert was_prior_line_validated(lineage, 0, _matching_line()) is True
    assert processed_fact is None

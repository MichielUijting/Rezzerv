"""Deterministic PostgreSQL fixture for F6-01 Kassa approval rollback authority."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import text

from p0_kassa_review_fixture import (
    FINANCIAL_RECEIPT_ID,
    TARGET_ADMIN_EMAIL,
    TARGET_HOUSEHOLD,
    create_postgresql_runtime_test_engine,
    prepare as prepare_p0_kassa_review,
)

PRESTATE_PATH = Path('/tmp/f6-kassa-controlled-5xx-prestate.json')
SOURCE_REFERENCE = f'receipt:{FINANCIAL_RECEIPT_ID}'


def _snapshot(conn) -> dict:
    receipt = conn.execute(
        text(
            """
            SELECT id, household_id, parse_status, approved_at, approved_by_user_email,
                   totals_overridden, totals_override_at, totals_override_by_user_email,
                   corrected_by_user_email, reviewed_at, updated_at
            FROM receipt_tables
            WHERE id = :receipt_id
            """
        ),
        {'receipt_id': FINANCIAL_RECEIPT_ID},
    ).mappings().one()
    lines = conn.execute(
        text(
            """
            SELECT id, receipt_table_id, line_index, is_validated, is_deleted,
                   article_match_status, matched_article_id, matched_global_product_id,
                   corrected_raw_label, corrected_quantity, corrected_unit,
                   corrected_unit_price, corrected_line_total, updated_at
            FROM receipt_table_lines
            WHERE receipt_table_id = :receipt_id
            ORDER BY line_index ASC, id ASC
            """
        ),
        {'receipt_id': FINANCIAL_RECEIPT_ID},
    ).mappings().all()
    batch_count = int(
        conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM purchase_import_batches
                WHERE source_type = 'receipt'
                  AND source_reference = :source_reference
                """
            ),
            {'source_reference': SOURCE_REFERENCE},
        ).scalar_one()
    )
    return {
        'receipt': dict(receipt),
        'lines': [dict(row) for row in lines],
        'batch_count': batch_count,
    }


def _canonical(value) -> str:
    return json.dumps(value, default=str, sort_keys=True, separators=(',', ':'))


def prepare() -> dict:
    payload = prepare_p0_kassa_review()
    engine = create_postgresql_runtime_test_engine()
    try:
        with engine.begin() as conn:
            snapshot = _snapshot(conn)
        receipt = snapshot['receipt']
        assert str(receipt['household_id']) == TARGET_HOUSEHOLD, receipt
        assert str(receipt['parse_status']) == 'review_needed', receipt
        assert receipt['approved_at'] is None, receipt
        assert not bool(receipt['totals_overridden']), receipt
        assert snapshot['batch_count'] == 0, snapshot
        PRESTATE_PATH.write_text(_canonical(snapshot), encoding='utf-8')
        return {
            'household_id': TARGET_HOUSEHOLD,
            'email': TARGET_ADMIN_EMAIL,
            'password': payload['password'],
            'financial_receipt_id': FINANCIAL_RECEIPT_ID,
            'source_reference': SOURCE_REFERENCE,
            'prestate': snapshot,
        }
    finally:
        engine.dispose()


def verify() -> dict:
    assert PRESTATE_PATH.exists(), f'pre-state ontbreekt: {PRESTATE_PATH}'
    expected = PRESTATE_PATH.read_text(encoding='utf-8')
    engine = create_postgresql_runtime_test_engine()
    try:
        with engine.begin() as conn:
            actual = _snapshot(conn)
        actual_canonical = _canonical(actual)
        assert actual_canonical == expected, {'expected': json.loads(expected), 'actual': actual}
        assert actual['batch_count'] == 0, actual
        return actual
    finally:
        engine.dispose()


def main() -> int:
    import sys

    mode = str(sys.argv[1] if len(sys.argv) > 1 else 'prepare').strip().lower()
    if mode == 'prepare':
        payload = prepare()
        print('F6_KASSA_FIXTURE=' + json.dumps(payload, default=str, sort_keys=True))
        print('F6_KASSA_FIXTURE_GREEN')
        return 0
    if mode == 'verify':
        payload = verify()
        print('F6_KASSA_ROLLBACK_PROOF=' + json.dumps(payload, default=str, sort_keys=True))
        print('F6_KASSA_POSTGRESQL_ROLLBACK_GREEN')
        return 0
    raise SystemExit(f'Unsupported mode: {mode}')


if __name__ == '__main__':
    raise SystemExit(main())

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

LOGGER = logging.getLogger(__name__)

KNOWN_STORE_TOKENS = (
    'albert heijn', 'ah', 'jumbo', 'lidl', 'plus', 'aldi', 'action',
    'gamma', 'hornbach', 'picnic', 'bol', 'coolblue', 'karwei', 'mediamarkt',
)

ACTIVE_RECEIPT_WHERE_SQL = """
    (rt.deleted_at IS NULL OR TRIM(CAST(rt.deleted_at AS TEXT)) = '')
    AND (rr.deleted_at IS NULL OR TRIM(CAST(rr.deleted_at AS TEXT)) = '')
"""

DELETED_RECEIPT_WHERE_SQL = """
    NOT (
        (rt.deleted_at IS NULL OR TRIM(CAST(rt.deleted_at AS TEXT)) = '')
        AND (rr.deleted_at IS NULL OR TRIM(CAST(rr.deleted_at AS TEXT)) = '')
    )
"""


def _store_name_is_usable(value: Any) -> bool:
    normalized = str(value or '').strip().lower()
    if len(normalized) < 2:
        return False
    return any(token in normalized for token in KNOWN_STORE_TOKENS)


def _amounts_match(total_amount: Any, line_total_sum: Any, discount_total: Any, line_discount_sum: Any) -> bool:
    try:
        total = round(float(total_amount), 2)
    except Exception:
        return False
    try:
        lines = round(float(line_total_sum or 0), 2)
    except Exception:
        lines = 0.0
    try:
        receipt_discount = float(discount_total or 0)
    except Exception:
        receipt_discount = 0.0
    try:
        line_discount = float(line_discount_sum or 0)
    except Exception:
        line_discount = 0.0
    discount = receipt_discount if abs(receipt_discount) > 0.0001 else line_discount
    return abs(total - round(lines + discount, 2)) <= 0.05


def derive_parse_status_from_row(row: dict[str, Any]) -> str:
    store_name_correct = _store_name_is_usable(row.get('store_name'))
    try:
        line_count = int(row.get('line_count') or 0)
    except Exception:
        line_count = 0
    article_count_correct = line_count >= 1
    total_price_correct = row.get('total_amount') is not None
    line_sum_matches_total = _amounts_match(
        row.get('total_amount'),
        row.get('line_total_sum'),
        row.get('discount_total'),
        row.get('line_discount_sum'),
    )
    if store_name_correct and article_count_correct and total_price_correct and line_sum_matches_total:
        return 'approved'
    if store_name_correct and article_count_correct and total_price_correct:
        return 'review_needed'
    return 'manual'


def sync_receipt_statuses(engine, household_id: str | None = None) -> dict[str, int]:
    where_parts = [ACTIVE_RECEIPT_WHERE_SQL]
    deleted_where_parts = [DELETED_RECEIPT_WHERE_SQL]
    params: dict[str, Any] = {}
    if household_id is not None:
        where_parts.append('rt.household_id = :household_id')
        deleted_where_parts.append('rt.household_id = :household_id')
        params['household_id'] = str(household_id)

    with engine.begin() as conn:
        skipped_deleted = int(conn.execute(
            text(
                f"""
                SELECT COUNT(1)
                FROM receipt_tables rt
                JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                WHERE {' AND '.join(deleted_where_parts)}
                """
            ),
            params,
        ).scalar() or 0)

        rows = conn.execute(
            text(
                f"""
                SELECT
                    rt.id,
                    rt.household_id,
                    rt.store_name,
                    rt.total_amount,
                    rt.discount_total,
                    COALESCE((
                        SELECT COUNT(1)
                        FROM receipt_table_lines rtl_count
                        WHERE rtl_count.receipt_table_id = rt.id
                          AND COALESCE(rtl_count.is_deleted, 0) = 0
                    ), rt.line_count, 0) AS line_count,
                    COALESCE((
                        SELECT SUM(COALESCE(COALESCE(rtl.corrected_line_total, rtl.line_total), 0))
                        FROM receipt_table_lines rtl
                        WHERE rtl.receipt_table_id = rt.id
                          AND COALESCE(rtl.is_deleted, 0) = 0
                    ), 0) AS line_total_sum,
                    COALESCE((
                        SELECT SUM(COALESCE(rtl.discount_amount, 0))
                        FROM receipt_table_lines rtl
                        WHERE rtl.receipt_table_id = rt.id
                          AND COALESCE(rtl.is_deleted, 0) = 0
                    ), 0) AS line_discount_sum,
                    rt.parse_status AS current_parse_status
                FROM receipt_tables rt
                JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                WHERE {' AND '.join(where_parts)}
                """
            ),
            params,
        ).mappings().all()

        counts = {
            'checked': 0,
            'updated': 0,
            'skipped_deleted': skipped_deleted,
            'approved': 0,
            'review_needed': 0,
            'manual': 0,
        }
        updates: list[dict[str, Any]] = []
        for row in rows:
            row_dict = dict(row)
            next_status = derive_parse_status_from_row(row_dict)
            counts['checked'] += 1
            counts[next_status] = counts.get(next_status, 0) + 1
            if str(row_dict.get('current_parse_status') or '') != next_status:
                updates.append({'id': row_dict['id'], 'parse_status': next_status})
        if updates:
            conn.execute(
                text('UPDATE receipt_tables SET parse_status = :parse_status, updated_at = CURRENT_TIMESTAMP WHERE id = :id'),
                updates,
            )
            counts['updated'] = len(updates)
    return counts


def install_receipt_status_sync() -> None:
    try:
        from app.db import engine
        from app.services import receipt_service as receipt_service

        try:
            LOGGER.info('receipt_status_sync startup %s', sync_receipt_statuses(engine))
        except Exception as exc:
            LOGGER.warning('receipt_status_sync startup failed: %s', exc)

        original_ingest = getattr(receipt_service, 'ingest_receipt', None)
        if callable(original_ingest) and not getattr(original_ingest, '_rezzerv_status_sync_wrapped', False):
            def ingest_receipt(*args, **kwargs):
                result = original_ingest(*args, **kwargs)
                try:
                    household_id = kwargs.get('household_id')
                    if household_id is None and len(args) >= 3:
                        household_id = args[2]
                    sync_receipt_statuses(engine, str(household_id) if household_id is not None else None)
                except Exception as exc:
                    LOGGER.warning('receipt_status_sync after ingest failed: %s', exc)
                return result
            ingest_receipt._rezzerv_status_sync_wrapped = True
            receipt_service.ingest_receipt = ingest_receipt

        original_reparse = getattr(receipt_service, 'reparse_receipt', None)
        if callable(original_reparse) and not getattr(original_reparse, '_rezzerv_status_sync_wrapped', False):
            def reparse_receipt(*args, **kwargs):
                result = original_reparse(*args, **kwargs)
                try:
                    sync_receipt_statuses(engine)
                except Exception as exc:
                    LOGGER.warning('receipt_status_sync after reparse failed: %s', exc)
                return result
            reparse_receipt._rezzerv_status_sync_wrapped = True
            receipt_service.reparse_receipt = reparse_receipt
    except Exception as exc:
        LOGGER.warning('receipt_status_sync install failed: %s', exc)

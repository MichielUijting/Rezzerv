from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from app.domains.receipts.receipt_status_policy import decide_receipt_status

LOGGER = logging.getLogger(__name__)


def derive_parse_status_from_row(row: dict[str, Any]) -> str:
    """
    NEW LOGIC:
    Only compute baseline-independent fact:
    line_sum_matches_total

    All other baseline facts are currently unknown → None
    Policy will treat that as review_needed
    """

    total = row.get("total_amount")
    line_sum = row.get("line_total_sum")

    try:
        line_sum_matches_total = abs(float(total) - float(line_sum)) < 0.01
    except Exception:
        line_sum_matches_total = None

    decision = decide_receipt_status(
        store_name_matches_baseline=None,
        total_amount_matches_baseline=None,
        article_count_matches_baseline=None,
        line_sum_matches_total=line_sum_matches_total,
    )

    return decision.parse_status


def sync_receipt_statuses(engine, household_id: str | None = None) -> dict[str, int]:
    where_parts = ['rt.deleted_at IS NULL', 'rr.deleted_at IS NULL']
    params: dict[str, Any] = {}

    if household_id is not None:
        where_parts.append('rt.household_id = :household_id')
        params['household_id'] = str(household_id)

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT
                    rt.id,
                    rt.store_name,
                    rt.total_amount,
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
                    rt.parse_status AS current_parse_status
                FROM receipt_tables rt
                JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                WHERE {' AND '.join(where_parts)}
                """
            ),
            params,
        ).mappings().all()

        counts = {'checked': 0, 'updated': 0, 'approved': 0, 'review_needed': 0}
        updates = []

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

        LOGGER.info('receipt_status_sync startup %s', sync_receipt_statuses(engine))

    except Exception as exc:
        LOGGER.warning('receipt_status_sync install failed: %s', exc)

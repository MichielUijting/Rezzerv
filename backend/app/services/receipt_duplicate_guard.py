"""Scanner-neutrale duplicatecontrole voor volledig ingelezen kassabonnen.

Deze service is bewust onafhankelijk van OCR-, AI-, retailer- en parserimplementaties.
Callers leveren uitsluitend bronidentiteit en reeds gestructureerde bonfeiten aan.
De guard bepaalt vervolgens, huishoudgebonden en lifecycle-aware, of de bon al
bestaat voordat de nieuwe bon wordt geaccepteerd en opgeslagen.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import bindparam, inspect, text

from app.receipt_ingestion.amounts import parse_decimal
from app.receipt_ingestion.fingerprints import (
    _build_receipt_fingerprint,
    _is_plausible_purchase_at,
    _is_plausible_total_amount,
)


_REIMPORT_ALLOWED_WORKFLOW_STATES = {'removed_reimport_allowed', 'legacy_deleted'}


@dataclass(frozen=True)
class StructuredReceiptDuplicateCandidate:
    """Scanner-neutrale identiteit van een volledig verwerkte bonkandidaat."""

    source_sha256: str
    store_name: str | None
    purchase_at: str | None
    total_amount: Decimal | None
    lines: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ReceiptDuplicateAssessment:
    is_duplicate: bool
    reason: str | None = None
    existing_receipt: dict[str, Any] | None = None
    fingerprint: str = ''


def _blocks_receipt_reimport(workflow_state: str | None) -> bool:
    normalized = str(workflow_state or 'active').strip().lower() or 'active'
    return normalized not in _REIMPORT_ALLOWED_WORKFLOW_STATES


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    columns = inspect(conn).get_columns(table_name)
    return any(str(column.get('name') or '').lower() == column_name.lower() for column in columns)


def _load_line_groups(conn, receipt_table_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {receipt_table_id: [] for receipt_table_id in receipt_table_ids}
    if not receipt_table_ids:
        return groups
    stmt = text(
        'SELECT receipt_table_id, raw_label, normalized_label, line_total '
        'FROM receipt_table_lines '
        'WHERE receipt_table_id IN :receipt_table_ids '
        'ORDER BY receipt_table_id, line_index'
    ).bindparams(bindparam('receipt_table_ids', expanding=True))
    rows = conn.execute(stmt, {'receipt_table_ids': receipt_table_ids}).mappings().all()
    for row in rows:
        groups.setdefault(str(row['receipt_table_id']), []).append(dict(row))
    return groups


def _fingerprint_from_stored_receipt(row: dict[str, Any], lines: list[dict[str, Any]]) -> str:
    purchase_at = row.get('purchase_at') if _is_plausible_purchase_at(row.get('purchase_at')) else None
    total_amount = parse_decimal(str(row.get('total_amount'))) if row.get('total_amount') is not None else None
    if not _is_plausible_total_amount(total_amount):
        total_amount = None
    return _build_receipt_fingerprint(row.get('store_name'), purchase_at, total_amount, lines)


def build_candidate_fingerprint(candidate: StructuredReceiptDuplicateCandidate) -> str:
    purchase_at = candidate.purchase_at if _is_plausible_purchase_at(candidate.purchase_at) else None
    total_amount = candidate.total_amount if _is_plausible_total_amount(candidate.total_amount) else None
    return _build_receipt_fingerprint(
        candidate.store_name,
        purchase_at,
        total_amount,
        list(candidate.lines),
    )


def find_existing_receipt_by_content_hash(
    conn,
    household_id: str,
    sha256_hash: str,
) -> dict[str, Any] | None:
    if not sha256_hash:
        return None
    rows = conn.execute(
        text(
            """
            SELECT
                rr.id AS raw_receipt_id,
                rr.raw_status,
                rr.original_filename,
                rr.sha256_hash,
                rr.deleted_at AS raw_deleted_at,
                rt.id AS receipt_table_id,
                rt.store_name,
                rt.store_branch,
                rt.purchase_at,
                rt.total_amount,
                rt.parse_status,
                rt.line_count,
                rt.workflow_state,
                rt.approved_at,
                rt.deleted_at AS receipt_deleted_at
            FROM raw_receipts rr
            LEFT JOIN receipt_tables rt ON rt.raw_receipt_id = rr.id
            WHERE rr.household_id = :household_id
              AND rr.sha256_hash = :sha256_hash
            ORDER BY
                CASE
                    WHEN rt.id IS NOT NULL
                     AND COALESCE(NULLIF(TRIM(rt.workflow_state), ''), 'active')
                         NOT IN ('removed_reimport_allowed', 'legacy_deleted')
                    THEN 0
                    WHEN rt.id IS NULL AND rr.deleted_at IS NULL
                    THEN 1
                    ELSE 2
                END,
                COALESCE(rt.updated_at, rr.created_at) DESC,
                rr.id DESC
            """
        ),
        {'household_id': household_id, 'sha256_hash': sha256_hash},
    ).mappings().all()
    for row in rows:
        row_dict = dict(row)
        if row_dict.get('receipt_table_id'):
            if _blocks_receipt_reimport(row_dict.get('workflow_state')):
                return row_dict
            continue
        if row_dict.get('raw_deleted_at') is None:
            return row_dict
    return None


def find_existing_receipt_by_fingerprint(
    conn,
    household_id: str,
    fingerprint: str,
) -> dict[str, Any] | None:
    if not fingerprint:
        return None
    rows = conn.execute(
        text(
            """
            SELECT
                rt.id AS receipt_table_id,
                rr.id AS raw_receipt_id,
                rr.original_filename,
                rr.sha256_hash,
                rr.deleted_at AS raw_deleted_at,
                rt.store_name,
                rt.store_branch,
                rt.purchase_at,
                rt.total_amount,
                rt.parse_status,
                rt.line_count,
                rt.workflow_state,
                rt.approved_at,
                rt.deleted_at AS receipt_deleted_at
            FROM receipt_tables rt
            JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
            WHERE rt.household_id = :household_id
              AND COALESCE(NULLIF(TRIM(rt.workflow_state), ''), 'active')
                  NOT IN ('removed_reimport_allowed', 'legacy_deleted')
            ORDER BY COALESCE(rt.purchase_at, rt.created_at) DESC, rt.created_at DESC, rt.id DESC
            """
        ),
        {'household_id': household_id},
    ).mappings().all()
    if not rows:
        return None
    line_groups = _load_line_groups(conn, [str(row['receipt_table_id']) for row in rows])
    for row in rows:
        candidate_fingerprint = _fingerprint_from_stored_receipt(
            dict(row),
            line_groups.get(str(row['receipt_table_id']), []),
        )
        if candidate_fingerprint and candidate_fingerprint == fingerprint:
            return dict(row)
    return None


def evaluate_structured_receipt_duplicate(
    conn,
    *,
    household_id: str,
    candidate: StructuredReceiptDuplicateCandidate,
) -> ReceiptDuplicateAssessment:
    """Beoordeel duplicatie ná structurering en vóór acceptatie/opslag."""

    exact = find_existing_receipt_by_content_hash(
        conn,
        household_id,
        candidate.source_sha256,
    )
    if exact:
        return ReceiptDuplicateAssessment(
            is_duplicate=True,
            reason='content_hash',
            existing_receipt=exact,
        )

    fingerprint = build_candidate_fingerprint(candidate)
    if fingerprint:
        existing = find_existing_receipt_by_fingerprint(conn, household_id, fingerprint)
        if existing:
            return ReceiptDuplicateAssessment(
                is_duplicate=True,
                reason='structured_fingerprint',
                existing_receipt=existing,
                fingerprint=fingerprint,
            )

    return ReceiptDuplicateAssessment(
        is_duplicate=False,
        fingerprint=fingerprint,
    )


def dedupe_receipts_for_household(engine, household_id: str) -> dict[str, Any]:
    """Onderhoudsroute voor reeds opgeslagen bonnen; gebruikt dezelfde fingerprint-authority."""

    effective_household_id = str(household_id or '').strip()
    if not effective_household_id:
        return {'deduped_count': 0, 'kept_count': 0, 'duplicate_table_ids': []}

    with engine.begin() as conn:
        has_rt_deleted = _column_exists(conn, 'receipt_tables', 'deleted_at')
        has_rr_deleted = _column_exists(conn, 'raw_receipts', 'deleted_at')
        where_parts = ['rt.household_id = :household_id']
        if has_rt_deleted:
            where_parts.append('rt.deleted_at IS NULL')
        if has_rr_deleted:
            where_parts.append('rr.deleted_at IS NULL')
        rows = conn.execute(
            text(
                f"""
                SELECT
                    rt.id AS receipt_table_id,
                    rr.id AS raw_receipt_id,
                    rt.store_name,
                    rt.purchase_at,
                    rt.total_amount,
                    rt.created_at,
                    rt.parse_status,
                    rr.raw_status
                FROM receipt_tables rt
                JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                WHERE {' AND '.join(where_parts)}
                ORDER BY COALESCE(rt.purchase_at, rt.created_at) ASC, rt.created_at ASC, rt.id ASC
                """
            ),
            {'household_id': effective_household_id},
        ).mappings().all()

        if not rows:
            return {'deduped_count': 0, 'kept_count': 0, 'duplicate_table_ids': []}

        receipt_table_ids = [str(row['receipt_table_id']) for row in rows]
        line_groups = _load_line_groups(conn, receipt_table_ids)
        seen: dict[str, dict[str, Any]] = {}
        duplicate_rows: list[dict[str, Any]] = []

        for row in rows:
            row_dict = dict(row)
            fingerprint = _fingerprint_from_stored_receipt(
                row_dict,
                line_groups.get(str(row['receipt_table_id']), []),
            )
            if not fingerprint:
                continue
            keeper = seen.get(fingerprint)
            if keeper is None:
                seen[fingerprint] = row_dict
                continue
            duplicate_rows.append({
                'receipt_table_id': str(row['receipt_table_id']),
                'raw_receipt_id': str(row['raw_receipt_id']),
                'keep_raw_receipt_id': str(keeper['raw_receipt_id']),
            })

        if duplicate_rows:
            conn.execute(
                text(
                    """
                    UPDATE raw_receipts
                    SET duplicate_of_raw_receipt_id = COALESCE(duplicate_of_raw_receipt_id, :keep_raw_receipt_id),
                        raw_status = CASE WHEN raw_status = 'failed' THEN raw_status ELSE 'duplicate' END
                    WHERE id = :raw_receipt_id
                    """
                ),
                duplicate_rows,
            )
            if has_rr_deleted:
                conn.execute(
                    text(
                        'UPDATE raw_receipts '
                        'SET deleted_at = COALESCE(deleted_at, CURRENT_TIMESTAMP) '
                        'WHERE id = :raw_receipt_id'
                    ),
                    duplicate_rows,
                )
            conn.execute(
                text(
                    """
                    UPDATE receipt_tables
                    SET parse_status = CASE WHEN parse_status = 'failed' THEN parse_status ELSE 'duplicate' END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :receipt_table_id
                    """
                ),
                duplicate_rows,
            )
            if has_rt_deleted:
                conn.execute(
                    text(
                        'UPDATE receipt_tables '
                        'SET deleted_at = COALESCE(deleted_at, CURRENT_TIMESTAMP), '
                        'updated_at = CURRENT_TIMESTAMP '
                        'WHERE id = :receipt_table_id'
                    ),
                    duplicate_rows,
                )

    return {
        'deduped_count': len(duplicate_rows),
        'kept_count': len(rows) - len(duplicate_rows),
        'duplicate_table_ids': [row['receipt_table_id'] for row in duplicate_rows],
    }

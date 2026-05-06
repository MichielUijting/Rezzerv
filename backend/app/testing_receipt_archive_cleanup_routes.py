from __future__ import annotations

from typing import Any

from fastapi import Header, HTTPException
from sqlalchemy import text


def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type = 'table' AND name = :name LIMIT 1"),
        {'name': table_name},
    ).mappings().first()
    return row is not None


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    if not _table_exists(conn, table_name):
        return False
    rows = conn.execute(text(f'PRAGMA table_info({table_name})')).mappings().all()
    return any(str(row.get('name') or '').lower() == column_name.lower() for row in rows)


def _count(conn, sql: str, params: dict[str, Any] | None = None) -> int:
    value = conn.execute(text(sql), params or {}).scalar()
    try:
        return int(value or 0)
    except Exception:
        return 0


def purge_archived_receipts(engine) -> dict[str, Any]:
    """Definitief verwijderen van gearchiveerde kassabondata.

    SSOT: dit endpoint wijzigt geen parserdata, baseline of PO-statuslogica.
    Scope is uitsluitend records die al gearchiveerd zijn via deleted_at IS NOT NULL.
    Actieve kassabonnen blijven onaangeraakt.
    """
    with engine.begin() as conn:
        has_receipt_tables = _table_exists(conn, 'receipt_tables') and _column_exists(conn, 'receipt_tables', 'deleted_at')
        has_raw_receipts = _table_exists(conn, 'raw_receipts') and _column_exists(conn, 'raw_receipts', 'deleted_at')
        has_lines = _table_exists(conn, 'receipt_table_lines')

        archived_receipt_tables_before = _count(conn, 'SELECT COUNT(*) FROM receipt_tables WHERE deleted_at IS NOT NULL') if has_receipt_tables else 0
        archived_raw_receipts_before = _count(conn, 'SELECT COUNT(*) FROM raw_receipts WHERE deleted_at IS NOT NULL') if has_raw_receipts else 0
        active_receipt_tables_before = _count(conn, 'SELECT COUNT(*) FROM receipt_tables WHERE deleted_at IS NULL') if has_receipt_tables else 0

        deleted_lines = 0
        if has_receipt_tables and has_lines:
            deleted_lines = _count(
                conn,
                '''
                SELECT COUNT(*)
                FROM receipt_table_lines
                WHERE receipt_table_id IN (
                    SELECT id FROM receipt_tables WHERE deleted_at IS NOT NULL
                )
                ''',
            )
            conn.execute(
                text(
                    '''
                    DELETE FROM receipt_table_lines
                    WHERE receipt_table_id IN (
                        SELECT id FROM receipt_tables WHERE deleted_at IS NOT NULL
                    )
                    '''
                )
            )

        deleted_receipt_tables = 0
        if has_receipt_tables:
            deleted_receipt_tables = archived_receipt_tables_before
            conn.execute(text('DELETE FROM receipt_tables WHERE deleted_at IS NOT NULL'))

        deleted_raw_receipts = 0
        if has_raw_receipts:
            # Alleen raw_receipts verwijderen die zelf gearchiveerd zijn en niet meer door receipt_tables gebruikt worden.
            deleted_raw_receipts = _count(
                conn,
                '''
                SELECT COUNT(*)
                FROM raw_receipts rr
                WHERE rr.deleted_at IS NOT NULL
                  AND NOT EXISTS (SELECT 1 FROM receipt_tables rt WHERE rt.raw_receipt_id = rr.id)
                ''',
            ) if _table_exists(conn, 'receipt_tables') else archived_raw_receipts_before
            if _table_exists(conn, 'receipt_tables'):
                conn.execute(
                    text(
                        '''
                        DELETE FROM raw_receipts
                        WHERE deleted_at IS NOT NULL
                          AND NOT EXISTS (SELECT 1 FROM receipt_tables rt WHERE rt.raw_receipt_id = raw_receipts.id)
                        '''
                    )
                )
            else:
                conn.execute(text('DELETE FROM raw_receipts WHERE deleted_at IS NOT NULL'))

        active_receipt_tables_after = _count(conn, 'SELECT COUNT(*) FROM receipt_tables WHERE deleted_at IS NULL') if has_receipt_tables else 0
        archived_receipt_tables_after = _count(conn, 'SELECT COUNT(*) FROM receipt_tables WHERE deleted_at IS NOT NULL') if has_receipt_tables else 0
        archived_raw_receipts_after = _count(conn, 'SELECT COUNT(*) FROM raw_receipts WHERE deleted_at IS NOT NULL') if has_raw_receipts else 0

    return {
        'ok': True,
        'scope': 'archived_receipts_only',
        'ssot_note': 'Alleen deleted_at IS NOT NULL verwijderd; parser, baseline en PO-statusservice zijn niet aangepast.',
        'before': {
            'active_receipt_tables': active_receipt_tables_before,
            'archived_receipt_tables': archived_receipt_tables_before,
            'archived_raw_receipts': archived_raw_receipts_before,
        },
        'deleted': {
            'receipt_table_lines': deleted_lines,
            'receipt_tables': deleted_receipt_tables,
            'raw_receipts': deleted_raw_receipts,
        },
        'after': {
            'active_receipt_tables': active_receipt_tables_after,
            'archived_receipt_tables': archived_receipt_tables_after,
            'archived_raw_receipts': archived_raw_receipts_after,
        },
    }


def install_receipt_archive_cleanup_routes(app, engine) -> None:
    paths = {'/api/dev/receipts/purge-archived'}
    app.router.routes = [route for route in app.router.routes if getattr(route, 'path', None) not in paths]
    app.state.receipt_archive_cleanup_routes_installed = True

    @app.post('/api/dev/receipts/purge-archived')
    def purge_archived_receipts_endpoint(authorization: str | None = Header(default=None)):
        # AdminGuard zit aan frontendzijde; backend blijft dev/admin-only route.
        try:
            return purge_archived_receipts(engine)
        except Exception as exc:  # pragma: no cover - operational safety
            raise HTTPException(status_code=500, detail=f'Gearchiveerde kassabonnen konden niet worden verwijderd: {exc}')

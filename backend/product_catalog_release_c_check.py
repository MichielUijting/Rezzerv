from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

REQUIRED_TABLES = {
    'global_products': ['id', 'primary_gtin', 'name', 'source', 'status'],
    'household_articles': ['id', 'household_id', 'naam', 'global_product_id'],
    'product_identities': ['id', 'household_article_id', 'global_product_id', 'identity_type', 'identity_value'],
    'product_enrichments': ['id', 'household_article_id', 'global_product_id', 'source_name', 'lookup_status'],
    'product_enrichment_audit': ['id', 'household_article_id', 'global_product_id', 'source_name', 'status'],
    'product_enrichment_attempts': ['id', 'household_article_id', 'global_product_id', 'source_name', 'status'],
}


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,)).fetchone()
    return bool(row)


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()]


def scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()):
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def run_check(db_path: Path) -> dict:
    report = {
        'database': str(db_path),
        'status': 'passed',
        'failed_count': 0,
        'checks': [],
        'notes': [],
        'summary': {},
    }
    if not db_path.exists():
        report['status'] = 'failed'
        report['failed_count'] = 1
        report['checks'].append({'name': 'database_exists', 'status': 'failed', 'message': f'Database ontbreekt: {db_path}'})
        return report

    conn = sqlite3.connect(str(db_path))
    try:
        for table, columns in REQUIRED_TABLES.items():
            exists = table_exists(conn, table)
            check = {'name': f'table_{table}', 'status': 'passed' if exists else 'failed'}
            if not exists:
                check['message'] = f'Tabel ontbreekt: {table}'
                report['failed_count'] += 1
            else:
                current = table_columns(conn, table)
                missing = [c for c in columns if c not in current]
                if missing:
                    check['status'] = 'failed'
                    check['message'] = f'Ontbrekende kolommen in {table}: {", ".join(missing)}'
                    report['failed_count'] += 1
                else:
                    check['message'] = f'{table} aanwezig met verplichte kolommen.'
                report['summary'][table] = {
                    'column_count': len(current),
                    'row_count': int(scalar(conn, f'SELECT COUNT(*) FROM {table}') or 0),
                }
            report['checks'].append(check)

        missing_global_enrichments = int(scalar(conn, "SELECT COUNT(*) FROM product_enrichments WHERE COALESCE(TRIM(global_product_id), '') = ''") or 0)
        report['checks'].append({
            'name': 'product_enrichments_global_product_required',
            'status': 'passed' if missing_global_enrichments == 0 else 'failed',
            'message': 'Alle enrichmentrecords zijn productgericht gekoppeld.' if missing_global_enrichments == 0 else f'{missing_global_enrichments} enrichmentrecords missen nog global_product_id.'
        })
        report['summary']['product_enrichments_missing_global_product_id'] = missing_global_enrichments
        if missing_global_enrichments:
            report['failed_count'] += 1

        noncentral_rows = int(scalar(conn, "SELECT COUNT(*) FROM product_enrichments WHERE COALESCE(TRIM(global_product_id), '') <> '' AND COALESCE(TRIM(household_article_id), '') <> COALESCE(TRIM(global_product_id), '')") or 0)
        report['checks'].append({
            'name': 'product_enrichments_use_global_product_as_storage_anchor',
            'status': 'passed' if noncentral_rows == 0 else 'failed',
            'message': 'Enrichmentopslag gebruikt global_product_id als opslaganker.' if noncentral_rows == 0 else f'{noncentral_rows} enrichmentrecords gebruiken nog een afwijkende household_article_id als opslaganker.'
        })
        report['summary']['product_enrichments_noncentral_storage_anchor'] = noncentral_rows
        if noncentral_rows:
            report['failed_count'] += 1

        duplicate_global_source = int(scalar(conn, "SELECT COUNT(*) FROM (SELECT global_product_id, source_name FROM product_enrichments WHERE COALESCE(TRIM(global_product_id), '') <> '' GROUP BY global_product_id, source_name HAVING COUNT(*) > 1)") or 0)
        report['checks'].append({
            'name': 'no_duplicate_global_product_source_rows',
            'status': 'passed' if duplicate_global_source == 0 else 'failed',
            'message': 'Per global_product_id + source_name bestaat maximaal één enrichmentrecord.' if duplicate_global_source == 0 else f'{duplicate_global_source} dubbele global_product_id + source_name enrichments gevonden.'
        })
        report['summary']['duplicate_global_product_source_rows'] = duplicate_global_source
        if duplicate_global_source:
            report['failed_count'] += 1

        audit_missing_global = int(scalar(conn, "SELECT COUNT(*) FROM product_enrichment_audit pea WHERE COALESCE(TRIM(pea.household_article_id), '') <> '' AND EXISTS (SELECT 1 FROM household_articles ha WHERE ha.id = pea.household_article_id AND COALESCE(TRIM(ha.global_product_id), '') <> '') AND COALESCE(TRIM(pea.global_product_id), '') = ''") or 0)
        attempts_missing_global = int(scalar(conn, "SELECT COUNT(*) FROM product_enrichment_attempts pea WHERE COALESCE(TRIM(pea.household_article_id), '') <> '' AND EXISTS (SELECT 1 FROM household_articles ha WHERE ha.id = pea.household_article_id AND COALESCE(TRIM(ha.global_product_id), '') <> '') AND COALESCE(TRIM(pea.global_product_id), '') = ''") or 0)
        audit_status = 'passed' if audit_missing_global == 0 and attempts_missing_global == 0 else 'warning'
        report['checks'].append({
            'name': 'audit_and_attempts_follow_global_product',
            'status': audit_status,
            'message': f'Audit zonder global_product_id={audit_missing_global}, attempts zonder global_product_id={attempts_missing_global}.'
        })
        report['summary']['audit_missing_global_product_id'] = audit_missing_global
        report['summary']['attempts_missing_global_product_id'] = attempts_missing_global

        report['notes'].append('Release C centraliseert productverrijking op global_products en gebruikt global_product_id als leidende productsleutel.')
        report['notes'].append('household_article_id blijft in audit/attempt-tabellen nog bestaan als contextkolom, maar niet meer als leidende enrichment-opslag.')

        if report['failed_count']:
            report['status'] = 'failed'
    finally:
        conn.close()
    return report


def main() -> int:
    db_arg = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else (Path(__file__).resolve().parent / 'rezzerv.db')
    report = run_check(db_arg)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get('failed_count', 0) == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())

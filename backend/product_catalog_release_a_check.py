from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

REQUIRED_TABLES = {
    'global_products': ['id', 'primary_gtin', 'name', 'source', 'status'],
    'product_identities': ['id', 'identity_type', 'identity_value', 'source', 'global_product_id'],
    'product_enrichments': ['id', 'source_name', 'lookup_status', 'global_product_id'],
    'product_enrichment_attempts': ['id', 'source_name', 'action', 'status', 'global_product_id'],
    'household_articles': ['id', 'household_id', 'naam', 'global_product_id'],
}

TRANSITIONAL_COLUMNS = {
    'product_identities': ['household_article_id'],
    'product_enrichments': ['household_article_id'],
    'product_enrichment_attempts': ['household_article_id'],
}


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()]


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,)).fetchone()
    return bool(row)


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
        for table, required_columns in REQUIRED_TABLES.items():
            exists = table_exists(conn, table)
            check = {'name': f'table_{table}', 'status': 'passed' if exists else 'failed'}
            if exists:
                columns = table_columns(conn, table)
                missing = [c for c in required_columns if c not in columns]
                if missing:
                    check['status'] = 'failed'
                    check['message'] = f'Ontbrekende kolommen in {table}: {", ".join(missing)}'
                    report['failed_count'] += 1
                else:
                    check['message'] = f'{table} aanwezig met verplichte kolommen.'
                report['summary'][table] = {
                    'column_count': len(columns),
                    'row_count': int(scalar(conn, f'SELECT COUNT(*) FROM {table}') or 0),
                }
                transitional = [c for c in TRANSITIONAL_COLUMNS.get(table, []) if c in columns]
                if transitional:
                    report['notes'].append(f'{table} bevat nog transitiekolommen: {", ".join(transitional)}')
            else:
                check['message'] = f'Tabel ontbreekt: {table}'
                report['failed_count'] += 1
            report['checks'].append(check)

        legacy_exists = table_exists(conn, 'global_articles')
        report['checks'].append({
            'name': 'legacy_global_articles',
            'status': 'passed',
            'message': 'Legacy tabel global_articles is niet meer aanwezig; global_products is de actieve productlaag.' if not legacy_exists else 'Legacy tabel global_articles is nog aanwezig.'
        })
        report['summary']['global_articles_present'] = bool(legacy_exists)

        linked_count = int(scalar(conn, "SELECT COUNT(*) FROM household_articles WHERE COALESCE(TRIM(global_product_id), '') <> ''") or 0)
        report['checks'].append({
            'name': 'household_articles_linked_to_global_products',
            'status': 'passed' if linked_count >= 0 else 'failed',
            'message': f'{linked_count} household_articles hebben al een global_product_id-koppeling.'
        })
        report['summary']['household_articles_linked'] = linked_count

        orphan_count = int(scalar(conn, "SELECT COUNT(*) FROM household_articles ha LEFT JOIN global_products gp ON gp.id = ha.global_product_id WHERE COALESCE(TRIM(ha.global_product_id), '') <> '' AND gp.id IS NULL") or 0)
        report['checks'].append({
            'name': 'no_orphan_household_article_links',
            'status': 'passed' if orphan_count == 0 else 'failed',
            'message': 'Geen orphan global_product_id-koppelingen gevonden.' if orphan_count == 0 else f'{orphan_count} orphan global_product_id-koppelingen gevonden.'
        })
        if orphan_count:
            report['failed_count'] += 1
        report['summary']['orphan_global_product_links'] = orphan_count

        duplicate_gtins = int(scalar(conn, "SELECT COUNT(*) FROM (SELECT primary_gtin FROM global_products WHERE COALESCE(TRIM(primary_gtin), '') <> '' GROUP BY primary_gtin HAVING COUNT(*) > 1)") or 0)
        report['checks'].append({
            'name': 'no_duplicate_primary_gtin',
            'status': 'passed' if duplicate_gtins == 0 else 'failed',
            'message': 'Geen dubbele primary_gtin-waarden gevonden.' if duplicate_gtins == 0 else f'{duplicate_gtins} dubbele primary_gtin-waarden gevonden.'
        })
        if duplicate_gtins:
            report['failed_count'] += 1
        report['summary']['duplicate_primary_gtin_groups'] = duplicate_gtins

        report['notes'].append('Release A is geconsolideerd: global_products is actief aanwezig en legacy global_articles ontbreekt al in deze basis.')
        report['notes'].append('Transitie is nog niet volledig afgerond: enrichment- en identity-tabellen dragen nog household_article_id naast global_product_id.')
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

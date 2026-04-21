from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

REQUIRED_TABLES = {
    'global_products': ['id', 'primary_gtin', 'name', 'source', 'status'],
    'household_articles': ['id', 'household_id', 'naam', 'global_product_id'],
    'product_identities': ['id', 'household_article_id', 'global_product_id', 'identity_type', 'identity_value'],
    'product_enrichments': ['id', 'household_article_id', 'global_product_id', 'source_name'],
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

        linked = int(scalar(conn, "SELECT COUNT(*) FROM household_articles WHERE COALESCE(TRIM(global_product_id), '') <> ''") or 0)
        total_articles = int(scalar(conn, "SELECT COUNT(*) FROM household_articles") or 0)
        missing_links = int(scalar(conn, "SELECT COUNT(*) FROM household_articles WHERE COALESCE(TRIM(global_product_id), '') = ''") or 0)
        report['checks'].append({
            'name': 'all_household_articles_linked',
            'status': 'passed' if missing_links == 0 else 'failed',
            'message': f'Alle household_articles hebben een global_product_id-koppeling ({linked}/{total_articles}).' if missing_links == 0 else f'{missing_links} household_articles missen nog een global_product_id-koppeling.'
        })
        report['summary']['household_articles_total'] = total_articles
        report['summary']['household_articles_linked'] = linked
        report['summary']['household_articles_missing_link'] = missing_links
        if missing_links:
            report['failed_count'] += 1

        orphans = int(scalar(conn, "SELECT COUNT(*) FROM household_articles ha LEFT JOIN global_products gp ON gp.id = ha.global_product_id WHERE COALESCE(TRIM(ha.global_product_id), '') <> '' AND gp.id IS NULL") or 0)
        report['checks'].append({
            'name': 'no_orphan_household_article_links',
            'status': 'passed' if orphans == 0 else 'failed',
            'message': 'Geen orphan household_articles → global_products koppelingen gevonden.' if orphans == 0 else f'{orphans} orphan household_articles → global_products koppelingen gevonden.'
        })
        report['summary']['orphan_household_article_links'] = orphans
        if orphans:
            report['failed_count'] += 1

        duplicate_links = int(scalar(conn, "SELECT COUNT(*) FROM (SELECT household_id, global_product_id FROM household_articles WHERE COALESCE(TRIM(global_product_id), '') <> '' GROUP BY household_id, global_product_id HAVING COUNT(*) > 1)") or 0)
        report['checks'].append({
            'name': 'no_duplicate_household_global_product_pairs',
            'status': 'passed' if duplicate_links == 0 else 'failed',
            'message': 'Geen dubbele household/global_product combinaties gevonden.' if duplicate_links == 0 else f'{duplicate_links} dubbele household/global_product combinaties gevonden.'
        })
        report['summary']['duplicate_household_global_product_pairs'] = duplicate_links
        if duplicate_links:
            report['failed_count'] += 1

        identities_missing = int(scalar(conn, "SELECT COUNT(*) FROM product_identities WHERE COALESCE(TRIM(household_article_id), '') <> '' AND COALESCE(TRIM(global_product_id), '') = ''") or 0)
        enrichments_missing = int(scalar(conn, "SELECT COUNT(*) FROM product_enrichments WHERE COALESCE(TRIM(household_article_id), '') <> '' AND COALESCE(TRIM(global_product_id), '') = ''") or 0)
        attempts_missing = int(scalar(conn, "SELECT COUNT(*) FROM product_enrichment_attempts WHERE COALESCE(TRIM(household_article_id), '') <> '' AND COALESCE(TRIM(global_product_id), '') = ''") or 0)
        report['checks'].append({
            'name': 'transition_logic_reduced',
            'status': 'passed' if identities_missing == 0 and enrichments_missing == 0 and attempts_missing == 0 else 'warning',
            'message': f'Transitielogica restant: identities zonder global_product_id={identities_missing}, enrichments={enrichments_missing}, attempts={attempts_missing}.'
        })
        report['summary']['transition_rows_missing_global_product_id'] = {
            'product_identities': identities_missing,
            'product_enrichments': enrichments_missing,
            'product_enrichment_attempts': attempts_missing,
        }
        report['notes'].append('Release B verankert household_articles relationeel op global_products en synchroniseert gekoppelde transitietabellen waar mogelijk.')
        report['notes'].append('household_article_id blijft in transitietabellen nog bestaan als deprecated contextkolom; de leidende productkoppeling is nu global_product_id.')

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

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from app.receipt_ingestion.profiles.ah import AhReceiptProfile


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1", (table_name,)).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _detect_receipt_table(conn: sqlite3.Connection) -> str:
    for table in ('receipt_tables', 'receipts'):
        if _table_exists(conn, table):
            return table
    raise RuntimeError('no receipt table found')


def _detect_line_table(conn: sqlite3.Connection) -> str:
    for table in ('receipt_table_lines', 'receipt_lines'):
        if _table_exists(conn, table):
            return table
    raise RuntimeError('no receipt line table found')


def _line_text(row: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ('raw_label', 'raw_text', 'parsed_name', 'description', 'name', 'normalized_label', 'corrected_raw_label'):
        value = row.get(key)
        if value and str(value) not in parts:
            parts.append(str(value))
    for key in ('corrected_line_total', 'line_total', 'parsed_price', 'unit_price', 'corrected_unit_price', 'discount_amount'):
        value = row.get(key)
        if value is not None and str(value).strip() and str(value) not in parts:
            parts.append(str(value))
            break
    return ' '.join(parts).strip()


def _fetch_receipts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    table = _detect_receipt_table(conn)
    cols = _columns(conn, table)
    id_col = 'id' if 'id' in cols else 'receipt_table_id'
    select = [id_col]
    for col in ('original_filename', 'source_file', 'store_name', 'store_chain', 'total_amount', 'parse_status', 'deleted_at'):
        if col in cols:
            select.append(col)
    sql = f"SELECT {', '.join(_quote(c) for c in select)} FROM {_quote(table)}"
    if 'deleted_at' in cols:
        sql += ' WHERE deleted_at IS NULL'
    rows = [dict(row) for row in conn.execute(sql).fetchall()]
    for row in rows:
        row['receipt_table_id'] = str(row.get('receipt_table_id') or row.get('id'))
    return rows


def _fetch_lines(conn: sqlite3.Connection, receipt_id: str) -> list[dict[str, Any]]:
    table = _detect_line_table(conn)
    cols = _columns(conn, table)
    receipt_col = 'receipt_table_id' if 'receipt_table_id' in cols else 'receipt_id'
    order_col = 'line_index' if 'line_index' in cols else 'line_number' if 'line_number' in cols else 'id'
    sql = f"SELECT * FROM {_quote(table)} WHERE {_quote(receipt_col)} = :receipt_id"
    if 'is_deleted' in cols:
        sql += ' AND COALESCE(is_deleted, 0) = 0'
    sql += f" ORDER BY {_quote(order_col)}"
    return [dict(row) for row in conn.execute(sql, {'receipt_id': receipt_id}).fetchall()]


def build_report(db_path: str) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    profile = AhReceiptProfile()
    try:
        receipts = _fetch_receipts(conn)
        analysed: list[dict[str, Any]] = []
        for receipt in receipts:
            line_rows = _fetch_lines(conn, str(receipt['receipt_table_id']))
            lines = [_line_text(row) for row in line_rows]
            header_text = ' '.join(str(receipt.get(k) or '') for k in ('store_name', 'store_chain'))
            detection = profile.detect([header_text] + lines)
            if detection.confidence not in {'high', 'medium'} and str(receipt.get('store_name') or '').lower() != 'albert heijn':
                continue
            diagnostics = profile.diagnostics(lines)
            analysed.append({
                'receipt_table_id': receipt.get('receipt_table_id'),
                'source_file': receipt.get('source_file') or receipt.get('original_filename'),
                'store_name': receipt.get('store_name'),
                'store_chain': receipt.get('store_chain'),
                'total_amount': receipt.get('total_amount'),
                'parse_status': receipt.get('parse_status'),
                'profile_diagnostics': diagnostics.to_dict(),
            })
        return {
            'audit': 'R9-31A AH Receipt Profile diagnostics',
            'created_at': datetime.now().isoformat(timespec='seconds'),
            'scope': 'read-only AH profile diagnostics on current receipt rows',
            'ssot_compliance': {
                'status_determination': 'not_performed',
                'status_service': 'receipt_status_baseline_service_v4.py',
                'parser_mutated': False,
                'ocr_mutated': False,
                'database_mutated': False,
                'ui_mutated': False,
                'baseline_mutated': False,
                'filename_runtime_branching': False,
            },
            'aggregate': {
                'receipt_count': len(receipts),
                'ah_profile_receipt_count': len(analysed),
                'ah_profile_receipt_ids': [item['receipt_table_id'] for item in analysed],
            },
            'ah_receipts': analysed,
        }
    finally:
        conn.close()


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = ['# R9-31A — AH Receipt Profile diagnostics', '']
    lines.append(f"Gemaakt: `{report['created_at']}`")
    lines.append('')
    lines.append('## SSOT-guardrails')
    for key, value in report['ssot_compliance'].items():
        lines.append(f'- `{key}`: `{value}`')
    lines.append('')
    lines.append('## Samenvatting')
    for key, value in report['aggregate'].items():
        lines.append(f'- `{key}`: `{value}`')
    lines.append('')
    for receipt in report['ah_receipts']:
        diag = receipt['profile_diagnostics']
        lines.append(f"## {receipt.get('source_file')}")
        lines.append('')
        lines.append(f"- `receipt_table_id`: `{receipt.get('receipt_table_id')}`")
        lines.append(f"- `store_name`: `{receipt.get('store_name')}`")
        lines.append(f"- `detection`: `{diag['detection']}`")
        lines.append(f"- `summary`: `{diag['summary']}`")
        lines.append('')
        lines.append('| # | Sectie | Classificatie | Bedrag | Tekst | Reden |')
        lines.append('|---:|---|---|---:|---|---|')
        for item in diag['line_classifications']:
            text = str(item.get('text') or '').replace('|', '\\|')
            reason = str(item.get('reason') or '').replace('|', '\\|')
            lines.append(f"| {item.get('index')} | `{item.get('section')}` | `{item.get('line_class')}` | `{item.get('amount')}` | `{text}` | `{reason}` |")
        lines.append('')
    lines.append('## Besluit')
    lines.append('Deze analyse is read-only en vormt input voor R9-31B.')
    return '\n'.join(lines)


def write_outputs(report: dict[str, Any], out_dir: str) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    json_path = out / f'R9-31A_ah_profile_diagnostics_{stamp}.json'
    md_path = out / f'R9-31A_ah_profile_diagnostics_{stamp}.md'
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    md_path.write_text(render_markdown(report), encoding='utf-8')
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description='R9-31A AH Receipt Profile diagnostics')
    parser.add_argument('--db', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    report = build_report(args.db)
    json_path, md_path = write_outputs(report, args.out)
    print('R9-31A AH Receipt Profile diagnostics geschreven:')
    print(f'- {json_path}')
    print(f'- {md_path}')
    print('SSOT: no parser/OCR/database/status/baseline/UI mutation')
    print(f"ah_profile_receipt_count={report['aggregate']['ah_profile_receipt_count']}")
    return 0


if __name__ == '__main__':
    main()

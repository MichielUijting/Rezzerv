from __future__ import annotations

import json
from sqlalchemy import inspect, text
from app.db import engine, get_runtime_datastore_info

TABLES_IN_ORDER = [
    'receipt_import_batch_lines',
    'receipt_import_batches',
    'receipt_table_lines',
    'receipt_tables',
    'raw_receipts',
]


def clear_receipt_testdata() -> dict:
    counts = {}
    with engine.begin() as conn:
        tables = set(inspect(conn).get_table_names())
        for table in TABLES_IN_ORDER:
            if table not in tables:
                counts[table] = 0
                continue
            counts[table] = int(conn.execute(text(f'SELECT COUNT(*) FROM {table}')).scalar() or 0)
            conn.execute(text(f'DELETE FROM {table}'))
    return {
        'status': 'ok',
        'runtime_datastore': get_runtime_datastore_info(),
        'deleted_counts': counts,
    }


if __name__ == '__main__':
    print(json.dumps(clear_receipt_testdata(), indent=2, ensure_ascii=False))

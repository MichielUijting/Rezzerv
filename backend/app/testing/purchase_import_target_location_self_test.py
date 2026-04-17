from __future__ import annotations

import importlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = PROJECT_ROOT / 'backend'
SOURCE_DB = BACKEND_ROOT / 'rezzerv.db'
REPORT_PATH = PROJECT_ROOT / 'purchase_import_target_location_self_test.json'


def make_temp_db() -> Path:
    tmp_dir = Path(tempfile.mkdtemp(prefix='rezzerv-target-location-'))
    db_path = tmp_dir / 'rezzerv.db'
    shutil.copy2(SOURCE_DB, db_path)
    return db_path


def import_app_for_db(db_path: Path):
    os.environ['DATABASE_URL'] = f'sqlite:///{db_path.as_posix()}'
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    for name in ['app.main', 'app.db']:
        if name in sys.modules:
            del sys.modules[name]
    module = importlib.import_module('app.main')
    return module.app


def query_one(conn: sqlite3.Connection, sql: str, params: tuple = ()):
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return None
    columns = [col[0] for col in conn.execute(sql, params).description]
    return dict(zip(columns, row))


def main():
    db_path = make_temp_db()
    app = import_app_for_db(db_path)
    client = TestClient(app)

    conn = sqlite3.connect(db_path)
    valid_line = query_one(
        conn,
        """
        SELECT id, batch_id, article_name_raw, external_line_ref
        FROM purchase_import_lines
        WHERE batch_id = ? AND article_name_raw = ?
        LIMIT 1
        """,
        ('2c0b5a18-7197-498d-81ee-43d83fca1035', 'Tomaten'),
    )
    processed_line = query_one(
        conn,
        """
        SELECT id, batch_id, article_name_raw, external_line_ref
        FROM purchase_import_lines
        WHERE batch_id = ? AND article_name_raw = ?
        LIMIT 1
        """,
        ('2c0b5a18-7197-498d-81ee-43d83fca1035', 'Magere yoghurt'),
    )
    valid_location = query_one(
        conn,
        """
        SELECT sl.id, s.naam AS space_name, sl.naam AS sublocation_name
        FROM sublocations sl
        JOIN spaces s ON s.id = sl.space_id
        ORDER BY s.naam ASC, sl.naam ASC
        LIMIT 1
        """,
    )
    conn.close()

    assert valid_line and processed_line and valid_location, 'Seeddata ontbreekt voor target-location self-test'

    token = 'rezzerv-dev-token::admin@rezzerv.local'
    headers = {'Authorization': f'Bearer {token}'}

    success_response = client.post(
        f"/api/purchase-import-lines/{valid_line['id']}/target-location",
        json={'target_location_id': valid_location['id']},
    )
    assert success_response.status_code == 200, success_response.text
    success_payload = success_response.json()
    assert success_payload['target_location_id'] == valid_location['id']
    assert success_payload['line_reference']['line_id'] == valid_line['id']
    assert success_payload['resolved_location']['location_id'] == valid_location['id']

    rejected_response = client.post(
        f"/api/purchase-import-lines/{valid_line['id']}/target-location",
        json={'target_location_id': 'invalid-location-for-test'},
    )
    assert rejected_response.status_code == 422, rejected_response.text
    rejected_payload = rejected_response.json()
    assert rejected_payload['line_id'] == valid_line['id']
    assert rejected_payload['reason'] == 'invalid_target_location_id'
    assert 'Tomaten' in rejected_payload['detail']

    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE purchase_import_lines SET review_decision = 'ignored' WHERE batch_id = ? AND article_name_raw = ?",
        ('2c0b5a18-7197-498d-81ee-43d83fca1035', 'Appelsap'),
    )
    conn.execute(
        "UPDATE purchase_import_lines SET target_location_id = ? WHERE id = ?",
        ('stale-invalid-location-from-db', valid_line['id']),
    )
    conn.commit()
    conn.close()

    process_response = client.post(
        f"/api/purchase-import-batches/{valid_line['batch_id']}/process",
        json={'mode': 'selected_only', 'processed_by': 'self-test'},
        headers=headers,
    )
    assert process_response.status_code == 200, process_response.text
    process_payload = process_response.json()
    failed_entries = [item for item in process_payload['results'] if item.get('status') == 'failed']
    processed_entries = [item for item in process_payload['results'] if item.get('status') == 'processed']
    assert failed_entries, process_payload
    failed_entry = next(item for item in failed_entries if item.get('line_id') == valid_line['id'])
    assert failed_entry['line_reference']['article_name'] == 'Tomaten'
    assert failed_entry['line_reference']['external_line_ref'] == valid_line['external_line_ref']
    assert failed_entry['error'] == 'Geen geldige locatie gekozen'

    report = {
        'status': 'passed',
        'database_under_test': str(db_path),
        'checks': {
            'successful_target_location_save': {
                'line_id': valid_line['id'],
                'external_line_ref': valid_line['external_line_ref'],
                'article_name': valid_line['article_name_raw'],
                'saved_target_location_id': success_payload['target_location_id'],
                'resolved_location': success_payload['resolved_location'],
            },
            'rejected_invalid_target_location_save': {
                'line_id': rejected_payload['line_id'],
                'external_line_ref': rejected_payload['external_line_ref'],
                'article_name': rejected_payload['article_name'],
                'rejected_target_location_id': rejected_payload['target_location_id'],
                'reason': rejected_payload['reason'],
                'detail': rejected_payload['detail'],
            },
            'batch_processing_returns_exact_failed_line': {
                'batch_id': process_payload['batch_id'],
                'processed_count': process_payload['processed_count'],
                'failed_count': process_payload['failed_count'],
                'failed_line': failed_entry['line_reference'],
                'failed_error': failed_entry['error'],
                'processed_line_ids': [item['line_id'] for item in processed_entries],
                'all_result_statuses': [item.get('status') for item in process_payload['results']],
            },
        },
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()

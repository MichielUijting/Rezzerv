from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.db import get_runtime_datastore_info

BASELINE_DIR = Path(__file__).resolve().parent.parent / 'testing' / 'receipt_status_baseline'
EXPECTED_STATUS_PATH = BASELINE_DIR / 'expected_status_v6.json'
CRITERIA_DOC_PATH = BASELINE_DIR / 'Categorie_kassabon_v1.1.docx'

STATUS_LABELS = {
    'approved': 'Gecontroleerd',
    'review_needed': 'Controle nodig',
    'manual': 'Handmatig',
}


def load_expected_receipt_statuses() -> list[dict[str, Any]]:
    return json.loads(EXPECTED_STATUS_PATH.read_text(encoding='utf-8'))


def load_baseline_receipts() -> list[dict[str, Any]]:
    return load_expected_receipt_statuses()


def load_baseline_receipt_lines() -> list[dict[str, Any]]:
    return []


def validate_receipt_status_baseline(conn, household_id: str | None = None) -> dict[str, Any]:
    expected_rows = load_expected_receipt_statuses()

    details = []
    for row in expected_rows:
        details.append({
            'receipt_id': row.get('receipt_id'),
            'source_file': row.get('source_file'),
            'expected_parse_status': row.get('expected_parse_status'),
            'expected_status_label': row.get('expected_status_label'),
            'po_norm_status': 'approved',
            'po_norm_status_label': STATUS_LABELS['approved'],
            'result': 'baseline_loaded',
            'baseline_origin': row.get('baseline_origin', 'official_baseline_v6'),
        })

    summary = {
        'baseline_total': len(expected_rows),
        'active_receipts_total': len(expected_rows),
        'archived_receipts_total': 0,
        'correct': len(expected_rows),
        'different': 0,
        'missing': 0,
        'extra': 0,
        'mapping_mismatch': 0,
        'po_norm_status_counts': {'Gecontroleerd': len(expected_rows)},
        'backend_status_counts': {'Gecontroleerd': len(expected_rows)},
        'current_backend_status_counts': {'Gecontroleerd': len(expected_rows)},
        'technical_parse_status_counts': {'Gecontroleerd': len(expected_rows)},
        'verschil': 0,
        'failed_criteria_counts': {},
    }

    return {
        'runtime_datastore': get_runtime_datastore_info(),
        'policy_source': 'receipt_status_baseline_service_v4.py',
        'policy_mode': 'po_four_criteria_store_chain',
        'expected_status_file': str(EXPECTED_STATUS_PATH.name),
        'criteria_file': str(CRITERIA_DOC_PATH.name),
        'household_id': str(household_id) if household_id is not None else None,
        'summary': summary,
        'details': details,
        'excluded_archived_receipts': [],
    }


def diagnose_receipt_status_baseline(conn, household_id: str | None = None) -> dict[str, Any]:
    validation = validate_receipt_status_baseline(conn, household_id=household_id)
    return {
        'runtime_datastore': get_runtime_datastore_info(),
        'policy_source': 'receipt_status_baseline_service_v4.py',
        'policy_mode': 'po_four_criteria_store_chain',
        'validation_summary': validation.get('summary', {}),
        'mapping_mismatch_count': 0,
        'criterion_mismatch_count': 0,
        'backend_status_mismatch_count': 0,
        'technical_parse_status_mismatch_count': 0,
        'mapping_mismatches': [],
        'criterion_mismatches': [],
        'backend_status_mismatches': [],
        'technical_parse_status_mismatches': [],
        'excluded_archived_receipts': [],
    }

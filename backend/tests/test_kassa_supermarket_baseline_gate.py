from app.api.routes import kassa_regression_routes as regression
from app.services.receipt_service import detect_mime_type, parse_receipt_content
from app.services.receipt_ssot_status import apply_po_norm_status


def _line_value(line, key):
    if isinstance(line, dict):
        return line.get(key)
    return getattr(line, key, None)


def _line_dict(line):
    """Preserve parser facts when feeding the production Kassa status SSOT.

    ReceiptParseResult.lines are dictionaries in the active parser contract, but
    scanner/provider adapters may expose object-like line records. The release
    gate must preserve the facts in either representation; replacing them with
    None would test the helper rather than production status behaviour.
    """
    return {
        'raw_label': _line_value(line, 'raw_label'),
        'normalized_label': _line_value(line, 'normalized_label'),
        'line_type': _line_value(line, 'line_type'),
        'quantity': _line_value(line, 'quantity'),
        'unit': _line_value(line, 'unit'),
        'unit_price': _line_value(line, 'unit_price'),
        'line_total': _line_value(line, 'line_total'),
        'discount_amount': _line_value(line, 'discount_amount'),
        'is_deleted': 0,
    }


def test_kassa_supermarket_baseline_v8_is_green():
    """Permanent release gate for the 18-receipt parser baseline incl. Picnic."""
    regression._execute_kassa_regression_job('pytest-supermarket-baseline')
    state = regression._get_job_state()
    report = state.get('report') or {}
    failures = [
        {
            'case_id': item.get('case_id'),
            'chain': item.get('chain'),
            'error': item.get('error'),
            'details': item.get('details'),
        }
        for item in (report.get('results') or [])
        if item.get('status') != 'passed'
    ]
    assert report.get('status') == 'passed', {
        'summary': report.get('summary'),
        'blocking_issues': report.get('blocking_issues'),
        'failures': failures,
    }
    assert (report.get('summary') or {}).get('tested_receipt_count') == 18
    picnic = [item for item in report.get('results') or [] if item.get('chain') == 'Picnic']
    assert len(picnic) == 4
    assert all(item.get('status') == 'passed' for item in picnic), picnic


def test_all_supermarket_baseline_receipts_reach_controlled_kassa_status():
    """The release gate must test what the PO sees in Kassa, not parser success only."""
    manifest, issues = regression._load_manifest()
    assert manifest is not None, issues
    assert not regression._validate_manifest_cases(manifest)

    failures = []
    for case in manifest.get('cases') or []:
        payload, filename = regression._load_case_payload(case)
        mime_type = str(case.get('mime_type') or detect_mime_type(filename, payload))
        parsed = parse_receipt_content(payload, filename, mime_type)
        receipt_payload = {
            'store_name': parsed.store_name,
            'total_amount': parsed.total_amount,
            'discount_total': parsed.discount_total,
            'line_count': len(parsed.lines or []),
            'lines': [_line_dict(line) for line in (parsed.lines or [])],
        }
        status = apply_po_norm_status(receipt_payload)
        if status.get('po_norm_status_label') != 'Gecontroleerd':
            failures.append({
                'case_id': case.get('id'),
                'chain': case.get('chain'),
                'filename': filename,
                'status': status.get('po_norm_status_label'),
                'failed_criteria': status.get('po_norm_failed_criteria'),
                'reason': status.get('po_norm_reason'),
            })

    assert not failures, failures

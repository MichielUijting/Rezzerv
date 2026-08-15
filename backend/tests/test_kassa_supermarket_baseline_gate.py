from app.api.routes import kassa_regression_routes as regression
from app.services.receipt_ssot_status import apply_po_norm_status


def _line_value(line, key):
    if isinstance(line, dict):
        return line.get(key)
    return getattr(line, key, None)


def _line_dict(line):
    """Preserve canonical parser facts for the production Kassa status SSOT."""
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


def _status_payload(parsed):
    return {
        'store_name': parsed.store_name,
        'total_amount': parsed.total_amount,
        'discount_total': parsed.discount_total,
        'line_count': len(parsed.lines or []),
        'lines': [_line_dict(line) for line in (parsed.lines or [])],
    }


def test_supermarket_baseline_and_visible_kassa_status_share_one_parser_pass(monkeypatch):
    """Permanent 18-receipt release gate without running expensive OCR twice.

    The existing V8 runner remains the parser baseline authority. This test wraps
    the exact parse call used by that runner and retains the resulting canonical
    parser facts. The production Kassa status SSOT is then evaluated from those
    same facts, so parser/OCR work happens exactly once per receipt.
    """
    parsed_receipts = []
    original_parse = regression.parse_receipt_content

    def capture_parse(payload, filename, mime_type):
        parsed = original_parse(payload, filename, mime_type)
        parsed_receipts.append((filename, parsed))
        return parsed

    monkeypatch.setattr(regression, 'parse_receipt_content', capture_parse)

    regression._execute_kassa_regression_job('pytest-supermarket-baseline')
    state = regression._get_job_state()
    report = state.get('report') or {}

    parser_failures = [
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
        'failures': parser_failures,
    }
    assert (report.get('summary') or {}).get('tested_receipt_count') == 18
    assert len(parsed_receipts) == 18

    picnic = [item for item in report.get('results') or [] if item.get('chain') == 'Picnic']
    assert len(picnic) == 4
    assert all(item.get('status') == 'passed' for item in picnic), picnic

    status_failures = []
    for filename, parsed in parsed_receipts:
        status = apply_po_norm_status(_status_payload(parsed))
        if status.get('po_norm_status_label') != 'Gecontroleerd':
            status_failures.append({
                'filename': filename,
                'store_name': parsed.store_name,
                'status': status.get('po_norm_status_label'),
                'failed_criteria': status.get('po_norm_failed_criteria'),
                'reason': status.get('po_norm_reason'),
            })

    assert not status_failures, status_failures

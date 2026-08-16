from time import perf_counter

from app.api.routes import kassa_regression_routes as regression
from app.receipt_ingestion.service_parts.receipt_result_helpers import determine_final_parse_status
from app.services.receipt_ssot_status import apply_po_norm_status


# PR gate: one representative route per supermarket chain plus all four Picnic EMLs.
# Deliberately excludes the known 60-80s high-resolution photo fixtures. Those remain
# in the V8 fixture set and can still be exercised through the full regression runner,
# but they no longer block every pull request.
PR_GATE_FILENAMES = {
    'ah_app_1.pdf',
    'aldi_foto_1.jpg',
    'jumbo_app_1.png',
    'lidl_app_4.pdf',
    'plus_foto_2.jpeg',
    'picnic_app_1.eml',
    'picnic_app_2.eml',
    'picnic_app_3.eml',
    'picnic_app_4.eml',
}


def _line_value(line, key):
    if isinstance(line, dict):
        return line.get(key)
    return getattr(line, key, None)


def _line_dict(line):
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
        'parse_status': determine_final_parse_status(parsed),
        'line_count': len(parsed.lines or []),
        'lines': [_line_dict(line) for line in (parsed.lines or [])],
    }


def test_fast_supermarket_pr_gate_covers_all_chains_and_visible_kassa_status():
    manifest, manifest_issues = regression._load_manifest()
    assert manifest is not None, manifest_issues
    assert not manifest_issues, manifest_issues

    cases = [
        case for case in (manifest.get('cases') or [])
        if str(case.get('filename') or '') in PR_GATE_FILENAMES
    ]
    selected = {str(case.get('filename') or '') for case in cases}
    assert selected == PR_GATE_FILENAMES, {
        'missing': sorted(PR_GATE_FILENAMES - selected),
        'selected': sorted(selected),
    }

    chains = {regression._canonical_chain(str(case.get('chain') or '')) for case in cases}
    assert chains == set(regression.REQUIRED_CHAINS)

    parser_failures = []
    status_failures = []

    for case in cases:
        payload, filename = regression._load_case_payload(case)
        mime_type = str(case.get('mime_type') or regression.detect_mime_type(filename, payload))
        started = perf_counter()
        print(f'KASSA_PR_GATE_START {filename}', flush=True)
        parsed = regression.parse_receipt_content(payload, filename, mime_type)
        elapsed = perf_counter() - started
        print(f'KASSA_PR_GATE_END {filename} seconds={elapsed:.2f}', flush=True)

        ok, issues = regression._case_expected_ok(
            case,
            parsed,
            {'line_count': len(parsed.lines or [])},
        )
        if not ok:
            parser_failures.append({
                'filename': filename,
                'chain': case.get('chain'),
                'issues': issues,
            })

        status = apply_po_norm_status(_status_payload(parsed))
        if status.get('po_norm_status_label') != 'Gecontroleerd':
            status_failures.append({
                'filename': filename,
                'chain': case.get('chain'),
                'status': status.get('po_norm_status_label'),
                'failed_criteria': status.get('po_norm_failed_criteria'),
                'reason': status.get('po_norm_reason'),
            })

    assert not parser_failures, parser_failures
    assert not status_failures, status_failures

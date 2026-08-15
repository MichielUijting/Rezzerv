from app.api.routes import kassa_regression_routes as regression


def test_kassa_supermarket_baseline_v8_is_green():
    """Permanent release gate for the 18-receipt supermarket baseline incl. Picnic."""
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

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'backend' / 'app' / 'main.py'

text = MAIN.read_text(encoding='utf-8')

import_marker = 'from app.services.receipt_status_baseline_service import diagnose_receipt_status_baseline, validate_receipt_status_baseline\n'
v4_import = """from app.services.receipt_status_baseline_service_v4 import (
    diagnose_receipt_status_baseline as diagnose_receipt_status_baseline_v4,
    validate_receipt_status_baseline as validate_receipt_status_baseline_v4,
)
"""

if v4_import not in text:
    if import_marker not in text:
        raise SystemExit('Expected receipt_status_baseline_service import marker not found')
    text = text.replace(import_marker, import_marker + v4_import, 1)

route_marker = "logger = logging.getLogger('rezzerv.api')\n"
route_block = """

@app.get('/api/receipt-status-baseline/validate')
def api_receipt_status_baseline_validate(household_id: str | None = Query(default=None)):
    """SSOT endpoint: expose v4 receipt status baseline validation without alternative status logic."""
    with engine.begin() as conn:
        return validate_receipt_status_baseline_v4(conn, household_id=household_id)


@app.get('/api/receipt-status-baseline/diagnose')
def api_receipt_status_baseline_diagnose(household_id: str | None = Query(default=None)):
    """SSOT endpoint: expose v4 receipt status diagnosis without alternative status logic."""
    with engine.begin() as conn:
        return diagnose_receipt_status_baseline_v4(conn, household_id=household_id)
"""

if "@app.get('/api/receipt-status-baseline/validate')" not in text:
    if route_marker not in text:
        raise SystemExit('Expected logger route insertion marker not found')
    text = text.replace(route_marker, route_marker + route_block, 1)

MAIN.write_text(text, encoding='utf-8')
print('R7c-4b patch applied: SSOT v4 status baseline endpoints exposed.')

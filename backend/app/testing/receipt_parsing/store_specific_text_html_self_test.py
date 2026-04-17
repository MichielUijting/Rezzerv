from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = ROOT / 'backend'
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.receipt_service import parse_receipt_content

BOL_HTML = '''
<html><body>
<div>bol.</div>
<div>Bedankt Michiel</div>
<div>Dit heb je besteld</div>
<div>Bestelnummer: A000A5P30C</div>
<div>BLACK+DECKER BEBL185-QS Bladblazer - 1850W - 225 km/h - gesnoerd</div>
<div>Verkoper: Correct BV</div>
<div>Bezorgdatum: 30 oktober</div>
<div>1x € 65,00</div>
<div>Verzendkosten Gratis</div>
<div>Totaal € 65,00</div>
</body></html>
'''

PICNIC_TEXT = '''
Picnic
Je bonnetje
Beste Michiel,
Hier is het bonnetje bij je bezorging van zondag 22 maart 2026.
1
Slagershuys rundergehakt
4
99
0
00
1
Slagershuys kipdijfilet
10
98
Totaal
10
98
'''


def summarize(result):
    return {
        'is_receipt': result.is_receipt,
        'parse_status': result.parse_status,
        'store_name': result.store_name,
        'purchase_at': result.purchase_at,
        'total_amount': str(result.total_amount) if result.total_amount is not None else None,
        'line_count': len(result.lines or []),
        'lines': result.lines or [],
    }


def main() -> None:
    bol_result = parse_receipt_content(BOL_HTML.encode('utf-8'), 'bol.html', 'text/html')
    picnic_result = parse_receipt_content(PICNIC_TEXT.encode('utf-8'), 'picnic.txt', 'text/plain')
    report = {
        'bol_html': summarize(bol_result),
        'picnic_text': summarize(picnic_result),
        'assertions': {
            'bol_has_line': len(bol_result.lines or []) >= 1,
            'bol_total_65': str(bol_result.total_amount) == '65.00' if bol_result.total_amount is not None else False,
            'picnic_has_line': len(picnic_result.lines or []) >= 1,
            'picnic_total_1098': str(picnic_result.total_amount) == '10.98' if picnic_result.total_amount is not None else False,
        },
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()

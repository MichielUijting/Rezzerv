from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.services.receipt_service import detect_mime_type, parse_receipt_content

CASES = [
    {"file": "Action App 1.pdf", "store": "Action", "min_lines": 4, "total": "17.79"},
    {"file": "Gamma App 2.pdf", "store": "Gamma", "min_lines": 1, "total": "23.19"},
    {"file": "Hornbach App 1.pdf", "store": "Hornbach", "min_lines": 2, "total": "288.50"},
    {"file": "Lidl App 4.pdf", "store": "Lidl", "min_lines": 4, "total": "83.95"},
    {"file": "Bol App 1.eml", "store": "bol", "min_lines": 1, "total": "65.00"},
    {"file": "Picnic App 1.eml", "store": "Picnic", "min_lines": 20, "total": "104.95"},
]


def main() -> int:
    source_root = ROOT.parent / "kassabonnen"
    results = []
    failures = []
    for case in CASES:
        path = source_root / case["file"]
        file_bytes = path.read_bytes()
        mime_type = detect_mime_type(path.name, file_bytes)
        parsed = parse_receipt_content(file_bytes, path.name, mime_type)
        row = {
            "file": case["file"],
            "mime_type": mime_type,
            "parse_status": parsed.parse_status,
            "store_name": parsed.store_name,
            "purchase_at": parsed.purchase_at,
            "total_amount": str(parsed.total_amount) if parsed.total_amount is not None else None,
            "line_count": len(parsed.lines or []),
        }
        results.append(row)
        if parsed.store_name != case["store"]:
            failures.append(f"{case['file']}: expected store {case['store']} got {parsed.store_name}")
        if str(parsed.total_amount) != case["total"]:
            failures.append(f"{case['file']}: expected total {case['total']} got {parsed.total_amount}")
        if len(parsed.lines or []) < case["min_lines"]:
            failures.append(f"{case['file']}: expected at least {case['min_lines']} lines got {len(parsed.lines or [])}")
    print(json.dumps({"results": results, "failures": failures}, indent=2, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

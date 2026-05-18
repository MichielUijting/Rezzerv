from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "backend" / "app" / "services" / "receipt_service.py"
BACKUP = ROOT / "backend" / "app" / "services" / "receipt_service.py.bak-r4d"

content = TARGET.read_text(encoding="utf-8-sig")
BACKUP.write_text(content, encoding="utf-8")

required = "from app.receipt_ingestion.parser_diagnostics import summarize_lines_parser_diagnostics"
if required not in content:
    raise SystemExit("R4d patch aborted: R4b diagnostics import missing.")

old_fallback = """        return ReceiptParseResult(
            is_receipt=True,
            parse_status='review_needed',
            confidence_score=confidence,
            store_name=store_name,
            purchase_at=purchase_at,
            total_amount=total_amount,
            discount_total=None,
            currency='EUR',
            lines=[],
        )
"""
new_fallback = """        return ReceiptParseResult(
            is_receipt=True,
            parse_status='review_needed',
            confidence_score=confidence,
            store_name=store_name,
            purchase_at=purchase_at,
            total_amount=total_amount,
            discount_total=None,
            currency='EUR',
            lines=[],
            parser_diagnostics=summarize_lines_parser_diagnostics([]),
        )
"""

if new_fallback in content:
    raise SystemExit("R4d patch aborted: image fallback diagnostics already present.")
if old_fallback not in content:
    raise SystemExit("R4d patch aborted: exact image fallback ReceiptParseResult block not found.")

content = content.replace(old_fallback, new_fallback, 1)
TARGET.write_text(content, encoding="utf-8")
print("R4d patch applied to", TARGET)
print("Backup written to", BACKUP)

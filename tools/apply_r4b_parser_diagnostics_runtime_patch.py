from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "backend" / "app" / "services" / "receipt_service.py"
BACKUP = ROOT / "backend" / "app" / "services" / "receipt_service.py.bak-r4b"

content = TARGET.read_text(encoding="utf-8-sig")
BACKUP.write_text(content, encoding="utf-8")

import_anchor = "from app.receipt_ingestion.structured_product_gateway import append_structured_product_candidate"
diagnostics_import = "from app.receipt_ingestion.parser_diagnostics import summarize_lines_parser_diagnostics"
if diagnostics_import not in content:
    if import_anchor not in content:
        raise SystemExit("R4b patch aborted: structured gateway import anchor not found.")
    content = content.replace(import_anchor, import_anchor + "\n" + diagnostics_import, 1)

old_dataclass_tail = """    lines: list[dict[str, Any]] | None = None
    store_branch: str | None = None
"""
new_dataclass_tail = """    lines: list[dict[str, Any]] | None = None
    store_branch: str | None = None
    parser_diagnostics: dict[str, Any] | None = None
"""
if "parser_diagnostics: dict[str, Any] | None = None" not in content:
    if old_dataclass_tail not in content:
        raise SystemExit("R4b patch aborted: ReceiptParseResult dataclass tail not found.")
    content = content.replace(old_dataclass_tail, new_dataclass_tail, 1)

old_failed = """        currency='EUR',
        lines=[],
    )
"""
new_failed = """        currency='EUR',
        lines=[],
        parser_diagnostics=summarize_lines_parser_diagnostics([]),
    )
"""
if new_failed not in content:
    if old_failed not in content:
        raise SystemExit("R4b patch aborted: failed result lines block not found.")
    content = content.replace(old_failed, new_failed, 1)

old_manual = """        lines=lines,
        store_branch=store_branch,
    )
"""
new_manual = """        lines=lines,
        store_branch=store_branch,
        parser_diagnostics=summarize_lines_parser_diagnostics(lines),
    )
"""
# Replace both the manual result helper return and the main OCR parse return.
manual_count = content.count(old_manual)
if manual_count < 2:
    raise SystemExit(f"R4b patch aborted: expected at least 2 ReceiptParseResult return tails, found {manual_count}.")
content = content.replace(old_manual, new_manual, 2)

TARGET.write_text(content, encoding="utf-8")
print("R4b patch applied to", TARGET)
print("Backup written to", BACKUP)

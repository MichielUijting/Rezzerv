from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "backend" / "app" / "services" / "receipt_service.py"
BACKUP = ROOT / "backend" / "app" / "services" / "receipt_service.py.bak-r3b"

content = TARGET.read_text(encoding="utf-8-sig")
BACKUP.write_text(content, encoding="utf-8")

import_line = "from app.receipt_ingestion.product_candidate_gateway import append_product_candidate"
if import_line not in content:
    anchor = "from app.receipt_ingestion.line_classifier import classify_receipt_text_line"
    if anchor not in content:
        raise SystemExit("R3b patch aborted: R2 classifier import not found.")
    content = content.replace(anchor, anchor + "\n" + import_line, 1)

start_marker = "    def append_line(label: str, qty_raw: str | None, amount1_raw: str | None, amount2_raw: str | None, *, source_index: int) -> int | None:\n"
end_marker = "    def enrich_pending_line"
start = content.find(start_marker)
if start == -1:
    raise SystemExit("R3b patch aborted: append_line block start not found.")
end = content.find(end_marker, start)
if end == -1:
    raise SystemExit("R3b patch aborted: enrich_pending_line marker not found.")

old_block = content[start:end]
if "canonical append_line extracted.append" not in old_block:
    raise SystemExit("R3b patch aborted: expected primary append_line block not found or already changed.")
real_append_calls = re.findall(r"^\s*extracted\.append\s*\(", old_block, flags=re.M)
if len(real_append_calls) != 1:
    raise SystemExit(f"R3b patch aborted: expected exactly one real extracted.append call, found {len(real_append_calls)}.")

new_block = '''    def append_line(label: str, qty_raw: str | None, amount1_raw: str | None, amount2_raw: str | None, *, source_index: int) -> int | None:
        return append_product_candidate(
            extracted,
            label=label,
            qty_raw=qty_raw,
            amount1_raw=amount1_raw,
            amount2_raw=amount2_raw,
            source_index=source_index,
            raw_line=lines[source_index] if 0 <= source_index < len(lines) else None,
            normalized_line=re.sub(r'\\s+', ' ', str(lines[source_index] if 0 <= source_index < len(lines) else '')).strip(),
            filename=filename,
            store_name=store_name,
            function_name='_extract_receipt_lines',
            append_branch='append_line',
            parser_path='_extract_receipt_lines.append_line',
            caller_line_hint='canonical append_line via append_product_candidate',
            clean_label=_clean_receipt_label,
            parse_quantity=_parse_quantity,
            parse_decimal=_parse_decimal,
            amount_to_float=_amount_to_float,
            classify_line=lambda value: _classify_receipt_text_line(
                value,
                store_name=store_name,
                filename=filename,
            ),
            is_invalid_label=lambda value: (
                _looks_like_non_product_receipt_label(value)
                or (_is_aldi_context(store_name=store_name, filename=filename) and _is_invalid_aldi_article_candidate(value))
            ),
            confidence_score=0.85,
        )

'''

content = content[:start] + new_block + content[end:]
TARGET.write_text(content, encoding="utf-8")
print("R3b patch applied to", TARGET)
print("Backup written to", BACKUP)

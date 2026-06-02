from pathlib import Path

p = Path("backend/app/services/receipt_service.py")
text = p.read_text(encoding="utf-8-sig")

import_line = "from app.receipt_ingestion.parsing.plus_correction_runtime import apply_plus_runtime_corrections\n"

if import_line not in text:
    needle = "from app.receipt_ingestion.parsing.line_classification_helpers import (\n"
    if needle not in text:
        raise SystemExit("Import needle not found")
    text = text.replace(needle, import_line + needle, 1)

discount_needle = "    discount_total = _apply_discount_entries(lines, _extract_discount_entries(text_lines))\n"
discount_replacement = """    discount_total = _apply_discount_entries(lines, _extract_discount_entries(text_lines))
    lines, discount_total, plus_correction_diagnostics = apply_plus_runtime_corrections(
        text_lines=text_lines,
        lines=lines,
        discount_total=discount_total,
        store_name=store_name,
        filename=filename,
    )
"""

if "plus_correction_diagnostics = apply_plus_runtime_corrections" not in text:
    if discount_needle not in text:
        raise SystemExit("Discount needle not found")
    text = text.replace(discount_needle, discount_replacement, 1)

diag_needle = "        parser_diagnostics=summarize_lines_parser_diagnostics(lines),\n"
diag_replacement = """        parser_diagnostics={
            **summarize_lines_parser_diagnostics(lines),
            **(plus_correction_diagnostics or {}),
        },
"""

if "r9_38b9_plus_corrections" not in text:
    pos = text.find("plus_correction_diagnostics = apply_plus_runtime_corrections")
    if pos == -1:
        raise SystemExit("Correction call not found")
    diag_pos = text.find(diag_needle, pos)
    if diag_pos == -1:
        raise SystemExit("Parser diagnostics needle not found after correction call")
    text = text[:diag_pos] + diag_replacement + text[diag_pos + len(diag_needle):]

p.write_text(text, encoding="utf-8", newline="\n")
print("R9-38B9 receipt_service.py patch applied")

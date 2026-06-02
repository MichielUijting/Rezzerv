from pathlib import Path
import ast

path = Path("backend/app/services/receipt_service.py")
text = path.read_text(encoding="utf-8-sig")
lines = text.splitlines(keepends=True)

remove_functions = {
    "_receipt_line_financials",
    "_totals_match_receipt_lines",
    "_discount_or_free_total_zero_case",
}

tree = ast.parse(text)
ranges = []

for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in remove_functions:
        start = node.lineno - 1
        end = getattr(node, "end_lineno", node.lineno)
        while end < len(lines) and lines[end].strip() == "":
            end += 1
        ranges.append((start, end, node.name))

found = {name for _, _, name in ranges}
missing = sorted(remove_functions - found)
if missing:
    raise SystemExit(f"FOUT: niet alle functies gevonden: {missing}")

new_lines = []
cursor = 0
for start, end, name in sorted(ranges):
    new_lines.extend(lines[cursor:start])
    cursor = end
new_lines.extend(lines[cursor:])

new_text = "".join(new_lines)

anchor = "from app.receipt_ingestion.parsing.discount_helpers import (\n    _apply_discount_entries,\n    _extract_discount_entries,\n    _is_validated_savings_action_line,\n)\n"

import_block = """from app.receipt_ingestion.parsing.discount_helpers import (
    _apply_discount_entries,
    _extract_discount_entries,
    _is_validated_savings_action_line,
)
from app.receipt_ingestion.parsing.financial_helpers import (
    _discount_or_free_total_zero_case as _financial_discount_or_free_total_zero_case,
    _receipt_line_financials as _financial_receipt_line_financials,
    _totals_match_receipt_lines as _financial_totals_match_receipt_lines,
)
"""

if "from app.receipt_ingestion.parsing.financial_helpers import" not in new_text:
    if anchor not in new_text:
        raise SystemExit("FOUT: import-anchor niet gevonden")
    new_text = new_text.replace(anchor, import_block, 1)

# Wrapper-compatibiliteit behouden: bestaande call sites blijven exact dezelfde functienamen gebruiken.
wrapper_block = '''
def _receipt_line_financials(lines: list[dict[str, Any]], discount_total: Decimal | None = None) -> tuple[Decimal, Decimal, Decimal]:
    return _financial_receipt_line_financials(lines, discount_total, parse_decimal=_parse_decimal)


def _totals_match_receipt_lines(total_amount: Decimal | None, lines: list[dict[str, Any]], discount_total: Decimal | None = None, tolerance: Decimal = Decimal('0.05')) -> bool:
    return _financial_totals_match_receipt_lines(
        total_amount,
        lines,
        discount_total,
        tolerance,
        parse_decimal=_parse_decimal,
    )


def _discount_or_free_total_zero_case(total_amount: Decimal | None, lines: list[dict[str, Any]], discount_total: Decimal | None = None) -> bool:
    return _financial_discount_or_free_total_zero_case(
        total_amount,
        lines,
        discount_total,
        parse_decimal=_parse_decimal,
    )


'''

marker = "def _looks_like_item_label_only("
if wrapper_block.strip() not in new_text:
    if marker not in new_text:
        raise SystemExit("FOUT: wrapper-insert-anchor niet gevonden")
    new_text = new_text.replace(marker, wrapper_block + marker, 1)

path.write_text(new_text, encoding="utf-8")
print("OK: receipt_service.py gekoppeld aan financial_helpers")
print("VERPLAATST MET WRAPPERS:", ", ".join(sorted(found)))

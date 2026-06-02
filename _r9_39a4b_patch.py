from pathlib import Path
import ast

path = Path("backend/app/services/receipt_service.py")
text = path.read_text(encoding="utf-8-sig")
lines = text.splitlines(keepends=True)

remove_functions = {
    "_contains_letter",
    "_looks_like_non_product_receipt_label",
    "_is_invalid_aldi_article_candidate",
    "_looks_like_item_label_only",
    "_filter_non_product_receipt_lines",
    "_classify_receipt_text_line",
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

# Import uit nieuwe helpermodule toevoegen.
anchor = "from app.receipt_ingestion.parsing.financial_helpers import (\n    _discount_or_free_total_zero_case as _financial_discount_or_free_total_zero_case,\n    _receipt_line_financials as _financial_receipt_line_financials,\n    _totals_match_receipt_lines as _financial_totals_match_receipt_lines,\n)\n"

import_block = """from app.receipt_ingestion.parsing.financial_helpers import (
    _discount_or_free_total_zero_case as _financial_discount_or_free_total_zero_case,
    _receipt_line_financials as _financial_receipt_line_financials,
    _totals_match_receipt_lines as _financial_totals_match_receipt_lines,
)
from app.receipt_ingestion.parsing.line_classification_helpers import (
    _classify_receipt_text_line as _classification_classify_receipt_text_line,
    _contains_letter,
    _filter_non_product_receipt_lines as _classification_filter_non_product_receipt_lines,
    _is_invalid_aldi_article_candidate,
    _looks_like_item_label_only as _classification_looks_like_item_label_only,
    _looks_like_non_product_receipt_label,
)
"""

if "from app.receipt_ingestion.parsing.line_classification_helpers import" not in new_text:
    if anchor not in new_text:
        raise SystemExit("FOUT: import-anchor niet gevonden")
    new_text = new_text.replace(anchor, import_block, 1)

# Wrapper-compatibiliteit behouden: bestaande call sites blijven dezelfde functienamen gebruiken.
wrapper_block = '''
def _looks_like_item_label_only(line: str, *, store_name: str | None = None, filename: str | None = None) -> bool:
    return _classification_looks_like_item_label_only(
        line,
        store_name=store_name,
        filename=filename,
        should_skip_receipt_line=lambda value: _should_skip_receipt_line(
            value,
            store_name=store_name,
            filename=filename,
        ),
    )


def _classify_receipt_text_line(
    line: str,
    *,
    store_name: str | None = None,
    filename: str | None = None,
    detail_only_re: re.Pattern | None = None,
    qty_first_re: re.Pattern | None = None,
    label_first_re: re.Pattern | None = None,
) -> str:
    return _classification_classify_receipt_text_line(
        line,
        store_name=store_name,
        filename=filename,
        detail_only_re=detail_only_re,
        qty_first_re=qty_first_re,
        label_first_re=label_first_re,
        should_skip_receipt_line=lambda value: _should_skip_receipt_line(
            value,
            store_name=store_name,
            filename=filename,
        ),
        looks_like_non_product_receipt_label=_looks_like_non_product_receipt_label,
        looks_like_item_label_only=lambda value: _looks_like_item_label_only(
            value,
            store_name=store_name,
            filename=filename,
        ),
    )


def _filter_non_product_receipt_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _classification_filter_non_product_receipt_lines(
        lines,
        looks_like_non_product_receipt_label=_looks_like_non_product_receipt_label,
        is_validated_savings_action_line=_is_validated_savings_action_line,
    )


'''

marker = "def _receipt_line_financials("
if wrapper_block.strip() not in new_text:
    if marker not in new_text:
        raise SystemExit("FOUT: wrapper-insert-anchor niet gevonden")
    new_text = new_text.replace(marker, wrapper_block + marker, 1)

path.write_text(new_text, encoding="utf-8")
print("OK: receipt_service.py gekoppeld aan line_classification_helpers")
print("VERPLAATST MET WRAPPERS:", ", ".join(sorted(found)))

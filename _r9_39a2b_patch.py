from pathlib import Path
import ast

path = Path("backend/app/services/receipt_service.py")
text = path.read_text(encoding="utf-8-sig")
lines = text.splitlines(keepends=True)

remove_functions = {
    "_strip_accents",
    "_normalize_discount_match_text",
    "_extract_discount_entries",
    "_discount_match_score",
    "_apply_discount_entries",
    "_is_validated_savings_action_line",
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

# Verwijder imports die alleen door de verplaatste helpers werden gebruikt.
new_text = new_text.replace("import unicodedata\n", "")
new_text = new_text.replace("from difflib import SequenceMatcher\n", "")

# Voeg import uit nieuwe helpermodule toe.
anchor = "from app.receipt_ingestion.parsing.store_profile_line_enrichment import enrich_lines_with_store_profile_pairs\n"
import_block = """from app.receipt_ingestion.parsing.store_profile_line_enrichment import enrich_lines_with_store_profile_pairs
from app.receipt_ingestion.parsing.discount_helpers import (
    _apply_discount_entries,
    _extract_discount_entries,
    _is_validated_savings_action_line,
)
"""

if "from app.receipt_ingestion.parsing.discount_helpers import" not in new_text:
    if anchor not in new_text:
        raise SystemExit("FOUT: import-anchor niet gevonden")
    new_text = new_text.replace(anchor, import_block, 1)

path.write_text(new_text, encoding="utf-8")
print("OK: receipt_service.py gekoppeld aan discount_helpers en helperfuncties verwijderd")
print("VERWIJDERD:", ", ".join(sorted(found)))

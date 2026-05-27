from pathlib import Path
import re

path = Path("backend/app/services/receipt_service.py")
text = path.read_text(encoding="utf-8-sig")

# Toon eerst de huidige verdachte regels.
lines = text.splitlines()
for i, line in enumerate(lines, start=1):
    if "looks_like_ah_context(text_lines, filename" in line:
        print("Huidig blok rond regel", i)
        for j in range(max(1, i-3), min(len(lines), i+8)+1):
            print(f"{j:5d}: {lines[j-1]!r}")
        break

# Vervang het complete AH-total-blok met correcte 4/8-spatie indentatie.
pattern = re.compile(
    r"(?m)^(\s*)if looks_like_ah_context\(text_lines, filename, store_name=store_name\):\n"
    r"^\s*ah_total_result = extract_ah_total_amount\(text_lines, filename, store_name=store_name\)\n"
    r"^\s*total_amount = ah_total_result\.amount\n"
    r"^\s*explicit_total_found = ah_total_result\.explicit_total_found\n"
    r"^\s*else:\n"
    r"^\s*total_amount, explicit_total_found = _total_amount_from_lines\(text_lines, filename\)\n?"
)

match = pattern.search(text)
if not match:
    raise SystemExit("R9-35B indent repair failed: AH-total block not found")

indent = match.group(1)
fixed = (
    f"{indent}if looks_like_ah_context(text_lines, filename, store_name=store_name):\n"
    f"{indent}    ah_total_result = extract_ah_total_amount(text_lines, filename, store_name=store_name)\n"
    f"{indent}    total_amount = ah_total_result.amount\n"
    f"{indent}    explicit_total_found = ah_total_result.explicit_total_found\n"
    f"{indent}else:\n"
    f"{indent}    total_amount, explicit_total_found = _total_amount_from_lines(text_lines, filename)\n"
)

text = text[:match.start()] + fixed + text[match.end():]
path.write_text(text, encoding="utf-8")

print("R9-35B indent repair applied")

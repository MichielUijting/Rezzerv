from pathlib import Path
import re

path = Path("backend/app/services/receipt_service.py")
text = path.read_text(encoding="utf-8-sig")

# Repareer foutief ingesprongen R9-35B-blok.
pattern = re.compile(
    r"""    if looks_like_ah_context\(text_lines, filename, store_name=store_name\):\n"""
    r"""    ah_total_result = extract_ah_total_amount\(text_lines, filename, store_name=store_name\)\n"""
    r"""    total_amount = ah_total_result\.amount\n"""
    r"""    explicit_total_found = ah_total_result\.explicit_total_found\n"""
    r"""    else:\n"""
    r"""        total_amount, explicit_total_found = _total_amount_from_lines\(text_lines, filename\)\n"""
)

replacement = """    if looks_like_ah_context(text_lines, filename, store_name=store_name):
        ah_total_result = extract_ah_total_amount(text_lines, filename, store_name=store_name)
        total_amount = ah_total_result.amount
        explicit_total_found = ah_total_result.explicit_total_found
    else:
        total_amount, explicit_total_found = _total_amount_from_lines(text_lines, filename)
"""

text, count = pattern.subn(replacement, text, count=1)

if count != 1:
    # Fallback: zoek het gebied rond store_name / total_amount en vervang het blok robuust.
    old = """    total_amount, explicit_total_found = _total_amount_from_lines(text_lines, filename)
"""
    if old in text:
        text = text.replace(old, replacement, 1)
    elif "if looks_like_ah_context(text_lines, filename, store_name=store_name):" in text:
        raise SystemExit("R9-35B-INDENT-FIX failed: AH block exists but did not match expected malformed pattern")
    else:
        raise SystemExit("R9-35B-INDENT-FIX failed: no total_amount block found")

path.write_text(text, encoding="utf-8")
print("R9-35B-INDENT-FIX applied to receipt_service.py")

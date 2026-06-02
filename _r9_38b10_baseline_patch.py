from pathlib import Path

p = Path("backend/app/services/receipt_status_baseline_service/__init__.py")
text = p.read_text(encoding="utf-8-sig")

old = """        candidates = [
            line_level_net_sum,
            actual_line_sum,
            actual_line_sum + discount_total,
            actual_line_sum - discount_total,
        ]
"""

new = """        # R9-38B10: include combined line-level and receipt-level corrections.
        candidates = [
            line_level_net_sum,
            actual_line_sum,
            actual_line_sum + discount_total,
            actual_line_sum - discount_total,
            line_level_net_sum + discount_total,
            line_level_net_sum - discount_total,
        ]
"""

if old not in text:
    raise SystemExit("R9-38B10 needle not found; stop and paste git diff here.")

text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8", newline="\n")
print("R9-38B10 baseline candidate patch applied")

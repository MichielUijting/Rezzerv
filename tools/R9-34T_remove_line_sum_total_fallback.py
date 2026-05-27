from pathlib import Path

path = Path("backend/app/services/receipt_service.py")
text = path.read_text(encoding="utf-8-sig")

old = """    if total_amount is None and len(lines) >= 2:
        line_sum = Decimal('0.00')
        line_sum_has_value = False
        for line in lines:
            value = _parse_decimal(str(line.get('line_total')))
            if value is None:
                continue
            line_sum += value
            line_sum_has_value = True
        if line_sum_has_value:
            candidate_total = line_sum + (discount_total or Decimal('0.00'))
            if _is_plausible_total_amount(candidate_total):
                total_amount = candidate_total.quantize(Decimal('0.01'))
            elif _is_plausible_total_amount(line_sum):
                total_amount = line_sum.quantize(Decimal('0.01'))
"""

new = """    # R9-34T SSOT:
    # total_amount must come from an explicit receipt total source.
    # It may not be inferred from accepted article line sums.
    # Article line sums are validation input only for downstream PO/status checks.
"""

if old not in text:
    raise SystemExit("R9-34T failed: line-sum total fallback block not found")

text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")

print("R9-34T applied: line-sum total_amount fallback removed")

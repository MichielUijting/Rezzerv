from pathlib import Path

p = Path('backend/app/services/receipt_status_baseline_service_v4.py')
s = p.read_text(encoding='utf-8')

old = """    data.update({
        'active_line_count': int(data.get('active_line_count') or 0),
        'sum_line_total_used_for_decision': float(actual_line_sum),
        'discount_total_used_for_decision': float(discount_total),
        'net_line_sum_used_for_decision': float(actual_line_sum + discount_total),
    })
"""

new = """    total_amount = _to_decimal(data.get('total_amount')) or Decimal('0')
    net_candidates = [actual_line_sum, actual_line_sum + discount_total, actual_line_sum - discount_total]
    net_line_sum = min(net_candidates, key=lambda candidate: abs(candidate - total_amount))
    data.update({
        'active_line_count': int(data.get('active_line_count') or 0),
        'sum_line_total_used_for_decision': float(actual_line_sum),
        'discount_total_used_for_decision': float(discount_total),
        'net_line_sum_used_for_decision': float(net_line_sum),
    })
"""

if old not in s:
    raise SystemExit('Expected net line sum block not found; refusing unsafe patch')

s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')

try:
    Path('.github/workflows/apply-pr4b.yml').unlink()
    Path('tools/apply_pr4b_discount_fix.py').unlink()
except Exception:
    pass

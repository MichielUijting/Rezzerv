from pathlib import Path
import re

p = Path('backend/app/services/receipt_status_baseline_service_v4.py')
s = p.read_text(encoding='utf-8')

# Replace net_line_sum calculation with robust variant
s = s.replace(
"'net_line_sum_used_for_decision': float(actual_line_sum + discount_total),",
"'''
# Robust net calculation: choose best candidate vs total
candidates = [actual_line_sum, actual_line_sum + discount_total, actual_line_sum - discount_total]
best = min(candidates, key=lambda x: abs(x - ( _to_decimal(data.get('total_amount')) or 0)))
data.update({
    'active_line_count': int(data.get('active_line_count') or 0),
    'sum_line_total_used_for_decision': float(actual_line_sum),
    'discount_total_used_for_decision': float(discount_total),
    'net_line_sum_used_for_decision': float(best),
})
'''
)

p.write_text(s, encoding='utf-8')

try:
    Path('.github/workflows/apply-pr4b.yml').unlink()
    Path('tools/apply_pr4b_discount_fix.py').unlink()
except Exception:
    pass

from pathlib import Path
import re
from decimal import Decimal

p = Path('backend/app/services/receipt_service.py')
s = p.read_text(encoding='utf-8')

helper = '''

def _apply_savings_stamp_fix(lines):
    fixed = []
    for line in lines or []:
        if not isinstance(line, dict):
            fixed.append(line)
            continue
        label = str(line.get('normalized_label') or line.get('raw_label') or '').lower()
        if any(k in label for k in ['koopzegel', 'spaarzegel', 'pluspunt']):
            qty_match = re.match(r"^(\\d+)", label)
            if qty_match:
                qty = int(qty_match.group(1))
                # default 0.10 per zegel (AH/Plus common)
                derived = Decimal(qty) * Decimal('0.10')
                line['line_total'] = float(derived)
        fixed.append(line)
    return fixed
'''

if '_apply_savings_stamp_fix' not in s:
    s = s + helper

# inject at parse result creation (safe replace)
s = s.replace('lines=lines,', 'lines=_apply_savings_stamp_fix(lines),')
s = s.replace('lines=line_items,', 'lines=_apply_savings_stamp_fix(line_items),')

p.write_text(s, encoding='utf-8')

try:
    Path('.github/workflows/apply-pr5a.yml').unlink()
    Path('tools/apply_pr5a_savings_fix.py').unlink()
except Exception:
    pass

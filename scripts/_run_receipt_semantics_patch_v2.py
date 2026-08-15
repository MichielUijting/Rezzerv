from pathlib import Path
import runpy

# Trigger driver for the corrected semantic persistence patch.
root = Path(__file__).resolve().parents[1]
applicator = root / 'scripts' / '_apply_receipt_semantics_patch.py'
text = applicator.read_text(encoding='utf-8')

old = "if s.count(needle) < 2:\n    raise SystemExit(f'PATCH FAILED: expected two parse_result loops, found {s.count(needle)}')"
new = "if s.count(needle) < 1:\n    raise SystemExit(f'PATCH FAILED: parse_result persistence loop not found; found {s.count(needle)}')"
if old not in text:
    raise SystemExit('PATCH DRIVER FAILED: original precondition not found')
text = text.replace(old, new, 1)

old_semantics = """    if classification in {'footer_payment_tax', 'ignore'}:
        return {'line_role': ROLE_FINANCIAL, 'inventory_eligible': False}
    return {'line_role': ROLE_METADATA, 'inventory_eligible': False}
"""
new_semantics = """    if classification == 'footer_payment_tax':
        return {'line_role': ROLE_FINANCIAL, 'inventory_eligible': False}
    if classification in {'metadata', 'amount_detail', 'continuation'}:
        return {'line_role': ROLE_METADATA, 'inventory_eligible': False}
    if classification == 'ignore' and rule != 'NO_RULE_MATCHED':
        return {'line_role': ROLE_METADATA, 'inventory_eligible': False}
    # receipt_table_lines already contains logical parsed receipt candidates.
    # If no explicit non-inventory rule matched, fail open to a physical product
    # so unknown/new article wording is never silently lost from Uitpakken.
    return {'line_role': ROLE_PRODUCT, 'inventory_eligible': True}
"""
if old_semantics not in text:
    raise SystemExit('PATCH DRIVER FAILED: semantic fallback block not found')
text = text.replace(old_semantics, new_semantics, 1)

applicator.write_text(text, encoding='utf-8')
runpy.run_path(str(applicator), run_name='__main__')

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
applicator.write_text(text.replace(old, new, 1), encoding='utf-8')
runpy.run_path(str(applicator), run_name='__main__')

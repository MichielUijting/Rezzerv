from pathlib import Path

p = Path('backend/app/services/receipt_service.py')
s = p.read_text(encoding='utf-8')

# Expand ignored markers for non-product lines
if 'korting' not in s:
    s = s.replace(
        "IGNORED_LINE_MARKERS = {",
        "IGNORED_LINE_MARKERS = {\n    'korting', 'bonus', 'actie', 'voordeel', 'retour', 'statiegeld',",
    )

p.write_text(s, encoding='utf-8')

# cleanup
try:
    Path('.github/workflows/apply-pr4a.yml').unlink()
    Path('tools/apply_pr4a_line_filter.py').unlink()
except Exception:
    pass

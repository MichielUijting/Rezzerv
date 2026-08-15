from pathlib import Path

root = Path(__file__).resolve().parents[1]
p = root / 'backend/app/receipt_ingestion/line_classifier.py'
s = p.read_text(encoding='utf-8')
old = '    is_spaarzegels_flow_excluded,\n'
if s.count(old) != 1:
    raise SystemExit(f'expected one dead import, found {s.count(old)}')
s = s.replace(old, '', 1)
p.write_text(s, encoding='utf-8')
print('DEAD_IMPORT_REMOVED')

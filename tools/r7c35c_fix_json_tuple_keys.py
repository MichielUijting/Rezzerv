from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
p = ROOT / 'tools' / 'r7c35c_dump_receipt_status_details.py'
s = p.read_text(encoding='utf-8')

old = '"detail_keys_counter": dict(Counter(tuple(sorted(item.keys())) for item in details)),\n'
new = '"detail_keys_counter": {"|".join(keys): count for keys, count in Counter(tuple(sorted(item.keys())) for item in details).items()},\n'
if old not in s:
    raise SystemExit('R7c35c JSON tuple-key patchpunt niet gevonden')
s = s.replace(old, new)

p.write_text(s, encoding='utf-8')
print('R7c35c JSON tuple-key fix toegepast')

from __future__ import annotations

from pathlib import Path

path = Path("backend/app/receipt_ingestion/service_parts/store_specific_parsers.py")
text = path.read_text(encoding="utf-8")

old = "cleaned = re.sub(r'[]+', '', line).strip()"
new = "cleaned = re.sub(r'[\\[\\]]+', '', line).strip()"

if old not in text:
    raise SystemExit("Picnic regex-fout niet gevonden; patch niet uitgevoerd.")

text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
print("Picnic parser regex hersteld: lege character class []+ vervangen door geldige bracket-cleanup [\\[\\]]+.")

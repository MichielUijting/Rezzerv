from pathlib import Path

path = Path("backend/app/services/receipt_service.py")
lines = path.read_text(encoding="utf-8-sig").splitlines()

target = "if looks_like_ah_context(text_lines, filename, store_name=store_name):"
start = None

for i, line in enumerate(lines):
    if target in line:
        start = i
        break

if start is None:
    raise SystemExit("Herstel niet uitgevoerd: kapotte AH-wiring niet gevonden")

indent = lines[start][:len(lines[start]) - len(lines[start].lstrip())]

# Zoek einde van het kapotte if/else-blok.
end = start + 1
while end < len(lines):
    line = lines[end]
    if "_total_amount_from_lines(text_lines, filename)" in line:
        end += 1
        break
    end += 1

replacement = [
    indent + "total_amount, explicit_total_found = _total_amount_from_lines(text_lines, filename)"
]

new_lines = lines[:start] + replacement + lines[end:]
path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

print("HOTFIX applied: broken AH total wiring removed from receipt_service.py")

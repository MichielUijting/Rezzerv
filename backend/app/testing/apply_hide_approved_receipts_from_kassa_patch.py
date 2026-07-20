"""Gecontroleerde patch: goedgekeurde bonnen verdwijnen uit de Kassa-lijst."""
from pathlib import Path

MAIN = Path(__file__).resolve().parents[1] / "main.py"
source = MAIN.read_text(encoding="utf-8")

route_start = source.index('@app.get("/api/receipts")')
route_end = source.index('@app.get("/api/receipts/{receipt_table_id}")', route_start)
route = source[route_start:route_end]

old = """                WHERE rt.household_id = :household_id
                  AND rt.deleted_at IS NULL
                  AND rr.deleted_at IS NULL
"""
new = """                WHERE rt.household_id = :household_id
                  AND rt.approved_at IS NULL
                  AND rt.deleted_at IS NULL
                  AND rr.deleted_at IS NULL
"""

if "AND rt.approved_at IS NULL" in route:
    print("PATCH_REEDS_AANWEZIG=JA")
    raise SystemExit(0)
if old not in route:
    raise RuntimeError("De verwachte Kassa-lijstquery is niet exact gevonden")

patched_route = route.replace(old, new, 1)
patched = source[:route_start] + patched_route + source[route_end:]
MAIN.write_text(patched, encoding="utf-8", newline="\n")

print("PATCH_TOEGEPAST=JA")
print(f"BESTAND={MAIN}")

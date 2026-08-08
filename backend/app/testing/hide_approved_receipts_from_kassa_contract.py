"""Statisch contract voor de Kassa-lijst na gebruikersgoedkeuring."""
from pathlib import Path

CANDIDATES = (
    Path("/app/app/main.py"),
    Path(__file__).resolve().parents[1] / "main.py",
    Path(__file__).resolve().parents[3] / "backend/app/main.py",
)
MAIN = next((path for path in CANDIDATES if path.exists()), None)
if MAIN is None:
    raise FileNotFoundError("main.py niet gevonden")
source = MAIN.read_text(encoding="utf-8")


def section(start: str, end: str) -> str:
    start_index = source.index(start)
    end_index = source.index(end, start_index)
    return source[start_index:end_index]


kassa_list = section(
    '@app.get("/api/receipts")',
    '@app.get("/api/receipts/{receipt_table_id}")',
)
unpack_list = section(
    '@app.get("/api/unpack-start-batches")',
    '@app.get("/api/receipts")',
)
approve_route = section(
    '@app.post("/api/receipts/{receipt_table_id}/approve")',
    '@app.post("/api/receipts/{receipt_table_id}/reparse")',
)

assert "AND rt.approved_at IS NULL" in kassa_list, (
    "De Kassa-lijst sluit goedgekeurde bonnen niet uit"
)
assert "AND rt.approved_at IS NOT NULL" in unpack_list, (
    "Uitpakken toont goedgekeurde bonnen niet meer"
)
assert "approved_at = CURRENT_TIMESTAMP" in approve_route, (
    "De goedkeuringsroute legt approved_at niet vast"
)
assert "deleted_at" not in approve_route.lower() or "UPDATE receipt_tables SET deleted_at" not in approve_route, (
    "Goedkeuren mag de kassabon niet verwijderen"
)

print(f"PASS: main.py gevonden op {MAIN}")
print("PASS: goedgekeurde bonnen verdwijnen uit de Kassa-lijst")
print("PASS: goedgekeurde bonnen blijven beschikbaar voor Uitpakken")
print("PASS: goedkeuren verwijdert geen bon of historie")

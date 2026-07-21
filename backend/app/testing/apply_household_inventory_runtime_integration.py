"""Apply the household-context integration to backend/app/main.py.

This is a deterministic repository maintenance helper. It refuses to modify the
file when the expected source anchors are absent or occur more than once.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TARGET = ROOT / "backend" / "app" / "main.py"


IMPORT_ANCHOR = "from app.services.testing_service import testing_service\n"
IMPORT_REPLACEMENT = IMPORT_ANCHOR + "from app.services.household_context_adapter import resolve_legacy_household_context\n"

OLD_PREVIEW = '''@app.get("/api/dev/inventory-preview")
def dev_inventory_preview(authorization: Optional[str] = Header(None)):
    effective_household_id = get_request_household_id(authorization)
'''
NEW_PREVIEW = '''@app.get("/api/dev/inventory-preview")
def dev_inventory_preview(authorization: Optional[str] = Header(None)):
    legacy_context = require_household_context(authorization)
    household_context = resolve_legacy_household_context(legacy_context=legacy_context)
    effective_household_id = household_context.active_household_id
'''

OLD_SPACE_LOOKUP = 'text("SELECT id FROM spaces WHERE id = :id LIMIT 1"),\n            {"id": normalized_space_id},'
NEW_SPACE_LOOKUP = 'text("SELECT id FROM spaces WHERE id = :id AND household_id = :household_id LIMIT 1"),\n            {"id": normalized_space_id, "household_id": household_id},'

OLD_SUBLOCATION_SIGNATURE = "def _dev_resolve_sublocation_id(conn, space_id: str | None, sublocation_id: str | None, sublocation_name: str | None):"
NEW_SUBLOCATION_SIGNATURE = "def _dev_resolve_sublocation_id(conn, household_id: str, space_id: str | None, sublocation_id: str | None, sublocation_name: str | None):"

OLD_SUBLOCATION_LOOKUP = 'text("SELECT id FROM sublocations WHERE id = :id LIMIT 1"),\n            {"id": normalized_sublocation_id},'
NEW_SUBLOCATION_LOOKUP = '''text(
                """
                SELECT sl.id
                FROM sublocations sl
                JOIN spaces s ON s.id = sl.space_id
                WHERE sl.id = :id
                  AND s.household_id = :household_id
                LIMIT 1
                """
            ),
            {"id": normalized_sublocation_id, "household_id": household_id},'''

OLD_UPDATE_SIGNATURE = '''@app.put("/api/dev/inventory/{inventory_id}")
def dev_update_inventory(inventory_id: str, payload: InventoryUpdate):
'''
NEW_UPDATE_SIGNATURE = '''@app.put("/api/dev/inventory/{inventory_id}")
def dev_update_inventory(
    inventory_id: str,
    payload: InventoryUpdate,
    authorization: Optional[str] = Header(None),
):
    legacy_context = require_household_context(authorization)
    household_context = resolve_legacy_household_context(legacy_context=legacy_context)
    effective_household_id = household_context.active_household_id
'''

REPLACEMENTS = [
    (IMPORT_ANCHOR, IMPORT_REPLACEMENT, "household context adapter import"),
    (OLD_PREVIEW, NEW_PREVIEW, "inventory preview context"),
    (OLD_SPACE_LOOKUP, NEW_SPACE_LOOKUP, "space household lookup"),
    (OLD_SUBLOCATION_SIGNATURE, NEW_SUBLOCATION_SIGNATURE, "sublocation household signature"),
    (OLD_SUBLOCATION_LOOKUP, NEW_SUBLOCATION_LOOKUP, "sublocation household lookup"),
    (OLD_UPDATE_SIGNATURE, NEW_UPDATE_SIGNATURE, "inventory update context"),
    (
        "WHERE id = :id\n                LIMIT 1",
        "WHERE id = :id\n                  AND household_id = :household_id\n                LIMIT 1",
        "inventory pre-read household filter",
    ),
    (
        '{"id": normalized_inventory_id},\n        ).mappings().first()',
        '{"id": normalized_inventory_id, "household_id": effective_household_id},\n        ).mappings().first()',
        "inventory pre-read parameters",
    ),
    (
        "household_id = str(existing.get(\"household_id\") or \"\").strip() or None\n        space_id = _dev_resolve_space_id(conn, household_id, payload.space_id, payload.space_name)\n        sublocation_id = _dev_resolve_sublocation_id(conn, space_id, payload.sublocation_id, payload.sublocation_name)",
        "household_id = effective_household_id\n        space_id = _dev_resolve_space_id(conn, household_id, payload.space_id, payload.space_name)\n        sublocation_id = _dev_resolve_sublocation_id(conn, household_id, space_id, payload.sublocation_id, payload.sublocation_name)",
        "resolver household propagation",
    ),
    (
        "WHERE id = :id\n                \"\"\"",
        "WHERE id = :id\n                  AND household_id = :household_id\n                \"\"\"",
        "inventory update household filter",
    ),
    (
        '"id": normalized_inventory_id,\n                "naam":',
        '"id": normalized_inventory_id,\n                "household_id": effective_household_id,\n                "naam":',
        "inventory update household parameter",
    ),
    (
        "WHERE i.id = :id\n                LIMIT 1",
        "WHERE i.id = :id\n                  AND i.household_id = :household_id\n                LIMIT 1",
        "inventory response household filter",
    ),
    (
        '{"id": normalized_inventory_id},\n        ).mappings().first()\n\n    return {"ok": True',
        '{"id": normalized_inventory_id, "household_id": effective_household_id},\n        ).mappings().first()\n\n    return {"ok": True',
        "inventory response household parameters",
    ),
]


def replace_once(content: str, old: str, new: str, label: str) -> str:
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: verwacht exact 1 bronanker, gevonden {count}")
    return content.replace(old, new, 1)


def main() -> None:
    content = TARGET.read_text(encoding="utf-8")
    original = content
    for old, new, label in REPLACEMENTS:
        content = replace_once(content, old, new, label)
    if content == original:
        raise RuntimeError("Geen wijziging uitgevoerd")
    TARGET.write_text(content, encoding="utf-8", newline="\n")
    print("HOUSEHOLD_INVENTORY_RUNTIME_INTEGRATION_APPLIED")


if __name__ == "__main__":
    main()

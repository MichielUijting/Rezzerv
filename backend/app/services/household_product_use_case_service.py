from __future__ import annotations

from sqlalchemy import text

PRODUCT_USE_CASES = ("inhuis_halen", "wat_inhuis", "waar_inhuis")
PRODUCT_USE_CASE_SET = frozenset(PRODUCT_USE_CASES)


def ensure_household_product_use_case_foundation(conn) -> None:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS household_product_use_cases (
            household_id TEXT NOT NULL,
            use_case TEXT NOT NULL
                CHECK (use_case IN ('inhuis_halen', 'wat_inhuis', 'waar_inhuis')),
            activated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (household_id, use_case)
        )
    """))


def activate_household_product_use_case(conn, *, household_id: str, use_case: str) -> None:
    normalized_household_id = str(household_id or "").strip()
    normalized_use_case = str(use_case or "").strip().lower()
    if not normalized_household_id:
        raise ValueError("Huishouden ontbreekt")
    if normalized_use_case not in PRODUCT_USE_CASE_SET:
        raise ValueError("Ongeldig gebruiksdoel")

    ensure_household_product_use_case_foundation(conn)
    conn.execute(text("""
        INSERT OR IGNORE INTO household_product_use_cases (
            household_id,
            use_case,
            activated_at
        ) VALUES (
            :household_id,
            :use_case,
            CURRENT_TIMESTAMP
        )
    """), {
        "household_id": normalized_household_id,
        "use_case": normalized_use_case,
    })


def resolve_active_household_product_use_cases(
    conn,
    *,
    household_id: str,
    primary_use_case: str | None = None,
) -> list[str]:
    normalized_household_id = str(household_id or "").strip()
    if not normalized_household_id:
        raise ValueError("Huishouden ontbreekt")

    ensure_household_product_use_case_foundation(conn)
    active = {
        str(row.get("use_case") or "").strip().lower()
        for row in conn.execute(text("""
            SELECT use_case
            FROM household_product_use_cases
            WHERE household_id = :household_id
        """), {"household_id": normalized_household_id}).mappings().all()
    }

    normalized_primary = str(primary_use_case or "").strip().lower()
    if normalized_primary in PRODUCT_USE_CASE_SET:
        active.add(normalized_primary)

    return [use_case for use_case in PRODUCT_USE_CASES if use_case in active]

from __future__ import annotations

from typing import Any

from sqlalchemy import inspect, text

from app.db import engine
from app.services.gpc_import_service import import_gs1_gpc_nl
from app.services.gpc_local_catalog_service import import_bundled_gpc_catalog


LOCALIZED_COLUMNS: dict[str, str] = {
    "gpc_brick_name_nl": "TEXT",
    "gpc_brick_name_en": "TEXT",
    "gpc_class_name_nl": "TEXT",
    "gpc_class_name_en": "TEXT",
    "gpc_family_name_nl": "TEXT",
    "gpc_family_name_en": "TEXT",
    "gpc_segment_name_nl": "TEXT",
    "gpc_segment_name_en": "TEXT",
}


def _columns(table_name: str) -> set[str]:
    try:
        return {str(column.get("name") or "") for column in inspect(engine).get_columns(table_name)}
    except Exception:
        return set()


def ensure_gpc_localization_schema() -> None:
    with engine.begin() as conn:
        existing = _columns("gpc_product_groups")
        for name, definition in LOCALIZED_COLUMNS.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE gpc_product_groups ADD COLUMN {name} {definition}"))


def _capture_language_snapshot(language_code: str) -> int:
    language_code = str(language_code or "").strip().lower()
    if language_code not in {"nl", "en"}:
        raise ValueError("Alleen Nederlandse en Engelse GPC-omschrijvingen worden ondersteund")

    ensure_gpc_localization_schema()
    suffix = "nl" if language_code == "nl" else "en"
    with engine.begin() as conn:
        result = conn.execute(text(f"""
            UPDATE gpc_product_groups
            SET gpc_brick_name_{suffix} = COALESCE(NULLIF(gpc_brick_name, ''), gpc_brick_name_{suffix}),
                gpc_class_name_{suffix} = COALESCE(NULLIF(gpc_class_name, ''), gpc_class_name_{suffix}),
                gpc_family_name_{suffix} = COALESCE(NULLIF(gpc_family_name, ''), gpc_family_name_{suffix}),
                gpc_segment_name_{suffix} = COALESCE(NULLIF(gpc_segment_name, ''), gpc_segment_name_{suffix})
            WHERE lower(COALESCE(language_code, '')) = :language_code
        """), {"language_code": language_code})
    return int(result.rowcount or 0)


def synchronize_dutch_product_type_display_names() -> dict[str, Any]:
    """Maak de Nederlandse Brick-omschrijving leidend voor de huidige Rezzerv-app.

    Deze handeling wijzigt uitsluitend centrale GPC-referentie- en presentatiedata.
    Voorraad, huishoudartikelen en Producttypekoppelingen blijven ongewijzigd.
    """
    ensure_gpc_localization_schema()
    _capture_language_snapshot("nl")
    _capture_language_snapshot("en")

    with engine.begin() as conn:
        missing = int(conn.execute(text("""
            SELECT COUNT(*)
            FROM gpc_product_groups
            WHERE COALESCE(active, 1) = 1
              AND (gpc_brick_name_nl IS NULL OR trim(gpc_brick_name_nl) = '')
        """)).scalar() or 0)
        if missing:
            raise ValueError(
                f"Nederlandse GPC-import is onvolledig: {missing} actieve Bricks hebben nog geen Nederlandse omschrijving"
            )

        result = conn.execute(text("""
            UPDATE product_inventory_groups
            SET display_name = (
                    SELECT g.gpc_brick_name_nl
                    FROM gpc_product_groups g
                    WHERE g.gpc_brick_code = product_inventory_groups.gpc_brick_code
                      AND COALESCE(g.active, 1) = 1
                ),
                gpc_class_name = (
                    SELECT g.gpc_class_name_nl
                    FROM gpc_product_groups g
                    WHERE g.gpc_brick_code = product_inventory_groups.gpc_brick_code
                ),
                gpc_family_name = (
                    SELECT g.gpc_family_name_nl
                    FROM gpc_product_groups g
                    WHERE g.gpc_brick_code = product_inventory_groups.gpc_brick_code
                ),
                updated_at = CURRENT_TIMESTAMP
            WHERE gpc_brick_code IS NOT NULL
              AND EXISTS (
                    SELECT 1
                    FROM gpc_product_groups g
                    WHERE g.gpc_brick_code = product_inventory_groups.gpc_brick_code
                      AND COALESCE(g.active, 1) = 1
                      AND g.gpc_brick_name_nl IS NOT NULL
                      AND trim(g.gpc_brick_name_nl) <> ''
                )
        """))
        total = int(conn.execute(text("""
            SELECT COUNT(*)
            FROM gpc_product_groups
            WHERE COALESCE(active, 1) = 1
              AND gpc_brick_name_nl IS NOT NULL
              AND trim(gpc_brick_name_nl) <> ''
        """)).scalar() or 0)

    return {
        "ok": True,
        "language": "nl",
        "localized_bricks": total,
        "product_types_updated": int(result.rowcount or 0),
        "display_policy": "dutch_required",
        "mutates_inventory": False,
    }


def import_gs1_gpc_nl_localized() -> dict[str, Any]:
    result = import_gs1_gpc_nl()
    captured = _capture_language_snapshot("nl")
    synchronized = synchronize_dutch_product_type_display_names()
    return {**result, "dutch_rows_captured": captured, "localization": synchronized}


def import_bundled_gpc_catalog_localized() -> dict[str, Any]:
    result = import_bundled_gpc_catalog()
    captured = _capture_language_snapshot("en")
    return {
        **result,
        "english_rows_captured": captured,
        "display_policy": "dutch_required",
        "note": "De Engelse catalogus vervangt geen Nederlandse Brick-omschrijving.",
    }

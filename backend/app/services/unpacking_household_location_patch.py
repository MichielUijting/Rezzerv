from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import text


def _required_household_id(value: Any) -> str:
    household_id = str(value or "").strip()
    if not household_id:
        raise HTTPException(status_code=400, detail="Actief huishouden ontbreekt")
    return household_id


def _line_reference(row, line_id: str) -> dict:
    if not row:
        return {"line_id": str(line_id)}
    external_ref = str(row.get("external_line_ref") or "").strip()
    display_ref = external_ref or f"regel {int(row.get('ui_sort_order') or 0) + 1}"
    article_name = str(row.get("article_name_raw") or "").strip()
    return {
        "line_id": str(row.get("id") or line_id),
        "batch_id": str(row.get("batch_id") or ""),
        "household_id": str(row.get("household_id") or ""),
        "external_line_ref": external_ref,
        "ui_line_number": int(row.get("ui_sort_order") or 0) + 1,
        "article_name": article_name,
        "target_location_id": str(row.get("target_location_id") or ""),
        "review_decision": str(row.get("review_decision") or "pending"),
        "display_label": f"{display_ref}: {article_name}" if article_name else display_ref,
    }


def validate_purchase_import_target_location(conn, line_id: str, target_location_id: str | None):
    line = conn.execute(
        text(
            """
            SELECT pil.id,
                   pil.batch_id,
                   pil.external_line_ref,
                   pil.article_name_raw,
                   pil.target_location_id,
                   pil.review_decision,
                   COALESCE(pil.ui_sort_order, 0) AS ui_sort_order,
                   pib.household_id
            FROM purchase_import_lines pil
            JOIN purchase_import_batches pib ON pib.id = pil.batch_id
            WHERE pil.id = :line_id
            LIMIT 1
            """
        ),
        {"line_id": str(line_id)},
    ).mappings().first()
    if not line:
        raise HTTPException(status_code=404, detail="Inkoopregel niet gevonden")

    household_id = _required_household_id(line.get("household_id"))
    line_ref = _line_reference(line, line_id)
    normalized_target_id = str(target_location_id or "").strip()
    if not normalized_target_id:
        return None, line_ref

    sublocation = conn.execute(
        text(
            """
            SELECT sl.id AS location_id,
                   sl.space_id,
                   s.naam AS space_name,
                   sl.naam AS sublocation_name
            FROM sublocations sl
            JOIN spaces s ON s.id = sl.space_id
            WHERE sl.id = :target_location_id
              AND s.household_id = :household_id
            LIMIT 1
            """
        ),
        {
            "target_location_id": normalized_target_id,
            "household_id": household_id,
        },
    ).mappings().first()
    if sublocation:
        return {
            "location_id": str(sublocation["location_id"]),
            "space_id": str(sublocation["space_id"]),
            "sublocation_id": str(sublocation["location_id"]),
            "location_label": f"{sublocation['space_name']} / {sublocation['sublocation_name']}",
        }, line_ref

    space = conn.execute(
        text(
            """
            SELECT id, naam
            FROM spaces
            WHERE id = :target_location_id
              AND household_id = :household_id
            LIMIT 1
            """
        ),
        {
            "target_location_id": normalized_target_id,
            "household_id": household_id,
        },
    ).mappings().first()
    if space:
        return {
            "location_id": str(space["id"]),
            "space_id": str(space["id"]),
            "sublocation_id": None,
            "location_label": str(space["naam"]),
        }, line_ref

    return None, line_ref


def resolve_space_and_sublocation_ids(
    conn,
    household_id: Any,
    space_id: str | None = None,
    sublocation_id: str | None = None,
    space_name: str | None = None,
    sublocation_name: str | None = None,
):
    household_id = _required_household_id(household_id)
    normalized_space_name = " ".join(str(space_name or "").strip().split()) or None
    normalized_sublocation_name = " ".join(str(sublocation_name or "").strip().split()) or None
    resolved_space_id = str(space_id or "").strip() or None
    resolved_sublocation_id = str(sublocation_id or "").strip() or None

    if resolved_space_id:
        row = conn.execute(
            text("SELECT id FROM spaces WHERE id = :id AND household_id = :household_id LIMIT 1"),
            {"id": resolved_space_id, "household_id": household_id},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=400, detail="Onbekende space_id")
    elif normalized_space_name:
        row = conn.execute(
            text("SELECT id FROM spaces WHERE household_id = :household_id AND lower(trim(naam)) = lower(trim(:naam)) LIMIT 1"),
            {"household_id": household_id, "naam": normalized_space_name},
        ).mappings().first()
        if row:
            resolved_space_id = str(row["id"])
        else:
            resolved_space_id = str(conn.execute(
                text("INSERT INTO spaces (id, naam, household_id) VALUES (lower(hex(randomblob(16))), :naam, :household_id) RETURNING id"),
                {"naam": normalized_space_name, "household_id": household_id},
            ).scalar_one())

    if resolved_sublocation_id:
        row = conn.execute(
            text(
                """
                SELECT sl.id, sl.space_id
                FROM sublocations sl
                JOIN spaces s ON s.id = sl.space_id
                WHERE sl.id = :id
                  AND s.household_id = :household_id
                LIMIT 1
                """
            ),
            {"id": resolved_sublocation_id, "household_id": household_id},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=400, detail="Onbekende sublocation_id")
        if resolved_space_id and str(row["space_id"]) != resolved_space_id:
            raise HTTPException(status_code=400, detail="sublocation_id hoort niet bij de gekozen ruimte")
        resolved_space_id = resolved_space_id or str(row["space_id"])
    elif normalized_sublocation_name:
        if not resolved_space_id:
            raise HTTPException(status_code=400, detail="Ruimte is verplicht voor een sublocatie")
        row = conn.execute(
            text(
                """
                SELECT sl.id
                FROM sublocations sl
                JOIN spaces s ON s.id = sl.space_id
                WHERE sl.space_id = :space_id
                  AND s.household_id = :household_id
                  AND lower(trim(sl.naam)) = lower(trim(:naam))
                LIMIT 1
                """
            ),
            {
                "space_id": resolved_space_id,
                "household_id": household_id,
                "naam": normalized_sublocation_name,
            },
        ).mappings().first()
        if row:
            resolved_sublocation_id = str(row["id"])
        else:
            resolved_sublocation_id = str(conn.execute(
                text(
                    """
                    INSERT INTO sublocations (id, naam, space_id)
                    SELECT lower(hex(randomblob(16))), :naam, s.id
                    FROM spaces s
                    WHERE s.id = :space_id
                      AND s.household_id = :household_id
                    RETURNING id
                    """
                ),
                {
                    "naam": normalized_sublocation_name,
                    "space_id": resolved_space_id,
                    "household_id": household_id,
                },
            ).scalar_one())

    return resolved_space_id, resolved_sublocation_id


def install_unpacking_household_location_patch(main_module) -> None:
    main_module.validate_purchase_import_target_location = validate_purchase_import_target_location
    main_module.resolve_space_and_sublocation_ids = resolve_space_and_sublocation_ids

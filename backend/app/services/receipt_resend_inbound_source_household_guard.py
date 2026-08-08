from __future__ import annotations

from typing import Any

from fastapi import HTTPException


def resolve_registered_inbound_source(module: Any, recipient_addresses: list[str]) -> dict[str, Any]:
    normalized_addresses = sorted({
        str(value or "").strip().lower()
        for value in (recipient_addresses or [])
        if str(value or "").strip()
    })
    if not normalized_addresses:
        raise HTTPException(status_code=400, detail="De inkomende e-mail bevat geen bruikbaar Rezzerv-ontvangstadres.")

    placeholders = ", ".join(f":address_{index}" for index, _ in enumerate(normalized_addresses))
    parameters = {
        f"address_{index}": address
        for index, address in enumerate(normalized_addresses)
    }
    with module.engine.begin() as conn:
        rows = conn.execute(
            module.text(
                f"""
                SELECT
                    rs.id,
                    rs.household_id,
                    rs.type,
                    rs.label,
                    rs.source_path,
                    rs.is_active,
                    rs.last_scan_at,
                    rs.created_at,
                    rs.updated_at
                FROM receipt_sources rs
                JOIN household_registry hr ON hr.id = rs.household_id
                WHERE rs.type = 'email'
                  AND COALESCE(rs.is_active, 0) = 1
                  AND lower(trim(rs.source_path)) IN ({placeholders})
                ORDER BY rs.id ASC
                """
            ),
            parameters,
        ).mappings().all()

    unique_rows: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        source_id = str(item.get("id") or "").strip()
        household_id = str(item.get("household_id") or "").strip()
        source_path = str(item.get("source_path") or "").strip().lower()
        if not source_id or not household_id or source_path not in normalized_addresses:
            continue
        unique_rows[source_id] = item

    if not unique_rows:
        raise HTTPException(
            status_code=400,
            detail="Deze inkomende e-mail past niet bij een vooraf geregistreerd actief Rezzerv-adres.",
        )
    if len(unique_rows) != 1:
        raise HTTPException(
            status_code=409,
            detail="Het inkomende e-mailadres is dubbelzinnig geconfigureerd en kan niet veilig aan één huishouden worden gekoppeld.",
        )

    row = next(iter(unique_rows.values()))
    response = module.build_receipt_source_response(row)
    response["route_address"] = str(row.get("source_path") or "").strip().lower()
    response["household_id"] = str(row.get("household_id") or "").strip()
    if not response["household_id"]:
        raise HTTPException(status_code=400, detail="De geregistreerde receiptbron heeft geen geldig huishouden.")
    return response


def install_receipt_resend_inbound_source_household_guard(module: Any) -> None:
    if getattr(module, "_receipt_resend_inbound_source_household_guard_installed", False):
        return

    def strict_resolver(recipient_addresses: list[str]) -> dict[str, Any]:
        return resolve_registered_inbound_source(module, recipient_addresses)

    module.resolve_household_email_source = strict_resolver
    module._receipt_resend_inbound_source_household_guard_installed = True

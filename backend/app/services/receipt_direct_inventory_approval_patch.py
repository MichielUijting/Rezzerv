from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import text

from app.services.canonical_direct_location_service import ensure_canonical_direct_location
from app.services.household_product_configuration_service import (
    resolve_household_product_configuration,
)

_APPROVE_PATH = "/api/receipts/{receipt_table_id}/approve"


def should_process_approved_receipt_directly_to_inventory(configuration) -> bool:
    if configuration is None:
        return False
    return bool(
        getattr(configuration, "receipt_processing_enabled", False)
        and getattr(configuration, "simple_inventory_enabled", False)
        and not getattr(configuration, "unpacking_enabled", False)
        and str(
            getattr(configuration, "location_tracking_level", "") or ""
        ).strip().lower()
        in {"none", "global"}
    )


def _prepare_receipt_batch_for_direct_inventory(
    main_module,
    conn,
    *,
    batch_id: str,
    household_id: str,
    configuration,
) -> int:
    normalized_batch_id = str(batch_id or "").strip()
    normalized_household_id = str(household_id or "").strip()
    if not normalized_batch_id or not normalized_household_id:
        raise HTTPException(
            status_code=400,
            detail="Bonbatch of huishouden ontbreekt voor directe voorraadverwerking",
        )

    location_level = str(
        getattr(configuration, "location_tracking_level", "") or ""
    ).strip().lower()
    if location_level not in {"none", "global"}:
        raise HTTPException(
            status_code=409,
            detail="Directe voorraadverwerking vereist geen of alleen globale locaties",
        )

    direct_location_id = None
    if location_level == "global":
        direct_location_id = ensure_canonical_direct_location(
            conn,
            household_id=normalized_household_id,
        )

    lines = conn.execute(
        text(
            """
            SELECT id, article_name_raw, matched_household_article_id,
                   matched_global_product_id, external_article_code, brand_raw
            FROM purchase_import_lines
            WHERE batch_id = :batch_id
            ORDER BY COALESCE(ui_sort_order, 999999), created_at ASC, id ASC
            """
        ),
        {"batch_id": normalized_batch_id},
    ).mappings().all()

    prepared_count = 0
    for line in lines:
        line_id = str(line.get("id") or "").strip()
        if not line_id:
            continue

        article_id = str(line.get("matched_household_article_id") or "").strip() or None
        global_product_id = str(line.get("matched_global_product_id") or "").strip() or None
        article_name = main_module.normalize_household_article_name(
            str(line.get("article_name_raw") or "")
        )

        if not article_id and global_product_id:
            article_id = main_module.ensure_household_article_for_global_product(
                conn,
                normalized_household_id,
                global_product_id,
                article_name_hint=article_name or None,
                barcode=line.get("external_article_code"),
                brand=line.get("brand_raw"),
            )
        if not article_id:
            if not article_name:
                raise HTTPException(
                    status_code=400,
                    detail="Bonregel zonder artikelnaam kan niet direct naar Voorraad",
                )
            article_id = main_module.ensure_household_article(
                conn,
                normalized_household_id,
                article_name,
            )

        conn.execute(
            text(
                """
                UPDATE purchase_import_lines
                SET matched_household_article_id = :article_id,
                    suggested_household_article_id = COALESCE(
                        suggested_household_article_id,
                        :article_id
                    ),
                    match_status = 'matched',
                    review_decision = 'selected',
                    target_location_id = :target_location_id,
                    suggested_location_id = COALESCE(
                        suggested_location_id,
                        :target_location_id
                    ),
                    article_override_mode = 'auto',
                    location_override_mode = 'auto',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :line_id
                  AND batch_id = :batch_id
                """
            ),
            {
                "article_id": str(article_id),
                "target_location_id": direct_location_id,
                "line_id": line_id,
                "batch_id": normalized_batch_id,
            },
        )
        prepared_count += 1

    main_module.update_batch_status(conn, normalized_batch_id)
    return prepared_count


def install_receipt_direct_inventory_approval_patch(main_module) -> None:
    app = main_module.app
    if getattr(app.state, "receipt_direct_inventory_approval_patch_installed", False):
        return

    original_approve = main_module.approve_receipt_table

    def approve_receipt_table_with_direct_inventory(
        receipt_table_id: str,
        authorization: str | None = None,
    ):
        result = original_approve(receipt_table_id, authorization)

        direct_batch_id = None
        direct_actor = "ui"
        with main_module.engine.begin() as conn:
            receipt = conn.execute(
                text(
                    """
                    SELECT household_id, approved_by_user_email
                    FROM receipt_tables
                    WHERE id = :receipt_table_id
                    LIMIT 1
                    """
                ),
                {"receipt_table_id": receipt_table_id},
            ).mappings().first()
            if not receipt:
                return result

            household_id = str(receipt.get("household_id") or "").strip()
            direct_actor = str(receipt.get("approved_by_user_email") or "").strip() or "ui"
            try:
                configuration = resolve_household_product_configuration(
                    conn,
                    household_id,
                )
            except LookupError:
                configuration = None

            if not should_process_approved_receipt_directly_to_inventory(configuration):
                result["approval_destination"] = "unpacking"
                return result

            batch = conn.execute(
                text(
                    """
                    SELECT id
                    FROM purchase_import_batches
                    WHERE household_id = :household_id
                      AND source_type = 'receipt'
                      AND source_reference = :source_reference
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                    """
                ),
                {
                    "household_id": household_id,
                    "source_reference": f"receipt:{receipt_table_id}",
                },
            ).mappings().first()
            if not batch:
                raise HTTPException(
                    status_code=500,
                    detail="Goedgekeurde bon heeft geen voorraadbatch gekregen",
                )

            direct_batch_id = str(batch["id"])
            prepared_count = _prepare_receipt_batch_for_direct_inventory(
                main_module,
                conn,
                batch_id=direct_batch_id,
                household_id=household_id,
                configuration=configuration,
            )
            if prepared_count < 1:
                raise HTTPException(
                    status_code=400,
                    detail="De goedgekeurde bon bevat geen voorraadregels om te verwerken",
                )

        inventory_processing = main_module.process_purchase_import_batch(
            direct_batch_id,
            main_module.ProcessBatchRequest(
                processed_by=direct_actor,
                mode="selected_only",
            ),
            authorization,
        )
        failed_count = int((inventory_processing or {}).get("failed_count") or 0)
        skipped_count = int((inventory_processing or {}).get("skipped_count") or 0)
        if failed_count or skipped_count:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Bon is goedgekeurd, maar niet alle regels konden direct naar "
                    "Voorraad worden verwerkt. Probeer Goedkeuren opnieuw; reeds "
                    "verwerkte regels worden niet dubbel geboekt."
                ),
            )

        refreshed = main_module.get_receipt_detail(receipt_table_id, authorization)
        refreshed["approval_destination"] = "inventory"
        refreshed["inventory_processing"] = {
            "batch_id": inventory_processing.get("batch_id"),
            "status": inventory_processing.get("status"),
            "processed_count": int(inventory_processing.get("processed_count") or 0),
            "failed_count": failed_count,
            "skipped_count": skipped_count,
        }
        return refreshed

    main_module.approve_receipt_table = approve_receipt_table_with_direct_inventory

    patched_route = False
    for route in app.routes:
        if (
            getattr(route, "path", None) == _APPROVE_PATH
            and "POST" in (getattr(route, "methods", set()) or set())
        ):
            route.endpoint = approve_receipt_table_with_direct_inventory
            if getattr(route, "dependant", None) is not None:
                route.dependant.call = approve_receipt_table_with_direct_inventory
            patched_route = True
            break
    if not patched_route:
        raise RuntimeError("Receipt approve-route niet gevonden voor directe voorraadpatch")

    app.state.receipt_direct_inventory_approval_patch_installed = True

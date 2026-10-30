from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import text

from app.services.household_product_configuration_service import (
    resolve_household_product_configuration,
)
from app.services.receipt_stock_review_service import (
    checked_stock_quantity,
    resolve_stock_household_article,
)
from app.services.temporary_consumable_automation_policy import (
    install_temporary_all_articles_consumable_policy,
)

_APPROVE_PATH = "/api/receipts/{receipt_table_id}/approve"
_CREATE_LINE_PATH = "/api/receipts/{receipt_table_id}/lines"


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
    store_provider_code: str = "",
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

    # Kassa may bypass Uitpakken when location assignment is unavailable.
    # "Direct" is not a physical stock location: ordinary STOCK lines must
    # enter inventory with real NULL/NULL location fields.
    target_location_id = None

    lines = conn.execute(
        text(
            """
            SELECT id, article_name_raw, matched_household_article_id,
                   matched_global_product_id, external_article_code, brand_raw,
                   quantity_raw, unit_raw, processing_status, processed_event_id
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

        if checked_stock_quantity(line.get("quantity_raw"), line.get("unit_raw")) <= 0:
            raise HTTPException(
                status_code=409,
                detail="Een kassabonartikel heeft geen betrouwbare hoeveelheid. Controleer de hoeveelheid in Kassa.",
            )
        article_id = resolve_stock_household_article(
            conn,
            main_module=main_module,
            household_id=normalized_household_id,
            line=line,
            store_provider_code=store_provider_code,
            allow_new_receipt_article=True,
        )
        if not article_id:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Een kassabonartikel kan niet met zekerheid aan Mijn artikel worden "
                    "gekoppeld. Controleer de artikelkoppeling in Kassa; er is niets "
                    "naar Voorraad geboekt."
                ),
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
                    suggested_location_id = NULL,
                    article_override_mode = 'auto',
                    location_override_mode = 'cleared',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :line_id
                  AND batch_id = :batch_id
                """
            ),
            {
                "article_id": str(article_id),
                "target_location_id": target_location_id,
                "line_id": line_id,
                "batch_id": normalized_batch_id,
            },
        )
        prepared_count += 1

    main_module.update_batch_status(conn, normalized_batch_id)
    return prepared_count


def _validate_direct_receipt_quantities(main_module, conn, receipt_table_id: str) -> None:
    """Use the shared stock quantity rule before approving a direct receipt.

    This check runs inside a read transaction BEFORE the legacy Kassa approval
    transaction, so an invalid receipt is neither approved nor auto-booked.
    Financial/non-stock lines are skipped using the canonical classifier.
    """
    receipt = conn.execute(
        text("SELECT store_name FROM receipt_tables WHERE id = :id LIMIT 1"),
        {"id": receipt_table_id},
    ).mappings().first()
    if not receipt:
        raise HTTPException(status_code=404, detail="Kassabon niet gevonden")
    lines = conn.execute(text("""
        SELECT * FROM receipt_table_lines
        WHERE receipt_table_id = :receipt_table_id
          AND COALESCE(is_deleted, FALSE) = FALSE
    """), {"receipt_table_id": receipt_table_id}).mappings().all()
    for line in lines:
        semantics = main_module.derive_receipt_line_semantics(
            dict(line), store_name=str(receipt.get("store_name") or ""),
        )
        if not semantics["inventory_eligible"]:
            continue
        quantity = line.get("corrected_quantity")
        unit = line.get("corrected_unit")
        if quantity is None:
            quantity = line.get("quantity")
        if not unit:
            unit = line.get("unit")
        if checked_stock_quantity(quantity, unit) <= 0:
            raise HTTPException(
                status_code=409,
                detail="Een kassabonartikel heeft geen betrouwbare hoeveelheid. Controleer de hoeveelheid in Kassa.",
            )


def _manual_receipt_line_id(result, article_name: str) -> str | None:
    normalized_name = " ".join(str(article_name or "").strip().split()).casefold()
    candidates = []
    for line in (result or {}).get("lines") or []:
        if bool(line.get("is_deleted")):
            continue
        display_name = " ".join(
            str(
                line.get("display_label")
                or line.get("corrected_raw_label")
                or line.get("raw_label")
                or ""
            ).strip().split()
        ).casefold()
        if display_name != normalized_name:
            continue
        candidates.append(line)
    if not candidates:
        return None
    newest = max(
        candidates,
        key=lambda line: (
            int(line.get("line_index") or 0),
            str(line.get("id") or ""),
        ),
    )
    return str(newest.get("id") or "").strip() or None


def _persist_manual_receipt_line_product_semantics(
    main_module,
    *,
    receipt_table_id: str,
    article_name: str,
    authorization: str | None,
    create_result,
):
    line_id = _manual_receipt_line_id(create_result, article_name)
    if not line_id:
        raise HTTPException(
            status_code=500,
            detail="Handmatig toegevoegde bonregel kon niet worden teruggevonden",
        )

    with main_module.engine.begin() as conn:
        main_module.require_receipt_write_context(
            conn,
            receipt_table_id,
            authorization,
        )
        updated = conn.execute(
            text(
                """
                UPDATE receipt_table_lines
                SET line_role = 'product',
                    inventory_eligible = 1,
                    corrected_unit = COALESCE(
                        NULLIF(BTRIM(corrected_unit), ''),
                        NULLIF(BTRIM(unit), ''),
                        'stuk'
                    ),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :line_id
                  AND receipt_table_id = :receipt_table_id
                  AND COALESCE(is_deleted, FALSE) = FALSE
                """
            ),
            {
                "line_id": line_id,
                "receipt_table_id": receipt_table_id,
            },
        )
        if int(updated.rowcount or 0) != 1:
            raise HTTPException(
                status_code=500,
                detail="Handmatig toegevoegde bonregel kon niet als voorraadproduct worden vastgelegd",
            )

    return main_module.get_receipt_detail(receipt_table_id, authorization)


def _patch_route(app, path: str, endpoint) -> bool:
    for route in app.routes:
        if (
            getattr(route, "path", None) == path
            and "POST" in (getattr(route, "methods", set()) or set())
        ):
            route.endpoint = endpoint
            if getattr(route, "dependant", None) is not None:
                route.dependant.call = endpoint
            return True
    return False


def install_receipt_direct_inventory_approval_patch(main_module) -> None:
    app = main_module.app
    install_temporary_all_articles_consumable_policy(main_module)
    if getattr(app.state, "receipt_direct_inventory_approval_patch_installed", False):
        return

    original_approve = main_module.approve_receipt_table
    original_create_line = main_module.create_receipt_line

    def create_receipt_line_with_product_semantics(
        receipt_table_id: str,
        payload,
        authorization: str | None = None,
    ):
        result = original_create_line(receipt_table_id, payload, authorization)
        return _persist_manual_receipt_line_product_semantics(
            main_module,
            receipt_table_id=receipt_table_id,
            article_name=getattr(payload, "article_name", ""),
            authorization=authorization,
            create_result=result,
        )

    def approve_receipt_table_with_direct_inventory(
        receipt_table_id: str,
        authorization: str | None = None,
    ):
        # A fully processed direct-inventory receipt is already approved. Re-running
        # the legacy receipt-to-batch synchronization is both unnecessary and can
        # disturb the canonical household-article identity established by the first
        # direct processing pass. Treat an identical second approval as a true no-op.
        already_processed_batch = None
        with main_module.engine.begin() as conn:
            receipt_state = conn.execute(
                text(
                    """
                    SELECT household_id, approved_at, approved_by_user_email
                    FROM receipt_tables
                    WHERE id = :receipt_table_id
                    LIMIT 1
                    """
                ),
                {"receipt_table_id": receipt_table_id},
            ).mappings().first()
            if receipt_state and receipt_state.get("approved_at") is not None:
                main_module.require_receipt_write_context(
                    conn,
                    receipt_table_id,
                    authorization,
                )
                household_id = str(receipt_state.get("household_id") or "").strip()
                try:
                    configuration = resolve_household_product_configuration(
                        conn,
                        household_id,
                    )
                except LookupError:
                    configuration = None

                if should_process_approved_receipt_directly_to_inventory(configuration):
                    batch = conn.execute(
                        text(
                            """
                            SELECT id, import_status
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
                    if batch:
                        line_counts = conn.execute(
                            text(
                                """
                                SELECT COUNT(*) AS total_count,
                                       SUM(
                                           CASE
                                               WHEN processing_status = 'processed' THEN 1
                                               ELSE 0
                                           END
                                       ) AS processed_count
                                FROM purchase_import_lines
                                WHERE batch_id = :batch_id
                                """
                            ),
                            {"batch_id": str(batch["id"])},
                        ).mappings().one()
                        total_count = int(line_counts.get("total_count") or 0)
                        processed_count = int(line_counts.get("processed_count") or 0)
                        if total_count > 0 and processed_count == total_count:
                            already_processed_batch = {
                                "batch_id": str(batch["id"]),
                                "status": str(batch.get("import_status") or "processed"),
                            }

        if already_processed_batch is not None:
            refreshed = main_module.get_receipt_detail(receipt_table_id, authorization)
            refreshed["approval_destination"] = "inventory"
            refreshed["inventory_processing"] = {
                "batch_id": already_processed_batch["batch_id"],
                "status": already_processed_batch["status"],
                "processed_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
            }
            return refreshed

        # Do not approve a direct receipt whose quantity is only a guessed
        # one-piece parser default. Uitpakken uses the same stock normalizer.
        with main_module.engine.begin() as conn:
            receipt_owner = conn.execute(text(
                "SELECT household_id FROM receipt_tables WHERE id = :id LIMIT 1"
            ), {"id": receipt_table_id}).mappings().first()
            if receipt_owner:
                main_module.require_receipt_write_context(
                    conn, receipt_table_id, authorization,
                )
                try:
                    direct_config = resolve_household_product_configuration(
                        conn, str(receipt_owner["household_id"]),
                    )
                except LookupError:
                    direct_config = None
                if should_process_approved_receipt_directly_to_inventory(direct_config):
                    _validate_direct_receipt_quantities(
                        main_module, conn, receipt_table_id,
                    )

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
                    SELECT pib.id AS id, sp.code AS store_provider_code
                    FROM purchase_import_batches pib
                    JOIN store_providers sp ON sp.id = pib.store_provider_id
                    WHERE pib.household_id = :household_id
                      AND pib.source_type = 'receipt'
                      AND pib.source_reference = :source_reference
                    ORDER BY pib.created_at DESC, pib.id DESC
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
                store_provider_code=str(batch.get("store_provider_code") or ""),
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

    main_module.create_receipt_line = create_receipt_line_with_product_semantics
    main_module.approve_receipt_table = approve_receipt_table_with_direct_inventory

    if not _patch_route(app, _CREATE_LINE_PATH, create_receipt_line_with_product_semantics):
        raise RuntimeError("Receipt create-line-route niet gevonden voor productsemantiekpatch")
    if not _patch_route(app, _APPROVE_PATH, approve_receipt_table_with_direct_inventory):
        raise RuntimeError("Receipt approve-route niet gevonden voor directe voorraadpatch")

    app.state.receipt_direct_inventory_approval_patch_installed = True

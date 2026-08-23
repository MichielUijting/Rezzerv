from __future__ import annotations

import json
import traceback
from contextvars import ContextVar
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text

from app.services.household_product_configuration_service import (
    resolve_household_product_configuration,
)
from app.services.inventory_location_policy_service import (
    LOCATION_NONE,
    resolve_inventory_target_location,
)

_PROCESS_PATH = "/api/purchase-import-batches/{batch_id}/process"
_processing_household_id: ContextVar[str | None] = ContextVar(
    "purchase_import_processing_household_id",
    default=None,
)


def classify_locationless_ready_line(line: Any) -> tuple[bool, str | None, str | None]:
    """Ready-only contract for a household that deliberately has no locations."""

    article_id = line.get("matched_household_article_id")
    matched_global_product_id = str(line.get("matched_global_product_id") or "").strip()
    article_group_id = line.get("selected_article_group_id")
    target_location_id = str(line.get("target_location_id") or "").strip()

    if not article_id and not matched_global_product_id:
        return False, "Nog geen artikel of product gekoppeld", "article_resolution"
    if not article_group_id:
        return False, "Nog geen artikelgroep gekozen", "article_group_resolution"
    if target_location_id:
        return (
            False,
            "Dit huishouden gebruikt voorraad zonder locatie; verwijder de gekozen locatie",
            "purchase_event_write",
        )
    return True, None, None


def _batch_household_configuration(main_module, batch_id: str):
    with main_module.engine.begin() as conn:
        household_id = conn.execute(
            text(
                """
                SELECT household_id
                FROM purchase_import_batches
                WHERE id = :batch_id
                LIMIT 1
                """
            ),
            {"batch_id": str(batch_id)},
        ).scalar()
        if not household_id:
            return None, None
        try:
            configuration = resolve_household_product_configuration(conn, str(household_id))
        except LookupError:
            return str(household_id), None
    return str(household_id), configuration


def _policy_store_storage_target_location(main_module, original_resolver, conn, target_location_id):
    household_id = _processing_household_id.get()
    if not household_id:
        return original_resolver(conn, target_location_id)
    try:
        return resolve_inventory_target_location(
            conn,
            household_id,
            target_location_id,
        )
    except HTTPException:
        # Preserve the legacy per-line failure contract: invalid locations resolve
        # to no usable storage target instead of aborting the complete batch.
        return None


def _process_locationless_ready_only_batch(
    main_module,
    batch_id: str,
    payload,
    authorization: str | None,
):
    m = main_module
    current_line_id = None
    current_line_name = None
    current_stage = "batch_start"

    try:
        with m.engine.begin() as conn:
            batch = conn.execute(
                text(
                    """
                    SELECT
                        pib.id,
                        pib.household_id,
                        pib.import_status,
                        pib.raw_payload,
                        sp.code AS store_provider_code
                    FROM purchase_import_batches pib
                    JOIN store_providers sp ON sp.id = pib.store_provider_id
                    WHERE pib.id = :id
                    """
                ),
                {"id": batch_id},
            ).mappings().first()
            if not batch:
                raise HTTPException(status_code=404, detail="Onbekende purchase import batch")

            context = m.require_household_context(authorization, str(batch["household_id"]))
            if str(context.get("display_role") or "").strip().lower() == "viewer":
                raise HTTPException(
                    status_code=403,
                    detail="Kijkers mogen kassabonnen wel opvoeren, maar niet naar voorraad verwerken",
                )

            configuration = resolve_household_product_configuration(
                conn,
                str(batch["household_id"]),
            )
            if configuration.location_tracking_level != LOCATION_NONE:
                raise RuntimeError(
                    "Locationless ready-only processor aangeroepen voor huishouden met locaties"
                )

            raw_payload: dict[str, Any] = {}
            try:
                raw_payload = json.loads(batch.get("raw_payload") or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                raw_payload = {}
            batch_metadata = raw_payload.get("batch_metadata")
            if not isinstance(batch_metadata, dict):
                batch_metadata = {}
            purchase_date = str(batch_metadata.get("purchase_date") or "").strip() or None

            lines = conn.execute(
                text(
                    """
                    SELECT id, external_line_ref, article_name_raw, brand_raw,
                           external_article_code, quantity_raw, unit_raw,
                           review_decision, matched_household_article_id,
                           matched_global_product_id,
                           COALESCE(
                               selected_article_group_id,
                               (
                                   SELECT ha.article_group_id
                                   FROM household_articles ha
                                   WHERE ha.id = purchase_import_lines.matched_household_article_id
                                     AND ha.household_id = :household_id
                                   LIMIT 1
                               )
                           ) AS selected_article_group_id,
                           target_location_id, processing_status, processed_event_id
                    FROM purchase_import_lines
                    WHERE batch_id = :batch_id
                    ORDER BY COALESCE(ui_sort_order, 999999), created_at ASC, id ASC
                    """
                ),
                {
                    "batch_id": batch_id,
                    "household_id": str(batch["household_id"]),
                },
            ).mappings().all()

            selected_lines = [
                line
                for line in lines
                if (line["review_decision"] or "pending") == "selected"
            ]
            results: list[dict[str, Any]] = []
            processable_lines = []
            skipped_count = 0

            for line in selected_lines:
                line_id = line["id"]
                current_line_id = line_id
                current_line_name = line.get("article_name_raw") or ""
                line_reference = m.build_purchase_import_line_reference(conn, line_id)
                ready, reason, failure_stage = classify_locationless_ready_line(line)
                if not ready:
                    results.append(
                        {
                            "line_id": line_id,
                            "line_reference": line_reference,
                            "status": "skipped",
                            "reason": reason,
                            "failure_stage": failure_stage,
                        }
                    )
                    skipped_count += 1
                    continue
                processable_lines.append(line)

            if not processable_lines:
                raise HTTPException(
                    status_code=400,
                    detail="Geen klaarstaande regels om naar voorraad te verwerken",
                )

            processed_count = 0
            failed_count = 0

            for line in processable_lines:
                line_id = line["id"]
                current_line_id = line_id
                current_line_name = line.get("article_name_raw") or ""
                line_reference = m.build_purchase_import_line_reference(conn, line_id)

                if line["processing_status"] == "processed" and line["processed_event_id"]:
                    results.append(
                        {
                            "line_id": line_id,
                            "line_reference": line_reference,
                            "status": "processed",
                            "event_id": line["processed_event_id"],
                            "message": "Al eerder verwerkt",
                        }
                    )
                    processed_count += 1
                    continue

                article_id = line["matched_household_article_id"]
                matched_global_product_id = str(
                    line.get("matched_global_product_id") or ""
                ).strip()
                if not article_id and matched_global_product_id:
                    article_id = m.ensure_household_article_for_global_product(
                        conn,
                        str(batch["household_id"]),
                        matched_global_product_id,
                        article_name_hint=line.get("article_name_raw"),
                        barcode=line.get("external_article_code"),
                        brand=line.get("brand_raw"),
                    )
                    if article_id:
                        conn.execute(
                            text(
                                """
                                UPDATE purchase_import_lines
                                SET matched_household_article_id = :matched_household_article_id,
                                    suggested_household_article_id = COALESCE(
                                        suggested_household_article_id,
                                        :matched_household_article_id
                                    ),
                                    match_status = 'matched',
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE id = :id
                                """
                            ),
                            {
                                "id": line_id,
                                "matched_household_article_id": article_id,
                            },
                        )

                if not str(line.get("external_line_ref") or "").strip().startswith(
                    "receipt-line:"
                ):
                    synced_links = m.sync_purchase_import_line_product_links(
                        conn,
                        line_id,
                        str(batch["household_id"]),
                    )
                    if synced_links:
                        article_id = (
                            synced_links.get("matched_household_article_id") or article_id
                        )
                        matched_global_product_id = (
                            synced_links.get("matched_global_product_id")
                            or matched_global_product_id
                        )

                selected_article_input = str(article_id or matched_global_product_id or "")
                original_article = (
                    m.resolve_review_article_option(
                        conn,
                        article_id,
                        str(batch["household_id"]),
                    )
                    if article_id
                    else None
                )
                article = m.resolve_processing_article(
                    conn,
                    str(batch["household_id"]),
                    original_article,
                )
                if article:
                    article_id = article["id"]
                if not article:
                    error = "Geen geldige artikelkoppeling gekozen"
                    diagnostic = m.build_purchase_import_line_diagnostic(
                        line=line,
                        batch=batch,
                        selected_article_input=selected_article_input,
                        original_article=original_article,
                        resolved_article=None,
                        resolved_location=None,
                        purchase_quantity=0,
                        pre_purchase_total=0,
                        purchase_event_created=False,
                        purchase_event_id=None,
                        history_contains_purchase_event=False,
                        history_lookup_article_id=selected_article_input,
                        history_lookup_result_count=0,
                        auto_consume_household_mode=m.get_household_auto_consume_mode(
                            conn, str(batch["household_id"])
                        ),
                        auto_consume_article_override=m.ARTICLE_AUTO_CONSUME_FOLLOW_HOUSEHOLD,
                        auto_consume_effective_mode=m.ARTICLE_AUTO_CONSUME_NONE,
                        auto_consume_should_apply=False,
                        auto_consume_decision_reason=error,
                        auto_consume_requested_deduction_quantity=0,
                        auto_consume_applied_deduction_quantity=0,
                        auto_consume_event_created=False,
                        auto_consume_event_id=None,
                        inventory_after_purchase_total=0,
                        inventory_after_auto_consume_total=0,
                        processing_status="failed",
                        failure_stage="article_resolution",
                        failure_message=error,
                    )
                    m.store_purchase_import_line_diagnostic(conn, line_id, diagnostic)
                    conn.execute(
                        text(
                            "UPDATE purchase_import_lines "
                            "SET processing_status = 'failed', processing_error = :error, "
                            "updated_at = CURRENT_TIMESTAMP WHERE id = :id"
                        ),
                        {"error": error, "id": line_id},
                    )
                    results.append(
                        {
                            "line_id": line_id,
                            "line_reference": line_reference,
                            "status": "failed",
                            "error": error,
                            "diagnostic": diagnostic,
                        }
                    )
                    failed_count += 1
                    continue

                resolved_location = resolve_inventory_target_location(
                    conn,
                    str(batch["household_id"]),
                    line["target_location_id"],
                )

                quantity = m.normalize_store_import_quantity(
                    line.get("quantity_raw"),
                    line.get("unit_raw"),
                )
                if quantity <= 0:
                    error = "Ongeldige hoeveelheid"
                    diagnostic = m.build_purchase_import_line_diagnostic(
                        line=line,
                        batch=batch,
                        selected_article_input=selected_article_input,
                        original_article=original_article,
                        resolved_article=article,
                        resolved_location=resolved_location,
                        purchase_quantity=0,
                        pre_purchase_total=0,
                        purchase_event_created=False,
                        purchase_event_id=None,
                        history_contains_purchase_event=False,
                        history_lookup_article_id=str(article_id),
                        history_lookup_result_count=0,
                        auto_consume_household_mode=m.get_household_auto_consume_mode(
                            conn, str(batch["household_id"])
                        ),
                        auto_consume_article_override=m.get_household_article_auto_consume_override(
                            conn,
                            str(batch["household_id"]),
                            str(article_id),
                        ),
                        auto_consume_effective_mode=m.ARTICLE_AUTO_CONSUME_NONE,
                        auto_consume_should_apply=False,
                        auto_consume_decision_reason=error,
                        auto_consume_requested_deduction_quantity=0,
                        auto_consume_applied_deduction_quantity=0,
                        auto_consume_event_created=False,
                        auto_consume_event_id=None,
                        inventory_after_purchase_total=0,
                        inventory_after_auto_consume_total=0,
                        processing_status="failed",
                        failure_stage="purchase_event_write",
                        failure_message=error,
                    )
                    m.store_purchase_import_line_diagnostic(conn, line_id, diagnostic)
                    conn.execute(
                        text(
                            "UPDATE purchase_import_lines "
                            "SET processing_status = 'failed', processing_error = :error, "
                            "updated_at = CURRENT_TIMESTAMP WHERE id = :id"
                        ),
                        {"error": error, "id": line_id},
                    )
                    results.append(
                        {
                            "line_id": line_id,
                            "line_reference": line_reference,
                            "status": "failed",
                            "error": error,
                            "diagnostic": diagnostic,
                        }
                    )
                    failed_count += 1
                    continue

                article_group_id = (
                    str(line.get("selected_article_group_id") or "").strip() or None
                )
                valid_article_group = conn.execute(
                    text(
                        """
                        SELECT id
                        FROM article_groups
                        WHERE id = :article_group_id
                          AND household_id = :household_id
                          AND COALESCE(status, 'active') = 'active'
                        LIMIT 1
                        """
                    ),
                    {
                        "article_group_id": article_group_id,
                        "household_id": str(batch["household_id"]),
                    },
                ).mappings().first()
                if article_group_id and not valid_article_group:
                    error = (
                        "De gekozen artikelgroep bestaat niet binnen het actieve huishouden"
                    )
                    conn.execute(
                        text(
                            "UPDATE purchase_import_lines "
                            "SET processing_status = 'failed', processing_error = :error, "
                            "updated_at = CURRENT_TIMESTAMP WHERE id = :id"
                        ),
                        {"error": error, "id": line_id},
                    )
                    results.append(
                        {
                            "line_id": line_id,
                            "line_reference": line_reference,
                            "status": "failed",
                            "error": error,
                        }
                    )
                    failed_count += 1
                    continue

                article_name = article["name"]
                note = m.build_store_import_note(
                    batch["store_provider_code"],
                    batch_id,
                    line_id,
                    line["article_name_raw"],
                )
                pre_purchase_total = m.get_inventory_total_by_household_article(
                    conn,
                    batch["household_id"],
                    str(article_id),
                )
                effective_inventory_handling = m.resolve_effective_line_inventory_handling(
                    conn,
                    household_id=str(batch["household_id"]),
                    household_article_id=str(article_id),
                    line_id=str(line_id),
                )

                if effective_inventory_handling == m.DAY_ARTICLE_DIRECT_CONSUMPTION:
                    current_stage = "direct_purchase_financial_event_write"
                    direct_purchase_event_id = m.create_inventory_purchase_event(
                        conn,
                        batch["household_id"],
                        article_id,
                        article_name,
                        quantity,
                        resolved_location,
                        note,
                        supplier_name=(
                            batch.get("store_name")
                            or batch.get("store_label")
                            or batch.get("store_provider_name")
                            or batch.get("store_provider_code")
                        ),
                        price=(
                            float(line.get("line_price_raw"))
                            if line.get("line_price_raw") is not None
                            else None
                        ),
                        currency=line.get("currency_code") or "EUR",
                        purchase_date=purchase_date,
                        article_number=line.get("external_article_code"),
                        barcode=line.get("barcode") or None,
                    )
                    direct_actor_context = m.require_household_context(
                        authorization,
                        str(batch["household_id"]),
                    )
                    direct_result = m.process_direct_purchase_import_line(
                        conn,
                        household_id=str(batch["household_id"]),
                        household_article_id=str(article_id),
                        line_id=str(line_id),
                        quantity=quantity,
                        actor_user_id=str(
                            direct_actor_context.get("user_id")
                            or payload.processed_by
                            or "ui"
                        ),
                    )
                    removed_direct_inventory_rows = m.remove_direct_inventory_artifacts(
                        conn,
                        household_id=str(batch["household_id"]),
                        household_article_id=str(article_id),
                    )
                    m.sync_household_article_price_metrics(
                        conn,
                        batch["household_id"],
                        article_id,
                        m.ensure_household_article_global_product_link(
                            conn,
                            article_id,
                            line.get("barcode") or None,
                        ),
                    )
                    conn.execute(
                        text(
                            """
                            UPDATE purchase_import_lines
                            SET processing_status = 'processed',
                                processed_at = CURRENT_TIMESTAMP,
                                processed_event_id = :event_id,
                                processing_error = NULL,
                                final_location_id = :final_location_id,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = :id
                            """
                        ),
                        {
                            "event_id": direct_purchase_event_id,
                            "final_location_id": resolved_location["location_id"],
                            "id": line_id,
                        },
                    )
                    conn.execute(
                        text(
                            """
                            UPDATE household_articles
                            SET article_group_id = :article_group_id,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = :article_id
                              AND household_id = :household_id
                            """
                        ),
                        {
                            "article_group_id": article_group_id,
                            "article_id": str(article_id),
                            "household_id": str(batch["household_id"]),
                        },
                    )
                    results.append(
                        {
                            "line_id": line_id,
                            "line_reference": line_reference,
                            "status": "processed",
                            "event_id": direct_purchase_event_id,
                            "financial_purchase_registered": True,
                            "inventory_mutation_skipped": True,
                            "removed_direct_inventory_rows": removed_direct_inventory_rows,
                            "direct_consumption": direct_result,
                            "message": (
                                "Aankoop financieel geregistreerd en direct verbruikt; "
                                "bestaande voorraad ongewijzigd"
                            ),
                        }
                    )
                    processed_count += 1
                    continue

                auto_consume_decision = m.determine_auto_consume_decision(
                    conn,
                    str(batch["household_id"]),
                    str(article_id),
                    article_name,
                    pre_purchase_total,
                    quantity,
                )
                household_mode = auto_consume_decision["household_mode"]
                article_override = auto_consume_decision["article_override"]
                effective_mode = auto_consume_decision["effective_mode"]
                decision_reason = auto_consume_decision["decision_reason"]
                should_auto_consume = auto_consume_decision["should_auto_consume"]
                requested_deduction_quantity = auto_consume_decision[
                    "requested_deduction_quantity"
                ]
                current_stage = "purchase_event_write"
                event_id = None
                auto_event_id = None
                inventory_after_purchase_total = pre_purchase_total
                inventory_after_auto_consume_total = pre_purchase_total
                history_lookup_result_count = 0
                history_contains_purchase_event = False
                applied_deduction_quantity = 0

                try:
                    event_id = m.create_inventory_purchase_event(
                        conn,
                        batch["household_id"],
                        article_id,
                        article_name,
                        quantity,
                        resolved_location,
                        note,
                        supplier_name=(
                            batch.get("store_name")
                            or batch.get("store_label")
                            or batch.get("store_provider_name")
                            or batch.get("store_provider_code")
                        ),
                        price=(
                            float(line.get("line_price_raw"))
                            if line.get("line_price_raw") is not None
                            else None
                        ),
                        currency=line.get("currency_code") or "EUR",
                        purchase_date=purchase_date,
                        article_number=line.get("external_article_code"),
                        barcode=line.get("barcode") or None,
                    )
                    purchase_inventory_id = m.apply_inventory_purchase_by_identity(
                        conn,
                        household_id=str(batch["household_id"]),
                        household_article_id=str(article_id),
                        quantity=quantity,
                        space_id=resolved_location.get("space_id"),
                        sublocation_id=resolved_location.get("sublocation_id"),
                    )
                    m.sync_household_article_price_metrics(
                        conn,
                        batch["household_id"],
                        article_id,
                        m.ensure_household_article_global_product_link(
                            conn,
                            article_id,
                            line.get("barcode") or None,
                        ),
                    )
                    inventory_after_purchase_total = (
                        m.get_inventory_total_by_household_article(
                            conn,
                            batch["household_id"],
                            str(article_id),
                        )
                    )
                    current_stage = "history_lookup"
                    (
                        history_lookup_result_count,
                        history_contains_purchase_event,
                    ) = m.count_history_events_for_article(
                        conn,
                        str(batch["household_id"]),
                        str(article_id),
                        event_id,
                    )
                    current_stage = "auto_consume_decision"
                    if should_auto_consume:
                        current_stage = "auto_consume_write"
                        auto_event_id = m.create_auto_repurchase_event(
                            conn,
                            batch["household_id"],
                            article_id,
                            article_name,
                            resolved_location,
                            quantity=requested_deduction_quantity,
                            purchase_date=purchase_date,
                        )
                        consumption_result = m.apply_inventory_consumption(
                            conn,
                            batch["household_id"],
                            article_name,
                            requested_deduction_quantity,
                            resolved_location,
                            household_article_id=str(article_id),
                            mode=effective_mode,
                            protected_quantity_on_purchase_row=int(quantity),
                            protected_purchase_inventory_id=purchase_inventory_id,
                        )
                        applied_deduction_quantity = int(
                            consumption_result.get("applied_quantity") or 0
                        )
                    inventory_after_auto_consume_total = (
                        m.get_inventory_total_by_household_article(
                            conn,
                            batch["household_id"],
                            str(article_id),
                        )
                    )
                except Exception as exc:
                    detail_parts = [
                        f"exception_type={exc.__class__.__name__}",
                        f"exception_message={str(exc) or exc.__class__.__name__}",
                        f"article_id={article_id}",
                        f"article_name={article_name}",
                        f"quantity={quantity}",
                        f"location_id={resolved_location.get('location_id') if resolved_location else None}",
                        f"location_label={resolved_location.get('location_label') if resolved_location else None}",
                    ]
                    error = " | ".join(detail_parts)
                    diagnostic = m.build_purchase_import_line_diagnostic(
                        line=line,
                        batch=batch,
                        selected_article_input=selected_article_input,
                        original_article=original_article,
                        resolved_article=article,
                        resolved_location=resolved_location,
                        purchase_quantity=int(quantity),
                        pre_purchase_total=int(pre_purchase_total),
                        purchase_event_created=bool(event_id),
                        purchase_event_id=event_id,
                        history_contains_purchase_event=history_contains_purchase_event,
                        history_lookup_article_id=str(article_id),
                        history_lookup_result_count=history_lookup_result_count,
                        auto_consume_household_mode=household_mode,
                        auto_consume_article_override=article_override,
                        auto_consume_effective_mode=effective_mode,
                        auto_consume_should_apply=should_auto_consume,
                        auto_consume_decision_reason=decision_reason,
                        auto_consume_requested_deduction_quantity=requested_deduction_quantity,
                        auto_consume_applied_deduction_quantity=(
                            applied_deduction_quantity if auto_event_id else 0
                        ),
                        auto_consume_event_created=bool(auto_event_id),
                        auto_consume_event_id=auto_event_id,
                        inventory_after_purchase_total=int(
                            inventory_after_purchase_total
                        ),
                        inventory_after_auto_consume_total=int(
                            inventory_after_auto_consume_total
                        ),
                        processing_status="failed",
                        failure_stage=current_stage,
                        failure_message=error,
                    )
                    diagnostic["backend_trace_excerpt"] = traceback.format_exc(limit=2)
                    m.store_purchase_import_line_diagnostic(conn, line_id, diagnostic)
                    conn.execute(
                        text(
                            "UPDATE purchase_import_lines "
                            "SET processing_status = 'failed', processing_error = :error, "
                            "updated_at = CURRENT_TIMESTAMP WHERE id = :id"
                        ),
                        {"error": error, "id": line_id},
                    )
                    results.append(
                        {
                            "line_id": line_id,
                            "line_reference": line_reference,
                            "status": "failed",
                            "error": error,
                            "diagnostic": diagnostic,
                        }
                    )
                    failed_count += 1
                    continue

                diagnostic = m.build_purchase_import_line_diagnostic(
                    line=line,
                    batch=batch,
                    selected_article_input=selected_article_input,
                    original_article=original_article,
                    resolved_article=article,
                    resolved_location=resolved_location,
                    purchase_quantity=int(quantity),
                    pre_purchase_total=int(pre_purchase_total),
                    purchase_event_created=bool(event_id),
                    purchase_event_id=event_id,
                    history_contains_purchase_event=history_contains_purchase_event,
                    history_lookup_article_id=str(article_id),
                    history_lookup_result_count=history_lookup_result_count,
                    auto_consume_household_mode=household_mode,
                    auto_consume_article_override=article_override,
                    auto_consume_effective_mode=effective_mode,
                    auto_consume_should_apply=should_auto_consume,
                    auto_consume_decision_reason=decision_reason,
                    auto_consume_requested_deduction_quantity=requested_deduction_quantity,
                    auto_consume_applied_deduction_quantity=(
                        applied_deduction_quantity if auto_event_id else 0
                    ),
                    auto_consume_event_created=bool(auto_event_id),
                    auto_consume_event_id=auto_event_id,
                    inventory_after_purchase_total=int(inventory_after_purchase_total),
                    inventory_after_auto_consume_total=int(
                        inventory_after_auto_consume_total
                    ),
                    processing_status="processed",
                    failure_stage="none",
                    failure_message="",
                )
                m.store_purchase_import_line_diagnostic(conn, line_id, diagnostic)
                conn.execute(
                    text(
                        """
                        UPDATE purchase_import_lines
                        SET processing_status = 'processed',
                            processed_at = CURRENT_TIMESTAMP,
                            processed_event_id = :event_id,
                            processing_error = NULL,
                            final_location_id = :final_location_id,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                        """
                    ),
                    {
                        "event_id": event_id,
                        "final_location_id": resolved_location["location_id"],
                        "id": line_id,
                    },
                )
                conn.execute(
                    text(
                        """
                        UPDATE household_articles
                        SET article_group_id = :article_group_id,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :article_id
                          AND household_id = :household_id
                        """
                    ),
                    {
                        "article_group_id": article_group_id,
                        "article_id": str(article_id),
                        "household_id": str(batch["household_id"]),
                    },
                )
                m.remember_store_import_choice(
                    conn,
                    str(batch["household_id"]),
                    batch["store_provider_code"],
                    line["article_name_raw"],
                    line.get("brand_raw"),
                    article_id,
                    resolved_location["location_id"],
                )
                results.append(
                    {
                        "line_id": line_id,
                        "status": "processed",
                        "event_id": event_id,
                        "auto_event_id": auto_event_id,
                        "diagnostic": diagnostic,
                    }
                )
                processed_count += 1

            batch_status = m.update_batch_status(conn, batch_id)
            if batch_status in {"processed", "partially_processed"}:
                conn.execute(
                    text(
                        "UPDATE purchase_import_batches "
                        "SET processed_at = CURRENT_TIMESTAMP WHERE id = :id"
                    ),
                    {"id": batch_id},
                )
            diagnostics = m.build_purchase_import_batch_diagnostics(conn, batch_id)

        return {
            "batch_id": batch_id,
            "status": batch_status,
            "processed_count": processed_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "results": results,
            "diagnostics": diagnostics,
        }
    except HTTPException:
        raise
    except Exception as exc:
        detail = (
            "Verwerking naar voorraad mislukt bij regel "
            f"'{current_line_name or current_line_id or '?'}' op stap {current_stage}: "
            f"{exc.__class__.__name__}: {str(exc) or exc.__class__.__name__}"
        )
        m.logger.exception(
            "Procesfout locationless batch %s regel %s",
            batch_id,
            current_line_id,
        )
        raise HTTPException(status_code=500, detail=detail)


def install_purchase_import_location_policy_patch(main_module) -> None:
    app = main_module.app
    if getattr(app.state, "purchase_import_location_policy_patch_installed", False):
        return

    original_resolver = main_module.resolve_store_storage_target_location
    original_endpoint = main_module.process_purchase_import_batch

    def policy_store_storage_target_location(conn, target_location_id):
        return _policy_store_storage_target_location(
            main_module,
            original_resolver,
            conn,
            target_location_id,
        )

    def process_purchase_import_batch_with_location_policy(
        batch_id: str,
        payload,
        authorization: str | None = None,
    ):
        household_id, configuration = _batch_household_configuration(
            main_module,
            batch_id,
        )
        if not household_id or configuration is None:
            return original_endpoint(batch_id, payload, authorization)

        token = _processing_household_id.set(household_id)
        try:
            if (
                payload.mode == "ready_only"
                and configuration.location_tracking_level == LOCATION_NONE
            ):
                return _process_locationless_ready_only_batch(
                    main_module,
                    batch_id,
                    payload,
                    authorization,
                )
            return original_endpoint(batch_id, payload, authorization)
        finally:
            _processing_household_id.reset(token)

    main_module.resolve_store_storage_target_location = (
        policy_store_storage_target_location
    )
    main_module.process_purchase_import_batch = (
        process_purchase_import_batch_with_location_policy
    )

    patched_route = False
    for route in app.routes:
        if (
            getattr(route, "path", None) == _PROCESS_PATH
            and "POST" in (getattr(route, "methods", set()) or set())
        ):
            route.endpoint = process_purchase_import_batch_with_location_policy
            if getattr(route, "dependant", None) is not None:
                route.dependant.call = process_purchase_import_batch_with_location_policy
            patched_route = True
            break
    if not patched_route:
        raise RuntimeError("Purchase-import processroute niet gevonden voor locatiepolicy")

    app.state.purchase_import_location_policy_patch_installed = True

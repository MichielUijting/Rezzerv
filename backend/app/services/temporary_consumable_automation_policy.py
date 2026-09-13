from __future__ import annotations


def resolve_auto_consume_effective_mode_all_articles(
    main_module,
    household_mode: str,
    article_override: str,
    _consumable: bool,
) -> str:
    """Temporarily let every article participate in household auto-consume.

    Stored/catalog consumable data stays untouched. This policy only affects the
    household-automation decision until Catalogus becomes the canonical authority
    for consumable classification. See GitHub issue #427.
    """
    effective_mode = household_mode
    if article_override == main_module.ARTICLE_AUTO_CONSUME_PURCHASED_QUANTITY:
        effective_mode = main_module.ARTICLE_AUTO_CONSUME_PURCHASED_QUANTITY
    elif article_override == main_module.ARTICLE_AUTO_CONSUME_ALL_EXISTING:
        effective_mode = main_module.ARTICLE_AUTO_CONSUME_ALL_EXISTING
    elif article_override == main_module.ARTICLE_AUTO_CONSUME_NONE:
        effective_mode = main_module.ARTICLE_AUTO_CONSUME_NONE

    return (
        effective_mode
        if effective_mode in main_module.HOUSEHOLD_AUTO_CONSUME_ALLOWED
        else main_module.ARTICLE_AUTO_CONSUME_NONE
    )


def install_temporary_all_articles_consumable_policy(main_module) -> None:
    app = main_module.app
    if getattr(app.state, "temporary_all_articles_consumable_policy_installed", False):
        return

    original_apply_inventory_consumption = main_module.apply_inventory_consumption

    def resolve_auto_consume_effective_mode(
        household_mode: str,
        article_override: str,
        consumable: bool,
    ) -> str:
        return resolve_auto_consume_effective_mode_all_articles(
            main_module,
            household_mode,
            article_override,
            consumable,
        )

    def apply_inventory_consumption_postgresql_safe(
        conn,
        household_id: str,
        article_name: str,
        quantity: float,
        resolved_location: dict,
        *,
        household_article_id: str | None = None,
        mode: str | None = None,
        protected_quantity_on_purchase_row: int = 0,
        protected_purchase_inventory_id: str | None = None,
    ):
        normalized_mode = main_module.normalize_household_auto_consume_mode(mode)
        if normalized_mode != main_module.ARTICLE_AUTO_CONSUME_ALL_EXISTING:
            return original_apply_inventory_consumption(
                conn,
                household_id,
                article_name,
                quantity,
                resolved_location,
                household_article_id=household_article_id,
                mode=mode,
                protected_quantity_on_purchase_row=protected_quantity_on_purchase_row,
                protected_purchase_inventory_id=protected_purchase_inventory_id,
            )

        normalized_household_article_id = str(household_article_id or "").strip()
        if not normalized_household_article_id:
            raise main_module.HTTPException(
                status_code=400,
                detail="household_article_id is verplicht voor voorraadverbruik",
            )
        main_module.require_resolved_location(resolved_location)
        quantity_int = int(quantity)
        if quantity_int <= 0:
            return {"applied_quantity": 0, "affected_inventory_ids": []}

        protected_quantity_int = max(0, int(protected_quantity_on_purchase_row or 0))
        rows = conn.execute(
            main_module.text(
                """
                SELECT id, aantal,
                       CASE
                         WHEN id = :protected_purchase_inventory_id
                         THEN 1 ELSE 0
                       END AS is_purchase_row
                FROM inventory
                WHERE household_id = :household_id
                  AND household_article_id = :household_article_id
                ORDER BY is_purchase_row ASC, aantal ASC, id ASC
                """
            ),
            {
                "household_id": household_id,
                "household_article_id": normalized_household_article_id,
                "protected_purchase_inventory_id": (
                    str(protected_purchase_inventory_id)
                    if protected_purchase_inventory_id
                    else None
                ),
            },
        ).mappings().all()

        remaining_to_consume = quantity_int
        affected_ids = []
        for row in rows:
            if remaining_to_consume <= 0:
                break
            current_quantity = int(row["aantal"] or 0)
            if current_quantity <= 0:
                continue
            protected_for_row = protected_quantity_int if bool(row["is_purchase_row"]) else 0
            available_to_consume = max(0, current_quantity - protected_for_row)
            if available_to_consume <= 0:
                continue
            consume_here = min(available_to_consume, remaining_to_consume)
            new_row_quantity = current_quantity - consume_here
            if new_row_quantity > 0:
                conn.execute(
                    main_module.text(
                        """
                        UPDATE inventory
                        SET aantal = :aantal, updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                        """
                    ),
                    {"aantal": new_row_quantity, "id": row["id"]},
                )
            else:
                conn.execute(
                    main_module.text("DELETE FROM inventory WHERE id = :id"),
                    {"id": row["id"]},
                )
            remaining_to_consume -= consume_here
            affected_ids.append(row["id"])

        return {
            "applied_quantity": quantity_int - remaining_to_consume,
            "affected_inventory_ids": affected_ids,
        }

    # Intentional temporary product policy. Do not rewrite household_articles data.
    # The all-existing branch above mirrors the current main.py behavior but removes
    # the redundant `:parameter IS NOT NULL` predicate. PostgreSQL 17 cannot infer a
    # bind type from that predicate; `id = :parameter` is semantically equivalent
    # here and supplies the required type context even when the value is NULL.
    # Remove this installer when issue #427 introduces Catalogus as authority.
    main_module.resolve_auto_consume_effective_mode = resolve_auto_consume_effective_mode
    main_module.apply_inventory_consumption = apply_inventory_consumption_postgresql_safe
    app.state.temporary_all_articles_consumable_policy_installed = True

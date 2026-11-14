"""Household-scoped, confirmed Catalogus synonym-group repurchase deduction.

A group is derived from confirmed links and verified identity, never names. All
reads/writes run inside the caller's receipt transaction. No schema mutation.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.services.product_day_auto_consume_service import (
    AUTO_CONSUME_NONE,
    AUTO_CONSUME_ALL_EXISTING,
    AUTO_CONSUME_PURCHASED_QUANTITY,
    _canonical_purchase_day,
)
from app.services.synonym_auto_consume_identity import confirmed_household_synonym_group
from app.services.synonym_product_family_rules import normalized_package_quantity


def _whole(value) -> int:
    number = Decimal(str(value or 0))
    if not number.is_finite() or number < 0 or number != number.to_integral_value():
        raise ValueError("Synoniemvoorraad heeft een ongeldig of gebroken aantal")
    return int(number)


def _verified_household_package_factors(conn, household_id, article_ids):
    """Return exact common-dimension package sizes, or fail closed.

    A confirmed synonym edge proves product equivalence, not a numeric quantity
    conversion. Pack sizes must be verified in Catalogus for each private
    household member; missing/incompatible sizes cannot share deductions.
    """
    members = conn.execute(text("""
        SELECT ha.id AS article_id, gp.size_value, gp.size_unit,
               gp.status AS product_status
        FROM household_articles ha
        JOIN global_products gp ON gp.id = ha.global_product_id
        WHERE ha.household_id = :household_id
          AND ha.id = ANY(:article_ids)
          AND COALESCE(ha.status, 'active') = 'active'
    """), {"household_id": household_id, "article_ids": list(article_ids)}).mappings().all()
    if len(members) != len(article_ids):
        return None
    sizes = {}
    dimension = None
    for member in members:
        article_id = str(member["article_id"])
        if article_id in sizes or str(member.get("product_status") or "").lower() != "active":
            return None
        size = normalized_package_quantity(member)
        if size is None or (dimension is not None and size[0] != dimension):
            return None
        dimension = size[0]
        sizes[article_id] = size[1]
    if set(sizes) != set(article_ids):
        return None
    if max(sizes.values()) / min(sizes.values()) > Decimal("1000"):
        return None
    return dimension, sizes


def plan_confirmed_synonym_deduction(
    conn,
    *,
    household_id: str,
    purchased_article_id: str,
    purchase_date: str | None,
    purchased_quantity: int,
    household_mode: str,
    effective_mode_for_article,
) -> dict | None:
    """Plan the whole confirmed component; None means legacy single-article flow.

    Does not write. The caller must keep the transaction open until the returned
    plan has been applied. A household mode of 'none' never deducts anything.
    """
    if household_mode == AUTO_CONSUME_NONE:
        return None
    day = _canonical_purchase_day(purchase_date)
    if day is None or _whole(purchased_quantity) == 0:
        return None
    household_id = str(household_id)
    purchased_article_id = str(purchased_article_id)
    group = confirmed_household_synonym_group(conn, household_id, purchased_article_id)
    if len(group) < 2 or purchased_article_id not in group:
        return None
    verified = _verified_household_package_factors(conn, household_id, group)
    if verified is None:
        return None  # Never consume a differently sized package as one unit.
    dimension, package_sizes = verified

    # Both article rows are locked in deterministic order before any group read.
    # The purchase route already owns the containing transaction.
    member_rows = []
    for article_id in sorted(group):
        row = conn.execute(text("""
            SELECT id, naam, default_inventory_handling
            FROM household_articles
            WHERE household_id=:household_id AND id=:article_id
              AND COALESCE(status,'active')='active'
            FOR UPDATE
        """), {'household_id': household_id, 'article_id': article_id}).mappings().first()
        if row is None:
            return None
        # Direct-consumption articles must never become a source of stock.
        if str(row.get('default_inventory_handling') or '').upper() == 'DIRECT_CONSUMPTION':
            return None
        member_rows.append(dict(row))

    modes = [effective_mode_for_article(row['id'], row['naam']) for row in member_rows]
    if len(set(modes)) != 1 or modes[0] not in (
        AUTO_CONSUME_PURCHASED_QUANTITY, AUTO_CONSUME_ALL_EXISTING
    ):
        return None
    mode = modes[0]

    # A group is not retroactively rewritten when a newer-dated receipt has
    # already been processed: keep the well-tested single-article fallback.
    recent = conn.execute(text("""
        SELECT MAX(substr(CAST(purchase_date AS TEXT),1,10))
        FROM inventory_events
        WHERE household_id=:household_id
          AND household_article_id = ANY(:article_ids)
          AND event_type='purchase' AND source='store_import'
    """), {'household_id': household_id, 'article_ids': list(group)}).scalar()
    if recent and str(recent) > day:
        return None

    pre = {}
    prior_purchased = {}
    prior_deducted = {}
    stock_rows = {}
    for row in member_rows:
        article_id = str(row['id'])
        # Lock the exact stock rows, including their locations, while planning.
        # No name-based or cross-household inventory read is permitted.
        positions = conn.execute(text("""
            SELECT id, aantal, space_id, sublocation_id
            FROM inventory
            WHERE household_id=:household_id
              AND household_article_id=:article_id
              AND COALESCE(status,'active')='active'
            ORDER BY id ASC FOR UPDATE
        """), {'household_id': household_id, 'article_id': article_id}).mappings().all()
        stock_rows[article_id] = [dict(position) for position in positions]
        pre[article_id] = sum(_whole(position['aantal']) for position in positions)
        events = conn.execute(text("""
            SELECT event_type, source, quantity, location_id
            FROM inventory_events
            WHERE household_id=:household_id AND household_article_id=:article_id
              AND substr(trim(COALESCE(CAST(purchase_date AS TEXT),'')),1,10)=:day
              AND ((event_type='purchase' AND source='store_import')
                   OR (event_type='auto_repurchase' AND source='auto_repurchase'))
        """), {'household_id': household_id, 'article_id': article_id, 'day': day}).mappings().all()
        prior_purchased[article_id] = sum(
            _whole(e['quantity']) for e in events if e['event_type'] == 'purchase'
        )
        prior_deducted[article_id] = sum(
            _whole(abs(Decimal(str(e['quantity'] or 0))))
            for e in events if e['event_type'] == 'auto_repurchase'
        )
        # Reserve same-day purchases *at their actual locations*. When an
        # earlier direct-consumption receipt produced no stock or legacy
        # locations are ambiguous, return to the safe existing single-item
        # path instead of accidentally deducting fresh inventory.
        protected_by_location = {}
        for event in events:
            if event['event_type'] != 'purchase':
                continue
            key = str(event.get('location_id') or '')
            protected_by_location[key] = (
                protected_by_location.get(key, 0) + _whole(event['quantity'])
            )
        observed_locations = set()
        for position in stock_rows[article_id]:
            key = str(position.get('sublocation_id') or position.get('space_id') or '')
            if key in observed_locations:
                return None  # ambiguous old/new stock split at this location
            observed_locations.add(key)
            protected = protected_by_location.get(key, 0)
            if protected > _whole(position['aantal']):
                return None
            position['available_old'] = _whole(position['aantal']) - protected
        if any(key not in observed_locations for key in protected_by_location):
            return None

    # Aggregate in one exact common content unit (g/ml/pieces), not in
    # package counts: 2 x 500 ml must equal 1 x 1 l for deduction planning.
    total_pre = sum((pre[aid] * package_sizes[aid] for aid in group), Decimal(0))
    total_prior_purchases = sum((
        prior_purchased[aid] * package_sizes[aid] for aid in group
    ), Decimal(0))
    total_prior_deductions = sum((
        prior_deducted[aid] * package_sizes[aid] for aid in group
    ), Decimal(0))
    start_stock = total_pre - total_prior_purchases + total_prior_deductions
    if start_stock < 0:
        return None
    cumulative = (total_prior_purchases +
                  _whole(purchased_quantity) * package_sizes[purchased_article_id])
    if mode == AUTO_CONSUME_ALL_EXISTING:
        desired = start_stock
    else:
        desired = min(start_stock, cumulative)
    requested_equivalent = max(Decimal(0), desired - total_prior_deductions)
    old_stock_equivalent = sum((
        position['available_old'] * package_sizes[article_id]
        for article_id, positions in stock_rows.items() for position in positions
    ), Decimal(0))
    requested_equivalent = min(requested_equivalent, old_stock_equivalent)

    order = [article_id for article_id in group if article_id != purchased_article_id]
    order.append(purchased_article_id)
    allocations = []
    remaining = requested_equivalent
    for article_id in order:
        package = package_sizes[article_id]
        for position in stock_rows[article_id]:
            # Only whole packages can be deducted. Leave leftover capacity
            # unconsumed instead of rounding up and deleting fresh stock.
            quantity = min(position['available_old'], int(remaining // package))
            if not quantity:
                continue
            allocations.append({
                'article_id': article_id,
                'article_name': next(row['naam'] for row in member_rows
                                     if row['id'] == article_id),
                'inventory_id': str(position['id']),
                'pre_quantity': _whole(position['aantal']),
                'space_id': position.get('space_id'),
                'sublocation_id': position.get('sublocation_id'),
                'quantity': quantity,
            })
            remaining -= quantity * package
            if remaining <= 0:
                break
    requested = sum(item['quantity'] for item in allocations)
    return {
        'mode': mode,
        'members': tuple(group),
        'purchase_day': day,
        'requested_deduction_quantity': requested,
        'allocations': allocations,
        'day_start_stock': float(start_stock),
        'prior_day_purchased_quantity': float(total_prior_purchases),
        'prior_day_auto_consumed_quantity': float(total_prior_deductions),
        'cumulative_day_purchased_quantity': float(cumulative),
        'content_unit': dimension,
        'requested_equivalent_content': float(requested_equivalent - remaining),
    }


def apply_confirmed_synonym_deduction(
    conn,
    *,
    household_id: str,
    purchased_article_id: str,
    purchased_quantity: int,
    purchase_inventory_id: str,
    resolved_location: dict,
    plan: dict,
    create_auto_event,
) -> dict:
    """Deduct exact old stock rows at their own location; create matching events.

    This is run after the purchase within the same receipt transaction. All
    failures must roll back that transaction, including newly written events.
    A purchased unit never enters a pre-purchase allocation.
    """
    event_ids = []
    applied = 0
    for item in plan['allocations']:
        article_id = str(item['article_id'])
        inventory_id = str(item['inventory_id'])
        quantity = _whole(item['quantity'])
        row = conn.execute(text("""
            SELECT id, aantal, space_id, sublocation_id
            FROM inventory
            WHERE id=:inventory_id AND household_id=:household_id
              AND household_article_id=:article_id
              AND COALESCE(status,'active')='active'
            FOR UPDATE
        """), {
            'inventory_id': inventory_id,
            'household_id': str(household_id),
            'article_id': article_id,
        }).mappings().first()
        if not row:
            raise RuntimeError('Synoniemafboeking: verwachte voorraadregel ontbreekt')
        if (row['space_id'] != item['space_id']
                or row['sublocation_id'] != item['sublocation_id']):
            raise RuntimeError('Synoniemafboeking: voorraadlocatie gewijzigd')
        now = _whole(row['aantal'])
        if now < _whole(item['pre_quantity']) or now < quantity:
            raise RuntimeError('Synoniemafboeking: beschermde voorraad gewijzigd')
        # The newly bought quantity may only have increased its own purchase
        # row; no prepared deduction exceeds the old available quantity.
        location = {
            'space_id': row['space_id'],
            'sublocation_id': row['sublocation_id'],
            'location_id': row['sublocation_id'] or row['space_id'],
            'location_label': '',
        }
        event_id = create_auto_event(
            conn, household_id, article_id, item['article_name'],
            location, quantity=quantity, purchase_date=plan['purchase_day'],
        )
        if not event_id:
            raise RuntimeError('Synoniemafboeking: mutatiebewijs ontbreekt')
        after = now - quantity
        params = {
            'inventory_id': inventory_id,
            'household_id': str(household_id),
            'article_id': article_id,
            'before': now,
            'after': after,
        }
        if after:
            write = conn.execute(text("""
                UPDATE inventory SET aantal=:after, updated_at=CURRENT_TIMESTAMP
                WHERE id=:inventory_id AND household_id=:household_id
                  AND household_article_id=:article_id
                  AND aantal=:before AND COALESCE(status,'active')='active'
            """), params)
        else:
            write = conn.execute(text("""
                DELETE FROM inventory
                WHERE id=:inventory_id AND household_id=:household_id
                  AND household_article_id=:article_id
                  AND aantal=:before AND COALESCE(status,'active')='active'
            """), params)
        if int(write.rowcount or 0) != 1:
            raise RuntimeError('Synoniemafboeking: voorraadmutatie niet atomair bevestigd')
        event_ids.append(event_id)
        applied += quantity
    if applied != plan['requested_deduction_quantity']:
        raise RuntimeError('Synoniemafboeking: afboeksom is niet volledig verwerkt')
    return {'applied_quantity': applied, 'event_ids': event_ids}

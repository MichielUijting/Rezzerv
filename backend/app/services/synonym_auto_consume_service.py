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


def _whole(value) -> int:
    number = Decimal(str(value or 0))
    if not number.is_finite() or number < 0 or number != number.to_integral_value():
        raise ValueError("Synoniemvoorraad heeft een ongeldig of gebroken aantal")
    return int(number)


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

    total_pre = sum(pre.values())
    total_prior_purchases = sum(prior_purchased.values())
    total_prior_deductions = sum(prior_deducted.values())
    # Today's preceding receipts are added back/removed to recover the
    # start-of-day baseline even when other shops sell different group members.
    start_stock = total_pre - total_prior_purchases + total_prior_deductions
    if start_stock < 0:
        return None  # stock ledger cannot safely establish the baseline
    cumulative = total_prior_purchases + _whole(purchased_quantity)
    if mode == AUTO_CONSUME_ALL_EXISTING:
        desired = start_stock
    else:
        desired = min(start_stock, cumulative)
    requested = max(0, desired - total_prior_deductions)

    # Plan from the *specific pre-purchase stock rows*, not just article totals.
    # This protects previous same-day purchases even when the household keeps
    # multiple stock locations or the new purchase joins an existing row.
    requested = min(requested, sum(
        pos['available_old'] for positions in stock_rows.values() for pos in positions
    ))
    order = [article_id for article_id in group if article_id != purchased_article_id]
    order.append(purchased_article_id)
    allocations = []
    remaining = requested
    for article_id in order:
        for pos in stock_rows[article_id]:
            quantity = min(remaining, pos['available_old'])
            if not quantity:
                continue
            allocations.append({
                'article_id': article_id,
                'article_name': next(row['naam'] for row in member_rows if row['id'] == article_id),
                'inventory_id': str(pos['id']),
                'pre_quantity': _whole(pos['aantal']),
                'space_id': pos.get('space_id'),
                'sublocation_id': pos.get('sublocation_id'),
                'quantity': quantity,
            })
            remaining -= quantity
            if remaining == 0:
                break

    return {
        'mode': mode,
        'members': tuple(group),
        'purchase_day': day,
        'requested_deduction_quantity': requested,
        'allocations': allocations,
        'day_start_stock': start_stock,
        'prior_day_purchased_quantity': total_prior_purchases,
        'prior_day_auto_consumed_quantity': total_prior_deductions,
        'cumulative_day_purchased_quantity': cumulative,
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

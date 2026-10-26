"""Read-only household projections for equivalent GPC products.

Grouping never replaces household article identity or writes inventory. Content
is expressed in representative packages, so the existing shopping contract keeps
its meaning. Incomplete central types/content deliberately remain separate products.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
from typing import Any

from sqlalchemy import bindparam, text


UNITS = {
    'l': ('l', 1), 'liter': ('l', 1), 'ml': ('l', .001),
    'cl': ('l', .01), 'dl': ('l', .1),
    'kg': ('kg', 1), 'g': ('kg', .001), 'mg': ('kg', .000001),
    'stuk': ('stuk', 1), 'stuks': ('stuk', 1), 'st': ('stuk', 1),
}


def positive_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def content(value, unit):
    quantity = positive_number(value)
    normalized_unit = UNITS.get(str(unit or '').strip().lower())
    if quantity is None or normalized_unit is None:
        return None
    return quantity * normalized_unit[1], normalized_unit[0]


def grouping_key(row, settings=None):
    from app.services.automatic_product_type_service import classify_product_type, package_content
    try:
        facts = json.loads(row.get('facts_json') or '{}')
    except (ValueError, TypeError):
        facts = None
    if not isinstance(facts, dict):
        return ('product', str(row.get('global_product_id') or row['id'])), 1.0
    product = {**facts, 'name': row.get('product_name') or row.get('name') or '',
               'variant': row.get('variant') or facts.get('variant') or '',
               'size_value': row.get('size_value'), 'size_unit': row.get('size_unit')}
    profile = classify_product_type(product, str(row.get('brick_code') or ''))
    size = package_content(product)
    if profile['status'] == 'ready' and size:
        return ('automatic_product_type', profile['key'], profile['label'], size[1]), size[0]
    return ('product', str(row.get('global_product_id') or row['id'])), 1.0


def load_groups(conn, household_id, article_rows, settings_by_article):
    ids = [str(row['id']) for row in article_rows]
    if not ids:
        return []
    metadata = conn.execute(text('''
        SELECT ha.id, ha.global_product_id, gp.size_value, gp.size_unit, gp.name AS product_name, gp.variant, gb.brick_code, cp.facts_json
        FROM household_articles ha
        LEFT JOIN global_products gp ON gp.id = ha.global_product_id
        LEFT JOIN global_product_gpc_bricks gb ON gb.global_product_id = gp.id
        LEFT JOIN global_product_consumption_profiles cp ON cp.global_product_id = gp.id
        WHERE ha.household_id = :household_id AND ha.id IN :ids
          AND COALESCE(ha.status, 'active') = 'active'
    ''').bindparams(bindparam('ids', expanding=True)), {'household_id': str(household_id), 'ids': ids}).mappings().all()
    by_id = {str(row['id']): dict(row) for row in metadata}
    groups = {}
    for article in sorted(article_rows, key=lambda row: str(row['id'])):
        article_id = str(article['id'])
        if article_id not in by_id:
            continue
        row = {**dict(article), **by_id[article_id]}
        key, factor = grouping_key(row, settings_by_article.get(article_id, {}))
        group = groups.setdefault(key, {'key': key, 'members': [], 'factors': {}})
        group['members'].append(dict(article))
        group['factors'][article_id] = factor
    return list(groups.values())


def load_group_projection(conn, household_id, group):
    ids = [str(row['id']) for row in group['members']]
    params = {'household_id': str(household_id), 'ids': ids}
    inventory = conn.execute(text('''
        SELECT i.id, i.household_article_id, i.naam AS article_name,
               i.aantal AS quantity, i.space_id, i.sublocation_id,
               COALESCE(s.naam, '') AS space_name, COALESCE(sl.naam, '') AS sublocation_name
        FROM inventory i
        LEFT JOIN spaces s ON s.id = i.space_id AND s.household_id = :household_id
        LEFT JOIN sublocations sl ON sl.id = i.sublocation_id AND sl.space_id = s.id
        WHERE i.household_id = :household_id AND i.household_article_id IN :ids
          AND COALESCE(i.status, 'active') = 'active'
        ORDER BY i.id
    ''').bindparams(bindparam('ids', expanding=True)), params).mappings().all()
    events = conn.execute(text('''
        SELECT * FROM inventory_events
        WHERE household_id = :household_id AND article_id IN :ids
        ORDER BY created_at, id
    ''').bindparams(bindparam('ids', expanding=True)), params).mappings().all()
    representative = group['members'][0]
    package_size = group['factors'][str(representative['id'])]

    def converted(row, id_field):
        result = dict(row)
        factor = group['factors'][str(row[id_field])] / package_size
        result['original_quantity'] = float(row.get('quantity') or 0)
        result['quantity'] = result['original_quantity'] * factor
        result['product_scope_article_ids'] = ids
        result['location_label'] = result.get('location_label') or ' / '.join(filter(None, [result.get('space_name'), result.get('sublocation_name')]))
        return result

    inconsistent = False
    for member_id in ids:
        stock = sum(float(row.get('quantity') or 0) for row in inventory if str(row['household_article_id']) == member_id)
        member_events = [row for row in events if str(row['article_id']) == member_id]
        net = sum(float(row.get('quantity') or 0) for row in member_events)
        if stock < 0 or (member_events and abs(stock - net) > 1e-9):
            inconsistent = True

    return {
        'inventory_rows': [converted(row, 'household_article_id') for row in inventory],
        'event_rows': [converted(row, 'article_id') for row in events],
        'member_article_ids': ids,
        'member_data_inconsistent': inconsistent,
        'aggregation_scope': group['key'][0],
        'aggregation_variant': group['key'][2] if group['key'][0] == 'automatic_product_type' else None,
        'aggregation_unit': group['key'][3] if group['key'][0] == 'automatic_product_type' else None,
        'representative_package_content': package_size if group['key'][0] == 'automatic_product_type' else None,
    }


def prediction_from_events(events, prediction_days, now=None):
    """Quantity-weighted purchase rhythm; multiple purchases on one day are one occasion."""
    days: dict[Any, float] = {}
    now = now or datetime.now(timezone.utc)
    for event in events:
        if event.get('event_type') not in {'purchase', 'auto_repurchase'}:
            continue
        quantity = positive_number(event.get('quantity'))
        if quantity is None:
            continue
        date = None
        for raw in (event.get('purchase_date'), event.get('created_at')):
            try:
                date = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
                date = date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date.astimezone(timezone.utc)
                break
            except (ValueError, TypeError):
                continue
        if date is None:
            continue
        if date.date() > now.date():
            continue
        days[date.date()] = days.get(date.date(), 0) + quantity
    dates = sorted(days)
    if len(dates) < 2:
        return None
    elapsed = (dates[-1] - dates[0]).days
    # Quantities bought before the last occasion supplied the observed interval.
    rate = sum(days[date] for date in dates[:-1]) / elapsed
    last = datetime.combine(dates[-1], datetime.min.time(), tzinfo=timezone.utc)
    since = max((now - last).total_seconds() / 86400, 0)
    until = max(days[dates[-1]] / rate - since, 0)
    return {
        'prediction_available': True, 'prediction_basis': 'quantity_weighted_purchase_interval',
        'prediction_scope': 'automatic_product_type',
        'average_purchase_interval_days': elapsed / (len(dates) - 1),
        'average_purchase_quantity': sum(days.values()) / len(dates),
        'last_purchase_at': last.isoformat(), 'days_since_last_purchase': since,
        'predicted_days_until_depletion': round(until, 3),
        'predicted_depletion_date': (now + timedelta(days=until)).date().isoformat(),
        'predicted_depletion_at': (now + timedelta(days=until)).isoformat(),
        'prediction_threshold_days': prediction_days,
        'prediction_triggered': until <= prediction_days, 'purchase_event_count': len(dates),
    }

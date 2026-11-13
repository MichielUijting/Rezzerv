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



def confirmed_synonym_factors(conn, metadata):
    """Group complete confirmed synonym components with reliable package units.

    Previously only isolated A-B pairs could form a read-only Bijna op group.
    For 3+ connected members a stronger policy now applies: the whole group
    must be present, each product uniquely represented, every member in one
    PO-approved fresh family, and ALL package contents exactly comparable.
    A partial chain, missing package size or non-curated group stays separate.
    No stock, history, household article or Catalogus record is changed.
    """
    by_product = {}
    for row in metadata:
        product_id = str(row.get('global_product_id') or '')
        if product_id:
            by_product.setdefault(product_id, []).append(row)
    if len(by_product) < 2:
        return {}
    product_ids = sorted(by_product)
    # Inspect all links touching a selected product, not just links whose other
    # endpoint happens to be in this household. This prevents unsafe partial
    # chains from being silently treated as independent pairs.
    links = conn.execute(text("""
        SELECT left_product_id, right_product_id
          FROM article_synonym_links
         WHERE left_product_id IN :ids OR right_product_id IN :ids
    """).bindparams(bindparam('ids', expanding=True)), {'ids': product_ids}).mappings().all()
    neighbors = {}
    for link in links:
        left = str(link['left_product_id'])
        right = str(link['right_product_id'])
        neighbors.setdefault(left, set()).add(right)
        neighbors.setdefault(right, set()).add(left)
    factors = {}
    visited = set()
    for start in product_ids:
        if start in visited or start not in neighbors:
            continue
        component = set()
        frontier = [start]
        while frontier and len(component) <= 200:
            current = frontier.pop()
            if current in component:
                continue
            component.add(current)
            frontier.extend(neighbors.get(current, set()) - component)
        visited.update(component)
        if not 2 <= len(component) <= 200:
            continue
        # Never aggregate a partial component or two household articles that
        # both claim the same central identity.
        if any(pid not in by_product or len(by_product[pid]) != 1
               for pid in component):
            continue
        entries = [by_product[pid][0] for pid in sorted(component)]
        sizes = [content(row.get('size_value'), row.get('size_unit'))
                 for row in entries]
        if not all(sizes) or len({size[1] for size in sizes}) != 1:
            continue

        if len(component) > 2:
            # The original two-member equivalence policy remains unchanged.
            # A-B-C+ needs the explicit stronger family and conversion proof.
            from app.services.synonym_product_family_rules import approved_family
            families = {
                approved_family({
                    'name': row.get('product_name') or '',
                    'variant': row.get('variant') or '',
                })
                for row in entries
            }
            if families != {'verse_courgette_v1'}:
                continue

        members = sorted(component)
        key = ('confirmed_synonym', ':'.join(members),
               'Bevestigde synoniemen', sizes[0][1])
        for pid, package in zip(members, sizes):
            factors[pid] = (key, package[0])
    return factors

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
    synonym_factors = confirmed_synonym_factors(conn, list(by_id.values()))
    # Keep pre-existing automatic product-type groups intact: a new synonym pair
    # must not split an already aggregated three-or-more-member product type.
    baseline = {}
    for article in article_rows:
        article_id = str(article['id'])
        if article_id in by_id:
            baseline[article_id] = grouping_key({**dict(article), **by_id[article_id]}, settings_by_article.get(article_id, {}))
    baseline_counts = {}
    for key, _factor in baseline.values():
        baseline_counts[key] = baseline_counts.get(key, 0) + 1
    # A pair is either eligible as a whole or not at all.
    pair_members = {}
    for article in article_rows:
        article_id = str(article['id'])
        if article_id not in baseline:
            continue
        product_id = str(by_id[article_id].get('global_product_id') or '')
        pair = synonym_factors.get(product_id)
        if pair:
            pair_members.setdefault(pair[0], []).append(article_id)
    disabled_pairs = {
        key for key, members in pair_members.items()
        if any(baseline_counts[baseline[member][0]] > 1 for member in members)
    }
    groups = {}
    for article in sorted(article_rows, key=lambda row: str(row['id'])):
        article_id = str(article['id'])
        if article_id not in by_id:
            continue
        row = {**dict(article), **by_id[article_id]}
        key, factor = synonym_factors.get(str(row.get('global_product_id') or ''), (None, None))
        if key is not None and key in disabled_pairs:
            # Never split an existing automatic group to make a partial pair.
            key = None
        if key is None:
            key, factor = baseline[article_id]
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
        'aggregation_variant': group['key'][2] if group['key'][0] in {'automatic_product_type', 'confirmed_synonym'} else None,
        'aggregation_unit': group['key'][3] if group['key'][0] in {'automatic_product_type', 'confirmed_synonym'} else None,
        'representative_package_content': package_size if group['key'][0] in {'automatic_product_type', 'confirmed_synonym'} else None,
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

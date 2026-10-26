"""TD-07: central, data-driven consumption types, independent of product identity.

Only complete, non-conflicting attributes produce an aggregation key. Missing
information is a normal pending result, never a request for household input.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from sqlalchemy import text

DATA = Path(__file__).resolve().parents[1] / 'data'


def normalized(value):
    value = unicodedata.normalize('NFKD', str(value or '').casefold())
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[^a-z0-9+]+', ' ', value).split())


@lru_cache(maxsize=1)
def policy():
    return json.loads((DATA / 'product_consumption_policy.json').read_text())


@lru_cache(maxsize=1)
def official_reference():
    return json.loads((DATA / 'gpc_bricks_nl.json').read_text())


@lru_cache(maxsize=1)
def official_bricks():
    return {r['gpc_brick_code']: r for r in official_reference()['bricks']}


def verified_official_labels(row):
    """Prevent corrupt labels from lending another official code false evidence."""
    row = dict(row)
    if row.get('source_version') == official_reference()['publication_version']:
        official = official_bricks().get(str(row.get('brick_code') or ''))
        if not official:
            return None
        for level in ('brick', 'class', 'family', 'segment'):
            row[f'{level}_description'] = official[f'gpc_{level}_name']
            row[f'{level}_code'] = official[f'gpc_{level}_code']
    return row


def _matches(text_value, term):
    return list(re.finditer(r'(?<!\w)' + re.escape(normalized(term)) + r'(?!\w)', text_value)) if normalized(term) else []


def gpc_brick_conflict(product, brick_code):
    """Reject known contradictions, without inventing an alternative Brick.

    Separate validation rules cover products whose consumption attributes are
    not yet complete enough for automatic aggregation.
    """
    facts = source_facts(product)
    title = normalized(' '.join(str(facts.get(key) or '') for key in ('name', 'product_name', 'variant')))
    for rule in policy().get('brick_validation_rules', []):
        if (any(_matches(title, term) for term in rule['terms'])
                and not any(_matches(title, term) for term in rule.get('exclude_terms', []))
                and str(brick_code) in rule['incompatible_brick_codes']):
            return 'De broncategorie past niet bij de productomschrijving. Het artikel blijft voorlopig ongekoppeld; je hoeft niets in te vullen.'
    return None


def _attribute_value(definition, title, structured):
    matches = []
    for code, item in definition['values'].items():
        for term in item.get('terms', []):
            matches.extend((m.start(), m.end(), code) for m in _matches(title, term))
    # Prefer "jong belegen" to its overlapping "jong" and "belegen" tokens.
    occupied = []
    values = set()
    for start, end, code in sorted(matches, key=lambda m: (-(m[1] - m[0]), m[0])):
        if any(start < right and end > left for left, right in occupied):
            continue
        occupied.append((start, end))
        values.add(code)
    evidence = ['productomschrijving'] if values else []
    for field in definition.get('fields', []):
        raw = structured.get(field)
        if raw is None or raw == '':
            continue
        source_value = normalized(raw)
        found = set()
        for code, item in definition['values'].items():
            allowed = [code, item['label'], *item.get('terms', []), *item.get('source_values', [])]
            if source_value in {normalized(v) for v in allowed}:
                found.add(code)
        if not found:
            return None, [field], 'unknown_value'
        values.update(found)
        evidence.append(field)
    if len(values) > 1:
        return None, evidence, 'conflict'
    if values:
        return next(iter(values)), evidence, None
    default = definition.get('default')
    return default, ['productconventie'] if default else [], None if default else 'missing'


def source_facts(product):
    """Whitelist product facts; no receipts, sessions or full provider payloads."""
    if not isinstance(product, dict):
        return {}
    allowed = {'product_name', 'name', 'variant', 'category', 'categories', 'quantity', 'quantity_label', 'net_content', 'size_value', 'size_unit'}
    allowed.update(field for definition in policy()['attributes'].values() for field in definition.get('fields', []))
    nested = product.get('attributes') if isinstance(product.get('attributes'), dict) else {}
    return {key: value for key, value in {**nested, **product}.items() if key in allowed and isinstance(value, (str, int, float)) and not isinstance(value, bool)}


def classify_product_type(product, brick_code=''):
    product = source_facts(product)
    title = normalized(' '.join(str(product.get(key) or '') for key in ('name', 'product_name', 'variant')))
    brick = official_bricks().get(str(brick_code or '').strip())
    rules = policy()['rules']
    named = [r for r in rules if any(_matches(title, term) for term in r['terms'])]
    def compatible(rule):
        return bool(brick and brick['gpc_segment_code'] in rule['segment_codes'] and (brick_code in rule['brick_codes'] or any(normalized(term) in normalized(brick['gpc_brick_name']) for term in rule['brick_terms'])))
    compatible_rules = [r for r in rules if compatible(r)]
    candidates = [r for r in named if compatible(r)] if brick else named
    if not candidates and brick and not named:
        candidates = compatible_rules
    size = package_content(product)
    base = {'aggregation_ready': False, 'package_content': {'value': size[0], 'unit': size[1]} if size else None, 'status': 'pending', 'key': None, 'label': None, 'attributes': {}, 'evidence': {}, 'missing': [], 'reason': None, 'policy_version': policy()['version'], 'gpc_brick_code': str(brick_code or '')}
    if len(candidates) != 1:
        base['reason'] = 'conflicting_category' if named and brick else 'unsupported_or_ambiguous_type'
        return base
    rule = candidates[0]
    base['type'] = rule['key']
    attributes, evidence, missing = {}, {}, []
    for key in rule['attributes']:
        definition = policy()['attributes'][key]
        value, sources, problem = _attribute_value(definition, title, product)
        if problem:
            missing.append(definition['label'])
            if problem == 'conflict':
                base['reason'] = 'conflicting_attributes'
        elif value in rule.get('forbidden_values', {}).get(key, []):
            base['reason'] = 'conflicting_category'
            missing.append(definition['label'])
        else:
            attributes[key] = value
            evidence[key] = sources
    base.update(attributes=attributes, evidence=evidence, missing=missing)
    if not brick:
        # A single unambiguous official Brick may follow from an explicit type.
        allowed = rule['brick_codes']
        if len(allowed) == 1 and allowed[0] in official_bricks():
            return classify_product_type(product, allowed[0])
        base['reason'] = base['reason'] or 'missing_gpc_classification'
        return base
    if missing:
        base['reason'] = base['reason'] or 'missing_attributes'
        return base
    qualifiers = sorted({item['key'] for item in policy().get('separating_terms', []) if any(_matches(title, term) for term in item['terms'])})
    signature = json.dumps([policy()['version'], brick_code, rule['key'], attributes, qualifiers], sort_keys=True, ensure_ascii=True)
    digest = hashlib.sha256(signature.encode()).hexdigest()[:24]
    labels = [policy()['attributes'][key]['values'][value]['label'] for key, value in attributes.items()]
    return {**base, 'aggregation_ready': bool(size), 'status': 'ready', 'reason': None, 'key': f'consumption:{digest}', 'label': ' · '.join([rule['label'], *labels]), 'qualifiers': qualifiers}


def package_content(product):
    """Return total content per package, including explicit multipacks."""
    import math
    units = {'l': ('l', 1), 'liter': ('l', 1), 'ml': ('l', .001), 'cl': ('l', .01), 'dl': ('l', .1), 'kg': ('kg', 1), 'g': ('kg', .001), 'mg': ('kg', .000001), 'stuk': ('stuk', 1), 'stuks': ('stuk', 1), 'st': ('stuk', 1)}
    value, unit = product.get('size_value'), str(product.get('size_unit') or '').strip().lower()
    if value is None or unit not in units:
        label = str(product.get('quantity') or product.get('quantity_label') or product.get('net_content') or '')
        match = re.fullmatch(r'\s*(?:(\d+)\s*[x×]\s*)?(\d+(?:[.,]\d+)?)\s*(ml|cl|dl|l|kg|g|mg|stuks?|st)\s*', label, flags=re.I)
        if not match:
            title = str(product.get('product_name') or product.get('name') or '')
            found = list(re.finditer(r'(?<!\w)(?:\d+\s*[x×]\s*)?\d+(?:[.,]\d+)?\s*(?:ml|cl|dl|l|kg|g|mg|stuks?|st)\b', title, flags=re.I))
            if len(found) != 1:
                return None
            return package_content({'quantity': found[0].group()})
        value = float(match[1] or 1) * float(match[2].replace(',', '.'))
        unit = match[3].lower()
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return (value * units[unit][1], units[unit][0]) if math.isfinite(value) and value > 0 else None


def persist_product_type(conn, global_product_id, product, brick_code):
    facts = source_facts(product)
    profile = classify_product_type(facts, brick_code)
    fingerprint = hashlib.sha256(json.dumps([facts, brick_code, policy()['version']], sort_keys=True).encode()).hexdigest()
    conn.execute(text('''
        INSERT INTO global_product_consumption_profiles
          (global_product_id, classification_key, status, label, facts_json, profile_json, source_fingerprint, policy_version, updated_at)
        VALUES (:id, :key, :status, :label, :facts, :profile, :fingerprint, :version, CURRENT_TIMESTAMP)
        ON CONFLICT (global_product_id) DO UPDATE SET
          classification_key = excluded.classification_key, status = excluded.status,
          label = excluded.label, facts_json = excluded.facts_json,
          profile_json = excluded.profile_json, source_fingerprint = excluded.source_fingerprint,
          policy_version = excluded.policy_version, updated_at = CURRENT_TIMESTAMP
    '''), {'id': str(global_product_id), 'key': profile['key'], 'status': profile['status'], 'label': profile['label'], 'facts': json.dumps(facts), 'profile': json.dumps(profile), 'fingerprint': fingerprint, 'version': policy()['version']})
    return profile

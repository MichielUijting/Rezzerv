"""TD-05: central, explicitly confirmed product synonym pairs.

Candidate generation never writes. Product, household and stock identities stay
separate. Pure sparse TF-IDF/cosine baseline, inspired by the matching probe.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
import json
from math import log, sqrt
import re
import unicodedata

from sqlalchemy import text

from app.services.gtin_validation_service import is_valid_gtin

METHOD = 'word12-char35-tfidf-v1'
MIN_SCORE = 0.20
MAX_PER_PRODUCT = 7

RETAILER_NAMES = {
    'ah': 'Albert Heijn',
    'albert-heijn': 'Albert Heijn',
    'jumbo': 'Jumbo',
    'lidl': 'Lidl',
    'aldi': 'Aldi',
    'plus': 'PLUS',
    'picnic': 'Picnic',
    'dirk': 'Dirk',
}


def _retailer_code(value):
    value = unicodedata.normalize('NFKD', str(value or '').strip().lower())
    value = ''.join(c for c in value if not unicodedata.combining(c))
    code = re.sub(r'[^a-z0-9]+', '-', value).strip('-')
    return 'ah' if code == 'albert-heijn' else code


def _store_name(code):
    return RETAILER_NAMES.get(code, code.replace('-', ' ').title()) if code else 'Niet vastgelegd'


def _normalized(value):
    value = unicodedata.normalize('NFKD', str(value or '').lower())
    value = ''.join(c for c in value if not unicodedata.combining(c))
    # Retailer names are not functional product characteristics.
    return ' '.join(w for w in re.findall(r'\w+', value) if w not in {'ah', 'jumbo', 'lidl', 'albert', 'heijn'})


def _features(product, chars=False):
    value = _normalized(f"{product['name']} {product.get('variant') or ''}")
    if chars:
        return Counter(value[i:i+n] for n in range(3, 6) for i in range(max(0, len(value)-n+1)))
    words = value.split()
    return Counter([' '.join(words[i:i+n]) for n in (1, 2) for i in range(max(0, len(words)-n+1))])


def _vectors(products, chars=False):
    counts = [_features(p, chars) for p in products]
    frequency = Counter(term for terms in counts for term in terms)
    result = []
    for terms in counts:
        vector = {term: count * (log((1+len(products))/(1+frequency[term]))+1) for term, count in terms.items()}
        norm = sqrt(sum(v*v for v in vector.values())) or 1
        result.append({term: value/norm for term, value in vector.items()})
    return result


def _fingerprint(left, right):
    # A changed thumbnail or display label does not change product identity.
    stable = [{k: v for k, v in product.items() if k not in {'image_url', 'store_name'}} for product in (left, right)]
    value = json.dumps([METHOD, *stable], sort_keys=True, ensure_ascii=False, default=str)
    return sha256(value.encode()).hexdigest()


def load_products(conn):
    """Only central catalog facts; never read private household articles/receipts."""
    codes = defaultdict(set)
    retailers = defaultdict(set)
    for row in conn.execute(text("""
        SELECT global_product_id, retailer_code, external_article_code
        FROM external_article_product_links
        WHERE status='confirmed' AND TRIM(retailer_code) <> ''
    """)).mappings():
        retailer = _retailer_code(row['retailer_code'])
        if not retailer:
            continue
        retailers[row['global_product_id']].add(retailer)
        if str(row['external_article_code'] or '').strip():
            codes[row['global_product_id']].add(f"{retailer}: {row['external_article_code']}")
    products = []
    for row in conn.execute(text("""
        SELECT gp.id, gp.name, gp.brand, gp.variant, gp.primary_gtin,
               gp.size_value, gp.size_unit, gp.image_url, gp.source, gpc.brick_code
        FROM global_products gp
        LEFT JOIN global_product_gpc_bricks gpc ON gpc.global_product_id=gp.id
        WHERE gp.status='active' AND TRIM(gp.name) <> '' ORDER BY gp.id
    """)).mappings():
        product = dict(row)
        gtin = str(product.get('primary_gtin') or '').strip()
        valid_gtin = gtin.zfill(14) if gtin.isascii() and gtin.isdigit() and is_valid_gtin(gtin) else ''
        article_codes = sorted(codes[product['id']])
        if not valid_gtin and not article_codes:
            continue
        known_retailers = set(retailers[product['id']])
        # A catalog source is shop evidence only when it names an actual shop.
        source_retailer = _retailer_code(product.pop('source'))
        if not known_retailers and source_retailer in RETAILER_NAMES:
            known_retailers.add(source_retailer)
        retailer_code = next(iter(known_retailers)) if len(known_retailers) == 1 else ''
        product.update(
            primary_gtin=valid_gtin,
            article_codes=article_codes,
            retailer_code=retailer_code,
            store_name=_store_name(retailer_code),
            image_url=str(product.get('image_url') or '').strip(),
        )
        # Stable serialization across PostgreSQL Decimal and HTTP JSON.
        product['size_value'] = str(product['size_value'] or '')
        products.append(product)
    return products


def suggest_pairs(products, confirmed=()):
    """Sparse inverted-index ranking; no dense all-products similarity matrix."""
    products = sorted(products, key=lambda p: p['id'])
    confirmed = set(confirmed)
    words, chars = _vectors(products), _vectors(products, True)
    postings = []
    for vectors in (words, chars):
        index = defaultdict(list)
        for i, vector in enumerate(vectors):
            for term, value in vector.items():
                index[term].append((i, value))
        postings.append(index)
    pairs = {}
    for i, left in enumerate(products):
        scores = defaultdict(float)
        for vector, index in zip((words[i], chars[i]), postings):
            for term, value in vector.items():
                for j, other in index[term]:
                    if i != j:
                        scores[j] += .5 * value * other
        candidates = []
        for j, score in scores.items():
            right = products[j]
            a, b = sorted((left['id'], right['id']))
            if score < MIN_SCORE or (a, b) in confirmed:
                continue
            # Shop-specific synonyms need two distinct, documented shops.
            if not left.get('retailer_code') or not right.get('retailer_code') or left['retailer_code'] == right['retailer_code']:
                continue
            if left.get('primary_gtin') and left['primary_gtin'] == right.get('primary_gtin'):
                continue  # Same trade item, not a synonym with a different identity.
            if set(left.get('article_codes', [])) & set(right.get('article_codes', [])):
                continue
            if left.get('brick_code') and right.get('brick_code') and left['brick_code'] != right['brick_code']:
                continue
            candidates.append((j, score))
        for j, score in sorted(candidates, key=lambda pair: (-pair[1], products[pair[0]]['id']))[:MAX_PER_PRODUCT]:
            first, second = sorted((left, products[j]), key=lambda p: p['id'])
            key = (first['id'], second['id'])
            pairs[key] = {
                'id': json.dumps(key, separators=(',', ':')),
                'left': first, 'right': second, 'score': min(1.0, round(score, 4)),
                'fingerprint': _fingerprint(first, second),
                'warning': 'Controleer variant, bereiding en inhoud; de score is geen zekerheid.',
            }
    return sorted(pairs.values(), key=lambda pair: (-pair['score'], pair['id']))


def confirmed_pairs(conn):
    return set(tuple(row) for row in conn.execute(text(
        'SELECT left_product_id, right_product_id FROM article_synonym_links'
    )))


def confirm_pairs(conn, selections, actor_id):
    """Atomic, idempotent bulk confirmation with current-candidate validation."""
    from fastapi import HTTPException
    ids = sorted({s[k] for s in selections for k in ('left_product_id', 'right_product_id')})
    # Serialize edits/deletion of selected catalog records and repeated confirmations.
    if conn.dialect.name == 'postgresql':
        for product_id in ids:
            conn.execute(text('SELECT id FROM global_products WHERE id=:id FOR UPDATE'), {'id': product_id}).all()
    products = load_products(conn)
    existing = confirmed_pairs(conn)
    proposals = {(p['left']['id'], p['right']['id']): p for p in suggest_pairs(products, existing)}
    by_id = {p['id']: p for p in products}
    to_insert = {}
    for selection in selections:
        key = (selection['left_product_id'], selection['right_product_id'])
        proposal = proposals.get(key)
        if key in existing and all(pid in by_id for pid in key):
            proposal = {'fingerprint': _fingerprint(by_id[key[0]], by_id[key[1]])}
        if not proposal or proposal['fingerprint'] != selection['fingerprint']:
            raise HTTPException(409, 'Een suggestie is gewijzigd of niet meer beschikbaar. Vernieuw de lijst en controleer opnieuw.')
        if key not in existing:
            to_insert[key] = proposal
    for (left, right), proposal in to_insert.items():
        conn.execute(text('''
            INSERT INTO article_synonym_links
                (left_product_id, right_product_id, confirmed_by, source_fingerprint, method, score)
            VALUES (:left, :right, :actor, :fingerprint, :method, :score)
            ON CONFLICT (left_product_id, right_product_id) DO NOTHING
        '''), dict(left=left, right=right, actor=actor_id, fingerprint=proposal['fingerprint'], method=METHOD, score=proposal['score']))
    return {'linked': len(to_insert), 'already_linked': len({(s['left_product_id'], s['right_product_id']) for s in selections} & existing)}

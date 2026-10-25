"""TD-05: read-only public NL Lidl product evidence; no accounts or writes.

Receipt codes, webshop SKUs and GTINs remain separate namespaces. Only a GTIN
explicitly attached to the selected product is returned, never a page-wide digit
match, recommendation, offer ID or fabricated check digit.
"""
from __future__ import annotations

import html
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from app.services.gtin_validation_service import is_valid_gtin

MAX_BYTES = 2 * 1024 * 1024
HOST = 'www.lidl.nl'


class LidlLookupError(ValueError):
    pass


def product_url(value):
    url = urllib.parse.urljoin('https://' + HOST, value)
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname != HOST or parsed.port not in (None, 443)
            or parsed.username or parsed.password or parsed.fragment or parsed.query
            or not re.fullmatch(r'/p/[^/]+/p[0-9]{1,14}', parsed.path)):
        raise LidlLookupError('invalid_product_url')
    return url


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_product_page(code):
    """At most three GETs, 12s total, 2MiB; redirect targets checked before GET."""
    url = product_url('/p/-/p' + code)
    opener = urllib.request.build_opener(NoRedirect())
    deadline = time.monotonic() + 12
    for _ in range(3):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise LidlLookupError('unavailable')
        try:
            request = urllib.request.Request(url, headers={
                'User-Agent': 'Inhuis/1.0 public product lookup', 'Accept': 'text/html',
            })
            with opener.open(request, timeout=min(5, remaining)) as response:
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise LidlLookupError('response_too_large')
                return raw.decode('utf-8'), url
        except urllib.error.HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308}:
                url = product_url(urllib.parse.urljoin(url, exc.headers.get('Location', '')))
                # Never follow a redirect to a different product identifier.
                if not urllib.parse.urlsplit(url).path.endswith('/p' + code):
                    raise LidlLookupError('product_mismatch') from None
                continue
            raise LidlLookupError('not_found' if exc.code == 404 else 'unavailable') from None
        except (OSError, UnicodeError, ValueError) as exc:
            if isinstance(exc, LidlLookupError):
                raise
            raise LidlLookupError('unavailable') from None
    raise LidlLookupError('unavailable')


class ProductPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.blocks = []
        self.kind = ''
        self.parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script':
            self.kind = ('ld' if attrs.get('type') == 'application/ld+json' else
                         'nuxt' if attrs.get('id') == '__NUXT_DATA__' else '')
            self.parts = []

    def handle_data(self, data):
        if self.kind:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.kind:
            try:
                self.blocks.append((self.kind, json.loads(''.join(self.parts))))
            except (ValueError, RecursionError):
                pass
            self.kind = ''


def clean(value):
    return ' '.join(html.unescape(re.sub(r'<[^>]*>', ' ', str(value or ''))).split())[:500]


def valid_gtin(value):
    # The common validator normalizes punctuation; this source boundary must not.
    return (value if isinstance(value, str) and re.fullmatch(r'[0-9]{8}|[0-9]{12,14}', value)
            and set(value) != {'0'} and is_valid_gtin(value) else '')


def name_compatible(source, candidate):
    def tokens(value):
        value = unicodedata.normalize('NFKD', str(value).lower())
        value = re.sub(r'\bjong\s+belegen\b', 'jongbelegen', value)
        aliases = {'halfvol': 'halfvolle', 'vol': 'volle', 'mager': 'magere',
                   'vers': 'verse', 'houdbaar': 'houdbare', 'jong': 'jonge', 'oud': 'oude'}
        return {aliases.get(t, t) for t in re.findall(r'[a-z0-9]+', value)
                if len(t) >= 3 and t not in {'lidl', 'stuk', 'stuks', 'pak', 'zak'}}
    wanted, actual = tokens(source), tokens(candidate)
    if not wanted or not actual or len(wanted & actual) / len(wanted) < .6:
        return False
    for family in ({'halfvolle', 'volle', 'magere'}, {'jonge', 'oude', 'belegen', 'jongbelegen'},
                   {'houdbare', 'verse'}, {'ongekruid', 'gekruid'}):
        a, b = wanted & family, actual & family
        if a and a != b:
            return False
    return True


def _products(value, depth=0):
    if depth > 6:
        return []
    if isinstance(value, list):
        return [p for entry in value[:50] for p in _products(entry, depth + 1)]
    if not isinstance(value, dict):
        return []
    kinds = value.get('@type', [])
    result = [value] if kinds == 'Product' or isinstance(kinds, list) and 'Product' in kinds else []
    # Never traverse offers, variants or recommendations.
    return result + _products(value.get('@graph'), depth + 1)


def _nuxt_value(table, ref):
    return table[ref] if type(ref) is int and 0 <= ref < len(table) else None


def _nuxt_eans(table, code, name):
    """Read only the eans list on one exact product node in Nuxt's ref table."""
    if not isinstance(table, list) or len(table) > 50000:
        return []
    nodes = []
    for node in table:
        if not isinstance(node, dict) or str(_nuxt_value(table, node.get('erpNumber'))) != code:
            continue
        facts = _nuxt_value(table, node.get('keyfacts'))
        if not isinstance(facts, dict):
            continue
        titles = [clean(_nuxt_value(table, facts.get(key))) for key in ('title', 'fullTitle')]
        if name.casefold() not in {title.casefold() for title in titles}:
            continue
        nodes.append(node)
    if len(nodes) != 1:
        return []
    refs = _nuxt_value(table, nodes[0].get('eans'))
    if not isinstance(refs, list):
        return []
    return [code for ref in refs[:20] if (code := valid_gtin(_nuxt_value(table, ref)))]


def parse_product_page(page_html, source_url, code, receipt_name):
    product_url(source_url)
    if not urllib.parse.urlsplit(source_url).path.endswith('/p' + code):
        raise LidlLookupError('product_mismatch')
    parser = ProductPage()
    parser.feed(page_html)
    products = [p for kind, block in parser.blocks if kind == 'ld' for p in _products(block)
                if str(p.get('sku', '')) == code]
    if len(products) != 1:
        raise LidlLookupError('not_found')
    product = products[0]
    name = clean(product.get('name'))
    description = clean(product.get('description'))
    if not name_compatible(receipt_name, name + ' ' + description):
        raise LidlLookupError('name_conflict')
    brand = product.get('brand')
    brand = clean(brand.get('name')) if isinstance(brand, dict) else clean(brand) if isinstance(brand, str) else ''
    codes = {value for key in ('gtin', 'gtin8', 'gtin12', 'gtin13', 'gtin14')
             if (value := valid_gtin(product.get(key)))}
    for kind, block in parser.blocks:
        if kind == 'nuxt':
            codes.update(_nuxt_eans(block, code, name))
    return {
        'product_name': name, 'brand': brand, 'description': description,
        'article_number': code, 'source_url': source_url, 'source': 'Lidl Nederland',
        'gtins': sorted(codes),
        # Multiple legitimate EANs may belong to one shop article; don't pick one.
        'status': 'barcode_found' if len(codes) == 1 else 'multiple_barcodes' if codes else 'no_barcode',
    }


def lookup_lidl_product(item):
    code = str(item.get('external_article_code') or '').strip()
    if not re.fullmatch(r'[0-9]{1,14}', code):
        return {'status': 'no_article_number', 'source': 'Lidl Nederland'}
    try:
        page_html, url = fetch_product_page(code)
        return parse_product_page(page_html, url, code, item.get('receipt_line_text', ''))
    except LidlLookupError as exc:
        return {'status': str(exc), 'source': 'Lidl Nederland'}

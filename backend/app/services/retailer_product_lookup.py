"""TD-05: bounded anonymous AH/Jumbo product discovery, without account or writes.

Protocols proven by the isolated retailer catalog probe. AH hqId is the receipt
namespace; webshopId is used only for product detail. Jumbo uses an exact public
product SKU. Neither namespace is converted into a GTIN.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from app.services.external_product_identity_policy import external_product_identity_compatibility
from app.services.lidl_product_lookup import NoRedirect, ProductPage, _products, clean, name_compatible, valid_gtin

HOSTS = {'ah': 'api.ah.nl', 'jumbo': 'www.jumbo.com'}
AH_QUERY = 'query InhuisCatalogProduct($id:Int!){product(id:$id){id title tradeItem{gtin}}}'
JUMBO_QUERY = 'query InhuisCatalogProduct($sku:String!){product(sku:$sku){sku title brand ean}}'
MAX_DETAILS = 8
MAX_BYTES = 2 * 1024 * 1024


class CatalogError(ValueError):
    pass


def retailer_code(value):
    normalized = re.sub(r'[^a-z0-9]+', '-', str(value or '').lower()).strip('-')
    return 'ah' if normalized in {'ah', 'albert-heijn', 'albert-heijn-digitaal'} else normalized


def identifier(value):
    if type(value) is int and 0 <= value < 10 ** 14:
        return str(value)
    return value.strip() if isinstance(value, str) and len(value) <= 100 else ''


def safe_url(provider, path):
    if provider not in HOSTS or not isinstance(path, str):
        raise CatalogError('invalid_url')
    url = urllib.parse.urljoin('https://' + HOSTS[provider], path)
    p = urllib.parse.urlsplit(url)
    if (p.scheme != 'https' or p.hostname != HOSTS[provider] or p.port not in (None, 443)
            or p.username or p.password or p.fragment):
        raise CatalogError('invalid_url')
    return url


class GuestTransport:
    def __init__(self):
        self.calls = 0
        self.deadline = time.monotonic() + 30
        self.opener = urllib.request.build_opener(NoRedirect())

    def __call__(self, provider, path, payload=None, *, token='', as_html=False):
        url = safe_url(provider, path)
        parsed = urllib.parse.urlsplit(url)
        route = parsed.path
        if payload is None:
            allowed = (provider == 'ah' and route == '/mobile-services/product/search/v2'
                       or provider == 'jumbo' and (route == '/producten/' or
                           re.fullmatch(r'/producten/[a-zA-Z0-9_-]+-[0-9]{3,}[A-Z]{2,}', route)))
        else:
            allowed = (provider == 'ah' and path == '/mobile-auth/v1/auth/token/anonymous'
                       and payload == {'clientId': 'appie-ios'})
            allowed |= (provider == 'ah' and path == '/graphql' and payload.get('query') == AH_QUERY)
            allowed |= (provider == 'jumbo' and path == '/api/graphql' and payload.get('query') == JUMBO_QUERY)
        if not allowed or token and provider != 'ah':
            raise CatalogError('operation_not_allowed')
        remaining = self.deadline - time.monotonic()
        if self.calls >= 20 or remaining <= 0:
            raise CatalogError('budget_exhausted')
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; InhuisProductLookup/1.0)',
                   'Accept': 'text/html' if as_html else 'application/json'}
        if provider == 'ah':
            headers.update({'User-Agent': 'Appie/9.28 (iPhone17,3; iPhone; CPU OS 26_1 like Mac OS X)',
                            'x-client-name': 'appie-ios', 'x-client-version': '9.28', 'x-application': 'AHWEBSHOP'})
        if token:
            headers['Authorization'] = 'Bearer ' + token
        data = None
        if payload is not None:
            data = json.dumps(payload).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        self.calls += 1
        try:
            with self.opener.open(urllib.request.Request(url, data=data, headers=headers),
                                  timeout=min(8, remaining)) as response:
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise CatalogError('response_too_large')
            return raw.decode('utf-8') if as_html else json.loads(raw)
        except urllib.error.HTTPError as exc:
            raise CatalogError('http_' + str(exc.code)) from None
        except (OSError, ValueError, UnicodeError, RecursionError) as exc:
            if isinstance(exc, CatalogError):
                raise
            raise CatalogError('unavailable') from None


def compatible(item, name, brand=''):
    return name_compatible(item.get('receipt_line_text', ''), name) and bool(
        external_product_identity_compatibility(retailer_code=retailer_code(item.get('retailer_code')),
            receipt_text=item.get('receipt_line_text'), candidate_name=name, candidate_brand=brand).get('ok'))


def _candidate(item, provider, name, brand, gtin, receipt_code, url, quantity=''):
    name, brand = clean(name), clean(brand)
    if not compatible(item, name, brand) or not valid_gtin(gtin):
        return None
    return {'product_name': name, 'brand': brand, 'gtin': gtin, 'quantity': clean(quantity),
            'source': 'Albert Heijn' if provider == 'ah' else 'Jumbo', 'source_url': url,
            'receipt_code_match': bool(item.get('external_article_code')) and
                str(item['external_article_code']).strip() == receipt_code,
            'identity_compatible': True}


def _ah(item, transport):
    auth = transport('ah', '/mobile-auth/v1/auth/token/anonymous', {'clientId': 'appie-ios'})
    token = auth.get('access_token') if isinstance(auth, dict) else None
    if not isinstance(token, str) or not token or len(token) > 10000:
        raise CatalogError('guest_auth_invalid')
    code = identifier(item.get('external_article_code'))
    cards, failures = {}, []
    for query in dict.fromkeys(q for q in (code, item.get('receipt_line_text')) if q):
        try:
            payload = transport('ah', '/mobile-services/product/search/v2?' + urllib.parse.urlencode(
                {'query': query, 'size': 20, 'page': 0, 'sortOn': 'RELEVANCE'}), token=token)
            products = payload.get('products') if isinstance(payload, dict) else None
            if not isinstance(products, list):
                raise CatalogError('catalog_layout_unknown')
            for card in products[:20]:
                if not isinstance(card, dict) or not compatible(item, card.get('title'), card.get('brand')):
                    continue
                webshop = identifier(card.get('webshopId'))
                if re.fullmatch(r'[0-9]{1,10}', webshop):
                    cards[webshop] = card
            if code and any(identifier(card.get('hqId')) == code for card in cards.values()):
                break
        except CatalogError as exc:
            failures.append(str(exc))
    candidates = []
    ranked = sorted(cards.items(), key=lambda entry: bool(code) and identifier(entry[1].get('hqId')) == code, reverse=True)
    for webshop, card in ranked[:MAX_DETAILS]:
        try:
            payload = transport('ah', '/graphql', {'query': AH_QUERY, 'variables': {'id': int(webshop)}}, token=token)
            product = (payload.get('data') or {}).get('product')
            if payload.get('errors') or not isinstance(product, dict) or identifier(product.get('id')) != webshop:
                raise CatalogError('product_identity_mismatch')
            candidate = _candidate(item, 'ah', product.get('title'), card.get('brand'),
                (product.get('tradeItem') or {}).get('gtin'), identifier(card.get('hqId')),
                'https://www.ah.nl/producten/product/wi' + webshop, card.get('salesUnitSize', ''))
            if candidate:
                candidates.append(candidate)
        except (CatalogError, AttributeError, TypeError) as exc:
            failures.append(str(exc) if isinstance(exc, CatalogError) else 'catalog_layout_unknown')
    return candidates, failures


class ProductLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = {}

    def handle_starttag(self, tag, attrs):
        href = dict(attrs).get('href', '')
        if tag == 'a' and len(self.links) < 100:
            match = re.fullmatch(r'/producten/[a-zA-Z0-9_-]+-([0-9]{3,}[A-Z]{2,})', href)
            if match:
                self.links.setdefault(match[1], href)


def _jumbo(item, transport):
    page = transport('jumbo', '/producten/?' + urllib.parse.urlencode(
        {'searchType': 'keyword', 'searchTerms': item.get('receipt_line_text', '')}), as_html=True)
    parser = ProductLinks()
    parser.feed(page)
    candidates, failures = [], []
    public_only = False
    for sku, link in list(parser.links.items())[:MAX_DETAILS]:
        try:
            product = None
            if not public_only:
                try:
                    payload = transport('jumbo', '/api/graphql', {'query': JUMBO_QUERY, 'variables': {'sku': sku}})
                    product = (payload.get('data') or {}).get('product')
                    if payload.get('errors') or not isinstance(product, dict) or product.get('sku') != sku:
                        raise CatalogError('product_identity_mismatch')
                except CatalogError as exc:
                    if str(exc) not in {'http_401', 'http_403'}:
                        raise
                    public_only = True
            if public_only:
                detail = transport('jumbo', link, as_html=True)
                page_parser = ProductPage()
                page_parser.feed(detail)
                matches = [p for kind, block in page_parser.blocks if kind == 'ld' for p in _products(block)
                           if identifier(p.get('sku')) == sku]
                if len(matches) != 1:
                    raise CatalogError('product_identity_mismatch')
                product = matches[0]
                brand = product.get('brand')
                brand = brand.get('name', '') if isinstance(brand, dict) else brand
                barcode = next((v for k in ('gtin14', 'gtin13', 'gtin12', 'gtin8', 'gtin')
                                if (v := valid_gtin(product.get(k)))), '')
                candidate = _candidate(item, 'jumbo', product.get('name'), brand, barcode, sku,
                                       'https://www.jumbo.com' + link)
            else:
                candidate = _candidate(item, 'jumbo', product.get('title'), product.get('brand'),
                                       product.get('ean'), sku, 'https://www.jumbo.com' + link)
            if candidate:
                candidates.append(candidate)
        except (CatalogError, AttributeError, TypeError, ValueError) as exc:
            failures.append(str(exc) if isinstance(exc, CatalogError) else 'catalog_layout_unknown')
    return candidates, failures


def lookup_retailer_products(item, transport=None):
    provider = retailer_code(item.get('retailer_code'))
    if provider not in HOSTS:
        return {'status': 'not_applicable', 'candidates': []}
    try:
        candidates, failures = (_ah if provider == 'ah' else _jumbo)(item, transport or GuestTransport())
    except (CatalogError, AttributeError, TypeError, ValueError) as exc:
        candidates, failures = [], [str(exc) if isinstance(exc, CatalogError) else 'catalog_layout_unknown']
    # Keep the strongest evidence for each GTIN; presentation dedupe is not a write.
    unique = {}
    for candidate in candidates:
        key = candidate['gtin'].zfill(14)
        if key not in unique or candidate['receipt_code_match']:
            unique[key] = candidate
    candidates = sorted(unique.values(), key=lambda c: c['receipt_code_match'], reverse=True)
    exact = [c for c in candidates if c['receipt_code_match']]
    status = ('conflicting_barcodes' if len(exact) > 1 else 'barcode_found' if exact else
              'name_suggestions' if candidates else 'unavailable' if failures else 'not_found')
    return {'status': status, 'source': 'Albert Heijn' if provider == 'ah' else 'Jumbo',
            'candidates': candidates, 'errors': failures}

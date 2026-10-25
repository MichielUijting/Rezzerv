"""TD-05: server-resolved, read-only store evidence plus existing OFF search."""
from __future__ import annotations

from app.services import off_search_service as off
from app.services.retailer_product_lookup import compatible, lookup_retailer_products, retailer_code
from app.services.lidl_product_lookup import lookup_lidl_product, name_compatible, valid_gtin


_MESSAGES = {
    'barcode_found': 'Lidl vermeldt één geldige barcode bij dit product.',
    'multiple_barcodes': 'Lidl vermeldt meerdere barcodes bij dit artikel. Er wordt geen barcode gekozen.',
    'no_barcode': 'Lidl-product gevonden, maar de pagina vermeldt geen geldige barcode. Hieronder staan OFF-suggesties.',
    'no_article_number': 'Geen Lidl-artikelnummer beschikbaar. Er wordt op artikelnaam gezocht in OFF.',
    'not_found': 'Geen passende Lidl-productpagina gevonden. Er wordt op artikelnaam gezocht in OFF.',
    'name_conflict': 'De Lidl-productpagina past niet bij de bontekst en is niet gebruikt. Hieronder staan OFF-suggesties.',
}


def search_article_candidates(payload):
    # Accept only the source ID. Browser-supplied retailer/name/code/URL are never
    # used to resolve a product or to choose a network destination.
    item = off.resolve_receipt_item(off._text(payload.get('receipt_item_id')))
    try:
        limit = max(1, min(int(payload.get('limit') or 20), 20))
    except (TypeError, ValueError):
        raise off.OffSearchError('Ongeldig maximum aantal kandidaten') from None
    request = {'receipt_item_id': item['receipt_item_id'], 'mode': 'automatic', 'limit': limit}
    if retailer_code(item.get('retailer_code')) in {'ah', 'jumbo'}:
        return _search_ah_jumbo(item, request)
    evidence = None
    lookup = {'status': 'not_applicable'}
    if str(item.get('retailer_code') or '').strip().lower() == 'lidl':
        lookup = lookup_lidl_product(item)
        evidence = dict(lookup, message=_MESSAGES.get(lookup['status'],
            'Lidl-productgegevens zijn tijdelijk niet beschikbaar. Hieronder staan OFF-suggesties.'))

    if lookup['status'] == 'barcode_found':
        gtin = lookup['gtins'][0]
        # A store-observed GTIN remains useful if OFF is unavailable or missing.
        result = {
            'gtin': gtin, 'product_name': lookup['product_name'], 'brand': lookup['brand'],
            'quantity': '', 'source': 'Lidl Nederland', 'source_url': lookup['source_url'],
            'evidence_label': 'Barcode vermeld door Lidl', 'score': 1.0,
            'identity_compatible': True,
        }
        match = off.lookup_off_product_by_gtin(gtin)
        product = match.get('product') or {}
        if (match.get('status') == 'found' and product.get('gtin') == gtin
                and name_compatible(lookup['product_name'], product.get('product_name', ''))):
            result.update(product)
            result.update(source='Lidl + Open Food Facts', source_url=lookup['source_url'],
                          evidence_label='Lidl-barcode gevonden in OFF', score=1.0)
        evidence['off_status'] = match.get('status')
        # 100% means a directly observed barcode, never an automatic saved link.
        return _response(item, [result], 'lidl_product_page', evidence)

    search_item = dict(item)
    if lookup.get('product_name'):
        search_item['receipt_line_text'] = lookup['product_name']
    response = off.search_off_candidates_for_item(request, search_item)
    # Preserve the original source's constraints when an expanded title is used.
    if lookup.get('product_name'):
        response['results'] = [row for row in response['results']
            if name_compatible(item['receipt_line_text'], row.get('product_name', ''))]
    response['results'] = [dict(row, source='Open Food Facts', evidence_label='Suggestie op artikelnaam')
                           for row in response['results'] if valid_gtin(row.get('gtin'))]
    response['result_count'] = len(response['results'])
    response['status'] = 'found' if response['results'] else 'no_results'
    response['retailer_evidence'] = evidence
    return response


def _response(item, results, provider, evidence):
    return {
        'receipt_item_id': item['receipt_item_id'], 'provider': provider, 'mode': 'automatic',
        'results': results, 'result_count': len(results), 'status': 'found' if results else 'no_results',
        'retailer_evidence': evidence, 'mutated': False, 'creates_global_product': False,
        'creates_household_article': False, 'creates_inventory_event': False, 'creates_external_candidate': False,
    }


def _search_ah_jumbo(item, request):
    lookup = lookup_retailer_products(item)
    source = lookup['source']
    status = lookup['status']
    messages = {
        'barcode_found': f'{source} bevestigt het artikelnummer en vermeldt een geldige barcode.',
        'conflicting_barcodes': f'{source} geeft meerdere barcodes bij hetzelfde artikelnummer. De resultaten blijven suggesties.',
        'name_suggestions': f'Producten gevonden bij {source}. De koppeling met het bonartikel is alleen op naam; controleer de suggesties.',
        'not_found': f'Geen passend product met barcode gevonden bij {source}. Hieronder staan OFF-suggesties.',
        'unavailable': f'{source} is tijdelijk niet bereikbaar. Hieronder staan OFF-suggesties.',
    }
    evidence = {'source': source, 'status': status, 'message': messages[status]}
    rows = []
    candidates = lookup['candidates']
    if status == 'barcode_found':
        candidates = [c for c in candidates if c['receipt_code_match']]
    for candidate in candidates:
        exact = status == 'barcode_found'
        row = dict(candidate, evidence_label='Artikelnummer en barcode bevestigd' if exact else 'Winkelproduct; suggestie op naam',
                   score=1.0 if exact else .9)
        # A GTIN on a store product is useful even if OFF does not know it.
        # Exact OFF enrichment is only needed for a unique receipt-code match.
        if exact:
            # AH may publish a zero-padded GTIN-14 for a GTIN-13 package.
            # This is the same GS1 identity, never a shop-ID-to-barcode conversion.
            off_gtin = row['gtin']
            if len(off_gtin) == 14 and off_gtin.startswith('0') and valid_gtin(off_gtin[1:]):
                off_gtin = off_gtin[1:]
            match = off.lookup_off_product_by_gtin(off_gtin)
            product = match.get('product') or {}
            if (match.get('status') == 'found' and product.get('gtin') == off_gtin
                    and name_compatible(row['product_name'], product.get('product_name', ''))
                    and compatible(item, product.get('product_name', ''), product.get('brand', ''))):
                row.update(product)
                row.update(source=source + ' + Open Food Facts', source_url=candidate['source_url'],
                           evidence_label='Winkelartikel en barcode gevonden in OFF', score=1.0)
            evidence['off_status'] = match.get('status')
        rows.append(row)
    if status == 'barcode_found':
        evidence.update(article_number=str(item.get('external_article_code') or ''), gtins=[rows[0]['gtin']])
        return _response(item, rows[:request['limit']], 'retailer_catalog', evidence)

    fallback = off.search_off_candidates_for_item(request, item)
    evidence['off_status'] = fallback.get('provider')
    if rows and fallback.get('provider') == 'unavailable':
        evidence['message'] += ' OFF is tijdelijk niet bereikbaar; de winkelresultaten blijven beschikbaar.'
    # Store suggestions do not acquire exact identity merely by ranking first.
    # Merge by validated GTIN; retain the observed store source over a fuzzy OFF hit.
    by_gtin = {row['gtin'].zfill(14): row for row in rows}
    for row in fallback['results']:
        if not valid_gtin(row.get('gtin')):
            continue
        key = row['gtin'].zfill(14)
        by_gtin.setdefault(key, dict(row, source='Open Food Facts', evidence_label='Suggestie op artikelnaam'))
    results = list(by_gtin.values())[:request['limit']]
    response = _response(item, results, 'retailer_catalog' if rows else fallback.get('provider'), evidence)
    response['query_diagnostics'] = fallback.get('query_diagnostics', [])
    return response

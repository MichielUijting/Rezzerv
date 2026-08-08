from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.services.external_retailer_taxonomy import build_off_query_terms
from app.services.product_taxonomy_store import normalize_taxonomy_text

OFF_SEARCH_PROVIDER = os.getenv("REZZERV_OFF_SEARCH_PROVIDER", "search_a_licious").strip() or "search_a_licious"
OFF_SEARCH_A_LICIOUS_BASE_URL = os.getenv("REZZERV_OFF_SEARCH_A_LICIOUS_BASE_URL", "https://search.openfoodfacts.org/search").strip()
OFF_SEARCH_BASE_URL = os.getenv("REZZERV_OFF_SEARCH_BASE_URL", "https://world.openfoodfacts.org/cgi/search.pl").strip()
OFF_SEARCH_TIMEOUT_SECONDS = float(os.getenv("REZZERV_OFF_SEARCH_TIMEOUT_SECONDS", "8") or 8)
OFF_SEARCH_MAX_RESULTS = 10
OFF_SEARCH_MAX_QUERIES = max(1, min(int(os.getenv("REZZERV_OFF_SEARCH_MAX_QUERIES", "3") or 3), 4))
OFF_SEARCH_FIELDS_LIST = [
    "code",
    "product_name",
    "product_name_nl",
    "brands",
    "quantity",
    "categories",
    "categories_tags",
    "countries",
    "countries_tags",
    "stores",
    "stores_tags",
    "image_front_small_url",
    "image_front_url",
]
OFF_SEARCH_FIELDS = ",".join(OFF_SEARCH_FIELDS_LIST)
FLAVORED_PRODUCT_TOKENS = {
    "aardbei",
    "aardbeien",
    "banaan",
    "bananen",
    "caramel",
    "choco",
    "chocolade",
    "cacao",
    "framboos",
    "frambozen",
    "hazelnoot",
    "koffie",
    "mokka",
    "stracciatella",
    "vanille",
    "yoghurt",
}


def _text(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(_text(item) for item in value if _text(item))
    return str(value or "").strip()


def _normalize(value: Any) -> str:
    normalized = _text(value).lower()
    normalized = normalized.replace(".", " ").replace("-", " ")
    normalized = re.sub(r"[^a-z0-9áéíóúàèìòùäëïöüâêîôûçñ\s]+", " ", normalized, flags=re.IGNORECASE)
    return " ".join(normalized.split())


def _tokens(value: Any) -> set[str]:
    return {token for token in _normalize(value).split() if len(token) >= 3}


def _candidate_name_without_retailer(candidate_name: str, retailer_code: str) -> str:
    normalized_candidate = _text(candidate_name)
    normalized_retailer = normalize_taxonomy_text(retailer_code)
    if not normalized_candidate or not normalized_retailer:
        return normalized_candidate
    candidate_norm = _normalize(normalized_candidate)
    retailer_norm = _normalize(normalized_retailer)
    if candidate_norm.startswith(f"{retailer_norm} "):
        return normalized_candidate.split(" ", 1)[1].strip()
    return normalized_candidate


def _unique_terms(values: list[str]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize(value)
        if not normalized or normalized in seen:
            continue
        terms.append(normalized)
        seen.add(normalized)
    return terms


def _rank_query_terms(search_terms: list[str], *, receipt_line_text: str = "") -> list[str]:
    normalized_receipt = _normalize(receipt_line_text)
    preferred = [term for term in search_terms if _normalize(term) != normalized_receipt]
    fallback = [term for term in search_terms if _normalize(term) == normalized_receipt]
    return sorted(preferred, key=lambda term: (-len(term.split()), -len(term), term)) + fallback


def build_off_search_terms(
    *,
    receipt_line_text: str,
    retailer_code: str,
    candidate_name: str | None = None,
    candidate_brand: str | None = None,
    category: str | None = None,
    product_type: str | None = None,
    quantity_label: str | None = None,
) -> list[str]:
    normalized_candidate_name = _candidate_name_without_retailer(candidate_name or "", retailer_code)
    taxonomy_terms = build_off_query_terms(receipt_line_text, retailer_code)
    return _unique_terms([
        f"{normalized_candidate_name} {product_type or ''} {category or ''}",
        f"{normalized_candidate_name} {product_type or ''}",
        f"{normalized_candidate_name} {category or ''}",
        f"{normalized_candidate_name} {quantity_label or ''}",
        normalized_candidate_name,
        candidate_brand or "",
        category or "",
        product_type or "",
        *taxonomy_terms,
        receipt_line_text,
    ])[:12]


def _off_product_url(code: str) -> str:
    normalized_code = _text(code)
    if not normalized_code:
        return ""
    return f"https://world.openfoodfacts.org/product/{urllib.parse.quote(normalized_code)}"


def _score_overlap(query_tokens: set[str], candidate_tokens: set[str]) -> float:
    if not query_tokens or not candidate_tokens:
        return 0.0
    overlap = query_tokens & candidate_tokens
    return max(len(overlap) / max(1, len(query_tokens)), len(overlap) / max(1, len(candidate_tokens)))


def _requested_product_text(payload: dict[str, Any]) -> str:
    return _text(payload.get("candidate_name") or payload.get("receipt_line_text") or payload.get("query"))


def _product_name_score(requested_text: str, product_name: str) -> float:
    requested_norm = _normalize(requested_text)
    product_norm = _normalize(product_name)
    if not requested_norm or not product_norm:
        return 0.0
    if requested_norm == product_norm:
        return 1.0
    if requested_norm in product_norm or product_norm in requested_norm:
        return 0.82
    return _score_overlap(_tokens(requested_norm), _tokens(product_norm))


def _flavored_mismatch_penalty(payload: dict[str, Any], product: dict[str, Any]) -> float:
    requested_tokens = _tokens(" ".join([
        _requested_product_text(payload),
        _text(payload.get("category")),
        _text(payload.get("product_type")),
    ]))
    product_name = _text(product.get("product_name_nl") or product.get("product_name"))
    product_tokens = _tokens(product_name)
    unexpected_flavor_tokens = (product_tokens & FLAVORED_PRODUCT_TOKENS) - requested_tokens
    if not unexpected_flavor_tokens:
        return 0.0
    return 0.35


def _score_off_product(product: dict[str, Any], search_terms: list[str], payload: dict[str, Any]) -> tuple[float, dict[str, float]]:
    product_name = _text(product.get("product_name_nl") or product.get("product_name"))
    requested_text = _requested_product_text(payload)
    name_score = _product_name_score(requested_text, product_name)

    brand_tokens = _tokens(payload.get("candidate_brand")) | _tokens(payload.get("retailer_code"))
    product_brand_tokens = _tokens(product.get("brands"))
    brand_score = _score_overlap(brand_tokens, product_brand_tokens) if brand_tokens else 0.0

    category_tokens = _tokens(" ".join([_text(payload.get("category")), _text(payload.get("product_type"))]))
    product_category_tokens = _tokens(product.get("categories")) | _tokens(" ".join(product.get("categories_tags") or []))
    category_score = _score_overlap(category_tokens, product_category_tokens) if category_tokens else 0.0

    quantity_tokens = _tokens(payload.get("quantity_label"))
    product_quantity_tokens = _tokens(product.get("quantity"))
    quantity_score = _score_overlap(quantity_tokens, product_quantity_tokens) if quantity_tokens else 0.0

    country_tokens = _tokens(product.get("countries")) | _tokens(" ".join(product.get("countries_tags") or []))
    store_tokens = _tokens(product.get("stores")) | _tokens(" ".join(product.get("stores_tags") or []))
    nl_score = 1.0 if ({"netherlands", "nederland", "nl"} & country_tokens) else 0.0
    retailer_score = _score_overlap(_tokens(payload.get("retailer_code")), store_tokens) if payload.get("retailer_code") else 0.0
    image_score = 1.0 if _text(product.get("image_front_small_url") or product.get("image_front_url")) else 0.0
    flavored_mismatch_penalty = _flavored_mismatch_penalty(payload, product)

    score = (
        name_score * 0.60
        + brand_score * 0.08
        + category_score * 0.10
        + quantity_score * 0.07
        + max(nl_score, retailer_score) * 0.10
        + image_score * 0.05
        - flavored_mismatch_penalty
    )
    score = round(min(max(score, 0.0), 1.0), 3)
    return score, {
        "name_score": round(name_score, 3),
        "brand_score": round(brand_score, 3),
        "category_score": round(category_score, 3),
        "quantity_score": round(quantity_score, 3),
        "market_or_store_score": round(max(nl_score, retailer_score), 3),
        "image_score": round(image_score, 3),
        "flavored_mismatch_penalty": round(flavored_mismatch_penalty, 3),
    }


def _normalize_off_product(product: dict[str, Any], search_terms: list[str], payload: dict[str, Any]) -> dict[str, Any] | None:
    code = _text(product.get("code") or product.get("id") or product.get("_id"))
    if not code:
        return None
    product_name = _text(product.get("product_name_nl") or product.get("product_name"))
    if not product_name:
        return None
    score, breakdown = _score_off_product(product, search_terms, payload)
    image_url = _text(product.get("image_front_small_url") or product.get("image_front_url"))
    return {
        "source_name": "open_food_facts",
        "source_product_code": code,
        "candidate_source_product_code": code,
        "code": code,
        "gtin": code,
        "ean": code,
        "barcode": code,
        "product_name": product_name,
        "candidate_name": product_name,
        "brands": _text(product.get("brands")),
        "candidate_brand": _text(product.get("brands")),
        "quantity": _text(product.get("quantity")),
        "quantity_label": _text(product.get("quantity")),
        "categories": _text(product.get("categories")),
        "countries": _text(product.get("countries")),
        "stores": _text(product.get("stores")),
        "image_url": image_url,
        "source_url": _off_product_url(code),
        "score": score,
        "score_breakdown": breakdown,
        "candidate_status": "off_candidate" if score >= 0.70 else "off_low_score_candidate",
        "has_real_barcode": True,
        "is_open_food_facts_result": True,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }


def _extract_search_a_licious_products(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    candidates = payload.get("products") or payload.get("items") or payload.get("results") or payload.get("documents") or payload.get("hits") or []
    if isinstance(candidates, dict):
        candidates = candidates.get("hits") or candidates.get("items") or candidates.get("results") or []
    products: list[dict[str, Any]] = []
    if not isinstance(candidates, list):
        return products
    for item in candidates:
        if not isinstance(item, dict):
            continue
        source = item.get("_source") or item.get("source") or item.get("document") or item.get("data") or item
        if isinstance(source, dict):
            products.append(source)
    return products


def _query_search_a_licious(search_term: str, page_size: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    request_payload = {
        "q": search_term,
        "page_size": max(1, min(page_size, OFF_SEARCH_MAX_RESULTS)),
        "page": 1,
        "fields": OFF_SEARCH_FIELDS_LIST,
        "langs": ["nl", "en"],
        "boost_phrase": True,
    }
    request = urllib.request.Request(
        OFF_SEARCH_A_LICIOUS_BASE_URL,
        data=json.dumps(request_payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Rezzerv OFF search preview",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=OFF_SEARCH_TIMEOUT_SECONDS) as response:
        http_status = getattr(response, "status", None) or response.getcode()
        payload = json.loads(response.read().decode("utf-8"))
    products = _extract_search_a_licious_products(payload)
    return products, {
        "provider": "search_a_licious",
        "http_status": http_status,
        "url": OFF_SEARCH_A_LICIOUS_BASE_URL,
        "raw_count": len(products),
    }


def _query_legacy_cgi(search_term: str, page_size: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    params = {
        "search_terms": search_term,
        "search_simple": "1",
        "action": "process",
        "json": "1",
        "page_size": str(max(1, min(page_size, OFF_SEARCH_MAX_RESULTS))),
        "fields": OFF_SEARCH_FIELDS,
    }
    url = f"{OFF_SEARCH_BASE_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "Rezzerv OFF search preview"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=OFF_SEARCH_TIMEOUT_SECONDS) as response:
        http_status = getattr(response, "status", None) or response.getcode()
        payload = json.loads(response.read().decode("utf-8"))
    products = payload.get("products") or []
    return [product for product in products if isinstance(product, dict)], {
        "provider": "legacy_cgi",
        "http_status": http_status,
        "url": url,
        "raw_count": len(products),
    }


def _query_provider_with_fallback(search_term: str, page_size: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    diagnostics: list[dict[str, Any]] = []
    errors: list[str] = []
    providers = ["search_a_licious", "legacy_cgi"] if OFF_SEARCH_PROVIDER == "search_a_licious" else ["legacy_cgi"]
    for provider in providers:
        try:
            if provider == "search_a_licious":
                products, diagnostic = _query_search_a_licious(search_term, page_size)
            else:
                products, diagnostic = _query_legacy_cgi(search_term, page_size)
            diagnostics.append({"search_term": search_term, **diagnostic})
            return products, diagnostics, errors
        except urllib.error.HTTPError as exc:
            errors.append(f"OFF {provider} HTTP-fout voor '{search_term}': {exc.code}")
            continue
        except Exception as exc:  # pragma: no cover - network dependent
            errors.append(f"OFF {provider} zoekfout voor '{search_term}': {exc}")
            continue
    return [], diagnostics, errors


def search_open_food_facts_preview(payload: dict[str, Any]) -> dict[str, Any]:
    receipt_line_text = _text(payload.get("receipt_line_text") or payload.get("query"))
    retailer_code = normalize_taxonomy_text(payload.get("retailer_code"))
    if not receipt_line_text:
        return {
            "ok": False,
            "error": "receipt_line_text is verplicht",
            "results": [],
            "creates_global_product": False,
            "creates_household_article": False,
            "creates_inventory_event": False,
        }
    manual_search_text = _text(payload.get("candidate_name"))
    is_manual_search = _text(payload.get("source")).lower() == "manual_off_search" and bool(manual_search_text)

    # OFF_HANDMATIGE_ZOEKOPDRACHT_STRIKT:
    # Een handmatige zoekactie gebruikt uitsluitend de door de gebruiker
    # ingevoerde zoektekst. Taxonomie-, merk- en bonregelvarianten mogen deze
    # expliciete zoekopdracht niet vervangen of verbreden.
    if is_manual_search:
        search_terms = _unique_terms([manual_search_text])
    else:
        search_terms = build_off_search_terms(
            receipt_line_text=receipt_line_text,
            retailer_code=retailer_code,
            candidate_name=manual_search_text,
            candidate_brand=_text(payload.get("candidate_brand")),
            category=_text(payload.get("category")),
            product_type=_text(payload.get("product_type")),
            quantity_label=_text(payload.get("quantity_label")),
        )
    limit = max(1, min(int(payload.get("limit") or 5), OFF_SEARCH_MAX_RESULTS))
    requested_query_limit = int(payload.get("max_queries") or OFF_SEARCH_MAX_QUERIES)
    query_limit = max(1, min(requested_query_limit, OFF_SEARCH_MAX_QUERIES))
    query_terms = _rank_query_terms([term for term in search_terms if term], receipt_line_text=receipt_line_text)[:query_limit]
    if not query_terms:
        query_terms = [_normalize(receipt_line_text)]
    results_by_code: dict[str, dict[str, Any]] = {}
    diagnostics: list[dict[str, Any]] = []
    errors: list[str] = []
    for term in query_terms:
        products, term_diagnostics, term_errors = _query_provider_with_fallback(term, page_size=limit)
        diagnostics.extend(term_diagnostics)
        errors.extend(term_errors)
        for product in products:
            normalized = _normalize_off_product(product, search_terms, payload)
            if not normalized:
                continue

            # Bij een handmatige zoekopdracht moet de productnaam inhoudelijk
            # overeenkomen met de ingevoerde tekst. Providerresultaten zonder
            # woordoverlap worden niet als kandidaat getoond.
            if is_manual_search:
                name_score = float((normalized.get("score_breakdown") or {}).get("name_score") or 0)
                if name_score <= 0:
                    continue

            existing = results_by_code.get(normalized["code"])
            if not existing or float(normalized.get("score") or 0) > float(existing.get("score") or 0):
                results_by_code[normalized["code"]] = normalized
    results = sorted(results_by_code.values(), key=lambda item: (-float(item.get("score") or 0), item.get("product_name") or ""))[:limit]
    external_source_available = bool(diagnostics)
    status = "found" if results else ("no_results" if external_source_available else "external_source_unavailable")
    provider_names = []
    for diagnostic in diagnostics:
        provider = diagnostic.get("provider")
        if provider and provider not in provider_names:
            provider_names.append(provider)
    return {
        "ok": True,
        "source_name": "open_food_facts",
        "mode": "read_only_search_preview",
        "status": status,
        "external_source_available": external_source_available,
        "provider": OFF_SEARCH_PROVIDER,
        "providers_used": provider_names,
        "receipt_line_text": receipt_line_text,
        "retailer_code": retailer_code,
        "search_terms": search_terms,
        "queried_terms": query_terms,
        "query_limit": query_limit,
        "timeout_seconds": OFF_SEARCH_TIMEOUT_SECONDS,
        "results": results,
        "result_count": len(results),
        "diagnostics": diagnostics,
        "errors": errors,
        "requires_user_selection": True,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }

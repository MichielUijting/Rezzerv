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

OFF_SEARCH_BASE_URL = os.getenv("REZZERV_OFF_SEARCH_BASE_URL", "https://world.openfoodfacts.org/cgi/search.pl").strip()
OFF_SEARCH_TIMEOUT_SECONDS = float(os.getenv("REZZERV_OFF_SEARCH_TIMEOUT_SECONDS", "4.0") or 4.0)
OFF_SEARCH_MAX_RESULTS = 10
OFF_SEARCH_FIELDS = ",".join([
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
])


def _text(value: Any) -> str:
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
    """Build a conservative OFF text-search profile from a Rezzerv candidate.

    These terms are query hints only. They are not article numbers and must never
    be presented as barcode/GTIN evidence.
    """
    normalized_candidate_name = _candidate_name_without_retailer(candidate_name or "", retailer_code)
    taxonomy_terms = build_off_query_terms(receipt_line_text, retailer_code)
    return _unique_terms([
        normalized_candidate_name,
        f"{normalized_candidate_name} {product_type or ''}",
        f"{normalized_candidate_name} {category or ''}",
        f"{normalized_candidate_name} {product_type or ''} {category or ''}",
        f"{normalized_candidate_name} {quantity_label or ''}",
        candidate_brand or "",
        category or "",
        product_type or "",
        receipt_line_text,
        *taxonomy_terms,
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
    return max(
        len(overlap) / max(1, len(query_tokens)),
        len(overlap) / max(1, len(candidate_tokens)),
    )


def _score_off_product(product: dict[str, Any], search_terms: list[str], payload: dict[str, Any]) -> tuple[float, dict[str, float]]:
    query_text = " ".join([
        *search_terms,
        _text(payload.get("candidate_name")),
        _text(payload.get("category")),
        _text(payload.get("product_type")),
    ])
    query_tokens = _tokens(query_text)
    product_name = _text(product.get("product_name_nl") or product.get("product_name"))
    product_tokens = _tokens(" ".join([
        product_name,
        _text(product.get("brands")),
        _text(product.get("categories")),
        _text(product.get("quantity")),
    ]))

    text_score = _score_overlap(query_tokens, product_tokens)

    brand_tokens = _tokens(payload.get("candidate_brand")) | _tokens(payload.get("retailer_code"))
    product_brand_tokens = _tokens(product.get("brands"))
    brand_score = _score_overlap(brand_tokens, product_brand_tokens) if brand_tokens else 0.0

    category_tokens = _tokens(" ".join([_text(payload.get("category")), _text(payload.get("product_type"))]))
    product_category_tokens = _tokens(product.get("categories"))
    category_score = _score_overlap(category_tokens, product_category_tokens) if category_tokens else 0.0

    quantity_tokens = _tokens(payload.get("quantity_label"))
    product_quantity_tokens = _tokens(product.get("quantity"))
    quantity_score = _score_overlap(quantity_tokens, product_quantity_tokens) if quantity_tokens else 0.0

    country_tokens = _tokens(product.get("countries")) | _tokens(" ".join(product.get("countries_tags") or []))
    store_tokens = _tokens(product.get("stores")) | _tokens(" ".join(product.get("stores_tags") or []))
    nl_score = 1.0 if ({"netherlands", "nederland", "nl"} & country_tokens) else 0.0
    retailer_score = _score_overlap(_tokens(payload.get("retailer_code")), store_tokens) if payload.get("retailer_code") else 0.0
    image_score = 1.0 if _text(product.get("image_front_small_url") or product.get("image_front_url")) else 0.0

    score = (
        text_score * 0.44
        + brand_score * 0.16
        + category_score * 0.16
        + quantity_score * 0.08
        + max(nl_score, retailer_score) * 0.10
        + image_score * 0.06
    )
    breakdown = {
        "text_score": round(text_score, 3),
        "brand_score": round(brand_score, 3),
        "category_score": round(category_score, 3),
        "quantity_score": round(quantity_score, 3),
        "market_or_store_score": round(max(nl_score, retailer_score), 3),
        "image_score": round(image_score, 3),
    }
    return round(min(max(score, 0.0), 1.0), 3), breakdown


def _normalize_off_product(product: dict[str, Any], search_terms: list[str], payload: dict[str, Any]) -> dict[str, Any] | None:
    code = _text(product.get("code"))
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


def _query_off(search_term: str, page_size: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
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
        headers={
            "Accept": "application/json",
            "User-Agent": "Rezzerv/dev (M2C2i-25 OFF search preview)",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=OFF_SEARCH_TIMEOUT_SECONDS) as response:
        http_status = getattr(response, "status", None) or response.getcode()
        payload = json.loads(response.read().decode("utf-8"))
    products = payload.get("products") or []
    return [product for product in products if isinstance(product, dict)], {
        "http_status": http_status,
        "url": url,
        "raw_count": len(products),
    }


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

    search_terms = build_off_search_terms(
        receipt_line_text=receipt_line_text,
        retailer_code=retailer_code,
        candidate_name=_text(payload.get("candidate_name")),
        candidate_brand=_text(payload.get("candidate_brand")),
        category=_text(payload.get("category")),
        product_type=_text(payload.get("product_type")),
        quantity_label=_text(payload.get("quantity_label")),
    )
    limit = max(1, min(int(payload.get("limit") or 5), OFF_SEARCH_MAX_RESULTS))
    query_terms = [term for term in search_terms if term][:4]
    if not query_terms:
        query_terms = [_normalize(receipt_line_text)]

    results_by_code: dict[str, dict[str, Any]] = {}
    diagnostics: list[dict[str, Any]] = []
    errors: list[str] = []

    for term in query_terms:
        try:
            products, diagnostic = _query_off(term, page_size=limit)
            diagnostics.append({"search_term": term, **diagnostic})
        except urllib.error.HTTPError as exc:
            errors.append(f"OFF HTTP-fout voor '{term}': {exc.code}")
            continue
        except Exception as exc:  # pragma: no cover - netwerkafhankelijk
            errors.append(f"OFF zoekfout voor '{term}': {exc}")
            continue

        for product in products:
            normalized = _normalize_off_product(product, search_terms, payload)
            if not normalized:
                continue
            existing = results_by_code.get(normalized["code"])
            if not existing or float(normalized.get("score") or 0) > float(existing.get("score") or 0):
                results_by_code[normalized["code"]] = normalized

    results = sorted(results_by_code.values(), key=lambda item: (-float(item.get("score") or 0), item.get("product_name") or ""))[:limit]
    return {
        "ok": True,
        "source_name": "open_food_facts",
        "mode": "read_only_search_preview",
        "receipt_line_text": receipt_line_text,
        "retailer_code": retailer_code,
        "search_terms": search_terms,
        "queried_terms": query_terms,
        "results": results,
        "result_count": len(results),
        "diagnostics": diagnostics,
        "errors": errors,
        "requires_user_selection": True,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }

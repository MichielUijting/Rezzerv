from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
import uuid
from typing import Any

from sqlalchemy import text

from app.db import engine


SEARCH_A_LICIOUS_URL = os.getenv(
    "REZZERV_OFF_SEARCH_A_LICIOUS_BASE_URL",
    "https://search.openfoodfacts.org/search",
).strip()
LEGACY_CGI_URL = os.getenv(
    "REZZERV_OFF_SEARCH_BASE_URL",
    "https://world.openfoodfacts.org/cgi/search.pl",
).strip()
TIMEOUT_SECONDS = float(os.getenv("REZZERV_OFF_SEARCH_TIMEOUT_SECONDS", "8") or 8)

OFF_FIELDS = [
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


class OffSearchError(ValueError):
    pass


def _text(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(_text(item) for item in value if _text(item))
    return str(value or "").strip()


def _normalize(value: Any) -> str:
    normalized = _text(value).lower().replace(".", " ").replace("-", " ")
    normalized = re.sub(
        r"[^a-z0-9áéíóúàèìòùäëïöüâêîôûçñ\s]+",
        " ",
        normalized,
        flags=re.IGNORECASE,
    )
    return " ".join(normalized.split())


def _tokens(value: Any) -> set[str]:
    return {token for token in _normalize(value).split() if len(token) >= 3}


def _table_exists(conn, table_name: str) -> bool:
    dialect = str(engine.dialect.name or "").lower()
    if dialect == "sqlite":
        return conn.execute(
            text("SELECT name FROM sqlite_master WHERE type = 'table' AND name = :name"),
            {"name": table_name},
        ).first() is not None
    return conn.execute(
        text(
            '''
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = :name
            LIMIT 1
            '''
        ),
        {"name": table_name},
    ).first() is not None


def _resolve_purchase_import_line(conn, source_id: str) -> dict[str, Any] | None:
    if not _table_exists(conn, "purchase_import_lines"):
        return None
    row = conn.execute(
        text(
            '''
            SELECT
                pil.id AS source_id,
                pil.article_name_raw AS receipt_line_text,
                pil.external_article_code AS external_article_code,
                pil.brand_raw AS brand,
                pil.quantity_raw AS quantity,
                pil.unit_raw AS unit,
                pib.raw_payload AS batch_raw_payload
            FROM purchase_import_lines pil
            LEFT JOIN purchase_import_batches pib ON pib.id = pil.batch_id
            WHERE pil.id = :source_id
            LIMIT 1
            '''
        ),
        {"source_id": source_id},
    ).mappings().first()
    if not row:
        return None

    retailer = ""
    raw_payload = row.get("batch_raw_payload")
    if raw_payload:
        try:
            payload = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            metadata = payload.get("batch_metadata") if isinstance(payload.get("batch_metadata"), dict) else {}
            retailer = _text(
                metadata.get("store_name")
                or metadata.get("store_label")
                or payload.get("store_name")
                or payload.get("store_label")
                or payload.get("retailer_code")
                or payload.get("retailer")
            )

    return {
        "receipt_item_type": "purchase_import_line",
        "receipt_item_source_id": source_id,
        "receipt_line_text": _text(row.get("receipt_line_text") or row.get("external_article_code")),
        "retailer_code": retailer,
        "brand": _text(row.get("brand")),
        "quantity_label": " ".join(
            value for value in (_text(row.get("quantity")), _text(row.get("unit"))) if value
        ),
    }


def _resolve_receipt_line(conn, source_id: str) -> dict[str, Any] | None:
    if not _table_exists(conn, "receipt_lines"):
        return None
    row = conn.execute(
        text(
            '''
            SELECT
                rl.id AS source_id,
                COALESCE(NULLIF(rl.parsed_name, ''), rl.raw_text) AS receipt_line_text,
                COALESCE(rl.parsed_quantity, '') AS quantity,
                COALESCE(rl.parsed_unit, '') AS unit,
                COALESCE(r.store_name, '') AS retailer_code
            FROM receipt_lines rl
            LEFT JOIN receipts r ON r.id = rl.receipt_id
            WHERE rl.id = :source_id
            LIMIT 1
            '''
        ),
        {"source_id": source_id},
    ).mappings().first()
    if not row:
        return None
    return {
        "receipt_item_type": "receipt_line",
        "receipt_item_source_id": source_id,
        "receipt_line_text": _text(row.get("receipt_line_text")),
        "retailer_code": _text(row.get("retailer_code")),
        "brand": "",
        "quantity_label": " ".join(
            value for value in (_text(row.get("quantity")), _text(row.get("unit"))) if value
        ),
    }


def _resolve_receipt_table_line(conn, source_id: str) -> dict[str, Any] | None:
    if not _table_exists(conn, "receipt_table_lines") or not _table_exists(conn, "receipt_tables"):
        return None
    row = conn.execute(
        text(
            '''
            SELECT
                rtl.id AS source_id,
                COALESCE(NULLIF(rtl.raw_label, ''), rtl.normalized_label) AS receipt_line_text,
                COALESCE(rtl.quantity, '') AS quantity,
                COALESCE(rtl.unit, '') AS unit,
                COALESCE(rt.store_name, '') AS retailer_code
            FROM receipt_table_lines rtl
            JOIN receipt_tables rt ON rt.id = rtl.receipt_table_id
            WHERE rtl.id = :source_id
            LIMIT 1
            '''
        ),
        {"source_id": source_id},
    ).mappings().first()
    if not row:
        return None
    return {
        "receipt_item_type": "receipt_table_line",
        "receipt_item_source_id": source_id,
        "receipt_line_text": _text(row.get("receipt_line_text")),
        "retailer_code": _text(row.get("retailer_code")),
        "brand": "",
        "quantity_label": " ".join(
            value for value in (_text(row.get("quantity")), _text(row.get("unit"))) if value
        ),
    }


def resolve_receipt_item(receipt_item_id: str) -> dict[str, Any]:
    normalized_id = _text(receipt_item_id)
    if ":" not in normalized_id:
        raise OffSearchError("Ongeldige receipt_item_id")

    prefix, source_id = normalized_id.split(":", 1)
    source_id = source_id.strip()
    if not source_id:
        raise OffSearchError("Ongeldige receipt_item_id")

    resolvers = {
        "purchase-import-line": _resolve_purchase_import_line,
        "receipt-line": _resolve_receipt_line,
        "receipt-table-line": _resolve_receipt_table_line,
    }
    resolver = resolvers.get(prefix)
    if resolver is None:
        raise OffSearchError("Onbekend receipt_item_type")

    with engine.begin() as conn:
        item = resolver(conn, source_id)

    if not item:
        raise OffSearchError("Bonartikel niet gevonden")

    item["receipt_item_id"] = normalized_id
    return item


def _strip_retailer_prefix(receipt_text: str, retailer_code: str) -> str:
    text_value = _text(receipt_text)
    retailer = _normalize(retailer_code)
    normalized_text = _normalize(text_value)
    if retailer and normalized_text.startswith(f"{retailer} "):
        parts = text_value.split(maxsplit=1)
        return parts[1].strip() if len(parts) == 2 else text_value
    return text_value


def _extract_products(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    candidates = (
        payload.get("products")
        or payload.get("items")
        or payload.get("results")
        or payload.get("documents")
        or payload.get("hits")
        or []
    )
    if isinstance(candidates, dict):
        candidates = candidates.get("hits") or candidates.get("items") or candidates.get("results") or []
    if not isinstance(candidates, list):
        return []

    products: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        source = item.get("_source") or item.get("source") or item.get("document") or item.get("data") or item
        if isinstance(source, dict):
            products.append(source)
    return products


def _query_search_a_licious(query: str, page_size: int) -> tuple[list[dict[str, Any]], str]:
    request_payload = {
        "q": query,
        "page_size": page_size,
        "page": 1,
        "fields": OFF_FIELDS,
        "langs": ["nl", "en"],
        "boost_phrase": True,
    }
    request = urllib.request.Request(
        SEARCH_A_LICIOUS_URL,
        data=json.dumps(request_payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Rezzerv OFF search v2",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return _extract_products(payload), "search_a_licious"


def _query_legacy_cgi(query: str, page_size: int) -> tuple[list[dict[str, Any]], str]:
    params = {
        "search_terms": query,
        "search_simple": "1",
        "action": "process",
        "json": "1",
        "page_size": str(page_size),
        "fields": ",".join(OFF_FIELDS),
    }
    url = f"{LEGACY_CGI_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "Rezzerv OFF search v2"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return _extract_products(payload), "legacy_cgi"


def _query_off(query: str, page_size: int) -> tuple[list[dict[str, Any]], str]:
    errors: list[str] = []
    successful_provider = ""

    # OFF is aantoonbaar incidenteel onbereikbaar. Elke provider krijgt daarom
    # maximaal twee directe pogingen. Er wordt niet gewacht en er vindt geen
    # databasewijziging plaats.
    for provider in (_query_search_a_licious, _query_legacy_cgi):
        for attempt in (1, 2):
            try:
                products, provider_name = provider(query, page_size)
                successful_provider = successful_provider or provider_name
                if products:
                    return products, provider_name
                break
            except Exception as exc:
                errors.append(
                    f"{provider.__name__} poging {attempt}: {exc}"
                )

    if successful_provider:
        return [], successful_provider

    raise OffSearchError(
        "Open Food Facts is niet beschikbaar"
        + (f" ({'; '.join(errors)})" if errors else "")
    )


def _name_score(query: str, product_name: str) -> float:
    query_norm = _normalize(query)
    product_norm = _normalize(product_name)
    if not query_norm or not product_norm:
        return 0.0
    if query_norm == product_norm:
        return 1.0
    if query_norm in product_norm or product_norm in query_norm:
        return 0.9

    query_tokens = _tokens(query_norm)
    product_tokens = _tokens(product_norm)
    if not query_tokens or not product_tokens:
        return 0.0

    overlap = query_tokens & product_tokens
    if not overlap:
        return 0.0
    return len(overlap) / len(query_tokens)


def _score_product(
    *,
    query: str,
    retailer_code: str,
    quantity_label: str,
    product: dict[str, Any],
) -> tuple[float, dict[str, float]]:
    product_name = _text(product.get("product_name_nl") or product.get("product_name"))
    name = _name_score(query, product_name)
    required_match = 1.0 if _contains_required_product_tokens(query, product_name) else 0.0

    if name <= 0 or required_match <= 0:
        return 0.0, {
            "name": round(name, 3),
            "required_product_match": required_match,
            "brand": 0.0,
            "quantity": 0.0,
            "market": 0.0,
            "completeness": 0.0,
        }

    brand = _retailer_brand_affinity(retailer_code, product)

    requested_quantity = _tokens(quantity_label)
    product_quantity = _tokens(product.get("quantity"))
    quantity = (
        len(requested_quantity & product_quantity) / len(requested_quantity)
        if requested_quantity
        else 0.0
    )

    country_tokens = _tokens(product.get("countries")) | _tokens(product.get("countries_tags"))
    market = 1.0 if {"netherlands", "nederland"} & country_tokens else 0.0
    completeness = 1.0 if _text(
        product.get("image_front_small_url") or product.get("image_front_url")
    ) else 0.0

    score = round(
        min(
            1.0,
            name * 0.68
            + required_match * 0.12
            + brand * 0.10
            + quantity * 0.05
            + market * 0.03
            + completeness * 0.02,
        ),
        3,
    )
    return score, {
        "name": round(name, 3),
        "required_product_match": required_match,
        "brand": round(brand, 3),
        "quantity": round(quantity, 3),
        "market": round(market, 3),
        "completeness": round(completeness, 3),
    }


def _normalize_result(
    *,
    query: str,
    retailer_code: str,
    quantity_label: str,
    product: dict[str, Any],
) -> dict[str, Any] | None:
    gtin = _text(product.get("code") or product.get("id") or product.get("_id"))
    product_name = _text(product.get("product_name_nl") or product.get("product_name"))
    if not gtin or not product_name:
        return None
    if not (gtin.isdigit() and len(gtin) in {8, 12, 13, 14}):
        return None

    score, breakdown = _score_product(
        query=query,
        retailer_code=retailer_code,
        quantity_label=quantity_label,
        product=product,
    )
    if breakdown["name"] <= 0:
        return None

    return {
        "gtin": gtin,
        "product_name": product_name,
        "brand": _text(product.get("brands")),
        "quantity": _text(product.get("quantity")),
        "category": _text(product.get("categories")),
        "image_url": _text(product.get("image_front_small_url") or product.get("image_front_url")),
        "source_url": f"https://world.openfoodfacts.org/product/{urllib.parse.quote(gtin)}",
        "score": score,
        "score_breakdown": breakdown,
    }


AUTO_QUERY_STOPWORDS = {
    "jumbo", "ah", "albert", "heijn", "lidl", "plus", "aldi", "coop", "dirk",
    "deka", "dekamarkt", "hoogvliet", "spar", "vomar", "picnic",
    "rust", "vers", "verse", "bio", "biologisch", "mini", "groot", "klein",
    "pak", "zak", "doos", "fles", "blik", "pot", "stuks", "stuk",
}


def _automatic_query_variants(item: dict[str, Any]) -> list[dict[str, Any]]:
    receipt_text = _strip_retailer_prefix(
        item.get("receipt_line_text", ""),
        item.get("retailer_code", ""),
    )
    raw_tokens = [token for token in _normalize(receipt_text).split() if len(token) >= 3]
    core_tokens = [token for token in raw_tokens if token not in AUTO_QUERY_STOPWORDS]

    variants: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(kind: str, query: str, weight: float) -> None:
        normalized = _normalize(query)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        variants.append({"kind": kind, "query": normalized, "weight": weight})

    if len(core_tokens) >= 2:
        add("core_phrase", " ".join(core_tokens), 1.0)
    if len(raw_tokens) >= 2:
        add("clean_phrase", " ".join(raw_tokens), 0.9)
    if len(core_tokens) == 1:
        add("single_core", core_tokens[0], 0.55)
    elif len(core_tokens) >= 2:
        for token in core_tokens:
            add("single_core", token, 0.35)

    return variants[:5]


PRODUCT_MODIFIER_TOKENS = {
    "halfvolle",
    "halfvol",
    "magere",
    "mager",
    "volle",
    "vol",
    "verse",
    "vers",
    "bio",
    "biologisch",
    "rust",
    "naturel",
    "original",
    "klassiek",
    "classic",
    "licht",
    "light",
}

RETAILER_BRAND_ALIASES = {
    "jumbo": {"jumbo"},
    "lidl": {"lidl", "milbona", "deluxe", "chef select", "favorina"},
    "albert heijn": {"albert heijn", "ah"},
    "ah": {"albert heijn", "ah"},
    "aldi": {"aldi", "milsani"},
    "plus": {"plus"},
}


def _required_product_tokens(query: str) -> set[str]:
    query_tokens = _tokens(query)
    required = {
        token
        for token in query_tokens
        if token not in PRODUCT_MODIFIER_TOKENS
    }
    return required or query_tokens


def _contains_required_product_tokens(query: str, product_name: str) -> bool:
    required = _required_product_tokens(query)
    product_tokens = _tokens(product_name)
    return bool(required) and required.issubset(product_tokens)


def _retailer_brand_affinity(retailer_code: str, product: dict[str, Any]) -> float:
    retailer = _normalize(retailer_code)
    if not retailer:
        return 0.0

    aliases = RETAILER_BRAND_ALIASES.get(retailer, {retailer})
    candidate_text = _normalize(
        " ".join(
            [
                _text(product.get("brands")),
                _text(product.get("stores")),
                _text(product.get("stores_tags")),
            ]
        )
    )
    candidate_tokens = _tokens(candidate_text)

    for alias in aliases:
        alias_tokens = _tokens(alias)
        if alias_tokens and alias_tokens.issubset(candidate_tokens):
            return 1.0
    return 0.0


def _automatic_candidate_is_acceptable(candidate: dict[str, Any]) -> bool:
    phrase_hits = int(candidate.get("phrase_hits") or 0)
    total_hits = int(candidate.get("query_hits") or 0)
    exact_single_hits = int(candidate.get("exact_single_hits") or 0)
    best_name_score = float(candidate.get("best_name_score") or 0)
    best_score = float(candidate.get("best_score") or 0)

    if phrase_hits >= 1 and best_name_score >= 0.80 and best_score >= 0.70:
        return True

    if total_hits >= 2 and best_name_score >= 0.70 and best_score >= 0.70:
        return True

    if exact_single_hits >= 1 and best_name_score >= 1.0 and best_score >= 0.80:
        return True

    return False


def _automatic_search(item: dict[str, Any], limit: int) -> tuple[str, str, list[dict[str, Any]], list[dict[str, Any]]]:
    variants = _automatic_query_variants(item)
    if not variants:
        raise OffSearchError("Geen automatische zoektekst beschikbaar")

    aggregate: dict[str, dict[str, Any]] = {}
    providers: list[str] = []
    diagnostics: list[dict[str, Any]] = []
    successful_queries = 0

    for variant in variants:
        query = variant["query"]

        try:
            products, provider = _query_off(query, max(limit * 3, 10))
            successful_queries += 1
        except OffSearchError as exc:
            diagnostics.append(
                {
                    "kind": variant["kind"],
                    "query": query,
                    "provider": "error",
                    "raw_count": 0,
                    "accepted_count": 0,
                    "error": str(exc),
                }
            )
            continue

        if provider and provider not in providers:
            providers.append(provider)

        accepted_count = 0
        for product in products:
            result = _normalize_result(
                query=query,
                retailer_code=item.get("retailer_code", ""),
                quantity_label=item.get("quantity_label", ""),
                product=product,
            )
            if result is None:
                continue

            accepted_count += 1
            gtin = result["gtin"]
            entry = aggregate.setdefault(
                gtin,
                {
                    "result": result,
                    "query_hits": 0,
                    "phrase_hits": 0,
                    "exact_single_hits": 0,
                    "weighted_hits": 0.0,
                    "best_name_score": 0.0,
                    "best_score": 0.0,
                    "matched_queries": [],
                },
            )

            entry["query_hits"] += 1
            if variant["kind"] in {"core_phrase", "clean_phrase"}:
                entry["phrase_hits"] += 1

            current_name_score = float(
                result.get("score_breakdown", {}).get("name") or 0
            )
            if variant["kind"] == "single_core" and current_name_score >= 1.0:
                entry["exact_single_hits"] += 1

            entry["weighted_hits"] += float(variant["weight"])
            entry["best_name_score"] = max(
                entry["best_name_score"],
                current_name_score,
            )
            entry["best_score"] = max(
                entry["best_score"],
                float(result.get("score") or 0),
            )
            entry["matched_queries"].append(query)

            current = entry["result"]
            if float(result.get("score") or 0) > float(current.get("score") or 0):
                entry["result"] = result

        diagnostics.append(
            {
                "kind": variant["kind"],
                "query": query,
                "provider": provider,
                "raw_count": len(products),
                "accepted_count": accepted_count,
            }
        )

    ranked: list[dict[str, Any]] = []
    for entry in aggregate.values():
        if not _automatic_candidate_is_acceptable(entry):
            continue

        result = dict(entry["result"])
        result["automatic_evidence"] = {
            "query_hits": entry["query_hits"],
            "phrase_hits": entry["phrase_hits"],
            "exact_single_hits": entry["exact_single_hits"],
            "weighted_hits": round(entry["weighted_hits"], 3),
            "best_name_score": round(entry["best_name_score"], 3),
            "matched_queries": entry["matched_queries"],
        }
        result["automatic_rank_score"] = round(
            float(result.get("score") or 0) * 0.65
            + min(1.0, entry["weighted_hits"] / 1.5) * 0.20
            + min(1.0, entry["phrase_hits"]) * 0.15,
            3,
        )
        result["confidence"] = (
            "high"
            if result["automatic_rank_score"] >= 0.85
            else "medium"
            if result["automatic_rank_score"] >= 0.70
            else "low"
        )
        ranked.append(result)

    ranked.sort(
        key=lambda row: (
            float(row.get("automatic_rank_score") or 0),
            float(row.get("score") or 0),
            row.get("product_name", "").lower(),
        ),
        reverse=True,
    )

    primary_query = variants[0]["query"]

    if successful_queries == 0:
        return primary_query, "unavailable", [], diagnostics

    provider_label = ",".join(providers) if providers else "none"
    return primary_query, provider_label, ranked[:limit], diagnostics


def search_off_candidates(payload: dict[str, Any]) -> dict[str, Any]:
    receipt_item_id = _text(payload.get("receipt_item_id"))
    mode = _text(payload.get("mode") or "manual").lower()
    if mode not in {"manual", "automatic"}:
        raise OffSearchError("mode moet manual of automatic zijn")

    item = resolve_receipt_item(receipt_item_id)
    limit = max(1, min(int(payload.get("limit") or 10), 20))
    query_diagnostics: list[dict[str, Any]] = []

    if mode == "manual":
        query = _text(payload.get("query"))
        if not query:
            raise OffSearchError("query is verplicht bij handmatig zoeken")

        raw_products, provider = _query_off(query, max(limit * 3, 10))
        best_by_gtin: dict[str, dict[str, Any]] = {}
        for product in raw_products:
            result = _normalize_result(
                query=query,
                retailer_code=item.get("retailer_code", ""),
                quantity_label=item.get("quantity_label", ""),
                product=product,
            )
            if result is None:
                continue
            existing = best_by_gtin.get(result["gtin"])
            if existing is None or result["score"] > existing["score"]:
                best_by_gtin[result["gtin"]] = result

        results = sorted(
            best_by_gtin.values(),
            key=lambda row: (row["score"], row["product_name"].lower()),
            reverse=True,
        )[:limit]
    else:
        query, provider, results, query_diagnostics = _automatic_search(item, limit)

    return {
        "search_id": str(uuid.uuid4()),
        "receipt_item_id": receipt_item_id,
        "query": query,
        "mode": mode,
        "provider": provider,
        "results": results,
        "result_count": len(results),
        "status": "found" if results else "no_results",
        "query_diagnostics": query_diagnostics,
        "mutated": False,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
        "creates_external_candidate": False,
    }

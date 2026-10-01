"""Shared exact-GTIN lookup for public product sources.

This module is read-only. It never creates catalog products, household articles,
or inventory events. Callers decide if and when a verified result may be saved.
"""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.services.off_search_service import lookup_off_product_by_gtin

MYREALFOOD_PRODUCT_URL = "https://www.myrealfood.app/es/product/{gtin}"
DEFAULT_TIMEOUT_SECONDS = 6.0


def _digits(value: Any) -> str:
    return "".join(character for character in str(value or "").strip() if character.isdigit())


def _normalize_gtin(value: Any) -> str:
    normalized = _digits(value)
    return normalized if len(normalized) in {8, 12, 13, 14} else ""


def _clean_text(value: Any) -> str:
    return " ".join(html.unescape(str(value or "")).strip().split())


def _jsonld_products(value: Any) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            products.extend(_jsonld_products(item))
        return products
    if not isinstance(value, dict):
        return products
    type_value = value.get("@type")
    types = type_value if isinstance(type_value, list) else [type_value]
    if any(str(item or "").strip().lower() == "product" for item in types):
        products.append(value)
    for nested in value.values():
        if isinstance(nested, (dict, list)):
            products.extend(_jsonld_products(nested))
    return products


def _brand_text(value: Any) -> str:
    if isinstance(value, dict):
        return _clean_text(value.get("name"))
    if isinstance(value, list):
        for item in value:
            resolved = _brand_text(item)
            if resolved:
                return resolved
        return ""
    return _clean_text(value)


def _extract_myrealfood_product(page_html: str, gtin: str, source_url: str) -> dict[str, Any] | None:
    for match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        page_html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        raw_json = html.unescape(match.group(1)).strip()
        try:
            parsed = json.loads(raw_json)
        except Exception:
            continue
        for product in _jsonld_products(parsed):
            name = _clean_text(product.get("name"))
            if not name:
                continue
            product_gtin = _digits(
                product.get("gtin13")
                or product.get("gtin")
                or product.get("sku")
                or gtin
            )
            if product_gtin and product_gtin != gtin:
                continue
            image = product.get("image")
            if isinstance(image, list):
                image = next((item for item in image if str(item or "").strip()), "")
            return {
                "gtin": gtin,
                "product_name": name,
                "brand": _brand_text(product.get("brand")),
                "category": _clean_text(product.get("category")),
                "image_url": _clean_text(image),
                "source": "myrealfood",
                "source_url": source_url,
                "quality_score": 0.92,
            }

    title_match = re.search(
        r"<title[^>]*>(.*?)</title>",
        page_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not title_match:
        return None
    title = _clean_text(re.sub(r"<[^>]+>", " ", title_match.group(1)))
    if not title:
        return None

    # MyRealFood product pages currently expose titles such as
    # "Producto Curry Madrás - Vitasia". Keep this fallback intentionally strict:
    # an exact GTIN page plus a concrete product title is required.
    normalized_title = re.sub(r"^producto\s+", "", title, flags=re.IGNORECASE).strip()
    normalized_title = re.sub(r"\s*[|·]\s*myrealfood.*$", "", normalized_title, flags=re.IGNORECASE).strip()
    parts = [part.strip() for part in normalized_title.split(" - ") if part.strip()]
    if not parts:
        return None
    product_name = parts[0]
    brand = parts[1] if len(parts) >= 2 else ""
    if not product_name or product_name.lower() in {"myrealfood", "producto"}:
        return None
    return {
        "gtin": gtin,
        "product_name": product_name,
        "brand": brand,
        "category": "",
        "image_url": "",
        "source": "myrealfood",
        "source_url": source_url,
        "quality_score": 0.88,
    }


def lookup_myrealfood_product_by_gtin(gtin: Any) -> dict[str, Any]:
    """Look up one exact GTIN on MyRealFood without local mutation."""
    normalized_gtin = _normalize_gtin(gtin)
    if not normalized_gtin:
        return {
            "ok": False,
            "status": "invalid_gtin",
            "gtin": normalized_gtin,
            "product": None,
            "mutated": False,
        }

    source_url = MYREALFOOD_PRODUCT_URL.format(gtin=urllib.parse.quote(normalized_gtin))
    request = urllib.request.Request(
        source_url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "Inhuis/1.0 (exact GTIN product lookup)",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            status = int(getattr(response, "status", None) or response.getcode() or 200)
            page_html = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {
                "ok": True,
                "status": "not_found",
                "gtin": normalized_gtin,
                "product": None,
                "source": "myrealfood",
                "http_status": 404,
                "mutated": False,
            }
        return {
            "ok": True,
            "status": "external_source_unavailable",
            "gtin": normalized_gtin,
            "product": None,
            "source": "myrealfood",
            "http_status": exc.code,
            "error": str(exc),
            "mutated": False,
        }
    except Exception as exc:
        return {
            "ok": True,
            "status": "external_source_unavailable",
            "gtin": normalized_gtin,
            "product": None,
            "source": "myrealfood",
            "error": str(exc),
            "mutated": False,
        }

    product = _extract_myrealfood_product(page_html, normalized_gtin, source_url)
    if not product:
        return {
            "ok": True,
            "status": "not_found",
            "gtin": normalized_gtin,
            "product": None,
            "source": "myrealfood",
            "http_status": status,
            "mutated": False,
        }
    return {
        "ok": True,
        "status": "found",
        "gtin": normalized_gtin,
        "product": product,
        "source": "myrealfood",
        "http_status": status,
        "mutated": False,
    }


def lookup_exact_gtin_sources(gtin: Any) -> dict[str, Any]:
    """Try exact-GTIN public sources in deterministic order, without mutation."""
    normalized_gtin = _normalize_gtin(gtin)
    if not normalized_gtin:
        return {
            "ok": False,
            "status": "invalid_gtin",
            "gtin": normalized_gtin,
            "product": None,
            "sources": [],
            "mutated": False,
        }

    attempts: list[dict[str, Any]] = []
    off_result = lookup_off_product_by_gtin(normalized_gtin)
    attempts.append({
        "source": "open_food_facts",
        "status": off_result.get("status"),
        "product": off_result.get("product"),
    })
    if off_result.get("status") == "found" and off_result.get("product", {}).get("product_name"):
        return {
            "ok": True,
            "status": "found",
            "gtin": normalized_gtin,
            "product": off_result["product"],
            "matched_source": "open_food_facts",
            "sources": attempts,
            "mutated": False,
        }

    myrealfood_result = lookup_myrealfood_product_by_gtin(normalized_gtin)
    attempts.append({
        "source": "myrealfood",
        "status": myrealfood_result.get("status"),
        "product": myrealfood_result.get("product"),
    })
    if (
        myrealfood_result.get("status") == "found"
        and myrealfood_result.get("product", {}).get("product_name")
    ):
        return {
            "ok": True,
            "status": "found",
            "gtin": normalized_gtin,
            "product": myrealfood_result["product"],
            "matched_source": "myrealfood",
            "sources": attempts,
            "mutated": False,
        }

    return {
        "ok": True,
        "status": "not_found",
        "gtin": normalized_gtin,
        "product": None,
        "matched_source": None,
        "sources": attempts,
        "mutated": False,
    }

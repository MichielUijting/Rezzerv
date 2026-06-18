from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any

PROBABLE_CANDIDATE_THRESHOLD = 0.85
POSSIBLE_CANDIDATE_THRESHOLD = 0.70

SCORE_WEIGHTS = {
    "text_score": 0.30,
    "brand_score": 0.20,
    "product_type_score": 0.20,
    "quantity_score": 0.10,
    "variant_score": 0.10,
    "source_score": 0.10,
}


@dataclass(frozen=True)
class RetailerCandidateTemplate:
    candidate_name: str
    brand: str
    retailer_article_number: str
    product_type_terms: tuple[str, ...]
    quantity_label: str = ""
    variant: str = ""
    source_name: str = "lidl_product_group"
    source_url: str = ""
    source_score: float = 0.80


LIDL_TERM_LIBRARY: dict[str, tuple[str, ...]] = {
    "kruidenm": ("kruidenmix", "specerijenmix", "seasoning mix"),
    "mexicaanse": ("mexicaans", "mexican"),
    "taco saus": ("taco sauce", "sauce pour tacos"),
    "saus": ("sauce", "salsa"),
    "hot": ("scherp", "pikant"),
    "medium": ("mild", "middel"),
}

LIDL_HOUSE_BRANDS = (
    "Belbake",
    "Chef Select",
    "Culinea",
    "Dulano",
    "El Tequito",
    "Freeway",
    "Grafschafter",
    "Kanig",
    "Kania",
    "Milbona",
    "Snack Day",
)

LIDL_CANDIDATES = (
    RetailerCandidateTemplate(
        candidate_name="Kania Taco Specerijenmix",
        brand="Kania/Kanig",
        retailer_article_number="21175",
        product_type_terms=("mexicaanse kruidenmix", "taco specerijenmix", "taco seasoning", "kruidenmix"),
        quantity_label="25-35 g",
        variant="Taco",
        source_url="https://www.lidl.nl/p/mexicaanse-kruidenmix/p21175",
    ),
    RetailerCandidateTemplate(
        candidate_name="Kania Burrito Specerijenmix",
        brand="Kania/Kanig",
        retailer_article_number="21175",
        product_type_terms=("mexicaanse kruidenmix", "burrito specerijenmix", "burrito seasoning", "kruidenmix"),
        quantity_label="25-35 g",
        variant="Burrito",
        source_url="https://www.lidl.nl/p/mexicaanse-kruidenmix/p21175",
    ),
    RetailerCandidateTemplate(
        candidate_name="Kania Fajita Specerijenmix",
        brand="Kania/Kanig",
        retailer_article_number="21175",
        product_type_terms=("mexicaanse kruidenmix", "fajita specerijenmix", "fajita seasoning", "kruidenmix"),
        quantity_label="25-35 g",
        variant="Fajita",
        source_url="https://www.lidl.nl/p/mexicaanse-kruidenmix/p21175",
    ),
    RetailerCandidateTemplate(
        candidate_name="El Tequito Taco Sauce hot",
        brand="El Tequito",
        retailer_article_number="20122386",
        product_type_terms=("taco saus", "taco sauce", "sauce pour tacos", "hot sauce"),
        quantity_label="215 ml / 230 g",
        variant="Hot",
        source_name="lidl_product_candidate",
        source_score=0.85,
    ),
    RetailerCandidateTemplate(
        candidate_name="El Tequito Taco Sauce",
        brand="El Tequito",
        retailer_article_number="20122393",
        product_type_terms=("taco saus", "taco sauce", "sauce pour tacos", "salsa"),
        quantity_label="215 ml / 230 g",
        variant="",
        source_name="lidl_product_candidate",
        source_score=0.85,
    ),
)

RETAILER_CONFIG = {
    "lidl": {
        "retailer_code": "lidl",
        "retailer_name": "Lidl",
        "version": "external-databases-v1",
        "status": "active",
        "probable_candidate_threshold": PROBABLE_CANDIDATE_THRESHOLD,
        "possible_candidate_threshold": POSSIBLE_CANDIDATE_THRESHOLD,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
        "candidate_policy": "preview_only_until_user_confirmed_or_external_database_override",
        "term_library": LIDL_TERM_LIBRARY,
        "house_brands": LIDL_HOUSE_BRANDS,
        "score_weights": SCORE_WEIGHTS,
        "supported_examples": ["Mexicaanse kruidenm.", "Taco saus"],
    }
}


def normalize_match_text(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    normalized = normalized.replace(".", " ")
    normalized = re.sub(r"[^a-z0-9áéíóúàèìòùäëïöüçñ\s-]+", " ", normalized, flags=re.IGNORECASE)
    return " ".join(normalized.split())


def expand_terms_for_retailer(receipt_line_text: str, retailer_code: str) -> list[str]:
    normalized = normalize_match_text(receipt_line_text)
    expanded = {normalized}
    config = RETAILER_CONFIG.get(retailer_code, {})
    term_library = config.get("term_library", {})
    for source_term, replacements in term_library.items():
        source_term_normalized = normalize_match_text(source_term)
        if source_term_normalized and source_term_normalized in normalized:
            for replacement in replacements:
                expanded.add(normalized.replace(source_term_normalized, normalize_match_text(replacement)))
                expanded.add(normalize_match_text(replacement))
    return [item for item in sorted(expanded) if item]


def _text_similarity(left: str, right: str) -> float:
    left_normalized = normalize_match_text(left)
    right_normalized = normalize_match_text(right)
    if not left_normalized or not right_normalized:
        return 0.0
    if left_normalized == right_normalized:
        return 1.0
    if left_normalized in right_normalized or right_normalized in left_normalized:
        return 0.92
    return difflib.SequenceMatcher(None, left_normalized, right_normalized).ratio()


def _best_text_score(expanded_terms: list[str], candidate: RetailerCandidateTemplate) -> float:
    values = [candidate.candidate_name, candidate.brand, candidate.variant, *candidate.product_type_terms]
    return max((_text_similarity(term, value) for term in expanded_terms for value in values), default=0.0)


def _brand_score(expanded_terms: list[str], candidate: RetailerCandidateTemplate) -> float:
    haystack = " ".join(expanded_terms)
    brand_tokens = [normalize_match_text(part) for part in re.split(r"[/,]", candidate.brand)]
    if any(token and token in haystack for token in brand_tokens):
        return 1.0
    if candidate.brand in {"Kania/Kanig", "El Tequito"}:
        return 0.86
    return 0.65


def _product_type_score(expanded_terms: list[str], candidate: RetailerCandidateTemplate) -> float:
    return max((_text_similarity(term, product_type) for term in expanded_terms for product_type in candidate.product_type_terms), default=0.0)


def _quantity_score(candidate: RetailerCandidateTemplate) -> float:
    return 0.80 if candidate.quantity_label else 0.50


def _variant_score(expanded_terms: list[str], candidate: RetailerCandidateTemplate) -> float:
    if not candidate.variant:
        return 0.75
    variant = normalize_match_text(candidate.variant)
    if any(variant and variant in term for term in expanded_terms):
        return 1.0
    # Lidl receipt lines often contain the product group but not the exact variant.
    if any("mexica" in term or "kruiden" in term for term in expanded_terms):
        return 0.82
    if any("taco" in term for term in expanded_terms) and variant == "hot":
        return 0.86
    return 0.70


def candidate_status_for_score(score: float) -> str:
    if score >= PROBABLE_CANDIDATE_THRESHOLD:
        return "probable_candidate"
    if score >= POSSIBLE_CANDIDATE_THRESHOLD:
        return "possible_candidate"
    return "weak_candidate"


def score_candidate(receipt_line_text: str, retailer_code: str, candidate: RetailerCandidateTemplate) -> dict[str, Any]:
    expanded_terms = expand_terms_for_retailer(receipt_line_text, retailer_code)
    breakdown = {
        "text_score": round(_best_text_score(expanded_terms, candidate), 3),
        "brand_score": round(_brand_score(expanded_terms, candidate), 3),
        "product_type_score": round(_product_type_score(expanded_terms, candidate), 3),
        "quantity_score": round(_quantity_score(candidate), 3),
        "variant_score": round(_variant_score(expanded_terms, candidate), 3),
        "source_score": round(candidate.source_score, 3),
    }
    score = sum(breakdown[key] * SCORE_WEIGHTS[key] for key in SCORE_WEIGHTS)
    score = round(score, 3)
    return {
        "candidate_name": candidate.candidate_name,
        "candidate_brand": candidate.brand,
        "candidate_source_name": candidate.source_name,
        "candidate_source_product_code": candidate.retailer_article_number,
        "retailer_article_number": candidate.retailer_article_number,
        "quantity_label": candidate.quantity_label,
        "variant": candidate.variant,
        "source_url": candidate.source_url,
        "score": score,
        "score_breakdown": breakdown,
        "candidate_status": candidate_status_for_score(score),
        "is_probable": score >= PROBABLE_CANDIDATE_THRESHOLD,
        "is_user_confirmed": False,
        "is_external_database_override": False,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
        "created_by": "external_database_lidl_matchpreview_v1",
    }


def match_retailer_receipt_line(retailer_code: str, receipt_line_text: str, include_below_threshold: bool = True) -> dict[str, Any]:
    normalized_retailer = normalize_match_text(retailer_code)
    if normalized_retailer not in RETAILER_CONFIG:
        return {
            "retailer_code": normalized_retailer,
            "receipt_line_text": receipt_line_text,
            "expanded_terms": [],
            "probable_candidate_threshold": PROBABLE_CANDIDATE_THRESHOLD,
            "candidates": [],
            "message": "Winkelketen wordt nog niet ondersteund in Externe databases v1.",
            "creates_global_product": False,
            "creates_household_article": False,
            "creates_inventory_event": False,
        }
    expanded_terms = expand_terms_for_retailer(receipt_line_text, normalized_retailer)
    scored = [score_candidate(receipt_line_text, normalized_retailer, candidate) for candidate in LIDL_CANDIDATES]
    if not include_below_threshold:
        scored = [candidate for candidate in scored if candidate["score"] >= PROBABLE_CANDIDATE_THRESHOLD]
    scored.sort(key=lambda item: (-item["score"], item["candidate_name"]))
    return {
        "retailer_code": normalized_retailer,
        "receipt_line_text": receipt_line_text,
        "expanded_terms": expanded_terms,
        "probable_candidate_threshold": PROBABLE_CANDIDATE_THRESHOLD,
        "possible_candidate_threshold": POSSIBLE_CANDIDATE_THRESHOLD,
        "candidates": scored,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }


def get_external_database_summary() -> dict[str, Any]:
    return {
        "module": "Externe databases",
        "version": "external-databases-v1",
        "supported_retailers": len(RETAILER_CONFIG),
        "active_retailers": [config["retailer_name"] for config in RETAILER_CONFIG.values() if config.get("status") == "active"],
        "candidate_policy": "preview_only_no_product_or_inventory_mutations",
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }


def list_external_database_retailers() -> list[dict[str, Any]]:
    return [
        {
            "retailer_code": code,
            "retailer_name": config["retailer_name"],
            "status": config["status"],
            "version": config["version"],
            "probable_candidate_threshold": config["probable_candidate_threshold"],
            "supported_examples": config["supported_examples"],
            "creates_global_product": False,
            "creates_household_article": False,
            "creates_inventory_event": False,
        }
        for code, config in RETAILER_CONFIG.items()
    ]


# M2C2i broad local OFF index matcher
_m2c2i_legacy_match_retailer_receipt_line = match_retailer_receipt_line


def _m2c2i_index_table_exists(conn) -> bool:
    from sqlalchemy import text as sql_text

    dialect_name = str(conn.engine.dialect.name or "").lower()
    if dialect_name == "sqlite":
        row = conn.execute(
            sql_text("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'external_product_index'")
        ).first()
        return row is not None

    row = conn.execute(
        sql_text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = 'external_product_index'
            LIMIT 1
            """
        )
    ).first()
    return row is not None


def _m2c2i_index_columns(conn) -> set[str]:
    from sqlalchemy import text as sql_text

    dialect_name = str(conn.engine.dialect.name or "").lower()
    if dialect_name == "sqlite":
        rows = conn.execute(sql_text("PRAGMA table_info(external_product_index)")).mappings().all()
        return {str(row.get("name") or "") for row in rows}

    rows = conn.execute(
        sql_text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'external_product_index'
            """
        )
    ).mappings().all()
    return {str(row.get("column_name") or "") for row in rows}


def _m2c2i_first_column(columns: set[str], names: list[str]) -> str | None:
    for name in names:
        if name in columns:
            return name
    return None


def _m2c2i_expr(columns: set[str], names: list[str], fallback: str = "''") -> str:
    column = _m2c2i_first_column(columns, names)
    if not column:
        return fallback
    return column


def _m2c2i_value(row: dict[str, Any], names: list[str]) -> str:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _m2c2i_numeric_tokens(value: str) -> set[str]:
    return set(re.findall(r"\d+(?:[,.]\d+)?", normalize_match_text(value)))


def _m2c2i_token_overlap_score(left: str, right: str) -> float:
    left_tokens = {token for token in normalize_match_text(left).split() if len(token) >= 3}
    right_tokens = {token for token in normalize_match_text(right).split() if len(token) >= 3}
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = left_tokens & right_tokens
    return len(overlap) / max(1, len(left_tokens | right_tokens))


def _m2c2i_score_index_candidate(receipt_line_text: str, row: dict[str, Any]) -> dict[str, Any]:
    product_name = _m2c2i_value(row, [
        "product_name",
        "name",
        "product_name_nl",
        "generic_name",
        "generic_name_nl",
        "brands_tags",
    ])
    brand = _m2c2i_value(row, ["brand", "brands", "manufacturer", "producer"])
    source_name = _m2c2i_value(row, ["source_name"]) or "OFF-index"
    source_product_code = _m2c2i_value(row, [
        "source_product_code",
        "gtin",
        "code",
        "barcode",
        "ean",
        "product_code",
    ])
    quantity_label = _m2c2i_value(row, [
        "quantity",
        "quantity_label",
        "net_content",
        "net_weight",
        "packaging",
        "serving_size",
    ])
    category = _m2c2i_value(row, [
        "category",
        "categories",
        "main_category",
        "pnns_groups_1",
        "pnns_groups_2",
    ])
    source_url = _m2c2i_value(row, ["source_url", "url", "product_url"])

    text_score = max(
        _text_similarity(receipt_line_text, product_name),
        _m2c2i_token_overlap_score(receipt_line_text, product_name),
    )

    normalized_receipt = normalize_match_text(receipt_line_text)
    normalized_brand = normalize_match_text(brand)
    if normalized_brand and normalized_brand in normalized_receipt:
        brand_score = 1.0
    elif normalized_brand:
        brand_score = max(0.55, _m2c2i_token_overlap_score(receipt_line_text, brand))
    else:
        brand_score = 0.40

    receipt_numbers = _m2c2i_numeric_tokens(receipt_line_text)
    quantity_numbers = _m2c2i_numeric_tokens(quantity_label)
    if receipt_numbers and quantity_numbers and receipt_numbers & quantity_numbers:
        quantity_score = 1.0
    elif quantity_label:
        quantity_score = 0.65
    else:
        quantity_score = 0.45

    normalized_code = normalize_match_text(source_product_code)
    if normalized_code and normalized_code in normalized_receipt:
        code_score = 1.0
    elif normalized_code:
        code_score = 0.55
    else:
        code_score = 0.35

    category_score = max(
        0.45,
        _m2c2i_token_overlap_score(receipt_line_text, category),
    ) if category else 0.40

    source_score = 0.92 if "off" in normalize_match_text(source_name) or source_name == "OFF-index" else 0.80

    breakdown = {
        "text_score": round(text_score, 3),
        "brand_score": round(brand_score, 3),
        "product_type_score": round(category_score, 3),
        "quantity_score": round(quantity_score, 3),
        "variant_score": 0.70,
        "source_score": round(source_score, 3),
        "code_score": round(code_score, 3),
        "category_score": round(category_score, 3),
    }

    # Bestaande gewichten blijven leidend; code/category zijn aanvullend.
    base_score = sum(breakdown[key] * SCORE_WEIGHTS[key] for key in SCORE_WEIGHTS)
    bonus = (code_score * 0.08) + (category_score * 0.04)
    score = round(min(1.0, base_score + bonus), 3)

    return {
        "candidate_name": product_name or source_product_code or "Onbekend OFF-product",
        "candidate_brand": brand,
        "candidate_source_name": source_name,
        "candidate_source_product_code": source_product_code or "unknown",
        "source_name": source_name,
        "source_product_code": source_product_code or "unknown",
        "retailer_article_number": source_product_code or "",
        "quantity_label": quantity_label,
        "variant": category,
        "source_url": source_url,
        "score": score,
        "score_breakdown": breakdown,
        "candidate_status": candidate_status_for_score(score),
        "is_probable": score >= PROBABLE_CANDIDATE_THRESHOLD,
        "is_user_confirmed": False,
        "is_external_database_override": False,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
        "created_by": "external_database_off_index_matcher_v1",
    }


def _m2c2i_query_index_candidates(receipt_line_text: str, limit: int = 80) -> list[dict[str, Any]]:
    from sqlalchemy import text as sql_text
    from app.db import engine

    normalized = normalize_match_text(receipt_line_text)
    tokens = [token for token in normalized.split() if len(token) >= 3]
    if not tokens:
        return []

    with engine.begin() as conn:
        if not _m2c2i_index_table_exists(conn):
            return []

        columns = _m2c2i_index_columns(conn)

        name_col = _m2c2i_expr(columns, ["product_name", "name", "product_name_nl", "generic_name", "generic_name_nl"])
        brand_col = _m2c2i_expr(columns, ["brand", "brands", "manufacturer", "producer"])
        code_col = _m2c2i_expr(columns, ["source_product_code", "gtin", "code", "barcode", "ean", "product_code"])
        category_col = _m2c2i_expr(columns, ["category", "categories", "main_category", "pnns_groups_1", "pnns_groups_2"])
        quantity_col = _m2c2i_expr(columns, ["quantity", "quantity_label", "net_content", "net_weight", "packaging", "serving_size"])
        source_col = _m2c2i_expr(columns, ["source_name"])
        url_col = _m2c2i_expr(columns, ["source_url", "url", "product_url"])

        search_expr = f"""
            lower(COALESCE(CAST({name_col} AS TEXT), '') || ' ' ||
                  COALESCE(CAST({brand_col} AS TEXT), '') || ' ' ||
                  COALESCE(CAST({code_col} AS TEXT), '') || ' ' ||
                  COALESCE(CAST({category_col} AS TEXT), '') || ' ' ||
                  COALESCE(CAST({quantity_col} AS TEXT), ''))
        """

        where_parts = []
        params: dict[str, Any] = {"limit": max(10, min(int(limit or 80), 200))}
        for index, token in enumerate(tokens[:8]):
            key = f"token_{index}"
            where_parts.append(f"{search_expr} LIKE :{key}")
            params[key] = f"%{token}%"

        where_sql = " OR ".join(where_parts)

        rows = conn.execute(
            sql_text(
                f"""
                SELECT *
                FROM external_product_index
                WHERE {where_sql}
                LIMIT :limit
                """
            ),
            params,
        ).mappings().all()

    return [dict(row) for row in rows]


def match_retailer_receipt_line(retailer_code: str, receipt_line_text: str, include_below_threshold: bool = True) -> dict[str, Any]:
    """M2C2i: zoek primair in lokale OFF-index; gebruik legacy Lidl-set alleen als fallback."""
    normalized_retailer = normalize_match_text(retailer_code)
    index_rows = _m2c2i_query_index_candidates(receipt_line_text, limit=120)

    scored = [_m2c2i_score_index_candidate(receipt_line_text, row) for row in index_rows]
    if not include_below_threshold:
        scored = [candidate for candidate in scored if candidate["score"] >= PROBABLE_CANDIDATE_THRESHOLD]

    scored.sort(key=lambda item: (-item["score"], item["candidate_name"]))
    scored = scored[:5]

    if scored:
        return {
            "retailer_code": normalized_retailer,
            "receipt_line_text": receipt_line_text,
            "expanded_terms": expand_terms_for_retailer(receipt_line_text, normalized_retailer) if normalized_retailer in RETAILER_CONFIG else [normalize_match_text(receipt_line_text)],
            "probable_candidate_threshold": PROBABLE_CANDIDATE_THRESHOLD,
            "possible_candidate_threshold": POSSIBLE_CANDIDATE_THRESHOLD,
            "candidates": scored,
            "candidate_source": "external_product_index",
            "uses_legacy_fallback": False,
            "creates_global_product": False,
            "creates_household_article": False,
            "creates_inventory_event": False,
        }

    if normalized_retailer != "lidl":
        return {
            "retailer_code": normalized_retailer,
            "receipt_line_text": receipt_line_text,
            "expanded_terms": [normalize_match_text(receipt_line_text)],
            "probable_candidate_threshold": PROBABLE_CANDIDATE_THRESHOLD,
            "possible_candidate_threshold": POSSIBLE_CANDIDATE_THRESHOLD,
            "candidates": [],
            "candidate_source": "no_retailer_specific_legacy_candidates",
            "uses_legacy_fallback": False,
            "creates_global_product": False,
            "creates_household_article": False,
            "creates_inventory_event": False,
        }

    legacy = _m2c2i_legacy_match_retailer_receipt_line(
        retailer_code=retailer_code,
        receipt_line_text=receipt_line_text,
        include_below_threshold=include_below_threshold,
    )
    legacy["candidate_source"] = "legacy_lidl_testset"
    legacy["uses_legacy_fallback"] = True
    return legacy


# M2C2i-2 generic OFF index matcher
from app.services.external_product_index_store import search_external_product_index_candidates

def _m2c2i2_build_lidl_taxonomy_preview(
    retailer_code: str,
    receipt_line_text: str,
    include_below_threshold: bool = True,
) -> dict[str, Any]:
    normalized_retailer = normalize_match_text(retailer_code)
    expanded_terms = expand_terms_for_retailer(receipt_line_text, normalized_retailer)

    scored = [
        score_candidate(receipt_line_text, normalized_retailer, candidate)
        for candidate in LIDL_CANDIDATES
    ]

    if not include_below_threshold:
        scored = [
            candidate
            for candidate in scored
            if candidate["score"] >= PROBABLE_CANDIDATE_THRESHOLD
        ]

    scored.sort(key=lambda item: (-item["score"], item["candidate_name"]))

    return {
        "retailer_code": normalized_retailer,
        "receipt_line_text": receipt_line_text,
        "expanded_terms": expanded_terms,
        "probable_candidate_threshold": PROBABLE_CANDIDATE_THRESHOLD,
        "possible_candidate_threshold": POSSIBLE_CANDIDATE_THRESHOLD,
        "candidates": scored,
        "candidate_source": "lidl_taxonomy",
        "uses_legacy_fallback": False,
        "uses_retailer_taxonomy_preview": True,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }


def _m2c2i2_value(row: dict[str, Any], names: list[str]) -> str:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _m2c2i2_numeric_tokens(value: str) -> set[str]:
    return set(re.findall(r"\d+(?:[,.]\d+)?", normalize_match_text(value)))


def _m2c2i2_token_overlap_score(left: str, right: str) -> float:
    left_tokens = {token for token in normalize_match_text(left).split() if len(token) >= 3}
    right_tokens = {token for token in normalize_match_text(right).split() if len(token) >= 3}
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = left_tokens & right_tokens
    return len(overlap) / max(1, len(left_tokens | right_tokens))


def _m2c2i2_score_candidate(receipt_line_text: str, row: dict[str, Any]) -> dict[str, Any]:
    product_name = _m2c2i2_value(row, ["product_name", "name", "generic_name"])
    brand = _m2c2i2_value(row, ["brand", "brands"])
    quantity_label = _m2c2i2_value(row, ["quantity", "net_content", "packaging"])
    category = _m2c2i2_value(row, ["category", "categories"])
    source_name = _m2c2i2_value(row, ["source_name"]) or "OFF-index"
    source_product_code = _m2c2i2_value(row, ["source_product_code", "gtin", "ean", "code"]) or "unknown"
    source_url = _m2c2i2_value(row, ["source_url", "url", "product_url"])

    text_score = max(
        _text_similarity(receipt_line_text, product_name),
        _m2c2i2_token_overlap_score(receipt_line_text, product_name),
    )

    normalized_receipt = normalize_match_text(receipt_line_text)
    normalized_brand = normalize_match_text(brand)
    brand_score = 1.0 if normalized_brand and normalized_brand in normalized_receipt else (0.60 if brand else 0.40)

    receipt_numbers = _m2c2i2_numeric_tokens(receipt_line_text)
    quantity_numbers = _m2c2i2_numeric_tokens(quantity_label)
    quantity_score = 1.0 if receipt_numbers and quantity_numbers and receipt_numbers & quantity_numbers else (0.65 if quantity_label else 0.45)

    normalized_code = normalize_match_text(source_product_code)
    code_score = 1.0 if normalized_code and normalized_code in normalized_receipt else (0.55 if source_product_code != "unknown" else 0.35)

    category_score = max(0.45, _m2c2i2_token_overlap_score(receipt_line_text, category)) if category else 0.40
    source_score = 0.92 if source_name == "OFF-index" else 0.80

    breakdown = {
        "text_score": round(text_score, 3),
        "brand_score": round(brand_score, 3),
        "product_type_score": round(category_score, 3),
        "quantity_score": round(quantity_score, 3),
        "variant_score": 0.70,
        "source_score": round(source_score, 3),
        "code_score": round(code_score, 3),
        "category_score": round(category_score, 3),
    }

    base_score = sum(breakdown[key] * SCORE_WEIGHTS[key] for key in SCORE_WEIGHTS)
    score = round(min(1.0, base_score + (code_score * 0.08) + (category_score * 0.04)), 3)

    return {
        "candidate_name": product_name or source_product_code,
        "candidate_brand": brand,
        "candidate_source_name": source_name,
        "candidate_source_product_code": source_product_code,
        "source_name": source_name,
        "source_product_code": source_product_code,
        "retailer_article_number": source_product_code,
        "quantity_label": quantity_label,
        "variant": category,
        "source_url": source_url,
        "score": score,
        "score_breakdown": breakdown,
        "candidate_status": candidate_status_for_score(score),
        "is_probable": score >= PROBABLE_CANDIDATE_THRESHOLD,
        "is_user_confirmed": False,
        "is_external_database_override": False,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
        "created_by": "external_database_off_index_matcher_v2",
    }


def match_retailer_receipt_line(retailer_code: str, receipt_line_text: str, include_below_threshold: bool = True) -> dict[str, Any]:
    normalized_retailer = normalize_match_text(retailer_code)
    index_rows = search_external_product_index_candidates(receipt_line_text, limit=120, retailer_code=normalized_retailer)

    scored = [_m2c2i2_score_candidate(receipt_line_text, row) for row in index_rows]
    if not include_below_threshold:
        scored = [candidate for candidate in scored if candidate["score"] >= PROBABLE_CANDIDATE_THRESHOLD]

    scored.sort(key=lambda item: (-item["score"], item["candidate_name"]))
    scored = scored[:5]

    if scored:
        return {
            "retailer_code": normalized_retailer,
            "receipt_line_text": receipt_line_text,
            "expanded_terms": [normalize_match_text(receipt_line_text)],
            "probable_candidate_threshold": PROBABLE_CANDIDATE_THRESHOLD,
            "possible_candidate_threshold": POSSIBLE_CANDIDATE_THRESHOLD,
            "candidates": scored,
            "candidate_source": "external_product_index",
            "uses_legacy_fallback": False,
            "creates_global_product": False,
            "creates_household_article": False,
            "creates_inventory_event": False,
        }

    if normalized_retailer != "lidl":
        return {
            "retailer_code": normalized_retailer,
            "receipt_line_text": receipt_line_text,
            "expanded_terms": [normalize_match_text(receipt_line_text)],
            "probable_candidate_threshold": PROBABLE_CANDIDATE_THRESHOLD,
            "possible_candidate_threshold": POSSIBLE_CANDIDATE_THRESHOLD,
            "candidates": [],
            "candidate_source": "no_retailer_specific_legacy_candidates",
            "uses_legacy_fallback": False,
            "creates_global_product": False,
            "creates_household_article": False,
            "creates_inventory_event": False,
        }

    return _m2c2i2_build_lidl_taxonomy_preview(
        retailer_code=retailer_code,
        receipt_line_text=receipt_line_text,
        include_below_threshold=include_below_threshold,
    )

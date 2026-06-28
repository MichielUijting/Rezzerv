"""
Technical Design Reference:
- TD Section: TD-03 Receipt ingestion en parsers
- Module Role: Receipt source parsing and data extraction
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: receipt_spaarzegels_terms.json
- Reads Data: managed dictionary data
- Writes Data: no
- Status Authority: no
- Refactor Status: classify
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

TERMS_PATH = Path(__file__).resolve().parents[1] / "data" / "receipt_spaarzegels_terms.json"
AMOUNT_RE = re.compile(r"(?<!\d)-?\d+[\.,]\d{2}(?!\d)")


def _as_tuple(values: Any) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(str(value).strip().lower() for value in values if str(value).strip())


@lru_cache(maxsize=1)
def load_spaarzegels_terms() -> dict[str, tuple[str, ...]]:
    try:
        payload = json.loads(TERMS_PATH.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    return {
        "metadata_tokens": _as_tuple(payload.get("metadata_tokens")),
        "priced_tokens": _as_tuple(payload.get("priced_tokens")),
        "value_label_patterns": _as_tuple(payload.get("value_label_patterns")),
        "non_product_label_tokens": _as_tuple(payload.get("non_product_label_tokens")),
    }


def spaarzegels_metadata_tokens() -> tuple[str, ...]:
    return load_spaarzegels_terms()["metadata_tokens"]


def spaarzegels_priced_tokens() -> tuple[str, ...]:
    return load_spaarzegels_terms()["priced_tokens"]


def spaarzegels_value_label_patterns() -> tuple[str, ...]:
    return load_spaarzegels_terms()["value_label_patterns"]


def spaarzegels_non_product_label_tokens() -> tuple[str, ...]:
    return load_spaarzegels_terms()["non_product_label_tokens"]


def _normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _combined_text(*values: str | None) -> str:
    return " ".join(_normalize_text(value) for value in values if str(value or "").strip()).strip()


def _has_amount(value: str | None) -> bool:
    return AMOUNT_RE.search(str(value or "")) is not None


def token_match_from_terms(value: str, tokens: tuple[str, ...]) -> str | None:
    lowered = str(value or "").lower()
    for token in tokens:
        if token and token in lowered:
            return token
    return None


def matches_spaarzegels_value_label(value: str) -> bool:
    normalized = _normalize_text(value)
    return any(re.fullmatch(pattern, normalized) for pattern in spaarzegels_value_label_patterns())


def contains_spaarzegels_metadata_token(value: str) -> str | None:
    return token_match_from_terms(value, spaarzegels_metadata_tokens())


def contains_spaarzegels_priced_token(value: str) -> str | None:
    return token_match_from_terms(value, spaarzegels_priced_tokens())


def contains_spaarzegels_non_product_token(value: str) -> bool:
    return token_match_from_terms(value, spaarzegels_non_product_label_tokens()) is not None


def is_spaarzegels_financial_line(value: str | None) -> bool:
    normalized = _normalize_text(value)
    if not normalized or not _has_amount(normalized):
        return False
    return contains_spaarzegels_priced_token(normalized) is not None


def is_spaarzegels_financial_pair(*, label_text: str | None, detail_text: str | None) -> bool:
    combined = _combined_text(label_text, detail_text)
    if not combined or not _has_amount(combined):
        return False
    return contains_spaarzegels_priced_token(combined) is not None


def spaarzegels_financial_metadata(
    value: str | None = None,
    *,
    label_text: str | None = None,
    detail_text: str | None = None,
) -> dict[str, Any]:
    combined = _combined_text(value, label_text, detail_text)
    matched = contains_spaarzegels_priced_token(combined)
    if not matched:
        return {}
    if value is not None and is_spaarzegels_financial_line(value):
        pass
    elif not is_spaarzegels_financial_pair(label_text=label_text, detail_text=detail_text):
        return {}
    return {
        "line_type": "spaarzegels",
        "is_spaarzegels": True,
        "include_in_receipt_total": True,
        "exclude_from_inventory": True,
        "external_matching_allowed": False,
        "matched_spaarzegels_term": matched,
    }

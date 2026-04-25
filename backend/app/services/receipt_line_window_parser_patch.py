"""Window-based receipt line parser patch.

This module replaces the legacy single-line receipt line extractor with a
slightly broader parser that can combine nearby label fragments with amount
lines. It is intentionally small and reversible.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from app.services import receipt_service as _svc

_ORIGINAL_EXTRACT_RECEIPT_LINES = _svc._extract_receipt_lines
_AMOUNT_AT_END_RE = re.compile(r"(?P<amount>-?\d{1,6}(?:[\.,]\d{2}))\s*(?:EUR|[A-Z]{1,3})?$", re.IGNORECASE)
_QTY_X_AMOUNT_RE = re.compile(
    r"(?P<label>.+?)\s+(?P<qty>\d+(?:[\.,]\d+)?)\s*[xX]\s+(?P<amount>-?\d{1,6}(?:[\.,]\d{2}))\s*(?:EUR|[A-Z]{1,3})?$",
    re.IGNORECASE,
)
_QTY_FIRST_RE = re.compile(
    r"^(?P<qty>\d+(?:[\.,]\d+)?(?:\s*kg)?)\s+(?P<label>.+?)\s+(?P<amount>-?\d{1,6}(?:[\.,]\d{2}))\s*(?:EUR|[A-Z]{1,3})?$",
    re.IGNORECASE,
)
_NOISE_TOKENS = {
    "totaal", "subtotaal", "te betalen", "betaling", "betaald", "bankpas", "pin", "pinnen",
    "contant", "wisselgeld", "btw", "kassa", "kassabon", "bonnr", "ticket", "filiaal",
    "terminal", "transactie", "autorisatie", "datum", "tijd", "kaart", "klant", "saldo",
}


def _normalize_line(value: Any) -> str:
    normalized = re.sub(r"\s+", " ", str(value or "")).strip()
    normalized = re.sub(r"(?<=\d)/(?!/)(?=\d{2}\b)", ",", normalized)
    normalized = re.sub(r"^[^A-Za-z0-9]+", "", normalized).strip()
    normalized = re.sub(r"[^A-Za-z0-9\.,%€\- ]+$", "", normalized).strip()
    return normalized


def _amount_to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _clean_label(value: str, *, store_name: str | None, filename: str | None) -> str | None:
    label = _svc._clean_receipt_label(value)
    if not label or len(label) < 2:
        return None
    if label.replace(" ", "").isdigit():
        return None
    lowered = label.lower()
    if any(token in lowered for token in _NOISE_TOKENS):
        return None
    if _svc._looks_like_non_product_receipt_label(label):
        return None
    if _svc._is_aldi_context(store_name=store_name, filename=filename) and _svc._is_invalid_aldi_article_candidate(label):
        return None
    return label[:180]


def _label_fragment(value: str, *, store_name: str | None, filename: str | None) -> str | None:
    normalized = _normalize_line(value)
    if not normalized or len(normalized) < 2:
        return None
    lowered = normalized.lower()
    if any(token in lowered for token in _NOISE_TOKENS):
        return None
    if re.search(r"\d{1,2}[/-]\d{1,2}[/-]\d{4}", normalized):
        return None
    if _AMOUNT_AT_END_RE.search(normalized):
        return None
    if _svc._should_skip_receipt_line(normalized, store_name=store_name, filename=filename):
        return None
    if not re.search(r"[A-Za-zÀ-ÿ]", normalized):
        return None
    if len(normalized.split()) > 8:
        return None
    return normalized


def _build_line(label: str, amount_raw: str, *, source_index: int, qty_raw: str | None = None, store_name: str | None = None, filename: str | None = None) -> dict[str, Any] | None:
    clean = _clean_label(label, store_name=store_name, filename=filename)
    amount = _svc._parse_decimal(amount_raw)
    quantity = _svc._parse_quantity((qty_raw or "").replace("kg", "").replace("KG", "").strip()) if qty_raw else None
    if clean is None or amount is None:
        return None
    unit_price = amount
    if quantity is not None and quantity > 0 and amount is not None and qty_raw and "x" in str(qty_raw).lower():
        try:
            unit_price = (amount / quantity).quantize(Decimal("0.01"))
        except Exception:
            unit_price = amount
    return {
        "raw_label": clean,
        "normalized_label": clean,
        "quantity": _amount_to_float(quantity),
        "unit": "kg" if qty_raw and "kg" in qty_raw.lower() else None,
        "unit_price": _amount_to_float(unit_price),
        "line_total": _amount_to_float(amount),
        "discount_amount": None,
        "barcode": None,
        "confidence_score": 0.82,
        "source_index": source_index,
    }


def _dedupe_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for line in sorted(lines, key=lambda item: int(item.get("source_index") or 0)):
        key = (
            str(line.get("raw_label") or "").strip().lower(),
            str(line.get("line_total") or ""),
            str(line.get("source_index") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(line)
    return result


def _extract_receipt_lines_windowed(lines: list[str], *, store_name: str | None = None, filename: str | None = None) -> list[dict[str, Any]]:
    legacy_lines = _ORIGINAL_EXTRACT_RECEIPT_LINES(lines, store_name=store_name, filename=filename)
    candidates: list[dict[str, Any]] = []
    pending_fragments: list[tuple[int, str]] = []

    for source_index, raw_line in enumerate(lines):
        normalized = _normalize_line(raw_line)
        if len(normalized) < 2:
            continue
        if _svc._should_skip_receipt_line(normalized, store_name=store_name, filename=filename):
            pending_fragments.clear()
            continue

        qty_first = _QTY_FIRST_RE.match(normalized)
        if qty_first:
            built = _build_line(
                qty_first.group("label"),
                qty_first.group("amount"),
                qty_raw=qty_first.group("qty"),
                source_index=source_index,
                store_name=store_name,
                filename=filename,
            )
            if built:
                candidates.append(built)
                pending_fragments.clear()
                continue

        qty_x = _QTY_X_AMOUNT_RE.match(normalized)
        if qty_x:
            built = _build_line(
                qty_x.group("label"),
                qty_x.group("amount"),
                qty_raw=qty_x.group("qty"),
                source_index=source_index,
                store_name=store_name,
                filename=filename,
            )
            if built:
                candidates.append(built)
                pending_fragments.clear()
                continue

        amount_match = _AMOUNT_AT_END_RE.search(normalized)
        if amount_match:
            inline_label = normalized[: amount_match.start()].strip(" .:-")
            label_parts: list[str] = []
            inline_fragment = _label_fragment(inline_label, store_name=store_name, filename=filename)
            if inline_fragment:
                label_parts.append(inline_fragment)
            elif pending_fragments:
                # Use at most the last two nearby label fragments.
                nearby = [fragment for idx, fragment in pending_fragments if source_index - idx <= 3]
                label_parts.extend(nearby[-2:])
            if label_parts:
                built = _build_line(
                    " ".join(label_parts),
                    amount_match.group("amount"),
                    source_index=source_index,
                    store_name=store_name,
                    filename=filename,
                )
                if built:
                    candidates.append(built)
            pending_fragments.clear()
            continue

        fragment = _label_fragment(normalized, store_name=store_name, filename=filename)
        if fragment:
            pending_fragments.append((source_index, fragment))
            pending_fragments = pending_fragments[-3:]
        else:
            pending_fragments.clear()

    combined = _dedupe_lines(legacy_lines + candidates)
    # Keep the richer result. This avoids degrading receipts where the legacy parser already performed better.
    if len(combined) >= len(legacy_lines):
        return combined
    return legacy_lines


_svc._extract_receipt_lines = _extract_receipt_lines_windowed

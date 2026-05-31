from __future__ import annotations

import math
import re
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any, Callable

_AMOUNT_RE = re.compile(r"-?\d{1,6}(?:[\.,]\d{2})")
_SKIP_TOKENS = (
    "totaal",
    "subtotaal",
    "betaling",
    "bankpas",
    "maestro",
    "terminal",
    "transactie",
    "autorisatie",
    "kaart",
    "btw",
    "zegel",
    "pluspunten",
    "klantticket",
    "datum",
    "leesmethode",
)
_DISCOUNT_TOKENS = ("plus geeft", "voordeel", "korting", "actie", "prijsvoordeel")
_QTY_TOKEN_RE = re.compile(r"^\d+\s*[xX]$|^[xX]$|^[*]+$")

ParseDecimal = Callable[[str | None], Decimal | None]
NonProductLabelCheck = Callable[[str], bool]


def is_plus_context(*, store_name: str | None = None, filename: str | None = None) -> bool:
    return "plus" in f"{store_name or ''} {filename or ''}".lower()


def _key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _clean_label(value: str | None) -> str:
    label = re.sub(r"\s+", " ", str(value or "")).strip()
    label = re.sub(r"^[^A-Za-z0-9]+", "", label).strip()
    label = re.sub(r"[^A-Za-z0-9]+$", "", label).strip()
    return label


def _has_existing(extracted: list[dict[str, Any]], label: str, amount: Decimal) -> bool:
    wanted = _key(label)
    if not wanted:
        return False
    for line in extracted or []:
        existing_label = str(line.get("raw_label") or line.get("normalized_label") or "")
        existing = _key(existing_label)
        if not existing:
            continue
        try:
            existing_total = Decimal(str(line.get("line_total") or "0")).quantize(Decimal("0.01"))
        except Exception:
            existing_total = Decimal("0.00")
        if existing_total != amount:
            continue
        if wanted in existing or existing in wanted:
            return True
        if SequenceMatcher(None, wanted, existing).ratio() >= 0.72:
            return True
    return False


def _bad_label(label: str, checker: NonProductLabelCheck | None) -> bool:
    label = _clean_label(label)
    lowered = label.lower()
    if len(label) < 3:
        return True
    if not re.search(r"[A-Za-z]", label):
        return True
    if any(token in lowered for token in _SKIP_TOKENS):
        return True
    if checker and checker(label):
        return True
    return False


def _amounts(raw_line: str, parse_decimal: ParseDecimal) -> list[tuple[str, Decimal]]:
    result: list[tuple[str, Decimal]] = []
    for match in _AMOUNT_RE.finditer(raw_line):
        raw = match.group(0)
        parsed = parse_decimal(raw)
        if parsed is None:
            continue
        amount = Decimal(str(parsed)).quantize(Decimal("0.01"))
        if amount > Decimal("0.00"):
            result.append((raw, amount))
    return result


def _split_labels(raw_line: str, count: int) -> list[str]:
    first_amount = _AMOUNT_RE.search(raw_line)
    article_text = raw_line[: first_amount.start()] if first_amount else raw_line
    tokens = [token for token in re.split(r"\s+", article_text.strip()) if token]
    tokens = [token for token in tokens if not _QTY_TOKEN_RE.match(token)]
    if count <= 0 or len(tokens) < count * 2:
        return []
    labels: list[str] = []
    cursor = 0
    for index in range(count):
        remaining_labels = count - index
        remaining_tokens = len(tokens) - cursor
        size = max(2, int(math.ceil(remaining_tokens / remaining_labels)))
        labels.append(_clean_label(" ".join(tokens[cursor : cursor + size])))
        cursor += size
    return labels


def plus_multi_amount_candidates(
    *,
    lines: list[str],
    extracted: list[dict[str, Any]],
    source_index: int,
    store_name: str | None = None,
    filename: str | None = None,
    parse_decimal: ParseDecimal,
    is_invalid_label: NonProductLabelCheck | None = None,
) -> list[dict[str, Any]]:
    if not is_plus_context(store_name=store_name, filename=filename):
        return []
    if source_index < 0 or source_index >= len(lines or []):
        return []
    raw_line = re.sub(r"\s+", " ", str(lines[source_index] or "")).strip()
    if not raw_line:
        return []
    lowered = raw_line.lower()
    if any(token in lowered for token in _SKIP_TOKENS):
        return []
    if any(token in lowered for token in _DISCOUNT_TOKENS):
        return []
    amount_pairs = _amounts(raw_line, parse_decimal)
    if len(amount_pairs) < 2 or len(amount_pairs) > 4:
        return []
    labels = _split_labels(raw_line, len(amount_pairs))
    if len(labels) != len(amount_pairs):
        return []
    candidates: list[dict[str, Any]] = []
    for label, (raw_amount, amount) in zip(labels, amount_pairs):
        if _bad_label(label, is_invalid_label):
            continue
        if _has_existing(extracted, label, amount):
            continue
        candidates.append({
            "label": label,
            "qty_raw": "1",
            "amount1_raw": raw_amount,
            "amount2_raw": raw_amount,
            "source_index": source_index,
            "raw_line": raw_line,
            "normalized_line": raw_line,
        })
    return candidates if len(candidates) == len(amount_pairs) else []

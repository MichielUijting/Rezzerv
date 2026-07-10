"""
Technical Design Reference:
- TD Section: TD-03 Receipt ingestion en parsers
- Module Role: AH image receipt bbox/article-block reconstruction
- Runtime Type: production
- Used By: backend/app/receipt_ingestion/service_parts/image_ocr_flow.py
- Status Authority: no
- Refactor Status: targeted
"""

from __future__ import annotations

from statistics import median
from typing import Any
import re


_AMOUNT_RE = re.compile(r"(?<!\d)(\d{1,5}[\.,]\d{2})(?!\d)")


def _bbox_anchor(box: Any) -> tuple[float, float, float] | None:
    try:
        if isinstance(box, (list, tuple)) and len(box) == 4 and not isinstance(box[0], (list, tuple)):
            x1, y1, x2, y2 = [float(v) for v in box]
            return ((y1 + y2) / 2.0, x1, max(1.0, y2 - y1))
        points = []
        for point in box or []:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                points.append((float(point[0]), float(point[1])))
        if not points:
            return None
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return ((min(ys) + max(ys)) / 2.0, min(xs), max(1.0, max(ys) - min(ys)))
    except Exception:
        return None


def _group_texts_to_rows(texts: list[str] | None, boxes: list[Any] | None) -> list[str]:
    if not texts:
        return []
    if not boxes or len(boxes) != len(texts):
        return [re.sub(r"\s+", " ", str(text or "")).strip() for text in texts if str(text or "").strip()]

    fragments: list[tuple[float, float, float, str]] = []
    heights: list[float] = []
    for text, box in zip(texts, boxes):
        value = re.sub(r"\s+", " ", str(text or "")).strip()
        if not value:
            continue
        anchor = _bbox_anchor(box)
        if anchor is None:
            fragments.append((float(len(fragments) * 100), float(len(fragments)), 10.0, value))
            continue
        y, x, height = anchor
        heights.append(height)
        fragments.append((y, x, height, value))

    if not fragments:
        return []

    fragments.sort(key=lambda item: (item[0], item[1]))
    threshold = max(10.0, (median(heights) if heights else 10.0) * 0.62)
    groups: list[list[tuple[float, float, float, str]]] = []
    for fragment in fragments:
        if not groups:
            groups.append([fragment])
            continue
        current_y = sum(item[0] for item in groups[-1]) / len(groups[-1])
        if abs(fragment[0] - current_y) <= threshold:
            groups[-1].append(fragment)
        else:
            groups.append([fragment])

    rows: list[str] = []
    for group in groups:
        group.sort(key=lambda item: item[1])
        row = re.sub(r"\s+", " ", " ".join(item[3] for item in group)).strip()
        if row:
            rows.append(row)
    return rows


def _looks_like_ah(lines: list[str]) -> bool:
    haystack = " ".join(str(line or "").lower() for line in lines[:25])
    return (
        "albert heijn" in haystack
        or "bonuskaart" in haystack
        or "airmiles" in haystack
    ) and "subtotaal" in haystack


def _amount_tokens(line: str) -> list[str]:
    return _AMOUNT_RE.findall(str(line or ""))


def _clean_label(value: str | None) -> str:
    label = re.sub(r"^[^A-Za-zÀ-ÖØ-öø-ÿ0-9]+", "", str(value or "")).strip()
    label = re.sub(r"\s+", " ", label)
    return label.strip(" .:-")


def _recover_loyalty_row_label(line: str | None) -> str | None:
    raw = re.sub(r"\s+", " ", str(line or "")).strip()
    if not re.search(r"bonuskaart|airmiles", raw, re.I):
        return None
    candidate = re.sub(r".*\b(?:AIRMILES\s+NR\.?|BONUSKAART)\b", "", raw, flags=re.I)
    candidate = re.sub(r"\*", " ", candidate)
    candidate = re.sub(r"\bxx\d+\b", " ", candidate, flags=re.I)
    candidate = re.sub(r"\d+", " ", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip(" .:-")
    if len(candidate) < 3 or not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", candidate):
        return None
    if any(token in candidate.lower() for token in ("subtotaal", "totaal", "bonus", "koopzegel", "voordeel")):
        return None
    return _clean_label(candidate)


def _split_ah_prefixed_label(label_part: str) -> list[str]:
    words = str(label_part or "").split()
    for pos, word in enumerate(words[1:], start=1):
        if word.upper().strip(".,;:") == "AH":
            left = _clean_label(" ".join(words[:pos]))
            right = _clean_label(" ".join(words[pos:]))
            if left and right:
                return [left, right]
    return [_clean_label(label_part)]


def _first_subtotal_index(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if "subtotaal" in str(line or "").lower():
            return index
    return None


def _header_index(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        lowered = str(line or "").lower()
        if "omschrijving" in lowered and ("prijs" in lowered or "pri js" in lowered or "bedrag" in lowered):
            return index
    return None


def _product_from_price_per_row(raw: str) -> str | None:
    """Return product row from AH price-per detail rows that also contain a next item.

    A line like "Prijs per kg 11,97 KOMKOMMER 0,99" contains a unit-price detail
    for the previous weighted article and a separate visible article. The unit
    price must not become a product line; the trailing article may be preserved.
    """
    line = re.sub(r"\s+", " ", str(raw or "")).strip()
    match = re.match(
        r"^prijs\s+per\s+(?:kg|kilo|stuk)\s+"
        r"(?:(?:\d{1,5}[\.,]\d{2})\s+)?"
        r"(?P<label>[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ0-9 '\-]{2,}?)\s+"
        r"(?P<amount>\d{1,5}[\.,]\d{2})(?:\s*[A-Z])?\s*$",
        line,
        flags=re.I,
    )
    if not match:
        return None
    label = _clean_label(match.group("label"))
    amount = match.group("amount")
    if not label:
        return None
    if any(token in label.lower() for token in ("prijs per", "subtotaal", "totaal", "bonus", "voordeel", "koopzegel")):
        return None
    return f"1 {label} {amount}"


def _normalize_article_block(lines: list[str]) -> tuple[list[str], bool]:
    start = _header_index(lines)
    end = _first_subtotal_index(lines)
    if start is None or end is None or end <= start:
        return lines, False

    output: list[str] = list(lines[: start + 1])
    changed = False
    pending_label: str | None = None

    index = start + 1
    while index < end:
        raw = re.sub(r"\s+", " ", str(lines[index] or "")).strip()
        lowered = raw.lower()
        if not raw:
            index += 1
            continue

        if re.match(r"^prijs\s+per\b", lowered):
            product_row = _product_from_price_per_row(raw)
            if product_row:
                output.append(product_row)
            changed = True
            index += 1
            continue

        recovered = _recover_loyalty_row_label(raw)
        if recovered:
            pending_label = recovered
            output.append(raw)
            index += 1
            continue

        if "bonuskaart" in lowered or "airmiles" in lowered:
            output.append(raw)
            index += 1
            continue

        if re.match(r"^\s*(?:\d{1,2}\s+)?\d+[\.,]\d{3}\s*(?:k|kg)\b", raw, re.I):
            output.append(raw)
            index += 1
            continue

        amounts = _amount_tokens(raw)
        if not amounts:
            output.append(raw)
            index += 1
            continue

        quantity_match = re.match(r"^\s*(?P<qty>\d{1,2})\s+(?P<body>.+)$", raw)
        if not quantity_match:
            output.append(raw)
            index += 1
            continue

        qty = quantity_match.group("qty")
        body = quantity_match.group("body")
        b_marker = bool(re.search(r"(?:^|\s)B(?:\s|$)", body))
        first_amount = re.search(r"(?<!\d)\d{1,5}[\.,]\d{2}(?!\d)", body)
        if not first_amount:
            output.append(raw)
            index += 1
            continue

        label_part = body[: first_amount.start()].strip()
        labels = _split_ah_prefixed_label(label_part)

        if pending_label and len(labels) == 1 and len(amounts) >= 2 and b_marker:
            output.append(f"{qty} {labels[0]} {amounts[0]} B")
            output.append(f"1 {pending_label} {amounts[-1]}")
            pending_label = None
            changed = True
            index += 1
            continue

        if len(labels) >= 2 and len(amounts) == 2 and b_marker and labels[1].upper().startswith("AH "):
            output.append(f"1 {labels[0]} {amounts[1]} B")
            output.append(f"{qty} {labels[1]} {amounts[0]}")
            changed = True
            index += 1
            continue

        output.append(raw)
        index += 1

    output.extend(lines[end:])
    return output, changed


def apply_ah_photo_bbox_article_reconstruction(
    *,
    filename: str | None,
    texts: list[str] | None,
    boxes: list[Any] | None,
    current_lines: list[str] | None,
) -> list[str] | None:
    """Reconstruct AH photo article rows from Paddle bbox/text layout.

    This is intentionally source-driven. It may split or pair rows only when the
    relevant labels and amounts are visible in OCR/bbox-derived text. It does not
    use receipt ids, filenames as examples, product catalogs or fixed article names.
    """
    candidates = _group_texts_to_rows(texts or [], boxes or []) or list(current_lines or [])
    if not candidates or not _looks_like_ah(candidates):
        return None

    normalized, changed = _normalize_article_block(candidates)
    if not changed:
        # Fallback: current_lines may already contain a better grouped article block
        # than bbox row grouping. Try the same guarded normalization there.
        normalized, changed = _normalize_article_block(list(current_lines or []))

    if not changed:
        return None
    return normalized

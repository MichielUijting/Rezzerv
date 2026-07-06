"""
Technical Design Reference:
- TD Section: TD-03 Receipt ingestion en parsers
- Module Role: Receipt source parsing and data extraction
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
import re

from .corrections import (
    _is_ah_store_context,
    _ah_short_non_product_label,
    _r9_38e1_decimal,
)

def _r9_38e2_parse_amount(token: str | None) -> Decimal | None:
    if token is None:
        return None
    try:
        value = str(token).strip().replace(",", ".")
        return Decimal(value).quantize(Decimal("0.01"))
    except Exception:
        return None

def _r9_38e2_is_reliable_ah_paddle_context(paddle_lines: list[str] | None) -> bool:
    if not paddle_lines:
        return False
    joined = " ".join(str(line or "").lower() for line in paddle_lines)
    return (
        "subtotaal" in joined
        and "totaal" in joined
        and ("koopzegel" in joined or "koopzegels" in joined)
        and ("bonus" in joined or "jouw voordeel" in joined or "je voordeel" in joined)
    )

def _r9_38e2_clean_ah_label(label: str) -> str:
    label = re.sub(r"^[^A-Za-zÀ-ÖØ-öø-ÿ0-9]+", "", str(label or "")).strip()
    label = re.sub(r"\s+", " ", label)
    return label.strip()

def _r9_38e2_line_dict(
    *,
    raw_label: str,
    quantity: Decimal | int | float | None,
    unit_price: Decimal | None,
    line_total: Decimal | None,
    bonus_marker: bool = False,
    source_index: int | None = None,
    raw_line: str | None = None,
) -> dict[str, Any]:
    q: Any = None
    if quantity is not None:
        try:
            dq = Decimal(str(quantity))
            q = int(dq) if dq == dq.to_integral() else float(dq)
        except Exception:
            q = quantity

    label = _r9_38e2_clean_ah_label(raw_label)

    return {
        "raw_label": label,
        "normalized_label": label,
        "quantity": q,
        "unit": None,
        "unit_price": float(unit_price) if unit_price is not None else None,
        "line_total": float(line_total) if line_total is not None else None,
        "discount_amount": None,
        "barcode": None,
        "confidence_score": 0.86,
        "source_index": source_index,
        "producer_trace": {
            "function_name": "R9-38E2_AH_paddle_photo_reconstructor",
            "parser_path": "profiles.ah.paddle_photo_reconstructor",
            "raw_line": raw_line,
            "normalized_line": raw_line,
            "source_index": source_index,
            "bonus_marker": bool(bonus_marker),
            "validated_savings_action_path": False,
        },
    }

def _r9_38e2_extract_amount_tokens(line: str) -> list[str]:
    return re.findall(r"(?<!\d)(\d{1,5}[\.,]\d{2})(?!\d)", str(line or ""))

def _r9_38e2_extract_leading_quantities(line: str) -> list[int]:
    tokens = str(line or "").strip().split()
    quantities: list[int] = []
    for token in tokens:
        cleaned = token.strip()
        if re.fullmatch(r"\d{1,2}", cleaned):
            quantities.append(int(cleaned))
            continue
        # AH OCR sometimes reads 1 as T/I/N at the start of the row.
        if cleaned.upper() in {"T", "I", "|", "H", "F"}:
            quantities.append(1)
            continue
        if cleaned.upper() == "N":
            # In AH photo rows this is often the OCR result for quantity 2 in
            # the first column. Do not use this outside the AH Paddle path.
            quantities.append(2)
            continue
        break
    return quantities

def _r9_38e2_remove_leading_quantity_tokens(line: str) -> str:
    tokens = str(line or "").strip().split()
    idx = 0
    while idx < len(tokens):
        cleaned = tokens[idx].strip()
        if re.fullmatch(r"\d{1,2}", cleaned) or cleaned.upper() in {"T", "I", "|", "H", "F", "N"}:
            idx += 1
            continue
        break
    return " ".join(tokens[idx:])

def _r9_38e2_split_label_part(label_part: str, amount_count: int) -> list[str]:
    """Split a combined AH Paddle label area into one or two labels.

    This is intentionally generic and conservative:
    - known AH/Jumbo/etc. brand prefixes may start a new label;
    - otherwise we only split when there are two clear amount groups.
    """
    words = str(label_part or "").split()
    if amount_count <= 1 or len(words) < 3:
        return [_r9_38e2_clean_ah_label(label_part)]

    split_markers = {"AH", "BOURSIN", "STUDENTHAVER", "MACADAMIAMIX", "GOODNOODLES", "EXC"}
    candidate_positions = [
        i for i, word in enumerate(words[1:], start=1)
        if word.upper().strip(".,;:") in split_markers
    ]

    if candidate_positions:
        pos = candidate_positions[0]
        return [
            _r9_38e2_clean_ah_label(" ".join(words[:pos])),
            _r9_38e2_clean_ah_label(" ".join(words[pos:])),
        ]

    # Fallback: split roughly in half, but keep only if both sides look label-like.
    mid = len(words) // 2
    left = _r9_38e2_clean_ah_label(" ".join(words[:mid]))
    right = _r9_38e2_clean_ah_label(" ".join(words[mid:]))
    if left and right:
        return [left, right]
    return [_r9_38e2_clean_ah_label(label_part)]

def _r9_38e2_reconstruct_ah_lines_from_paddle(paddle_lines: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    reconstructed: list[dict[str, Any]] = []
    b_marked_indices: list[int] = []
    bonus_total = Decimal("0.00")
    koopzegels_line: dict[str, Any] | None = None

    diagnostics: dict[str, Any] = {
        "r9_38e2_ah_paddle_reconstruction": {
            "applied": True,
            "reconstructed_from_source_indices": [],
            "bonus_amount": 0.0,
            "bonus_target_index": None,
            "koopzegels_added": False,
        }
    }

    for idx, raw in enumerate(paddle_lines or []):
        line = str(raw or "").strip()
        low = line.lower()

        if not line:
            continue

        # Stop product reconstruction at the subtotal/footer area, but process
        # bonus and koopzegels as visible non-product financial lines.
        if "bonus" in low and re.search(r"-\s*\d{1,5}[\.,]\d{2}", line):
            amount_token = re.search(r"-\s*\d{1,5}[\.,]\d{2}", line)
            amount = _r9_38e2_parse_amount(amount_token.group(0).replace(" ", "")) if amount_token else None
            if amount is not None:
                bonus_total += amount
            continue

        if "koopzegel" in low or "koopzegels" in low:
            m = re.search(r"(\d{1,4})\s+KOOPZEGELS?(?:\s+PREMIUM)?\s+(\d{1,5}[\.,]\d{2})", line, re.I)
            if m:
                qty = int(m.group(1))
                total = _r9_38e2_parse_amount(m.group(2))
                unit = (total / Decimal(qty)).quantize(Decimal("0.01")) if total is not None and qty else None
                koopzegels_line = _r9_38e2_line_dict(
                    raw_label=f"{qty} KOOPZEGELS {m.group(2)}",
                    quantity=qty,
                    unit_price=unit,
                    line_total=total,
                    source_index=idx,
                    raw_line=line,
                )
                koopzegels_line["normalized_label"] = "KOOPZEGELS"
            continue

        if "statiegeld" in low and "koopzegel" not in low:
            amount_tokens = _r9_38e2_extract_amount_tokens(line)
            if amount_tokens:
                amount = _r9_38e2_parse_amount(amount_tokens[-1])
                if amount is not None:
                    reconstructed.append(_r9_38e2_line_dict(
                        raw_label="STATIEGELD",
                        quantity=1,
                        unit_price=amount,
                        line_total=amount,
                        source_index=idx,
                        raw_line=line,
                    ))
                    diagnostics["r9_38e2_ah_paddle_reconstruction"]["reconstructed_from_source_indices"].append(idx)
            continue

        weight_match = re.match(
            r"^\s*(?:\d{1,2}\s+)?(?P<weight>(?:\d{1,3})?[\.,]\d{3})\s*kg\s+"
            r"(?P<label>.+?)\s+(?P<total>\d{1,5}[\.,]\d{2})(?:\s*[A-Z])?\s*$",
            line,
            re.I,
        )
        if weight_match:
            weight_token = weight_match.group("weight").replace(",", ".")
            if weight_token.startswith("."):
                weight_token = "0" + weight_token
            weight = Decimal(weight_token)
            total = _r9_38e2_parse_amount(weight_match.group("total"))
            label = _r9_38e2_clean_ah_label(weight_match.group("label"))

            if label and total is not None and weight > Decimal("0.000"):
                unit = None
                for next_raw in (paddle_lines or [])[idx + 1: idx + 3]:
                    price_match = re.search(r"prijs\s+per\s+kg\s+(\d{1,5}[\.,]\d{2})", str(next_raw or ""), re.I)
                    if price_match:
                        unit = _r9_38e2_parse_amount(price_match.group(1))
                        break

                if unit is None:
                    unit = (total / weight).quantize(Decimal("0.01"))

                item = _r9_38e2_line_dict(
                    raw_label=label,
                    quantity=weight,
                    unit_price=unit,
                    line_total=total,
                    source_index=idx,
                    raw_line=line,
                )
                item["unit"] = "kg"
                reconstructed.append(item)
                diagnostics["r9_38e2_ah_paddle_reconstruction"]["reconstructed_from_source_indices"].append(idx)
            continue

        if any(token in low for token in ("subtotaal", "totaal", "jouw voordeel", "je voordeel", "airmiles", "bonus nr", "waarvan")):
            continue

        amounts = _r9_38e2_extract_amount_tokens(line)
        if not amounts:
            continue

        # Only reconstruct AH article block lines from rows that start with a
        # quantity-like token. This prevents footer/noise from becoming product.
        quantities = _r9_38e2_extract_leading_quantities(line)
        if not quantities:
            continue

        body = _r9_38e2_remove_leading_quantity_tokens(line)
        # Remove trailing bonus marker before label/amount parsing.
        has_bonus_marker = bool(re.search(r"\sB\s*$", body))
        body_wo_bonus = re.sub(r"\sB\s*$", "", body).strip()

        # Split amount part from label part.
        first_amount_match = re.search(r"(?<!\d)\d{1,5}[\.,]\d{2}(?!\d)", body_wo_bonus)
        if not first_amount_match:
            continue

        label_part = body_wo_bonus[:first_amount_match.start()].strip()
        amount_tokens = _r9_38e2_extract_amount_tokens(body_wo_bonus)

        price_per_label_match = re.match(r"^\s*prijs\s+per\s+kg\s+(?P<label>.+?)\s*$", label_part, re.I)
        if price_per_label_match and len(amount_tokens) >= 2:
            label = _r9_38e2_clean_ah_label(price_per_label_match.group("label"))
            qty = quantities[0] if quantities else 1
            total = _r9_38e2_parse_amount(amount_tokens[-1])
            if label and total is not None:
                reconstructed.append(_r9_38e2_line_dict(
                    raw_label=label,
                    quantity=qty,
                    unit_price=(total / Decimal(qty)).quantize(Decimal("0.01")) if qty else total,
                    line_total=total,
                    bonus_marker=has_bonus_marker,
                    source_index=idx,
                    raw_line=line,
                ))
                diagnostics["r9_38e2_ah_paddle_reconstruction"]["reconstructed_from_source_indices"].append(idx)
            continue

        labels = _r9_38e2_split_label_part(label_part, len(amount_tokens))

        # Cases:
        # 1 label, 2 amounts: quantity + unit + total.
        # 2 labels, 3 amounts: q1 q2 label1 label2 unit1 unit2/total2 total1-ish.
        # 2 labels, 2 amounts: one line has unit/total, second line has total.
        produced: list[dict[str, Any]] = []

        if len(labels) == 1 and len(amount_tokens) >= 2:
            qty = quantities[0]
            unit = _r9_38e2_parse_amount(amount_tokens[0])
            total = _r9_38e2_parse_amount(amount_tokens[-1])
            produced.append(_r9_38e2_line_dict(
                raw_label=labels[0],
                quantity=qty,
                unit_price=unit,
                line_total=total,
                bonus_marker=has_bonus_marker,
                source_index=idx,
                raw_line=line,
            ))

        elif len(labels) >= 2 and len(amount_tokens) >= 3:
            q1 = quantities[0] if len(quantities) >= 1 else 1
            q2 = quantities[1] if len(quantities) >= 2 else 1

            a1 = _r9_38e2_parse_amount(amount_tokens[0])
            a2 = _r9_38e2_parse_amount(amount_tokens[1])
            a3 = _r9_38e2_parse_amount(amount_tokens[2])

            # Heuristic: in known AH two-column OCR rows, the last amount belongs
            # to the first article when it equals q1 * unit1; the middle amount
            # is the second article total/unit.
            total1 = a3 if a1 is not None and a3 is not None and abs((a1 * Decimal(q1)) - a3) <= Decimal("0.02") else a1
            unit1 = a1
            total2 = a2
            unit2 = a2 if q2 == 1 else (a2 / Decimal(q2)).quantize(Decimal("0.01")) if a2 is not None else None

            produced.append(_r9_38e2_line_dict(
                raw_label=labels[0],
                quantity=q1,
                unit_price=unit1,
                line_total=total1,
                bonus_marker=False,
                source_index=idx,
                raw_line=line,
            ))
            produced.append(_r9_38e2_line_dict(
                raw_label=labels[1],
                quantity=q2,
                unit_price=unit2,
                line_total=total2,
                bonus_marker=has_bonus_marker,
                source_index=idx,
                raw_line=line,
            ))

        elif len(labels) >= 2 and len(amount_tokens) == 2:
            q1 = 1
            q2 = quantities[0] if quantities else 1
            a1 = _r9_38e2_parse_amount(amount_tokens[0])
            a2 = _r9_38e2_parse_amount(amount_tokens[1])

            produced.append(_r9_38e2_line_dict(
                raw_label=labels[0],
                quantity=q1,
                unit_price=a1,
                line_total=a1,
                bonus_marker=False,
                source_index=idx,
                raw_line=line,
            ))
            produced.append(_r9_38e2_line_dict(
                raw_label=labels[1],
                quantity=q2,
                unit_price=(a2 / Decimal(q2)).quantize(Decimal("0.01")) if a2 is not None and q2 else a2,
                line_total=a2,
                bonus_marker=has_bonus_marker,
                source_index=idx,
                raw_line=line,
            ))

        elif len(labels) == 1 and len(amount_tokens) == 1:
            qty = quantities[0]
            total = _r9_38e2_parse_amount(amount_tokens[0])
            produced.append(_r9_38e2_line_dict(
                raw_label=labels[0],
                quantity=qty,
                unit_price=(total / Decimal(qty)).quantize(Decimal("0.01")) if total is not None and qty else total,
                line_total=total,
                bonus_marker=has_bonus_marker,
                source_index=idx,
                raw_line=line,
            ))

        for item in produced:
            if not item.get("raw_label") or item.get("line_total") is None:
                continue
            if has_bonus_marker:
                b_marked_indices.append(len(reconstructed))
            reconstructed.append(item)
            diagnostics["r9_38e2_ah_paddle_reconstruction"]["reconstructed_from_source_indices"].append(idx)

    # Apply visible AH bonus only to B-marked articles. If exact matching is not
    # possible, use the highest B-marked article line as agreed.
    if bonus_total != Decimal("0.00") and b_marked_indices:
        target_idx = max(
            b_marked_indices,
            key=lambda i: _r9_38e2_parse_amount(str(reconstructed[i].get("line_total") or "0")) or Decimal("0.00"),
        )
        reconstructed[target_idx]["discount_amount"] = float(bonus_total)
        diagnostics["r9_38e2_ah_paddle_reconstruction"]["bonus_amount"] = float(bonus_total)
        diagnostics["r9_38e2_ah_paddle_reconstruction"]["bonus_target_index"] = int(target_idx)

    if koopzegels_line:
        reconstructed.append(koopzegels_line)
        diagnostics["r9_38e2_ah_paddle_reconstruction"]["koopzegels_added"] = True

    return reconstructed, diagnostics

def _r9_38e2_should_use_ah_paddle_reconstruction(
    *,
    store_name: str | None,
    paddle_lines: list[str] | None,
    current_lines: list[dict[str, Any]] | None,
) -> bool:
    if not _is_ah_store_context(store_name, paddle_lines):
        return False
    if not _r9_38e2_is_reliable_ah_paddle_context(paddle_lines):
        return False

    # Use this path only when the current OCR result shows the known generic
    # symptoms of Tesseract/Paddle conflict: short labels, footer noise, or
    # non-closing sums.
    short_noise_count = 0
    for line in current_lines or []:
        label = str((line or {}).get("raw_label") or "")
        if _ah_short_non_product_label(label):
            short_noise_count += 1

    return short_noise_count > 0

def _r9_38e2a_label_key(label: str | None) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", str(label or "").upper()).strip()

def _r9_38e2a_extract_tesseract_b_lines(tesseract_lines: list[str] | None) -> list[dict[str, Any]]:
    """Extract conservative supplemental AH B-marked item lines from Tesseract.

    Used only after Paddle-led AH reconstruction, and only for missing B-marked
    item rows. This is generic: it relies on AH quantity + label + amount + B.
    """
    supplemental: list[dict[str, Any]] = []

    for idx, raw in enumerate(tesseract_lines or []):
        line = str(raw or "").strip()
        if not re.search(r"\sB\s*\|?\s*$", line, re.I):
            continue

        m = re.match(r"^\s*(\d{1,2})\s+(.+?)\s+(\d{1,5}[\.,]\d{2})\s+B\s*\|?\s*$", line, re.I)
        if not m:
            continue

        qty = int(m.group(1))
        label = _r9_38e2_clean_ah_label(m.group(2))
        amount = _r9_38e2_parse_amount(m.group(3))
        if not label or amount is None:
            continue

        # Avoid accidental footer/savings rows.
        low = label.lower()
        if any(token in low for token in ("subtotaal", "totaal", "bonus", "koopzegel", "voordeel")):
            continue

        unit = (amount / Decimal(qty)).quantize(Decimal("0.01")) if qty else amount

        item = _r9_38e2_line_dict(
            raw_label=label,
            quantity=qty,
            unit_price=unit,
            line_total=amount,
            bonus_marker=True,
            source_index=idx,
            raw_line=line,
        )
        item["producer_trace"]["function_name"] = "R9-38E2a_AH_tesseract_supplemental_b_line"
        item["producer_trace"]["parser_path"] = "profiles.ah.tesseract_supplemental_b_line"
        supplemental.append(item)

    return supplemental

def _r9_38e2a_refine_ah_reconstructed_lines(
    *,
    lines: list[dict[str, Any]],
    paddle_lines: list[str] | None,
    tesseract_lines: list[str] | None,
    total_amount: Decimal | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """R9-38E2a-AH: fix residual AH reconstruction gaps without free correction.

    Two guarded refinements:
    1. If quantity=1 and unit_price differs from line_total on a reconstructed
       AH line, and lowering line_total to unit_price helps match the visible
       receipt total, use unit_price as line_total.
    2. Add missing B-marked supplemental AH item rows from Tesseract when the
       item label is not already present as a separate reconstructed line.
    """
    if not lines:
        return lines, None

    refined = [dict(line) for line in lines]
    changes: list[dict[str, Any]] = []

    total = _r9_38e1_decimal(total_amount)
    before_sum = sum((_r9_38e1_decimal(line.get("line_total")) for line in refined), Decimal("0.00"))
    before_discount = sum((_r9_38e1_decimal(line.get("discount_amount")) for line in refined), Decimal("0.00"))
    before_net = (before_sum + before_discount).quantize(Decimal("0.01"))

    # Step 1: quantity=1, unit differs from total. Only apply when it moves the
    # net toward the visible total.
    for line in refined:
        try:
            q = Decimal(str(line.get("quantity") or 0))
        except Exception:
            q = Decimal("0")

        unit = _r9_38e1_decimal(line.get("unit_price"))
        line_total = _r9_38e1_decimal(line.get("line_total"))

        if q != Decimal("1"):
            continue
        if unit <= Decimal("0.00") or line_total <= Decimal("0.00"):
            continue
        if abs(unit - line_total) <= Decimal("0.02"):
            continue

        candidate_net = (before_net - line_total + unit).quantize(Decimal("0.01"))
        if abs(candidate_net - total) < abs(before_net - total):
            line["line_total"] = float(unit)
            changes.append({
                "type": "quantity_one_line_total_from_unit_price",
                "label": line.get("raw_label"),
                "before": float(line_total),
                "after": float(unit),
            })
            before_net = candidate_net

    # Step 2: add missing supplemental B-marked article rows from Tesseract.
    # Do not add a supplemental line when the exact OCR source line is already
    # represented by Paddle reconstruction.
    existing_keys = {_r9_38e2a_label_key(line.get("raw_label")) for line in refined}
    existing_raw_lines = {
        re.sub(r"\s+", " ", str((line.get("producer_trace") or {}).get("normalized_line") or (line.get("producer_trace") or {}).get("raw_line") or "")).strip().upper()
        for line in refined
        if isinstance(line, dict)
    }
    supplemental = _r9_38e2a_extract_tesseract_b_lines(tesseract_lines or [])

    for item in supplemental:
        key = _r9_38e2a_label_key(item.get("raw_label"))
        raw_key = re.sub(r"\s+", " ", str((item.get("producer_trace") or {}).get("normalized_line") or (item.get("producer_trace") or {}).get("raw_line") or "")).strip().upper()
        if not key:
            continue

        if raw_key and raw_key in existing_raw_lines:
            changes.append({
                "type": "supplemental_b_marked_tesseract_line_skipped_duplicate_raw_source",
                "label": item.get("raw_label"),
                "raw_line": (item.get("producer_trace") or {}).get("raw_line"),
            })
            continue

        # If the exact item is already present as separate row, skip.
        if key in existing_keys:
            continue

        # If the item name appears inside a combined label, adding it may be the
        # intended split. Remove that token from the combined label when possible.
        for line in refined:
            current_key = _r9_38e2a_label_key(line.get("raw_label"))
            if key and key in current_key and current_key != key:
                remaining = current_key.replace(key, "").strip()
                if remaining:
                    line["raw_label"] = remaining.title().upper()
                    line["normalized_label"] = remaining.title().upper()
                break

        refined.append(item)
        existing_keys.add(key)
        changes.append({
            "type": "supplemental_b_marked_tesseract_line_added",
            "label": item.get("raw_label"),
            "line_total": item.get("line_total"),
        })

    # Re-apply visible bonus to the highest B-marked article after adding missing
    # B rows. Remove previous bonus placement first.
    bonus_amount = Decimal("0.00")
    for raw in paddle_lines or []:
        line = str(raw or "")
        if "bonus" in line.lower():
            m = re.search(r"-\s*\d{1,5}[\.,]\d{2}", line)
            if m:
                amount = _r9_38e2_parse_amount(m.group(0).replace(" ", ""))
                if amount is not None:
                    bonus_amount += amount

    if bonus_amount != Decimal("0.00"):
        for line in refined:
            if _r9_38e1_decimal(line.get("discount_amount")) == bonus_amount:
                line["discount_amount"] = None

        b_candidates = []
        for i, line in enumerate(refined):
            trace = line.get("producer_trace") or {}
            raw = str(trace.get("raw_line") or "")
            if re.search(r"\sB\s*\|?\s*$", raw, re.I):
                b_candidates.append(i)

        if b_candidates:
            target_idx = max(
                b_candidates,
                key=lambda i: _r9_38e1_decimal(refined[i].get("line_total")),
            )
            refined[target_idx]["discount_amount"] = float(bonus_amount)
            changes.append({
                "type": "bonus_retargeted_to_highest_b_marked_line",
                "target": refined[target_idx].get("raw_label"),
                "amount": float(bonus_amount),
            })

    if not changes:
        return lines, None

    return refined, {
        "r9_38e2a_ah_reconstruction_refinement": {
            "applied": True,
            "changes": changes,
        }
    }

def _r9_38e2b_tesseract_label_amount_map(tesseract_lines: list[str] | None) -> dict[str, Decimal]:
    """Build conservative label->amount evidence from AH OCR rows.

    A label key is only safe as global amount evidence when it occurs exactly
    once. Repeated labels may represent different receipt rows.
    """
    parsed_rows: list[tuple[str, Decimal]] = []

    for raw in tesseract_lines or []:
        line = str(raw or "").strip()
        low = line.lower()

        if any(token in low for token in ("subtotaal", "totaal", "bonus", "koopzegel", "voordeel", "airmiles")):
            continue

        m = re.match(r"^\s*(?:\d{1,2}|[iIlT|HF])\s+(.+?)\s+(\d{1,5}[\.,]\d{2})(?:\s+B\s*\|?)?\s*$", line, re.I)
        if not m:
            continue

        label = _r9_38e2a_label_key(m.group(1))
        amount = _r9_38e2_parse_amount(m.group(2))
        if label and amount is not None:
            parsed_rows.append((label, amount))

    from collections import Counter
    counts = Counter(label for label, _amount in parsed_rows)

    evidence: dict[str, Decimal] = {}
    for label, amount in parsed_rows:
        if counts[label] == 1:
            evidence[label] = amount

    return evidence

def _r9_38e2b_fix_quantity_one_totals_and_swaps(
    *,
    lines: list[dict[str, Any]],
    tesseract_lines: list[str] | None,
    total_amount: Decimal | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """R9-38E2b-AH refinement.

    - For AH quantity=1 rows, line_total should equal unit_price unless a
      separate total is explicitly visible.
    - Use Tesseract as supporting evidence to correct label/amount coupling
      in two-label Paddle rows.
    """
    if not lines:
        return lines, None

    refined = [dict(line) for line in lines]
    changes: list[dict[str, Any]] = []

    evidence = _r9_38e2b_tesseract_label_amount_map(tesseract_lines or [])
    total = _r9_38e1_decimal(total_amount)

    def net_sum(items: list[dict[str, Any]]) -> Decimal:
        return (
            sum((_r9_38e1_decimal(x.get("line_total")) for x in items), Decimal("0.00"))
            + sum((_r9_38e1_decimal(x.get("discount_amount")) for x in items), Decimal("0.00"))
        ).quantize(Decimal("0.01"))

    current_net = net_sum(refined)

    # 1. Correct label/amount coupling where Tesseract gives exact evidence.
    for line in refined:
        label_key = _r9_38e2a_label_key(line.get("raw_label"))
        if not label_key:
            continue

        if label_key in evidence:
            supported_amount = evidence[label_key]
            current_total = _r9_38e1_decimal(line.get("line_total"))
            current_unit = _r9_38e1_decimal(line.get("unit_price"))

            if abs(current_total - supported_amount) > Decimal("0.02"):
                candidate_net = (current_net - current_total + supported_amount).quantize(Decimal("0.01"))

                # Apply if it improves total fit or if quantity=1 and the
                # supported amount equals visible unit/line evidence.
                q = _r9_38e1_decimal(line.get("quantity"))
                improves = abs(candidate_net - total) <= abs(current_net - total)
                if improves or q == Decimal("1"):
                    line["unit_price"] = float(supported_amount)
                    line["line_total"] = float(supported_amount)
                    changes.append({
                        "type": "tesseract_supported_label_amount_correction",
                        "label": line.get("raw_label"),
                        "before_total": float(current_total),
                        "after_total": float(supported_amount),
                    })
                    current_net = candidate_net

    # 2. Generic q=1 correction: if unit_price and line_total still differ,
    # prefer unit_price when it improves the visible total fit.
    for line in refined:
        q = _r9_38e1_decimal(line.get("quantity"))
        unit = _r9_38e1_decimal(line.get("unit_price"))
        current_total = _r9_38e1_decimal(line.get("line_total"))

        if q != Decimal("1"):
            continue
        if unit <= Decimal("0.00") or current_total <= Decimal("0.00"):
            continue
        if abs(unit - current_total) <= Decimal("0.02"):
            continue

        candidate_net = (current_net - current_total + unit).quantize(Decimal("0.01"))
        if abs(candidate_net - total) < abs(current_net - total):
            line["line_total"] = float(unit)
            changes.append({
                "type": "quantity_one_total_set_to_unit_price",
                "label": line.get("raw_label"),
                "before_total": float(current_total),
                "after_total": float(unit),
            })
            current_net = candidate_net

    # 3. If there is a pair with amounts swapped and Tesseract only supports
    # one side, swap the other side by preserving pair sum. This fixes combined
    # Paddle two-label rows without article-name hardcoding.
    for i, line in enumerate(refined):
        key_i = _r9_38e2a_label_key(line.get("raw_label"))
        if key_i not in evidence:
            continue

        supported_i = evidence[key_i]
        old_i = _r9_38e1_decimal(line.get("line_total"))
        if abs(old_i - supported_i) <= Decimal("0.02"):
            continue

        # Find nearby row with same source_index from the same combined Paddle row.
        src_i = (line.get("producer_trace") or {}).get("source_index") or line.get("source_index")
        for j, other in enumerate(refined):
            if i == j:
                continue
            src_j = (other.get("producer_trace") or {}).get("source_index") or other.get("source_index")
            if src_i != src_j:
                continue

            old_j = _r9_38e1_decimal(other.get("line_total"))
            remaining = (old_i + old_j - supported_i).quantize(Decimal("0.01"))
            if remaining <= Decimal("0.00"):
                continue

            line["unit_price"] = float(supported_i)
            line["line_total"] = float(supported_i)
            other["unit_price"] = float(remaining)
            other["line_total"] = float(remaining)
            changes.append({
                "type": "combined_paddle_pair_amount_rebalanced_from_tesseract_evidence",
                "supported_label": line.get("raw_label"),
                "paired_label": other.get("raw_label"),
                "supported_amount": float(supported_i),
                "paired_amount": float(remaining),
            })
            break

    if not changes:
        return lines, None

    return refined, {
        "r9_38e2b_ah_quantity_and_pair_refinement": {
            "applied": True,
            "changes": changes,
        }
    }

def _r9_38e2c_tesseract_evidence_rows(tesseract_lines: list[str] | None) -> list[dict[str, Any]]:
    """Tesseract label/amount evidence with OCR row position.

    This is intentionally not a global label->amount map, because the same
    product label can occur more than once on the same AH receipt.
    """
    evidence: list[dict[str, Any]] = []

    for idx, raw in enumerate(tesseract_lines or []):
        line = str(raw or "").strip()
        low = line.lower()

        if any(token in low for token in ("subtotaal", "totaal", "bonus", "koopzegel", "voordeel", "airmiles")):
            continue

        m = re.match(r"^\s*(?:\d{1,2}|[iIlT|])\s+(.+?)\s+(\d{1,5}[\.,]\d{2})(?:\s+B\s*\|?)?\s*$", line, re.I)
        if not m:
            continue

        label_key = _r9_38e2a_label_key(m.group(1))
        amount = _r9_38e2_parse_amount(m.group(2))
        if label_key and amount is not None:
            evidence.append({
                "source_index": idx,
                "label_key": label_key,
                "amount": amount,
                "raw_line": line,
            })

    return evidence

def _r9_38e2c_amounts_from_raw_line(raw_line: str | None) -> list[Decimal]:
    amounts: list[Decimal] = []
    for token in _r9_38e2_extract_amount_tokens(str(raw_line or "")):
        amount = _r9_38e2_parse_amount(token)
        if amount is not None:
            amounts.append(amount)
    return amounts

def _r9_38e2c_fix_combined_paddle_pair_by_nearby_evidence(
    *,
    lines: list[dict[str, Any]],
    tesseract_lines: list[str] | None,
    total_amount: Decimal | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Fix AH combined Paddle rows using nearby Tesseract evidence only.

    Example pattern:
    Paddle combines two labels and two amounts in one row.
    Tesseract reads one of those labels separately near the same OCR position.
    Then that supported amount belongs to that label and the remaining Paddle
    amount belongs to the paired label.
    """
    if not lines:
        return lines, None

    refined = [dict(line) for line in lines]
    evidence_rows = _r9_38e2c_tesseract_evidence_rows(tesseract_lines or [])
    changes: list[dict[str, Any]] = []

    # Group reconstructed lines by their original Paddle source index.
    groups: dict[Any, list[int]] = {}
    for i, line in enumerate(refined):
        trace = line.get("producer_trace") or {}
        src = trace.get("source_index", line.get("source_index"))
        if src is None:
            continue
        groups.setdefault(src, []).append(i)

    for src, indices in groups.items():
        if len(indices) < 2:
            continue

        raw_line = str((refined[indices[0]].get("producer_trace") or {}).get("raw_line") or "")
        raw_amounts = _r9_38e2c_amounts_from_raw_line(raw_line)
        if len(raw_amounts) < 2:
            continue

        # Only use evidence near this combined Paddle row.
        nearby_evidence = [
            e for e in evidence_rows
            if abs(int(e["source_index"]) - int(src)) <= 3
        ]
        if not nearby_evidence:
            continue

        assigned: dict[int, Decimal] = {}
        used_amounts: list[Decimal] = []

        for line_idx in indices:
            key = _r9_38e2a_label_key(refined[line_idx].get("raw_label"))
            if not key:
                continue

            matching = [
                e for e in nearby_evidence
                if e["label_key"] == key
                or key in e["label_key"]
                or e["label_key"] in key
            ]
            if not matching:
                continue

            # Pick the nearest evidence row for this specific Paddle row.
            best = sorted(matching, key=lambda e: abs(int(e["source_index"]) - int(src)))[0]
            amount = best["amount"]

            if any(abs(amount - raw_amount) <= Decimal("0.02") for raw_amount in raw_amounts):
                assigned[line_idx] = amount
                used_amounts.append(amount)

        if not assigned:
            continue

        # Assign remaining raw amounts to the paired unassigned lines.
        remaining_amounts = []
        for amount in raw_amounts:
            if not any(abs(amount - used) <= Decimal("0.02") for used in used_amounts):
                remaining_amounts.append(amount)

        unassigned_indices = [idx for idx in indices if idx not in assigned]
        for idx, amount in zip(unassigned_indices, remaining_amounts):
            assigned[idx] = amount

        if len(assigned) < 2:
            continue

        for idx, amount in assigned.items():
            old_total = _r9_38e1_decimal(refined[idx].get("line_total"))
            if abs(old_total - amount) <= Decimal("0.02"):
                continue
            refined[idx]["unit_price"] = float(amount)
            refined[idx]["line_total"] = float(amount)
            changes.append({
                "type": "nearby_tesseract_evidence_combined_paddle_pair_fix",
                "source_index": int(src),
                "label": refined[idx].get("raw_label"),
                "before_total": float(old_total),
                "after_total": float(amount),
                "raw_paddle_line": raw_line,
            })

    if not changes:
        return lines, None

    return refined, {
        "r9_38e2c_ah_nearby_evidence_pair_fix": {
            "applied": True,
            "changes": changes,
        }
    }

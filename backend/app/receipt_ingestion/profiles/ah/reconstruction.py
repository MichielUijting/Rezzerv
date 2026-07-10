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

from collections import Counter
from decimal import Decimal
from typing import Any
import re

from .corrections import (
    _is_ah_store_context,
    _ah_short_non_product_label,
    _r9_38e1_decimal,
)

CENT = Decimal("0.01")


def _r9_38e2_parse_amount(token: str | None) -> Decimal | None:
    if token is None:
        return None
    try:
        value = str(token).strip().replace("−", "-").replace(",", ".")
        value = re.sub(r"[^0-9.\-]", "", value)
        if value in {"", "-", ".", "-."}:
            return None
        return Decimal(value).quantize(CENT)
    except Exception:
        return None


def _r9_38e2_decimal(value: Any) -> Decimal:
    try:
        if value is None or value == "":
            return Decimal("0.00")
        return Decimal(str(value)).quantize(CENT)
    except Exception:
        return Decimal("0.00")


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


def _r9_38e2_clean_ah_label(label: str | None) -> str:
    cleaned = re.sub(r"^[^A-Za-zÀ-ÖØ-öø-ÿ0-9]+", "", str(label or "")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" .:-")


def _r9_38e2_label_key(label: str | None) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", str(label or "").upper()).strip()


def _r9_38e2_line_dict(
    *,
    raw_label: str,
    quantity: Decimal | int | float | None,
    unit_price: Decimal | None,
    line_total: Decimal | None,
    bonus_marker: bool = False,
    source_index: int | None = None,
    raw_line: str | None = None,
    function_name: str = "R9-38E2_AH_paddle_photo_reconstructor",
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
            "function_name": function_name,
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
    quantities: list[int] = []
    for token in str(line or "").strip().split():
        cleaned = token.strip()
        if re.fullmatch(r"\d{1,2}", cleaned):
            quantities.append(int(cleaned))
            continue
        if cleaned.upper() in {"T", "I", "|", "H", "F"}:
            quantities.append(1)
            continue
        if cleaned.upper() == "N":
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

    mid = len(words) // 2
    left = _r9_38e2_clean_ah_label(" ".join(words[:mid]))
    right = _r9_38e2_clean_ah_label(" ".join(words[mid:]))
    if left and right:
        return [left, right]
    return [_r9_38e2_clean_ah_label(label_part)]


def _r9_38e2_recover_preceding_ah_label(previous_line: str | None) -> str | None:
    """Recover an article label that AH/Paddle merged into a loyalty row."""
    raw = str(previous_line or "").strip()
    if not raw or not re.search(r"bonuskaart|airmiles", raw, re.I):
        return None

    candidate = re.sub(r".*\b(?:AIRMILES\s+NR\.?|BONUSKAART)\b", "", raw, flags=re.I)
    candidate = re.sub(r"\*", " ", candidate)
    candidate = re.sub(r"\bxx\d+\b", " ", candidate, flags=re.I)
    candidate = re.sub(r"\d+", " ", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip(" .:-")

    if candidate.upper() in {"", "NR", "AIRMILES", "BONUSKAART"}:
        return None
    if len(candidate) < 3 or not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", candidate):
        return None
    if any(token in candidate.lower() for token in ("subtotaal", "totaal", "bonus", "koopzegel", "voordeel")):
        return None
    return _r9_38e2_clean_ah_label(candidate)


def _r9_38e2_weight_match(line: str) -> re.Match[str] | None:
    return re.match(
        r"^\s*(?:\d{1,2}\s+)?(?P<weight>(?:\d{1,3})?[\.,]\d{3})\s*(?:k|kg)\s+"
        r"(?P<label>.+?)\s+(?P<total>\d{1,5}[\.,]\d{2})(?:\s*[A-Z])?\s*$",
        line,
        re.I,
    )


def _r9_38e2_append_weight_line(
    *,
    reconstructed: list[dict[str, Any]],
    diagnostics: dict[str, Any],
    paddle_lines: list[str],
    idx: int,
    line: str,
    weight_match: re.Match[str],
) -> None:
    weight_token = weight_match.group("weight").replace(",", ".")
    if weight_token.startswith("."):
        weight_token = "0" + weight_token
    weight = Decimal(weight_token)
    total = _r9_38e2_parse_amount(weight_match.group("total"))
    label = _r9_38e2_clean_ah_label(weight_match.group("label"))
    if not label or total is None or weight <= Decimal("0.000"):
        return

    unit = None
    for next_raw in (paddle_lines or [])[idx + 1: idx + 3]:
        price_match = re.search(r"prijs\s+per\s+kg\s+(\d{1,5}[\.,]\d{2})", str(next_raw or ""), re.I)
        if price_match:
            unit = _r9_38e2_parse_amount(price_match.group(1))
            break
    if unit is None:
        unit = (total / weight).quantize(CENT)

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
    diagnostics["r9_38e2_ah_paddle_reconstruction"]["weight_k_or_kg_added"] += 1


def _r9_38e2_body_has_bonus_marker(body: str) -> bool:
    # Accept both visual patterns: "... B" and "... B 1,09".
    return bool(re.search(r"\sB(?:\s+\d{1,5}[\.,]\d{2})?\s*$", str(body or ""), re.I))


def _r9_38e2_remove_bonus_marker(body: str) -> str:
    # Remove only the B marker; keep a trailing amount because it may belong to a
    # preceding loyalty-row label, e.g. "OLIJFOLIE 4.79 B 1,09".
    return re.sub(r"\sB(?=\s+\d{1,5}[\.,]\d{2}\s*$|\s*$)", "", str(body or ""), flags=re.I).strip()


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
            "recovered_preceding_label_added": 0,
            "weight_k_or_kg_added": 0,
        }
    }

    for idx, raw in enumerate(paddle_lines or []):
        line = str(raw or "").strip()
        low = line.lower()
        if not line:
            continue

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
                unit = (total / Decimal(qty)).quantize(CENT) if total is not None and qty else None
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

        weight_match = _r9_38e2_weight_match(line)
        if weight_match:
            _r9_38e2_append_weight_line(
                reconstructed=reconstructed,
                diagnostics=diagnostics,
                paddle_lines=paddle_lines or [],
                idx=idx,
                line=line,
                weight_match=weight_match,
            )
            continue

        if any(token in low for token in ("subtotaal", "totaal", "jouw voordeel", "je voordeel", "airmiles", "bonus nr", "waarvan")):
            continue

        amount_tokens = _r9_38e2_extract_amount_tokens(line)
        if not amount_tokens:
            continue
        quantities = _r9_38e2_extract_leading_quantities(line)
        if not quantities:
            continue

        body = _r9_38e2_remove_leading_quantity_tokens(line)
        has_bonus_marker = _r9_38e2_body_has_bonus_marker(body)
        body_wo_bonus = _r9_38e2_remove_bonus_marker(body)
        first_amount_match = re.search(r"(?<!\d)\d{1,5}[\.,]\d{2}(?!\d)", body_wo_bonus)
        if not first_amount_match:
            continue

        label_part = body_wo_bonus[:first_amount_match.start()].strip()
        amount_tokens = _r9_38e2_extract_amount_tokens(body_wo_bonus)
        labels = _r9_38e2_split_label_part(label_part, len(amount_tokens))
        produced: list[dict[str, Any]] = []

        if len(labels) == 1 and len(amount_tokens) >= 2:
            qty = quantities[0]
            first_amount = _r9_38e2_parse_amount(amount_tokens[0])
            last_amount = _r9_38e2_parse_amount(amount_tokens[-1])
            recovered_label = _r9_38e2_recover_preceding_ah_label((paddle_lines or [None])[idx - 1] if idx > 0 else None)
            if recovered_label and first_amount is not None and last_amount is not None and has_bonus_marker:
                produced.append(_r9_38e2_line_dict(
                    raw_label=labels[0],
                    quantity=qty,
                    unit_price=first_amount,
                    line_total=first_amount,
                    bonus_marker=has_bonus_marker,
                    source_index=idx,
                    raw_line=line,
                ))
                produced.append(_r9_38e2_line_dict(
                    raw_label=recovered_label,
                    quantity=1,
                    unit_price=last_amount,
                    line_total=last_amount,
                    bonus_marker=False,
                    source_index=idx - 1,
                    raw_line=str((paddle_lines or [])[idx - 1]) if idx > 0 else line,
                    function_name="R9-38E2d_AH_preceding_loyalty_row_label_recovery",
                ))
                diagnostics["r9_38e2_ah_paddle_reconstruction"]["recovered_preceding_label_added"] += 1
            else:
                unit = first_amount
                total = last_amount
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
            total1 = a3 if a1 is not None and a3 is not None and abs((a1 * Decimal(q1)) - a3) <= Decimal("0.02") else a1
            unit1 = a1
            total2 = a2
            unit2 = a2 if q2 == 1 else (a2 / Decimal(q2)).quantize(CENT) if a2 is not None else None
            produced.append(_r9_38e2_line_dict(raw_label=labels[0], quantity=q1, unit_price=unit1, line_total=total1, source_index=idx, raw_line=line))
            produced.append(_r9_38e2_line_dict(raw_label=labels[1], quantity=q2, unit_price=unit2, line_total=total2, bonus_marker=has_bonus_marker, source_index=idx, raw_line=line))

        elif len(labels) >= 2 and len(amount_tokens) == 2:
            q1 = 1
            q2 = quantities[0] if quantities else 1
            a1 = _r9_38e2_parse_amount(amount_tokens[0])
            a2 = _r9_38e2_parse_amount(amount_tokens[1])
            if has_bonus_marker and _r9_38e2_label_key(labels[1]).startswith("AH "):
                left_amount = a2
                right_amount = a1
            else:
                left_amount = a1
                right_amount = a2
            produced.append(_r9_38e2_line_dict(raw_label=labels[0], quantity=q1, unit_price=left_amount, line_total=left_amount, source_index=idx, raw_line=line))
            produced.append(_r9_38e2_line_dict(raw_label=labels[1], quantity=q2, unit_price=(right_amount / Decimal(q2)).quantize(CENT) if right_amount is not None and q2 else right_amount, line_total=right_amount, bonus_marker=has_bonus_marker, source_index=idx, raw_line=line))

        elif len(labels) == 1 and len(amount_tokens) == 1:
            qty = quantities[0]
            total = _r9_38e2_parse_amount(amount_tokens[0])
            produced.append(_r9_38e2_line_dict(
                raw_label=labels[0],
                quantity=qty,
                unit_price=(total / Decimal(qty)).quantize(CENT) if total is not None and qty else total,
                line_total=total,
                bonus_marker=has_bonus_marker,
                source_index=idx,
                raw_line=line,
            ))

        for item in produced:
            if not item.get("raw_label") or item.get("line_total") is None:
                continue
            if item.get("producer_trace", {}).get("bonus_marker"):
                b_marked_indices.append(len(reconstructed))
            reconstructed.append(item)
            diagnostics["r9_38e2_ah_paddle_reconstruction"]["reconstructed_from_source_indices"].append(idx)

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
    short_noise_count = 0
    for line in current_lines or []:
        label = str((line or {}).get("raw_label") or "")
        if _ah_short_non_product_label(label):
            short_noise_count += 1
    return short_noise_count > 0


def _r9_38e2a_label_key(label: str | None) -> str:
    return _r9_38e2_label_key(label)


def _r9_38e2a_extract_tesseract_b_lines(tesseract_lines: list[str] | None) -> list[dict[str, Any]]:
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
        if any(token in label.lower() for token in ("subtotaal", "totaal", "bonus", "koopzegel", "voordeel")):
            continue
        supplemental.append(_r9_38e2_line_dict(
            raw_label=label,
            quantity=qty,
            unit_price=(amount / Decimal(qty)).quantize(CENT) if qty else amount,
            line_total=amount,
            bonus_marker=True,
            source_index=idx,
            raw_line=line,
            function_name="R9-38E2a_AH_tesseract_supplemental_b_line",
        ))
    return supplemental


def _r9_38e2a_refine_ah_reconstructed_lines(
    *,
    lines: list[dict[str, Any]],
    paddle_lines: list[str] | None,
    tesseract_lines: list[str] | None,
    total_amount: Decimal | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    if not lines:
        return lines, None
    refined = [dict(line) for line in lines]
    changes: list[dict[str, Any]] = []
    total = _r9_38e1_decimal(total_amount)
    current_net = (
        sum((_r9_38e1_decimal(line.get("line_total")) for line in refined), Decimal("0.00"))
        + sum((_r9_38e1_decimal(line.get("discount_amount")) for line in refined), Decimal("0.00"))
    ).quantize(CENT)

    for line in refined:
        q = _r9_38e1_decimal(line.get("quantity"))
        unit = _r9_38e1_decimal(line.get("unit_price"))
        line_total = _r9_38e1_decimal(line.get("line_total"))
        if q != Decimal("1") or unit <= Decimal("0.00") or line_total <= Decimal("0.00"):
            continue
        if abs(unit - line_total) <= Decimal("0.02"):
            continue
        candidate_net = (current_net - line_total + unit).quantize(CENT)
        if abs(candidate_net - total) < abs(current_net - total):
            line["line_total"] = float(unit)
            changes.append({"type": "quantity_one_line_total_from_unit_price", "label": line.get("raw_label"), "before": float(line_total), "after": float(unit)})
            current_net = candidate_net

    existing_keys = {_r9_38e2a_label_key(line.get("raw_label")) for line in refined}
    existing_raw_lines = {
        re.sub(r"\s+", " ", str((line.get("producer_trace") or {}).get("normalized_line") or (line.get("producer_trace") or {}).get("raw_line") or "")).strip().upper()
        for line in refined
        if isinstance(line, dict)
    }
    supplemental = _r9_38e2a_extract_tesseract_b_lines(tesseract_lines or [])
    for item in supplemental:
        key = _r9_38e2a_label_key(item.get("raw_label"))
        raw_key = re.sub(r"\s+", " ", str((item.get("producer_trace") or {}).get("raw_line") or "")).strip().upper()
        if not key:
            continue
        if raw_key and raw_key in existing_raw_lines:
            changes.append({"type": "supplemental_b_marked_tesseract_line_skipped_duplicate_raw_source", "label": item.get("raw_label"), "raw_line": (item.get("producer_trace") or {}).get("raw_line")})
            continue
        if key in existing_keys:
            continue
        refined.append(item)
        existing_keys.add(key)
        changes.append({"type": "supplemental_b_marked_tesseract_line_added", "label": item.get("raw_label"), "line_total": item.get("line_total")})

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
            if _r9_38e2_body_has_bonus_marker(raw):
                b_candidates.append(i)
        if b_candidates:
            target_idx = max(b_candidates, key=lambda i: _r9_38e1_decimal(refined[i].get("line_total")))
            refined[target_idx]["discount_amount"] = float(bonus_amount)
            changes.append({"type": "bonus_retargeted_to_highest_b_marked_line", "target": refined[target_idx].get("raw_label"), "amount": float(bonus_amount)})

    if not changes:
        return lines, None
    return refined, {"r9_38e2a_ah_reconstruction_refinement": {"applied": True, "changes": changes}}


def _r9_38e2b_tesseract_label_amount_map(tesseract_lines: list[str] | None) -> dict[str, Decimal]:
    parsed_rows: list[tuple[str, Decimal]] = []
    for raw in tesseract_lines or []:
        line = str(raw or "").strip()
        if any(token in line.lower() for token in ("subtotaal", "totaal", "bonus", "koopzegel", "voordeel", "airmiles")):
            continue
        m = re.match(r"^\s*(?:\d{1,2}|[iIlT|HF])\s+(.+?)\s+(\d{1,5}[\.,]\d{2})(?:\s+B\s*\|?)?\s*$", line, re.I)
        if not m:
            continue
        label = _r9_38e2a_label_key(m.group(1))
        amount = _r9_38e2_parse_amount(m.group(2))
        if label and amount is not None:
            parsed_rows.append((label, amount))
    counts = Counter(label for label, _amount in parsed_rows)
    return {label: amount for label, amount in parsed_rows if counts[label] == 1}


def _r9_38e2b_fix_quantity_one_totals_and_swaps(
    *,
    lines: list[dict[str, Any]],
    tesseract_lines: list[str] | None,
    total_amount: Decimal | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
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
        ).quantize(CENT)

    current_net = net_sum(refined)
    for line in refined:
        label_key = _r9_38e2a_label_key(line.get("raw_label"))
        if label_key not in evidence:
            continue
        supported_amount = evidence[label_key]
        current_total = _r9_38e1_decimal(line.get("line_total"))
        if abs(current_total - supported_amount) <= Decimal("0.02"):
            continue
        candidate_net = (current_net - current_total + supported_amount).quantize(CENT)
        q = _r9_38e1_decimal(line.get("quantity"))
        improves = abs(candidate_net - total) <= abs(current_net - total)
        if improves or q == Decimal("1"):
            line["unit_price"] = float(supported_amount)
            line["line_total"] = float(supported_amount)
            changes.append({"type": "tesseract_supported_label_amount_correction", "label": line.get("raw_label"), "before_total": float(current_total), "after_total": float(supported_amount)})
            current_net = candidate_net

    for line in refined:
        q = _r9_38e1_decimal(line.get("quantity"))
        unit = _r9_38e1_decimal(line.get("unit_price"))
        current_total = _r9_38e1_decimal(line.get("line_total"))
        if q != Decimal("1") or unit <= Decimal("0.00") or current_total <= Decimal("0.00"):
            continue
        if abs(unit - current_total) <= Decimal("0.02"):
            continue
        candidate_net = (current_net - current_total + unit).quantize(CENT)
        if abs(candidate_net - total) < abs(current_net - total):
            line["line_total"] = float(unit)
            changes.append({"type": "quantity_one_total_set_to_unit_price", "label": line.get("raw_label"), "before_total": float(current_total), "after_total": float(unit)})
            current_net = candidate_net

    if not changes:
        return lines, None
    return refined, {"r9_38e2b_ah_quantity_and_pair_refinement": {"applied": True, "changes": changes}}


def _r9_38e2c_tesseract_evidence_rows(tesseract_lines: list[str] | None) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for idx, raw in enumerate(tesseract_lines or []):
        line = str(raw or "").strip()
        if any(token in line.lower() for token in ("subtotaal", "totaal", "bonus", "koopzegel", "voordeel", "airmiles")):
            continue
        m = re.match(r"^\s*(?:\d{1,2}|[iIlT|])\s+(.+?)\s+(\d{1,5}[\.,]\d{2})(?:\s+B\s*\|?)?\s*$", line, re.I)
        if not m:
            continue
        label_key = _r9_38e2a_label_key(m.group(1))
        amount = _r9_38e2_parse_amount(m.group(2))
        if label_key and amount is not None:
            evidence.append({"source_index": idx, "label_key": label_key, "amount": amount, "raw_line": line})
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
    if not lines:
        return lines, None
    refined = [dict(line) for line in lines]
    evidence_rows = _r9_38e2c_tesseract_evidence_rows(tesseract_lines or [])
    changes: list[dict[str, Any]] = []
    groups: dict[Any, list[int]] = {}
    for i, line in enumerate(refined):
        trace = line.get("producer_trace") or {}
        src = trace.get("source_index", line.get("source_index"))
        if src is not None:
            groups.setdefault(src, []).append(i)

    for src, indices in groups.items():
        if len(indices) < 2:
            continue
        raw_line = str((refined[indices[0]].get("producer_trace") or {}).get("raw_line") or "")
        raw_amounts = _r9_38e2c_amounts_from_raw_line(raw_line)
        if len(raw_amounts) < 2:
            continue
        nearby_evidence = [e for e in evidence_rows if abs(int(e["source_index"]) - int(src)) <= 3]
        if not nearby_evidence:
            continue
        assigned: dict[int, Decimal] = {}
        used_amounts: list[Decimal] = []
        for line_idx in indices:
            key = _r9_38e2a_label_key(refined[line_idx].get("raw_label"))
            matching = [
                e for e in nearby_evidence
                if e["label_key"] == key or key in e["label_key"] or e["label_key"] in key
            ]
            if not matching:
                continue
            best = sorted(matching, key=lambda e: abs(int(e["source_index"]) - int(src)))[0]
            amount = best["amount"]
            if any(abs(amount - raw_amount) <= Decimal("0.02") for raw_amount in raw_amounts):
                assigned[line_idx] = amount
                used_amounts.append(amount)
        if not assigned:
            continue
        remaining_amounts = [amount for amount in raw_amounts if not any(abs(amount - used) <= Decimal("0.02") for used in used_amounts)]
        for idx, amount in zip([idx for idx in indices if idx not in assigned], remaining_amounts):
            assigned[idx] = amount
        if len(assigned) < 2:
            continue
        for idx, amount in assigned.items():
            old_total = _r9_38e1_decimal(refined[idx].get("line_total"))
            if abs(old_total - amount) <= Decimal("0.02"):
                continue
            refined[idx]["unit_price"] = float(amount)
            refined[idx]["line_total"] = float(amount)
            changes.append({"type": "nearby_tesseract_evidence_combined_paddle_pair_fix", "source_index": int(src), "label": refined[idx].get("raw_label"), "before_total": float(old_total), "after_total": float(amount), "raw_paddle_line": raw_line})

    if not changes:
        return lines, None
    return refined, {"r9_38e2c_ah_nearby_evidence_pair_fix": {"applied": True, "changes": changes}}

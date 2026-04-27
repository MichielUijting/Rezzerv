"""Runtime receipt financial rule patch for Release 1.

This module is loaded automatically by Python when the backend starts. It keeps
UI, database schema and baseline tooling untouched, and patches only the receipt
financial status rules in the legacy receipt service.

Release 1 goal:
- production status is based on generic financial consistency;
- baseline remains test-only;
- Kassa keeps showing database/backend status;
- stamp/points lines are retained as financial lines, not as inventory products.
"""

from __future__ import annotations

from decimal import Decimal
import re


def _to_decimal(value):
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except Exception:
        return None


def _money_matches(left, right, tolerance=Decimal("0.05")) -> bool:
    left_decimal = _to_decimal(left)
    right_decimal = _to_decimal(right)
    if left_decimal is None or right_decimal is None:
        return False
    return abs(left_decimal - right_decimal) <= tolerance


def _line_type_for_label(label: str | None, amount=None) -> str:
    lowered = re.sub(r"\s+", " ", str(label or "").strip().lower())
    amount_decimal = _to_decimal(amount)
    if not lowered:
        return "noise"
    if any(token in lowered for token in (
        "koopzegel",
        "koopzegels",
        "pluspunten",
        "plus punten",
        "spaarzegel",
        "spaarzegels",
        "e-spaarzegel",
        "espaarzegel",
        "zegel",
    )):
        return "stamp_or_points"
    if any(token in lowered for token in (
        "korting",
        "bonus",
        "prijsvoordeel",
        "totaal prijsvoordeel",
        "actiebon",
        "actie bon",
        "coupon",
        "lidl plus",
        "uw voordeel",
        "plus geeft meer voordeel",
    )):
        # Positieve bedragen kunnen op sommige bonnen kortingsoverzichten of
        # voordeelregels zijn; negatieve bedragen zijn expliciete correcties.
        if amount_decimal is None or amount_decimal <= 0:
            return "discount"
        return "financial_correction"
    if any(token in lowered for token in ("bankpas", "betaling", "betaald", "pin", "contant", "wisselgeld")):
        return "payment"
    if any(token in lowered for token in ("totaal", "subtotaal", "btw", "te betalen")):
        return "total"
    return "product"


def _install_receipt_financial_patch() -> None:
    try:
        from app.services import receipt_service as rs
    except Exception:
        return

    original_non_product_check = getattr(rs, "_looks_like_non_product_receipt_label", lambda label: False)
    original_discount_free_zero = getattr(rs, "_discount_or_free_total_zero_case", None)

    def patched_filter_non_product_receipt_lines(lines):
        filtered = []
        seen = set()
        for line in lines or []:
            if not isinstance(line, dict):
                continue
            label = str(line.get("raw_label") or line.get("normalized_label") or "").strip()
            amount = _to_decimal(line.get("line_total"))
            line_type = str(line.get("line_type") or "").strip() or _line_type_for_label(label, amount)
            line["line_type"] = line_type

            # Stamps/points/discounts are not inventory products, but they are
            # financial receipt lines and must be retained for status checks.
            if line_type not in {"stamp_or_points", "discount", "financial_correction"} and original_non_product_check(label):
                continue

            key = (
                re.sub(r"\s+", " ", label).strip().lower(),
                str(line.get("quantity") or ""),
                str(line.get("line_total") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            filtered.append(line)
        return filtered

    def receipt_line_financials(lines, discount_total=None):
        gross_sum = Decimal("0.00")
        line_discount_sum = Decimal("0.00")
        financial_line_count = 0

        for line in lines or []:
            if not isinstance(line, dict):
                continue
            amount = _to_decimal(line.get("line_total"))
            discount_amount = _to_decimal(line.get("discount_amount"))
            label = str(line.get("raw_label") or line.get("normalized_label") or "")
            line_type = str(line.get("line_type") or "").strip() or _line_type_for_label(label, amount)
            line["line_type"] = line_type

            if line_type in {"payment", "total", "noise"}:
                continue
            if amount is not None:
                gross_sum += amount
                financial_line_count += 1
            if discount_amount is not None:
                line_discount_sum += discount_amount

        explicit_discount = _to_decimal(discount_total)
        effective_discount = explicit_discount if explicit_discount not in (None, Decimal("0.00")) else line_discount_sum
        effective_discount = effective_discount or Decimal("0.00")

        candidates = [gross_sum]
        if effective_discount:
            candidates.extend([gross_sum - effective_discount, gross_sum + effective_discount])

        # For backward compatibility this tuple keeps the old shape.
        # The third value is the best default net sum using the conventional
        # positive discount_total convention.
        return gross_sum, effective_discount, gross_sum - effective_discount

    def totals_match_receipt_lines(total_amount, lines, discount_total=None, tolerance=Decimal("0.05")):
        total = _to_decimal(total_amount)
        if total is None:
            return False

        gross_sum = Decimal("0.00")
        line_discount_sum = Decimal("0.00")
        financial_line_count = 0
        for line in lines or []:
            if not isinstance(line, dict):
                continue
            amount = _to_decimal(line.get("line_total"))
            discount_amount = _to_decimal(line.get("discount_amount"))
            label = str(line.get("raw_label") or line.get("normalized_label") or "")
            line_type = str(line.get("line_type") or "").strip() or _line_type_for_label(label, amount)
            line["line_type"] = line_type
            if line_type in {"payment", "total", "noise"}:
                continue
            if amount is not None:
                gross_sum += amount
                financial_line_count += 1
            if discount_amount is not None:
                line_discount_sum += discount_amount

        if financial_line_count == 0:
            return False

        candidates = {gross_sum}
        explicit_discount = _to_decimal(discount_total)
        if explicit_discount not in (None, Decimal("0.00")):
            candidates.add(gross_sum - explicit_discount)
            candidates.add(gross_sum + explicit_discount)
        if line_discount_sum:
            candidates.add(gross_sum - line_discount_sum)
            candidates.add(gross_sum + line_discount_sum)

        return any(abs(candidate - total) <= tolerance for candidate in candidates)

    def determine_final_parse_status(parse_result):
        if not parse_result or not getattr(parse_result, "is_receipt", False):
            return "failed"
        has_store = bool(str(getattr(parse_result, "store_name", "") or "").strip())
        has_total = getattr(parse_result, "total_amount", None) is not None
        lines = getattr(parse_result, "lines", None) or []
        if not has_store or not has_total or not lines:
            return "review_needed"

        if totals_match_receipt_lines(getattr(parse_result, "total_amount", None), lines, getattr(parse_result, "discount_total", None)):
            return "parsed"

        if callable(original_discount_free_zero):
            try:
                if original_discount_free_zero(getattr(parse_result, "total_amount", None), lines, getattr(parse_result, "discount_total", None)):
                    return "parsed"
            except Exception:
                pass

        return "review_needed"

    rs._line_type_for_label = _line_type_for_label
    rs._filter_non_product_receipt_lines = patched_filter_non_product_receipt_lines
    rs._receipt_line_financials = receipt_line_financials
    rs._totals_match_receipt_lines = totals_match_receipt_lines
    rs.determine_final_parse_status = determine_final_parse_status


_install_receipt_financial_patch()

"""
Technical Design Reference:
- TD Section: TD-04 Status en SSOT
- Module Role: Map production PO norm status to API/UI fields
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: receipt payload content only
- Reads Data: none
- Writes Data: none
- Status Authority: yes
- Refactor Status: cleanup
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


# Canonical receipt roles that contribute once to the amount paid for the
# purchase. Roles such as total/payment/tax are summaries or settlement facts
# and must never be added to article components a second time.
_PURCHASE_COMPONENT_ROLES = {
    "product",
    "discount",
    "deposit",
    "shipping",
    "fee",
    "loyalty",
    "spaarzegels",
}
_PRODUCT_ROLES = {"product"}
_USER_CORRECTION_FIELDS = {
    "corrected_raw_label",
    "corrected_quantity",
    "corrected_unit",
    "corrected_unit_price",
    "corrected_line_total",
}


def _safe_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _amount_equals(left: Any, right: Any, tolerance: Decimal = Decimal("0.01")) -> bool:
    left_dec = _safe_decimal(left)
    right_dec = _safe_decimal(right)
    if left_dec is None or right_dec is None:
        return False
    return abs(left_dec - right_dec) <= tolerance


def _normalize_status_label(label: Any) -> str:
    normalized = str(label or "").strip()
    if normalized == "Gecontroleerd":
        return "Gecontroleerd"
    return "Controle nodig"


def _status_code(label: str) -> str:
    return "controlled" if _normalize_status_label(label) == "Gecontroleerd" else "review"


def _active_lines(payload: dict[str, Any]) -> list[dict[str, Any]]:
    lines = payload.get("lines")
    if not isinstance(lines, list):
        return []
    return [
        line for line in lines
        if isinstance(line, dict) and int(line.get("is_deleted") or 0) == 0
    ]


def _canonical_role(line: dict[str, Any]) -> str | None:
    value = line.get("line_type") or line.get("line_role")
    normalized = str(value or "").strip().lower()
    return normalized or None


def _line_count(payload: dict[str, Any]) -> int:
    lines = _active_lines(payload)
    typed_lines = [line for line in lines if _canonical_role(line)]
    if typed_lines:
        return sum(1 for line in typed_lines if _canonical_role(line) in _PRODUCT_ROLES)

    # Transitional compatibility for receipts persisted before canonical roles
    # became authoritative. No text interpretation is performed.
    value = payload.get("line_count")
    if value is None:
        value = len(lines)
    try:
        return int(value or 0)
    except Exception:
        return 0


def _has_user_corrections(payload: dict[str, Any]) -> bool:
    try:
        if int(payload.get("totals_overridden") or 0) != 0:
            return True
    except Exception:
        if bool(payload.get("totals_overridden")):
            return True

    for line in _active_lines(payload):
        if any(line.get(field) not in (None, "") for field in _USER_CORRECTION_FIELDS):
            return True
    return False


def _scanner_approval_is_current(payload: dict[str, Any]) -> bool:
    """Use scanner approval while its persisted canonical observation is current.

    Full receipt payloads prove this from canonical line roles. Kassa list/detail
    summary payloads deliberately omit the line collection and expose only the
    persisted scanner decision plus ``line_count``. In that summary shape an
    ``approved`` scanner result with at least one persisted line remains current;
    a user edit is routed through receipt review recomputation and therefore
    changes the persisted parse status/correction state before this SSOT is read.

    This keeps one status authority without reintroducing a second financial
    line-sum decision in summary/detail presentation. No retailer or receipt text
    is inspected here.
    """
    if str(payload.get("parse_status") or "").strip().lower() != "approved":
        return False
    if _has_user_corrections(payload):
        return False

    lines = _active_lines(payload)
    if not lines:
        try:
            return int(payload.get("line_count") or 0) > 0
        except Exception:
            return False

    roles = [_canonical_role(line) for line in lines]
    return all(role is not None for role in roles) and any(role in _PRODUCT_ROLES for role in roles)


def _line_discount_total(payload: dict[str, Any]) -> Decimal:
    lines = _active_lines(payload)
    if lines:
        total = Decimal("0")
        for line in lines:
            value = _safe_decimal(line.get("discount_amount"))
            if value is not None:
                total += value
        return total

    value = _safe_decimal(payload.get("line_discount_sum"))
    return value if value is not None else Decimal("0")


def _receipt_discount_total(payload: dict[str, Any]) -> Decimal:
    value = _safe_decimal(payload.get("discount_total"))
    return value if value is not None else Decimal("0")


def _line_total_from_lines(payload: dict[str, Any]) -> Decimal | None:
    lines = _active_lines(payload)
    if not lines:
        return None

    has_canonical_roles = any(_canonical_role(line) for line in lines)
    total = Decimal("0")
    seen = False
    for line in lines:
        role = _canonical_role(line)
        if has_canonical_roles and role not in _PURCHASE_COMPONENT_ROLES:
            continue

        value = _safe_decimal(
            line.get("display_line_total")
            if line.get("display_line_total") is not None
            else line.get("corrected_line_total")
            if line.get("corrected_line_total") is not None
            else line.get("line_total")
        )
        if value is None:
            continue
        total += value
        seen = True
    return total if seen else None


def _net_line_total_variants(payload: dict[str, Any]) -> list[Decimal]:
    """Return source-driven financial totals without semantic double counting."""
    line_total = _line_total_from_lines(payload)
    if line_total is None:
        line_total = _safe_decimal(payload.get("line_total_sum"))

    variants: list[Decimal] = []
    explicit_net = _safe_decimal(payload.get("net_line_total_sum"))
    if explicit_net is not None:
        variants.append(explicit_net)

    if line_total is not None:
        variants.append(line_total)
        line_discount = _line_discount_total(payload)
        receipt_discount = _receipt_discount_total(payload)
        if line_discount:
            variants.append(line_total + line_discount)
        if receipt_discount:
            variants.append(line_total + receipt_discount)
        if line_discount and receipt_discount and line_discount != receipt_discount:
            variants.append(line_total + line_discount + receipt_discount)

    deduped: list[Decimal] = []
    for value in variants:
        if value not in deduped:
            deduped.append(value)
    return deduped


def _net_line_total(payload: dict[str, Any]) -> Decimal | None:
    variants = _net_line_total_variants(payload)
    return variants[0] if variants else None


def _production_status_item(payload: dict[str, Any]) -> dict[str, Any]:
    """Determine production Kassa status from canonical facts only."""
    failed: list[str] = []

    store_name = str(payload.get("store_name") or payload.get("store_branch") or "").strip()
    if not store_name:
        failed.append("STORE_NAME_MISSING")

    total_amount = _safe_decimal(payload.get("total_amount"))
    if total_amount is None:
        failed.append("TOTAL_AMOUNT_MISSING")

    line_count = _line_count(payload)
    if line_count <= 0:
        failed.append("NO_ARTICLE_LINES")

    scanner_approved = _scanner_approval_is_current(payload)
    net_line_sums = _net_line_total_variants(payload)
    if total_amount is not None and line_count > 0 and not scanner_approved:
        if not net_line_sums:
            failed.append("LINE_SUM_MISSING")
        elif not any(_amount_equals(net_line_sum, total_amount) for net_line_sum in net_line_sums):
            failed.append("LINE_SUM_TOTAL_MISMATCH")

    label = "Gecontroleerd" if not failed else "Controle nodig"

    if not failed:
        if scanner_approved:
            reason = (
                "Gecontroleerd: winkel, totaalbedrag, canonieke productregels en "
                "actuele scannerkwaliteit voldoen aan productieve Kassa-statuscriteria."
            )
        else:
            reason = (
                "Gecontroleerd: winkel, totaalbedrag en canonieke aankoopcomponenten "
                "voldoen aan productieve Kassa-statuscriteria."
            )
    else:
        labels = {
            "STORE_NAME_MISSING": "winkelnaam ontbreekt",
            "TOTAL_AMOUNT_MISSING": "totaalbedrag ontbreekt",
            "NO_ARTICLE_LINES": "geen artikelregels gevonden",
            "LINE_SUM_MISSING": "som van aankoopcomponenten ontbreekt",
            "LINE_SUM_TOTAL_MISMATCH": "som van aankoopcomponenten sluit niet aan op kassabontotaal",
        }
        reason = "Controle nodig: " + "; ".join(labels.get(code, code) for code in failed)

    return {
        "po_norm_status": _status_code(label),
        "po_norm_status_label": label,
        "po_norm_failed_criteria": failed,
        "po_norm_reason": reason,
    }


def load_po_norm_status_items() -> dict[str, dict[str, Any]]:
    return {}


def apply_po_norm_status(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply the Kassa status SSOT using canonical facts, never receipt text."""
    if not isinstance(payload, dict):
        return payload

    item = _production_status_item(payload)
    label = _normalize_status_label(item.get("po_norm_status_label"))
    status_code = _status_code(label)

    payload.pop("parse_status", None)
    payload.pop("actual_parse_status", None)
    payload.pop("actual_status_label", None)

    payload["po_norm_status"] = status_code
    payload["po_norm_status_label"] = label
    payload["po_norm_failed_criteria"] = item.get("po_norm_failed_criteria") or []
    payload["po_norm_reason"] = item.get("po_norm_reason")
    payload["inbox_status"] = label
    payload["status"] = label

    if any(key in payload for key in ("parse_status", "actual_parse_status", "actual_status_label")):
        raise RuntimeError("INVALID STATUS SOURCE")
    return payload

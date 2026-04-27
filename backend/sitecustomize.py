"""Runtime receipt financial rule patch for Release 1.1.

Loaded automatically by Python at backend startup. Keeps UI, database schema and
baseline tooling untouched, and makes both parsing and the admin recompute route
use the same generic financial receipt rules.
"""

from __future__ import annotations

from decimal import Decimal
import builtins
import re
import sys


def _dec(value):
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except Exception:
        return None


def _line_type(label, amount=None):
    text = re.sub(r"\s+", " ", str(label or "").strip().lower())
    amt = _dec(amount)
    if not text:
        return "noise"
    if any(t in text for t in ("koopzegel", "pluspunten", "plus punten", "spaarzegel", "e-spaarzegel", "espaarzegel", "zegel")):
        return "stamp_or_points"
    if any(t in text for t in ("korting", "bonus", "prijsvoordeel", "totaal prijsvoordeel", "actiebon", "actie bon", "coupon", "lidl plus", "uw voordeel", "plus geeft meer voordeel")):
        return "discount" if amt is None or amt <= 0 else "financial_correction"
    if any(t in text for t in ("bankpas", "betaling", "betaald", "pin", "contant", "wisselgeld")):
        return "payment"
    if any(t in text for t in ("totaal", "subtotaal", "btw", "te betalen")):
        return "total"
    return "product"


def _matches(total, candidates, tolerance=Decimal("0.05")):
    total_dec = _dec(total)
    if total_dec is None:
        return False
    return any((cand := _dec(candidate)) is not None and abs(cand - total_dec) <= tolerance for candidate in candidates)


def _financial(lines, discount_total=None):
    gross = Decimal("0.00")
    line_discount = Decimal("0.00")
    count = 0
    for line in lines or []:
        if not isinstance(line, dict):
            continue
        amount = _dec(line.get("line_total"))
        discount_amount = _dec(line.get("discount_amount"))
        label = line.get("raw_label") or line.get("normalized_label") or ""
        kind = str(line.get("line_type") or "").strip() or _line_type(label, amount)
        line["line_type"] = kind
        if kind in {"payment", "total", "noise"}:
            continue
        if amount is not None:
            gross += amount
            count += 1
        if discount_amount is not None:
            line_discount += discount_amount
    candidates = {gross}
    explicit_discount = _dec(discount_total)
    if explicit_discount not in (None, Decimal("0.00")):
        candidates.add(gross - explicit_discount)
        candidates.add(gross + explicit_discount)
    if line_discount:
        candidates.add(gross - line_discount)
        candidates.add(gross + line_discount)
    return gross, line_discount, candidates, count


def _totals_match(total_amount, lines, discount_total=None, tolerance=Decimal("0.05")):
    _, _, candidates, count = _financial(lines, discount_total)
    return count > 0 and _matches(total_amount, candidates, tolerance)


def _install_receipt_service_patch():
    try:
        from app.services import receipt_service as rs
    except Exception:
        return
    old_non_product = getattr(rs, "_looks_like_non_product_receipt_label", lambda label: False)
    old_zero_case = getattr(rs, "_discount_or_free_total_zero_case", None)

    def filter_non_product(lines):
        filtered = []
        seen = set()
        for line in lines or []:
            if not isinstance(line, dict):
                continue
            label = str(line.get("raw_label") or line.get("normalized_label") or "").strip()
            amount = _dec(line.get("line_total"))
            kind = str(line.get("line_type") or "").strip() or _line_type(label, amount)
            line["line_type"] = kind
            if kind not in {"stamp_or_points", "discount", "financial_correction"} and old_non_product(label):
                continue
            key = (re.sub(r"\s+", " ", label).strip().lower(), str(line.get("quantity") or ""), str(line.get("line_total") or ""))
            if key in seen:
                continue
            seen.add(key)
            filtered.append(line)
        return filtered

    def receipt_line_financials(lines, discount_total=None):
        gross, line_discount, _, _ = _financial(lines, discount_total)
        explicit = _dec(discount_total)
        effective = explicit if explicit not in (None, Decimal("0.00")) else line_discount
        effective = effective or Decimal("0.00")
        return gross, effective, gross - effective

    def determine_status(parse_result):
        if not parse_result or not getattr(parse_result, "is_receipt", False):
            return "failed"
        if not str(getattr(parse_result, "store_name", "") or "").strip():
            return "review_needed"
        if getattr(parse_result, "total_amount", None) is None:
            return "review_needed"
        lines = getattr(parse_result, "lines", None) or []
        if not lines:
            return "review_needed"
        if _totals_match(getattr(parse_result, "total_amount", None), lines, getattr(parse_result, "discount_total", None)):
            return "parsed"
        if callable(old_zero_case):
            try:
                if old_zero_case(getattr(parse_result, "total_amount", None), lines, getattr(parse_result, "discount_total", None)):
                    return "parsed"
            except Exception:
                pass
        return "review_needed"

    rs._line_type_for_label = _line_type
    rs._filter_non_product_receipt_lines = filter_non_product
    rs._receipt_line_financials = receipt_line_financials
    rs._totals_match_receipt_lines = _totals_match
    rs.determine_final_parse_status = determine_status


def _install_status_sync_patch():
    try:
        from app.services import receipt_status_sync as sync
    except Exception:
        return

    def amounts_match(total_amount, line_total_sum, discount_total, line_discount_sum):
        lines = _dec(line_total_sum) or Decimal("0.00")
        candidates = {lines}
        for discount in (_dec(discount_total), _dec(line_discount_sum)):
            if discount not in (None, Decimal("0.00")):
                candidates.add(lines - discount)
                candidates.add(lines + discount)
        return _matches(total_amount, candidates)

    sync._amounts_match = amounts_match


def _install_main_patch(module):
    if getattr(module, "_rezzerv_financial_recompute_patch", False):
        return
    try:
        from sqlalchemy import text
    except Exception:
        return

    def evaluate(receipt):
        try:
            line_count = int(receipt.get("line_count") or 0)
        except Exception:
            line_count = 0
        store_ok = module.is_receipt_store_name_correct(receipt.get("store_name"))
        total_ok = receipt.get("total_amount") is not None
        sum_ok = _matches(receipt.get("total_amount"), receipt.get("financial_candidates") or [])
        if store_ok and line_count >= 1 and total_ok and sum_ok:
            status, parse_status = "Gecontroleerd", "approved"
        elif store_ok and line_count >= 1 and total_ok:
            status, parse_status = "Controle nodig", "review_needed"
        else:
            status, parse_status = "Handmatig", "manual"
        return {"store_name_correct": store_ok, "article_count_correct": line_count >= 1, "total_price_correct": total_ok, "line_sum_matches_total": sum_ok, "inbox_status": status, "parse_status": parse_status, "line_count": line_count}

    def load_lines(conn, receipt_id):
        return [dict(row) for row in conn.execute(text("""
            SELECT
                COALESCE(corrected_raw_label, raw_label, normalized_label, '') AS raw_label,
                COALESCE(normalized_label, corrected_raw_label, raw_label, '') AS normalized_label,
                COALESCE(corrected_line_total, line_total) AS line_total,
                COALESCE(discount_amount, 0) AS discount_amount
            FROM receipt_table_lines
            WHERE receipt_table_id = :receipt_id
              AND COALESCE(is_deleted, 0) = 0
              AND TRIM(COALESCE(corrected_raw_label, raw_label, normalized_label, '')) <> ''
        """), {"receipt_id": receipt_id}).mappings().all()]

    def backfill(conn, household_id=None, limit=None):
        query = """
            SELECT rt.id, rt.household_id, rt.store_name, rt.purchase_at, rt.total_amount, rt.discount_total, rt.parse_status
            FROM receipt_tables rt
            JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
            WHERE COALESCE(rt.deleted_at, '') = '' AND COALESCE(rr.deleted_at, '') = ''
        """
        params = {}
        if household_id is not None:
            query += " AND rt.household_id = :household_id"
            params["household_id"] = str(household_id)
        query += " ORDER BY rt.created_at DESC"
        if limit is not None:
            query += " LIMIT :limit"
            params["limit"] = int(limit)
        rows = conn.execute(text(query), params).mappings().all()
        report = {"scanned": 0, "updated": 0, "unchanged": 0, "errors": 0, "status_counts": {"Gecontroleerd": 0, "Controle nodig": 0, "Handmatig": 0}, "parse_status_counts": {}, "lines": {}}
        for row in rows:
            receipt_id = str(row.get("id") or "").strip()
            if not receipt_id:
                continue
            report["scanned"] += 1
            try:
                lines = load_lines(conn, receipt_id)
                gross, line_discount, candidates, count = _financial(lines, row.get("discount_total"))
                row_dict = dict(row)
                row_dict.update({"line_count": count, "line_total_sum": float(gross), "line_discount_sum": float(line_discount), "financial_candidates": list(candidates)})
                criteria = evaluate(row_dict)
                status = str(criteria.get("inbox_status") or "Handmatig")
                next_parse_status = str(criteria.get("parse_status") or "manual").strip().lower() or "manual"
                report["status_counts"][status] = int(report["status_counts"].get(status, 0) or 0) + 1
                report["parse_status_counts"][next_parse_status] = int(report["parse_status_counts"].get(next_parse_status, 0) or 0) + 1
                changed = str(row.get("parse_status") or "").strip().lower() != next_parse_status
                if changed:
                    conn.execute(text("UPDATE receipt_tables SET parse_status = :parse_status, line_count = :line_count, updated_at = CURRENT_TIMESTAMP WHERE id = :id"), {"id": receipt_id, "parse_status": next_parse_status, "line_count": count})
                    report["updated"] += 1
                else:
                    report["unchanged"] += 1
                report["lines"][receipt_id] = {"store_name": row.get("store_name"), "line_count": count, "total_amount": row.get("total_amount"), "line_total_sum": float(gross), "line_discount_sum": float(line_discount), "financial_candidates": [float(item) for item in candidates], "status": status, "parse_status": next_parse_status}
            except Exception as exc:
                report["errors"] += 1
                report["lines"][receipt_id] = {"error": str(exc)}
        return report

    module.evaluate_receipt_unpack_criteria = evaluate
    module.backfill_receipt_unpack_statuses = backfill
    module._rezzerv_financial_recompute_patch = True


def _try_patch_main():
    module = sys.modules.get("app.main")
    if module is not None:
        _install_main_patch(module)


_original_import = builtins.__import__


def _import_hook(name, globals=None, locals=None, fromlist=(), level=0):
    module = _original_import(name, globals, locals, fromlist, level)
    if name == "app.main" or (name == "app" and "main" in (fromlist or ())):
        _try_patch_main()
    return module


builtins.__import__ = _import_hook
_install_receipt_service_patch()
_install_status_sync_patch()
_try_patch_main()

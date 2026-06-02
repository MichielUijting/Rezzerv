from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


AMOUNT_RE = re.compile(r"(?<!\d)(-?\d{1,3}(?:[.,]\d{2}))(?!\d)")

PATTERNS = {
    "AH_TOTAL": [r"\b(totaal|te\s*betalen|subtotaal|saldo)\b"],
    "AH_PAYMENT": [r"\b(pin|maestro|visa|mastercard|contactloos|contant|betaald|betaling|wisselgeld|bankpas|transactie)\b"],
    "AH_TAX": [r"\b(btw|vat|laag|hoog|tarief|netto|belasting)\b"],
    "AH_DISCOUNT": [r"\b(bonus|korting|actie|voordeel|aanbieding|prijsvoordeel|koopkorting|bonuskaart|2e\s*halve|gratis|retour)\b"],
    "AH_LOYALTY_STAMPS": [r"\b(zegel|zegels|koopzegel|koopzegels|premiumzegel|premiumzegels|spaarzegel|spaarzegels)\b"],
    "AH_LOYALTY_POINTS": [r"\b(punt|punten|air\s*miles|bonuspunten|loyalty|persoonlijke\s*bonus|kaartnummer)\b"],
    "AH_METADATA": [r"\b(albert\s*heijn|ah\.?|winkel|filiaal|kassa|bonnr|bonnummer|datum|tijd|www\.|klantenservice|welkom|bedankt|adres|straat|tel|kvk)\b"],
    "AH_NOISE": [r"^[\W_]+$", r"^\s*$"],
}


@dataclass
class SemanticLine:
    receipt_table_id: str
    raw_receipt_id: str | None
    store_name: str | None
    store_chain: str | None
    reference: str | None
    total_amount: float | None
    discount_total: float | None
    line_id: str
    line_index: int
    raw_line: str
    normalized_line: str
    db_line_total: float | None
    db_discount_amount: float | None
    amount_detected_from_text: float | None
    line_type: str
    article_candidate: bool
    financial_effect: str
    loyalty_effect: bool
    include_in_article_count: bool
    include_in_article_sum: bool
    include_in_total_validation: bool
    rule_id: str
    reason: str


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def amount(text: str) -> float | None:
    matches = AMOUNT_RE.findall(text or "")
    if not matches:
        return None
    try:
        return float(matches[-1].replace(",", "."))
    except Exception:
        return None


def match_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def classify(row: dict[str, Any]) -> SemanticLine:
    raw = str(row.get("raw_label") or "")
    n = norm(raw)
    text_amount = amount(n)
    db_line_total = row.get("line_total")
    db_discount_amount = row.get("discount_amount")

    base = {
        "receipt_table_id": row.get("receipt_table_id"),
        "raw_receipt_id": row.get("raw_receipt_id"),
        "store_name": row.get("store_name"),
        "store_chain": row.get("store_chain"),
        "reference": row.get("reference"),
        "total_amount": row.get("total_amount"),
        "discount_total": row.get("discount_total"),
        "line_id": row.get("line_id"),
        "line_index": int(row.get("line_index") or 0),
        "raw_line": raw,
        "normalized_line": n,
        "db_line_total": db_line_total,
        "db_discount_amount": db_discount_amount,
        "amount_detected_from_text": text_amount,
    }

    def make(line_type, article, financial, loyalty, count, article_sum, total_validation, rule, reason):
        return SemanticLine(
            **base,
            line_type=line_type,
            article_candidate=article,
            financial_effect=financial,
            loyalty_effect=loyalty,
            include_in_article_count=count,
            include_in_article_sum=article_sum,
            include_in_total_validation=total_validation,
            rule_id=rule,
            reason=reason,
        )

    if match_any(n, PATTERNS["AH_NOISE"]):
        return make("AH_NOISE", False, "none", False, False, False, False, "AH_NOISE_RULE", "lege/ruisregel")

    if match_any(n, PATTERNS["AH_TOTAL"]):
        return make("AH_TOTAL", False, "total", False, False, False, True, "AH_TOTAL_RULE", "totaalregel; bewaren voor controle, niet als artikel")

    if match_any(n, PATTERNS["AH_PAYMENT"]):
        return make("AH_PAYMENT", False, "payment", False, False, False, False, "AH_PAYMENT_RULE", "betaalregel; niet als artikel")

    if match_any(n, PATTERNS["AH_TAX"]):
        return make("AH_TAX", False, "tax", False, False, False, False, "AH_TAX_RULE", "btw/fiscale regel; niet als artikel")

    if match_any(n, PATTERNS["AH_LOYALTY_STAMPS"]):
        has_amount = db_line_total is not None or text_amount is not None
        return make("AH_LOYALTY_STAMPS", False, "loyalty_amount" if has_amount else "none", True, False, False, has_amount, "AH_LOYALTY_STAMPS_RULE", "zegels bewaren, niet als artikel")

    if match_any(n, PATTERNS["AH_LOYALTY_POINTS"]):
        return make("AH_LOYALTY_POINTS", False, "none", True, False, False, False, "AH_LOYALTY_POINTS_RULE", "punten/kaartinfo bewaren, niet als artikel")

    if match_any(n, PATTERNS["AH_DISCOUNT"]):
        has_amount = db_line_total is not None or text_amount is not None
        return make("AH_DISCOUNT", False, "discount" if has_amount else "discount_metadata", False, False, False, has_amount, "AH_DISCOUNT_RULE", "korting bewaren, niet als artikel")

    if match_any(n, PATTERNS["AH_METADATA"]) and db_line_total is None and text_amount is None:
        return make("AH_METADATA", False, "none", False, False, False, False, "AH_METADATA_RULE", "metadata zonder bedrag")

    alpha_chars = len(re.findall(r"[a-zA-ZÀ-ÿ]", n))

    # Audit-only: db_line_total explains what currently contributes to sum.
    # This does not determine PO status.
    if db_line_total is not None and alpha_chars >= 3:
        return make("AH_ARTICLE", True, "article_price", False, True, True, True, "AH_DB_LINE_TOTAL_ARTICLE_RULE", "huidige parser heeft line_total; tekst lijkt artikel")

    if db_line_total is not None:
        return make("AH_AMOUNT_METADATA", False, "amount_metadata", False, False, False, True, "AH_DB_AMOUNT_METADATA_RULE", "huidige parser heeft bedrag maar geen duidelijke artikeltekst")

    if text_amount is not None and alpha_chars >= 3:
        return make("AH_ARTICLE_CANDIDATE_TEXT_ONLY", True, "article_price_text_only", False, True, True, True, "AH_TEXT_AMOUNT_ARTICLE_RULE", "tekst bevat bedrag en artikelachtige tekst")

    return make("AH_METADATA", False, "none", False, False, False, False, "AH_METADATA_FALLBACK_RULE", "geen artikel-/korting-/loyaltypatroon")


def fetch_ah_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    sql = """
    SELECT
      rt.id AS receipt_table_id,
      rt.raw_receipt_id,
      rt.store_name,
      rt.store_chain,
      rt.reference,
      rt.total_amount,
      rt.discount_total,
      rtl.id AS line_id,
      rtl.line_index,
      rtl.raw_label,
      rtl.normalized_label,
      rtl.line_total,
      rtl.discount_amount,
      rtl.article_match_status,
      rtl.is_deleted
    FROM receipt_tables rt
    JOIN receipt_table_lines rtl ON rtl.receipt_table_id = rt.id
    WHERE COALESCE(rtl.is_deleted, 0) = 0
      AND (
        LOWER(COALESCE(rt.store_name, '')) LIKE '%albert%'
        OR LOWER(COALESCE(rt.store_chain, '')) LIKE '%albert%'
        OR LOWER(COALESCE(rt.reference, '')) LIKE '%ah%'
        OR LOWER(COALESCE(rt.reference, '')) LIKE '%albert%'
      )
    ORDER BY rt.created_at, rt.id, rtl.line_index
    """
    return [dict(row) for row in conn.execute(sql).fetchall()]


def summarize(lines: list[SemanticLine]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    article_sum = 0.0
    validation_sum = 0.0
    discount_sum = 0.0
    loyalty_sum = 0.0

    for line in lines:
        counts[line.line_type] = counts.get(line.line_type, 0) + 1

        if line.include_in_article_sum and line.db_line_total is not None:
            article_sum += float(line.db_line_total)

        if line.include_in_total_validation:
            if line.db_line_total is not None:
                validation_sum += float(line.db_line_total)
            elif line.amount_detected_from_text is not None:
                validation_sum += float(line.amount_detected_from_text)

        if line.line_type == "AH_DISCOUNT":
            if line.db_line_total is not None:
                discount_sum += float(line.db_line_total)
            elif line.amount_detected_from_text is not None:
                discount_sum += float(line.amount_detected_from_text)

        if line.line_type == "AH_LOYALTY_STAMPS":
            if line.db_line_total is not None:
                loyalty_sum += float(line.db_line_total)
            elif line.amount_detected_from_text is not None:
                loyalty_sum += float(line.amount_detected_from_text)

    return {
        "line_type_counts": counts,
        "article_count_for_audit_only": sum(1 for line in lines if line.include_in_article_count),
        "article_sum_from_db_line_total_for_audit_only": round(article_sum, 2),
        "validation_sum_for_audit_only": round(validation_sum, 2),
        "discount_amount_sum_for_audit_only": round(discount_sum, 2),
        "loyalty_amount_sum_for_audit_only": round(loyalty_sum, 2),
        "loyalty_line_count_for_audit_only": sum(1 for line in lines if line.loyalty_effect),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/app/data/rezzerv.db")
    ap.add_argument("--out", default="/tmp/R9-28A4_reports")
    ap.add_argument("--receipt-id", default=None, help="Optional receipt_table_id filter, e.g. AH foto 3 current receipt id.")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    rows = fetch_ah_rows(conn)
    if args.receipt_id:
        rows = [row for row in rows if row.get("receipt_table_id") == args.receipt_id]

    classified = [classify(row) for row in rows]

    by_receipt: dict[str, list[SemanticLine]] = {}
    receipt_meta: dict[str, dict[str, Any]] = {}

    for line in classified:
        by_receipt.setdefault(line.receipt_table_id, []).append(line)
        receipt_meta.setdefault(line.receipt_table_id, {
            "receipt_table_id": line.receipt_table_id,
            "raw_receipt_id": line.raw_receipt_id,
            "store_name": line.store_name,
            "store_chain": line.store_chain,
            "reference": line.reference,
            "total_amount": line.total_amount,
            "discount_total": line.discount_total,
            "status_source": "not_included_ssot_clean_audit",
        })

    receipts = []
    for rid, lines in by_receipt.items():
        receipts.append({
            **receipt_meta[rid],
            "summary": summarize(lines),
            "lines": [asdict(line) for line in lines],
        })

    audit = {
        "audit": "R9-28A4 AH semantic line classification audit SSOT-clean",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "db": args.db,
        "scope": "AH only; audit only; no parser/status/baseline mutation",
        "ssot_compliance": {
            "status_determination": "not_performed",
            "status_service": "receipt_status_baseline_service_v4.py",
            "parse_status_used": False,
            "po_status_label_used": False,
            "ui_status_touched": False,
            "parser_mutated": False,
            "baseline_mutated": False,
            "note": "This report only classifies receipt_table_lines for diagnostic purposes. It does not compute or override Gecontroleerd/Controle nodig.",
        },
        "sql_source": {
            "receipt_table": "receipt_tables",
            "line_table": "receipt_table_lines",
            "join": "receipt_table_lines.receipt_table_id = receipt_tables.id",
            "line_text": "receipt_table_lines.raw_label",
            "line_total": "receipt_table_lines.line_total",
            "excluded_status_fields": ["receipt_tables.parse_status"],
        },
        "receipt_filter": args.receipt_id,
        "receipt_count": len(receipts),
        "line_count": len(classified),
        "receipts": receipts,
    }

    path = out_dir / f"R9-28A4_ah_semantic_line_classification_audit_ssot_clean_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"R9-28A4 SSOT-clean audit geschreven naar: {path}")
    print("SSOT: status_determination=not_performed parse_status_used=False parser_mutated=False baseline_mutated=False")
    print(f"receipt_count={len(receipts)} line_count={len(classified)}")
    for r in receipts:
        print(f"{r['receipt_table_id']} | {r.get('store_name')} | total={r.get('total_amount')} | {r['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

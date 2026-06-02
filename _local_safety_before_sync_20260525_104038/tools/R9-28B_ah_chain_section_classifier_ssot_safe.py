from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


# R9-28B
# AH chain section classifier, SSOT-safe.
#
# Scope:
# - AH only
# - audit/diagnostic output only
# - no status determination
# - no parser mutation
# - no UI mutation
# - no baseline/status-service mutation
#
# Purpose:
# Classify AH receipt lines into stable chain-level sections before any
# article parsing correction is introduced.

AMOUNT_RE = re.compile(r"(?<!\d)(-?\d{1,3}(?:[.,]\d{2}))(?!\d)")


SECTION_PATTERNS = {
    "AH_COLUMN_HEADER": [
        r"\baantal\b.*\bomschr(?:ijving|\.?jving)?\b.*\bprijs\b.*\bbedrag\b",
        r"\bomschr(?:ijving|\.?jving)?\b.*\bprijs\b.*\bbedrag\b",
        r"^\s*(aantal|omschrijving|omschr\.?jving|prijs|bedrag)(\s+(aantal|omschrijving|omschr\.?jving|prijs|bedrag))*\s*$",
    ],
    "AH_SUBTOTAL": [
        r"\bsubtotaal\b",
    ],
    "AH_DISCOUNT": [
        r"\bbonus\b",
        r"\bbbox\b",
        r"\buw\s+voordeel\b",
        r"\bwaarvan\b",
        r"\bvoordeel\b",
        r"\bkorting\b",
        r"\bactie\b",
        r"\bprijsvoordeel\b",
    ],
    "AH_LOYALTY_STAMPS": [
        r"\bkoopzegels?\b",
        r"\bespaarzegels?\b",
        r"\bpremium\s+zegels?\b",
        r"\bspaarzegels?\b",
    ],
    "AH_LOYALTY_POINTS": [
        r"\bmijn\s+ah\s+miles\b",
        r"\bairmiles\b",
        r"\bair\s*miles\b",
        r"\bspaaracties\b",
        r"\bpremium\b.*\bmiles\b",
    ],
    "AH_TOTAL": [
        r"^\s*totaal\b",
        r"\bte\s+betalen\b",
    ],
    "AH_PAYMENT": [
        r"\bbetaald\s+met\b",
        r"\bpinnen\b",
        r"\bpin\b",
        r"\bpoi\b",
        r"\bterminal\b",
        r"\bmerchant\b",
        r"\bperiode\b",
        r"\btransactie\b",
        r"\btoken\b",
        r"\bv\s*pay\b",
        r"\bmaestro\b",
        r"\bkaart\b",
        r"\bkaartserienummer\b",
        r"\bbetaling\b",
        r"\bautorisatiecode\b",
        r"\bcontactless\b",
        r"\bleesmethode\b",
        r"\bnfc\b",
        r"\bchip\b",
    ],
    "AH_TAX": [
        r"\bbtw\b",
        r"\bover\b.*\beur\b",
        r"^\s*9%\b",
        r"^\s*21%\b",
        r"\bvat\b",
    ],
    "AH_FOOTER": [
        r"\bvragen\s+over\b",
        r"\bkassabon\b",
        r"\bkassamedewerkers\b",
        r"\bhelpen\s+je\s+graag\b",
        r"\blekker\s+lang\s+open\b",
        r"\bma\s+t/m\s+za\b",
        r"\bzo\s+\d",
    ],
    "AH_STORE_HEADER": [
        r"\balbert\s+heijn\b",
        r"\bger\s+koopman\b",
        r"\bstation\s+groningen\b",
        r"\bpolenplein\b",
        r"\btel\b",
    ],
    "AH_LOYALTY_CARD": [
        r"\bbonuskaart\b",
        r"\bairmiles\s+nr\b",
    ],
}


@dataclass
class AHSectionLine:
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
    section_type: str
    section_group: str
    may_be_article: bool
    may_affect_total: bool
    may_affect_loyalty: bool
    rule_id: str
    reason: str


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def amount_from_text(text: str) -> float | None:
    matches = AMOUNT_RE.findall(text or "")
    if not matches:
        return None
    try:
        return float(matches[-1].replace(",", "."))
    except Exception:
        return None


def match_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def first_section_match(n: str) -> tuple[str | None, str | None]:
    # Order matters: column headers/payment/tax must be caught before generic article-ish text.
    ordered = [
        "AH_COLUMN_HEADER",
        "AH_PAYMENT",
        "AH_TAX",
        "AH_TOTAL",
        "AH_SUBTOTAL",
        "AH_DISCOUNT",
        "AH_LOYALTY_STAMPS",
        "AH_LOYALTY_POINTS",
        "AH_LOYALTY_CARD",
        "AH_FOOTER",
        "AH_STORE_HEADER",
    ]
    for section in ordered:
        if match_any(n, SECTION_PATTERNS[section]):
            return section, f"{section}_RULE"
    return None, None


def classify_row(row: dict[str, Any]) -> AHSectionLine:
    raw = str(row.get("raw_label") or "")
    n = normalize(raw)
    text_amount = amount_from_text(n)
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

    def make(section_type: str, section_group: str, may_article: bool, may_total: bool, may_loyalty: bool, rule: str, reason: str) -> AHSectionLine:
        return AHSectionLine(
            **base,
            section_type=section_type,
            section_group=section_group,
            may_be_article=may_article,
            may_affect_total=may_total,
            may_affect_loyalty=may_loyalty,
            rule_id=rule,
            reason=reason,
        )

    if not n:
        return make("AH_NOISE", "outside_article_section", False, False, False, "AH_EMPTY_LINE_RULE", "lege OCR-regel")

    section, rule = first_section_match(n)
    if section:
        if section == "AH_COLUMN_HEADER":
            return make(section, "structure", False, False, False, rule, "AH-kolomkop; mag nooit artikel zijn")
        if section == "AH_PAYMENT":
            return make(section, "payment", False, False, False, rule, "betaal-/terminalregel; mag nooit artikel zijn")
        if section == "AH_TAX":
            return make(section, "tax", False, False, False, rule, "BTW/fiscale regel; mag nooit artikel zijn")
        if section == "AH_TOTAL":
            return make(section, "total", False, True, False, rule, "totaalregel; controleanker, geen artikel")
        if section == "AH_SUBTOTAL":
            return make(section, "subtotal", False, True, False, rule, "subtotaalregel; controleanker, geen artikel")
        if section == "AH_DISCOUNT":
            return make(section, "discount", False, True, False, rule, "korting/bonusregel; bewaren als correctie, geen artikel")
        if section == "AH_LOYALTY_STAMPS":
            return make(section, "loyalty_stamps", False, True, True, rule, "koopzegels/spaarzegels; betaalimpact mogelijk, geen voorraadartikel")
        if section == "AH_LOYALTY_POINTS":
            return make(section, "loyalty_points", False, False, True, rule, "punten/spaaractie; bewaren als loyalty, geen artikel")
        if section == "AH_LOYALTY_CARD":
            return make(section, "loyalty_card", False, False, True, rule, "klantkaartinformatie; geen artikel")
        if section == "AH_FOOTER":
            return make(section, "footer", False, False, False, rule, "footertekst; geen artikel")
        if section == "AH_STORE_HEADER":
            return make(section, "header", False, False, False, rule, "winkelheader; geen artikel")

    # Candidate article line.
    # This is deliberately broad: R9-28B only separates structural sections.
    # Real AH article parsing/splitting follows in R9-28C.
    alpha_chars = len(re.findall(r"[a-zA-ZÀ-ÿ]", n))
    if alpha_chars >= 3:
        return make("AH_ARTICLE_CANDIDATE", "article_section", True, True, False, "AH_ARTICLE_SECTION_CANDIDATE_RULE", "niet-structurele AH-regel binnen mogelijke artikelzone")

    return make("AH_NOISE_OR_METADATA", "outside_article_section", False, False, False, "AH_NOISE_OR_METADATA_RULE", "geen duidelijke AH-sectie of artikeltekst")


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


def summarize(lines: list[AHSectionLine]) -> dict[str, Any]:
    section_counts: dict[str, int] = {}
    group_counts: dict[str, int] = {}
    candidate_sum = 0.0
    non_article_total_sum = 0.0

    for line in lines:
        section_counts[line.section_type] = section_counts.get(line.section_type, 0) + 1
        group_counts[line.section_group] = group_counts.get(line.section_group, 0) + 1

        if line.may_be_article and line.db_line_total is not None:
            candidate_sum += float(line.db_line_total)

        if not line.may_be_article and line.db_line_total is not None:
            non_article_total_sum += float(line.db_line_total)

    blocked_db_total_lines = [
        {
            "line_index": line.line_index,
            "raw_line": line.raw_line,
            "section_type": line.section_type,
            "db_line_total": line.db_line_total,
            "reason": line.reason,
        }
        for line in lines
        if not line.may_be_article and line.db_line_total is not None
    ]

    return {
        "section_counts": section_counts,
        "section_group_counts": group_counts,
        "article_candidate_count_for_audit_only": sum(1 for line in lines if line.may_be_article),
        "article_candidate_sum_from_db_line_total_for_audit_only": round(candidate_sum, 2),
        "blocked_non_article_db_total_sum_for_audit_only": round(non_article_total_sum, 2),
        "blocked_non_article_db_total_lines": blocked_db_total_lines,
    }


def build_report(db: str, receipt_id: str | None) -> dict[str, Any]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row

    rows = fetch_ah_rows(conn)
    if receipt_id:
        rows = [row for row in rows if row.get("receipt_table_id") == receipt_id]

    classified = [classify_row(row) for row in rows]

    by_receipt: dict[str, list[AHSectionLine]] = {}
    receipt_meta: dict[str, dict[str, Any]] = {}

    for line in classified:
        by_receipt.setdefault(line.receipt_table_id, []).append(line)
        receipt_meta.setdefault(
            line.receipt_table_id,
            {
                "receipt_table_id": line.receipt_table_id,
                "raw_receipt_id": line.raw_receipt_id,
                "store_name": line.store_name,
                "store_chain": line.store_chain,
                "reference": line.reference,
                "total_amount": line.total_amount,
                "discount_total": line.discount_total,
                "status_source": "not_included_ssot_clean_audit",
            },
        )

    receipts = []
    for rid, lines in by_receipt.items():
        receipts.append({
            **receipt_meta[rid],
            "summary": summarize(lines),
            "lines": [asdict(line) for line in lines],
        })

    chain_summary: dict[str, Any] = {
        "receipt_count": len(receipts),
        "line_count": len(classified),
        "section_counts": {},
        "section_group_counts": {},
        "blocked_non_article_db_total_line_count": 0,
    }

    for receipt in receipts:
        summary = receipt["summary"]
        for key, value in summary["section_counts"].items():
            chain_summary["section_counts"][key] = chain_summary["section_counts"].get(key, 0) + value
        for key, value in summary["section_group_counts"].items():
            chain_summary["section_group_counts"][key] = chain_summary["section_group_counts"].get(key, 0) + value
        chain_summary["blocked_non_article_db_total_line_count"] += len(summary["blocked_non_article_db_total_lines"])

    return {
        "audit": "R9-28B AH chain section classifier SSOT-safe",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "db": db,
        "scope": "AH chain profile; section classification only; no parser/status/baseline/UI mutation",
        "ssot_compliance": {
            "status_determination": "not_performed",
            "status_service": "receipt_status_baseline_service_v4.py",
            "parse_status_used": False,
            "po_status_label_used": False,
            "ui_status_touched": False,
            "parser_mutated": False,
            "baseline_mutated": False,
            "note": "R9-28B only classifies AH receipt sections to prevent column headers/payment/tax/footer lines from being treated as article candidates in later steps.",
        },
        "chain_profile": {
            "store_chain": "Albert Heijn",
            "recognized_sections": [
                "AH_STORE_HEADER",
                "AH_LOYALTY_CARD",
                "AH_COLUMN_HEADER",
                "AH_ARTICLE_CANDIDATE",
                "AH_SUBTOTAL",
                "AH_DISCOUNT",
                "AH_LOYALTY_STAMPS",
                "AH_LOYALTY_POINTS",
                "AH_TOTAL",
                "AH_PAYMENT",
                "AH_TAX",
                "AH_FOOTER",
                "AH_NOISE_OR_METADATA",
            ],
            "next_steps": [
                "R9-28C column-aware AH article parser",
                "R9-28D AH discount/stamps/points parser",
                "R9-28E AH total reconciliation",
                "R9-28F full receipt batch regression",
            ],
        },
        "sql_source": {
            "receipt_table": "receipt_tables",
            "line_table": "receipt_table_lines",
            "join": "receipt_table_lines.receipt_table_id = receipt_tables.id",
            "line_text": "receipt_table_lines.raw_label",
            "line_total": "receipt_table_lines.line_total",
            "excluded_status_fields": ["receipt_tables.parse_status"],
        },
        "receipt_filter": receipt_id,
        "chain_summary": chain_summary,
        "receipts": receipts,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="/app/data/rezzerv.db")
    parser.add_argument("--out", default="/tmp/R9-28B_reports")
    parser.add_argument("--receipt-id", default=None)
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = build_report(args.db, args.receipt_id)

    path = out_dir / f"R9-28B_ah_chain_section_classifier_ssot_safe_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"R9-28B AH chain section classifier geschreven naar: {path}")
    print("SSOT: status_determination=not_performed parse_status_used=False parser_mutated=False baseline_mutated=False")
    print(f"receipt_count={report['chain_summary']['receipt_count']} line_count={report['chain_summary']['line_count']}")
    print(f"section_counts={report['chain_summary']['section_counts']}")
    print(f"blocked_non_article_db_total_line_count={report['chain_summary']['blocked_non_article_db_total_line_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

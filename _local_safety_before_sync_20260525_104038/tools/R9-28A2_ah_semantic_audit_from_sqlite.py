from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


AH_FILE_PATTERNS = ["ah foto", "ah app"]
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
    receipt_id: Any
    bestand: str
    line_number: int | None
    raw_line: str
    normalized_line: str
    amount_detected: float | None
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


def classify(receipt_id: Any, bestand: str, line_number: int | None, raw: str) -> SemanticLine:
    n = norm(raw)
    a = amount(n)

    if match_any(n, PATTERNS["AH_NOISE"]):
        return SemanticLine(receipt_id, bestand, line_number, raw, n, a, "AH_NOISE", False, "none", False, False, False, False, "AH_NOISE_RULE", "lege/ruisregel")

    for line_type in ["AH_TOTAL", "AH_PAYMENT", "AH_TAX", "AH_LOYALTY_STAMPS", "AH_LOYALTY_POINTS", "AH_DISCOUNT"]:
        if match_any(n, PATTERNS[line_type]):
            if line_type == "AH_TOTAL":
                return SemanticLine(receipt_id, bestand, line_number, raw, n, a, line_type, False, "total", False, False, False, True, "AH_TOTAL_RULE", "totaalregel; niet als artikel")
            if line_type == "AH_PAYMENT":
                return SemanticLine(receipt_id, bestand, line_number, raw, n, a, line_type, False, "payment", False, False, False, False, "AH_PAYMENT_RULE", "betaalregel; niet als artikel")
            if line_type == "AH_TAX":
                return SemanticLine(receipt_id, bestand, line_number, raw, n, a, line_type, False, "tax", False, False, False, False, "AH_TAX_RULE", "btw/fiscale regel")
            if line_type == "AH_LOYALTY_STAMPS":
                return SemanticLine(receipt_id, bestand, line_number, raw, n, a, line_type, False, "loyalty_amount" if a is not None else "none", True, False, False, a is not None, "AH_LOYALTY_STAMPS_RULE", "zegels bewaren, niet als artikel")
            if line_type == "AH_LOYALTY_POINTS":
                return SemanticLine(receipt_id, bestand, line_number, raw, n, a, line_type, False, "none", True, False, False, False, "AH_LOYALTY_POINTS_RULE", "punten bewaren, niet als artikel")
            if line_type == "AH_DISCOUNT":
                return SemanticLine(receipt_id, bestand, line_number, raw, n, a, line_type, False, "discount" if a is not None else "discount_metadata", False, False, False, a is not None, "AH_DISCOUNT_RULE", "korting bewaren, niet als artikel")

    if match_any(n, PATTERNS["AH_METADATA"]) and a is None:
        return SemanticLine(receipt_id, bestand, line_number, raw, n, a, "AH_METADATA", False, "none", False, False, False, False, "AH_METADATA_RULE", "metadata zonder bedrag")

    alpha_chars = len(re.findall(r"[a-zA-ZÀ-ÿ]", n))
    if a is not None and alpha_chars >= 3:
        return SemanticLine(receipt_id, bestand, line_number, raw, n, a, "AH_ARTICLE", True, "article_price", False, True, True, True, "AH_ARTICLE_WITH_PRICE_RULE", "artikelkandidaat met tekst en bedrag")

    if a is not None:
        return SemanticLine(receipt_id, bestand, line_number, raw, n, a, "AH_METADATA", False, "amount_metadata", False, False, False, True, "AH_AMOUNT_METADATA_RULE", "bedrag zonder duidelijke artikeltekst")

    return SemanticLine(receipt_id, bestand, line_number, raw, n, a, "AH_METADATA", False, "none", False, False, False, False, "AH_METADATA_FALLBACK_RULE", "geen artikel-/korting-/loyaltypatroon")


def table_info(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def tables(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]


def first_existing(cols: list[str], candidates: list[str]) -> str | None:
    for c in candidates:
        if c in cols:
            return c
    return None


def discover_schema(conn: sqlite3.Connection) -> dict[str, Any]:
    ts = tables(conn)
    info = {t: table_info(conn, t) for t in ts}

    receipt_candidates = []
    line_candidates = []

    for t, cols in info.items():
        lower = t.lower()
        if "receipt" in lower and not any(x in lower for x in ["line", "item"]):
            receipt_candidates.append(t)
        if "receipt" in lower and any(x in lower for x in ["line", "item"]):
            line_candidates.append(t)

    return {"tables": ts, "columns": info, "receipt_candidates": receipt_candidates, "line_candidates": line_candidates}


def fetch_receipt_lines(conn: sqlite3.Connection, schema: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    # Prefer canonical schema.
    preferred_pairs = [
        ("receipts", "receipt_lines"),
        ("receipt_tables", "receipt_table_lines"),
        ("purchase_receipts", "purchase_receipt_lines"),
    ]

    for receipt_table, line_table in preferred_pairs:
        if receipt_table in schema["columns"] and line_table in schema["columns"]:
            rows = try_pair(conn, receipt_table, line_table, schema["columns"][receipt_table], schema["columns"][line_table])
            if rows:
                return rows, {"receipt_table": receipt_table, "line_table": line_table, "strategy": "preferred_pair"}

    # Try all discovered pairs.
    for receipt_table in schema["receipt_candidates"]:
        for line_table in schema["line_candidates"]:
            rows = try_pair(conn, receipt_table, line_table, schema["columns"][receipt_table], schema["columns"][line_table])
            if rows:
                return rows, {"receipt_table": receipt_table, "line_table": line_table, "strategy": "discovered_pair"}

    return [], {"strategy": "not_found"}


def try_pair(conn: sqlite3.Connection, receipt_table: str, line_table: str, rcols: list[str], lcols: list[str]) -> list[dict[str, Any]]:
    rid = first_existing(rcols, ["id", "receipt_id", "receipt_table_id"])
    rfile = first_existing(rcols, ["bestand", "filename", "source_filename", "file_name", "original_filename", "name"])
    lid = first_existing(lcols, ["receipt_id", "receipt_table_id", "table_id"])
    raw = first_existing(lcols, ["raw_text", "raw_line", "line_text", "text", "ocr_text", "description", "parsed_name"])
    lno = first_existing(lcols, ["line_number", "line_no", "position", "idx"])

    if not rid or not lid or not raw:
        return []

    # If no filename column exists, try store_name + id only, but this is weaker.
    filename_expr = f"r.{rfile}" if rfile else "CAST(r.id AS TEXT)"
    line_no_expr = f"l.{lno}" if lno else "NULL"

    sql = f"""
    SELECT r.{rid} AS receipt_id,
           {filename_expr} AS bestand,
           {line_no_expr} AS line_number,
           l.{raw} AS raw_line
    FROM {receipt_table} r
    JOIN {line_table} l ON l.{lid} = r.{rid}
    WHERE LOWER(COALESCE({filename_expr}, '')) LIKE '%ah%'
       OR LOWER(COALESCE({filename_expr}, '')) LIKE '%albert%'
    ORDER BY r.{rid}, {line_no_expr}
    """
    try:
        rows = [dict(r) for r in conn.execute(sql).fetchall()]
    except Exception:
        return []

    # Keep AH foto/app files if filename is present.
    filtered = []
    for row in rows:
        b = str(row.get("bestand") or "").lower()
        raw_line = str(row.get("raw_line") or "").strip()
        if not raw_line:
            continue
        if any(p in b for p in AH_FILE_PATTERNS) or "albert" in b or "ah" in b:
            filtered.append(row)
    return filtered


def summarize(lines: list[SemanticLine]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    article_sum = 0.0
    validation_sum = 0.0
    discount_sum = 0.0
    loyalty_sum = 0.0

    for line in lines:
        counts[line.line_type] = counts.get(line.line_type, 0) + 1
        if line.include_in_article_sum and line.amount_detected is not None:
            article_sum += line.amount_detected
        if line.include_in_total_validation and line.amount_detected is not None:
            validation_sum += line.amount_detected
        if line.line_type == "AH_DISCOUNT" and line.amount_detected is not None:
            discount_sum += line.amount_detected
        if line.line_type == "AH_LOYALTY_STAMPS" and line.amount_detected is not None:
            loyalty_sum += line.amount_detected

    return {
        "line_type_counts": counts,
        "article_count": sum(1 for line in lines if line.include_in_article_count),
        "article_sum": round(article_sum, 2),
        "validation_sum": round(validation_sum, 2),
        "discount_amount_sum": round(discount_sum, 2),
        "loyalty_amount_sum": round(loyalty_sum, 2),
        "loyalty_line_count": sum(1 for line in lines if line.loyalty_effect),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/app/data/rezzerv.db")
    ap.add_argument("--out", default="/app/tools/reports")
    args = ap.parse_args()

    db = Path(args.db)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row

    schema = discover_schema(conn)
    rows, strategy = fetch_receipt_lines(conn, schema)

    by_file: dict[str, list[SemanticLine]] = {}
    for row in rows:
        bestand = str(row.get("bestand") or "unknown")
        line = classify(row.get("receipt_id"), bestand, row.get("line_number"), str(row.get("raw_line") or ""))
        by_file.setdefault(bestand, []).append(line)

    receipts = []
    for bestand, lines in sorted(by_file.items()):
        receipts.append({
            "bestand": bestand,
            "summary": summarize(lines),
            "lines": [asdict(line) for line in lines],
        })

    audit = {
        "audit": "R9-28A2 AH semantic line classification audit from runtime sqlite",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "db": str(db),
        "schema_strategy": strategy,
        "scope": "AH only; audit only; no parser/status/baseline mutation",
        "receipt_count": len(receipts),
        "receipts": receipts,
        "schema_discovery": {
            "receipt_candidates": schema["receipt_candidates"],
            "line_candidates": schema["line_candidates"],
        },
    }

    path = out_dir / f"R9-28A2_ah_semantic_line_classification_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"R9-28A2 audit geschreven naar: {path}")
    print(f"strategy={strategy}")
    print(f"receipt_count={len(receipts)}")
    for r in receipts:
        print(f"{r['bestand']}: {r['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

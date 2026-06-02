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
AH_MARKERS = [
    "albert heijn",
    "aantal omschrijving",
    "omschr",
    "bonuskaart",
    "koopzegels",
    "betaald met",
    "pinnen",
    "btw over",
]


@dataclass
class RawSource:
    table: str
    row_id: Any
    receipt_table_id: str | None
    raw_receipt_id: str | None
    source_column: str
    text: str


@dataclass
class SectionLine:
    source_table: str
    source_row_id: Any
    receipt_table_id: str | None
    raw_receipt_id: str | None
    line_index: int
    raw_line: str
    normalized_line: str
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


def table_names(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]


def table_cols(conn: sqlite3.Connection, table: str) -> list[tuple[str, str]]:
    return [(r[1], r[2]) for r in conn.execute(f"PRAGMA table_info({table})")]


def safe_select_text_samples(conn: sqlite3.Connection, table: str, cols: list[str], limit: int) -> list[dict[str, Any]]:
    select_cols = ", ".join(cols)
    try:
        rows = conn.execute(f"SELECT {select_cols} FROM {table} LIMIT {limit}").fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def likely_text_columns(cols: list[tuple[str, str]]) -> list[str]:
    out = []
    for name, typ in cols:
        lname = name.lower()
        ltyp = (typ or "").lower()
        if any(k in lname for k in ["ocr", "raw", "text", "content", "result", "response", "diagnostic", "parsed"]):
            if "blob" not in ltyp:
                out.append(name)
    return out


def detect_sources(conn: sqlite3.Connection) -> tuple[list[RawSource], dict[str, Any]]:
    sources: list[RawSource] = []
    discovery: dict[str, Any] = {"tables": {}, "note": "R9-28B2 searches raw/full OCR text sources; it deliberately avoids receipt_table_lines as primary input."}

    for table in table_names(conn):
        cols_info = table_cols(conn, table)
        cols = [c for c, _ in cols_info]
        text_cols = likely_text_columns(cols_info)
        if not text_cols:
            discovery["tables"][table] = {"text_columns": [], "sampled": False}
            continue

        id_col = "id" if "id" in cols else cols[0]
        rt_col = "receipt_table_id" if "receipt_table_id" in cols else None
        rr_col = "raw_receipt_id" if "raw_receipt_id" in cols else None

        select_cols = [id_col]
        for optional in [rt_col, rr_col]:
            if optional and optional not in select_cols:
                select_cols.append(optional)
        for c in text_cols:
            if c not in select_cols:
                select_cols.append(c)

        rows = safe_select_text_samples(conn, table, select_cols, 5000)
        matched_count = 0
        for row in rows:
            for c in text_cols:
                value = row.get(c)
                if not isinstance(value, str):
                    continue
                text = value.strip()
                if len(text) < 20:
                    continue
                n = normalize(text)
                if any(marker in n for marker in AH_MARKERS):
                    matched_count += 1
                    sources.append(
                        RawSource(
                            table=table,
                            row_id=row.get(id_col),
                            receipt_table_id=row.get(rt_col) if rt_col else None,
                            raw_receipt_id=row.get(rr_col) if rr_col else None,
                            source_column=c,
                            text=text,
                        )
                    )

        discovery["tables"][table] = {
            "text_columns": text_cols,
            "sampled": True,
            "sample_rows": len(rows),
            "ah_text_matches": matched_count,
        }

    # Enrich raw_receipt_id -> receipt_table_id if possible.
    try:
        mapping = {
            r["raw_receipt_id"]: r["id"]
            for r in conn.execute("SELECT id, raw_receipt_id FROM receipt_tables WHERE raw_receipt_id IS NOT NULL").fetchall()
        }
        for s in sources:
            if not s.receipt_table_id and s.raw_receipt_id in mapping:
                s.receipt_table_id = mapping[s.raw_receipt_id]
    except Exception:
        pass

    return sources, discovery


def classify_line(source: RawSource, line_index: int, raw_line: str) -> SectionLine:
    n = normalize(raw_line)
    a = amount_from_text(n)

    def make(section_type: str, group: str, may_article: bool, may_total: bool, may_loyalty: bool, rule: str, reason: str) -> SectionLine:
        return SectionLine(
            source_table=source.table,
            source_row_id=source.row_id,
            receipt_table_id=source.receipt_table_id,
            raw_receipt_id=source.raw_receipt_id,
            line_index=line_index,
            raw_line=raw_line,
            normalized_line=n,
            amount_detected_from_text=a,
            section_type=section_type,
            section_group=group,
            may_be_article=may_article,
            may_affect_total=may_total,
            may_affect_loyalty=may_loyalty,
            rule_id=rule,
            reason=reason,
        )

    if not n:
        return make("AH_NOISE", "outside_article_section", False, False, False, "AH_EMPTY_LINE_RULE", "lege OCR-regel")

    if re.search(r"\baantal\b.*\bomschr", n) and re.search(r"\bprijs\b|\bbedrag\b", n):
        return make("AH_COLUMN_HEADER", "structure", False, False, False, "AH_COLUMN_HEADER_RULE", "AH kolomkop; nooit artikel")

    if re.search(r"\b(albert\s+heijn|tel:|telefoon|polenplein|station\s+groningen|ger\s+koopman)\b", n):
        return make("AH_STORE_HEADER", "header", False, False, False, "AH_STORE_HEADER_RULE", "winkelheader; geen artikel")

    if re.search(r"\b(bonuskaart|airmiles\s+nr|air\s*miles\s+nr)\b", n):
        return make("AH_LOYALTY_CARD", "loyalty_card", False, False, True, "AH_LOYALTY_CARD_RULE", "klantkaartinformatie; geen artikel")

    if re.search(r"^\s*\d+\s+subtotaal\b|\bsubtotaal\b", n):
        return make("AH_SUBTOTAL", "subtotal", False, True, False, "AH_SUBTOTAL_RULE", "subtotaalregel; controleanker, geen artikel")

    if re.search(r"\b(bonus|bbox|uw\s+voordeel|waarvan|voordeel|korting|actie|prijsvoordeel)\b", n):
        return make("AH_DISCOUNT", "discount", False, True, False, "AH_DISCOUNT_RULE", "bonus/korting; bewaren als correctie, geen artikel")

    if re.search(r"\b(koopzegels?|espa(a)?rzegels?|spaarzegels?)\b", n):
        return make("AH_LOYALTY_STAMPS", "loyalty_stamps", False, True, True, "AH_LOYALTY_STAMPS_RULE", "koop-/spaarzegels; betaalimpact mogelijk, geen voorraadartikel")

    if re.search(r"\b(spaaracties|mijn\s+ah\s+miles|miles\s+premium)\b", n):
        return make("AH_LOYALTY_POINTS", "loyalty_points", False, False, True, "AH_LOYALTY_POINTS_RULE", "punten/spaaractie; bewaren als loyalty, geen artikel")

    if re.search(r"^\s*totaal\b|\bte\s+betalen\b", n):
        return make("AH_TOTAL", "total", False, True, False, "AH_TOTAL_RULE", "totaalregel; controleanker, geen artikel")

    if re.search(r"\b(betaald\s+met|pinnen|pin|poi|terminal|merchant|periode|transactie|token|v\s*pay|maestro|kaart|kaartserienummer|betaling|autorisatiecode|contactless|leesmethode|nfc|chip)\b", n):
        return make("AH_PAYMENT", "payment", False, False, False, "AH_PAYMENT_RULE", "betaal-/terminalregel; nooit artikel")

    if re.search(r"\b(btw|over\s+eur|vat)\b|^\s*(9%|21%)\b", n):
        return make("AH_TAX", "tax", False, False, False, "AH_TAX_RULE", "BTW/fiscale regel; nooit artikel")

    if re.search(r"\b(vragen\s+over|kassabon|kassamedewerkers|helpen\s+je\s+graag|lekker\s+lang\s+open|ma\s+t/m\s+za|gratis\s+een\s+product)\b", n):
        return make("AH_FOOTER", "footer", False, False, False, "AH_FOOTER_RULE", "footertekst; geen artikel")

    # Candidate article: count/quantity-like prefix or article line with meaningful text.
    if re.search(r"^\s*(\d+|[ilItT])\s+[a-zA-ZÀ-ÿ0-9]", raw_line):
        return make("AH_ARTICLE_CANDIDATE", "article_section", True, True, False, "AH_ARTICLE_PREFIX_RULE", "regel start met aantal/ocr-variant en artikeltekst")

    if len(re.findall(r"[a-zA-ZÀ-ÿ]", n)) >= 3:
        return make("AH_TEXT_CANDIDATE_OR_METADATA", "unknown_text", True, False, False, "AH_TEXT_FALLBACK_RULE", "tekstregel zonder duidelijke AH-structuur; kandidaat voor vervolganalyse")

    return make("AH_NOISE_OR_METADATA", "outside_article_section", False, False, False, "AH_NOISE_OR_METADATA_RULE", "geen duidelijke AH-sectie of artikeltekst")


def split_lines(text: str) -> list[str]:
    # Keep line order; remove extreme control chars but do not normalize columns away.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for line in text.split("\n"):
        clean = line.strip()
        if clean:
            lines.append(clean)
    return lines


def build_report(db: str) -> dict[str, Any]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    sources, discovery = detect_sources(conn)

    source_reports = []
    chain_counts: dict[str, int] = {}
    group_counts: dict[str, int] = {}
    all_lines: list[SectionLine] = []

    for source in sources:
        lines = [classify_line(source, i, line) for i, line in enumerate(split_lines(source.text))]
        all_lines.extend(lines)
        counts: dict[str, int] = {}
        for line in lines:
            counts[line.section_type] = counts.get(line.section_type, 0) + 1
            chain_counts[line.section_type] = chain_counts.get(line.section_type, 0) + 1
            group_counts[line.section_group] = group_counts.get(line.section_group, 0) + 1
        source_reports.append({
            "source": asdict(source),
            "line_count": len(lines),
            "section_counts": counts,
            "lines": [asdict(line) for line in lines],
        })

    return {
        "audit": "R9-28B2 AH raw OCR/source section classifier SSOT-safe",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "db": db,
        "scope": "AH chain profile; raw/source section classification only; no parser/status/baseline/UI mutation",
        "ssot_compliance": {
            "status_determination": "not_performed",
            "status_service": "receipt_status_baseline_service_v4.py",
            "parse_status_used": False,
            "po_status_label_used": False,
            "ui_status_touched": False,
            "parser_mutated": False,
            "baseline_mutated": False,
            "note": "R9-28B2 uses raw/full OCR-like source text when available. It does not compute or override Gecontroleerd/Controle nodig.",
        },
        "why_b2_exists": {
            "problem_in_R9_28B": "R9-28B classified receipt_table_lines, which are already post-parser article rows. That input cannot expose header/discount/stamps/total/tax/footer sections reliably.",
            "correction": "R9-28B2 searches raw/full OCR source text before article parsing.",
        },
        "discovery": discovery,
        "chain_summary": {
            "source_count": len(sources),
            "line_count": len(all_lines),
            "section_counts": chain_counts,
            "section_group_counts": group_counts,
        },
        "sources": source_reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="/app/data/rezzerv.db")
    parser.add_argument("--out", default="/tmp/R9-28B2_reports")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = build_report(args.db)
    path = out_dir / f"R9-28B2_ah_raw_source_section_classifier_ssot_safe_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"R9-28B2 AH raw/source section classifier geschreven naar: {path}")
    print("SSOT: status_determination=not_performed parse_status_used=False parser_mutated=False baseline_mutated=False")
    print(f"source_count={report['chain_summary']['source_count']} line_count={report['chain_summary']['line_count']}")
    print(f"section_counts={report['chain_summary']['section_counts']}")
    if report["chain_summary"]["source_count"] == 0:
        print("LET OP: geen raw/full OCR-source gevonden. Bekijk discovery in het JSON-rapport; dan moet de upstream OCR opslag of export worden gebruikt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

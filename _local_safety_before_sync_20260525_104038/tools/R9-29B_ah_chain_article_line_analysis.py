from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


# R9-29B
# AH chain-wide article-line analysis from existing Kassa data.
#
# Guardrails:
# - read-only
# - no parser mutation
# - no OCR mutation
# - no database mutation
# - no status determination
# - no UI mutation
# - no change to receipt_status_baseline_service_v4.py
#
# Purpose:
# Use the current receipt_import_batches.results_json scope and existing
# receipt_tables / receipt_table_lines to analyse all AH receipts together:
# - article lines vs non-article candidates
# - discounts
# - loyalty / stamps / points / zegels
# - line sum mismatch signals
# - chain-wide recurring AH patterns
#
# This is an analysis tool. It does not fix or promote rules automatically.


AH_STORE_PATTERNS = (
    re.compile(r"\balbert\s+hei(?:jn|in)\b", re.IGNORECASE),
    re.compile(r"(^|\W)ah($|\W)", re.IGNORECASE),
    re.compile(r"\bah\s*to\s*go\b", re.IGNORECASE),
)

NON_ARTICLE_TERMS = re.compile(
    r"\b("
    r"totaal|subtotaal|te\s+betalen|betaling|betaald|pin|contactloos|nfc|visa|mastercard|"
    r"maestro|transactie|terminal|referentie|btw|belasting|wisselgeld|contant|bonnummer|"
    r"datum|tijd|kassabon|welkom|bedankt|filiaal|winkel|klant|bonuskaart|ah\s+bonus|"
    r"saldo|spaarsaldo"
    r")\b",
    re.IGNORECASE,
)

LOYALTY_TERMS = re.compile(
    r"\b("
    r"zegel|zegels|koopzegel|koopzegels|spaar|sparen|punten|punt|bonusbox|premium|"
    r"actiezegel|actie\s*zegel|spaaractie"
    r")\b",
    re.IGNORECASE,
)

DISCOUNT_TERMS = re.compile(
    r"\b("
    r"korting|bonus|actie|voordeel|actieprijs|prijsvoordeel|2e\s+halve|2e\s+gratis|"
    r"gratis|retour|correctie"
    r")\b",
    re.IGNORECASE,
)

QUANTITY_OR_MULTIBUY = re.compile(
    r"(^|\s)(\d+[,.]?\d*)\s*[xX]\s*[-+]?\d+[,.]\d{2}\b|"
    r"\b\d+\s*voor\s*[-+]?\d+[,.]\d{2}\b|"
    r"\b\d+[,.]?\d*\s*(kg|g|l|ml)\b",
    re.IGNORECASE,
)

AMOUNT_PATTERN = re.compile(r"[-+]?\d+[,.]\d{2}")


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    if not _has_table(conn, table):
        return []
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _first_existing(cols: list[str], candidates: list[str]) -> str | None:
    by_lower = {c.lower(): c for c in cols}
    for c in candidates:
        if c.lower() in by_lower:
            return by_lower[c.lower()]
    return None


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _load_latest_batch(conn: sqlite3.Connection, source_filename: str, batch_id: str | None = None) -> dict[str, Any]:
    if not _has_table(conn, "receipt_import_batches"):
        raise RuntimeError("receipt_import_batches table not found")

    if batch_id:
        row = conn.execute("SELECT * FROM receipt_import_batches WHERE id = ?", (batch_id,)).fetchone()
    else:
        row = conn.execute(
            """
            SELECT *
            FROM receipt_import_batches
            WHERE source_filename = ?
              AND status = 'completed'
            ORDER BY finished_at DESC, created_at DESC
            LIMIT 1
            """,
            (source_filename,),
        ).fetchone()

    if not row:
        raise RuntimeError(f"No completed receipt_import_batches row found for {source_filename!r}")
    return dict(row)


def _load_batch_entries(batch: dict[str, Any]) -> list[dict[str, Any]]:
    raw = batch.get("results_json")
    if not raw:
        return []
    data = json.loads(raw)
    if not isinstance(data, list):
        raise RuntimeError("receipt_import_batches.results_json is not a list")
    return [dict(x) for x in data]


def _is_ah(row: dict[str, Any]) -> bool:
    store_text = " | ".join(
        str(row.get(k) or "")
        for k in ("store_name", "store_chain")
    )
    return any(p.search(store_text) for p in AH_STORE_PATTERNS)


def _fetch_receipts(conn: sqlite3.Connection, receipt_table_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not receipt_table_ids:
        return {}
    placeholders = ",".join("?" for _ in receipt_table_ids)
    rows = conn.execute(
        f"""
        SELECT
            rt.*,
            rr.original_filename AS raw_original_filename,
            rr.mime_type AS raw_mime_type,
            rr.storage_path AS raw_storage_path
        FROM receipt_tables rt
        LEFT JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
        WHERE rt.id IN ({placeholders})
        """,
        receipt_table_ids,
    ).fetchall()
    return {str(row["id"]): dict(row) for row in rows}


def _fetch_lines(conn: sqlite3.Connection, receipt_table_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not _has_table(conn, "receipt_table_lines"):
        return [], {"error": "receipt_table_lines table not found"}

    cols = _columns(conn, "receipt_table_lines")
    receipt_col = _first_existing(cols, ["receipt_table_id", "receipt_id", "table_id"])
    if not receipt_col:
        return [], {"error": "receipt_table_id column not found", "columns": cols}

    order_col = _first_existing(cols, ["line_index", "row_index", "position", "sort_order", "created_at", "id"])
    order_sql = f"ORDER BY {_q(order_col)}" if order_col else ""

    rows = conn.execute(
        f"SELECT * FROM receipt_table_lines WHERE {_q(receipt_col)} = ? {order_sql}",
        (receipt_table_id,),
    ).fetchall()
    return [dict(r) for r in rows], {
        "columns": cols,
        "receipt_column": receipt_col,
        "order_column": order_col,
    }


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return None


def _pick_name(line: dict[str, Any]) -> str:
    for key in [
        "article_name", "name", "description", "omschrijving", "raw_text",
        "line_text", "text", "display_name", "product_name", "label",
    ]:
        if key in line and _stringify(line.get(key)):
            return _stringify(line.get(key))
    # Fallback: concatenate non-numeric short textual values.
    parts = []
    for k, v in line.items():
        text = _stringify(v)
        if not text or len(text) > 90:
            continue
        if k.lower().endswith("id") or k.lower() in {"created_at", "updated_at"}:
            continue
        if _float_or_none(text) is None:
            parts.append(text)
    return " | ".join(parts[:3])


def _pick_amount(line: dict[str, Any]) -> tuple[float | None, str | None]:
    preferred = [
        "line_total", "total_price", "total_amount", "amount", "price_total",
        "net_amount", "gross_amount", "price", "unit_price",
    ]
    for key in preferred:
        if key in line:
            value = _float_or_none(line.get(key))
            if value is not None:
                return value, key

    # Last resort: scan all values for amount-looking values, use last.
    found: list[float] = []
    for v in line.values():
        text = _stringify(v)
        for m in AMOUNT_PATTERN.findall(text):
            parsed = _float_or_none(m)
            if parsed is not None:
                found.append(parsed)
    if found:
        return found[-1], "amount_pattern_fallback"
    return None, None


def _classify_line(name: str, amount: float | None, line: dict[str, Any]) -> dict[str, Any]:
    text = " ".join([name] + [_stringify(v) for v in line.values() if isinstance(v, str)])
    classes: list[str] = []
    reasons: list[str] = []

    if LOYALTY_TERMS.search(text):
        classes.append("loyalty_or_stamps")
        reasons.append("loyalty/zegels/punten term")
    if DISCOUNT_TERMS.search(text) or (amount is not None and amount < 0):
        classes.append("discount_or_bonus")
        reasons.append("discount term or negative amount")
    if NON_ARTICLE_TERMS.search(text):
        classes.append("non_article_candidate")
        reasons.append("payment/total/header/footer term")
    if QUANTITY_OR_MULTIBUY.search(text):
        classes.append("quantity_or_multibuy_signal")
        reasons.append("quantity/multibuy pattern")

    if not classes:
        if amount is not None:
            classes.append("article_candidate")
            reasons.append("has amount and no obvious non-article term")
        else:
            classes.append("unpriced_text_candidate")
            reasons.append("no amount detected")

    # Keep discounts and loyalty as relevant business lines, not discarded lines.
    included_in_business_review = any(c in classes for c in [
        "article_candidate",
        "discount_or_bonus",
        "loyalty_or_stamps",
        "quantity_or_multibuy_signal",
    ]) and "non_article_candidate" not in classes

    return {
        "classes": classes,
        "reason": "; ".join(reasons),
        "included_in_business_review": included_in_business_review,
    }


def _load_status_report(path: Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    if not path.exists():
        raise RuntimeError(f"status report not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _baseline_index(status_report: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    if not status_report:
        return index

    for section in ["criterion_mismatches", "technical_parse_status_mismatches"]:
        for item in status_report.get(section, []) or []:
            rid = str(item.get("receipt_table_id") or "")
            if rid and rid not in index:
                index[rid] = item

    # Correct receipts may not be in mismatches. The report currently focuses on mismatches.
    return index


def build_report(
    db_path: Path,
    source_filename: str,
    batch_id: str | None,
    status_report_path: Path | None,
) -> dict[str, Any]:
    conn = _connect(db_path)
    batch = _load_latest_batch(conn, source_filename, batch_id)
    entries = _load_batch_entries(batch)
    ids = [str(e.get("receipt_table_id")) for e in entries if e.get("receipt_table_id")]
    receipts = _fetch_receipts(conn, ids)

    status_report = _load_status_report(status_report_path)
    baseline_by_id = _baseline_index(status_report)

    scoped: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []

    for entry in entries:
        rid = str(entry.get("receipt_table_id") or "")
        receipt = receipts.get(rid, {})
        merged = {**entry, **receipt}
        merged["batch_filename"] = entry.get("filename")
        merged["batch_archive_path"] = entry.get("archive_path")
        scoped.append(merged)
        if _is_ah(merged):
            selected.append(merged)

    ah_reports: list[dict[str, Any]] = []
    pattern_counter: Counter[str] = Counter()
    class_counter: Counter[str] = Counter()
    failed_criteria_counter: Counter[str] = Counter()
    amount_source_counter: Counter[str] = Counter()

    for receipt in selected:
        rid = str(receipt.get("id") or receipt.get("receipt_table_id") or "")
        lines, line_schema = _fetch_lines(conn, rid)
        analysed_lines = []
        current_sum = 0.0
        sum_count = 0

        for idx, line in enumerate(lines, start=1):
            name = _pick_name(line)
            amount, amount_source = _pick_amount(line)
            cls = _classify_line(name, amount, line)
            if amount is not None:
                current_sum += amount
                sum_count += 1
            if amount_source:
                amount_source_counter[amount_source] += 1
            for c in cls["classes"]:
                class_counter[c] += 1
            analysed_lines.append({
                "index": idx,
                "name": name,
                "amount": amount,
                "amount_source": amount_source,
                "classification": cls,
                "raw": line,
            })

        baseline_item = baseline_by_id.get(rid)
        if baseline_item:
            for fc in baseline_item.get("failed_criteria") or []:
                failed_criteria_counter[str(fc)] += 1

        expected_line_count = baseline_item.get("expected_line_count") if baseline_item else None
        expected_total = baseline_item.get("expected_total_amount") if baseline_item else receipt.get("total_amount")
        baseline_line_count = baseline_item.get("line_count") if baseline_item else len(lines)
        baseline_sum = baseline_item.get("sum_line_total_used_for_decision") if baseline_item else None
        baseline_net = baseline_item.get("net_line_sum_used_for_decision") if baseline_item else None
        baseline_discount = baseline_item.get("discount_total_used_for_decision") if baseline_item else None

        non_article_count = sum(1 for l in analysed_lines if "non_article_candidate" in l["classification"]["classes"])
        discount_count = sum(1 for l in analysed_lines if "discount_or_bonus" in l["classification"]["classes"])
        loyalty_count = sum(1 for l in analysed_lines if "loyalty_or_stamps" in l["classification"]["classes"])
        article_candidate_count = sum(1 for l in analysed_lines if "article_candidate" in l["classification"]["classes"])

        if expected_line_count is not None:
            if len(lines) < int(expected_line_count):
                pattern_counter["missing_article_candidates_vs_baseline"] += 1
            elif len(lines) > int(expected_line_count):
                pattern_counter["extra_lines_vs_baseline"] += 1

        if non_article_count:
            pattern_counter["non_article_candidates_present"] += 1
        if discount_count:
            pattern_counter["discount_or_bonus_lines_present"] += 1
        if loyalty_count:
            pattern_counter["loyalty_or_stamps_lines_present"] += 1

        ah_reports.append({
            "receipt_table_id": rid,
            "source_file": receipt.get("batch_filename") or receipt.get("raw_original_filename") or receipt.get("original_filename"),
            "store_name": receipt.get("store_name"),
            "store_chain": receipt.get("store_chain"),
            "total_amount": receipt.get("total_amount"),
            "parse_status": receipt.get("parse_status"),
            "baseline": {
                "expected_line_count": expected_line_count,
                "actual_line_count_in_status_report": baseline_line_count,
                "expected_total_amount": expected_total,
                "sum_line_total_used_for_decision": baseline_sum,
                "discount_total_used_for_decision": baseline_discount,
                "net_line_sum_used_for_decision": baseline_net,
                "failed_criteria": baseline_item.get("failed_criteria") if baseline_item else [],
                "reason": baseline_item.get("reason") if baseline_item else None,
            },
            "line_schema": line_schema,
            "db_line_count": len(lines),
            "diagnostic_line_sum_from_db_lines": round(current_sum, 2) if sum_count else None,
            "classification_counts": dict(Counter(c for line in analysed_lines for c in line["classification"]["classes"])),
            "article_candidate_count": article_candidate_count,
            "discount_or_bonus_count": discount_count,
            "loyalty_or_stamps_count": loyalty_count,
            "non_article_candidate_count": non_article_count,
            "analysed_lines": analysed_lines,
        })

    recommendations = []
    if failed_criteria_counter.get("ARTICLE_COUNT_MISMATCH"):
        recommendations.append({
            "priority": 1,
            "theme": "AH semantic line classification",
            "action": "Maak een AH-profiel dat regels classificeert als article, discount/bonus, loyalty/stamps/points, payment/total/footer/header.",
            "guardrail": "Kortingen, zegels en punten niet wegfilteren maar expliciet als business-relevante regelsoort modelleren.",
        })
    if failed_criteria_counter.get("LINE_SUM_TOTAL_MISMATCH"):
        recommendations.append({
            "priority": 2,
            "theme": "AH amount attribution and reconciliation",
            "action": "Koppel bedragen expliciet aan de juiste artikel-/kortingsregel en voorkom dat totalen/betaalregels meetellen in line_sum.",
            "guardrail": "Status blijft bepaald door receipt_status_baseline_service_v4.py.",
        })
    if pattern_counter.get("loyalty_or_stamps_lines_present"):
        recommendations.append({
            "priority": 3,
            "theme": "AH loyalty/stamps/points handling",
            "action": "Maak zegels/punten als aparte AH-regelklasse zichtbaar in diagnostics; bepaal daarna of ze meetellen in expected article count of als auxiliary business line.",
            "guardrail": "Niet generiek uitfilteren, omdat de PO ze expliciet wil meenemen.",
        })
    recommendations.append({
        "priority": 4,
        "theme": "Regression",
        "action": "Na elke AH-parserwijziging volledige 14-bonnen baseline draaien en controleren dat eerder Gecontroleerd niet onbedoeld degradeert.",
        "guardrail": "Geen wijziging in statusservice of PO-statusnorm.",
    })

    return {
        "audit": "R9-29B AH chain-wide article-line analysis",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "scope": "read-only analysis on latest Kassa import batch and existing receipt_table_lines",
        "ssot_compliance": {
            "status_determination": "not_performed",
            "status_service": "receipt_status_baseline_service_v4.py",
            "parser_mutated": False,
            "ocr_mutated": False,
            "database_mutated": False,
            "ui_mutated": False,
            "baseline_mutated": False,
        },
        "input": {
            "db_path": str(db_path),
            "source_filename": source_filename,
            "batch_id": batch_id,
            "status_report_path": str(status_report_path) if status_report_path else None,
        },
        "batch": {
            "id": batch.get("id"),
            "source_filename": batch.get("source_filename"),
            "total_files": batch.get("total_files"),
            "processed_files": batch.get("processed_files"),
            "imported_files": batch.get("imported_files"),
            "status": batch.get("status"),
            "created_at": batch.get("created_at"),
            "finished_at": batch.get("finished_at"),
        },
        "aggregate": {
            "batch_entry_count": len(entries),
            "ah_receipt_count": len(selected),
            "ah_receipt_ids": [r["receipt_table_id"] for r in ah_reports],
            "failed_criteria_counts_from_status_report": dict(failed_criteria_counter),
            "line_class_counts": dict(class_counter),
            "pattern_counts": dict(pattern_counter),
            "amount_source_counts": dict(amount_source_counter),
        },
        "ah_receipts": ah_reports,
        "recommendations": recommendations,
        "next_step": "Use this report to define AH profile changes in a separate patch; do not change status logic.",
    }


def _fmt_money(value: Any) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):.2f}"
    except Exception:
        return str(value)


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines += [
        "# R9-29B — AH ketenbrede artikelregel-analyse",
        "",
        f"Gemaakt: `{report['created_at']}`",
        "",
        "## SSOT-guardrails",
        "",
    ]
    for k, v in report["ssot_compliance"].items():
        lines.append(f"- `{k}`: `{v}`")

    lines += ["", "## Batch", ""]
    for k, v in report["batch"].items():
        lines.append(f"- `{k}`: `{v}`")

    lines += ["", "## Samenvatting", ""]
    for k, v in report["aggregate"].items():
        lines.append(f"- `{k}`: `{v}`")

    lines += [
        "",
        "## AH-bonnen",
        "",
        "| Bon | receipt_table_id | Totaal | Status | Verwacht regels | DB-regels | Failed criteria |",
        "|---|---|---:|---|---:|---:|---|",
    ]
    for r in report["ah_receipts"]:
        baseline = r["baseline"]
        failed = ", ".join(baseline.get("failed_criteria") or [])
        lines.append(
            f"| `{r.get('source_file')}` | `{r.get('receipt_table_id')}` | `{_fmt_money(r.get('total_amount'))}` | "
            f"`{r.get('parse_status')}` | `{baseline.get('expected_line_count')}` | `{r.get('db_line_count')}` | `{failed}` |"
        )

    lines += ["", "## Detail per AH-bon", ""]
    for r in report["ah_receipts"]:
        lines += [
            f"### {r.get('source_file')}",
            "",
            f"- `receipt_table_id`: `{r.get('receipt_table_id')}`",
            f"- `total_amount`: `{_fmt_money(r.get('total_amount'))}`",
            f"- `parse_status`: `{r.get('parse_status')}`",
            f"- `expected_line_count`: `{r['baseline'].get('expected_line_count')}`",
            f"- `db_line_count`: `{r.get('db_line_count')}`",
            f"- `status_report_reason`: `{r['baseline'].get('reason')}`",
            f"- `classification_counts`: `{r.get('classification_counts')}`",
            "",
            "| # | Bedrag | Classificatie | Naam / tekst | Reden |",
            "|---:|---:|---|---|---|",
        ]
        for line in r["analysed_lines"]:
            cls = ",".join(line["classification"]["classes"])
            name = str(line.get("name") or "").replace("|", "\\|")
            reason = str(line["classification"].get("reason") or "").replace("|", "\\|")
            lines.append(
                f"| {line['index']} | `{_fmt_money(line.get('amount'))}` | `{cls}` | `{name}` | `{reason}` |"
            )
        lines.append("")

    lines += ["## Gezamenlijke AH-foutpatronen", ""]
    patterns = report["aggregate"].get("pattern_counts") or {}
    if patterns:
        for k, v in patterns.items():
            lines.append(f"- `{k}`: `{v}`")
    else:
        lines.append("- Geen patronen gedetecteerd door deze diagnostische classificatie.")

    lines += ["", "## Aanbevolen oplossingsvolgorde", ""]
    for rec in report["recommendations"]:
        lines += [
            f"### {rec['priority']}. {rec['theme']}",
            "",
            f"- Actie: {rec['action']}",
            f"- Guardrail: {rec['guardrail']}",
            "",
        ]

    lines += [
        "## Besluit",
        "",
        "Gebruik dit rapport als input voor een aparte AH-profielpatch. Deze analyse heeft niets gewijzigd.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="/app/data/rezzerv.db")
    parser.add_argument("--source-filename", default="supermarkten.zip")
    parser.add_argument("--batch-id", default=None)
    parser.add_argument("--status-report", default=None, help="Optional JSON from existing status/baseline validation Swagger report")
    parser.add_argument("--out", default="/tmp/R9-29B_ah_chain_analysis")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = build_report(
        db_path=Path(args.db),
        source_filename=args.source_filename,
        batch_id=args.batch_id,
        status_report_path=Path(args.status_report) if args.status_report else None,
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"R9-29B_ah_chain_article_line_analysis_{stamp}.json"
    md_path = out_dir / f"R9-29B_ah_chain_article_line_analysis_{stamp}.md"

    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print("R9-29B AH chain-wide article-line analysis geschreven:")
    print(f"- {json_path}")
    print(f"- {md_path}")
    print("SSOT: no parser/OCR/database/status/baseline/UI mutation")
    print(f"batch_entry_count={report['aggregate']['batch_entry_count']}")
    print(f"ah_receipt_count={report['aggregate']['ah_receipt_count']}")
    print(f"failed_criteria_counts_from_status_report={report['aggregate']['failed_criteria_counts_from_status_report']}")
    print(f"line_class_counts={report['aggregate']['line_class_counts']}")
    print(f"pattern_counts={report['aggregate']['pattern_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

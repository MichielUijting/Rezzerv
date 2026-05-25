#!/usr/bin/env python3
"""
R9-29B — AH chain-wide article-line analysis.

Read-only diagnostic tool for the Rezzerv Kassa receipt ingestion flow.

Scope / guardrails:
- Does not determine receipt status.
- Does not mutate parser, OCR, database, baseline, UI or status service.
- Uses receipt_status_baseline_service_v4.py output only as read-only input when
  a Swagger/status validation JSON is provided.
- Designed to be run inside the backend container against /app/data/rezzerv.db.

Typical usage:
  PYTHONPATH=/app python tools/R9-29B_ah_chain_article_line_analysis.py \
    --db /app/data/rezzerv.db \
    --source-filename supermarkten.zip \
    --status-report /tmp/response_1779696031371.json \
    --out /tmp/R9-29B_ah_chain_analysis
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


PAYMENT_TOTAL_HEADER_TERMS = (
    "pin",
    "betaling",
    "betaald",
    "totaal",
    "subtotaal",
    "btw",
    "wisselgeld",
    "contant",
    "leesmethode",
    "nfc",
    "chip",
    "over",
    "bonnr",
    "kassa",
    "filiaal",
    "transactie",
)

DISCOUNT_BONUS_TERMS = (
    "bonus",
    "korting",
    "actie",
    "aanbieding",
    "2e halve prijs",
    "prijsvoordeel",
)

LOYALTY_STAMP_TERMS = (
    "zegel",
    "zegels",
    "koopzegel",
    "koopzegels",
    "punten",
    "air miles",
    "premium",
    "spaarkaart",
)

AH_ALIASES = {"albert heijn", "ah"}


# ----------------------------- generic helpers -----------------------------


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("€", "").replace(" ", "")
    if not text:
        return None
    # Dutch decimal comma, but keep simple dot decimals intact.
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _first_present(mapping: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        if name in mapping and mapping[name] is not None:
            return mapping[name]
    return None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    try:
        rows = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    except sqlite3.Error:
        return []
    return [str(row[1]) for row in rows]


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


# ----------------------------- status report -----------------------------


def _load_status_report(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    candidate = Path(path)
    if not candidate.exists():
        raise RuntimeError(f"status report not found: {path}")
    with candidate.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise RuntimeError("status report root is not a JSON object")
    return data


def _status_details_index(status_report: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Index status report details by receipt_table_id and normalized source filename.

    The current Swagger JSON has this structure:
      summary.failed_criteria_counts
      details[].receipt_table_id
      details[].expected_line_count
      details[].failed_criteria

    Older/local diagnostics may miss some of these fields. Missing fields are
    treated as absent, not inferred.
    """
    by_id: dict[str, dict[str, Any]] = {}
    by_file: dict[str, dict[str, Any]] = {}
    for item in status_report.get("details") or []:
        if not isinstance(item, dict):
            continue
        receipt_table_id = str(item.get("receipt_table_id") or "").strip()
        if receipt_table_id:
            by_id[receipt_table_id] = item
        for key in ("source_file", "matched_original_filename", "original_filename"):
            filename = _normalize_text(item.get(key))
            if filename and filename not in by_file:
                by_file[filename] = item
    return by_id, by_file


def _status_for_receipt(
    receipt: dict[str, Any],
    status_by_id: dict[str, dict[str, Any]],
    status_by_file: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    receipt_id = str(receipt.get("receipt_table_id") or receipt.get("id") or "").strip()
    if receipt_id and receipt_id in status_by_id:
        return status_by_id[receipt_id]
    source_file = _normalize_text(receipt.get("source_file") or receipt.get("original_filename"))
    return status_by_file.get(source_file, {})


# ----------------------------- database readers -----------------------------


def _detect_receipt_table(conn: sqlite3.Connection) -> str:
    candidates = ["receipt_tables", "receipts"]
    for table in candidates:
        if _table_exists(conn, table):
            return table
    raise RuntimeError("no supported receipt table found; expected receipt_tables or receipts")


def _detect_line_table(conn: sqlite3.Connection) -> str:
    candidates = ["receipt_table_lines", "receipt_lines"]
    for table in candidates:
        if _table_exists(conn, table):
            return table
    raise RuntimeError("no supported receipt line table found; expected receipt_table_lines or receipt_lines")


def _fetch_receipts_from_status_report(status_report: dict[str, Any]) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for item in status_report.get("details") or []:
        if not isinstance(item, dict):
            continue
        receipt_table_id = item.get("receipt_table_id")
        if not receipt_table_id:
            continue
        receipts.append(
            {
                "receipt_table_id": str(receipt_table_id),
                "id": str(receipt_table_id),
                "source_file": item.get("source_file") or item.get("matched_original_filename"),
                "original_filename": item.get("source_file") or item.get("matched_original_filename"),
                "store_name": item.get("store_name"),
                "store_chain": item.get("store_chain"),
                "total_amount": item.get("total_amount"),
                "parse_status": item.get("po_norm_status") or item.get("actual_parse_status") or item.get("technical_parse_status"),
            }
        )
    return receipts


def _fetch_receipts_from_db(conn: sqlite3.Connection, source_filename: str | None) -> list[dict[str, Any]]:
    table = _detect_receipt_table(conn)
    columns = _table_columns(conn, table)
    id_col = "id" if "id" in columns else "receipt_table_id" if "receipt_table_id" in columns else None
    if not id_col:
        raise RuntimeError(f"could not detect receipt id column in {table}")

    select_cols = [id_col]
    for col in ["original_filename", "source_file", "store_name", "store_chain", "total_amount", "parse_status", "deleted_at"]:
        if col in columns:
            select_cols.append(col)

    where = []
    params: dict[str, Any] = {}
    if "deleted_at" in columns:
        where.append("deleted_at IS NULL")
    # Some installations persist source zip on the receipt row. Use it when present, but do not require it.
    if source_filename and "source_filename" in columns:
        where.append("source_filename = :source_filename")
        params["source_filename"] = source_filename

    sql = f"SELECT {', '.join(_quote_ident(c) for c in select_cols)} FROM {_quote_ident(table)}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
    for row in rows:
        row["receipt_table_id"] = str(row.get("receipt_table_id") or row.get("id"))
        row.setdefault("source_file", row.get("original_filename"))
    return rows


def _fetch_receipt_lines(conn: sqlite3.Connection, receipt_table_id: str) -> tuple[list[str], str, str, list[dict[str, Any]]]:
    table = _detect_line_table(conn)
    columns = _table_columns(conn, table)
    receipt_col = "receipt_table_id" if "receipt_table_id" in columns else "receipt_id" if "receipt_id" in columns else None
    if not receipt_col:
        raise RuntimeError(f"could not detect receipt FK column in {table}")
    order_col = "line_index" if "line_index" in columns else "line_number" if "line_number" in columns else "id"
    sql = f"SELECT * FROM {_quote_ident(table)} WHERE {_quote_ident(receipt_col)} = :receipt_id"
    if "is_deleted" in columns:
        sql += " AND COALESCE(is_deleted, 0) = 0"
    sql += f" ORDER BY {_quote_ident(order_col)}"
    rows = [dict(row) for row in conn.execute(sql, {"receipt_id": receipt_table_id}).fetchall()]
    return columns, receipt_col, order_col, rows


# ----------------------------- classification -----------------------------


def _line_name(line: dict[str, Any]) -> str:
    raw_label = _first_present(line, ["raw_label", "raw_text", "parsed_name", "description", "name"])
    normalized_label = _first_present(line, ["normalized_label", "corrected_raw_label"])
    match_status = _first_present(line, ["article_match_status", "status"])
    parts = []
    if raw_label:
        parts.append(str(raw_label))
    if normalized_label and normalized_label != raw_label:
        parts.append(str(normalized_label))
    elif normalized_label:
        parts.append(str(normalized_label))
    if match_status:
        parts.append(str(match_status))
    return " | ".join(parts) if parts else ""


def _line_amount(line: dict[str, Any]) -> tuple[float | None, str | None]:
    for col in ["corrected_line_total", "line_total", "parsed_price", "unit_price", "corrected_unit_price", "discount_amount"]:
        amount = _to_float(line.get(col))
        if amount is not None:
            return amount, col
    return None, None


def _classify_line(line: dict[str, Any]) -> dict[str, Any]:
    text = _normalize_text(_line_name(line))
    amount, _source = _line_amount(line)
    classes: list[str] = []
    reason = ""

    if any(term in text for term in PAYMENT_TOTAL_HEADER_TERMS):
        classes.append("non_article_candidate")
        reason = "payment/total/header/footer term"
    elif any(term in text for term in LOYALTY_STAMP_TERMS):
        classes.append("loyalty_or_stamps")
        reason = "loyalty/stamps term"
    elif any(term in text for term in DISCOUNT_BONUS_TERMS) or (amount is not None and amount < 0):
        classes.append("discount_or_bonus")
        reason = "discount/bonus term or negative amount"
    elif re.search(r"\b\d+[,.]\d+\s*kg\b|\b\d+\s*x\b|\b\d+\s+voor\b", text):
        classes.append("quantity_or_multibuy_signal")
        reason = "quantity/multibuy pattern"
    elif amount is not None:
        classes.append("article_candidate")
        reason = "has amount and no obvious non-article term"
    else:
        classes.append("unclassified")
        reason = "no amount and no recognized semantic marker"

    return {
        "classes": classes,
        "reason": reason,
        "included_in_business_review": "non_article_candidate" not in classes,
    }


# ----------------------------- report builder -----------------------------


def _is_ah_receipt(receipt: dict[str, Any]) -> bool:
    chain = _normalize_text(receipt.get("store_chain"))
    name = _normalize_text(receipt.get("store_name"))
    source = _normalize_text(receipt.get("source_file") or receipt.get("original_filename"))
    return chain in AH_ALIASES or name in AH_ALIASES or "albert heijn" in name or source.startswith("ah ")


def _build_batch_summary(status_report: dict[str, Any], receipts: list[dict[str, Any]], source_filename: str | None) -> dict[str, Any]:
    summary = status_report.get("summary") or {}
    return {
        "id": None,
        "source_filename": source_filename,
        "total_files": summary.get("active_receipts_total") or len(receipts),
        "processed_files": summary.get("active_receipts_total") or len(receipts),
        "imported_files": summary.get("active_receipts_total") or len(receipts),
        "status": "completed" if receipts else None,
        "created_at": None,
        "finished_at": None,
    }


def build_report(db_path: str, source_filename: str | None, status_report_path: str | None) -> dict[str, Any]:
    status_report = _load_status_report(status_report_path)
    status_by_id, status_by_file = _status_details_index(status_report)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        receipts = _fetch_receipts_from_status_report(status_report)
        if not receipts:
            receipts = _fetch_receipts_from_db(conn, source_filename)

        ah_receipts = [r for r in receipts if _is_ah_receipt(r)]
        failed_counts = status_report.get("summary", {}).get("failed_criteria_counts") or {}

        aggregate_class_counts: Counter[str] = Counter()
        aggregate_patterns: Counter[str] = Counter()
        amount_sources: Counter[str] = Counter()
        analysed_receipts: list[dict[str, Any]] = []

        for receipt in ah_receipts:
            receipt_table_id = str(receipt.get("receipt_table_id") or receipt.get("id"))
            status_item = _status_for_receipt(receipt, status_by_id, status_by_file)
            columns, receipt_col, order_col, lines = _fetch_receipt_lines(conn, receipt_table_id)

            analysed_lines: list[dict[str, Any]] = []
            classification_counts: Counter[str] = Counter()
            diagnostic_sum = 0.0
            for idx, line in enumerate(lines, start=1):
                amount, amount_source = _line_amount(line)
                if amount is not None and amount_source in {"line_total", "corrected_line_total", "parsed_price"}:
                    diagnostic_sum += amount
                if amount_source:
                    amount_sources[amount_source] += 1
                classification = _classify_line(line)
                for cls in classification["classes"]:
                    classification_counts[cls] += 1
                    aggregate_class_counts[cls] += 1
                analysed_lines.append(
                    {
                        "index": idx,
                        "name": _line_name(line),
                        "amount": amount,
                        "amount_source": amount_source,
                        "classification": classification,
                        "raw": dict(line),
                    }
                )

            if classification_counts.get("non_article_candidate", 0) > 0:
                aggregate_patterns["non_article_candidates_present"] += 1

            baseline = {
                "expected_line_count": status_item.get("expected_line_count"),
                "actual_line_count_in_status_report": status_item.get("line_count"),
                "expected_total_amount": status_item.get("expected_total_amount"),
                "sum_line_total_used_for_decision": status_item.get("sum_line_total_used_for_decision"),
                "discount_total_used_for_decision": status_item.get("discount_total_used_for_decision"),
                "net_line_sum_used_for_decision": status_item.get("net_line_sum_used_for_decision"),
                "failed_criteria": status_item.get("failed_criteria") or [],
                "reason": status_item.get("reason") or status_item.get("difference_reason"),
            }

            analysed_receipts.append(
                {
                    "receipt_table_id": receipt_table_id,
                    "source_file": receipt.get("source_file") or receipt.get("original_filename"),
                    "store_name": receipt.get("store_name"),
                    "store_chain": receipt.get("store_chain"),
                    "total_amount": _to_float(receipt.get("total_amount")),
                    "parse_status": receipt.get("parse_status"),
                    "baseline": baseline,
                    "line_schema": {
                        "columns": columns,
                        "receipt_column": receipt_col,
                        "order_column": order_col,
                    },
                    "db_line_count": len(lines),
                    "diagnostic_line_sum_from_db_lines": round(diagnostic_sum, 2),
                    "classification_counts": dict(classification_counts),
                    "article_candidate_count": classification_counts.get("article_candidate", 0),
                    "discount_or_bonus_count": classification_counts.get("discount_or_bonus", 0),
                    "loyalty_or_stamps_count": classification_counts.get("loyalty_or_stamps", 0),
                    "non_article_candidate_count": classification_counts.get("non_article_candidate", 0),
                    "analysed_lines": analysed_lines,
                }
            )

        return {
            "audit": "R9-29B AH chain-wide article-line analysis",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "scope": "read-only analysis on current Kassa receipt rows and existing receipt lines",
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
                "db_path": db_path,
                "source_filename": source_filename,
                "batch_id": None,
                "status_report_path": status_report_path,
            },
            "batch": _build_batch_summary(status_report, receipts, source_filename),
            "aggregate": {
                "batch_entry_count": len(receipts),
                "ah_receipt_count": len(ah_receipts),
                "ah_receipt_ids": [r.get("receipt_table_id") for r in ah_receipts],
                "failed_criteria_counts_from_status_report": dict(failed_counts),
                "line_class_counts": dict(aggregate_class_counts),
                "pattern_counts": dict(aggregate_patterns),
                "amount_source_counts": dict(amount_sources),
            },
            "ah_receipts": analysed_receipts,
            "recommendations": [
                {
                    "priority": 1,
                    "theme": "Status report mapping",
                    "action": "Use summary.failed_criteria_counts and details[].receipt_table_id/details[].failed_criteria/details[].expected_line_count from the Swagger status report as read-only diagnostics.",
                    "guardrail": "No status logic changes; status remains governed by receipt_status_baseline_service_v4.py.",
                },
                {
                    "priority": 4,
                    "theme": "Regression",
                    "action": "After every AH parser change, run the complete 14-receipt baseline and verify that previously Gecontroleerd receipts do not degrade.",
                    "guardrail": "No change in status service or PO status norm.",
                },
            ],
            "next_step": "Use this report to define AH profile changes in a separate patch; do not change status logic.",
        }
    finally:
        conn.close()


def _md_table_row(values: list[Any]) -> str:
    return "| " + " | ".join("" if v is None else str(v).replace("|", "\\|") for v in values) + " |"


def render_markdown(report: dict[str, Any]) -> str:
    aggregate = report["aggregate"]
    lines: list[str] = []
    lines.append("# R9-29B — AH ketenbrede artikelregel-analyse")
    lines.append("")
    lines.append(f"Gemaakt: `{report['created_at']}`")
    lines.append("")
    lines.append("## SSOT-guardrails")
    lines.append("")
    for key, value in report["ssot_compliance"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## Batch")
    lines.append("")
    for key, value in report["batch"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## Samenvatting")
    lines.append("")
    for key in [
        "batch_entry_count",
        "ah_receipt_count",
        "ah_receipt_ids",
        "failed_criteria_counts_from_status_report",
        "line_class_counts",
        "pattern_counts",
        "amount_source_counts",
    ]:
        lines.append(f"- `{key}`: `{aggregate.get(key)}`")
    lines.append("")
    lines.append("## AH-bonnen")
    lines.append("")
    lines.append("| Bon | receipt_table_id | Totaal | Status | Verwacht regels | DB-regels | Failed criteria |")
    lines.append("|---|---|---:|---|---:|---:|---|")
    for receipt in report["ah_receipts"]:
        baseline = receipt.get("baseline") or {}
        lines.append(
            _md_table_row(
                [
                    f"`{receipt.get('source_file')}`",
                    f"`{receipt.get('receipt_table_id')}`",
                    f"`{receipt.get('total_amount')}`",
                    f"`{receipt.get('parse_status')}`",
                    f"`{baseline.get('expected_line_count')}`",
                    f"`{receipt.get('db_line_count')}`",
                    "`, `".join(baseline.get("failed_criteria") or []),
                ]
            )
        )
    lines.append("")
    lines.append("## Detail per AH-bon")
    for receipt in report["ah_receipts"]:
        baseline = receipt.get("baseline") or {}
        lines.append("")
        lines.append(f"### {receipt.get('source_file')}")
        lines.append("")
        lines.append(f"- `receipt_table_id`: `{receipt.get('receipt_table_id')}`")
        lines.append(f"- `total_amount`: `{receipt.get('total_amount')}`")
        lines.append(f"- `parse_status`: `{receipt.get('parse_status')}`")
        lines.append(f"- `expected_line_count`: `{baseline.get('expected_line_count')}`")
        lines.append(f"- `actual_line_count_in_status_report`: `{baseline.get('actual_line_count_in_status_report')}`")
        lines.append(f"- `db_line_count`: `{receipt.get('db_line_count')}`")
        lines.append(f"- `failed_criteria`: `{baseline.get('failed_criteria')}`")
        lines.append(f"- `status_report_reason`: `{baseline.get('reason')}`")
        lines.append(f"- `classification_counts`: `{receipt.get('classification_counts')}`")
        lines.append("")
        lines.append("| # | Bedrag | Classificatie | Naam / tekst | Reden |")
        lines.append("|---:|---:|---|---|---|")
        for line in receipt.get("analysed_lines") or []:
            classification = line.get("classification") or {}
            lines.append(
                _md_table_row(
                    [
                        line.get("index"),
                        f"`{line.get('amount')}`",
                        f"`{', '.join(classification.get('classes') or [])}`",
                        f"`{line.get('name')}`",
                        f"`{classification.get('reason')}`",
                    ]
                )
            )
    lines.append("")
    lines.append("## Gezamenlijke AH-foutpatronen")
    lines.append("")
    patterns = aggregate.get("pattern_counts") or {}
    if patterns:
        for key, value in patterns.items():
            lines.append(f"- `{key}`: `{value}`")
    else:
        lines.append("- Geen gezamenlijke patronen gevonden.")
    lines.append("")
    lines.append("## Aanbevolen oplossingsvolgorde")
    lines.append("")
    for recommendation in report.get("recommendations") or []:
        lines.append(f"### {recommendation.get('priority')}. {recommendation.get('theme')}")
        lines.append("")
        lines.append(f"- Actie: {recommendation.get('action')}")
        lines.append(f"- Guardrail: {recommendation.get('guardrail')}")
        lines.append("")
    lines.append("## Besluit")
    lines.append("")
    lines.append("Gebruik dit rapport als input voor een aparte AH-profielpatch. Deze analyse heeft niets gewijzigd.")
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], out_dir: str) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = _now_stamp()
    json_path = out / f"R9-29B_ah_chain_article_line_analysis_{stamp}.json"
    md_path = out / f"R9-29B_ah_chain_article_line_analysis_{stamp}.md"
    json_path.write_text(json.dumps(_json_safe(report), ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="R9-29B AH chain-wide article-line analysis")
    parser.add_argument("--db", required=True, help="Path to SQLite runtime database")
    parser.add_argument("--source-filename", default=None, help="Optional source zip filename, for reporting")
    parser.add_argument("--status-report", default=None, help="Optional Swagger status validation JSON")
    parser.add_argument("--out", required=True, help="Output directory")
    args = parser.parse_args()

    report = build_report(args.db, args.source_filename, args.status_report)
    json_path, md_path = write_outputs(report, args.out)
    aggregate = report["aggregate"]
    print("R9-29B AH chain-wide article-line analysis geschreven:")
    print(f"- {json_path}")
    print(f"- {md_path}")
    print("SSOT: no parser/OCR/database/status/baseline/UI mutation")
    print(f"batch_entry_count={aggregate.get('batch_entry_count')}")
    print(f"ah_receipt_count={aggregate.get('ah_receipt_count')}")
    print(f"failed_criteria_counts_from_status_report={aggregate.get('failed_criteria_counts_from_status_report')}")
    print(f"line_class_counts={aggregate.get('line_class_counts')}")
    print(f"pattern_counts={aggregate.get('pattern_counts')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

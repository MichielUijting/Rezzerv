from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


# R9-28B3-SCAN
# Existing OCR/source retention inventory.
#
# Scope:
# - Inventory only
# - No parser change
# - No OCR change
# - No database mutation
# - No status determination
# - No UI change
# - No modification of receipt_status_baseline_service_v4.py
#
# Purpose:
# Establish whether raw OCR/source retention already exists in the Rezzerv codebase
# and identify the safest reuse path for AH chain-level parsing work.


TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".json", ".yaml", ".yml", ".sql",
    ".ts", ".tsx", ".js", ".jsx",
}

EXCLUDED_DIR_PARTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
}

SIGNAL_PATTERNS: dict[str, list[str]] = {
    "ocr_runtime": [
        r"\b_ocr_image_text_with_paddle\b",
        r"\b_ocr_image_text_with_tesseract\b",
        r"\b_ocr_pdf_text_with_ocrmypdf\b",
        r"\b_get_paddle_ocr\b",
        r"\b_group_paddle_texts_to_lines\b",
        r"\bpytesseract\b",
        r"\bPaddleOCR\b",
        r"\bpaddleocr\b",
        r"\btesseract\b",
        r"\bocr_routes\b",
    ],
    "raw_text_or_lines": [
        r"\braw_text\b",
        r"\bdirect_text\b",
        r"\bocr_lines\b",
        r"\braw_ocr\b",
        r"\bfull_text\b",
        r"\bline_text\b",
        r"\bocr_text\b",
        r"\braw_label\b",
        r"\bnormalized_label\b",
    ],
    "bounding_boxes_or_layout": [
        r"\bbounding\b",
        r"\bbox(?:es)?\b",
        r"\btext_layout\b",
        r"\btopology\b",
        r"\braw_paddle_current\b",
        r"\bocr_box_count\b",
        r"\bline_index\b",
    ],
    "persistence_tables": [
        r"\braw_receipts\b",
        r"\breceipt_tables\b",
        r"\breceipt_table_lines\b",
        r"\breceipt_processing_runs\b",
        r"\bpurchase_import_batches\b",
        r"\bpurchase_import_lines\b",
        r"\breceipt_import_batches\b",
        r"\breceipt_email_messages\b",
    ],
    "diagnostics": [
        r"\bprocessing_diagnostics\b",
        r"\bdiagnostics\b",
        r"\breceipt_parser_diagnosis\b",
        r"\breceipt_line_diagnosis\b",
        r"\bexplainability\b",
        r"\bnormalized_review_diagnostics\b",
        r"\bcross_route_ocr_consensus\b",
        r"\bocr_structural_normalization\b",
        r"\bpre_ocr_image_correction_governance\b",
    ],
    "status_risk": [
        r"\bparse_status\b",
        r"\bpo_norm_status\b",
        r"\bGecontroleerd\b",
        r"\bControle nodig\b",
        r"\breceipt_status_baseline_service_v4\b",
        r"\bapply_po_norm_status\b",
    ],
}

CRITICAL_FILES = [
    "backend/app/services/receipt_service.py",
    "backend/app/receipt_ingestion/ocr_routes.py",
    "backend/receipt_ingestion/pipeline.py",
    "backend/receipt_ingestion/explainability.py",
    "backend/receipt_ingestion/normalized_review_diagnostics.py",
    "backend/receipt_ingestion/diagnostics/summary.py",
    "backend/app/testing_receipt_parser_diagnosis_routes.py",
    "backend/app/testing_receipt_line_diagnosis_routes.py",
    "backend/app/main.py",
    "docs/R9-01-receipt-service-responsibility-inventory.md",
    "docs/architecture/R7c11_image_preprocessing_route_diagnostics.md",
    "docs/architecture/R7c12_conservative_topology_reconstruction.md",
    "docs/architecture/R7c8_paddle_text_layout_diagnostics.md",
]

READ_SNIPPET_LINES = 4


@dataclass
class Match:
    file: str
    line_number: int
    category: str
    pattern: str
    line: str


@dataclass
class FunctionInfo:
    file: str
    name: str
    line_number: int
    category_guess: str


def should_skip(path: Path) -> bool:
    return any(part in EXCLUDED_DIR_PARTS for part in path.parts)


def iter_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if should_skip(path):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        files.append(path)
    return sorted(files)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="latin-1")
        except Exception:
            return ""
    except Exception:
        return ""


def rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def scan_patterns(root: Path, files: list[Path]) -> list[Match]:
    matches: list[Match] = []
    for path in files:
        text = read_text(path)
        if not text:
            continue
        lines = text.splitlines()
        for idx, line in enumerate(lines, start=1):
            if len(line) > 5000:
                continue
            for category, patterns in SIGNAL_PATTERNS.items():
                for pattern in patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        matches.append(Match(rel(root, path), idx, category, pattern, line.strip()[:500]))
                        break
    return matches


def guess_function_category(name: str) -> str:
    n = name.lower()
    if "ocr" in n or "paddle" in n or "tesseract" in n:
        return "ocr_runtime"
    if "diagnos" in n or "explain" in n or "review" in n:
        return "diagnostics"
    if "receipt" in n and ("line" in n or "raw" in n or "parse" in n):
        return "receipt_parser_or_retention"
    if "status" in n:
        return "status_related_do_not_touch"
    return "other"


def scan_python_functions(root: Path, files: list[Path]) -> list[FunctionInfo]:
    out: list[FunctionInfo] = []
    for path in files:
        if path.suffix.lower() != ".py":
            continue
        text = read_text(path)
        if not text:
            continue
        try:
            tree = ast.parse(text)
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name
                category = guess_function_category(name)
                if category != "other":
                    out.append(FunctionInfo(rel(root, path), name, int(getattr(node, "lineno", 0)), category))
    return sorted(out, key=lambda x: (x.file, x.line_number, x.name))


def group_matches(matches: list[Match]) -> dict[str, Any]:
    by_category: dict[str, int] = {}
    by_file: dict[str, dict[str, int]] = {}

    for m in matches:
        by_category[m.category] = by_category.get(m.category, 0) + 1
        by_file.setdefault(m.file, {})
        by_file[m.file][m.category] = by_file[m.file].get(m.category, 0) + 1

    important_files = sorted(
        [
            {
                "file": file,
                "total_matches": sum(counts.values()),
                "categories": counts,
            }
            for file, counts in by_file.items()
        ],
        key=lambda r: (-r["total_matches"], r["file"]),
    )[:80]

    return {"by_category": by_category, "important_files": important_files}


def collect_critical_file_snippets(root: Path, matches: list[Match]) -> dict[str, Any]:
    matches_by_file: dict[str, list[Match]] = {}
    for m in matches:
        matches_by_file.setdefault(m.file, []).append(m)

    snippets: dict[str, Any] = {}
    for file in CRITICAL_FILES:
        path = root / file
        if not path.exists():
            snippets[file] = {"exists": False, "matches": []}
            continue
        file_matches = matches_by_file.get(file, [])
        snippets[file] = {
            "exists": True,
            "match_count": len(file_matches),
            "matches": [asdict(m) for m in file_matches[:120]],
        }
    return snippets


def inspect_db(db_path: str | None) -> dict[str, Any] | None:
    if not db_path:
        return None
    path = Path(db_path)
    if not path.exists():
        return {"db": db_path, "exists": False}

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row

    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
    interesting = [
        "raw_receipts",
        "receipt_tables",
        "receipt_table_lines",
        "receipt_processing_runs",
        "purchase_import_batches",
        "purchase_import_lines",
        "receipt_import_batches",
        "receipt_email_messages",
    ]

    table_info: dict[str, Any] = {}
    for table in interesting:
        if table not in tables:
            table_info[table] = {"exists": False}
            continue
        cols = [dict(row) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        text_cols = [c["name"] for c in cols if any(k in c["name"].lower() for k in ["ocr", "raw", "text", "label", "diagnostic", "payload", "result", "body"])]
        samples: list[dict[str, Any]] = []
        if text_cols and count:
            select_cols = ["id"] if any(c["name"] == "id" for c in cols) else []
            select_cols += [c for c in text_cols if c not in select_cols][:8]
            try:
                rows = conn.execute(f"SELECT {', '.join(select_cols)} FROM {table} LIMIT 5").fetchall()
                for row in rows:
                    d = dict(row)
                    for k, v in list(d.items()):
                        if isinstance(v, str) and len(v) > 600:
                            d[k] = v[:600] + "...<truncated>"
                    samples.append(d)
            except Exception as exc:
                samples = [{"error": type(exc).__name__, "message": str(exc)}]

        table_info[table] = {
            "exists": True,
            "row_count": count,
            "columns": cols,
            "text_like_columns": text_cols,
            "samples": samples,
        }

    return {"db": db_path, "exists": True, "tables": table_info}


def derive_inventory_conclusions(scan: dict[str, Any]) -> dict[str, Any]:
    files = scan["grouped_matches"]["important_files"]
    file_names = {f["file"] for f in files}
    cats = scan["grouped_matches"]["by_category"]

    existing = []
    missing = []
    reuse = []
    risks = []

    if cats.get("ocr_runtime", 0) > 0:
        existing.append("OCR-runtime code is aanwezig: zoekresultaten bevatten Paddle/Tesseract/OCR-routes en OCR-helperfuncties.")
    else:
        missing.append("Geen OCR-runtime signalen gevonden met de huidige scanpatterns.")

    if cats.get("diagnostics", 0) > 0:
        existing.append("Diagnostieklaag is aanwezig: processing_diagnostics, parser diagnosis, explainability en normalized review diagnostics komen voor.")
        reuse.append("Gebruik bestaande diagnosemodules/routes als voorkeursingang voor AH-ketenanalyse.")
    else:
        missing.append("Geen diagnostieklaag gevonden met de huidige scanpatterns.")

    if cats.get("persistence_tables", 0) > 0:
        existing.append("Persistente receipt-tabellen zijn aanwezig: raw_receipts, receipt_tables, receipt_table_lines, receipt_processing_runs en importtabellen komen voor.")
    else:
        missing.append("Geen persistente receipt-tabellen gevonden met de huidige scanpatterns.")

    if cats.get("raw_text_or_lines", 0) > 0:
        existing.append("Er zijn raw/text/line velden en variabelen aanwezig, maar per codepad moet worden vastgesteld of dit pre-parser OCR is of post-parser output.")
    else:
        missing.append("Geen raw text/line signalen gevonden met de huidige scanpatterns.")

    if "backend/app/testing_receipt_parser_diagnosis_routes.py" in file_names:
        reuse.append("Onderzoek testing_receipt_parser_diagnosis_routes.py eerst; dit is waarschijnlijk de bestaande diagnose-ingang voor parser/OCR review.")
    else:
        reuse.append("Zoek expliciet naar testing_receipt_parser_diagnosis_routes.py; als het bestand ontbreekt in deze checkout is de diagnose-ingang mogelijk niet actief.")

    if "backend/app/services/receipt_service.py" in file_names:
        reuse.append("Onderzoek receipt_service.py als huidige orchestrator: OCR, parsing, raw_receipts en receipt_table_lines lijken daar bij elkaar te komen.")
    else:
        reuse.append("Zoek receipt_service.py handmatig; de huidige scan vond het niet als topbestand.")

    if cats.get("status_risk", 0) > 0:
        risks.append("Statusgerelateerde code is aanwezig in scanresultaten. R9-28B3-SCAN mag dit alleen inventariseren; geen wijziging in statusservice of parse_status-gebruik.")

    return {
        "existing_functionality": existing,
        "missing_or_uncertain": missing,
        "reuse_strategy": reuse,
        "risks_and_guardrails": risks,
        "decision": "Niet bouwen aan nieuwe raw OCR-retentie totdat exact is vastgesteld of bestaande OCR/diagnostics-code pre-parser OCR-regels of bounding boxes al beschikbaar maakt.",
        "recommended_next_patch": "R9-28B4 mag pas worden gekozen na review van dit scanrapport.",
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# R9-28B3-SCAN — Existing OCR/source retention inventory")
    lines.append("")
    lines.append(f"Gemaakt: `{report['created_at']}`")
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    for item in report["scope"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## SSOT-compliance")
    lines.append("")
    for k, v in report["ssot_compliance"].items():
        lines.append(f"- `{k}`: `{v}`")
    lines.append("")
    lines.append("## Conclusie")
    lines.append("")
    c = report["conclusions"]
    lines.append(f"**Besluit:** {c['decision']}")
    lines.append("")
    lines.append("### Bestaande functionaliteit")
    for item in c["existing_functionality"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("### Ontbrekend of onzeker")
    for item in c["missing_or_uncertain"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("### Hergebruikstrategie")
    for item in c["reuse_strategy"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("### Risico's en guardrails")
    for item in c["risks_and_guardrails"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Match-samenvatting")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(report["grouped_matches"]["by_category"], indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    lines.append("## Belangrijkste bestanden")
    lines.append("")
    for f in report["grouped_matches"]["important_files"][:30]:
        lines.append(f"- `{f['file']}` — matches: `{f['total_matches']}` — categories: `{f['categories']}`")
    lines.append("")
    lines.append("## OCR-/diagnosefuncties")
    lines.append("")
    for fn in report["functions"][:80]:
        lines.append(f"- `{fn['file']}:{fn['line_number']}` — `{fn['name']}` — `{fn['category_guess']}`")
    lines.append("")
    if report.get("db_inspection"):
        lines.append("## Database-inspectie")
        lines.append("")
        db = report["db_inspection"]
        lines.append(f"- DB: `{db.get('db')}`")
        lines.append(f"- Exists: `{db.get('exists')}`")
        if db.get("tables"):
            for table, info in db["tables"].items():
                lines.append(f"- `{table}`: exists=`{info.get('exists')}`, rows=`{info.get('row_count')}`, text_like_columns=`{info.get('text_like_columns')}`")
    lines.append("")
    lines.append("## Volgende stap")
    lines.append("")
    lines.append(report["conclusions"]["recommended_next_patch"])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Repository root. Default: current directory.")
    parser.add_argument("--out", default="tools/debug_output/R9-28B3_SCAN", help="Output directory.")
    parser.add_argument("--db", default=None, help="Optional SQLite database path for runtime-schema inspection.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    files = iter_source_files(root)
    matches = scan_patterns(root, files)
    functions = scan_python_functions(root, files)

    report = {
        "audit": "R9-28B3-SCAN Existing OCR/source retention inventory",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(root),
        "scope": [
            "inventory only",
            "no parser change",
            "no OCR change",
            "no database mutation",
            "no status determination",
            "no UI change",
            "no receipt_status_baseline_service_v4.py modification",
        ],
        "ssot_compliance": {
            "status_determination": "not_performed",
            "status_service": "receipt_status_baseline_service_v4.py",
            "parse_status_used_as_truth": False,
            "parser_mutated": False,
            "database_mutated": False,
            "baseline_mutated": False,
            "ui_touched": False,
        },
        "scan_parameters": {
            "file_count": len(files),
            "text_suffixes": sorted(TEXT_SUFFIXES),
            "excluded_dir_parts": sorted(EXCLUDED_DIR_PARTS),
            "signal_categories": sorted(SIGNAL_PATTERNS),
        },
        "grouped_matches": group_matches(matches),
        "critical_file_snippets": collect_critical_file_snippets(root, matches),
        "functions": [asdict(f) for f in functions],
        "db_inspection": inspect_db(args.db),
    }

    report["conclusions"] = derive_inventory_conclusions(report)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"R9-28B3_SCAN_existing_ocr_source_retention_inventory_{stamp}.json"
    md_path = out_dir / f"R9-28B3_SCAN_existing_ocr_source_retention_inventory_{stamp}.md"

    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"R9-28B3-SCAN rapport geschreven:")
    print(f"- {json_path}")
    print(f"- {md_path}")
    print("")
    print("SSOT: status_determination=not_performed parse_status_used_as_truth=False parser_mutated=False database_mutated=False baseline_mutated=False")
    print(f"file_count={len(files)}")
    print(f"match_categories={report['grouped_matches']['by_category']}")
    print("")
    print("Besluit:")
    print(report["conclusions"]["decision"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

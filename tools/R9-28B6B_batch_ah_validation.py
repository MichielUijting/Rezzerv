from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any


# R9-28B6B
# Batch validation for all AH receipts using generic AH Paddle-box reconstruction.
#
# Scope:
# - Batch diagnostics only
# - No receipt-specific rule introduction
# - No parser mutation
# - No OCR engine mutation
# - No database mutation
# - No status determination
# - No UI mutation
# - No receipt_status_baseline_service_v4.py mutation
#
# Purpose:
# Run the same R9-28B5 + R9-28B6 diagnostic pipeline for all AH receipts
# in a zip and report chain-level failure patterns.
#
# Guardrail:
# The classifier must not contain member-specific or filename-specific rules.


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
DEFAULT_AH_MEMBER_RE = r"(?i)(^|[/\\])(AH|Albert|Albert\s*Heijn)[^/\\]*\.(jpg|jpeg|png|bmp|tif|tiff|webp)$"


def _load_module(path: Path, name: str):
    if not path.exists():
        raise FileNotFoundError(f"Benodigd toolbestand ontbreekt: {path}")
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Kan module niet laden: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _members(zip_path: Path, member_regex: str) -> list[str]:
    pattern = re.compile(member_regex)
    with zipfile.ZipFile(zip_path, "r") as z:
        names = [
            n for n in z.namelist()
            if not n.endswith("/")
            and Path(n).suffix.lower() in IMAGE_SUFFIXES
            and pattern.search(n)
        ]
    return sorted(names)


def _safe_stem(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(name).stem)


def _summarize_reconstruction(member: str, b5_report: dict[str, Any], b6_report: dict[str, Any]) -> dict[str, Any]:
    articles = b6_report.get("reconstructed_articles", []) or []
    blocked = b6_report.get("blocked_non_article_items", []) or []
    amounts = [a.get("amount") for a in articles if isinstance(a.get("amount"), (int, float))]
    article_sum = round(sum(float(v) for v in amounts), 2)

    suspicious = []
    for a in articles:
        name = str(a.get("article_name") or "")
        amount = a.get("amount")
        amount_text = str(a.get("amount_text") or "")
        if not name.strip():
            suspicious.append({"type": "empty_article_name", "article": a})
        if amount is None:
            suspicious.append({"type": "missing_amount", "article": a})
        if re.search(r"\b(totaal|subtotaal|betalen|pin|nfc|chip|btw|over|terminal|transactie)\b", name, re.IGNORECASE):
            suspicious.append({"type": "non_article_term_in_article_name", "article": a})
        if amount_text in {"0,00", "0.00"}:
            suspicious.append({"type": "zero_amount_article_candidate", "article": a})

    return {
        "member": member,
        "ocr_summary": {
            "paddle_available": b5_report.get("paddle", {}).get("available"),
            "paddle_raw_text_count": b5_report.get("paddle", {}).get("raw_text_count"),
            "paddle_bbox_count": b5_report.get("paddle", {}).get("bbox_count"),
            "paddle_grouped_line_count": b5_report.get("paddle", {}).get("grouped_line_count"),
            "tesseract_line_count": b5_report.get("tesseract", {}).get("line_count"),
            "diagnostic_parser_input_choice": b5_report.get("parser_input_candidate_for_diagnostics_only", {}).get("diagnostic_choice"),
        },
        "reconstruction_summary": b6_report.get("summary", {}),
        "reconstructed_article_count": len(articles),
        "reconstructed_article_sum": article_sum,
        "reconstructed_articles": articles,
        "blocked_non_article_count": len(blocked),
        "suspicious_findings": suspicious,
        "suspicious_finding_count": len(suspicious),
        "pass_batch_diagnostic": len(articles) > 0 and len(suspicious) == 0,
    }


def _aggregate(member_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    failure_types: dict[str, int] = {}
    for item in member_summaries:
        for finding in item.get("suspicious_findings", []) or []:
            kind = finding.get("type", "unknown")
            failure_types[kind] = failure_types.get(kind, 0) + 1

    return {
        "ah_member_count": len(member_summaries),
        "passed_count": sum(1 for item in member_summaries if item.get("pass_batch_diagnostic")),
        "failed_or_suspicious_count": sum(1 for item in member_summaries if not item.get("pass_batch_diagnostic")),
        "failure_types": failure_types,
        "total_reconstructed_articles": sum(int(item.get("reconstructed_article_count") or 0) for item in member_summaries),
        "total_blocked_non_article_items": sum(int(item.get("blocked_non_article_count") or 0) for item in member_summaries),
    }


def build_batch_report(zip_path: Path, member_regex: str, out_dir: Path, preprocess: bool) -> dict[str, Any]:
    root = Path.cwd()
    b5_tool = root / "tools/R9-28B5_export_pre_parser_ocr_diagnostics.py"
    b6_tool = root / "tools/R9-28B6_ah_paddle_box_reconstruction.py"

    b5 = _load_module(b5_tool, "r9_28b5_export_pre_parser_ocr_diagnostics")
    b6 = _load_module(b6_tool, "r9_28b6_ah_paddle_box_reconstruction")

    members = _members(zip_path, member_regex)
    if not members:
        raise RuntimeError(f"Geen AH-members gevonden in {zip_path} met regex: {member_regex}")

    per_member_dir = out_dir / "per_member"
    per_member_dir.mkdir(parents=True, exist_ok=True)

    member_summaries: list[dict[str, Any]] = []

    for member in members:
        safe = _safe_stem(member)
        member_dir = per_member_dir / safe
        member_dir.mkdir(parents=True, exist_ok=True)

        # R9-28B5: build in-memory report for this member.
        b5_report = b5.build_report(zip_path, member, preprocess)

        b5_json = member_dir / f"R9-28B5_{safe}.json"
        b5_md = member_dir / f"R9-28B5_{safe}.md"
        b5_json.write_text(json.dumps(b5_report, indent=2, ensure_ascii=False), encoding="utf-8")
        b5_md.write_text(b5.render_markdown(b5_report), encoding="utf-8")

        # R9-28B6: run current generic reconstruction against this R9-28B5 report.
        b6_report = b6.build_report(b5_json)
        b6_json = member_dir / f"R9-28B6_{safe}.json"
        b6_md = member_dir / f"R9-28B6_{safe}.md"
        b6_json.write_text(json.dumps(b6_report, indent=2, ensure_ascii=False), encoding="utf-8")
        b6_md.write_text(b6.render_md(b6_report), encoding="utf-8")

        member_summaries.append(_summarize_reconstruction(member, b5_report, b6_report))

    aggregate = _aggregate(member_summaries)

    return {
        "audit": "R9-28B6B batch validation for all AH receipts",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "scope": "batch diagnostics only; no receipt-specific rules; no parser/OCR/database/status/baseline/UI mutation",
        "ssot_compliance": {
            "status_determination": "not_performed",
            "status_service": "receipt_status_baseline_service_v4.py",
            "parse_status_used_as_truth": False,
            "parser_mutated": False,
            "ocr_mutated": False,
            "database_mutated": False,
            "baseline_mutated": False,
            "ui_touched": False,
            "diagnostics_promoted_to_parser": False,
        },
        "receipt_specific_rule_guardrail": {
            "filename_specific_rules_allowed": False,
            "member_specific_rules_allowed": False,
            "hardcoded_receipt_ids_allowed": False,
            "member_regex_used_only_for_batch_selection": member_regex,
            "note": "The same R9-28B5/R9-28B6 generic pipeline is executed for every selected AH member.",
        },
        "input": {
            "zip_path": str(zip_path),
            "member_regex": member_regex,
            "preprocess": preprocess,
        },
        "aggregate": aggregate,
        "members": member_summaries,
        "next_step_hint": "Use batch-level recurring failure patterns only. Do not patch per receipt. If correction is needed, implement one generic AH rule and rerun this batch.",
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = [
        "# R9-28B6B — Batchvalidatie alle AH-bonnen",
        "",
        f"Gemaakt: `{report['created_at']}`",
        "",
        "## SSOT-compliance",
        "",
    ]
    for k, v in report["ssot_compliance"].items():
        lines.append(f"- `{k}`: `{v}`")

    lines += [
        "",
        "## Guardrail tegen bon-specifieke regels",
        "",
    ]
    for k, v in report["receipt_specific_rule_guardrail"].items():
        lines.append(f"- `{k}`: `{v}`")

    lines += [
        "",
        "## Batchsamenvatting",
        "",
    ]
    for k, v in report["aggregate"].items():
        lines.append(f"- `{k}`: `{v}`")

    lines += [
        "",
        "## Per AH-bon",
        "",
        "| Member | Pass | Artikelen | Som | Suspicious | OCR items | Boxes |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for m in report["members"]:
        ocr = m["ocr_summary"]
        lines.append(
            f"| `{m['member']}` | `{m['pass_batch_diagnostic']}` | "
            f"`{m['reconstructed_article_count']}` | `{m['reconstructed_article_sum']}` | "
            f"`{m['suspicious_finding_count']}` | `{ocr.get('paddle_raw_text_count')}` | `{ocr.get('paddle_bbox_count')}` |"
        )

    lines += [
        "",
        "## Gereconstrueerde artikelen per bon",
        "",
    ]
    for m in report["members"]:
        lines.append(f"### `{m['member']}`")
        if not m["reconstructed_articles"]:
            lines.append("- Geen artikelen gereconstrueerd.")
        for a in m["reconstructed_articles"]:
            lines.append(f"- `{a.get('article_name')}` — `{a.get('amount_text')}`")
        if m["suspicious_findings"]:
            lines.append("")
            lines.append("Suspicious findings:")
            for f in m["suspicious_findings"]:
                lines.append(f"- `{f.get('type')}`")
        lines.append("")

    lines += [
        "## Vervolg",
        "",
        report["next_step_hint"],
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_path", help="Zip met kassabonafbeeldingen")
    parser.add_argument("--out", default="/tmp/R9-28B6B_batch_ah_validation")
    parser.add_argument("--member-regex", default=DEFAULT_AH_MEMBER_RE)
    parser.add_argument("--preprocess", action="store_true")
    args = parser.parse_args()

    zip_path = Path(args.zip_path)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = build_batch_report(zip_path, args.member_regex, out_dir, args.preprocess)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"R9-28B6B_batch_ah_validation_{stamp}.json"
    md_path = out_dir / f"R9-28B6B_batch_ah_validation_{stamp}.md"

    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print("R9-28B6B batchvalidatie alle AH-bonnen geschreven:")
    print(f"- {json_path}")
    print(f"- {md_path}")
    print("SSOT: no parser/OCR/database/status/baseline/UI mutation")
    print("Guardrail: no receipt-specific or filename-specific rules introduced")
    print(f"ah_member_count={report['aggregate']['ah_member_count']}")
    print(f"passed_count={report['aggregate']['passed_count']}")
    print(f"failed_or_suspicious_count={report['aggregate']['failed_or_suspicious_count']}")
    print(f"failure_types={report['aggregate']['failure_types']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

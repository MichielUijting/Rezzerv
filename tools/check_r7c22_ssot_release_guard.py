from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KASSA_PAGE = ROOT / "frontend" / "src" / "features" / "receipts" / "KassaPage.jsx"
STATUS_BADGE = ROOT / "frontend" / "src" / "features" / "kassa" / "components" / "ReceiptStatusBadge.jsx"

TECHNICAL_PARSE_STATUS_ALLOWED_PATHS = {
    Path("backend/app/services/receipt_status_sync.py"),
    Path("backend/app/services/receipt_status_baseline_service_v4.py"),
    Path("backend/app/services/receipt_status_baseline_service/__init__.py"),
    Path("backend/app/api/receipt_admin_routes.py"),
    Path("backend/app/api/receipt_diagnosis_routes.py"),
}

SCAN_SUFFIXES = {".py", ".jsx", ".js", ".mjs"}
SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "build",
    "reports",
    "playwright-report",
    "test-results",
    "__pycache__",
}


def fail(message: str) -> None:
    print(f"R7c-24 FAILED: {message}")
    sys.exit(1)


def read(path: Path) -> str:
    if not path.exists():
        fail(f"missing file: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def relative(path: Path) -> Path:
    return path.relative_to(ROOT)


def should_scan(path: Path) -> bool:
    rel = relative(path)
    if path.suffix not in SCAN_SUFFIXES:
        return False
    if any(part in SKIP_DIRS for part in rel.parts):
        return False
    return True


def assert_frontend_ssot() -> None:
    page = read(KASSA_PAGE)
    badge = read(STATUS_BADGE)
    forbidden_page_tokens = [
        "parse" + "_status",
        "parse" + "Status",
        "parse" + "StatusLabel",
        "normalize" + "InboxStatus",
    ]
    for token in forbidden_page_tokens:
        if token in page:
            fail(f"active Kassa UI still contains forbidden status token: {token}")
    if "po_norm_status_label" not in page:
        fail("KassaPage.jsx does not use po_norm_status_label")
    forbidden_badge_tokens = ["manual", "Handmatig"]
    for token in forbidden_badge_tokens:
        if token in badge:
            fail(f"ReceiptStatusBadge.jsx still contains frontend status fallback token: {token}")


def assert_parse_status_is_technical_only() -> None:
    violations: list[str] = []
    token = "parse" + "_status"
    for path in ROOT.rglob("*"):
        if not path.is_file() or not should_scan(path):
            continue
        rel = relative(path)
        if token not in path.read_text(encoding="utf-8", errors="ignore"):
            continue
        if rel in TECHNICAL_PARSE_STATUS_ALLOWED_PATHS:
            continue
        violations.append(str(rel).replace("\\", "/"))
    if violations:
        fail("parse_status found outside technical diagnostics: " + ", ".join(sorted(violations)))


def assert_baseline_summary(report_path: Path | None) -> None:
    if report_path is None:
        print("R7c-24 INFO: no baseline report supplied; static SSOT guards only")
        return
    if not report_path.exists():
        fail(f"baseline report not found: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    summary = report.get("summary") or report.get("validation_summary") or {}
    backend_counts = summary.get("backend_status_counts")
    po_counts = summary.get("po_norm_status_counts")
    verschil = summary.get("verschil")
    if backend_counts != po_counts:
        fail(f"backend_status_counts != po_norm_status_counts: {backend_counts} != {po_counts}")
    if int(verschil or 0) != 0:
        fail(f"baseline verschil must be 0, got {verschil}")


def main() -> None:
    report_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if report_path is not None and not report_path.is_absolute():
        report_path = ROOT / report_path
    assert_frontend_ssot()
    assert_parse_status_is_technical_only()
    assert_baseline_summary(report_path)
    print("R7c-24 PASSED: parse_status is isolated to technical diagnostics")


if __name__ == "__main__":
    main()

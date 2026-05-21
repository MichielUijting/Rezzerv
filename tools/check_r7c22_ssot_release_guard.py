from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KASSA_PAGE = ROOT / "frontend" / "src" / "features" / "receipts" / "KassaPage.jsx"
STATUS_BADGE = ROOT / "frontend" / "src" / "features" / "kassa" / "components" / "ReceiptStatusBadge.jsx"
SSOT_PAYLOAD = ROOT / "backend" / "app" / "services" / "receipt_ssot_status.py"


def fail(message: str) -> None:
    print(f"R7c-24 FAILED: {message}")
    sys.exit(1)


def read(path: Path) -> str:
    if not path.exists():
        fail(f"missing file: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


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


def assert_kassa_payload_strips_technical_status() -> None:
    source = read(SSOT_PAYLOAD)
    required_contract_tokens = [
        "payload.pop(\"parse" + "_status\", None)",
        "payload.pop(\"actual_parse" + "_status\", None)",
        "payload.pop(\"actual_status_label\", None)",
        "payload[\"po_norm_status_label\"]",
        "payload[\"inbox_status\"]",
    ]
    for token in required_contract_tokens:
        if token not in source:
            fail(f"Kassa SSOT payload contract is missing: {token}")


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
    assert_kassa_payload_strips_technical_status()
    assert_baseline_summary(report_path)
    print("R7c-24 PASSED: active Kassa status is SSOT-only and technical status is stripped from payloads")


if __name__ == "__main__":
    main()

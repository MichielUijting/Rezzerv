from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = ROOT / "frontend" / "src"
KASSA_PAGE = FRONTEND_ROOT / "features" / "receipts" / "KassaPage.jsx"
SSOT_STATUS_SERVICE = ROOT / "backend" / "app" / "services" / "receipt_ssot_status.py"
BASELINE_SERVICE = ROOT / "backend" / "app" / "services" / "receipt_status_baseline_service_v4.py"
MAIN_PY = ROOT / "backend" / "app" / "main.py"

ALLOWED_FUNCTIONAL_LABELS = {"Controle nodig", "Gecontroleerd"}
FORBIDDEN_FRONTEND_STATUS_TOKENS = {
    "parse_status",
    "raw_status",
    "review_needed",
    "approved",
}

# Legacy manual/Handmatig is prohibited as a status category in Kassa.
# The word Manual may still appear in source labels such as "Manual upload".
FORBIDDEN_KASSA_STATUS_LABELS = {"Handmatig"}

FRONTEND_EXEMPT_PATH_PARTS = {
    "RegressionRunnerPage",
    "ReceiptReviewPreviewPage",
    "storeImportShared",
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def fail(message: str) -> None:
    print(f"R9-06 FAIL: {message}")
    raise SystemExit(1)


def ok(message: str) -> None:
    print(f"R9-06 OK: {message}")


def frontend_files() -> list[Path]:
    if not FRONTEND_ROOT.exists():
        fail(f"frontend root ontbreekt: {FRONTEND_ROOT}")
    return sorted(
        path for path in FRONTEND_ROOT.rglob("*")
        if path.suffix in {".js", ".jsx", ".ts", ".tsx"}
    )


def is_exempt_frontend_file(path: Path) -> bool:
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    return any(part in rel for part in FRONTEND_EXEMPT_PATH_PARTS)


def grep_forbidden_frontend_status_usage() -> list[str]:
    violations: list[str] = []
    token_pattern = re.compile(r"\b(" + "|".join(re.escape(token) for token in sorted(FORBIDDEN_FRONTEND_STATUS_TOKENS)) + r")\b")
    for path in frontend_files():
        if is_exempt_frontend_file(path):
            continue
        text = read_text(path)
        for line_no, line in enumerate(text.splitlines(), start=1):
            if token_pattern.search(line):
                stripped = line.strip().lower()
                if stripped.startswith("//") and ("niet" in stripped or "forbidden" in stripped or "verboden" in stripped):
                    continue
                rel = path.relative_to(ROOT)
                violations.append(f"{rel}:{line_no}: {line.strip()}")
    return violations


def assert_kassa_uses_po_norm_label_only() -> None:
    if not KASSA_PAGE.exists():
        fail(f"KassaPage ontbreekt: {KASSA_PAGE}")
    content = read_text(KASSA_PAGE)
    required = [
        "function requirePoNormStatusLabel(item)",
        "po_norm_status_label",
        "inbox_status: requirePoNormStatusLabel(item)",
        "filters.status ? item.inbox_status === filters.status : true",
        "Controle nodig",
        "Gecontroleerd",
    ]
    for marker in required:
        if marker not in content:
            fail(f"KassaPage mist verplicht statuscontract-marker: {marker}")
    forbidden = ["parse_status", "raw_status", "review_needed", "approved", ]
    for marker in forbidden:
        if re.search(rf"\b{re.escape(marker)}\b", content):
            fail(f"KassaPage bevat verboden technische statustoken: {marker}")
    for label in FORBIDDEN_KASSA_STATUS_LABELS:
        if re.search(rf"inbox_status\s*[:=]\s*['\"]{re.escape(label)}['\"]", content):
            fail(f"KassaPage gebruikt verboden functioneel statuslabel: {label}")
    ok("KassaPage rendert/filtert uitsluitend via po_norm_status_label/inbox_status")


def assert_ssot_mapping_contract() -> None:
    if not SSOT_STATUS_SERVICE.exists():
        fail(f"SSOT statusservice ontbreekt: {SSOT_STATUS_SERVICE}")
    content = read_text(SSOT_STATUS_SERVICE)
    required = [
        "def apply_po_norm_status",
        "validate_receipt_status_baseline",
        "payload.pop(\"parse_status\", None)",
        "payload[\"po_norm_status_label\"] = label",
        "payload[\"inbox_status\"] = label",
        "payload[\"status\"] = label",
        "INVALID STATUS SOURCE",
    ]
    for marker in required:
        if marker not in content:
            fail(f"receipt_ssot_status.py mist verplicht marker: {marker}")
    if "Handmatig" not in content or "manual" not in content:
        fail("receipt_ssot_status.py moet legacy manual/Handmatig normaliseren naar Controle nodig")
    ok("SSOT mapping verwijdert technische statussen uit Kassa-payload")


def assert_baseline_service_contract() -> None:
    if not BASELINE_SERVICE.exists():
        fail(f"baseline service ontbreekt: {BASELINE_SERVICE}")
    content = read_text(BASELINE_SERVICE)
    required = [
        "po_norm_status_label",
        "backend_status_counts",
        "po_norm_status_counts",
        "verschil",
        "technical_parse_status_counts",
        "status_matches_po_norm",
    ]
    for marker in required:
        if marker not in content:
            fail(f"receipt_status_baseline_service_v4.py mist governance-marker: {marker}")
    ok("baseline service levert statuscounts en technische statusdiagnostiek")


def assert_api_applies_ssot() -> None:
    if not MAIN_PY.exists():
        fail(f"main.py ontbreekt: {MAIN_PY}")
    content = read_text(MAIN_PY)
    required = [
        "from app.services.receipt_ssot_status import apply_po_norm_status",
        "serialized = apply_po_norm_status(serialize_receipt_row(dict(row)))",
        "payload = apply_po_norm_status(serialize_receipt_row(dict(header)))",
    ]
    for marker in required:
        if marker not in content:
            fail(f"main.py mist API-SSOT-marker: {marker}")
    ok("/api/receipts en /api/receipts/{id} passen apply_po_norm_status toe")


def assert_no_forbidden_frontend_status_usage() -> None:
    violations = grep_forbidden_frontend_status_usage()
    if violations:
        print("R9-06 verboden frontendstatusgebruik gevonden:")
        for violation in violations[:50]:
            print(f" - {violation}")
        if len(violations) > 50:
            print(f" - ... plus {len(violations) - 50} extra overtredingen")
        fail("frontend bevat nog directe technische statusafhankelijkheid")
    ok("frontend bevat geen directe technische statusafhankelijkheid buiten expliciet vrijgestelde diagnostics")


def runtime_api_contract_snapshot(url: str | None = None, token: str | None = None) -> dict[str, Any] | None:
    if not url:
        return None
    try:
        from urllib.request import Request, urlopen
        request = Request(url)
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        with urlopen(request, timeout=8) as response:  # nosec - local dev check only
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # pragma: no cover - runtime convenience
        fail(f"runtime API-contractcheck mislukt: {exc}")
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        fail("runtime API-contractcheck: response bevat geen items[]")
    missing = [item.get("receipt_table_id") for item in items if not item.get("po_norm_status_label")]
    if missing:
        fail(f"runtime API-contractcheck: po_norm_status_label ontbreekt voor {missing}")
    labels = {str(item.get("po_norm_status_label")) for item in items}
    invalid = labels - ALLOWED_FUNCTIONAL_LABELS
    if invalid:
        fail(f"runtime API-contractcheck: verboden functionele labels: {sorted(invalid)}")
    leaked_parse_status = [item.get("receipt_table_id") for item in items if "parse_status" in item]
    if leaked_parse_status:
        fail(f"runtime API-contractcheck: parse_status lekt in UI-payload voor {leaked_parse_status}")
    counts = {label: sum(1 for item in items if item.get("po_norm_status_label") == label) for label in sorted(ALLOWED_FUNCTIONAL_LABELS)}
    if sum(counts.values()) != len(items):
        fail("runtime API-contractcheck: statuscounts tellen niet op tot aantal items")
    ok(f"runtime API-contractcheck geslaagd: items={len(items)} counts={counts}")
    return {"items": len(items), "counts": counts}


def main() -> int:
    assert_kassa_uses_po_norm_label_only()
    assert_ssot_mapping_contract()
    assert_baseline_service_contract()
    assert_api_applies_ssot()
    assert_no_forbidden_frontend_status_usage()

    url = sys.argv[1] if len(sys.argv) >= 2 else None
    token = sys.argv[2] if len(sys.argv) >= 3 else None
    runtime_api_contract_snapshot(url, token)

    ok("R9-06 receipt status governance contract is geborgd")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



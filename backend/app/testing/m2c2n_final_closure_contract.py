from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = ROOT / "docs/quality/M2C2N-CLOSURE-MATRIX.md"
BASELINE_PATH = ROOT / "docs/quality/M2C2N-ROUTE-CATALOG-BASELINE.json"
REPORT_PATH = ROOT / "docs/quality/M2C2N-FINAL-REPORT.md"

REQUIRED_GEREED = {f"M2C2N-{number:02d}" for number in range(1, 23)} | {"M2C2N-24"}
REQUIRED_DEFERRED = {"M2C2N-23"}
REQUIRED_FILES = {
    ".github/workflows/m2c2n-route-catalog.yml",
    ".github/workflows/m2c2n-product-route-audit.yml",
    ".github/workflows/m2c2n-product-route-guard.yml",
    ".github/workflows/m2c2n-forecast-purchase-route-audit.yml",
    ".github/workflows/m2c2n-notification-route-audit.yml",
    ".github/workflows/m2c2n-household-fallback-audit.yml",
    "backend/app/testing/route_catalog.py",
    "backend/app/testing/receipt_admin_household_guard_contract.py",
    "backend/app/testing/product_route_household_guard_contract.py",
    "backend/app/testing/forecast_purchase_route_contract.py",
    "backend/app/testing/notification_route_contract.py",
    "backend/app/testing/household_fallback_contract.py",
}


def parse_matrix(text: str) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r"^\|\s*(M2C2N-\d{2})\s*\|.*?\|\s*(GEREED|CONTROLE|OPEN|DEFERRED)\s*\|", line)
        if match:
            statuses[match.group(1)] = match.group(2)
    return statuses


def main() -> None:
    matrix = MATRIX_PATH.read_text(encoding="utf-8")
    statuses = parse_matrix(matrix)

    assert set(statuses) == REQUIRED_GEREED | REQUIRED_DEFERRED, statuses
    assert {key for key, value in statuses.items() if value == "GEREED"} == REQUIRED_GEREED
    assert {key for key, value in statuses.items() if value == "DEFERRED"} == REQUIRED_DEFERRED
    assert not {key for key, value in statuses.items() if value in {"OPEN", "CONTROLE"}}

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    summary = baseline["summary"]
    assert summary["route_registrations"] == 194
    assert summary["unique_method_paths"] == 194
    assert summary["duplicates"] == 0
    assert summary["by_access"] == {"mutation": 109, "read": 85}
    assert summary["mutation_by_surface"] == {
        "admin": 10,
        "dev": 1,
        "production": 81,
        "testing": 17,
    }

    missing = sorted(path for path in REQUIRED_FILES if not (ROOT / path).is_file())
    assert not missing, missing

    report = REPORT_PATH.read_text(encoding="utf-8")
    assert "M2C2n eindadvies: GO" in report
    assert "M2C2N-23" in report and "DEFERRED" in report
    assert "194" in report and "nul dubbele" in report.lower()
    assert "PR #160" in report and "PR #185" in report
    assert "geen functionele schermacceptatie" in report.lower()

    print("M2C2N_FINAL_CLOSURE_GREEN")


if __name__ == "__main__":
    main()

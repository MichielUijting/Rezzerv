from __future__ import annotations

import json
import sys
from urllib.request import Request, urlopen


def fail(message: str) -> None:
    print(f"R9-08 FAIL: {message}")
    raise SystemExit(1)


def ok(message: str) -> None:
    print(f"R9-08 OK: {message}")


def fetch_json(url: str, token: str) -> dict:
    request = Request(url)
    request.add_header("Authorization", f"Bearer {token}")
    with urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    base_url = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8011"
    token = sys.argv[2] if len(sys.argv) > 2 else "rezzerv-dev-token::admin@rezzerv.local"
    receipts = fetch_json(f"{base_url}/api/receipts?householdId=1", token)
    items = receipts.get("items") or []
    if not items:
        fail("Geen bonnen beschikbaar voor endpointcheck")
    receipt_id = items[0].get("receipt_table_id")
    if not receipt_id:
        fail("Eerste bon mist receipt_table_id")

    payload = fetch_json(f"{base_url}/api/receipts/{receipt_id}/explainability", token)
    explainability = payload.get("explainability") or {}
    required = [
        "source_route",
        "ocr_route",
        "preprocessing",
        "header_decisions",
        "total_decision",
        "article_decisions",
        "status_explanation",
    ]
    for marker in required:
        if marker not in explainability:
            fail(f"Explainability mist marker: {marker}")
    if payload.get("read_only") is not True or explainability.get("read_only") is not True:
        fail("Explainability endpoint is niet expliciet read_only")
    ok(f"endpoint bereikbaar voor receipt_table_id={receipt_id}")
    ok("generic runtime explainability payload bevat verplichte secties")
    ok("R9-08 receipt explainability endpoint is geborgd")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
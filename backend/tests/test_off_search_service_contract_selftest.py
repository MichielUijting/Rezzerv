from __future__ import annotations

import sys
import traceback

from app.services import off_search_service as service


def assert_equal(actual, expected, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: verwacht {expected!r}, ontvangen {actual!r}")


def run_manual_search_contract() -> None:
    original_resolve_receipt_item = service.resolve_receipt_item
    original_query_off = service._query_off
    try:
        service.resolve_receipt_item = lambda receipt_item_id: {
            "receipt_item_id": receipt_item_id,
            "receipt_item_type": "purchase_import_line",
            "receipt_item_source_id": "line-1",
            "receipt_line_text": "Jumbo Passata Rust",
            "retailer_code": "Jumbo",
            "quantity_label": "",
        }
        service._query_off = lambda query, page_size: (
            [
                {"code": "8718452504435", "product_name": "Tomaten Gezeefd Passata", "brands": "Jumbo"},
                {"code": "8718452474356", "product_name": "Basmati rijst", "brands": "Jumbo"},
            ],
            "test_provider",
        )

        result = service.search_off_candidates(
            {
                "receipt_item_id": "purchase-import-line:line-1",
                "query": "Passata",
                "mode": "manual",
                "limit": 10,
            }
        )

        assert_equal(result["query"], "Passata", "handmatige zoekterm")
        assert_equal(result["mutated"], False, "handmatige zoekactie muteert niet")
        assert_equal(result["creates_external_candidate"], False, "maakt geen externe kandidaat")
        assert_equal(
            [row["product_name"] for row in result["results"]],
            ["Tomaten Gezeefd Passata"],
            "handmatige zoekresultaten",
        )
    finally:
        service.resolve_receipt_item = original_resolve_receipt_item
        service._query_off = original_query_off


def run_automatic_search_contract() -> None:
    original_resolve_receipt_item = service.resolve_receipt_item
    original_query_off = service._query_off
    captured = {}

    try:
        service.resolve_receipt_item = lambda receipt_item_id: {
            "receipt_item_id": receipt_item_id,
            "receipt_item_type": "purchase_import_line",
            "receipt_item_source_id": "line-1",
            "receipt_line_text": "Jumbo Passata Rust",
            "retailer_code": "Jumbo",
            "quantity_label": "",
        }

        def fake_query(query, page_size):
            captured["query"] = query
            return [], "test_provider"

        service._query_off = fake_query

        result = service.search_off_candidates(
            {
                "receipt_item_id": "purchase-import-line:line-1",
                "mode": "automatic",
            }
        )

        assert_equal(captured.get("query"), "passata", "automatische providerzoekterm gebruikt essentieel producttoken")
        assert_equal(result["query"], "passata rust", "automatische gerapporteerde zoekterm is genormaliseerd")
        assert_equal(result["results"], [], "automatische lege resultaatset")
        assert_equal(result["mutated"], False, "automatische zoekactie muteert niet")
    finally:
        service.resolve_receipt_item = original_resolve_receipt_item
        service._query_off = original_query_off


def main() -> int:
    checks = [
        ("manual_search_contract", run_manual_search_contract),
        ("automatic_search_contract", run_automatic_search_contract),
    ]
    failures = []

    for name, check in checks:
        try:
            check()
            print(f"PASS {name}")
        except Exception:
            failures.append(name)
            print(f"FAIL {name}")
            traceback.print_exc()

    print(f"RESULT {len(checks) - len(failures)}/{len(checks)} checks passed")
    if failures:
        print("FAILED_CHECKS " + ", ".join(failures))
        return 1

    print("OFF_SEARCH_SERVICE_CONTRACT_GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())

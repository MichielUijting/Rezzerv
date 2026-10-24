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
                {
                    "code": "8718452504435",
                    "product_name": "Tomaten Gezeefd Passata",
                    "brands": "Jumbo",
                    "categories_tags": ["en:tomatoes", "en:tomato-sauces"],
                    "selected_images": {
                        "front": {
                            "display": {
                                "nl": "https://images.openfoodfacts.test/passata-selected.jpg"
                            }
                        }
                    },
                    "image_front_small_url": "https://images.openfoodfacts.test/passata-legacy.jpg",
                },
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
        assert_equal(
            result["results"][0]["image_url"],
            "https://images.openfoodfacts.test/passata-selected.jpg",
            "OFF zoekresultaat gebruikt selected_images-frontfoto",
        )
        assert_equal(
            result["results"][0]["category_tags"],
            ["en:tomatoes", "en:tomato-sauces"],
            "OFF zoekresultaat bewaart canonieke categorietags",
        )
    finally:
        service.resolve_receipt_item = original_resolve_receipt_item
        service._query_off = original_query_off


def run_automatic_search_contract() -> None:
    original_resolve_receipt_item = service.resolve_receipt_item
    original_query_off = service._query_off
    captured = {"queries": []}

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
            captured["queries"].append(query)
            return [], "test_provider"

        service._query_off = fake_query

        result = service.search_off_candidates(
            {
                "receipt_item_id": "purchase-import-line:line-1",
                "mode": "automatic",
            }
        )

        assert_equal(captured.get("query"), "passata", "automatische providerzoekterm gebruikt essentieel producttoken")
        assert_equal(captured["queries"], ["jumbo passata rust", "passata rust", "passata"],
                     "bestaande huismerkzoekterm wordt gevolgd door ruimere suggestiezoektermen")
        assert_equal(result["query"], "jumbo passata rust", "automatische gerapporteerde zoekterm behoudt huismerkevidence")
        assert_equal(result["results"], [], "automatische lege resultaatset")
        assert_equal(result["mutated"], False, "automatische zoekactie muteert niet")

        def broader_query(query, page_size):
            if query == "jumbo passata rust":
                return [], "test_provider"
            return [{"code": "8718452504435", "product_name": "Passata", "brands": "Jumbo"}], "test_provider"

        service._query_off = broader_query
        suggestions = service.search_off_candidates({
            "receipt_item_id": "purchase-import-line:line-1", "mode": "automatic", "limit": 20,
        })
        assert_equal([row["gtin"] for row in suggestions["results"]], ["8718452504435"],
                     "geen exacte eerste hit levert bestaande ruimere OFF-suggestie op")
        assert_equal(suggestions["results"][0]["automatic_evidence"]["matched_queries"],
                     ["passata rust", "passata"], "suggestie behoudt bewijs van ruimere zoekvarianten")
        for flag in ("mutated", "creates_global_product", "creates_household_article",
                     "creates_inventory_event", "creates_external_candidate"):
            assert_equal(suggestions[flag], False, f"suggesties zoeken zonder {flag}")
    finally:
        service.resolve_receipt_item = original_resolve_receipt_item
        service._query_off = original_query_off




def run_exact_gtin_image_contract() -> None:
    original_urlopen = service.urllib.request.urlopen

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return service.json.dumps({
                "status": 1,
                "product": {
                    "code": "8718452504435",
                    "product_name": "Tomaten Gezeefd Passata",
                    "brands": "Jumbo",
                    "categories_tags": ["en:tomatoes", "en:tomato-sauces"],
                    "selected_images": {
                        "front": {
                            "display": {
                                "en": "https://images.openfoodfacts.test/passata-selected-full.jpg"
                            }
                        }
                    },
                    "image_front_url": "https://images.openfoodfacts.test/passata-legacy-full.jpg",
                },
            }).encode("utf-8")

    try:
        service.urllib.request.urlopen = lambda *args, **kwargs: FakeResponse()
        result = service.lookup_off_product_by_gtin("8718452504435")
        assert_equal(result["status"], "found", "exacte GTIN status")
        assert_equal(
            result["product"]["image_url"],
            "https://images.openfoodfacts.test/passata-selected-full.jpg",
            "exacte GTIN lookup gebruikt selected_images-frontfoto",
        )
        assert_equal(
            result["product"]["category_tags"],
            ["en:tomatoes", "en:tomato-sauces"],
            "exacte GTIN lookup bewaart canonieke categorietags",
        )
    finally:
        service.urllib.request.urlopen = original_urlopen

def main() -> int:
    checks = [
        ("manual_search_contract", run_manual_search_contract),
        ("automatic_search_contract", run_automatic_search_contract),
        ("exact_gtin_image_contract", run_exact_gtin_image_contract),
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

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.services import open_food_facts_search_preview as off


def test_backend_container_has_off_runtime_config():
    assert os.getenv("REZZERV_OFF_SEARCH_PROVIDER") == "search_a_licious"
    assert os.getenv("REZZERV_OFF_SEARCH_A_LICIOUS_BASE_URL", "").strip()
    assert os.getenv("REZZERV_OFF_SEARCH_BASE_URL", "").strip()
    assert os.getenv("REZZERV_OFF_SEARCH_TIMEOUT_SECONDS") == "8"
    assert os.getenv("REZZERV_OFF_SEARCH_MAX_QUERIES") == "3"


def test_search_preview_uses_search_a_licious_and_stays_read_only():
    original_query = off._query_provider_with_fallback
    original_provider = off.OFF_SEARCH_PROVIDER
    original_max_queries = off.OFF_SEARCH_MAX_QUERIES
    original_timeout = off.OFF_SEARCH_TIMEOUT_SECONDS

    def fake_query(search_term: str, page_size: int):
        return [
            {
                "code": "8710000000000",
                "product_name": "Halfvolle melk",
                "brands": "Jumbo",
                "quantity": "1 l",
                "categories": "Zuivel",
                "countries": "Nederland",
                "stores": "Jumbo",
            }
        ], [{"search_term": search_term, "provider": "search_a_licious", "http_status": 200, "url": "memory://search", "raw_count": 1}], []

    try:
        off._query_provider_with_fallback = fake_query
        off.OFF_SEARCH_PROVIDER = "search_a_licious"
        off.OFF_SEARCH_MAX_QUERIES = 3
        off.OFF_SEARCH_TIMEOUT_SECONDS = 8.0
        result = off.search_open_food_facts_preview(
            {
                "receipt_line_text": "halfvolle melk",
                "retailer_code": "jumbo",
                "candidate_name": "Halfvolle melk",
                "category": "zuivel",
                "quantity_label": "1 l",
                "limit": 5,
            }
        )
    finally:
        off._query_provider_with_fallback = original_query
        off.OFF_SEARCH_PROVIDER = original_provider
        off.OFF_SEARCH_MAX_QUERIES = original_max_queries
        off.OFF_SEARCH_TIMEOUT_SECONDS = original_timeout

    assert result["ok"] is True
    assert result["status"] == "found"
    assert result["provider"] == "search_a_licious"
    assert result["providers_used"] == ["search_a_licious"]
    assert result["query_limit"] == 3
    assert result["timeout_seconds"] == 8.0
    assert result["result_count"] == 1
    assert result["results"][0]["source_name"] == "open_food_facts"
    assert result["requires_user_selection"] is True
    assert result["creates_global_product"] is False
    assert result["creates_household_article"] is False
    assert result["creates_inventory_event"] is False


if __name__ == "__main__":
    test_backend_container_has_off_runtime_config()
    test_search_preview_uses_search_a_licious_and_stays_read_only()
    print("OFF_SEARCH_PREVIEW_CONTRACT_OK")

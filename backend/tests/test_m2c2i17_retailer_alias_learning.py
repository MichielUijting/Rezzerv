from __future__ import annotations

import json
import uuid

from app.services.external_database_matchflow_evidence import match_retailer_receipt_line
from app.services.external_product_alias_store import find_alias_candidates, save_alias_from_candidate
from app.services.product_evidence_packet import build_product_evidence_packet_dict
from app.services.retailer_catalog_enrichment import CATALOG_SEED_PATH


def _first_catalog_rule() -> dict:
    payload = json.loads(CATALOG_SEED_PATH.read_text(encoding="utf-8"))
    return dict((payload.get("rules") or [])[0])


def test_m2c2i17_catalog_seed_is_packaged_and_matchable() -> None:
    rule = _first_catalog_rule()
    receipt_term = str((rule.get("receipt_terms") or [])[0])
    expected_code = str(rule.get("source_product_code") or "")

    evidence = build_product_evidence_packet_dict(receipt_term, "lidl")

    assert evidence["matched"] is True
    assert evidence["retailer_article_code"] == expected_code
    assert evidence["creates_global_product"] is False
    assert evidence["creates_household_article"] is False
    assert evidence["creates_inventory_event"] is False


def test_m2c2i17_alias_is_learned_and_reused_for_new_receipt_text() -> None:
    rule = _first_catalog_rule()
    receipt_term = str((rule.get("receipt_terms") or [])[0])
    expected_code = str(rule.get("source_product_code") or "")

    initial_result = match_retailer_receipt_line("lidl", receipt_term, True)
    initial_candidate = initial_result["candidates"][0]
    alias_text = f"alias-probe-{uuid.uuid4().hex[:12]}"

    saved = save_alias_from_candidate("lidl", alias_text, initial_candidate, learned_from="test_alias_learning")
    assert saved["ok"] is True

    alias_candidates = find_alias_candidates("lidl", alias_text)
    assert alias_candidates
    assert alias_candidates[0]["candidate_source_product_code"] == expected_code
    assert alias_candidates[0]["creates_global_product"] is False
    assert alias_candidates[0]["creates_household_article"] is False
    assert alias_candidates[0]["creates_inventory_event"] is False

    learned_result = match_retailer_receipt_line("lidl", alias_text, True)
    learned_candidate = learned_result["candidates"][0]

    assert learned_candidate["candidate_source_product_code"] == expected_code
    assert learned_candidate["score"] >= 0.90
    assert learned_result["creates_global_product"] is False
    assert learned_result["creates_household_article"] is False
    assert learned_result["creates_inventory_event"] is False

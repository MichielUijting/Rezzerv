from __future__ import annotations

from app.services import external_database_matchflow_evidence as matchflow


def test_m2c2i20_item_with_external_product_code_is_resolved() -> None:
    item = {
        "is_receipt_item_placeholder": True,
        "purchase_import_line_id": "pil-1",
        "receipt_line_text": "Veldsla",
        "retailer_code": "lidl",
        "retailer_article_number": "lidl:groente.veldsla",
    }

    assert matchflow.is_m2c2i20_external_resolved_item(item) is True
    assert matchflow.m2c2i20_external_product_code(item) == "lidl:groente.veldsla"


def test_m2c2i20_item_without_external_product_code_is_not_resolved() -> None:
    item = {
        "is_receipt_item_placeholder": True,
        "purchase_import_line_id": "pil-2",
        "receipt_line_text": "Onbekend artikel",
        "retailer_code": "lidl",
        "candidate_status": "no_candidate",
    }

    assert matchflow.is_m2c2i20_external_resolved_item(item) is False
    assert matchflow.m2c2i20_external_product_code(item) == ""


def test_m2c2i20_ensure_skips_resolved_items(monkeypatch) -> None:
    captured = {}

    def fake_ensure_external_receipt_item_candidates(*args, **kwargs):
        items = kwargs.get("items") if "items" in kwargs else (args[0] if args else [])
        captured["items"] = list(items or [])
        return {
            "ok": True,
            "total": len(items or []),
            "processed": len(items or []),
            "saved_count": 0,
            "updated_count": 0,
            "skipped_count": 0,
            "errors": [],
            "creates_global_product": False,
            "creates_household_article": False,
            "creates_inventory_event": False,
        }

    monkeypatch.setattr(
        matchflow.candidate_store,
        "ensure_external_receipt_item_candidates",
        fake_ensure_external_receipt_item_candidates,
    )

    resolved_item = {
        "is_receipt_item_placeholder": True,
        "purchase_import_line_id": "pil-1",
        "receipt_line_text": "Veldsla",
        "retailer_code": "lidl",
        "retailer_article_number": "lidl:groente.veldsla",
    }
    unresolved_item = {
        "is_receipt_item_placeholder": True,
        "purchase_import_line_id": "pil-2",
        "receipt_line_text": "Nieuw onbekend artikel",
        "retailer_code": "lidl",
    }

    result = matchflow.ensure_external_receipt_item_candidates(
        items=[resolved_item, unresolved_item],
        include_below_threshold=True,
    )

    assert captured["items"] == [unresolved_item]
    assert result["total"] == 2
    assert result["processed"] == 1
    assert result["external_resolved_skipped_count"] == 1
    assert result["external_resolved_skipped"][0]["external_product_code"] == "lidl:groente.veldsla"
    assert result["m2c2i20_resolved_state_gate"] is True
    assert result["creates_global_product"] is False
    assert result["creates_household_article"] is False
    assert result["creates_inventory_event"] is False

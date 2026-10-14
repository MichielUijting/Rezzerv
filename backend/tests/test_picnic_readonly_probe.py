"""Synthetic read-only Picnic transport and financial boundary tests."""
import pytest

from app.integrations.picnic_readonly_probe import (
    PicnicReadOnlyProbe,
    PicnicReadOnlyContractError,
    summarize_picnic_delivery,
)


def delivery():
    return {
        "type": "DELIVERY",
        "delivery_id": "delivery-one",
        "status": "COMPLETED",
        "orders": [{
            "id": "order-one",
            "creation_time": "2026-10-12T11:00:00Z",
            "status": "COMPLETED",
            "total_price": 2499,
            "total_savings": 150,
            "total_deposit": 50,
            "items": [
                {"type": "ORDER_LINE", "quantity": 2, "name": "Voorbeeldartikel"},
                {"type": "ORDER_LINE", "quantity": 1, "name": "Tweede artikel"},
            ],
        }],
    }


def test_get_list_and_detail_allowlisted_methods_only():
    calls = []

    def transport(method, path, data):
        calls.append((method, path, data))
        if path == "/deliveries/summary":
            return [{"delivery_id": "delivery-one"}]
        return delivery()

    probe = PicnicReadOnlyProbe(transport)
    assert probe.list_deliveries() == [{"delivery_id": "delivery-one"}]
    result = probe.get_delivery_preview("delivery-one")
    assert result["provider"] == "picnic"
    assert result["ready_for_import"] is False
    assert result["orders"][0]["total_cents"] == 2499
    assert result["orders"][0]["deposit_cents"] == 50
    assert result["orders"][0]["savings_cents"] == 150
    assert len(result["orders"][0]["raw_items"]) == 2
    assert calls == [
        ("POST", "/deliveries/summary", []),
        ("GET", "/deliveries/delivery-one", None),
    ]


def test_rejects_identity_mismatch_before_receipt_import():
    probe = PicnicReadOnlyProbe(lambda method, path, data: delivery())
    with pytest.raises(PicnicReadOnlyContractError, match="unexpected response identity"):
        probe.get_delivery_preview("another-delivery")


@pytest.mark.parametrize("change,expected", [
    ({"orders": []}, "empty"),
    ({"delivery_id": ""}, "delivery_id"),
    ({"orders": [{"id": "one", "total_price": 12, "total_savings": 0, "total_deposit": 0, "items": []},
                 {"id": "one", "total_price": 12, "total_savings": 0, "total_deposit": 0, "items": []}]}, "repeated"),
    ({"orders": [{"id": "one", "total_price": 12.5, "total_savings": 0, "total_deposit": 0, "items": []}]}, "integer cents"),
    ({"orders": [{"id": "one", "total_price": 12, "total_savings": -1, "total_deposit": 0, "items": []}]}, "negative"),
])
def test_financial_and_structure_fail_closed(change, expected):
    sample = delivery()
    sample.update(change)
    with pytest.raises(PicnicReadOnlyContractError, match=expected):
        summarize_picnic_delivery(sample)


def test_history_bounded_and_error_propagates_without_mutations():
    probe = PicnicReadOnlyProbe(lambda method, path, data: [{"delivery_id": str(n)} for n in range(41)])
    with pytest.raises(PicnicReadOnlyContractError, match="excessive"):
        probe.list_deliveries()


def test_does_not_mutate_source_observations():
    sample = delivery()
    preview = summarize_picnic_delivery(sample)
    preview["orders"][0]["raw_items"][0]["name"] = "Mutated"
    assert sample["orders"][0]["items"][0]["name"] == "Voorbeeldartikel"

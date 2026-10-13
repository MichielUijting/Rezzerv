"""Conservative conversion of *synthetic* Picnic delivery orders to Inhuis receipts.

External API model reference: MRVDH/picnic-api src/domains/cart/types.ts.
A Picnic ORDER_LINE contains items: OrderArticle[], and price/display_price
in cents. The placed order also carries total_deposit and fees. Values must
reconcile exactly before a canonical retailer envelope is constructed.

No Picnic API account is needed to test this module. Real account responses
and final invoices have NOT been verified. No direct DB writes are performed.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from app.integrations.picnic_readonly_probe import (
    PicnicReadOnlyContractError,
    _array,
    _cents,
    _id,
)
from app.integrations.retailer_receipts import RetailerReceiptEnvelope


def _eur(cents: int) -> str:
    return str((Decimal(cents) / Decimal(100)).quantize(Decimal("0.01")))


def _positive_money(value: Any, field: str) -> int:
    cents = _cents(value, field)
    if cents < 0:
        raise PicnicReadOnlyContractError(f"{field}: negative amount")
    return cents


def _article_line(value: Any, index: int) -> tuple[dict[str, Any], int, int]:
    if not isinstance(value, dict) or value.get("type") != "ORDER_LINE":
        raise PicnicReadOnlyContractError("Unsupported Picnic order line structure")
    raw_items = _array(value.get("items"), "line.items", 250)
    if not raw_items:
        raise PicnicReadOnlyContractError("Picnic order line has no articles")
    # Each article occurrence has no stable explicit count. For now only accept
    # homogeneous occurrence arrays, without guessing mixed bundle allocations.
    identity = None
    for article in raw_items:
        if not isinstance(article, dict) or article.get("type") != "ORDER_ARTICLE":
            raise PicnicReadOnlyContractError("Unsupported Picnic article")
        article_id = _id(article.get("id"), "article.id")
        name = article.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 240:
            raise PicnicReadOnlyContractError("Picnic article name missing")
        this_identity = (article_id, name.strip())
        if identity is None:
            identity = this_identity
        if identity != this_identity:
            raise PicnicReadOnlyContractError("Mixed Picnic bundle needs review")
    gross = _positive_money(value.get("price"), "line.price")
    net = _positive_money(value.get("display_price"), "line.display_price")
    if net > gross:
        raise PicnicReadOnlyContractError("Picnic line net exceeds gross")
    qty = len(raw_items)
    # Splitting a group amount across units without exact cent divisibility
    # would fabricate a unit price. Fail closed rather than rounding.
    if gross % qty or net % qty:
        raise PicnicReadOnlyContractError("Picnic unit allocation needs review")
    item = {
        "name": identity[1],
        "quantity": str(qty),
        "retailerSku": identity[0],
        "grossAmount": _eur(gross),
        "unitPrice": _eur(gross // qty),
        "lineTotal": _eur(net),
    }
    if gross != net:
        item["discountAmount"] = _eur(gross - net)
    return item, net, gross - net


def picnic_order_to_envelope(delivery: Mapping[str, Any], order_id: str) -> RetailerReceiptEnvelope:
    """Strict verified-internal-math preview; does not establish invoice truth.

    Use only with known or synthetic deliveries; no real Picnic order import
    endpoint is enabled by this operation.
    """
    if not isinstance(delivery, dict):
        raise PicnicReadOnlyContractError("Picnic delivery invalid")
    delivery_id = _id(delivery.get("delivery_id"), "delivery_id")
    if delivery.get("status") != "COMPLETED":
        raise PicnicReadOnlyContractError("Delivery not completed")
    orders = _array(delivery.get("orders"), "orders", 20)
    selected = [x for x in orders if isinstance(x, dict) and x.get("id") == order_id]
    if len(selected) != 1:
        raise PicnicReadOnlyContractError("Order identity missing or ambiguous")
    order = selected[0]
    if order.get("status") != "COMPLETED" or order.get("cancellation_time") is not None:
        raise PicnicReadOnlyContractError("Order is not finalized")
    raw_lines = _array(order.get("items"), "order.items", 250)
    if not raw_lines:
        raise PicnicReadOnlyContractError("Order has no articles")
    lines: list[dict[str, Any]] = []
    lines_total = 0
    discount_total = 0
    for index, raw in enumerate(raw_lines, 1):
        item, net, discount = _article_line(raw, index)
        lines.append(item)
        lines_total += net
        discount_total += discount
    source_discount = _positive_money(order.get("total_savings"), "total_savings")
    if discount_total != source_discount:
        raise PicnicReadOnlyContractError("Picnic savings do not reconcile")
    deposit = _cents(order.get("total_deposit"), "total_deposit")
    if deposit != 0:
        raise PicnicReadOnlyContractError("Picnic deposits require invoice reconciliation")
    # No assumption about Picnic fee schema or whether totals already include
    # fees: reject any such financial components until real invoice evidence.
    if order.get("fees") or order.get("deposit_breakdown") or order.get("returned_containers"):
        raise PicnicReadOnlyContractError("Picnic financial adjustments require invoice reconciliation")
    final_total = _positive_money(order.get("total_price"), "total_price")
    checkout_total = _positive_money(order.get("checkout_total_price"), "checkout_total_price")
    if final_total != checkout_total or lines_total != final_total:
        raise PicnicReadOnlyContractError("Picnic order total does not reconcile")
    created = order.get("creation_time")
    if not isinstance(created, str) or len(created) < 10:
        raise PicnicReadOnlyContractError("Picnic purchase time missing")
    return RetailerReceiptEnvelope(
        provider="picnic",
        external_receipt_id=f"{delivery_id}:{_id(order_id, 'order.id')}",
        receipt={
            "id": f"{delivery_id}:{order_id}",
            "purchaseAt": created,
            "totalAmount": _eur(final_total),
            "paidTotal": _eur(final_total),
            "discountTotal": _eur(discount_total),
            "depositTotal": "0.00",
            "items": lines,
            "_picnic_invoice_verified": False,
        },
    )

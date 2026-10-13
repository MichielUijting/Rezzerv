"""Isolated read-only Picnic delivery transport and financial observations.

This is a protocol research boundary, NOT a connected Picnic account, Kassa
importer or authenticated production integration. Never store credentials,
call login, or persist a receipt in this component.

Research reference (unofficial; no contractual availability):
https://github.com/MRVDH/picnic-api/blob/main/src/domains/delivery/service.ts
https://github.com/MRVDH/picnic-api/blob/main/src/domains/cart/types.ts
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping
from urllib.parse import quote


class PicnicReadOnlyContractError(ValueError):
    """Reject unknown/malformed Picnic response before any Kassa write."""


MAX_DELIVERIES = 40
MAX_ORDERS = 20
MAX_LINES = 250


def _cents(value: Any, field: str) -> int:
    # The researched client types define integer cent values. Do not accept
    # floats, bools, or formatted currency amounts from untrusted responses.
    if isinstance(value, bool) or not isinstance(value, int) or abs(value) > 100_000_000:
        raise PicnicReadOnlyContractError(f"{field}: expected bounded integer cents")
    return value


def _id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 180:
        raise PicnicReadOnlyContractError(f"{field}: missing/invalid ID")
    return value.strip()


def _array(value: Any, field: str, limit: int) -> list:
    if not isinstance(value, list) or len(value) > limit:
        raise PicnicReadOnlyContractError(f"{field}: invalid or excessive records")
    return value


def _quantity(value: Any) -> str:
    # Preserve decimal quantities; do not silently convert weight to integer.
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise PicnicReadOnlyContractError("quantity: invalid value")
    try:
        quantity = Decimal(str(value))
        if not quantity.is_finite() or quantity <= 0 or quantity > 100_000:
            raise PicnicReadOnlyContractError("quantity: out of range")
        return format(quantity, "f")
    except (InvalidOperation, ValueError) as exc:
        raise PicnicReadOnlyContractError("quantity: invalid decimal") from exc


def _order_lines(order: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = _array(order.get("items"), "order.items", MAX_LINES)
    lines = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise PicnicReadOnlyContractError("order.items: invalid item")
        # The real API can contain grouped/substitution lines; preserving the
        # raw observation is safer than guessing which nested price is final.
        lines.append(dict(entry))
    return lines


def summarize_picnic_delivery(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Make a loss-aware preview, not a canonical receipt or invented total."""
    if not isinstance(payload, dict):
        raise PicnicReadOnlyContractError("delivery: invalid object")
    delivery_id = _id(payload.get("delivery_id"), "delivery_id")
    raw_orders = _array(payload.get("orders"), "delivery.orders", MAX_ORDERS)
    if not raw_orders:
        raise PicnicReadOnlyContractError("delivery.orders: empty")
    orders = []
    seen = set()
    for order in raw_orders:
        if not isinstance(order, dict):
            raise PicnicReadOnlyContractError("delivery.orders: invalid order")
        order_id = _id(order.get("id"), "order.id")
        if order_id in seen:
            raise PicnicReadOnlyContractError("delivery.orders: repeated order id")
        seen.add(order_id)
        total = _cents(order.get("total_price"), "order.total_price")
        savings = _cents(order.get("total_savings"), "order.total_savings")
        deposit = _cents(order.get("total_deposit"), "order.total_deposit")
        if total < 0 or savings < 0:
            raise PicnicReadOnlyContractError("order: invalid negative amount")
        orders.append({
            "order_id": order_id,
            "creation_time": order.get("creation_time"),
            "status": order.get("status"),
            "total_cents": total,
            "savings_cents": savings,
            "deposit_cents": deposit,
            "raw_items": _order_lines(order),
        })
    return {
        "provider": "picnic",
        "delivery_id": delivery_id,
        "delivery_status": payload.get("status"),
        "orders": orders,
        "ready_for_import": False,
        "reason": "Definitieve factuur/reconciliatie en live authenticatie niet geverifieerd",
    }


@dataclass(frozen=True)
class PicnicReadOnlyProbe:
    """Transport-injected, allowlisted API calls: no credentials or side effects.

    transport(method, path, payload) is owned by the caller. It must supply
    authenticated context *outside* this component if ever used for live
    diagnosis. This class deliberately does not implement login or tokens.
    """

    transport: Callable[[str, str, Any], Any]

    def list_deliveries(self) -> list[dict[str, Any]]:
        response = self.transport("POST", "/deliveries/summary", [])
        return _array(response, "deliveries", MAX_DELIVERIES)

    def get_delivery_preview(self, delivery_id: str) -> dict[str, Any]:
        safe_id = _id(delivery_id, "delivery_id")
        response = self.transport("GET", f"/deliveries/{quote(safe_id, safe='')}", None)
        preview = summarize_picnic_delivery(response)
        if preview["delivery_id"] != safe_id:
            raise PicnicReadOnlyContractError("delivery_id: unexpected response identity")
        return preview

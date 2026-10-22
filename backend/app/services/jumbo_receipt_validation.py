"""Pure server-side Jumbo structured receipt validation; no data writes."""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.integrations.retailer_receipts import RetailerReceiptEnvelope


def validate_jumbo_receipt_for_import(envelope: RetailerReceiptEnvelope) -> None:
    """Fail closed before any Kassa/receipt-source write.

    Browser-side validation and source_origin are not authorities. The server
    must independently reconcile a structured Jumbo envelope. Unrecognized
    discounts/weight layouts await explicit review instead of guessing.
    """
    if envelope.provider != "jumbo":
        return
    receipt = envelope.receipt
    identifier = str(envelope.external_receipt_id or "")
    # Preserve Jumbo's exact source identifier, including printable punctuation.
    # Receipt identity and equality still fail closed for blanks, whitespace,
    # control characters, non-ASCII values and length violations.
    if not re.fullmatch(r"[\x21-\x7E]{4,100}", identifier):
        raise ValueError("Ongeldig Jumbo-bonnummer")
    if str(receipt.get("transactionId") or "") != identifier:
        raise ValueError("Jumbo-bonnummer komt niet overeen")
    purchase_at = receipt.get("purchaseDateTime")
    if not isinstance(purchase_at, str) or len(purchase_at) < 10:
        raise ValueError("Jumbo-aankoopdatum ontbreekt")
    try:
        datetime.fromisoformat(purchase_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Jumbo-aankoopdatum is ongeldig") from exc
    lines = receipt.get("items")
    if not isinstance(lines, list) or not 1 <= len(lines) <= 250:
        raise ValueError("Jumbo-artikelregels ontbreken of zijn te talrijk")

    def cents(raw: Any) -> int:
        if isinstance(raw, bool) or not isinstance(raw, (str, int, float, Decimal)):
            raise ValueError("Jumbo-bedrag ontbreekt of heeft een onjuist type")
        try:
            value = Decimal(str(raw))
        except (ValueError, InvalidOperation) as exc:
            raise ValueError("Jumbo-bedrag is ongeldig") from exc
        if not value.is_finite() or value != value.quantize(Decimal("0.01")):
            raise ValueError("Jumbo-bedrag bevat ongeldige centen")
        return int(value * 100)

    summed = 0
    deposits = 0
    discounts = 0
    products = 0
    for line in lines:
        if not isinstance(line, dict):
            raise ValueError("Ongeldige Jumbo-bonregel")
        label = str(line.get("description") or "").strip()
        kind = line.get("lineType")
        if not label or len(label) > 240 or kind not in {"product", "deposit", "discount"}:
            raise ValueError("Onherkenbaar Jumbo-regeltype")
        qty = line.get("quantity")
        if isinstance(qty, bool) or not isinstance(qty, int) or not 1 <= qty <= 10000:
            raise ValueError("Ongeldig Jumbo-aantal")
        unit = cents(line.get("unitPrice"))
        amount = cents(line.get("lineTotal"))
        if kind == "product":
            products += 1
            if amount < 0 or unit < 0:
                raise ValueError("Negatieve Jumbo-productprijs")
        if kind == "deposit":
            deposits += amount
        if kind == "discount":
            if amount > 0:
                raise ValueError("Positieve Jumbo-korting")
            discounts += amount
        if abs(unit * qty - amount) > 1:
            raise ValueError("Jumbo-artikelbedrag sluit niet op aantal aan")
        summed += amount
    if products < 1:
        raise ValueError("Jumbo-bon bevat geen producten")
    grand_total = cents(receipt.get("grandTotal"))
    if grand_total < 0 or abs(summed - grand_total) > 1:
        raise ValueError("Jumbo-bontotaal sluit niet op regels aan")
    if cents(receipt.get("depositTotal")) != deposits:
        raise ValueError("Jumbo-statiegeldtotaal sluit niet aan")
    if cents(receipt.get("discountTotal")) != abs(discounts):
        raise ValueError("Jumbo-kortingstotaal sluit niet aan")



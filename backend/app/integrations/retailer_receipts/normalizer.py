"""
Technical Design Reference:
- TD Section: TD-03 Receipt ingestion en parsers
- Module Role: Normalize AH, Jumbo and Lidl structured receipt observations
- Runtime Type: production
- Used By: StructuredRetailerReceiptScannerAdapter
- Depends On: CanonicalReceiptV1
- Reads Data: no
- Writes Data: no
- Status Authority: no
- Refactor Status: keep
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from app.integrations.receipt_scanners.schemas.canonical_receipt_v1 import (
    CanonicalDocumentV1,
    CanonicalReceiptV1,
    IdentifiersV1,
    LineConfidenceV1,
    ProviderInfoV1,
    QualityV1,
    ReceiptBodyV1,
    ReceiptLineV1,
    StoreV1,
    TotalsV1,
    TransactionV1,
)
from app.integrations.retailer_receipts.contracts import RetailerReceiptEnvelope

_PROVIDER_NAMES = {
    "ah": "Albert Heijn",
    "jumbo": "Jumbo",
    "lidl": "Lidl",
}

_LINE_KEYS = ("items", "products", "lines", "entries", "receiptLines", "basketItems")
_WRAPPER_KEYS = ("receipt", "data", "ticket", "order")
_CONTEXT_KEYS = _WRAPPER_KEYS + ("transaction",)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def _nested_first(root: dict[str, Any], *keys: str) -> Any:
    candidates = [root]
    seen = {id(root)}
    cursor = 0
    while cursor < len(candidates):
        candidate = candidates[cursor]
        cursor += 1
        for wrapper in _CONTEXT_KEYS:
            nested = candidate.get(wrapper)
            if isinstance(nested, dict) and id(nested) not in seen:
                seen.add(id(nested))
                candidates.append(nested)
    for candidate in candidates:
        value = _first(candidate, *keys)
        if value not in (None, ""):
            return value
    return None


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, dict):
        value = _first(value, "amount", "value", "total", "price")
    if value in (None, ""):
        return None
    if isinstance(value, str):
        cleaned = value.strip().replace("€", "").replace("EUR", "").strip()
        if "," in cleaned and "." not in cleaned:
            cleaned = cleaned.replace(",", ".")
        value = cleaned
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _date_and_time(value: Any) -> tuple[date | None, time | None]:
    if value in (None, ""):
        return None, None
    text = str(value).strip()
    if not text:
        return None, None
    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
        return dt.date(), dt.timetz().replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.date(), None
        except ValueError:
            continue
    return None, None


def _receipt_root(payload: dict[str, Any]) -> dict[str, Any]:
    current = payload
    for key in _WRAPPER_KEYS:
        nested = current.get(key)
        if isinstance(nested, dict) and nested:
            current = nested
    return current


def _line_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    roots = [payload, _receipt_root(payload)]
    for root in roots:
        for key in _LINE_KEYS:
            value = root.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _line_type(item: dict[str, Any]) -> str:
    raw = str(_first(item, "line_type", "lineType", "type", "kind") or "").strip().lower()
    if raw in {"discount", "korting", "promotion", "promo"}:
        return "discount"
    if raw in {"deposit", "statiegeld", "returnable_deposit"}:
        return "deposit"
    if raw in {"loyalty", "stamp", "stamps", "koopzegels", "spaarzegels"}:
        return "loyalty"
    if raw in {"payment", "betaling"}:
        return "payment"
    if raw in {"tax", "vat", "btw"}:
        return "tax"
    if raw in {"total", "totaal", "subtotal", "subtotaal"}:
        return "total" if raw in {"total", "totaal"} else "subtotal"
    return "product"


def _normalize_line(item: dict[str, Any], index: int) -> ReceiptLineV1:
    product = _mapping(_first(item, "product", "article", "item"))
    label = (
        _first(item, "description", "name", "productName", "title", "label", "text")
        or _first(product, "description", "name", "title", "label")
        or f"Artikel {index}"
    )
    quantity = _decimal(_first(item, "quantity", "count", "qty", "units"))
    if quantity is None:
        quantity = Decimal("1")

    unit_price = _decimal(_first(item, "unit_price", "unitPrice", "currentUnitPrice", "pricePerUnit"))
    if unit_price is None:
        unit_price = _decimal(_first(product, "unitPrice", "price"))

    line_total = _decimal(_first(item, "line_total", "lineTotal", "totalPrice", "total", "amount", "finalPrice"))
    if line_total is None and unit_price is not None:
        line_total = unit_price * quantity

    discount = _decimal(_first(item, "discount_amount", "discountAmount", "discount", "priceDiscount"))
    barcode = _first(item, "gtin", "ean", "barcode", "codeInput", "productCode")
    if barcode in (None, ""):
        barcode = _first(product, "gtin", "ean", "barcode", "code", "id")
    retailer_sku = _first(item, "retailer_sku", "retailerSku", "sku", "articleNumber", "articleId")
    if retailer_sku in (None, ""):
        retailer_sku = _first(product, "sku", "articleNumber", "id")

    identifiers = None
    if barcode not in (None, "") or retailer_sku not in (None, ""):
        barcode_text = str(barcode).strip() if barcode not in (None, "") else None
        gtin = barcode_text if barcode_text and barcode_text.isdigit() and len(barcode_text) in {8, 12, 13, 14} else None
        identifiers = IdentifiersV1(
            gtin=gtin,
            barcode=barcode_text,
            retailer_sku=str(retailer_sku).strip() if retailer_sku not in (None, "") else None,
        )

    raw_text = str(_first(item, "raw_text", "rawText") or label).strip()
    return ReceiptLineV1(
        line_number=index,
        line_type=_line_type(item),
        raw_text=raw_text or f"Artikel {index}",
        description=str(label).strip(),
        quantity=quantity,
        unit=str(_first(item, "unit", "unitOfMeasure", "uom") or "").strip() or None,
        unit_price=unit_price,
        discount_amount=discount,
        line_total=line_total,
        identifiers=identifiers,
        confidence=LineConfidenceV1(
            description=1.0,
            quantity=1.0,
            unit_price=1.0 if unit_price is not None else None,
            line_total=1.0 if line_total is not None else None,
            identifier=1.0 if identifiers is not None else None,
        ),
    )


def _store(payload: dict[str, Any], provider: str) -> StoreV1:
    root = _receipt_root(payload)
    store = _mapping(_first(root, "store", "shop", "branch", "location"))
    branch_name = _first(store, "name", "branchName", "description")
    if not branch_name:
        branch_name = _nested_first(payload, "storeName", "branchName", "shopName")
    return StoreV1(
        name=_PROVIDER_NAMES[provider],
        branch_name=str(branch_name).strip() if branch_name not in (None, "") else None,
        address=str(_first(store, "address", "street", "addressLine") or "").strip() or None,
        postal_code=str(_first(store, "postalCode", "postcode", "zip") or "").strip() or None,
        city=str(_first(store, "city", "town") or "").strip() or None,
        country_code=str(_first(store, "countryCode", "country") or "NL").strip().upper()[:2],
        retailer_code=provider,
        confidence=1.0,
    )


def _total(payload: dict[str, Any], lines: Iterable[ReceiptLineV1]) -> Decimal:
    value = _nested_first(
        payload,
        "grand_total", "grandTotal", "totalAmount", "totalPrice", "total", "amountPaid", "finalAmount",
    )
    total = _decimal(value)
    if total is not None:
        return total
    line_values = [line.line_total for line in lines if line.line_total is not None and line.line_type in {"product", "deposit"}]
    if line_values:
        return sum(line_values, Decimal("0"))
    raise ValueError("Digitale kassabon bevat geen bruikbaar totaalbedrag")


def normalize_retailer_receipt(
    envelope: RetailerReceiptEnvelope,
    *,
    scan_id: str,
    document_sha256: str,
) -> CanonicalReceiptV1:
    payload = envelope.receipt
    raw_lines = _line_candidates(payload)
    if not raw_lines:
        raise ValueError("Digitale kassabon bevat geen artikelregels")
    lines = [_normalize_line(item, index) for index, item in enumerate(raw_lines, start=1)]
    grand_total = _total(payload, lines)

    purchase_value = _nested_first(
        payload,
        "purchaseAt", "purchaseDateTime", "transactionDateTime", "dateTime",
        "createdAt", "transactionDate", "purchaseDate", "date",
    )
    purchase_date, purchase_time = _date_and_time(purchase_value)
    explicit_time = _nested_first(payload, "purchaseTime", "transactionTime", "time")
    if purchase_time is None and explicit_time not in (None, ""):
        try:
            purchase_time = time.fromisoformat(str(explicit_time).strip())
        except ValueError:
            purchase_time = None

    currency = str(_nested_first(payload, "currency", "currencyCode") or "EUR").strip().upper()
    if len(currency) != 3:
        currency = "EUR"

    discount_total = _decimal(_nested_first(payload, "discountTotal", "totalDiscount", "discount"))
    subtotal = _decimal(_nested_first(payload, "subtotal", "subTotal"))
    receipt_number = _nested_first(payload, "receiptNumber", "receiptNo", "transactionId", "id")
    store = _store(payload, envelope.provider)

    missing_line_totals = sum(1 for line in lines if line.line_total is None)
    warnings: list[dict[str, Any]] = []
    if missing_line_totals:
        warnings.append({
            "code": "MISSING_LINE_TOTAL",
            "count": missing_line_totals,
            "message": "Niet alle digitale bonregels bevatten een regelbedrag.",
        })

    quality_score = 1.0 if missing_line_totals == 0 else max(0.7, 1.0 - (missing_line_totals / max(1, len(lines))))
    return CanonicalReceiptV1(
        scan_id=scan_id,
        provider=ProviderInfoV1(
            code=f"retailer-{envelope.provider}",
            result_id=envelope.external_receipt_id,
            model_version="retailer-receipt-v1",
        ),
        status="completed",
        document=CanonicalDocumentV1(
            sha256=document_sha256,
            mime_type="application/vnd.inhuis.retailer-receipt+json",
            page_count=1,
        ),
        receipt=ReceiptBodyV1(
            store=store,
            transaction=TransactionV1(
                purchase_date=purchase_date,
                purchase_time=purchase_time,
                receipt_number=str(receipt_number).strip() if receipt_number not in (None, "") else envelope.external_receipt_id,
                currency=currency,
                confidence=1.0 if purchase_date is not None else 0.8,
            ),
            totals=TotalsV1(
                subtotal=subtotal,
                discount_total=discount_total,
                grand_total=grand_total,
                paid_total=_decimal(_nested_first(payload, "paidTotal", "amountPaid")),
                confidence=1.0,
            ),
            lines=lines,
            warnings=warnings,
        ),
        quality=QualityV1(
            overall_confidence=quality_score,
            requires_review=bool(missing_line_totals),
        ),
        processed_at=datetime.now(timezone.utc),
    )

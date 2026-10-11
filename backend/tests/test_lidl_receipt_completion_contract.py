"""Focused regression contracts for Lidl discounts, deposit and durable source routing."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from app.integrations.receipt_scanners.normalizer import canonical_to_receipt_parse_result
from app.receipt_ingestion.receipt_line_semantics import derive_receipt_line_semantics
from app.integrations.retailer_receipts import RetailerReceiptEnvelope, normalize_retailer_receipt


def _normalized_receipt(*, items, total: str, discount: str | None = None):
    payload = {"dateTime": "2024-01-11T13:53:00", "totalAmount": total, "products": items}
    if discount is not None:
        payload["discountTotal"] = discount
    return normalize_retailer_receipt(
        RetailerReceiptEnvelope(provider="lidl", external_receipt_id="lidl-regression", receipt=payload),
        scan_id="lidl-regression",
        document_sha256="e" * 64,
    )


def test_lidl_discount_is_not_an_automatic_review_reason() -> None:
    canonical = _normalized_receipt(
        total="1.39",
        discount="0.60",
        items=[{"name": "Roerbakmix Chinees", "quantity": 1, "unitPrice": "1.99",
                "grossAmount": "1.99", "discountAmount": "0.60", "lineTotal": "1.39"}],
    )
    assert canonical.quality.requires_review is False
    assert canonical.receipt.totals.discount_total == Decimal("0.60")
    persisted = canonical_to_receipt_parse_result(canonical)
    assert persisted.parse_status == "approved"
    assert persisted.lines[0]["line_total"] == 1.39
    assert persisted.lines[0]["discount_amount"] == 0.6


def test_lidl_explicit_deposit_is_financial_but_not_product() -> None:
    canonical = _normalized_receipt(
        total="6.59",
        items=[
            {"name": "Ger. Wittems dubbel", "lineTotal": "5.99"},
            {"name": "6pak Ger. statiegeld", "lineType": "deposit", "lineTotal": "0.60"},
        ],
    )
    assert canonical.receipt.lines[1].line_type == "deposit"
    assert canonical.receipt.totals.deposit_total == Decimal("0.60")
    assert sum(line.line_total or Decimal("0") for line in canonical.receipt.lines) == Decimal("6.59")
    persisted = canonical_to_receipt_parse_result(canonical)
    assert persisted.lines[1]["line_type"] == "deposit"
    semantics = derive_receipt_line_semantics(persisted.lines[1])
    assert semantics["line_role"] == "financial"
    assert semantics["inventory_eligible"] is False
    assert persisted.parse_status == "approved"


def test_durable_retailer_root_is_separate_from_legacy_root() -> None:
    root = Path(__file__).resolve().parents[2]
    docker = (root / "docker-compose.yml").read_text(encoding="utf-8")
    routes = (root / "backend/app/api/retailer_receipt_routes.py").read_text(encoding="utf-8")
    previews = (root / "backend/app/api/receipt_preview_routes.py").read_text(encoding="utf-8")
    assert "rezzerv_retailer_receipts:/app/data/retailer-receipts" in docker
    assert "RETAILER_RECEIPT_STORAGE_ROOT" in routes
    assert '/app/data/retailer-receipts/raw' in routes
    assert "_is_allowed_receipt_storage_path" in previews
    assert "receipt_storage_root.resolve()" not in previews

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

SCHEMA_VERSION = "1.0"
ScannerStatus = Literal["queued", "processing", "completed", "failed", "cancelled", "expired"]
ReceiptLineType = Literal["product", "discount", "deposit", "subtotal", "total", "tax", "payment", "header", "footer", "loyalty", "unknown", "noise"]
StandardErrorCode = Literal["UNSUPPORTED_FORMAT", "DOCUMENT_TOO_LARGE", "DOCUMENT_UNREADABLE", "NO_RECEIPT_DETECTED", "MULTIPLE_RECEIPTS_DETECTED", "PROVIDER_TIMEOUT", "PROVIDER_UNAVAILABLE", "INVALID_PROVIDER_RESULT", "CONTRACT_VALIDATION_FAILED", "INTERNAL_MAPPING_ERROR", "DUPLICATE_RESULT"]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ProviderInfoV1(ContractModel):
    code: str | None = None
    job_id: str | None = None
    result_id: str | None = None
    model_version: str | None = None


class CanonicalDocumentV1(ContractModel):
    sha256: str
    mime_type: str
    page_count: int | None = Field(default=None, ge=1)

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        normalized = str(value or "").lower()
        if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
            raise ValueError("document.sha256 must contain exactly 64 hexadecimal characters")
        return normalized

    @field_validator("mime_type")
    @classmethod
    def validate_mime(cls, value: str) -> str:
        if "/" not in str(value or ""):
            raise ValueError("document.mime_type must be a MIME type")
        return value


class StoreV1(ContractModel):
    name: str | None = None
    branch_name: str | None = None
    address: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country_code: str | None = None
    retailer_code: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class TransactionV1(ContractModel):
    purchase_date: date | None = None
    purchase_time: time | None = None
    receipt_number: str | None = None
    register_number: str | None = None
    currency: str | None = "EUR"
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if len(value) != 3 or not value.isalpha() or value.upper() != value:
            raise ValueError("currency must be a three-letter uppercase code")
        return value


class TotalsV1(ContractModel):
    subtotal: Decimal | None = None
    discount_total: Decimal | None = None
    deposit_total: Decimal | None = None
    tax_total: Decimal | None = None
    grand_total: Decimal | None = None
    paid_total: Decimal | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class IdentifiersV1(ContractModel):
    gtin: str | None = None
    barcode: str | None = None
    retailer_sku: str | None = None


class TaxV1(ContractModel):
    rate: Decimal | None = None
    amount: Decimal | None = None


class LineConfidenceV1(ContractModel):
    description: float | None = Field(default=None, ge=0.0, le=1.0)
    quantity: float | None = Field(default=None, ge=0.0, le=1.0)
    unit_price: float | None = Field(default=None, ge=0.0, le=1.0)
    line_total: float | None = Field(default=None, ge=0.0, le=1.0)
    identifier: float | None = Field(default=None, ge=0.0, le=1.0)


class BoundingBoxV1(ContractModel):
    page: int = Field(ge=1)
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(ge=0.0, le=1.0)
    height: float = Field(ge=0.0, le=1.0)


class ReceiptLineV1(ContractModel):
    line_number: int = Field(ge=1)
    line_type: ReceiptLineType
    raw_text: str = Field(min_length=1)
    description: str | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    gross_amount: Decimal | None = None
    discount_amount: Decimal | None = None
    line_total: Decimal | None = None
    identifiers: IdentifiersV1 | None = None
    tax: TaxV1 | None = None
    confidence: LineConfidenceV1 | None = None
    bounding_box: BoundingBoxV1 | None = None


class ReceiptBodyV1(ContractModel):
    store: StoreV1
    transaction: TransactionV1
    totals: TotalsV1
    lines: list[ReceiptLineV1]
    warnings: list[Any] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_lines(self) -> "ReceiptBodyV1":
        if not self.lines:
            raise ValueError("receipt.lines must contain at least one visible receipt line")
        line_numbers = [line.line_number for line in self.lines]
        if len(line_numbers) != len(set(line_numbers)):
            raise ValueError("receipt.lines contains duplicate line_number values")
        productish = {"product", "deposit", "loyalty", "unknown"}
        if not any(line.line_type in productish for line in self.lines):
            raise ValueError("receipt.lines must contain a product, deposit, loyalty or unknown candidate")
        return self


class QualityV1(ContractModel):
    overall_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    requires_review: bool


class ScannerErrorV1(ContractModel):
    code: StandardErrorCode
    message: str = Field(min_length=1)
    retryable: bool
    provider_reference: str | None = None


class CanonicalReceiptV1(ContractModel):
    schema_version: str = SCHEMA_VERSION
    scan_id: str = Field(min_length=1)
    provider: ProviderInfoV1 | None = None
    status: ScannerStatus
    document: CanonicalDocumentV1 | None = None
    receipt: ReceiptBodyV1 | None = None
    quality: QualityV1 | None = None
    error: ScannerErrorV1 | None = None
    processed_at: datetime | None = None

    _legacy_parse_status: str | None = PrivateAttr(default=None)
    _legacy_parser_diagnostics: dict[str, Any] | None = PrivateAttr(default=None)
    _legacy_confidence_score: float | None = PrivateAttr(default=None)

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if str(value).split(".", 1)[0] != "1":
            raise ValueError("CanonicalReceiptV1 major schema version must be 1")
        return value

    @model_validator(mode="after")
    def validate_status_payload(self) -> "CanonicalReceiptV1":
        if self.status == "completed":
            if self.document is None:
                raise ValueError("document is required when status=completed")
            if self.receipt is None:
                raise ValueError("receipt is required when status=completed")
            if self.quality is None:
                raise ValueError("quality is required when status=completed")
            if self.receipt.totals.grand_total is None:
                raise ValueError("receipt.totals.grand_total is required when status=completed")
            if self.error is not None:
                raise ValueError("error must be absent when status=completed")
        elif self.status == "failed":
            if self.error is None:
                raise ValueError("error is required when status=failed")
            if self.receipt is not None:
                raise ValueError("receipt must be absent when status=failed")
        return self

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator


class ScanDocumentV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_ref: str = Field(min_length=1)
    mime_type: str = Field(min_length=3)
    original_filename: str = Field(min_length=1)
    sha256: str
    size_bytes: int = Field(ge=0)

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        normalized = str(value or "").lower()
        if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
            raise ValueError("sha256 must contain exactly 64 hexadecimal characters")
        return normalized


class ScanHintsV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locale: str | None = "nl-NL"
    currency: str | None = "EUR"
    expected_store: str | None = None


class ScanRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    scan_id: str = Field(min_length=1)
    document: ScanDocumentV1
    hints: ScanHintsV1 = Field(default_factory=ScanHintsV1)
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    _document_bytes: bytes | None = PrivateAttr(default=None)

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != "1.0":
            raise ValueError("Release A supports ScanRequestV1 schema_version 1.0 only")
        return value

    @classmethod
    def from_bytes(
        cls,
        *,
        scan_id: str,
        file_bytes: bytes,
        filename: str,
        mime_type: str,
        locale: str = "nl-NL",
        currency: str = "EUR",
        expected_store: str | None = None,
    ) -> Self:
        digest = hashlib.sha256(file_bytes).hexdigest()
        request = cls(
            scan_id=scan_id,
            document=ScanDocumentV1(
                content_ref=f"internal://receipt-scan/{scan_id}",
                mime_type=mime_type,
                original_filename=filename,
                sha256=digest,
                size_bytes=len(file_bytes),
            ),
            hints=ScanHintsV1(locale=locale, currency=currency, expected_store=expected_store),
        )
        request._document_bytes = bytes(file_bytes)
        return request

    def runtime_document_bytes(self) -> bytes:
        if self._document_bytes is None:
            raise RuntimeError("No runtime document bytes are attached to this ScanRequestV1")
        return self._document_bytes

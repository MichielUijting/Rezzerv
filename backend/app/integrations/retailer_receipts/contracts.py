"""
Technical Design Reference:
- TD Section: TD-03 Receipt ingestion en parsers
- Module Role: Structured retailer receipt import contract
- Runtime Type: production
- Used By: retailer receipt API and scanner adapter
- Depends On: Pydantic
- Reads Data: no
- Writes Data: no
- Status Authority: no
- Refactor Status: keep
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RETAILER_RECEIPT_MIME = "application/vnd.inhuis.retailer-receipt+json"
SUPPORTED_RETAILER_PROVIDERS = ("ah", "jumbo", "lidl")
RetailerProviderCode = Literal["ah", "jumbo", "lidl"]


class RetailerReceiptEnvelope(BaseModel):
    """Portable raw-provider envelope.

    Authentication material is deliberately outside this contract. A provider
    connector may fetch a receipt, but only the receipt observation enters the
    Inhuis receipt pipeline.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    provider: RetailerProviderCode
    external_receipt_id: str = Field(min_length=1, max_length=240)
    receipt: dict[str, Any]

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != "1.0":
            raise ValueError("Only retailer receipt envelope schema_version 1.0 is supported")
        return value

    def stable_json_bytes(self) -> bytes:
        return self.model_dump_json(
            exclude_none=True,
            by_alias=True,
        ).encode("utf-8")

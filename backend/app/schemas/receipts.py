"""
Technical Design Reference:
- TD Section: TD-05 Datastore en services
- Module Role: Backend application module
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class ReceiptDeleteRequest(BaseModel):
    receipt_table_ids: List[str] = Field(default_factory=list)


class ReceiptPurgeArchivedRequest(BaseModel):
    household_id: str


class ReceiptHeaderUpdateRequest(BaseModel):
    store_name: Optional[str] = None
    purchase_at: Optional[str] = None
    total_amount: Optional[float] = None
    reference: Optional[str] = None
    notes: Optional[str] = None


class ReceiptLineUpdateRequest(BaseModel):
    article_name: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    line_total: Optional[float] = None
    matched_article_id: Optional[str] = None
    is_validated: Optional[bool] = None
    is_deleted: Optional[bool] = None


class ReceiptLineCreateRequest(BaseModel):
    article_name: str
    quantity: Optional[float] = 1.0
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    line_total: Optional[float] = None
    matched_article_id: Optional[str] = None
    is_validated: bool = True

    @field_validator('article_name')
    @classmethod
    def validate_article_name(cls, value):
        normalized = ' '.join(str(value or '').strip().split())
        if not normalized:
            raise ValueError('Artikelnaam is verplicht')
        if len(normalized) > 180:
            raise ValueError('Artikelnaam mag maximaal 180 tekens bevatten')
        return normalized

from __future__ import annotations

from typing import Optional

from fastapi import Query
from pydantic import BaseModel, Field

from app import external_product_index_api as product_index_api
from app.services.external_database_matchers import (
    get_external_database_configuration,
    match_retailer_receipt_line,
)

app = product_index_api.app


class RetailerMatchPreviewRequest(BaseModel):
    receipt_line_text: str = Field(..., min_length=1, max_length=255)
    include_below_threshold: bool = True


@app.get("/api/external-databases/config")
def get_external_databases_config():
    return get_external_database_configuration()


@app.post("/api/external-databases/retailers/{retailer_code}/match-preview")
def preview_external_database_retailer_match(retailer_code: str, payload: RetailerMatchPreviewRequest):
    return match_retailer_receipt_line(
        retailer_code=retailer_code,
        receipt_line_text=payload.receipt_line_text,
        include_below_threshold=payload.include_below_threshold,
    )


@app.get("/api/external-databases/retailers/{retailer_code}/match-preview")
def preview_external_database_retailer_match_get(
    retailer_code: str,
    q: str = Query(..., min_length=1, max_length=255),
    include_below_threshold: Optional[bool] = Query(default=True),
):
    return match_retailer_receipt_line(
        retailer_code=retailer_code,
        receipt_line_text=q,
        include_below_threshold=bool(include_below_threshold),
    )

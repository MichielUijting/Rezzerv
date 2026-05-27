"""Source-kind routing skeleton for receipt ingestion."""

from __future__ import annotations


def routing_boundary() -> str:
    return 'receipt_ingestion.pipeline.source_router'
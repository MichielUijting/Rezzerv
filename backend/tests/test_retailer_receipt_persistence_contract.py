from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PATH = REPO_ROOT / "backend" / "app" / "services" / "receipt_service.py"


def _source() -> str:
    return SERVICE_PATH.read_text(encoding="utf-8")


def test_retailer_sku_is_persisted_as_external_article_code() -> None:
    source = _source()
    ingest_start = source.index("def ingest_receipt(")
    ingest_end = source.index("def _resolve_reparse_source_payload(", ingest_start)
    ingest = source[ingest_start:ingest_end]

    assert "external_article_code" in ingest
    assert "'external_article_code': line.get('retailer_sku')" in ingest
    assert ":external_article_code" in ingest


def test_reparse_preserves_retailer_sku_as_external_article_code() -> None:
    source = _source()
    start = source.index("def reparse_receipt(")
    end = source.index("def scan_receipt_source(", start)
    block = source[start:end]

    assert "external_article_code" in block
    assert "'external_article_code': line.get('retailer_sku')" in block
    assert ":external_article_code" in block

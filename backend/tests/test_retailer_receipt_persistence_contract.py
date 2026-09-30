from __future__ import annotations

import inspect

from app.services import receipt_service


def test_retailer_sku_is_persisted_as_external_article_code() -> None:
    source = inspect.getsource(receipt_service.ingest_receipt)

    assert "external_article_code" in source
    assert "'external_article_code': line.get('retailer_sku')" in source
    assert ":external_article_code" in source

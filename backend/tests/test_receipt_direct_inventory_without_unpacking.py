from types import SimpleNamespace

from app.services.receipt_direct_inventory_approval_patch import (
    _prepare_receipt_batch_for_direct_inventory,
)


class _Rows:
    def __init__(self, rows=None):
        self._rows = list(rows or [])

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _FakeConnection:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params):
        sql = " ".join(str(statement).split())
        payload = dict(params)
        self.calls.append((sql, payload))
        if sql.startswith(
            "SELECT id, article_name_raw, matched_household_article_id,"
        ):
            return _Rows(
                [
                    {
                        "id": "line-1",
                        "article_name_raw": "Melk",
                        "matched_household_article_id": "article-1",
                        "matched_global_product_id": None,
                        "external_article_code": None,
                        "brand_raw": None,
                    }
                ]
            )
        return _Rows()


def test_direct_kassa_to_inventory_clears_synthetic_direct_target():
    conn = _FakeConnection()
    updated_batches = []
    main_module = SimpleNamespace(
        normalize_household_article_name=lambda value: str(value).strip(),
        ensure_household_article_for_global_product=lambda *args, **kwargs: None,
        ensure_household_article=lambda *args, **kwargs: "article-created",
        update_batch_status=lambda connection, batch_id: updated_batches.append(batch_id),
    )
    configuration = SimpleNamespace(
        location_tracking_level="global",
        unpacking_enabled=False,
    )

    prepared = _prepare_receipt_batch_for_direct_inventory(
        main_module,
        conn,
        batch_id="batch-1",
        household_id="house-1",
        configuration=configuration,
    )

    update_calls = [
        (sql, params)
        for sql, params in conn.calls
        if sql.startswith("UPDATE purchase_import_lines")
    ]
    assert prepared == 1
    assert updated_batches == ["batch-1"]
    assert len(update_calls) == 1

    sql, params = update_calls[0]
    assert "target_location_id = :target_location_id" in sql
    assert "suggested_location_id = NULL" in sql
    assert "location_override_mode = 'cleared'" in sql
    assert params["target_location_id"] is None
    assert params["article_id"] == "article-1"

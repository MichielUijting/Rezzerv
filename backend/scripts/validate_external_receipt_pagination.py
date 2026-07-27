from __future__ import annotations

import json

from app.services.external_receipt_item_read_service import (
    list_external_receipt_items_page_read_only,
)


def main() -> None:
    first = list_external_receipt_items_page_read_only(
        page=1,
        page_size=10,
        sort_key="receiptLineText",
        sort_desc=False,
        filters={"catalogLinked": "all"},
    )
    second = list_external_receipt_items_page_read_only(
        page=2,
        page_size=10,
        sort_key="receiptLineText",
        sort_desc=False,
        filters={"catalogLinked": "all"},
    )

    assert first.get("read_only") is True
    assert second.get("read_only") is True
    assert int(first.get("page") or 0) == 1
    assert int(second.get("page") or 0) == 2
    assert int(first.get("page_size") or 0) == 10
    assert len(first.get("items") or []) <= 10
    assert len(second.get("items") or []) <= 10
    assert int(first.get("total") or 0) == int(second.get("total") or 0)

    first_ids = {
        str(item.get("receipt_item_id") or "")
        for item in first.get("items") or []
        if str(item.get("receipt_item_id") or "")
    }
    second_ids = {
        str(item.get("receipt_item_id") or "")
        for item in second.get("items") or []
        if str(item.get("receipt_item_id") or "")
    }
    assert not first_ids.intersection(second_ids)

    print(
        json.dumps(
            {
                "ok": True,
                "page_1_rows": len(first.get("items") or []),
                "page_2_rows": len(second.get("items") or []),
                "total": int(first.get("total") or 0),
                "projection_mode": first.get("projection_mode"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

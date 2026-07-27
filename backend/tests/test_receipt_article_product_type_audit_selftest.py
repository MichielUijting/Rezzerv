from __future__ import annotations

from sqlalchemy import text

from app.db import engine
from app.services.receipt_article_product_type_audit_service import (
    audit_linked_receipt_article_product_types,
)


def _count(conn, table_name: str) -> int:
    return int(conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar() or 0)


def main() -> None:
    with engine.begin() as conn:
        before = {
            "external_article_product_links": _count(conn, "external_article_product_links"),
            "product_group_memberships": _count(conn, "product_group_memberships"),
            "gpc_product_groups": _count(conn, "gpc_product_groups"),
            "inventory": _count(conn, "inventory"),
            "inventory_events": _count(conn, "inventory_events"),
        }

    result = audit_linked_receipt_article_product_types()

    assert result["ok"] is True
    assert result["read_only"] is True
    assert result["mutates_inventory"] is False
    assert result["display_language"] == "nl"
    assert result["scope"] == "confirmed_external_article_product_links"

    allowed = {
        "complete",
        "missing_global_product",
        "missing_product_type",
        "invalid_product_type",
        "missing_dutch_description",
        "missing_english_description",
    }
    items = result.get("items") or []
    assert all(item.get("status") in allowed for item in items)
    assert result["summary"]["linked_receipt_articles"] == len(items)
    assert result["summary"]["complete"] == sum(1 for item in items if item.get("status") == "complete")
    print("PASS receipt_article_product_type_audit_contract")

    with engine.begin() as conn:
        after = {
            "external_article_product_links": _count(conn, "external_article_product_links"),
            "product_group_memberships": _count(conn, "product_group_memberships"),
            "gpc_product_groups": _count(conn, "gpc_product_groups"),
            "inventory": _count(conn, "inventory"),
            "inventory_events": _count(conn, "inventory_events"),
        }

    assert before == after, {"before": before, "after": after}
    print("PASS receipt_article_product_type_audit_read_only")
    print("RECEIPT_ARTICLE_PRODUCT_TYPE_AUDIT_GREEN")


if __name__ == "__main__":
    main()

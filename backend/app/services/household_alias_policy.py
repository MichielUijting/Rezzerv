from __future__ import annotations

from types import ModuleType
from typing import Any, Callable


_POLICY_MARKER = '_rezzerv_household_alias_policy_installed'


def install_household_alias_policy(main_module: ModuleType) -> None:
    """Keep household custom_name owned by the household, not product enrichment.

    The legacy enrichment helpers also populate/merge custom_name from an enriched
    product title. That conflicts with the Article detail contract where custom_name
    is an optional household alias. We wrap those two legacy helpers at application
    startup so the product title can still enrich product fields, while custom_name
    remains exactly the persisted household value.

    Existing stored aliases are intentionally not migrated: historical automatic and
    user-entered values cannot be distinguished safely after the fact.
    """
    if getattr(main_module, _POLICY_MARKER, False):
        return

    original_apply: Callable[..., Any] = getattr(main_module, 'apply_household_article_defaults_from_enrichment')
    original_merge: Callable[..., dict] = getattr(main_module, 'merge_household_article_details_with_product_defaults')
    text = getattr(main_module, 'text')

    def apply_without_household_alias(conn, household_article_id: str | None, enrichment: dict | None):
        normalized_article_id = str(household_article_id or '').strip()
        original_alias = None
        alias_row_found = False
        if normalized_article_id:
            row = conn.execute(
                text('SELECT custom_name FROM household_articles WHERE id = :household_article_id LIMIT 1'),
                {'household_article_id': normalized_article_id},
            ).mappings().first()
            if row is not None:
                alias_row_found = True
                original_alias = row.get('custom_name')

        result = original_apply(conn, household_article_id, enrichment)

        if normalized_article_id and alias_row_found:
            conn.execute(
                text('UPDATE household_articles SET custom_name = :custom_name WHERE id = :household_article_id'),
                {
                    'custom_name': original_alias,
                    'household_article_id': normalized_article_id,
                },
            )
        return result

    def merge_without_household_alias(row: dict, product_details: dict | None) -> dict:
        merged = dict(original_merge(row, product_details) or {})
        merged['custom_name'] = (row or {}).get('custom_name')
        return merged

    apply_without_household_alias.__name__ = original_apply.__name__
    merge_without_household_alias.__name__ = original_merge.__name__
    main_module.apply_household_article_defaults_from_enrichment = apply_without_household_alias
    main_module.merge_household_article_details_with_product_defaults = merge_without_household_alias
    setattr(main_module, _POLICY_MARKER, True)

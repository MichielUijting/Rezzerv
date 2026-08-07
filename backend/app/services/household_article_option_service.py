"""Canonical household-article options for Uitpakken.

Slice 2B2 contract:
- household_articles.id is the sole functional identity;
- results are scoped to one active household;
- inventory names, mock ids and live:: aliases are never emitted;
- optional location defaults remain presentation metadata only.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import inspect, text


def _column_names(conn, table_name: str) -> set[str]:
    inspector = inspect(conn)
    if table_name not in inspector.get_table_names():
        return set()
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def _decode_setting(value: Any) -> str:
    if value is None:
        return ""
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = value
    return str(parsed or "").strip()


def _location_defaults(conn, article_ids: list[str]) -> dict[str, dict[str, str]]:
    if not article_ids:
        return {}
    columns = _column_names(conn, "household_article_settings")
    required = {"household_article_id", "setting_key", "setting_value"}
    if not required.issubset(columns):
        return {}

    placeholders = ", ".join(f":article_{index}" for index, _ in enumerate(article_ids))
    params = {f"article_{index}": article_id for index, article_id in enumerate(article_ids)}
    rows = conn.execute(
        text(
            f"""
            SELECT household_article_id, setting_key, setting_value
            FROM household_article_settings
            WHERE household_article_id IN ({placeholders})
              AND setting_key IN ('default_location_id', 'default_sublocation_id')
            """
        ),
        params,
    ).mappings().all()

    result: dict[str, dict[str, str]] = {}
    for row in rows:
        article_id = str(row.get("household_article_id") or "").strip()
        setting_key = str(row.get("setting_key") or "").strip()
        if not article_id or setting_key not in {"default_location_id", "default_sublocation_id"}:
            continue
        result.setdefault(article_id, {})[setting_key] = _decode_setting(row.get("setting_value"))
    return result


def list_canonical_household_article_options(conn, household_id: str, query: str | None = None) -> list[dict[str, Any]]:
    normalized_household_id = str(household_id or "").strip()
    if not normalized_household_id:
        raise ValueError("Actief huishouden ontbreekt")

    columns = _column_names(conn, "household_articles")
    required = {"id", "household_id", "naam"}
    if not required.issubset(columns):
        raise RuntimeError("household_articles-schema mist canonieke identiteitskolommen")

    article_group_expression = "article_group_id" if "article_group_id" in columns else "NULL"
    brand_expression = "brand_or_maker" if "brand_or_maker" in columns else "NULL"
    consumable_expression = "consumable" if "consumable" in columns else "NULL"

    active_conditions = []
    if "status" in columns:
        active_conditions.append("lower(trim(COALESCE(status, 'active'))) = 'active'")
    if "active" in columns:
        active_conditions.append("COALESCE(active, 1) = 1")
    active_clause = ""
    if active_conditions:
        active_clause = " AND " + " AND ".join(active_conditions)

    rows = conn.execute(
        text(
            f"""
            SELECT
                id,
                naam,
                {article_group_expression} AS article_group_id,
                {brand_expression} AS brand,
                {consumable_expression} AS consumable
            FROM household_articles
            WHERE household_id = :household_id
              AND trim(COALESCE(naam, '')) <> ''
              {active_clause}
            ORDER BY lower(naam) ASC, id ASC
            """
        ),
        {"household_id": normalized_household_id},
    ).mappings().all()

    article_ids = [str(row.get("id") or "").strip() for row in rows if str(row.get("id") or "").strip()]
    defaults = _location_defaults(conn, article_ids)
    normalized_query = str(query or "").strip().lower()

    items: list[dict[str, Any]] = []
    for row in rows:
        article_id = str(row.get("id") or "").strip()
        article_name = str(row.get("naam") or "").strip()
        brand = str(row.get("brand") or "").strip()
        if not article_id or not article_name:
            continue
        if article_id.startswith("live::"):
            raise RuntimeError("Niet-canonieke live::-identiteit aangetroffen in household_articles.id")
        if normalized_query and normalized_query not in f"{article_name} {brand}".lower():
            continue
        article_defaults = defaults.get(article_id, {})
        items.append(
            {
                "id": article_id,
                "household_article_id": article_id,
                "name": article_name,
                "article_group_id": row.get("article_group_id"),
                "brand": brand,
                "consumable": bool(row.get("consumable")) if row.get("consumable") is not None else None,
                "default_location_id": article_defaults.get("default_location_id") or "",
                "default_sublocation_id": article_defaults.get("default_sublocation_id") or "",
            }
        )

    return items

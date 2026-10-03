from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import inspect, text, bindparam
from sqlalchemy.engine import Connection


def _tables(conn: Connection) -> set[str]:
    return set(inspect(conn).get_table_names())


def _active_clause(conn: Connection, alias: str) -> str:
    if conn.dialect.name == "postgresql":
        return f"COALESCE({alias}.active, TRUE) IS TRUE"
    return f"COALESCE({alias}.active, 1) = 1"


def _normalize_ids(values: Iterable[Any]) -> list[str]:
    return sorted({
        str(value or "").strip()
        for value in values
        if str(value or "").strip()
    })


def _row_payload(row: Any) -> dict[str, str]:
    return {
        "gpc_brick_code": str(row.get("gpc_brick_code") or "").strip(),
        "gpc_brick_name": str(row.get("gpc_brick_name") or "").strip(),
        "gpc_class_code": str(row.get("gpc_class_code") or "").strip(),
        "gpc_class_name": str(row.get("gpc_class_name") or "").strip(),
        "gpc_family_code": str(row.get("gpc_family_code") or "").strip(),
        "gpc_family_name": str(row.get("gpc_family_name") or "").strip(),
        "gpc_segment_code": str(row.get("gpc_segment_code") or "").strip(),
        "gpc_segment_name": str(row.get("gpc_segment_name") or "").strip(),
    }


def dutch_gpc_by_global_product(
    conn: Connection,
    global_product_ids: Iterable[Any],
) -> dict[str, dict[str, str]]:
    ids = _normalize_ids(global_product_ids)
    required = {"global_product_gpc_bricks", "gpc_product_groups"}
    if not ids or not required.issubset(_tables(conn)):
        return {}

    rows = conn.execute(
        text(f"""
            SELECT
                CAST(a.global_product_id AS TEXT) AS global_product_id,
                nl.gpc_brick_code,
                nl.gpc_brick_name,
                nl.gpc_class_code,
                nl.gpc_class_name,
                nl.gpc_family_code,
                nl.gpc_family_name,
                nl.gpc_segment_code,
                nl.gpc_segment_name
            FROM global_product_gpc_bricks a
            JOIN gpc_product_groups nl
              ON nl.gpc_brick_code = a.brick_code
             AND lower(COALESCE(nl.language_code, '')) = 'nl'
             AND {_active_clause(conn, 'nl')}
            WHERE CAST(a.global_product_id AS TEXT) IN :global_product_ids
        """).bindparams(bindparam("global_product_ids", expanding=True)),
        {"global_product_ids": ids},
    ).mappings().all()

    return {
        str(row.get("global_product_id") or "").strip(): _row_payload(row)
        for row in rows
        if str(row.get("global_product_id") or "").strip()
    }


def dutch_gpc_by_household_article(
    conn: Connection,
    household_id: str,
    household_article_ids: Iterable[Any],
) -> dict[str, dict[str, str]]:
    ids = _normalize_ids(household_article_ids)
    required = {"household_articles", "global_product_gpc_bricks", "gpc_product_groups"}
    if not ids or not required.issubset(_tables(conn)):
        return {}

    rows = conn.execute(
        text(f"""
            SELECT
                CAST(ha.id AS TEXT) AS household_article_id,
                nl.gpc_brick_code,
                nl.gpc_brick_name,
                nl.gpc_class_code,
                nl.gpc_class_name,
                nl.gpc_family_code,
                nl.gpc_family_name,
                nl.gpc_segment_code,
                nl.gpc_segment_name
            FROM household_articles ha
            JOIN global_product_gpc_bricks a
              ON a.global_product_id = ha.global_product_id
            JOIN gpc_product_groups nl
              ON nl.gpc_brick_code = a.brick_code
             AND lower(COALESCE(nl.language_code, '')) = 'nl'
             AND {_active_clause(conn, 'nl')}
            WHERE ha.household_id = :household_id
              AND CAST(ha.id AS TEXT) IN :household_article_ids
        """).bindparams(bindparam("household_article_ids", expanding=True)),
        {
            "household_id": str(household_id),
            "household_article_ids": ids,
        },
    ).mappings().all()

    return {
        str(row.get("household_article_id") or "").strip(): _row_payload(row)
        for row in rows
        if str(row.get("household_article_id") or "").strip()
    }

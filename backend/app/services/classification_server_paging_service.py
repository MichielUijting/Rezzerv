"""Read-only, server-side Catalogus workqueue paging and CSV export.

Only canonical global_product IDs are selected by filters/sort. GPC/CBS and
confirmed retailer/synonym relationships are projected for the selected eight
identities, never for the whole Catalogus at first paint.
"""
from __future__ import annotations

import csv
from io import StringIO

from sqlalchemy import bindparam, text

from app.services.article_workqueue_service import (
    CLASSIFICATION_SQL, project_classification_tasks,
)

PAGE_SIZE = 8
MAX_EXPORT_IDS = 20000
_FILTER_KEYS = ("name", "gtin", "gpc_status", "cbs_status")
_SORT_KEYS = _FILTER_KEYS
_NAME = (
    "COALESCE(gp.name, '') || CASE WHEN NULLIF(TRIM(COALESCE(gp.brand, '')), '') "
    "IS NOT NULL THEN ' · ' || gp.brand ELSE '' END"
)
_GTIN = "COALESCE(gp.primary_gtin, '')"
_GPC = (
    "(SELECT NULLIF(TRIM(gpc.brick_code), '') "
    "FROM global_product_gpc_bricks gpc "
    "WHERE gpc.global_product_id = gp.id)"
)
_CBS = (
    "(SELECT CASE WHEN cbs.is_active THEN "
    "NULLIF(TRIM(COALESCE(cbs.cbs_code, '')), '') || ' ' || COALESCE(ref.name_nl, '') "
    "ELSE NULL END "
    "FROM global_product_cbs_classifications cbs "
    "LEFT JOIN cbs_ecoicop_categories ref "
    "ON ref.cbs_code = cbs.cbs_code AND ref.reference_version = cbs.reference_version "
    "WHERE cbs.global_product_id = gp.id)"
)
_EXPRESSIONS = {
    "name": _NAME,
    "gtin": _GTIN,
    "gpc_status": f"COALESCE({_GPC}, 'Niet geclassificeerd')",
    "cbs_status": f"COALESCE({_CBS}, 'Niet geclassificeerd')",
}
_CLASSIFIED_SQL_NEEDLE = (
    "         ORDER BY LOWER(gp.name), gp.id\n"
    "         LIMIT :limit OFFSET :offset"
)
if CLASSIFICATION_SQL.count(_CLASSIFIED_SQL_NEEDLE) != 1:
    raise RuntimeError("Classificatieprojectie is veranderd; gecontroleerde selectie is vereist.")
_SELECTED_PROJECTION_SQL = CLASSIFICATION_SQL.replace(
    _CLASSIFIED_SQL_NEEDLE,
    "           AND gp.id IN :product_ids\n"
    "         ORDER BY LOWER(gp.name), gp.id",
)
_EXPORT_FIELDS = (
    ("id", "product_id"),
    ("name", "Artikel"),
    ("brand", "Merk"),
    ("gtin", "Barcode"),
    ("gpc_code", "GS1 GPC code"),
    ("cbs_code", "CBS ECOICOPv2 code"),
    ("cbs_name", "CBS omschrijving"),
    ("cbs_reference_version", "CBS referentieversie"),
    ("gpc_status", "GS1 status"),
    ("cbs_status", "CBS status"),
)


def _filter_sql(filters: dict[str, str]) -> tuple[str, dict]:
    conditions = ["LOWER(COALESCE(gp.status, '')) <> 'deleted'"]
    params = {}
    for key in _FILTER_KEYS:
        value = str(filters.get(key) or "").strip().lower()
        if not value:
            continue
        expression = _EXPRESSIONS[key]
        if value == "=leeg":
            conditions.append(f"NULLIF(TRIM({expression}), '') IS NULL")
        elif value == "=nietleeg":
            conditions.append(f"NULLIF(TRIM({expression}), '') IS NOT NULL")
        else:
            safe = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append(f"LOWER({expression}) LIKE :filter_{key} ESCAPE '\\'")
            params[f"filter_{key}"] = f"%{safe}%"
    return " AND ".join(conditions), params


def _order_sql(sort_key: str, direction: str) -> str:
    if sort_key not in _SORT_KEYS or direction not in ("asc", "desc"):
        raise ValueError("Ongeldige sorteervolgorde.")
    return f"LOWER({_EXPRESSIONS[sort_key]}) {direction.upper()}, gp.id ASC"


def _select_filtered_ids(
    conn, *, filters: dict[str, str], sort_key: str, direction: str,
    offset: int, limit: int,
) -> tuple[list[str], int]:
    if offset < 0 or not 1 <= limit <= 1000:
        raise ValueError("Ongeldige paginering.")
    where, params = _filter_sql(filters)
    order = _order_sql(sort_key, direction)
    total = int(conn.execute(text(
        f"SELECT COUNT(*) FROM global_products gp WHERE {where}"
    ), params).scalar_one())
    ids = conn.execute(text(
        f"SELECT gp.id FROM global_products gp WHERE {where} "
        f"ORDER BY {order} LIMIT :limit OFFSET :offset"
    ), {**params, "limit": limit, "offset": offset}).scalars().all()
    return [str(value) for value in ids], total


def _project_ids(conn, product_ids: list[str]) -> tuple[list[dict], list[dict]]:
    if not product_ids:
        return [], []
    rows = conn.execute(
        text(_SELECTED_PROJECTION_SQL).bindparams(bindparam("product_ids", expanding=True)),
        {"product_ids": product_ids},
    ).mappings().all()
    items, tasks = project_classification_tasks(rows)
    by_id = {item["id"]: item for item in items}
    if len(by_id) != len(product_ids) or set(by_id) != set(product_ids):
        raise ValueError("Catalogusidentiteiten zijn tijdens paginering gewijzigd.")
    # SQL-enrichment is returned in the canonical global sort, while the
    # requested page may use any permitted column sort direction.
    return [by_id[pid] for pid in product_ids], tasks


def load_server_classification_page(
    conn, *, offset: int = 0, limit: int = PAGE_SIZE,
    sort_key: str = "name", direction: str = "asc",
    filters: dict[str, str] | None = None,
) -> dict:
    if not 1 <= limit <= PAGE_SIZE:
        raise ValueError("Maximaal acht artikelen per pagina.")
    filters = filters or {}
    ids, total = _select_filtered_ids(
        conn, filters=filters, sort_key=sort_key, direction=direction,
        offset=offset, limit=limit,
    )
    items, tasks = _project_ids(conn, ids)
    return {
        "items": items, "tasks": tasks, "total": total,
        "offset": offset, "limit": limit,
        "task_count_scope": "page", "product_count_scope": "filtered",
    }


def load_server_classification_ids(
    conn, *, offset: int = 0, limit: int = 1000,
    filters: dict[str, str] | None = None,
) -> dict:
    ids, total = _select_filtered_ids(
        conn, filters=filters or {}, sort_key="name", direction="asc",
        offset=offset, limit=limit,
    )
    return {"ids": ids, "total": total, "offset": offset, "limit": limit}


def load_classification_counts(conn) -> dict:
    """Global totals, independent of the paged list and its active filters."""
    sql = """
    SELECT COUNT(*) AS product_total,
           COALESCE(SUM(CASE WHEN NULLIF(TRIM(COALESCE(gpc.brick_code, '')), '')
                             IS NULL THEN 1 ELSE 0 END), 0)
         + COALESCE(SUM(CASE WHEN cbs.is_active
                              AND NULLIF(TRIM(COALESCE(cbs.cbs_code, '')), '')
                                  IS NOT NULL
                             THEN 0 ELSE 1 END), 0) AS task_total
    FROM global_products gp
    LEFT JOIN global_product_gpc_bricks gpc ON gpc.global_product_id = gp.id
    LEFT JOIN global_product_cbs_classifications cbs
           ON cbs.global_product_id = gp.id
    WHERE LOWER(COALESCE(gp.status, '')) <> 'deleted'
    """
    result = conn.execute(text(sql)).mappings().one()
    return {
        "product_total": int(result["product_total"] or 0),
        "task_total": int(result["task_total"] or 0),
        "task_count_scope": "global",
        "product_count_scope": "global",
    }


def _safe_csv_value(value) -> str:
    result = str(value if value is not None else "")
    if result.lstrip().startswith(("=", "+", "@", "-")):
        result = "'" + result
    return result


def build_selected_classification_csv(conn, product_ids: list[str]) -> bytes:
    """Explicit-only export. No client-controlled SQL; no household/receipt data."""
    if not product_ids or len(product_ids) > MAX_EXPORT_IDS:
        raise ValueError("Selecteer 1 tot maximaal 20.000 Catalogusartikelen.")
    if any(not isinstance(pid, str) or not pid or len(pid) > 200 for pid in product_ids):
        raise ValueError("Ongeldige Catalogusidentiteit.")
    if len(set(product_ids)) != len(product_ids):
        raise ValueError("Dubbele Catalogusidentiteit in exportselectie.")

    output = StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n", quoting=csv.QUOTE_ALL)
    writer.writerow([title for _, title in _EXPORT_FIELDS])
    for start in range(0, len(product_ids), 100):
        chunk = product_ids[start:start + 100]
        items, _ = _project_ids(conn, chunk)
        for item in items:
            writer.writerow([
                _safe_csv_value(
                    ("Geclassificeerd" if item.get(field) == "classified"
                     else "Niet geclassificeerd")
                    if field in ("gpc_status", "cbs_status")
                    else item.get(field)
                )
                for field, _ in _EXPORT_FIELDS
            ])
    return ("\ufeff" + output.getvalue()).encode("utf-8")

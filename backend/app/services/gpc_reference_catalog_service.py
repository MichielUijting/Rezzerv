from __future__ import annotations

import re
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection


_GPC_CODE = re.compile(r"^\d{8}$")


def _tables(conn: Connection) -> set[str]:
    return set(inspect(conn).get_table_names())


def _active_clause(conn: Connection, alias: str) -> str:
    if conn.dialect.name == "postgresql":
        return f"COALESCE({alias}.active, TRUE) IS TRUE"
    return f"COALESCE({alias}.active, 1) = 1"


def _valid_hierarchy(row: dict[str, Any]) -> bool:
    return all(
        _GPC_CODE.fullmatch(str(row.get(key) or "").strip())
        for key in ("brick_code", "class_code", "family_code", "segment_code")
    )


def _nl_select_sql(conn: Connection, *, where: str = "", limit: bool = False) -> str:
    active_sql = _active_clause(conn, "gpg")
    limit_sql = " LIMIT :limit" if limit else ""
    return f"""
        SELECT
            gpg.gpc_brick_code AS brick_code,
            gpg.gpc_brick_name AS brick_description,
            gpg.gpc_class_code AS class_code,
            gpg.gpc_class_name AS class_description,
            gpg.gpc_family_code AS family_code,
            gpg.gpc_family_name AS family_description,
            gpg.gpc_segment_code AS segment_code,
            gpg.gpc_segment_name AS segment_description,
            'gs1_gpc_nl' AS reference_source
        FROM gpc_product_groups gpg
        WHERE lower(COALESCE(gpg.language_code, '')) = 'nl'
          AND {active_sql}
          AND trim(COALESCE(gpg.gpc_brick_name, '')) <> ''
          AND trim(COALESCE(gpg.gpc_class_name, '')) <> ''
          AND trim(COALESCE(gpg.gpc_family_name, '')) <> ''
          AND trim(COALESCE(gpg.gpc_segment_name, '')) <> ''
          {where}
        ORDER BY gpg.gpc_brick_name, gpg.gpc_brick_code
        {limit_sql}
    """


def _product_group_row(conn: Connection, brick_code: str) -> dict[str, Any] | None:
    if "gpc_product_groups" not in _tables(conn):
        return None
    rows = conn.execute(
        text(_nl_select_sql(conn, where="AND gpg.gpc_brick_code = :brick_code", limit=True)),
        {"brick_code": str(brick_code or "").strip(), "limit": 1},
    ).mappings().all()
    if not rows:
        return None
    row = dict(rows[0])
    return row if _valid_hierarchy(row) else None


def _canonical_brick_row(conn: Connection, brick_code: str) -> dict[str, Any] | None:
    # Gebruikerszichtbare GPC-labels komen uitsluitend uit de officiële
    # Nederlandse GS1-publicatie die in gpc_product_groups is geïmporteerd.
    return _product_group_row(conn, brick_code)


def bundled_official_gpc_bricks() -> list[dict[str, Any]]:
    """Compatibiliteitsfunctie.

    Een gebundelde Engelstalige fallback wordt bewust niet meer gebruikt.
    Nederlandse GS1-referentiedata is verplicht voor gebruikerszichtbare GPC.
    """
    return []


def list_official_gpc_bricks(conn: Connection) -> list[dict[str, Any]]:
    if "gpc_product_groups" not in _tables(conn):
        return []
    return [
        dict(row)
        for row in conn.execute(text(_nl_select_sql(conn))).mappings().all()
        if _valid_hierarchy(dict(row))
    ]


def ensure_official_gpc_brick(conn: Connection, brick_code: str) -> dict[str, Any] | None:
    code = str(brick_code or "").strip()
    if not _GPC_CODE.fullmatch(code):
        return None

    dutch = _product_group_row(conn, code)
    if not dutch:
        return None

    tables = _tables(conn)
    required = {"gpc_segments", "gpc_families", "gpc_classes", "gpc_bricks"}
    if not required.issubset(tables):
        return None

    params = {
        "segment_code": dutch["segment_code"],
        "segment_description": str(dutch["segment_description"]).strip(),
        "family_code": dutch["family_code"],
        "family_description": str(dutch["family_description"]).strip(),
        "class_code": dutch["class_code"],
        "class_description": str(dutch["class_description"]).strip(),
        "brick_code": dutch["brick_code"],
        "brick_description": str(dutch["brick_description"]).strip(),
    }
    conn.execute(text("""
        INSERT INTO gpc_segments (segment_code, description)
        VALUES (:segment_code, :segment_description)
        ON CONFLICT(segment_code) DO NOTHING
    """), params)
    conn.execute(text("""
        INSERT INTO gpc_families (family_code, description, segment_code)
        VALUES (:family_code, :family_description, :segment_code)
        ON CONFLICT(family_code) DO NOTHING
    """), params)
    conn.execute(text("""
        INSERT INTO gpc_classes (class_code, description, family_code)
        VALUES (:class_code, :class_description, :family_code)
        ON CONFLICT(class_code) DO NOTHING
    """), params)
    conn.execute(text("""
        INSERT INTO gpc_bricks (brick_code, description, class_code)
        VALUES (:brick_code, :brick_description, :class_code)
        ON CONFLICT(brick_code) DO NOTHING
    """), params)
    return dutch


def search_official_gpc_bricks(
    conn: Connection,
    *,
    query: str = "",
    limit: int = 25,
) -> list[dict[str, Any]]:
    if "gpc_product_groups" not in _tables(conn):
        return []

    normalized = " ".join(str(query or "").strip().split()).lower()
    max_rows = max(1, min(int(limit), 100))
    params: dict[str, Any] = {"limit": max_rows}
    where = ""
    if normalized:
        params["query"] = f"%{normalized}%"
        where = """
          AND (
            lower(gpg.gpc_brick_code) LIKE :query
            OR lower(gpg.gpc_brick_name) LIKE :query
            OR lower(gpg.gpc_class_name) LIKE :query
            OR lower(gpg.gpc_family_name) LIKE :query
            OR lower(gpg.gpc_segment_name) LIKE :query
          )
        """

    return [
        dict(row)
        for row in conn.execute(
            text(_nl_select_sql(conn, where=where, limit=True)),
            params,
        ).mappings().all()
        if _valid_hierarchy(dict(row))
    ]

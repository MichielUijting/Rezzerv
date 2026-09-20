from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection


_GPC_CODE = re.compile(r"^\d{8}$")
_BUNDLED_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "gpc_bricks_2026_05_en.json"
_BUNDLED_REFERENCE_SOURCE = "bundled_gpc_2026_05_en"


def _tables(conn: Connection) -> set[str]:
    return set(inspect(conn).get_table_names())


def _active_clause(conn: Connection, alias: str) -> str:
    if conn.dialect.name == "postgresql":
        return f"COALESCE({alias}.active, TRUE) IS TRUE"
    return f"COALESCE({alias}.active, 1) = 1"


def _canonical_brick_row(conn: Connection, brick_code: str) -> dict[str, Any] | None:
    tables = _tables(conn)
    required = {"gpc_bricks", "gpc_classes", "gpc_families", "gpc_segments"}
    if not required.issubset(tables):
        return None
    has_translations = "gpc_translations" in tables
    brick_label = (
        "COALESCE((SELECT translated_text FROM gpc_translations tr "
        "WHERE tr.entity_type='brick' AND tr.entity_code=b.brick_code "
        "AND tr.language_code='nl' LIMIT 1), b.description)"
        if has_translations else "b.description"
    )
    class_label = (
        "COALESCE((SELECT translated_text FROM gpc_translations tr "
        "WHERE tr.entity_type='class' AND tr.entity_code=c.class_code "
        "AND tr.language_code='nl' LIMIT 1), c.description)"
        if has_translations else "c.description"
    )
    family_label = (
        "COALESCE((SELECT translated_text FROM gpc_translations tr "
        "WHERE tr.entity_type='family' AND tr.entity_code=f.family_code "
        "AND tr.language_code='nl' LIMIT 1), f.description)"
        if has_translations else "f.description"
    )
    segment_label = (
        "COALESCE((SELECT translated_text FROM gpc_translations tr "
        "WHERE tr.entity_type='segment' AND tr.entity_code=s.segment_code "
        "AND tr.language_code='nl' LIMIT 1), s.description)"
        if has_translations else "s.description"
    )
    row = conn.execute(text(f"""
        SELECT
            b.brick_code,
            {brick_label} AS brick_description,
            b.description AS brick_description_en,
            c.class_code,
            {class_label} AS class_description,
            f.family_code,
            {family_label} AS family_description,
            s.segment_code,
            {segment_label} AS segment_description,
            'gpc_bricks' AS reference_source
        FROM gpc_bricks b
        JOIN gpc_classes c ON c.class_code = b.class_code
        JOIN gpc_families f ON f.family_code = c.family_code
        JOIN gpc_segments s ON s.segment_code = f.segment_code
        WHERE b.brick_code = :brick_code
        LIMIT 1
    """), {"brick_code": brick_code}).mappings().first()
    return dict(row) if row else None


def _product_group_row(conn: Connection, brick_code: str) -> dict[str, Any] | None:
    if "gpc_product_groups" not in _tables(conn):
        return None
    active_sql = _active_clause(conn, "gpg")
    row = conn.execute(text(f"""
        SELECT
            gpg.gpc_brick_code AS brick_code,
            COALESCE(NULLIF(gpg.gpc_brick_name, ''), NULLIF(gpg.gpc_brick_name_en, ''), gpg.gpc_brick_code) AS brick_description,
            COALESCE(NULLIF(gpg.gpc_brick_name_en, ''), NULLIF(gpg.gpc_brick_name, ''), gpg.gpc_brick_code) AS brick_description_en,
            gpg.gpc_class_code AS class_code,
            COALESCE(NULLIF(gpg.gpc_class_name, ''), NULLIF(gpg.gpc_class_name_en, ''), gpg.gpc_class_code) AS class_description,
            gpg.gpc_family_code AS family_code,
            COALESCE(NULLIF(gpg.gpc_family_name, ''), NULLIF(gpg.gpc_family_name_en, ''), gpg.gpc_family_code) AS family_description,
            gpg.gpc_segment_code AS segment_code,
            COALESCE(NULLIF(gpg.gpc_segment_name, ''), NULLIF(gpg.gpc_segment_name_en, ''), gpg.gpc_segment_code) AS segment_description,
            'gpc_product_groups' AS reference_source
        FROM gpc_product_groups gpg
        WHERE gpg.gpc_brick_code = :brick_code
          AND {active_sql}
        LIMIT 1
    """), {"brick_code": brick_code}).mappings().first()
    return dict(row) if row else None


def _valid_hierarchy(row: dict[str, Any]) -> bool:
    return all(
        _GPC_CODE.fullmatch(str(row.get(key) or "").strip())
        for key in ("brick_code", "class_code", "family_code", "segment_code")
    )


def _bundled_row(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "brick_code": str(raw.get("gpc_brick_code") or "").strip(),
        "brick_description": str(raw.get("gpc_brick_name_en") or "").strip(),
        "brick_description_en": str(raw.get("gpc_brick_name_en") or "").strip(),
        "class_code": str(raw.get("gpc_class_code") or "").strip(),
        "class_description": str(raw.get("gpc_class_name_en") or "").strip(),
        "family_code": str(raw.get("gpc_family_code") or "").strip(),
        "family_description": str(raw.get("gpc_family_name_en") or "").strip(),
        "segment_code": str(raw.get("gpc_segment_code") or "").strip(),
        "segment_description": str(raw.get("gpc_segment_name_en") or "").strip(),
        "reference_source": _BUNDLED_REFERENCE_SOURCE,
    }


@lru_cache(maxsize=1)
def _bundled_rows() -> tuple[dict[str, Any], ...]:
    try:
        payload = json.loads(_BUNDLED_DATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    rows: list[dict[str, Any]] = []
    for raw in payload.get("bricks") or []:
        if not isinstance(raw, dict):
            continue
        row = _bundled_row(raw)
        if _valid_hierarchy(row) and row.get("brick_description"):
            rows.append(row)
    return tuple(rows)


@lru_cache(maxsize=1)
def _bundled_by_code() -> dict[str, dict[str, Any]]:
    return {str(row["brick_code"]): row for row in _bundled_rows()}


def _bundled_brick_row(brick_code: str) -> dict[str, Any] | None:
    row = _bundled_by_code().get(str(brick_code or "").strip())
    return dict(row) if row else None


def bundled_official_gpc_bricks() -> list[dict[str, Any]]:
    """Return the complete bundled official GPC fallback catalog.

    Callers receive copies so candidate ranking can add transient scoring fields
    without mutating the cached reference rows.
    """

    return [dict(row) for row in _bundled_rows()]


def list_official_gpc_bricks(conn: Connection) -> list[dict[str, Any]]:
    """Return the complete read-only official GPC reference for candidate ranking."""
    tables = _tables(conn)
    rows: list[dict[str, Any]] = []
    known: set[str] = set()
    required = {"gpc_bricks", "gpc_classes", "gpc_families", "gpc_segments"}
    if required.issubset(tables):
        has_translations = "gpc_translations" in tables
        has_product_groups = "gpc_product_groups" in tables
        brick_sources = []
        class_sources = []
        family_sources = []
        segment_sources = []
        if has_translations:
            brick_sources.append("(SELECT translated_text FROM gpc_translations tr WHERE tr.entity_type='brick' AND tr.entity_code=b.brick_code AND tr.language_code='nl' LIMIT 1)")
            class_sources.append("(SELECT translated_text FROM gpc_translations tr WHERE tr.entity_type='class' AND tr.entity_code=c.class_code AND tr.language_code='nl' LIMIT 1)")
            family_sources.append("(SELECT translated_text FROM gpc_translations tr WHERE tr.entity_type='family' AND tr.entity_code=f.family_code AND tr.language_code='nl' LIMIT 1)")
            segment_sources.append("(SELECT translated_text FROM gpc_translations tr WHERE tr.entity_type='segment' AND tr.entity_code=s.segment_code AND tr.language_code='nl' LIMIT 1)")
        if has_product_groups:
            brick_sources.append("(SELECT NULLIF(gpg.gpc_brick_name, '') FROM gpc_product_groups gpg WHERE gpg.gpc_brick_code=b.brick_code AND gpg.language_code='nl' LIMIT 1)")
            class_sources.append("(SELECT NULLIF(gpg.gpc_class_name, '') FROM gpc_product_groups gpg WHERE gpg.gpc_class_code=c.class_code AND gpg.language_code='nl' LIMIT 1)")
            family_sources.append("(SELECT NULLIF(gpg.gpc_family_name, '') FROM gpc_product_groups gpg WHERE gpg.gpc_family_code=f.family_code AND gpg.language_code='nl' LIMIT 1)")
            segment_sources.append("(SELECT NULLIF(gpg.gpc_segment_name, '') FROM gpc_product_groups gpg WHERE gpg.gpc_segment_code=s.segment_code AND gpg.language_code='nl' LIMIT 1)")
        brick_label = f"COALESCE({', '.join([*brick_sources, 'b.description'])})"
        class_label = f"COALESCE({', '.join([*class_sources, 'c.description'])})"
        family_label = f"COALESCE({', '.join([*family_sources, 'f.description'])})"
        segment_label = f"COALESCE({', '.join([*segment_sources, 's.description'])})"
        canonical = conn.execute(text(f"""
            SELECT b.brick_code, {brick_label} AS brick_description,
                   b.description AS brick_description_en,
                   c.class_code, {class_label} AS class_description,
                   f.family_code, {family_label} AS family_description,
                   s.segment_code, {segment_label} AS segment_description,
                   'gpc_bricks' AS reference_source
            FROM gpc_bricks b
            JOIN gpc_classes c ON c.class_code = b.class_code
            JOIN gpc_families f ON f.family_code = c.family_code
            JOIN gpc_segments s ON s.segment_code = f.segment_code
            ORDER BY b.brick_code
        """)).mappings().all()
        for item in canonical:
            row = dict(item)
            code = str(row.get("brick_code") or "")
            if code and _valid_hierarchy(row):
                rows.append(row)
                known.add(code)
    if "gpc_product_groups" in tables:
        active_sql = _active_clause(conn, "gpg")
        fallback = conn.execute(text(f"""
            SELECT gpg.gpc_brick_code AS brick_code,
                   COALESCE(NULLIF(gpg.gpc_brick_name, ''), NULLIF(gpg.gpc_brick_name_en, ''), gpg.gpc_brick_code) AS brick_description,
                   COALESCE(NULLIF(gpg.gpc_brick_name_en, ''), NULLIF(gpg.gpc_brick_name, ''), gpg.gpc_brick_code) AS brick_description_en,
                   gpg.gpc_class_code AS class_code,
                   COALESCE(NULLIF(gpg.gpc_class_name, ''), NULLIF(gpg.gpc_class_name_en, ''), gpg.gpc_class_code) AS class_description,
                   gpg.gpc_family_code AS family_code,
                   COALESCE(NULLIF(gpg.gpc_family_name, ''), NULLIF(gpg.gpc_family_name_en, ''), gpg.gpc_family_code) AS family_description,
                   gpg.gpc_segment_code AS segment_code,
                   COALESCE(NULLIF(gpg.gpc_segment_name, ''), NULLIF(gpg.gpc_segment_name_en, ''), gpg.gpc_segment_code) AS segment_description,
                   'gpc_product_groups' AS reference_source
            FROM gpc_product_groups gpg
            WHERE {active_sql}
            ORDER BY gpg.gpc_brick_code
        """)).mappings().all()
        for item in fallback:
            row = dict(item)
            code = str(row.get("brick_code") or "")
            if code and code not in known and _valid_hierarchy(row):
                rows.append(row)
                known.add(code)
    for bundled in _bundled_rows():
        code = str(bundled.get("brick_code") or "")
        if code and code not in known:
            rows.append(dict(bundled))
            known.add(code)
    rows.sort(key=lambda row: str(row.get("brick_code") or ""))
    return rows


def ensure_official_gpc_brick(conn: Connection, brick_code: str) -> dict[str, Any] | None:
    code = str(brick_code or "").strip()
    if not _GPC_CODE.fullmatch(code):
        return None

    existing = _canonical_brick_row(conn, code)
    if existing:
        return existing

    fallback = _product_group_row(conn, code)
    if not fallback or not _valid_hierarchy(fallback):
        fallback = _bundled_brick_row(code)
    if not fallback or not _valid_hierarchy(fallback):
        return None

    tables = _tables(conn)
    required = {"gpc_segments", "gpc_families", "gpc_classes", "gpc_bricks"}
    if not required.issubset(tables):
        return None

    params = {
        "segment_code": fallback["segment_code"],
        "segment_description": str(fallback.get("segment_description") or fallback["segment_code"]).strip(),
        "family_code": fallback["family_code"],
        "family_description": str(fallback.get("family_description") or fallback["family_code"]).strip(),
        "class_code": fallback["class_code"],
        "class_description": str(fallback.get("class_description") or fallback["class_code"]).strip(),
        "brick_code": fallback["brick_code"],
        "brick_description": str(fallback.get("brick_description_en") or fallback.get("brick_description") or fallback["brick_code"]).strip(),
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
    return _canonical_brick_row(conn, code)


def search_official_gpc_bricks(
    conn: Connection,
    *,
    query: str = "",
    limit: int = 25,
) -> list[dict[str, Any]]:
    normalized = " ".join(str(query or "").strip().split()).lower()
    max_rows = max(1, min(int(limit), 100))
    params: dict[str, Any] = {"limit": max_rows}
    like_where = ""
    if normalized:
        params["query"] = f"%{normalized}%"
        like_where = """
          AND (
            lower(gpg.gpc_brick_code) LIKE :query
            OR lower(COALESCE(gpg.gpc_brick_name, '')) LIKE :query
            OR lower(COALESCE(gpg.gpc_brick_name_en, '')) LIKE :query
            OR lower(COALESCE(gpg.gpc_class_name, '')) LIKE :query
            OR lower(COALESCE(gpg.gpc_class_name_en, '')) LIKE :query
          )
        """

    rows: list[dict[str, Any]] = []
    tables = _tables(conn)
    if {"gpc_bricks", "gpc_classes", "gpc_families", "gpc_segments"}.issubset(tables):
        has_translations = "gpc_translations" in tables
        translation_filter = ""
        if normalized and has_translations:
            translation_filter = """
                OR lower(COALESCE((
                    SELECT translated_text FROM gpc_translations tr
                    WHERE tr.entity_type='brick'
                      AND tr.entity_code=b.brick_code
                      AND tr.language_code='nl'
                    LIMIT 1
                ), '')) LIKE :query
            """
        canonical_where = ""
        if normalized:
            canonical_where = f"""
                WHERE (
                    lower(b.brick_code) LIKE :query
                    OR lower(b.description) LIKE :query
                    {translation_filter}
                )
            """
        canonical = conn.execute(text(f"""
            SELECT b.brick_code
            FROM gpc_bricks b
            {canonical_where}
            ORDER BY b.brick_code
            LIMIT :limit
        """), params).mappings().all()
        for item in canonical:
            row = _canonical_brick_row(conn, str(item["brick_code"]))
            if row:
                rows.append(row)

    known = {str(row.get("brick_code") or "") for row in rows}
    if "gpc_product_groups" in tables:
        active_sql = _active_clause(conn, "gpg")
        fallback_rows = conn.execute(text(f"""
            SELECT gpg.gpc_brick_code
            FROM gpc_product_groups gpg
            WHERE {active_sql}
            {like_where}
            ORDER BY gpg.gpc_brick_code
            LIMIT :limit
        """), params).mappings().all()
        for item in fallback_rows:
            code = str(item.get("gpc_brick_code") or "")
            if code in known:
                continue
            row = _product_group_row(conn, code)
            if row:
                rows.append(row)
                known.add(code)

    for bundled in _bundled_rows():
        code = str(bundled.get("brick_code") or "")
        if code in known:
            continue
        if normalized:
            haystack = " ".join(
                str(bundled.get(key) or "").lower()
                for key in (
                    "brick_code",
                    "brick_description",
                    "brick_description_en",
                    "class_description",
                    "family_description",
                    "segment_description",
                )
            )
            if normalized not in haystack:
                continue
        rows.append(dict(bundled))
        known.add(code)

    rows.sort(key=lambda row: (
        0 if normalized and str(row.get("brick_code") or "").lower() == normalized else 1,
        str(row.get("brick_description") or "").lower(),
        str(row.get("brick_code") or ""),
    ))
    return rows[:max_rows]

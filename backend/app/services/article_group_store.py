from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.db import engine


ARTICLE_GROUPS_SQL = """
CREATE TABLE IF NOT EXISTS article_groups (
    id TEXT PRIMARY KEY,
    household_id TEXT NOT NULL,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    sort_order INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT
)
"""

ARTICLE_GROUPS_HOUSEHOLD_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_article_groups_household_name
ON article_groups (household_id, normalized_name)
"""

HOUSEHOLD_ARTICLE_GROUP_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_household_articles_article_group
ON household_articles (article_group_id)
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_article_group_name(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    normalized = normalized.replace("ë", "e").replace("é", "e").replace("è", "e").replace("ï", "i")
    return " ".join(re.sub(r"\s+", " ", normalized).split())


def display_article_group_name(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _table_exists(conn, table_name: str) -> bool:
    dialect_name = str(engine.dialect.name or "").lower()
    if dialect_name == "sqlite":
        return conn.execute(
            text("SELECT name FROM sqlite_master WHERE type = 'table' AND name = :table_name"),
            {"table_name": table_name},
        ).mappings().first() is not None
    return conn.execute(
        text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = :table_name
            LIMIT 1
        """),
        {"table_name": table_name},
    ).mappings().first() is not None


def _get_columns(conn, table_name: str) -> set[str]:
    dialect_name = str(engine.dialect.name or "").lower()
    if dialect_name == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
        return {str(row.get("name") or "") for row in rows}
    rows = conn.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = :table_name"),
        {"table_name": table_name},
    ).mappings().all()
    return {str(row.get("column_name") or "") for row in rows}


def _ensure_missing_column(conn, table_name: str, column_name: str, definition: str) -> None:
    if not _table_exists(conn, table_name):
        return
    if column_name in _get_columns(conn, table_name):
        return
    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"))


def ensure_article_group_schema() -> None:
    with engine.begin() as conn:
        conn.execute(text(ARTICLE_GROUPS_SQL))
        conn.execute(text(ARTICLE_GROUPS_HOUSEHOLD_INDEX_SQL))
        conn.execute(text("UPDATE article_groups SET status = 'active' WHERE COALESCE(status, 'active') <> 'active'"))
        _ensure_missing_column(conn, "household_articles", "article_group_id", "TEXT")
        if _table_exists(conn, "household_articles"):
            conn.execute(text(HOUSEHOLD_ARTICLE_GROUP_INDEX_SQL))


def _normalize_household_id(household_id: Any) -> str:
    return str(household_id or "1").strip() or "1"


def _article_group_row(row: Any) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or ""),
        "household_id": str(row.get("household_id") or ""),
        "name": str(row.get("name") or ""),
        "normalized_name": str(row.get("normalized_name") or ""),
        "sort_order": int(row.get("sort_order") or 0),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def list_article_groups(household_id: Any = None) -> dict[str, Any]:
    ensure_article_group_schema()
    normalized_household_id = _normalize_household_id(household_id)
    with engine.begin() as conn:
        rows = conn.execute(
            text("""
                SELECT id, household_id, name, normalized_name, sort_order, created_at, updated_at
                FROM article_groups
                WHERE household_id = :household_id
                ORDER BY sort_order ASC, lower(name) ASC, id ASC
            """),
            {"household_id": normalized_household_id},
        ).mappings().all()
    return {"ok": True, "items": [_article_group_row(row) for row in rows], "mutates_inventory": False}


def create_article_group(household_id: Any, name: Any) -> dict[str, Any]:
    ensure_article_group_schema()
    normalized_household_id = _normalize_household_id(household_id)
    display_name = display_article_group_name(name)
    normalized_name = normalize_article_group_name(display_name)
    if not display_name or not normalized_name:
        return {"ok": False, "error": "Artikelgroepnaam is verplicht"}
    timestamp = now_iso()
    group_id = str(uuid.uuid4())
    with engine.begin() as conn:
        duplicate = conn.execute(
            text("""
                SELECT id
                FROM article_groups
                WHERE household_id = :household_id
                  AND normalized_name = :normalized_name
                LIMIT 1
            """),
            {"household_id": normalized_household_id, "normalized_name": normalized_name},
        ).mappings().first()
        if duplicate:
            return {"ok": False, "error": "Artikelgroep bestaat al"}
        max_sort = conn.execute(
            text("SELECT COALESCE(MAX(sort_order), 0) AS max_sort FROM article_groups WHERE household_id = :household_id"),
            {"household_id": normalized_household_id},
        ).mappings().first()
        sort_order = int(max_sort.get("max_sort") or 0) + 10 if max_sort else 10
        conn.execute(
            text("""
                INSERT INTO article_groups (id, household_id, name, normalized_name, status, sort_order, created_at, updated_at)
                VALUES (:id, :household_id, :name, :normalized_name, 'active', :sort_order, :created_at, :updated_at)
            """),
            {
                "id": group_id,
                "household_id": normalized_household_id,
                "name": display_name,
                "normalized_name": normalized_name,
                "sort_order": sort_order,
                "created_at": timestamp,
                "updated_at": timestamp,
            },
        )
    return {"ok": True, "item": {"id": group_id, "household_id": normalized_household_id, "name": display_name, "normalized_name": normalized_name, "sort_order": sort_order}, "mutates_inventory": False}


def update_article_group(group_id: Any, household_id: Any = None, name: Any = None, sort_order: Any = None) -> dict[str, Any]:
    ensure_article_group_schema()
    normalized_group_id = str(group_id or "").strip()
    if not normalized_group_id:
        return {"ok": False, "error": "Artikelgroep-id is verplicht"}
    timestamp = now_iso()
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT * FROM article_groups WHERE id = :id LIMIT 1"),
            {"id": normalized_group_id},
        ).mappings().first()
        if not existing:
            return {"ok": False, "error": "Artikelgroep niet gevonden"}
        normalized_household_id = _normalize_household_id(household_id or existing.get("household_id"))
        if str(existing.get("household_id") or "") != normalized_household_id:
            return {"ok": False, "error": "Artikelgroep hoort niet bij dit huishouden"}
        next_name = display_article_group_name(name if name is not None else existing.get("name"))
        next_normalized_name = normalize_article_group_name(next_name)
        if not next_name or not next_normalized_name:
            return {"ok": False, "error": "Artikelgroepnaam is verplicht"}
        duplicate = conn.execute(
            text("""
                SELECT id
                FROM article_groups
                WHERE household_id = :household_id
                  AND normalized_name = :normalized_name
                  AND id <> :id
                LIMIT 1
            """),
            {"household_id": normalized_household_id, "normalized_name": next_normalized_name, "id": normalized_group_id},
        ).mappings().first()
        if duplicate:
            return {"ok": False, "error": "Artikelgroep bestaat al"}
        try:
            next_sort_order = int(sort_order if sort_order is not None else existing.get("sort_order") or 0)
        except (TypeError, ValueError):
            next_sort_order = int(existing.get("sort_order") or 0)
        conn.execute(
            text("""
                UPDATE article_groups
                SET name = :name,
                    normalized_name = :normalized_name,
                    sort_order = :sort_order,
                    updated_at = :updated_at
                WHERE id = :id
            """),
            {"id": normalized_group_id, "name": next_name, "normalized_name": next_normalized_name, "sort_order": next_sort_order, "updated_at": timestamp},
        )
    return {"ok": True, "item": {"id": normalized_group_id, "household_id": normalized_household_id, "name": next_name, "normalized_name": next_normalized_name, "sort_order": next_sort_order}, "mutates_inventory": False}


def delete_article_group(group_id: Any, household_id: Any = None) -> dict[str, Any]:
    ensure_article_group_schema()
    normalized_group_id = str(group_id or "").strip()
    if not normalized_group_id:
        return {"ok": False, "error": "Artikelgroep-id is verplicht"}
    with engine.begin() as conn:
        existing = conn.execute(text("SELECT * FROM article_groups WHERE id = :id LIMIT 1"), {"id": normalized_group_id}).mappings().first()
        if not existing:
            return {"ok": False, "error": "Artikelgroep niet gevonden"}
        normalized_household_id = _normalize_household_id(household_id or existing.get("household_id"))
        if str(existing.get("household_id") or "") != normalized_household_id:
            return {"ok": False, "error": "Artikelgroep hoort niet bij dit huishouden"}
        linked_count = 0
        if _table_exists(conn, "household_articles") and "article_group_id" in _get_columns(conn, "household_articles"):
            linked_count = int(conn.execute(
                text("SELECT COUNT(*) AS count FROM household_articles WHERE article_group_id = :id"),
                {"id": normalized_group_id},
            ).mappings().first().get("count") or 0)
        if linked_count > 0:
            return {
                "ok": False,
                "error": f"Artikelgroep kan niet worden verwijderd zolang er {linked_count} artikel{'en' if linked_count != 1 else ''} aan gekoppeld zijn",
                "id": normalized_group_id,
                "deleted": False,
                "deactivated": False,
                "linked_count": linked_count,
                "mutates_inventory": False,
            }
        conn.execute(text("DELETE FROM article_groups WHERE id = :id"), {"id": normalized_group_id})
    return {"ok": True, "id": normalized_group_id, "deleted": True, "deactivated": False, "linked_count": 0, "mutates_inventory": False}


def _first_existing(columns: set[str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def list_household_articles_for_grouping(household_id: Any = None) -> dict[str, Any]:
    ensure_article_group_schema()
    normalized_household_id = _normalize_household_id(household_id)
    with engine.begin() as conn:
        if not _table_exists(conn, "household_articles"):
            return {"ok": True, "items": [], "mutates_inventory": False}
        columns = _get_columns(conn, "household_articles")
        id_column = _first_existing(columns, ["id", "household_article_id"])
        if not id_column:
            return {"ok": True, "items": [], "mutates_inventory": False}
        household_column = _first_existing(columns, ["household_id"])
        name_columns = [col for col in ["custom_name", "naam", "name", "article_name", "display_name", "canonical_name"] if col in columns]
        name_expr = "COALESCE(" + ", ".join(f"NULLIF(CAST(ha.{col} AS TEXT), '')" for col in name_columns) + ", '')" if name_columns else "''"
        group_expr = "ha.article_group_id" if "article_group_id" in columns else "NULL"
        where_clause = "1 = 1"
        params: dict[str, Any] = {}
        if household_column:
            where_clause = f"CAST(ha.{household_column} AS TEXT) = :household_id"
            params["household_id"] = normalized_household_id
        rows = conn.execute(
            text(f"""
                SELECT
                    CAST(ha.{id_column} AS TEXT) AS id,
                    {f'CAST(ha.{household_column} AS TEXT)' if household_column else "''"} AS household_id,
                    {name_expr} AS article_name,
                    {group_expr} AS article_group_id,
                    ag.name AS article_group_name
                FROM household_articles ha
                LEFT JOIN article_groups ag ON ag.id = {group_expr}
                WHERE {where_clause}
                ORDER BY lower({name_expr}) ASC, CAST(ha.{id_column} AS TEXT) ASC
            """),
            params,
        ).mappings().all()
    items = []
    for row in rows:
        article_name = str(row.get("article_name") or "").strip() or "Onbekend artikel"
        items.append({
            "id": str(row.get("id") or ""),
            "household_id": str(row.get("household_id") or normalized_household_id),
            "article_name": article_name,
            "article_group_id": row.get("article_group_id") or None,
            "article_group_name": row.get("article_group_name") or "Niet ingedeeld",
        })
    return {"ok": True, "items": items, "mutates_inventory": False}


def assign_household_article_group(article_id: Any, article_group_id: Any = None, household_id: Any = None) -> dict[str, Any]:
    ensure_article_group_schema()
    normalized_article_id = str(article_id or "").strip()
    if not normalized_article_id:
        return {"ok": False, "error": "Artikel-id is verplicht"}
    normalized_group_id = str(article_group_id or "").strip() or None
    with engine.begin() as conn:
        if not _table_exists(conn, "household_articles"):
            return {"ok": False, "error": "household_articles tabel ontbreekt"}
        columns = _get_columns(conn, "household_articles")
        id_column = _first_existing(columns, ["id", "household_article_id"])
        if not id_column:
            return {"ok": False, "error": "household_articles heeft geen id-kolom"}
        household_column = _first_existing(columns, ["household_id"])
        household_expr = f"CAST({household_column} AS TEXT)" if household_column else "''"
        row = conn.execute(
            text(f"SELECT CAST({id_column} AS TEXT) AS id, {household_expr} AS household_id FROM household_articles WHERE CAST({id_column} AS TEXT) = :id LIMIT 1"),
            {"id": normalized_article_id},
        ).mappings().first()
        if not row:
            return {"ok": False, "error": "Huishoudelijk artikel niet gevonden"}
        normalized_household_id = _normalize_household_id(household_id or row.get("household_id"))
        if household_column and str(row.get("household_id") or "") != normalized_household_id:
            return {"ok": False, "error": "Artikel hoort niet bij dit huishouden"}
        group_name = "Niet ingedeeld"
        if normalized_group_id:
            group = conn.execute(
                text("""
                    SELECT id, name
                    FROM article_groups
                    WHERE id = :id
                      AND household_id = :household_id
                    LIMIT 1
                """),
                {"id": normalized_group_id, "household_id": normalized_household_id},
            ).mappings().first()
            if not group:
                return {"ok": False, "error": "Artikelgroep niet gevonden"}
            group_name = str(group.get("name") or "") or group_name
        conn.execute(
            text(f"UPDATE household_articles SET article_group_id = :article_group_id WHERE CAST({id_column} AS TEXT) = :id"),
            {"id": normalized_article_id, "article_group_id": normalized_group_id},
        )
    return {"ok": True, "article_id": normalized_article_id, "article_group_id": normalized_group_id, "article_group_name": group_name, "mutates_inventory": False}

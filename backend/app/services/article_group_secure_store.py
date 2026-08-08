from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.services import article_group_store as legacy_store


def list_article_groups(household_id: Any = None) -> dict[str, Any]:
    return legacy_store.list_article_groups(household_id=household_id)


def create_article_group(household_id: Any, name: Any) -> dict[str, Any]:
    return legacy_store.create_article_group(household_id=household_id, name=name)


def list_household_articles_for_grouping(household_id: Any = None) -> dict[str, Any]:
    return legacy_store.list_household_articles_for_grouping(household_id=household_id)


def _required_household_id(household_id: Any) -> str:
    normalized = str(household_id or "").strip()
    if not normalized:
        raise ValueError("household_id is verplicht voor een huishoudgebonden mutatie")
    return normalized


def update_article_group(
    group_id: Any,
    household_id: Any,
    name: Any = None,
    sort_order: Any = None,
) -> dict[str, Any]:
    legacy_store.ensure_article_group_schema()
    normalized_group_id = str(group_id or "").strip()
    if not normalized_group_id:
        return {"ok": False, "error": "Artikelgroep-id is verplicht"}

    normalized_household_id = _required_household_id(household_id)
    timestamp = legacy_store.now_iso()

    with legacy_store.engine.begin() as conn:
        existing = conn.execute(
            text(
                """
                SELECT *
                FROM article_groups
                WHERE id = :id
                  AND household_id = :household_id
                LIMIT 1
                """
            ),
            {
                "id": normalized_group_id,
                "household_id": normalized_household_id,
            },
        ).mappings().first()
        if not existing:
            return {"ok": False, "error": "Artikelgroep niet gevonden"}

        next_name = legacy_store.display_article_group_name(
            name if name is not None else existing.get("name")
        )
        next_normalized_name = legacy_store.normalize_article_group_name(next_name)
        if not next_name or not next_normalized_name:
            return {"ok": False, "error": "Artikelgroepnaam is verplicht"}

        duplicate = conn.execute(
            text(
                """
                SELECT id
                FROM article_groups
                WHERE household_id = :household_id
                  AND normalized_name = :normalized_name
                  AND id <> :id
                LIMIT 1
                """
            ),
            {
                "household_id": normalized_household_id,
                "normalized_name": next_normalized_name,
                "id": normalized_group_id,
            },
        ).mappings().first()
        if duplicate:
            return {"ok": False, "error": "Artikelgroep bestaat al"}

        try:
            next_sort_order = int(
                sort_order if sort_order is not None else existing.get("sort_order") or 0
            )
        except (TypeError, ValueError):
            next_sort_order = int(existing.get("sort_order") or 0)

        result = conn.execute(
            text(
                """
                UPDATE article_groups
                SET name = :name,
                    normalized_name = :normalized_name,
                    sort_order = :sort_order,
                    updated_at = :updated_at
                WHERE id = :id
                  AND household_id = :household_id
                """
            ),
            {
                "id": normalized_group_id,
                "household_id": normalized_household_id,
                "name": next_name,
                "normalized_name": next_normalized_name,
                "sort_order": next_sort_order,
                "updated_at": timestamp,
            },
        )
        if int(result.rowcount or 0) != 1:
            return {"ok": False, "error": "Artikelgroep niet gevonden"}

    return {
        "ok": True,
        "item": {
            "id": normalized_group_id,
            "household_id": normalized_household_id,
            "name": next_name,
            "normalized_name": next_normalized_name,
            "sort_order": next_sort_order,
        },
        "mutates_inventory": False,
    }


def delete_article_group(group_id: Any, household_id: Any) -> dict[str, Any]:
    legacy_store.ensure_article_group_schema()
    normalized_group_id = str(group_id or "").strip()
    if not normalized_group_id:
        return {"ok": False, "error": "Artikelgroep-id is verplicht"}

    normalized_household_id = _required_household_id(household_id)

    with legacy_store.engine.begin() as conn:
        existing = conn.execute(
            text(
                """
                SELECT id
                FROM article_groups
                WHERE id = :id
                  AND household_id = :household_id
                LIMIT 1
                """
            ),
            {
                "id": normalized_group_id,
                "household_id": normalized_household_id,
            },
        ).mappings().first()
        if not existing:
            return {"ok": False, "error": "Artikelgroep niet gevonden"}

        linked_count = 0
        if legacy_store._table_exists(conn, "household_articles"):
            columns = legacy_store._get_columns(conn, "household_articles")
            if "article_group_id" in columns and "household_id" in columns:
                linked_count = int(
                    conn.execute(
                        text(
                            """
                            SELECT COUNT(*) AS count
                            FROM household_articles
                            WHERE article_group_id = :id
                              AND household_id = :household_id
                            """
                        ),
                        {
                            "id": normalized_group_id,
                            "household_id": normalized_household_id,
                        },
                    ).mappings().first().get("count")
                    or 0
                )

        if linked_count > 0:
            suffix = "en" if linked_count != 1 else ""
            return {
                "ok": False,
                "error": (
                    "Artikelgroep kan niet worden verwijderd zolang er "
                    f"{linked_count} artikel{suffix} aan gekoppeld zijn"
                ),
                "id": normalized_group_id,
                "deleted": False,
                "deactivated": False,
                "linked_count": linked_count,
                "mutates_inventory": False,
            }

        result = conn.execute(
            text(
                """
                DELETE FROM article_groups
                WHERE id = :id
                  AND household_id = :household_id
                """
            ),
            {
                "id": normalized_group_id,
                "household_id": normalized_household_id,
            },
        )
        if int(result.rowcount or 0) != 1:
            return {"ok": False, "error": "Artikelgroep niet gevonden"}

    return {
        "ok": True,
        "id": normalized_group_id,
        "deleted": True,
        "deactivated": False,
        "linked_count": 0,
        "mutates_inventory": False,
    }


def assign_household_article_group(
    article_id: Any,
    article_group_id: Any = None,
    household_id: Any = None,
) -> dict[str, Any]:
    legacy_store.ensure_article_group_schema()
    normalized_article_id = str(article_id or "").strip()
    if not normalized_article_id:
        return {"ok": False, "error": "Artikel-id is verplicht"}

    normalized_household_id = _required_household_id(household_id)
    normalized_group_id = str(article_group_id or "").strip() or None

    with legacy_store.engine.begin() as conn:
        if not legacy_store._table_exists(conn, "household_articles"):
            return {"ok": False, "error": "household_articles tabel ontbreekt"}

        columns = legacy_store._get_columns(conn, "household_articles")
        id_column = legacy_store._first_existing(columns, ["id", "household_article_id"])
        if not id_column:
            return {"ok": False, "error": "household_articles heeft geen id-kolom"}
        if "household_id" not in columns:
            return {
                "ok": False,
                "error": "household_articles heeft geen household_id-kolom",
            }

        article = conn.execute(
            text(
                f"""
                SELECT CAST({id_column} AS TEXT) AS id
                FROM household_articles
                WHERE CAST({id_column} AS TEXT) = :id
                  AND CAST(household_id AS TEXT) = :household_id
                LIMIT 1
                """
            ),
            {
                "id": normalized_article_id,
                "household_id": normalized_household_id,
            },
        ).mappings().first()
        if not article:
            return {"ok": False, "error": "Huishoudelijk artikel niet gevonden"}

        group_name = "Niet ingedeeld"
        if normalized_group_id:
            group = conn.execute(
                text(
                    """
                    SELECT id, name
                    FROM article_groups
                    WHERE id = :id
                      AND household_id = :household_id
                    LIMIT 1
                    """
                ),
                {
                    "id": normalized_group_id,
                    "household_id": normalized_household_id,
                },
            ).mappings().first()
            if not group:
                return {"ok": False, "error": "Artikelgroep niet gevonden"}
            group_name = str(group.get("name") or "") or group_name

        result = conn.execute(
            text(
                f"""
                UPDATE household_articles
                SET article_group_id = :article_group_id
                WHERE CAST({id_column} AS TEXT) = :id
                  AND CAST(household_id AS TEXT) = :household_id
                """
            ),
            {
                "id": normalized_article_id,
                "household_id": normalized_household_id,
                "article_group_id": normalized_group_id,
            },
        )
        if int(result.rowcount or 0) != 1:
            return {"ok": False, "error": "Huishoudelijk artikel niet gevonden"}

    return {
        "ok": True,
        "article_id": normalized_article_id,
        "article_group_id": normalized_group_id,
        "article_group_name": group_name,
        "mutates_inventory": False,
    }

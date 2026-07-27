"""Veilige vervanging van een generieke centrale productkoppeling.

Deze service wijzigt uitsluitend ``household_articles.global_product_id`` en de
bestaande verwijzing van de geselecteerde bonregel naar hetzelfde huishoudartikel.
Voorraad, locaties, artikelinstellingen en inventory-events worden niet gewijzigd.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import inspect, text

from app.services.barcode_identity_service import lookup_gtin


REPLACEMENT_CONFIRMATION_REQUIRED = "REPLACEMENT_CONFIRMATION_REQUIRED"
GENERIC_REPLACEMENT_BLOCKED = "GENERIC_REPLACEMENT_BLOCKED"


class GenericProductLinkReplacementError(ValueError):
    def __init__(self, status_code: int, detail: str | dict[str, Any]):
        super().__init__(str(detail))
        self.status_code = int(status_code)
        self.detail = detail


def _table_names(conn) -> set[str]:
    return set(inspect(conn).get_table_names())


def _column_names(conn, table_name: str) -> set[str]:
    return {
        str(column.get("name") or "")
        for column in inspect(conn).get_columns(table_name)
    }


def _first_existing(columns: set[str], *candidates: str) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _product_snapshot(conn, product_id: str) -> dict[str, Any] | None:
    product_columns = _column_names(conn, "global_products")
    selectable = {
        "id": "id",
        "name": "name",
        "brand": "brand",
        "primary_gtin": "primary_gtin",
        "source": "source",
        "status": "status",
    }
    select_sql = ", ".join(
        expression if alias in product_columns else f"NULL AS {alias}"
        for alias, expression in selectable.items()
    )
    row = conn.execute(
        text(
            f"""
            SELECT {select_sql}
            FROM global_products
            WHERE id = :product_id
            LIMIT 1
            """
        ),
        {"product_id": product_id},
    ).mappings().first()
    if not row:
        return None
    return dict(row)


def _has_gtin_identity(conn, product_id: str) -> bool:
    if "product_identities" not in _table_names(conn):
        return False
    columns = _column_names(conn, "product_identities")
    required = {"global_product_id", "identity_type", "identity_value"}
    if not required.issubset(columns):
        return False
    return bool(
        conn.execute(
            text(
                """
                SELECT 1
                FROM product_identities
                WHERE global_product_id = :product_id
                  AND lower(trim(identity_type)) IN ('gtin', 'ean', 'upc')
                  AND COALESCE(trim(identity_value), '') <> ''
                LIMIT 1
                """
            ),
            {"product_id": product_id},
        ).first()
    )


def _is_replaceable_generic_product(conn, product: dict[str, Any]) -> bool:
    product_id = str(product.get("id") or "").strip()
    primary_gtin = str(product.get("primary_gtin") or "").strip()
    source = str(product.get("source") or "").strip().lower()
    status = str(product.get("status") or "active").strip().lower()
    return (
        bool(product_id)
        and not primary_gtin
        and not _has_gtin_identity(conn, product_id)
        and source in {"user", "manual"}
        and status == "active"
    )


def _confirmation_detail(
    current_product: dict[str, Any],
    requested_product: dict[str, Any],
) -> dict[str, Any]:
    return {
        "code": REPLACEMENT_CONFIRMATION_REQUIRED,
        "message": (
            "Mijn artikel is al gekoppeld aan een generiek universeel artikel. "
            "Expliciete bevestiging is vereist om deze koppeling te vervangen."
        ),
        "current_product": current_product,
        "requested_product": requested_product,
        "replacement_allowed": True,
    }


def replace_generic_household_article_product_link(
    conn,
    *,
    household_id: str,
    purchase_import_line_id: str,
    household_article_id: str,
    gtin: str,
    global_product_id: str,
    confirm_replace_generic_link: bool = False,
) -> dict[str, Any]:
    """Vervang na expliciete bevestiging alleen een generieke koppeling zonder GTIN."""

    household_id = str(household_id or "").strip()
    line_id = str(purchase_import_line_id or "").strip()
    article_id = str(household_article_id or "").strip()
    requested_product_id = str(global_product_id or "").strip()

    if not household_id:
        raise GenericProductLinkReplacementError(400, "Het actieve huishouden ontbreekt.")
    if not line_id or not article_id or not requested_product_id:
        raise GenericProductLinkReplacementError(
            400,
            "Bonregel, Mijn artikel en universeel artikel zijn verplicht.",
        )

    lookup = lookup_gtin(conn, gtin)
    if lookup.get("match_status") != "matched":
        raise GenericProductLinkReplacementError(
            409,
            "Alleen een volledig en eenduidig herkende GTIN kan worden gekoppeld.",
        )

    matched_product_id = str(
        (lookup.get("product") or {}).get("global_product_id") or ""
    ).strip()
    normalized_gtin = str(lookup.get("gtin") or "").strip()
    if matched_product_id != requested_product_id:
        raise GenericProductLinkReplacementError(
            409,
            "Het universele artikel hoort niet bij de gecontroleerde GTIN.",
        )

    tables = _table_names(conn)
    required_tables = {
        "global_products",
        "purchase_import_lines",
        "purchase_import_batches",
        "household_articles",
    }
    missing = sorted(required_tables - tables)
    if missing:
        raise GenericProductLinkReplacementError(
            500,
            "Benodigde tabel ontbreekt: " + ", ".join(missing),
        )

    line_columns = _column_names(conn, "purchase_import_lines")
    batch_columns = _column_names(conn, "purchase_import_batches")
    article_columns = _column_names(conn, "household_articles")

    line_id_column = _first_existing(line_columns, "id", "line_id")
    line_batch_column = _first_existing(
        line_columns,
        "batch_id",
        "purchase_import_batch_id",
        "import_batch_id",
    )
    batch_id_column = _first_existing(batch_columns, "batch_id", "id")
    mapped_article_column = _first_existing(
        line_columns,
        "matched_household_article_id",
        "household_article_id",
        "selected_household_article_id",
    )

    if (
        not line_id_column
        or not line_batch_column
        or not batch_id_column
        or "household_id" not in batch_columns
        or not {"id", "household_id", "global_product_id"}.issubset(article_columns)
    ):
        raise GenericProductLinkReplacementError(
            500,
            "De productkoppeltabellen hebben niet de verwachte sleutelkolommen.",
        )

    line = conn.execute(
        text(
            f"""
            SELECT {line_id_column} AS line_id, {line_batch_column} AS batch_id
            FROM purchase_import_lines
            WHERE {line_id_column} = :line_id
            LIMIT 1
            """
        ),
        {"line_id": line_id},
    ).mappings().first()
    if not line:
        raise GenericProductLinkReplacementError(404, "Bonregel niet gevonden.")

    batch = conn.execute(
        text(
            f"""
            SELECT {batch_id_column} AS batch_id, household_id
            FROM purchase_import_batches
            WHERE {batch_id_column} = :batch_id
              AND household_id = :household_id
            LIMIT 1
            """
        ),
        {
            "batch_id": str(line.get("batch_id") or ""),
            "household_id": household_id,
        },
    ).mappings().first()
    if not batch:
        raise GenericProductLinkReplacementError(
            404,
            "Bonregel niet gevonden binnen het actieve huishouden.",
        )

    article = conn.execute(
        text(
            """
            SELECT id, household_id, global_product_id
            FROM household_articles
            WHERE id = :article_id
              AND household_id = :household_id
            LIMIT 1
            """
        ),
        {"article_id": article_id, "household_id": household_id},
    ).mappings().first()
    if not article:
        raise GenericProductLinkReplacementError(
            404,
            "Mijn artikel niet gevonden binnen het actieve huishouden.",
        )

    current_product_id = str(article.get("global_product_id") or "").strip()
    requested_product = _product_snapshot(conn, requested_product_id)
    if not requested_product:
        raise GenericProductLinkReplacementError(
            404,
            "Het geselecteerde universele artikel bestaat niet.",
        )

    if not current_product_id:
        raise GenericProductLinkReplacementError(
            409,
            {
                "code": GENERIC_REPLACEMENT_BLOCKED,
                "message": "Er is geen bestaande koppeling om te vervangen.",
                "replacement_allowed": False,
            },
        )

    if current_product_id == requested_product_id:
        return {
            "ok": True,
            "changed": False,
            "idempotent": True,
            "replacement_confirmed": bool(confirm_replace_generic_link),
            "purchase_import_line_id": line_id,
            "household_article_id": article_id,
            "previous_global_product_id": current_product_id,
            "global_product_id": requested_product_id,
            "gtin": normalized_gtin,
            "inventory_mutated": False,
            "product": lookup.get("product"),
        }

    current_product = _product_snapshot(conn, current_product_id)
    if not current_product:
        raise GenericProductLinkReplacementError(
            409,
            {
                "code": GENERIC_REPLACEMENT_BLOCKED,
                "message": "De bestaande universele koppeling is niet meer geldig.",
                "replacement_allowed": False,
            },
        )

    if not _is_replaceable_generic_product(conn, current_product):
        raise GenericProductLinkReplacementError(
            409,
            {
                "code": GENERIC_REPLACEMENT_BLOCKED,
                "message": (
                    "Mijn artikel is al gekoppeld aan een specifiek universeel "
                    "artikel en kan niet via deze flow worden overschreven."
                ),
                "current_product": current_product,
                "requested_product": requested_product,
                "replacement_allowed": False,
            },
        )

    if not confirm_replace_generic_link:
        raise GenericProductLinkReplacementError(
            409,
            _confirmation_detail(current_product, requested_product),
        )

    inventory_events_before = None
    if "inventory_events" in tables:
        inventory_events_before = conn.execute(
            text("SELECT COUNT(*) FROM inventory_events")
        ).scalar_one()

    updated_at_sql = (
        ", updated_at = CURRENT_TIMESTAMP"
        if "updated_at" in article_columns
        else ""
    )
    conn.execute(
        text(
            f"""
            UPDATE household_articles
            SET global_product_id = :global_product_id{updated_at_sql}
            WHERE id = :article_id
              AND household_id = :household_id
              AND global_product_id = :previous_global_product_id
            """
        ),
        {
            "global_product_id": requested_product_id,
            "article_id": article_id,
            "household_id": household_id,
            "previous_global_product_id": current_product_id,
        },
    )

    if mapped_article_column:
        conn.execute(
            text(
                f"""
                UPDATE purchase_import_lines
                SET {mapped_article_column} = :article_id
                WHERE {line_id_column} = :line_id
                """
            ),
            {"article_id": article_id, "line_id": line_id},
        )

    if "inventory_events" in tables:
        inventory_events_after = conn.execute(
            text("SELECT COUNT(*) FROM inventory_events")
        ).scalar_one()
        if inventory_events_after != inventory_events_before:
            raise GenericProductLinkReplacementError(
                500,
                "De vervanging heeft onverwacht de voorraadhistorie gewijzigd.",
            )

    return {
        "ok": True,
        "changed": True,
        "idempotent": False,
        "replacement_confirmed": True,
        "purchase_import_line_id": line_id,
        "household_article_id": article_id,
        "previous_global_product_id": current_product_id,
        "global_product_id": requested_product_id,
        "gtin": normalized_gtin,
        "inventory_mutated": False,
        "current_product": current_product,
        "product": lookup.get("product"),
    }

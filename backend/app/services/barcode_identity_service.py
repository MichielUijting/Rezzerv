"""Central, read-only barcode and GTIN validation/lookup service.

Domain rules:
- retailer article numbers are never interpreted as GTINs;
- only GTIN-8, GTIN-12, GTIN-13 and GTIN-14 are accepted;
- GTIN check digits are validated with the GS1 modulo-10 algorithm;
- validation and lookup never mutate products, identities, household articles or stock.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import inspect, text

GTIN_LENGTH_TO_FORMAT = {
    8: "GTIN-8",
    12: "GTIN-12",
    13: "GTIN-13",
    14: "GTIN-14",
}


def normalize_barcode_input(value: Any) -> str:
    """Remove user-friendly spaces and hyphens without accepting other characters."""
    raw = str(value or "").strip()
    return re.sub(r"[\s-]+", "", raw)


def calculate_gtin_check_digit(body: str) -> int:
    if not body or not body.isdigit():
        raise ValueError("GTIN-basis moet uitsluitend uit cijfers bestaan")
    total = 0
    for position, character in enumerate(reversed(body), start=1):
        multiplier = 3 if position % 2 == 1 else 1
        total += int(character) * multiplier
    return (10 - (total % 10)) % 10


def validate_barcode(value: Any, declared_type: str = "gtin") -> dict[str, Any]:
    raw_value = str(value or "")
    normalized_type = str(declared_type or "gtin").strip().lower()

    if normalized_type not in {"gtin", "retailer_article_number"}:
        return {
            "raw_value": raw_value,
            "normalized_value": normalize_barcode_input(raw_value),
            "identity_type": normalized_type,
            "gtin_format": None,
            "valid": False,
            "validation": {"length_valid": False, "check_digit_valid": False},
            "errors": [{"code": "UNSUPPORTED_IDENTITY_TYPE", "message": "Onbekend identiteitstype."}],
            "mutated": False,
        }

    normalized_value = normalize_barcode_input(raw_value)
    if normalized_type == "retailer_article_number":
        valid = bool(normalized_value) and len(normalized_value) <= 120
        return {
            "raw_value": raw_value,
            "normalized_value": normalized_value,
            "identity_type": "retailer_article_number",
            "gtin_format": None,
            "valid": valid,
            "validation": {"length_valid": valid, "check_digit_valid": None},
            "errors": [] if valid else [{"code": "EMPTY_RETAILER_ARTICLE_NUMBER", "message": "Winkelartikelcode ontbreekt."}],
            "mutated": False,
        }

    errors: list[dict[str, str]] = []
    digits_only = normalized_value.isdigit()
    length_valid = len(normalized_value) in GTIN_LENGTH_TO_FORMAT
    check_digit_valid = False

    if not digits_only:
        errors.append({"code": "NON_NUMERIC_GTIN", "message": "Een GTIN mag uitsluitend cijfers bevatten."})
    if not length_valid:
        errors.append({"code": "INVALID_GTIN_LENGTH", "message": "Alleen GTIN-8, GTIN-12, GTIN-13 en GTIN-14 zijn toegestaan."})
    if digits_only and length_valid:
        check_digit_valid = calculate_gtin_check_digit(normalized_value[:-1]) == int(normalized_value[-1])
        if not check_digit_valid:
            errors.append({"code": "INVALID_CHECK_DIGIT", "message": "Het controlecijfer van de GTIN is ongeldig."})

    return {
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "identity_type": "gtin",
        "gtin_format": GTIN_LENGTH_TO_FORMAT.get(len(normalized_value)),
        "valid": digits_only and length_valid and check_digit_valid,
        "validation": {"length_valid": length_valid, "check_digit_valid": check_digit_valid},
        "errors": errors,
        "mutated": False,
    }


def _table_names(conn) -> set[str]:
    return set(inspect(conn).get_table_names())


def lookup_gtin(conn, value: Any) -> dict[str, Any]:
    validation = validate_barcode(value, "gtin")
    gtin = str(validation["normalized_value"])
    if not validation["valid"]:
        return {
            "gtin": gtin,
            "valid": False,
            "match_status": "invalid",
            "validation": validation,
            "product": None,
            "identity": None,
            "product_type": None,
            "quality": None,
            "mutated": False,
        }

    tables = _table_names(conn)
    if "global_products" not in tables:
        return {
            "gtin": gtin,
            "valid": True,
            "match_status": "not_found",
            "product": None,
            "identity": None,
            "product_type": None,
            "quality": None,
            "mutated": False,
        }

    identity_join = ""
    identity_columns = "NULL AS identity_id, NULL AS identity_source, 0 AS identity_is_primary"
    identity_match_expression = "0 AS has_matching_gtin_identity"
    if "product_identities" in tables:
        identity_join = """
            LEFT JOIN product_identities pi
              ON pi.global_product_id = gp.id
             AND pi.identity_type = 'gtin'
             AND pi.identity_value = :gtin
        """
        identity_columns = "pi.id AS identity_id, pi.source AS identity_source, COALESCE(pi.is_primary, 0) AS identity_is_primary"
        identity_match_expression = "CASE WHEN pi.id IS NULL THEN 0 ELSE 1 END AS has_matching_gtin_identity"

    gpc_join = ""
    gpc_columns = "NULL AS product_type_key, NULL AS gpc_brick_code, NULL AS product_type_name, 0 AS has_active_official_gpc"
    if {"product_group_memberships", "product_inventory_groups"}.issubset(tables):
        gpc_join = """
            LEFT JOIN product_group_memberships pgm
              ON pgm.global_product_id = gp.id
             AND COALESCE(pgm.active, 1) = 1
             AND pgm.inventory_group_key GLOB 'gpc:[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'
            LEFT JOIN product_inventory_groups pig
              ON pig.inventory_group_key = pgm.inventory_group_key
             AND pig.gpc_brick_code = substr(pgm.inventory_group_key, 5)
             AND pig.source LIKE 'gs1_gpc_%'
             AND COALESCE(pig.active, 1) = 1
        """
        gpc_columns = "pgm.inventory_group_key AS product_type_key, pig.gpc_brick_code, pig.display_name AS product_type_name, CASE WHEN pig.inventory_group_key IS NULL THEN 0 ELSE 1 END AS has_active_official_gpc"

    lookup_predicate = "gp.primary_gtin = :gtin"
    if "product_identities" in tables:
        lookup_predicate += """
            OR EXISTS (
                SELECT 1 FROM product_identities pi_lookup
                WHERE pi_lookup.global_product_id = gp.id
                  AND pi_lookup.identity_type = 'gtin'
                  AND pi_lookup.identity_value = :gtin
            )
        """

    raw_rows = conn.execute(
        text(
            f"""
            SELECT
                gp.id,
                gp.name,
                gp.brand,
                gp.status,
                gp.primary_gtin,
                {identity_columns},
                {identity_match_expression},
                {gpc_columns}
            FROM global_products gp
            {identity_join}
            {gpc_join}
            WHERE ({lookup_predicate})
            ORDER BY CASE WHEN gp.primary_gtin = :gtin THEN 0 ELSE 1 END, gp.id
            LIMIT 20
            """
        ),
        {"gtin": gtin},
    ).mappings().all()

    row_by_product_id: dict[str, dict[str, Any]] = {}
    for raw_row in raw_rows:
        serialized_row = dict(raw_row)
        product_id = str(serialized_row.get("id") or "")
        if product_id and product_id not in row_by_product_id:
            row_by_product_id[product_id] = serialized_row
    row = list(row_by_product_id.values())

    if not row:
        return {
            "gtin": gtin,
            "valid": True,
            "match_status": "not_found",
            "product": None,
            "identity": None,
            "product_type": None,
            "quality": None,
            "mutated": False,
        }

    if len(row) > 1:
        return {
            "gtin": gtin,
            "valid": True,
            "match_status": "conflict",
            "product": None,
            "identity": None,
            "product_type": None,
            "quality": {"reason": "De GTIN verwijst naar meerdere universele producten."},
            "mutated": False,
        }

    item = dict(row[0])
    primary_consistent = str(item.get("primary_gtin") or "").strip() == gtin
    identity_consistent = bool(item.get("has_matching_gtin_identity"))
    official_gpc_active = bool(item.get("has_active_official_gpc"))
    product_active = str(item.get("status") or "active").strip().lower() == "active"
    complete = primary_consistent and identity_consistent and official_gpc_active and product_active

    return {
        "gtin": gtin,
        "valid": True,
        "match_status": "matched" if complete else "incomplete",
        "product": {
            "global_product_id": str(item.get("id") or ""),
            "name": item.get("name"),
            "brand": item.get("brand"),
            "status": item.get("status"),
            "primary_gtin": item.get("primary_gtin"),
        },
        "identity": {
            "identity_id": str(item.get("identity_id") or "") or None,
            "identity_type": "gtin",
            "identity_value": gtin,
            "is_primary": bool(item.get("identity_is_primary")),
            "source": item.get("identity_source"),
        } if identity_consistent else None,
        "product_type": {
            "official": official_gpc_active,
            "active": official_gpc_active,
            "gpc_brick_code": item.get("gpc_brick_code"),
            "display_name": item.get("product_type_name"),
            "inventory_group_key": item.get("product_type_key"),
        },
        "quality": {
            "product_active": product_active,
            "primary_gtin_consistent": primary_consistent,
            "identity_consistent": identity_consistent,
            "official_gpc_active": official_gpc_active,
        },
        "mutated": False,
    }



class BarcodeHouseholdArticleLinkError(ValueError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = int(status_code)
        self.detail = str(detail)


def _column_names(conn, table_name: str) -> set[str]:
    return {
        str(column["name"])
        for column in inspect(conn).get_columns(table_name)
    }


def _first_existing_column(
    columns: set[str],
    *candidates: str,
) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def link_household_article_to_matched_product(
    conn,
    *,
    household_id: str,
    purchase_import_line_id: str,
    household_article_id: str,
    gtin: str,
    global_product_id: str,
) -> dict[str, Any]:
    """Maak één expliciete productkoppeling zonder voorraadmutatie."""

    household_id = str(household_id or "").strip()
    line_id = str(purchase_import_line_id or "").strip()
    article_id = str(household_article_id or "").strip()
    requested_product_id = str(global_product_id or "").strip()

    if not household_id:
        raise BarcodeHouseholdArticleLinkError(
            400,
            "Het actieve huishouden ontbreekt.",
        )

    if not line_id or not article_id or not requested_product_id:
        raise BarcodeHouseholdArticleLinkError(
            400,
            "Bonregel, Mijn artikel en universeel artikel zijn verplicht.",
        )

    lookup = lookup_gtin(conn, gtin)

    if lookup.get("match_status") != "matched":
        raise BarcodeHouseholdArticleLinkError(
            409,
            "Alleen een volledig en eenduidig herkende GTIN kan worden gekoppeld.",
        )

    matched_product_id = str(
        (lookup.get("product") or {}).get("global_product_id") or ""
    ).strip()

    normalized_gtin = str(lookup.get("gtin") or "").strip()

    if matched_product_id != requested_product_id:
        raise BarcodeHouseholdArticleLinkError(
            409,
            "Het universele artikel hoort niet bij de gecontroleerde GTIN.",
        )

    tables = _table_names(conn)
    required_tables = {
        "purchase_import_lines",
        "purchase_import_batches",
        "household_articles",
    }

    missing_tables = sorted(required_tables - tables)
    if missing_tables:
        raise BarcodeHouseholdArticleLinkError(
            500,
            "Benodigde tabel ontbreekt: " + ", ".join(missing_tables),
        )

    line_columns = _column_names(conn, "purchase_import_lines")
    batch_columns = _column_names(conn, "purchase_import_batches")
    article_columns = _column_names(conn, "household_articles")

    line_id_column = _first_existing_column(
        line_columns,
        "id",
        "line_id",
    )
    line_batch_column = _first_existing_column(
        line_columns,
        "batch_id",
        "purchase_import_batch_id",
        "import_batch_id",
    )
    batch_id_column = _first_existing_column(
        batch_columns,
        "batch_id",
        "id",
    )

    if (
        not line_id_column
        or not line_batch_column
        or not batch_id_column
        or "household_id" not in batch_columns
    ):
        raise BarcodeHouseholdArticleLinkError(
            500,
            "De bonimporttabellen hebben niet de verwachte sleutelkolommen.",
        )

    line = conn.execute(
        text(
            f"""
            SELECT
                {line_id_column} AS line_id,
                {line_batch_column} AS batch_id
            FROM purchase_import_lines
            WHERE {line_id_column} = :line_id
            LIMIT 1
            """
        ),
        {"line_id": line_id},
    ).mappings().first()

    if not line:
        raise BarcodeHouseholdArticleLinkError(
            404,
            "Bonregel niet gevonden.",
        )

    batch = conn.execute(
        text(
            f"""
            SELECT
                {batch_id_column} AS batch_id,
                household_id
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
        raise BarcodeHouseholdArticleLinkError(
            404,
            "Bonregel niet gevonden binnen het actieve huishouden.",
        )

    required_article_columns = {
        "id",
        "household_id",
        "global_product_id",
    }

    if not required_article_columns.issubset(article_columns):
        raise BarcodeHouseholdArticleLinkError(
            500,
            "Mijn-artikeltabel mist verplichte koppelkolommen.",
        )

    article = conn.execute(
        text(
            """
            SELECT
                id,
                household_id,
                global_product_id
            FROM household_articles
            WHERE id = :article_id
              AND household_id = :household_id
            LIMIT 1
            """
        ),
        {
            "article_id": article_id,
            "household_id": household_id,
        },
    ).mappings().first()

    if not article:
        raise BarcodeHouseholdArticleLinkError(
            404,
            "Mijn artikel niet gevonden binnen het actieve huishouden.",
        )

    existing_product_id = str(
        article.get("global_product_id") or ""
    ).strip()

    if (
        existing_product_id
        and existing_product_id != requested_product_id
    ):
        raise BarcodeHouseholdArticleLinkError(
            409,
            "Mijn artikel is al aan een ander universeel artikel gekoppeld.",
        )

    inventory_before = None

    if "inventory_events" in tables:
        inventory_before = conn.execute(
            text("SELECT COUNT(*) FROM inventory_events")
        ).scalar_one()

    changed = existing_product_id != requested_product_id

    if changed:
        updated_at_fragment = (
            ", updated_at = CURRENT_TIMESTAMP"
            if "updated_at" in article_columns
            else ""
        )

        conn.execute(
            text(
                f"""
                UPDATE household_articles
                SET global_product_id = :global_product_id
                    {updated_at_fragment}
                WHERE id = :article_id
                  AND household_id = :household_id
                """
            ),
            {
                "global_product_id": requested_product_id,
                "article_id": article_id,
                "household_id": household_id,
            },
        )

    mapped_article_column = _first_existing_column(
        line_columns,
        "matched_household_article_id",
        "household_article_id",
        "selected_household_article_id",
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
            {
                "article_id": article_id,
                "line_id": line_id,
            },
        )

    if "inventory_events" in tables:
        inventory_after = conn.execute(
            text("SELECT COUNT(*) FROM inventory_events")
        ).scalar_one()

        if inventory_after != inventory_before:
            raise BarcodeHouseholdArticleLinkError(
                500,
                "De barcodekoppeling heeft onverwacht de voorraad gewijzigd.",
            )

    return {
        "ok": True,
        "changed": changed,
        "idempotent": not changed,
        "purchase_import_line_id": line_id,
        "household_article_id": article_id,
        "global_product_id": requested_product_id,
        "gtin": normalized_gtin,
        "inventory_mutated": False,
        "product": lookup.get("product"),
    }



def _insert_dynamic_row(
    conn,
    *,
    table_name: str,
    values: dict[str, Any],
) -> None:
    columns = _column_names(conn, table_name)
    selected = {
        key: value
        for key, value in values.items()
        if key in columns
    }

    if not selected:
        raise BarcodeHouseholdArticleLinkError(
            500,
            f"Tabel {table_name} bevat geen bruikbare kolommen.",
        )

    column_sql = ", ".join(selected.keys())
    value_sql = ", ".join(f":{key}" for key in selected)

    conn.execute(
        text(
            f"""
            INSERT INTO {table_name} ({column_sql})
            VALUES ({value_sql})
            """
        ),
        selected,
    )


def _resolve_catalog_product_for_save(
    conn,
    *,
    gtin: str,
    article_name: str,
    household_article_id: str,
) -> dict[str, Any]:
    tables = _table_names(conn)

    if "global_products" not in tables:
        raise BarcodeHouseholdArticleLinkError(
            500,
            "De centrale productcatalogus ontbreekt.",
        )

    product_columns = _column_names(conn, "global_products")
    identity_available = "product_identities" in tables

    product_ids: set[str] = set()

    if "primary_gtin" in product_columns:
        rows = conn.execute(
            text(
                """
                SELECT id
                FROM global_products
                WHERE primary_gtin = :gtin
                """
            ),
            {"gtin": gtin},
        ).mappings().all()

        product_ids.update(
            str(row.get("id") or "").strip()
            for row in rows
            if str(row.get("id") or "").strip()
        )

    if identity_available:
        rows = conn.execute(
            text(
                """
                SELECT global_product_id
                FROM product_identities
                WHERE identity_type = 'gtin'
                  AND identity_value = :gtin
                """
            ),
            {"gtin": gtin},
        ).mappings().all()

        product_ids.update(
            str(row.get("global_product_id") or "").strip()
            for row in rows
            if str(row.get("global_product_id") or "").strip()
        )

    if len(product_ids) > 1:
        raise BarcodeHouseholdArticleLinkError(
            409,
            "Deze GTIN verwijst naar meerdere centrale producten.",
        )

    created = False

    if product_ids:
        product_id = next(iter(product_ids))
    else:
        product_id = str(uuid.uuid4())
        created = True

        product_values = {
            "id": product_id,
            "name": article_name or f"Product {gtin}",
            "brand": None,
            "primary_gtin": gtin,
            "source": "receipt_user_confirmed",
            "status": "active",
            "created_at": None,
            "updated_at": None,
        }

        # Datumvelden worden niet met NULL gevuld wanneer zij bestaan.
        product_values.pop("created_at", None)
        product_values.pop("updated_at", None)

        _insert_dynamic_row(
            conn,
            table_name="global_products",
            values=product_values,
        )

    if "primary_gtin" in product_columns:
        conn.execute(
            text(
                """
                UPDATE global_products
                SET primary_gtin = CASE
                        WHEN trim(COALESCE(primary_gtin, '')) = ''
                        THEN :gtin
                        ELSE primary_gtin
                    END
                WHERE id = :product_id
                """
            ),
            {
                "gtin": gtin,
                "product_id": product_id,
            },
        )

    if "name" in product_columns:
        conn.execute(
            text(
                """
                UPDATE global_products
                SET name = CASE
                        WHEN trim(COALESCE(name, '')) = ''
                        THEN :article_name
                        ELSE name
                    END
                WHERE id = :product_id
                """
            ),
            {
                "article_name": article_name or f"Product {gtin}",
                "product_id": product_id,
            },
        )

    if identity_available:
        identity_columns = _column_names(
            conn,
            "product_identities",
        )

        existing_identity = conn.execute(
            text(
                """
                SELECT id, global_product_id
                FROM product_identities
                WHERE identity_type = 'gtin'
                  AND identity_value = :gtin
                LIMIT 1
                """
            ),
            {"gtin": gtin},
        ).mappings().first()

        if existing_identity:
            existing_product_id = str(
                existing_identity.get("global_product_id") or ""
            ).strip()

            if existing_product_id != product_id:
                raise BarcodeHouseholdArticleLinkError(
                    409,
                    "De GTIN is al aan een ander centraal product gekoppeld.",
                )
        else:
            identity_values = {
                "id": str(uuid.uuid4()),
                "household_article_id": household_article_id,
                "global_product_id": product_id,
                "identity_type": "gtin",
                "identity_value": gtin,
                "source": "receipt_user_confirmed",
                "confidence_score": 1.0,
                "is_primary": 1,
            }

            _insert_dynamic_row(
                conn,
                table_name="product_identities",
                values=identity_values,
            )

        if "is_primary" in identity_columns:
            conn.execute(
                text(
                    """
                    UPDATE product_identities
                    SET is_primary = CASE
                            WHEN identity_type = 'gtin'
                             AND identity_value = :gtin
                            THEN 1
                            ELSE is_primary
                        END
                    WHERE global_product_id = :product_id
                    """
                ),
                {
                    "gtin": gtin,
                    "product_id": product_id,
                },
            )

    product = conn.execute(
        text(
            """
            SELECT id, name, brand, status, primary_gtin
            FROM global_products
            WHERE id = :product_id
            LIMIT 1
            """
        ),
        {"product_id": product_id},
    ).mappings().first()

    return {
        "created": created,
        "product": {
            "global_product_id": product_id,
            "name": product.get("name") if product else article_name,
            "brand": product.get("brand") if product else None,
            "status": product.get("status") if product else "active",
            "primary_gtin": (
                product.get("primary_gtin")
                if product
                else gtin
            ),
        },
    }


def _link_saved_product_to_household(
    conn,
    *,
    household_id: str,
    purchase_import_line_id: str,
    household_article_id: str,
    global_product_id: str,
) -> None:
    tables = _table_names(conn)

    required_tables = {
        "purchase_import_lines",
        "purchase_import_batches",
        "household_articles",
    }

    missing_tables = sorted(required_tables - tables)

    if missing_tables:
        raise BarcodeHouseholdArticleLinkError(
            500,
            "Benodigde tabel ontbreekt: " + ", ".join(missing_tables),
        )

    line_columns = _column_names(
        conn,
        "purchase_import_lines",
    )
    batch_columns = _column_names(
        conn,
        "purchase_import_batches",
    )
    article_columns = _column_names(
        conn,
        "household_articles",
    )

    line_id_column = _first_existing_column(
        line_columns,
        "id",
        "line_id",
    )
    line_batch_column = _first_existing_column(
        line_columns,
        "batch_id",
        "purchase_import_batch_id",
        "import_batch_id",
    )
    batch_id_column = _first_existing_column(
        batch_columns,
        "batch_id",
        "id",
    )

    if (
        not line_id_column
        or not line_batch_column
        or not batch_id_column
        or "household_id" not in batch_columns
    ):
        raise BarcodeHouseholdArticleLinkError(
            500,
            "De bonimporttabellen hebben niet de verwachte sleutels.",
        )

    line = conn.execute(
        text(
            f"""
            SELECT
                {line_id_column} AS line_id,
                {line_batch_column} AS batch_id
            FROM purchase_import_lines
            WHERE {line_id_column} = :line_id
            LIMIT 1
            """
        ),
        {"line_id": purchase_import_line_id},
    ).mappings().first()

    if not line:
        raise BarcodeHouseholdArticleLinkError(
            404,
            "Bonregel niet gevonden.",
        )

    batch = conn.execute(
        text(
            f"""
            SELECT {batch_id_column} AS batch_id
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
        raise BarcodeHouseholdArticleLinkError(
            404,
            "Bonregel niet gevonden binnen het actieve huishouden.",
        )

    article = conn.execute(
        text(
            """
            SELECT id, global_product_id
            FROM household_articles
            WHERE id = :article_id
              AND household_id = :household_id
            LIMIT 1
            """
        ),
        {
            "article_id": household_article_id,
            "household_id": household_id,
        },
    ).mappings().first()

    if not article:
        raise BarcodeHouseholdArticleLinkError(
            404,
            "Mijn artikel niet gevonden binnen het actieve huishouden.",
        )

    existing_product_id = str(
        article.get("global_product_id") or ""
    ).strip()

    if (
        existing_product_id
        and existing_product_id != global_product_id
    ):
        raise BarcodeHouseholdArticleLinkError(
            409,
            "Mijn artikel is al aan een ander centraal product gekoppeld.",
        )

    article_updated_fragment = (
        ", updated_at = CURRENT_TIMESTAMP"
        if "updated_at" in article_columns
        else ""
    )

    conn.execute(
        text(
            f"""
            UPDATE household_articles
            SET global_product_id = :global_product_id
                {article_updated_fragment}
            WHERE id = :article_id
              AND household_id = :household_id
            """
        ),
        {
            "global_product_id": global_product_id,
            "article_id": household_article_id,
            "household_id": household_id,
        },
    )

    mapped_article_column = _first_existing_column(
        line_columns,
        "matched_household_article_id",
        "household_article_id",
        "selected_household_article_id",
    )

    mapped_product_column = _first_existing_column(
        line_columns,
        "matched_global_product_id",
        "global_product_id",
        "selected_global_product_id",
    )

    update_parts = []
    parameters = {
        "line_id": purchase_import_line_id,
        "article_id": household_article_id,
        "global_product_id": global_product_id,
    }

    if mapped_article_column:
        update_parts.append(
            f"{mapped_article_column} = :article_id"
        )

    if mapped_product_column:
        update_parts.append(
            f"{mapped_product_column} = :global_product_id"
        )

    if update_parts:
        conn.execute(
            text(
                f"""
                UPDATE purchase_import_lines
                SET {", ".join(update_parts)}
                WHERE {line_id_column} = :line_id
                """
            ),
            parameters,
        )


def save_gtin_catalog_and_household_link(
    conn,
    *,
    household_id: str,
    purchase_import_line_id: str,
    household_article_id: str,
    gtin: str,
    article_name: str,
) -> dict[str, Any]:
    """Sla een geldige GTIN centraal op en koppel die lokaal."""

    validation = validate_barcode(gtin, "gtin")

    if not validation.get("valid"):
        raise BarcodeHouseholdArticleLinkError(
            400,
            "De barcode is niet geldig.",
        )

    normalized_gtin = str(
        validation.get("normalized_value") or ""
    ).strip()

    normalized_household_id = str(
        household_id or ""
    ).strip()
    normalized_line_id = str(
        purchase_import_line_id or ""
    ).strip()
    normalized_article_id = str(
        household_article_id or ""
    ).strip()
    normalized_article_name = " ".join(
        str(article_name or "").strip().split()
    )

    if not normalized_household_id:
        raise BarcodeHouseholdArticleLinkError(
            400,
            "Het actieve huishouden ontbreekt.",
        )

    if not normalized_line_id or not normalized_article_id:
        raise BarcodeHouseholdArticleLinkError(
            400,
            "Bonregel en Mijn artikel zijn verplicht.",
        )

    tables = _table_names(conn)
    inventory_event_count = None

    if "inventory_events" in tables:
        inventory_event_count = conn.execute(
            text("SELECT COUNT(*) FROM inventory_events")
        ).scalar_one()

    catalog_result = _resolve_catalog_product_for_save(
        conn,
        gtin=normalized_gtin,
        article_name=normalized_article_name,
        household_article_id=normalized_article_id,
    )

    product = catalog_result["product"]
    product_id = str(
        product.get("global_product_id") or ""
    ).strip()

    _link_saved_product_to_household(
        conn,
        household_id=normalized_household_id,
        purchase_import_line_id=normalized_line_id,
        household_article_id=normalized_article_id,
        global_product_id=product_id,
    )

    if "inventory_events" in tables:
        inventory_event_count_after = conn.execute(
            text("SELECT COUNT(*) FROM inventory_events")
        ).scalar_one()

        if inventory_event_count_after != inventory_event_count:
            raise BarcodeHouseholdArticleLinkError(
                500,
                "De barcodeopslag heeft onverwacht de voorraad gewijzigd.",
            )

    return {
        "ok": True,
        "gtin": normalized_gtin,
        "catalog_product_created": bool(
            catalog_result.get("created")
        ),
        "product": product,
        "purchase_import_line_id": normalized_line_id,
        "household_article_id": normalized_article_id,
        "inventory_mutated": False,
    }

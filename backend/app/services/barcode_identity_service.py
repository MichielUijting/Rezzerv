"""Central, read-only barcode and GTIN validation/lookup service.

Domain rules:
- retailer article numbers are never interpreted as GTINs;
- only GTIN-8, GTIN-12, GTIN-13 and GTIN-14 are accepted;
- GTIN check digits are validated with the GS1 modulo-10 algorithm;
- validation and lookup never mutate products, identities, household articles or stock.
"""

from __future__ import annotations

import re
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

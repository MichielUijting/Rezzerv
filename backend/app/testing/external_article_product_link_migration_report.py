"""Read-only migratierapport voor algemene winkelartikelkoppelingen.

Dit rapport leest uitsluitend bestaande tabellen. Het maakt geen schema aan,
voert geen INSERT/UPDATE/DELETE uit en commit niets.

Uitvoeren in de actuele backendcontainer:

    python -m app.testing.external_article_product_link_migration_report
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.external_article_product_link_service import (
    normalize_external_link_article_code,
    normalize_external_link_receipt_text,
    normalize_external_link_retailer_code,
)

CONFIRMED_CANDIDATE_STATUSES = {"linked_to_catalog", "confirmed"}
TEST_MARKERS = ("test", "regression", "pseudo", "fixture", "contract")


def _table_exists(conn, table_name: str) -> bool:
    return bool(
        conn.execute(
            text(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table' AND name = :table_name
                LIMIT 1
                """
            ),
            {"table_name": table_name},
        ).scalar()
    )


def _columns(conn, table_name: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
    return {str(row["name"]) for row in rows}


def _value(row: dict[str, Any], key: str) -> Any:
    return row.get(key) if key in row else None


def _looks_like_test_record(row: dict[str, Any]) -> bool:
    values = [
        _value(row, "id"),
        _value(row, "receipt_line_id"),
        _value(row, "purchase_import_line_id"),
        _value(row, "context_key"),
        _value(row, "receipt_line_text"),
        _value(row, "candidate_name"),
        _value(row, "created_by"),
    ]
    haystack = " ".join(str(value or "").lower() for value in values)
    return any(marker in haystack for marker in TEST_MARKERS)


def _canonical_candidate(row: dict[str, Any]) -> dict[str, Any]:
    retailer = normalize_external_link_retailer_code(_value(row, "retailer_code"))
    receipt_text = normalize_external_link_receipt_text(_value(row, "receipt_line_text"))

    # candidate_source_product_code en retailer_article_number zijn vaak de GTIN
    # van het gekozen universele artikel. Zij zijn daarom niet automatisch een
    # winkelartikelcode. Alleen een expliciete external_article_code mag als
    # algemene winkelsleutel worden gebruikt wanneer die kolom bestaat.
    article_code = normalize_external_link_article_code(
        _value(row, "external_article_code")
    )

    return {
        "candidate_id": str(_value(row, "id") or ""),
        "retailer_code": retailer,
        "receipt_text_normalized": receipt_text,
        "external_article_code": article_code,
        "global_product_id": str(_value(row, "global_product_id") or "").strip(),
        "global_product_name": _value(row, "global_product_name"),
        "global_product_status": str(_value(row, "global_product_status") or "").lower(),
        "candidate_status": str(
            _value(row, "candidate_status") or _value(row, "status") or ""
        ).lower(),
        "is_user_confirmed": bool(_value(row, "is_user_confirmed")),
        "created_by": _value(row, "created_by"),
        "created_at": _value(row, "created_at"),
        "updated_at": _value(row, "updated_at"),
        "source_receipt_line_id": _value(row, "receipt_line_id"),
        "source_purchase_import_line_id": _value(row, "purchase_import_line_id"),
        "source_context_key": _value(row, "context_key"),
        "is_test_record": _looks_like_test_record(row),
    }


def _business_key(candidate: dict[str, Any]) -> tuple[str, str, str]:
    return (
        candidate["retailer_code"],
        candidate["external_article_code"],
        candidate["receipt_text_normalized"],
    )


def _print_section(title: str, rows: list[dict[str, Any]]) -> None:
    print()
    print(f"=== {title} ({len(rows)}) ===")
    if not rows:
        print("Geen records.")
        return
    for row in rows:
        print(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str))


def run_report() -> None:
    with engine.connect() as conn:
        if not _table_exists(conn, "external_product_candidates"):
            raise RuntimeError("Tabel external_product_candidates bestaat niet")
        if not _table_exists(conn, "global_products"):
            raise RuntimeError("Tabel global_products bestaat niet")

        candidate_columns = _columns(conn, "external_product_candidates")
        required = {
            "id",
            "retailer_code",
            "receipt_line_text",
            "global_product_id",
            "is_user_confirmed",
        }
        missing = sorted(required - candidate_columns)
        if missing:
            raise RuntimeError(
                "Verplichte kandidaatkolommen ontbreken: " + ", ".join(missing)
            )

        optional_candidate_columns = [
            "receipt_line_id",
            "purchase_import_line_id",
            "context_key",
            "external_article_code",
            "candidate_name",
            "candidate_status",
            "status",
            "created_by",
            "created_at",
            "updated_at",
        ]
        selected_optional = [
            column for column in optional_candidate_columns if column in candidate_columns
        ]
        select_optional = "".join(f", epc.{column}" for column in selected_optional)

        raw_rows = conn.execute(
            text(
                f"""
                SELECT
                    epc.id,
                    epc.retailer_code,
                    epc.receipt_line_text,
                    epc.global_product_id,
                    epc.is_user_confirmed
                    {select_optional},
                    gp.name AS global_product_name,
                    gp.status AS global_product_status
                FROM external_product_candidates epc
                LEFT JOIN global_products gp ON gp.id = epc.global_product_id
                WHERE epc.is_user_confirmed = 1
                   OR epc.global_product_id IS NOT NULL
                ORDER BY COALESCE(epc.updated_at, epc.created_at, '') DESC, epc.id
                """
            )
        ).mappings().all()

        candidates = [_canonical_candidate(dict(row)) for row in raw_rows]

        excluded_test: list[dict[str, Any]] = []
        invalid: list[dict[str, Any]] = []
        eligible: list[dict[str, Any]] = []

        for candidate in candidates:
            reasons: list[str] = []
            if candidate["is_test_record"]:
                excluded_test.append(candidate)
                continue
            if not candidate["is_user_confirmed"]:
                reasons.append("niet door gebruiker bevestigd")
            if candidate["candidate_status"] not in CONFIRMED_CANDIDATE_STATUSES:
                reasons.append("status is niet bevestigd/linked_to_catalog")
            if not candidate["global_product_id"]:
                reasons.append("global_product_id ontbreekt")
            if not candidate["global_product_name"]:
                reasons.append("universeel artikel bestaat niet")
            if candidate["global_product_status"] != "active":
                reasons.append("universeel artikel is niet actief")
            if not candidate["retailer_code"]:
                reasons.append("retailer_code ontbreekt")
            if not candidate["external_article_code"] and not candidate["receipt_text_normalized"]:
                reasons.append("geen stabiele winkelartikelcode of bontekst")

            if reasons:
                invalid.append({**candidate, "reasons": reasons})
            else:
                eligible.append(candidate)

        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for candidate in eligible:
            grouped[_business_key(candidate)].append(candidate)

        conflicts: list[dict[str, Any]] = []
        unique_eligible: list[dict[str, Any]] = []
        duplicates_same_product: list[dict[str, Any]] = []

        for key, group in sorted(grouped.items()):
            product_ids = sorted({item["global_product_id"] for item in group})
            if len(product_ids) > 1:
                conflicts.append(
                    {
                        "retailer_code": key[0],
                        "external_article_code": key[1],
                        "receipt_text_normalized": key[2],
                        "global_product_ids": product_ids,
                        "candidate_ids": [item["candidate_id"] for item in group],
                    }
                )
                continue
            newest = sorted(
                group,
                key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
                reverse=True,
            )[0]
            unique_eligible.append(newest)
            if len(group) > 1:
                duplicates_same_product.append(
                    {
                        "retailer_code": key[0],
                        "external_article_code": key[1],
                        "receipt_text_normalized": key[2],
                        "global_product_id": product_ids[0],
                        "candidate_ids": [item["candidate_id"] for item in group],
                    }
                )

        existing_links: list[dict[str, Any]] = []
        if _table_exists(conn, "external_article_product_links"):
            existing_links = [
                dict(row)
                for row in conn.execute(
                    text(
                        """
                        SELECT retailer_code, receipt_text_normalized,
                               external_article_code, global_product_id, status
                        FROM external_article_product_links
                        WHERE status = 'confirmed'
                        """
                    )
                ).mappings().all()
            ]

        existing_by_key = {
            (
                str(row.get("retailer_code") or ""),
                str(row.get("external_article_code") or ""),
                str(row.get("receipt_text_normalized") or ""),
            ): str(row.get("global_product_id") or "")
            for row in existing_links
        }

        already_present: list[dict[str, Any]] = []
        migration_conflicts: list[dict[str, Any]] = []
        safe_to_migrate: list[dict[str, Any]] = []

        for candidate in unique_eligible:
            key = _business_key(candidate)
            existing_product_id = existing_by_key.get(key)
            if existing_product_id == candidate["global_product_id"]:
                already_present.append(candidate)
            elif existing_product_id:
                migration_conflicts.append(
                    {
                        **candidate,
                        "existing_global_product_id": existing_product_id,
                        "reason": "centrale actieve koppeling wijst naar ander universeel artikel",
                    }
                )
            else:
                safe_to_migrate.append(candidate)

        print("READ-ONLY MIGRATIERAPPORT ALGEMENE WINKELARTIKELKOPPELINGEN")
        print("Geen INSERT, UPDATE, DELETE of schemawijziging uitgevoerd.")
        print()
        print("=== SAMENVATTING ===")
        summary = {
            "gelezen_kandidaatrecords": len(candidates),
            "uitgesloten_test_of_regressie": len(excluded_test),
            "ongeldig_of_onvoldoende_bewijs": len(invalid),
            "conflicterende_bevestigingen": len(conflicts),
            "dubbele_bevestigingen_zelfde_product": len(duplicates_same_product),
            "reeds_centraal_aanwezig": len(already_present),
            "conflict_met_bestaande_centrale_koppeling": len(migration_conflicts),
            "veilig_migreerbaar": len(safe_to_migrate),
        }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))

        _print_section("VEILIG MIGREERBAAR", safe_to_migrate)
        _print_section("REEDS CENTRAAL AANWEZIG", already_present)
        _print_section("CONFLICTERENDE BEVESTIGINGEN", conflicts)
        _print_section("CONFLICT MET CENTRALE KOPPELING", migration_conflicts)
        _print_section("DUBBEL, ZELFDE PRODUCT", duplicates_same_product)
        _print_section("ONGELDIG OF ONVOLDOENDE BEWIJS", invalid)
        _print_section("UITGESLOTEN TEST/REGRESSIE", excluded_test)

        print()
        print("READ-ONLY RAPPORT VOLTOOID")


if __name__ == "__main__":
    run_report()

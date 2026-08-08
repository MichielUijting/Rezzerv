"""Gecontroleerde eenmalige migratie van beoordeelde algemene koppelingen.

Deze migratie leest uitsluitend het expliciet beoordeelde JSON-manifest. Zij stopt
veilig zodra manifest, kandidaat, universeel artikel of bestaande centrale
koppeling afwijkt. Herhaald uitvoeren is idempotent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.external_article_product_link_domain_service import (
    confirm_global_external_article_product_link,
    find_global_external_article_product_link,
)
from app.services.external_article_product_link_service import (
    normalize_external_link_receipt_text,
    normalize_external_link_retailer_code,
)

MANIFEST_PATH = Path(__file__).with_name(
    "external_article_product_link_migration_manifest.json"
)
EXPECTED_MANIFEST_VERSION = "1.0"
EXPECTED_MODE = "explicit_reviewed_allowlist"
EXPECTED_APPROVED_COUNT = 1


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _load_manifest() -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    _require(
        manifest.get("manifest_version") == EXPECTED_MANIFEST_VERSION,
        "Onverwachte manifestversie",
    )
    _require(manifest.get("mode") == EXPECTED_MODE, "Onverwachte manifestmodus")
    approved = manifest.get("approved_for_migration")
    _require(isinstance(approved, list), "Manifest bevat geen geldige allowlist")
    _require(
        len(approved) == EXPECTED_APPROVED_COUNT,
        "Manifest bevat niet exact één goedgekeurde migratie",
    )
    _require(not manifest.get("conflicts"), "Manifest bevat conflicten")

    constraints = manifest.get("constraints") or {}
    for key in (
        "no_household_scope",
        "no_receipt_scope",
        "no_candidate_gtin_as_retailer_article_code",
        "requires_active_global_product",
        "requires_exact_candidate_id_match",
    ):
        _require(constraints.get(key) is True, f"Verplichte manifestregel ontbreekt: {key}")
    return manifest


def _read_candidate(conn, candidate_id: str) -> dict[str, Any]:
    row = conn.execute(
        text(
            """
            SELECT
                epc.id,
                epc.retailer_code,
                epc.receipt_line_text,
                epc.global_product_id,
                epc.is_user_confirmed,
                COALESCE(epc.candidate_status, epc.status, '') AS candidate_status,
                gp.name AS global_product_name,
                COALESCE(gp.status, '') AS global_product_status
            FROM external_product_candidates epc
            LEFT JOIN global_products gp ON gp.id = epc.global_product_id
            WHERE epc.id = :candidate_id
            LIMIT 1
            """
        ),
        {"candidate_id": candidate_id},
    ).mappings().first()
    _require(row is not None, "Goedgekeurde kandidaat bestaat niet meer")
    return dict(row)


def run_migration() -> None:
    manifest = _load_manifest()
    approved = manifest["approved_for_migration"][0]

    candidate_id = str(approved["candidate_id"])
    expected_retailer = str(approved["retailer_code"])
    expected_text = str(approved["receipt_text_normalized"])
    expected_code = str(approved.get("external_article_code") or "")
    expected_product_id = str(approved["global_product_id"])
    expected_product_name = str(approved["global_product_name"])

    with engine.begin() as conn:
        candidate = _read_candidate(conn, candidate_id)

        actual_retailer = normalize_external_link_retailer_code(
            candidate.get("retailer_code")
        )
        actual_text = normalize_external_link_receipt_text(
            candidate.get("receipt_line_text")
        )
        actual_product_id = str(candidate.get("global_product_id") or "")
        actual_product_name = str(candidate.get("global_product_name") or "")
        actual_status = str(candidate.get("candidate_status") or "").lower()
        actual_product_status = str(
            candidate.get("global_product_status") or ""
        ).lower()

        _require(bool(candidate.get("is_user_confirmed")), "Kandidaat is niet meer bevestigd")
        _require(
            actual_status in {"linked_to_catalog", "confirmed"},
            "Kandidaatstatus is niet meer bevestigd",
        )
        _require(actual_retailer == expected_retailer, "Winkelcode wijkt af van manifest")
        _require(actual_text == expected_text, "Bontekst wijkt af van manifest")
        _require(expected_code == "", "Manifest bevat onverwacht winkelartikelnummer")
        _require(actual_product_id == expected_product_id, "Product-ID wijkt af van manifest")
        _require(actual_product_name == expected_product_name, "Productnaam wijkt af van manifest")
        _require(actual_product_status == "active", "Universeel artikel is niet actief")

        existing = find_global_external_article_product_link(
            conn,
            retailer_code=expected_retailer,
            receipt_text=expected_text,
            external_article_code=expected_code,
        )

        if existing:
            _require(
                existing["global_product_id"] == expected_product_id,
                "Bestaande centrale koppeling wijst naar een ander universeel artikel",
            )
            result = existing
            outcome = "AL_REEDS_CENTRAAL_AANWEZIG"
        else:
            result = confirm_global_external_article_product_link(
                conn,
                retailer_code=expected_retailer,
                receipt_text=expected_text,
                external_article_code=expected_code,
                global_product_id=expected_product_id,
                confirmed_by="reviewed-migration-step-3",
                source_candidate_id=candidate_id,
            )
            outcome = "GEMIGREERD"

        active_count = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM external_article_product_links
                WHERE retailer_code = :retailer_code
                  AND receipt_text_normalized = :receipt_text_normalized
                  AND status = 'confirmed'
                """
            ),
            {
                "retailer_code": expected_retailer,
                "receipt_text_normalized": expected_text,
            },
        ).scalar_one()
        _require(active_count == 1, "Na migratie bestaat niet exact één actieve koppeling")

        smoke_count = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM external_article_product_links
                WHERE source_candidate_id IN (
                    'm2c2i22-smoke-candidate',
                    'm2c2i23-smoke-candidate'
                )
                """
            )
        ).scalar_one()
        _require(smoke_count == 0, "Een uitgesloten smoketestrecord is toch gemigreerd")

    print("STAP 3 MIGRATIE VOLTOOID")
    print(f"UITKOMST={outcome}")
    print(f"CANDIDATE_ID={candidate_id}")
    print(f"RETAILER_CODE={result['retailer_code']}")
    print(f"RECEIPT_TEXT_NORMALIZED={result['receipt_text_normalized']}")
    print(f"GLOBAL_PRODUCT_ID={result['global_product_id']}")
    print(f"GLOBAL_PRODUCT_NAME={result['global_product_name']}")
    print("ACTIEVE_KOPPELINGEN=1")
    print("SMOKETESTKOPPELINGEN=0")


if __name__ == "__main__":
    run_migration()

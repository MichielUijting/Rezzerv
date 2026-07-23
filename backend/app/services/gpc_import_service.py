from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.product_inventory_group_store import ensure_product_inventory_group_schema

GS1_GPC_HEADERS = {"Referer": "https://gpc-browser.gs1.org/"}
GS1_GPC_LANGUAGES_URL = "https://gpc-api.gs1.org/api/browser/language/all"
GS1_GPC_PUBLICATIONS_URL = "https://gpc-api.gs1.org/api/browser/publication?languageId={language_id}"
GS1_GPC_DOWNLOAD_URL = "https://gpc-api.gs1.org/api/blob/download/publication/{publication_id}/json"
GS1_GPC_DYNAMIC_DOWNLOAD_URL = "https://gpc-api.gs1.org/api/blob/dynamic/download/publication/{publication_id}/json"

GPC_PRODUCT_GROUPS_SQL = """
CREATE TABLE IF NOT EXISTS gpc_product_groups (
    gpc_brick_code TEXT PRIMARY KEY,
    gpc_brick_name TEXT NOT NULL,
    gpc_class_code TEXT,
    gpc_class_name TEXT,
    gpc_family_code TEXT,
    gpc_family_name TEXT,
    gpc_segment_code TEXT,
    gpc_segment_name TEXT,
    language_code TEXT DEFAULT 'nl',
    source_version TEXT,
    active INTEGER DEFAULT 1,
    created_at TEXT,
    updated_at TEXT
)
"""

GPC_PRODUCT_GROUPS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_gpc_product_groups_hierarchy
ON gpc_product_groups (gpc_family_code, gpc_class_code, gpc_brick_code)
"""

PRODUCT_INVENTORY_GROUP_GPC_COLUMNS: dict[str, str] = {
    "gpc_family_code": "TEXT",
    "gpc_family_name": "TEXT",
    "gpc_class_code": "TEXT",
    "gpc_class_name": "TEXT",
    "gpc_brick_code": "TEXT",
    "source": "TEXT",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_json(url: str, timeout: int = 60) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=GS1_GPC_HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _api_result(payload: dict[str, Any]) -> Any:
    if not bool(payload.get("isSuccess", False)):
        raise RuntimeError(f"GS1 GPC API gaf geen successtatus: {payload.get('statusCode')}")
    return payload.get("result")


def _fetch_language(language_code: str = "nl") -> dict[str, Any]:
    result = _api_result(_get_json(GS1_GPC_LANGUAGES_URL, timeout=30))
    requested = language_code.lower().strip()
    for language in result or []:
        candidates = {
            str(language.get("countryCode") or "").lower(),
            str(language.get("culture") or "").lower(),
            str(language.get("languageCode") or "").lower(),
            str(language.get("languageName") or "").lower(),
        }
        if requested in candidates:
            return language
    raise RuntimeError(f"GS1 GPC taal '{language_code}' niet gevonden")


def _fetch_latest_publication(language_id: int) -> dict[str, Any]:
    result = _api_result(_get_json(GS1_GPC_PUBLICATIONS_URL.format(language_id=language_id), timeout=30))
    publications = list(result or [])
    if not publications:
        raise RuntimeError("Geen GS1 GPC-publicaties gevonden voor Nederlands")
    return publications[0]


def _fetch_publication_json(publication_id: int) -> dict[str, Any]:
    urls = [
        GS1_GPC_DOWNLOAD_URL.format(publication_id=publication_id),
        GS1_GPC_DYNAMIC_DOWNLOAD_URL.format(publication_id=publication_id),
    ]
    last_error: Exception | None = None
    for url in urls:
        try:
            return _get_json(url, timeout=180)
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 404:
                continue
            raise
    raise RuntimeError(f"GS1 GPC-publicatie kon niet worden gedownload: {last_error}")


def _ensure_gpc_schema(conn) -> None:
    conn.execute(text(GPC_PRODUCT_GROUPS_SQL))
    conn.execute(text(GPC_PRODUCT_GROUPS_INDEX_SQL))
    existing_columns = {str(row.get("name") or "") for row in conn.execute(text("PRAGMA table_info(product_inventory_groups)")).mappings().all()}
    for column_name, column_definition in PRODUCT_INVENTORY_GROUP_GPC_COLUMNS.items():
        if column_name not in existing_columns:
            conn.execute(text(f"ALTER TABLE product_inventory_groups ADD COLUMN {column_name} {column_definition}"))


def _walk_schema(schema: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for segment in schema or []:
        segment_code = str(segment.get("Code") or "").strip()
        segment_name = str(segment.get("Title") or "").strip()
        for family in segment.get("Childs") or []:
            family_code = str(family.get("Code") or "").strip()
            family_name = str(family.get("Title") or "").strip()
            for class_item in family.get("Childs") or []:
                class_code = str(class_item.get("Code") or "").strip()
                class_name = str(class_item.get("Title") or "").strip()
                for brick in class_item.get("Childs") or []:
                    brick_code = str(brick.get("Code") or "").strip()
                    brick_name = str(brick.get("Title") or "").strip()
                    if not brick_code or not brick_name:
                        continue
                    rows.append({
                        "gpc_segment_code": segment_code,
                        "gpc_segment_name": segment_name,
                        "gpc_family_code": family_code,
                        "gpc_family_name": family_name,
                        "gpc_class_code": class_code,
                        "gpc_class_name": class_name,
                        "gpc_brick_code": brick_code,
                        "gpc_brick_name": brick_name,
                    })
    return rows


def _upsert_gpc_row(conn, row: dict[str, str], language_code: str, source_version: str, timestamp: str) -> str:
    existing = conn.execute(
        text("SELECT gpc_brick_code FROM gpc_product_groups WHERE gpc_brick_code = :gpc_brick_code LIMIT 1"),
        row,
    ).mappings().first()
    params = {**row, "language_code": language_code, "source_version": source_version, "created_at": timestamp, "updated_at": timestamp}
    if existing:
        conn.execute(text("""
            UPDATE gpc_product_groups
            SET gpc_brick_name = :gpc_brick_name,
                gpc_class_code = :gpc_class_code,
                gpc_class_name = :gpc_class_name,
                gpc_family_code = :gpc_family_code,
                gpc_family_name = :gpc_family_name,
                gpc_segment_code = :gpc_segment_code,
                gpc_segment_name = :gpc_segment_name,
                language_code = :language_code,
                source_version = :source_version,
                active = 1,
                updated_at = :updated_at
            WHERE gpc_brick_code = :gpc_brick_code
        """), params)
        return "updated"
    conn.execute(text("""
        INSERT INTO gpc_product_groups (
            gpc_brick_code, gpc_brick_name,
            gpc_class_code, gpc_class_name,
            gpc_family_code, gpc_family_name,
            gpc_segment_code, gpc_segment_name,
            language_code, source_version, active, created_at, updated_at
        ) VALUES (
            :gpc_brick_code, :gpc_brick_name,
            :gpc_class_code, :gpc_class_name,
            :gpc_family_code, :gpc_family_name,
            :gpc_segment_code, :gpc_segment_name,
            :language_code, :source_version, 1, :created_at, :updated_at
        )
    """), params)
    return "created"


def _upsert_rezzerv_product_group(conn, row: dict[str, str], timestamp: str) -> str:
    inventory_group_key = f"gpc:{row['gpc_brick_code']}"
    existing = conn.execute(
        text("SELECT inventory_group_key FROM product_inventory_groups WHERE inventory_group_key = :inventory_group_key LIMIT 1"),
        {"inventory_group_key": inventory_group_key},
    ).mappings().first()
    params = {
        "inventory_group_key": inventory_group_key,
        "display_name": row["gpc_brick_name"],
        "default_base_unit": "stuk",
        "gpc_family_code": row["gpc_family_code"],
        "gpc_family_name": row["gpc_family_name"],
        "gpc_class_code": row["gpc_class_code"],
        "gpc_class_name": row["gpc_class_name"],
        "gpc_brick_code": row["gpc_brick_code"],
        "source": "gs1_gpc_nl",
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    if existing:
        conn.execute(text("""
            UPDATE product_inventory_groups
            SET display_name = :display_name,
                default_base_unit = COALESCE(NULLIF(default_base_unit, ''), :default_base_unit),
                aggregation_mode = COALESCE(NULLIF(aggregation_mode, ''), 'sum_quantity'),
                gpc_family_code = :gpc_family_code,
                gpc_family_name = :gpc_family_name,
                gpc_class_code = :gpc_class_code,
                gpc_class_name = :gpc_class_name,
                gpc_brick_code = :gpc_brick_code,
                source = :source,
                active = 1,
                updated_at = :updated_at
            WHERE inventory_group_key = :inventory_group_key
        """), params)
        return "updated"
    conn.execute(text("""
        INSERT INTO product_inventory_groups (
            inventory_group_key, display_name, default_base_unit, aggregation_mode, active,
            gpc_family_code, gpc_family_name, gpc_class_code, gpc_class_name, gpc_brick_code, source,
            created_at, updated_at
        ) VALUES (
            :inventory_group_key, :display_name, :default_base_unit, 'sum_quantity', 1,
            :gpc_family_code, :gpc_family_name, :gpc_class_code, :gpc_class_name, :gpc_brick_code, :source,
            :created_at, :updated_at
        )
    """), params)
    return "created"


def import_gs1_gpc_nl() -> dict[str, Any]:
    """Import Dutch GS1 GPC as central Rezzerv application reference data.

    This is intentionally not household-specific and does not mutate inventory.
    """
    ensure_product_inventory_group_schema()
    language = _fetch_language("nl")
    publication = _fetch_latest_publication(int(language.get("languageId")))
    publication_id = int(publication.get("publicationId"))
    source_version = str(publication.get("version") or publication.get("publicationName") or "unknown")
    payload = _fetch_publication_json(publication_id)
    schema = payload.get("Schema") or []
    rows = _walk_schema(schema)
    if not rows:
        raise RuntimeError("GS1 GPC-publicatie bevat geen Brick-records")

    timestamp = now_iso()
    stats = {
        "gpc_created": 0,
        "gpc_updated": 0,
        "product_groups_created": 0,
        "product_groups_updated": 0,
    }
    with engine.begin() as conn:
        _ensure_gpc_schema(conn)
        for row in rows:
            gpc_action = _upsert_gpc_row(conn, row, "nl", source_version, timestamp)
            stats[f"gpc_{gpc_action}"] += 1
            product_group_action = _upsert_rezzerv_product_group(conn, row, timestamp)
            stats[f"product_groups_{product_group_action}"] += 1

    return {
        "ok": True,
        "source": "gs1_gpc_api",
        "language_code": "nl",
        "publication_id": publication_id,
        "source_version": source_version,
        "total_bricks": len(rows),
        "total_families": len({row["gpc_family_code"] for row in rows}),
        "total_classes": len({row["gpc_class_code"] for row in rows}),
        "mutates_inventory": False,
        **stats,
    }


def require_admin_key(header_value: str | None) -> None:
    configured = os.getenv("REZZERV_ADMIN_API_KEY", "").strip()
    if not configured:
        return
    supplied = str(header_value or "").strip()
    if supplied != configured:
        raise PermissionError("Admin-autorisatie ontbreekt of is ongeldig")

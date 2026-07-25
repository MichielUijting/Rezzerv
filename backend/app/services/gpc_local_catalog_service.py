from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text

from app.db import engine
from app.services.product_inventory_group_store import ensure_product_inventory_group_schema

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "gpc_bricks_2026_05_en.json"
SOURCE = "gs1_gpc_2026_05_en"
VERSION = "2026-05-20"

DUTCH_DISPLAY_OVERRIDES = {
    "10005895": "Appelbananen",
    "10005896": "Babybananen",
    "10005897": "Bananen",
    "10005898": "Bakbananen",
    "10005899": "Rode bananen",
    "10006111": "Zoete aardappelen",
    "10006835": "Stengels van zoete aardappel",
}

PHRASE_TRANSLATIONS = {
    "zoete aardappelen": "sweet potatoes",
    "zoete aardappel": "sweet potato",
    "rode bananen": "red bananas",
    "rode banaan": "red banana",
    "babybananen": "baby bananas",
    "baby bananen": "baby bananas",
    "bakbananen": "plantain bananas",
    "bakbanaan": "plantain banana",
    "appelbananen": "apple bananas",
    "appelbanaan": "apple banana",
    "bananen": "bananas",
    "banaan": "banana",
}

STOP_WORDS = {
    "ah", "jumbo", "lidl", "aldi", "plus", "coop", "dirk", "deka", "markt",
    "bio", "biologisch", "organic", "vers", "verse", "fresh", "stuks", "stuk",
    "gram", "kilogram", "kg", "g", "ml", "cl", "dl", "liter", "l",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _columns(table_name: str) -> set[str]:
    try:
        return {str(column.get("name") or "") for column in inspect(engine).get_columns(table_name)}
    except Exception:
        return set()


def _ensure_column(conn, table_name: str, name: str, definition: str) -> None:
    if name not in _columns(table_name):
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {name} {definition}"))


def ensure_local_gpc_schema() -> None:
    ensure_product_inventory_group_schema()
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS gpc_product_groups (
                gpc_brick_code TEXT PRIMARY KEY,
                gpc_brick_name TEXT NOT NULL,
                gpc_class_code TEXT,
                gpc_class_name TEXT,
                gpc_family_code TEXT,
                gpc_family_name TEXT,
                gpc_segment_code TEXT,
                gpc_segment_name TEXT,
                language_code TEXT,
                source_version TEXT,
                active INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            )
        """))
        for name, definition in {
            "gpc_brick_name_en": "TEXT",
            "gpc_class_name_en": "TEXT",
            "gpc_family_name_en": "TEXT",
            "gpc_segment_name_en": "TEXT",
            "brick_definition_includes_en": "TEXT",
            "brick_definition_excludes_en": "TEXT",
            "source": "TEXT",
        }.items():
            _ensure_column(conn, "gpc_product_groups", name, definition)
        for name, definition in {
            "gpc_family_code": "TEXT", "gpc_family_name": "TEXT",
            "gpc_class_code": "TEXT", "gpc_class_name": "TEXT",
            "gpc_brick_code": "TEXT", "source": "TEXT",
        }.items():
            _ensure_column(conn, "product_inventory_groups", name, definition)


def import_bundled_gpc_catalog() -> dict[str, Any]:
    ensure_local_gpc_schema()
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    rows = payload.get("bricks") or []
    timestamp = _now()
    created = updated = 0
    with engine.begin() as conn:
        for row in rows:
            code = str(row.get("gpc_brick_code") or "").strip()
            title_en = str(row.get("gpc_brick_name_en") or "").strip()
            if not re.fullmatch(r"\d{8}", code) or not title_en:
                continue
            display_name = DUTCH_DISPLAY_OVERRIDES.get(code, title_en)
            existing = conn.execute(text(
                "SELECT gpc_brick_code FROM gpc_product_groups WHERE gpc_brick_code=:code LIMIT 1"
            ), {"code": code}).first()
            params = {
                "code": code, "title": display_name, "title_en": title_en,
                "class_code": row.get("gpc_class_code"), "class_name": row.get("gpc_class_name_en"),
                "family_code": row.get("gpc_family_code"), "family_name": row.get("gpc_family_name_en"),
                "segment_code": row.get("gpc_segment_code"), "segment_name": row.get("gpc_segment_name_en"),
                "includes": row.get("brick_definition_includes_en"),
                "excludes": row.get("brick_definition_excludes_en"),
                "version": payload.get("version") or VERSION, "source": SOURCE,
                "timestamp": timestamp,
            }
            if existing:
                conn.execute(text("""
                    UPDATE gpc_product_groups SET
                      gpc_brick_name=CASE WHEN language_code='nl' THEN gpc_brick_name ELSE :title END,
                      gpc_brick_name_en=:title_en, gpc_class_code=:class_code,
                      gpc_class_name_en=:class_name, gpc_family_code=:family_code,
                      gpc_family_name_en=:family_name, gpc_segment_code=:segment_code,
                      gpc_segment_name_en=:segment_name,
                      brick_definition_includes_en=:includes,
                      brick_definition_excludes_en=:excludes, source_version=:version,
                      source=:source, active=1, updated_at=:timestamp
                    WHERE gpc_brick_code=:code
                """), params)
                updated += 1
            else:
                conn.execute(text("""
                    INSERT INTO gpc_product_groups (
                      gpc_brick_code,gpc_brick_name,gpc_brick_name_en,
                      gpc_class_code,gpc_class_name,gpc_class_name_en,
                      gpc_family_code,gpc_family_name,gpc_family_name_en,
                      gpc_segment_code,gpc_segment_name,gpc_segment_name_en,
                      brick_definition_includes_en,brick_definition_excludes_en,
                      language_code,source_version,source,active,created_at,updated_at
                    ) VALUES (
                      :code,:title,:title_en,:class_code,:class_name,:class_name,
                      :family_code,:family_name,:family_name,:segment_code,:segment_name,:segment_name,
                      :includes,:excludes,'en',:version,:source,1,:timestamp,:timestamp
                    )
                """), params)
                created += 1

            key = f"gpc:{code}"
            existing_group = conn.execute(text(
                "SELECT inventory_group_key, source FROM product_inventory_groups WHERE inventory_group_key=:key LIMIT 1"
            ), {"key": key}).mappings().first()
            group_params = {**params, "key": key, "display_name": display_name}
            if existing_group:
                conn.execute(text("""
                    UPDATE product_inventory_groups SET
                      display_name=CASE WHEN source='gs1_gpc_nl' THEN display_name ELSE :display_name END,
                      gpc_family_code=:family_code,
                      gpc_family_name=COALESCE(NULLIF(gpc_family_name,''),:family_name),
                      gpc_class_code=:class_code,
                      gpc_class_name=COALESCE(NULLIF(gpc_class_name,''),:class_name),
                      gpc_brick_code=:code,
                      source=CASE WHEN source='gs1_gpc_nl' THEN source ELSE :source END,
                      active=1, updated_at=:timestamp
                    WHERE inventory_group_key=:key
                """), group_params)
            else:
                conn.execute(text("""
                    INSERT INTO product_inventory_groups (
                      inventory_group_key,display_name,default_base_unit,aggregation_mode,active,
                      gpc_family_code,gpc_family_name,gpc_class_code,gpc_class_name,gpc_brick_code,source,
                      created_at,updated_at
                    ) VALUES (
                      :key,:display_name,'stuk','sum_quantity',1,
                      :family_code,:family_name,:class_code,:class_name,:code,:source,
                      :timestamp,:timestamp
                    )
                """), group_params)
    return {"ok": True, "source": SOURCE, "version": payload.get("version") or VERSION,
            "total_bricks": len(rows), "created": created, "updated": updated,
            "mutates_inventory": False}


def _normalize(value: Any) -> str:
    text_value = unicodedata.normalize("NFKD", str(value or "").lower())
    text_value = "".join(ch for ch in text_value if not unicodedata.combining(ch))
    text_value = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:kg|g|mg|l|dl|cl|ml|stuks?|x)\b", " ", text_value)
    for source, target in sorted(PHRASE_TRANSLATIONS.items(), key=lambda item: -len(item[0])):
        text_value = re.sub(rf"\b{re.escape(source)}\b", target, text_value)
    tokens = [token for token in re.findall(r"[a-z0-9]+", text_value) if token not in STOP_WORDS]
    return " ".join(tokens)


def _score(query: str, title: str) -> float:
    if not query or not title:
        return 0.0
    if query == title:
        return 1.0
    if re.search(rf"\b{re.escape(title)}\b", query):
        return 0.97
    if re.search(rf"\b{re.escape(query)}\b", title):
        return 0.91
    q = set(query.split())
    t = set(title.split())
    overlap = len(q & t)
    if not overlap:
        return 0.0
    jaccard = overlap / len(q | t)
    coverage = overlap / len(t)
    sequence = SequenceMatcher(None, query, title).ratio()
    return round(0.45 * jaccard + 0.35 * coverage + 0.20 * sequence, 6)


def classify_gpc_product(*, product_name: str, category: str = "", explicit_gpc_brick_code: str = "") -> dict[str, Any]:
    ensure_local_gpc_schema()
    explicit = re.sub(r"\D+", "", explicit_gpc_brick_code or "")
    with engine.begin() as conn:
        if re.fullmatch(r"\d{8}", explicit):
            row = conn.execute(text("""
                SELECT gpc_brick_code,gpc_brick_name,gpc_brick_name_en,source_version,source
                FROM gpc_product_groups WHERE gpc_brick_code=:code AND COALESCE(active,1)=1 LIMIT 1
            """), {"code": explicit}).mappings().first()
            if row:
                return {"ok": True, "status": "classified", "classification_source": "explicit_gpc_code",
                        "confidence": 1.0, "product_type_id": f"gpc:{explicit}", **dict(row)}

        query = _normalize(f"{product_name} {category}")
        rows = conn.execute(text("""
            SELECT gpc_brick_code,gpc_brick_name,gpc_brick_name_en,source_version,source
            FROM gpc_product_groups
            WHERE COALESCE(active,1)=1 AND gpc_segment_code='50000000'
              AND upper(COALESCE(gpc_brick_name_en,'')) NOT LIKE '%UNCLASSIFIED%'
        """)).mappings().all()
    ranked = []
    for row in rows:
        title = _normalize(row.get("gpc_brick_name_en"))
        score = _score(query, title)
        if score > 0:
            ranked.append((score, row))
    ranked.sort(key=lambda item: (-item[0], str(item[1].get("gpc_brick_code") or "")))
    if not ranked:
        return {"ok": True, "status": "not_classified", "reason": "no_match", "query": query}
    best_score, best = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else 0.0
    margin = best_score - second_score
    if best_score < 0.90 or (best_score < 0.97 and margin < 0.08):
        return {"ok": True, "status": "not_classified", "reason": "insufficient_confidence",
                "query": query, "best_score": best_score, "margin": margin}
    result = dict(best)
    return {"ok": True, "status": "classified", "classification_source": "gpc_taxonomy_name_match",
            "confidence": best_score, "margin": margin,
            "product_type_id": f"gpc:{best['gpc_brick_code']}", **result}

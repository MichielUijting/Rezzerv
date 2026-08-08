"""Language overlay for GS1 GPC reference descriptions.

The official GS1 source text remains untouched in the existing GPC tables.
Translated labels are stored separately and linked by entity type and code.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path

from sqlalchemy import Engine, text

from app.db import engine as runtime_engine

ENTITY_TABLES = {
    "segment": ("gpc_segments", "segment_code", "description"),
    "family": ("gpc_families", "family_code", "description"),
    "class": ("gpc_classes", "class_code", "description"),
    "brick": ("gpc_bricks", "brick_code", "description"),
    "attribute_type": ("gpc_attribute_types", "att_type_code", "att_type_text"),
    "attribute_value": ("gpc_attribute_values", "att_value_code", "att_value_text"),
}


@dataclass
class TranslationImportCounts:
    rows: int = 0
    inserted: int = 0
    updated: int = 0


def ensure_gpc_translation_schema(db_engine: Engine = runtime_engine) -> None:
    with db_engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS gpc_translations (
                entity_type VARCHAR(30) NOT NULL,
                entity_code VARCHAR(8) NOT NULL,
                language_code VARCHAR(12) NOT NULL,
                translated_text TEXT NOT NULL,
                translation_source TEXT NOT NULL,
                reviewed INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (entity_type, entity_code, language_code)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS gpc_translation_import_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_name TEXT NOT NULL,
                source_sha256 VARCHAR(64) NOT NULL,
                language_code VARCHAR(12) NOT NULL,
                imported_at TEXT NOT NULL,
                status VARCHAR(20) NOT NULL,
                row_count INTEGER NOT NULL,
                message TEXT
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_gpc_translation_language "
            "ON gpc_translations(language_code, entity_type)"
        ))


def export_translation_template(
    output_path: str | Path,
    *,
    target_language: str = "nl",
    db_engine: Engine = runtime_engine,
) -> dict:
    ensure_gpc_translation_schema(db_engine)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "entity_type", "entity_code", "source_text", "language_code",
            "translated_text", "translation_source", "reviewed",
        ))
        writer.writeheader()
        with db_engine.connect() as conn:
            for entity_type, (table, code_column, text_column) in ENTITY_TABLES.items():
                rows = conn.execute(text(
                    f"SELECT {code_column}, {text_column} FROM {table} ORDER BY {code_column}"
                ))
                for code, source_text in rows:
                    writer.writerow({
                        "entity_type": entity_type,
                        "entity_code": code,
                        "source_text": source_text,
                        "language_code": target_language,
                        "translated_text": "",
                        "translation_source": "",
                        "reviewed": "0",
                    })
                    count += 1
    return {"status": "exported", "path": str(target), "rows": count}


def import_gpc_translations_csv(
    csv_path: str | Path,
    *,
    required_language: str = "nl",
    require_complete: bool = True,
    db_engine: Engine = runtime_engine,
) -> dict:
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"Vertaalbestand niet gevonden: {path}")
    ensure_gpc_translation_schema(db_engine)
    source_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    imported_at = datetime.now(timezone.utc).isoformat()
    counts = TranslationImportCounts()
    seen: set[tuple[str, str, str]] = set()

    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {
            "entity_type", "entity_code", "language_code", "translated_text",
            "translation_source", "reviewed",
        }
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"Vertaalbestand mist kolommen: {', '.join(sorted(missing))}")
        rows = list(reader)

    with db_engine.begin() as conn:
        for row_number, row in enumerate(rows, start=2):
            entity_type = row["entity_type"].strip()
            entity_code = row["entity_code"].strip()
            language_code = row["language_code"].strip().lower()
            translated_text = row["translated_text"].strip()
            translation_source = row["translation_source"].strip()
            reviewed_raw = row["reviewed"].strip().lower()
            if entity_type not in ENTITY_TABLES:
                raise ValueError(f"Regel {row_number}: onbekend entity_type {entity_type}")
            if language_code != required_language.lower():
                raise ValueError(f"Regel {row_number}: taal moet {required_language} zijn")
            if not entity_code or not translated_text or not translation_source:
                raise ValueError(f"Regel {row_number}: code, vertaling en bron zijn verplicht")
            if reviewed_raw not in {"0", "1", "false", "true", "nee", "ja"}:
                raise ValueError(f"Regel {row_number}: reviewed moet 0/1 of false/true zijn")
            reviewed = 1 if reviewed_raw in {"1", "true", "ja"} else 0
            key = (entity_type, entity_code, language_code)
            if key in seen:
                raise ValueError(f"Regel {row_number}: dubbele vertaling voor {entity_type} {entity_code}")
            seen.add(key)
            table, code_column, _ = ENTITY_TABLES[entity_type]
            exists = conn.execute(text(
                f"SELECT 1 FROM {table} WHERE {code_column} = :code"
            ), {"code": entity_code}).first()
            if not exists:
                raise ValueError(f"Regel {row_number}: onbekende GPC-code {entity_code}")
            current = conn.execute(text("""
                SELECT 1 FROM gpc_translations
                WHERE entity_type=:entity_type AND entity_code=:entity_code
                  AND language_code=:language_code
            """), {
                "entity_type": entity_type,
                "entity_code": entity_code,
                "language_code": language_code,
            }).first()
            payload = {
                "entity_type": entity_type,
                "entity_code": entity_code,
                "language_code": language_code,
                "translated_text": translated_text,
                "translation_source": translation_source,
                "reviewed": reviewed,
                "updated_at": imported_at,
            }
            if current:
                conn.execute(text("""
                    UPDATE gpc_translations
                    SET translated_text=:translated_text,
                        translation_source=:translation_source,
                        reviewed=:reviewed, updated_at=:updated_at
                    WHERE entity_type=:entity_type AND entity_code=:entity_code
                      AND language_code=:language_code
                """), payload)
                counts.updated += 1
            else:
                conn.execute(text("""
                    INSERT INTO gpc_translations (
                        entity_type, entity_code, language_code, translated_text,
                        translation_source, reviewed, updated_at
                    ) VALUES (
                        :entity_type, :entity_code, :language_code, :translated_text,
                        :translation_source, :reviewed, :updated_at
                    )
                """), payload)
                counts.inserted += 1
            counts.rows += 1

        coverage = translation_coverage(
            required_language,
            db_engine=db_engine,
            connection=conn,
        )
        if require_complete and coverage["missing_total"]:
            raise ValueError(
                f"Nederlandse vertaling is niet compleet: {coverage['missing_total']} namen ontbreken"
            )
        conn.execute(text("""
            INSERT INTO gpc_translation_import_runs (
                source_name, source_sha256, language_code, imported_at,
                status, row_count, message
            ) VALUES (
                :source_name, :source_sha256, :language_code, :imported_at,
                'success', :row_count, NULL
            )
        """), {
            "source_name": path.name,
            "source_sha256": source_sha256,
            "language_code": required_language.lower(),
            "imported_at": imported_at,
            "row_count": counts.rows,
        })

    return {
        "status": "success",
        "source_name": path.name,
        "source_sha256": source_sha256,
        "language_code": required_language.lower(),
        "counts": asdict(counts),
        "coverage": coverage,
    }


def translation_coverage(
    language_code: str = "nl",
    *,
    db_engine: Engine = runtime_engine,
    connection=None,
) -> dict:
    own_connection = connection is None
    if own_connection:
        ensure_gpc_translation_schema(db_engine)
    conn = connection or db_engine.connect()
    try:
        entities = {}
        total = translated = 0
        for entity_type, (table, code_column, _) in ENTITY_TABLES.items():
            source_count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
            translated_count = conn.execute(text(f"""
                SELECT COUNT(*) FROM {table} source
                JOIN gpc_translations translation
                  ON translation.entity_type = :entity_type
                 AND translation.entity_code = source.{code_column}
                 AND translation.language_code = :language_code
            """), {
                "entity_type": entity_type,
                "language_code": language_code.lower(),
            }).scalar_one()
            entities[entity_type] = {
                "source": source_count,
                "translated": translated_count,
                "missing": source_count - translated_count,
            }
            total += source_count
            translated += translated_count
        return {
            "language_code": language_code.lower(),
            "entities": entities,
            "source_total": total,
            "translated_total": translated,
            "missing_total": total - translated,
            "complete": total == translated,
        }
    finally:
        if own_connection:
            conn.close()


def localized_text_expression(alias: str, entity_type: str, code_column: str, source_column: str) -> str:
    return (
        f"COALESCE((SELECT translated_text FROM gpc_translations t "
        f"WHERE t.entity_type='{entity_type}' AND t.entity_code={alias}.{code_column} "
        f"AND t.language_code='nl'), {alias}.{source_column})"
    )

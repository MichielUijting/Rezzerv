from __future__ import annotations

import csv
from pathlib import Path

from sqlalchemy import create_engine, text

from app.services.gpc_translation_service import import_gpc_translations_csv


def test_complete_translation_import_does_not_open_locked_second_connection(tmp_path: Path):
    database = tmp_path / "translation-lock.db"
    engine = create_engine(f"sqlite:///{database}")
    definitions = {
        "gpc_segments": ("segment_code", "description", "segment", "10000000"),
        "gpc_families": ("family_code", "description", "family", "20000000"),
        "gpc_classes": ("class_code", "description", "class", "30000000"),
        "gpc_bricks": ("brick_code", "description", "brick", "40000000"),
        "gpc_attribute_types": ("att_type_code", "att_type_text", "attribute_type", "50000000"),
        "gpc_attribute_values": ("att_value_code", "att_value_text", "attribute_value", "60000000"),
    }
    with engine.begin() as conn:
        for table, (code_column, text_column, _, code) in definitions.items():
            conn.execute(text(f"CREATE TABLE {table} ({code_column} TEXT PRIMARY KEY, {text_column} TEXT NOT NULL)"))
            conn.execute(text(f"INSERT INTO {table} ({code_column}, {text_column}) VALUES (:code, 'English')"), {"code": code})

    translation_file = tmp_path / "translations.csv"
    with translation_file.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "entity_type", "entity_code", "language_code", "translated_text",
            "translation_source", "reviewed",
        ))
        writer.writeheader()
        for _, (_, _, entity_type, code) in definitions.items():
            writer.writerow({
                "entity_type": entity_type,
                "entity_code": code,
                "language_code": "nl",
                "translated_text": "Nederlands",
                "translation_source": "test",
                "reviewed": "1",
            })

    result = import_gpc_translations_csv(translation_file, db_engine=engine)
    assert result["status"] == "success"
    assert result["coverage"]["complete"] is True
    assert result["counts"] == {"rows": 6, "inserted": 6, "updated": 0}
    engine.dispose()

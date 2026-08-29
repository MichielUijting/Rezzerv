from __future__ import annotations

import csv
import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import create_engine, text

from app.services.gpc_translation_service import (
    export_translation_template,
    import_gpc_translations_csv,
    translation_coverage,
)


BACKEND_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
HEAD_REVISION = "20260829_14"


def _engine(tmp_path: Path):
    database_path = tmp_path / "gpc.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    env["PYTHONPATH"] = str(BACKEND_ROOT)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ALEMBIC_INI),
            "upgrade",
            "head",
        ],
        cwd=BACKEND_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "Alembic GPC translation fixture migration failed:\n"
            + result.stdout
            + result.stderr
        )
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.begin() as conn:
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert revision == HEAD_REVISION
        conn.execute(text("INSERT OR REPLACE INTO gpc_segments VALUES ('50000000', 'Food/Beverage/Tobacco')"))
        conn.execute(text("INSERT OR REPLACE INTO gpc_families VALUES ('50100000', 'Fruits/Vegetables/Nuts/Seeds', '50000000')"))
        conn.execute(text("INSERT OR REPLACE INTO gpc_classes VALUES ('50101700', 'Vegetables - Unprepared/Unprocessed', '50100000')"))
        conn.execute(text("INSERT OR REPLACE INTO gpc_bricks VALUES ('10006144', 'Mustard Greens', '50101700')"))
        conn.execute(text("INSERT OR REPLACE INTO gpc_attribute_types VALUES ('20000794', 'Growing Method')"))
        conn.execute(text("INSERT OR REPLACE INTO gpc_attribute_values VALUES ('30002654', 'Conventional')"))
    return engine


def test_export_template_contains_every_official_name(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    output = tmp_path / "translations.csv"
    result = export_translation_template(output, db_engine=engine)
    assert result["rows"] == 6
    with output.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["entity_type"] for row in rows} == {
        "segment", "family", "class", "brick", "attribute_type", "attribute_value"
    }
    assert next(row for row in rows if row["entity_type"] == "brick")["source_text"] == "Mustard Greens"


def test_complete_dutch_overlay_import(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    csv_path = tmp_path / "nl.csv"
    rows = [
        ("segment", "50000000", "Voedingsmiddelen/Dranken/Tabak"),
        ("family", "50100000", "Fruit/Groenten/Noten/Zaden"),
        ("class", "50101700", "Groenten - Onbereid/Onbewerkt"),
        ("brick", "10006144", "Mosterdblad"),
        ("attribute_type", "20000794", "Teeltmethode"),
        ("attribute_value", "30002654", "Conventioneel"),
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "entity_type", "entity_code", "language_code", "translated_text",
            "translation_source", "reviewed",
        ))
        writer.writeheader()
        for entity_type, code, translated in rows:
            writer.writerow({
                "entity_type": entity_type, "entity_code": code,
                "language_code": "nl", "translated_text": translated,
                "translation_source": "Rezzerv gecontroleerde vertaling", "reviewed": "1",
            })
    result = import_gpc_translations_csv(csv_path, db_engine=engine)
    assert result["coverage"]["complete"] is True
    assert result["coverage"]["translated_total"] == 6
    with engine.connect() as conn:
        assert conn.execute(text("""
            SELECT translated_text FROM gpc_translations
            WHERE entity_type='brick' AND entity_code='10006144' AND language_code='nl'
        """)).scalar_one() == "Mosterdblad"
        assert conn.execute(text("SELECT description FROM gpc_bricks WHERE brick_code='10006144'" )).scalar_one() == "Mustard Greens"


def test_incomplete_overlay_is_rejected_atomically(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    csv_path = tmp_path / "partial.csv"
    csv_path.write_text(
        "entity_type,entity_code,language_code,translated_text,translation_source,reviewed\n"
        "brick,10006144,nl,Mosterdblad,test,0\n",
        encoding="utf-8",
    )
    try:
        import_gpc_translations_csv(csv_path, db_engine=engine)
    except ValueError as exc:
        assert "niet compleet" in str(exc)
    else:
        raise AssertionError("Onvolledige vertaling moet worden geweigerd")
    coverage = translation_coverage(db_engine=engine)
    assert coverage["translated_total"] == 0

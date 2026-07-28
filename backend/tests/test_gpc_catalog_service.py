from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from app.services.gpc_catalog_service import import_gpc_xml


SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<schema>
  <segment code="50000000" text="Food/Beverage/Tobacco">
    <family code="50100000" text="Fruits/Vegetables/Nuts/Seeds">
      <class code="50101700" text="Vegetables - Unprepared/Unprocessed">
        <brick code="10006144" text="Mustard Greens">
          <attType code="20000794" text="Growing Method">
            <attValue code="30002654" text="Conventional" />
          </attType>
        </brick>
      </class>
    </family>
  </segment>
</schema>
"""


def test_import_gpc_xml_creates_hierarchy_and_audit(tmp_path: Path):
    database_path = tmp_path / "rezzerv.db"
    xml_path = tmp_path / "nl-v-test.xml"
    xml_path.write_text(SAMPLE_XML, encoding="utf-8")
    engine = create_engine(f"sqlite:///{database_path}")

    result = import_gpc_xml(
        xml_path,
        language_code="nl",
        source_version="test",
        db_engine=engine,
    )

    assert result["counts"] == {
        "segments": 1,
        "families": 1,
        "classes": 1,
        "bricks": 1,
        "attribute_types": 1,
        "attribute_values": 1,
        "brick_attribute_types": 1,
        "attribute_type_values": 1,
    }
    assert set(result["tables"]) >= {
        "gpc_segments",
        "gpc_families",
        "gpc_classes",
        "gpc_bricks",
        "gpc_attribute_types",
        "gpc_attribute_values",
        "gpc_brick_attribute_types",
        "gpc_attribute_type_values",
        "gpc_import_runs",
    }

    with engine.begin() as conn:
        brick = conn.execute(
            text("SELECT brick_code, description, class_code FROM gpc_bricks")
        ).mappings().one()
        audit = conn.execute(
            text("SELECT language_code, source_version, status FROM gpc_import_runs")
        ).mappings().one()

    assert dict(brick) == {
        "brick_code": "10006144",
        "description": "Mustard Greens",
        "class_code": "50101700",
    }
    assert dict(audit) == {
        "language_code": "nl",
        "source_version": "test",
        "status": "success",
    }


def test_reimport_updates_descriptions_without_duplicates(tmp_path: Path):
    xml_path = tmp_path / "nl-v-test.xml"
    xml_path.write_text(SAMPLE_XML, encoding="utf-8")
    engine = create_engine("sqlite:///:memory:")

    import_gpc_xml(xml_path, db_engine=engine)
    xml_path.write_text(SAMPLE_XML.replace("Mustard Greens", "Mosterdblad"), encoding="utf-8")
    import_gpc_xml(xml_path, db_engine=engine)

    with engine.begin() as conn:
        brick_count = conn.execute(text("SELECT COUNT(*) FROM gpc_bricks")).scalar_one()
        description = conn.execute(
            text("SELECT description FROM gpc_bricks WHERE brick_code = '10006144'")
        ).scalar_one()
        import_count = conn.execute(text("SELECT COUNT(*) FROM gpc_import_runs")).scalar_one()

    assert brick_count == 1
    assert description == "Mosterdblad"
    assert import_count == 2


def test_invalid_root_is_rejected_before_schema_creation(tmp_path: Path):
    xml_path = tmp_path / "invalid.xml"
    xml_path.write_text("<not-schema />", encoding="utf-8")
    engine = create_engine("sqlite:///:memory:")

    try:
        import_gpc_xml(xml_path, db_engine=engine)
    except ValueError as exc:
        assert "root-element" in str(exc)
    else:
        raise AssertionError("ValueError expected")

    assert not any(name.startswith("gpc_") for name in inspect(engine).get_table_names())

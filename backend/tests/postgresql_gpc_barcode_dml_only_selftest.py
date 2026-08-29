from __future__ import annotations

import os
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

from app.services.barcode_identity_service import lookup_gtin, validate_barcode
from app.services.gpc_catalog_service import ensure_gpc_catalog_schema, import_gpc_xml
from app.services.gpc_local_catalog_service import ensure_local_gpc_schema, classify_gpc_product


XML_SOURCE_NAME = "pr2i-gpc-runtime-role.xml"
SEGMENT_CODE = "99900000"
FAMILY_CODE = "99910000"
CLASS_CODE = "99911000"
BRICK_CODE = "99911111"
ATTRIBUTE_TYPE_CODE = "99920000"
ATTRIBUTE_VALUE_CODE = "99930000"
LOCAL_BRICK_CODE = "99912222"
VALID_TEST_GTIN = "4006381333931"

XML_FIXTURE = f"""<?xml version="1.0" encoding="UTF-8"?>
<schema>
  <segment code="{SEGMENT_CODE}" text="PR2I Segment">
    <family code="{FAMILY_CODE}" text="PR2I Family">
      <class code="{CLASS_CODE}" text="PR2I Class">
        <brick code="{BRICK_CODE}" text="PR2I Brick">
          <attType code="{ATTRIBUTE_TYPE_CODE}" text="PR2I Attribute">
            <attValue code="{ATTRIBUTE_VALUE_CODE}" text="PR2I Value" />
          </attType>
        </brick>
      </class>
    </family>
  </segment>
</schema>
"""


def _engine_url():
    raw_url = str(os.getenv("DATABASE_URL") or "").strip()
    if not raw_url:
        raise RuntimeError("DATABASE_URL is required")
    url = make_url(raw_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return url


def _assert_runtime_create_denied(engine) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE pr2i_runtime_ddl_should_fail(id INTEGER)"))
    except ProgrammingError:
        print("POSTGRESQL_GPC_BARCODE_RUNTIME_CREATE_DENIED_GREEN")
        return
    raise AssertionError("Runtime role unexpectedly created a PR2i schema object")


def _assert_validation_only(engine) -> None:
    before_tables = set(inspect(engine).get_table_names())
    ensure_gpc_catalog_schema(engine)
    ensure_local_gpc_schema()
    after_tables = set(inspect(engine).get_table_names())
    if before_tables != after_tables:
        raise AssertionError("GPC schema validation unexpectedly mutated runtime schema")
    print("POSTGRESQL_GPC_BARCODE_SCHEMA_VALIDATION_ONLY_GREEN")


def _cleanup(conn) -> None:
    conn.execute(
        text(
            "DELETE FROM gpc_attribute_type_values "
            "WHERE att_type_code=:att_type OR att_value_code=:att_value"
        ),
        {"att_type": ATTRIBUTE_TYPE_CODE, "att_value": ATTRIBUTE_VALUE_CODE},
    )
    conn.execute(
        text(
            "DELETE FROM gpc_brick_attribute_types "
            "WHERE brick_code=:brick OR att_type_code=:att_type"
        ),
        {"brick": BRICK_CODE, "att_type": ATTRIBUTE_TYPE_CODE},
    )
    conn.execute(
        text("DELETE FROM gpc_attribute_values WHERE att_value_code=:code"),
        {"code": ATTRIBUTE_VALUE_CODE},
    )
    conn.execute(
        text("DELETE FROM gpc_attribute_types WHERE att_type_code=:code"),
        {"code": ATTRIBUTE_TYPE_CODE},
    )
    conn.execute(
        text("DELETE FROM gpc_bricks WHERE brick_code=:code"),
        {"code": BRICK_CODE},
    )
    conn.execute(
        text("DELETE FROM gpc_classes WHERE class_code=:code"),
        {"code": CLASS_CODE},
    )
    conn.execute(
        text("DELETE FROM gpc_families WHERE family_code=:code"),
        {"code": FAMILY_CODE},
    )
    conn.execute(
        text("DELETE FROM gpc_segments WHERE segment_code=:code"),
        {"code": SEGMENT_CODE},
    )
    conn.execute(
        text("DELETE FROM gpc_import_runs WHERE source_name=:source_name"),
        {"source_name": XML_SOURCE_NAME},
    )
    conn.execute(
        text("DELETE FROM gpc_product_groups WHERE gpc_brick_code=:code"),
        {"code": LOCAL_BRICK_CODE},
    )


def _assert_xml_import_dml_only(engine) -> None:
    with engine.begin() as conn:
        _cleanup(conn)

    with tempfile.TemporaryDirectory() as temp_dir:
        xml_path = Path(temp_dir) / XML_SOURCE_NAME
        xml_path.write_text(XML_FIXTURE, encoding="utf-8")
        result = import_gpc_xml(
            xml_path,
            language_code="nl",
            source_version="pr2i-runtime-role",
            db_engine=engine,
        )

    counts = result.get("counts") or {}
    expected_counts = {
        "segments": 1,
        "families": 1,
        "classes": 1,
        "bricks": 1,
        "attribute_types": 1,
        "attribute_values": 1,
        "brick_attribute_types": 1,
        "attribute_type_values": 1,
    }
    if counts != expected_counts:
        raise AssertionError(
            f"Unexpected GPC XML runtime-role counts: expected={expected_counts} actual={counts}"
        )

    with engine.connect() as conn:
        if conn.execute(
            text("SELECT description FROM gpc_bricks WHERE brick_code=:code"),
            {"code": BRICK_CODE},
        ).scalar_one_or_none() != "PR2I Brick":
            raise AssertionError("Runtime-role GPC XML import did not persist brick DML")
        run_count = int(
            conn.execute(
                text("SELECT COUNT(*) FROM gpc_import_runs WHERE source_name=:source_name"),
                {"source_name": XML_SOURCE_NAME},
            ).scalar_one()
        )
        if run_count != 1:
            raise AssertionError(f"Expected one GPC import-run row, got {run_count}")

    print("POSTGRESQL_GPC_XML_IMPORT_DML_ONLY_GREEN")


def _assert_local_catalog_classification(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM gpc_product_groups WHERE gpc_brick_code=:code"),
            {"code": LOCAL_BRICK_CODE},
        )
        conn.execute(
            text(
                """
                INSERT INTO gpc_product_groups (
                    gpc_brick_code,
                    gpc_brick_name,
                    gpc_brick_name_en,
                    gpc_segment_code,
                    language_code,
                    source_version,
                    source,
                    active
                ) VALUES (
                    :code,
                    'PR2I Testproduct',
                    'PR2I Test Product',
                    '50000000',
                    'en',
                    'pr2i-runtime-role',
                    'pr2i_runtime_role',
                    TRUE
                )
                """
            ),
            {"code": LOCAL_BRICK_CODE},
        )

    result = classify_gpc_product(
        product_name="ignored",
        explicit_gpc_brick_code=LOCAL_BRICK_CODE,
    )
    if result.get("status") != "classified":
        raise AssertionError(f"Explicit local GPC classification failed: {result}")
    if result.get("product_type_id") != f"gpc:{LOCAL_BRICK_CODE}":
        raise AssertionError(f"Unexpected local GPC product type: {result}")
    print("POSTGRESQL_GPC_LOCAL_CLASSIFICATION_DML_ONLY_GREEN")


def _assert_barcode_lookup_portable(engine) -> None:
    validation = validate_barcode(VALID_TEST_GTIN, "gtin")
    if not validation.get("valid"):
        raise AssertionError(f"Test GTIN unexpectedly invalid: {validation}")

    with engine.connect() as conn:
        result = lookup_gtin(conn, VALID_TEST_GTIN)
    if result.get("gtin") != VALID_TEST_GTIN:
        raise AssertionError(f"Barcode lookup returned unexpected GTIN: {result}")
    if result.get("match_status") not in {"not_found", "incomplete", "matched"}:
        raise AssertionError(f"Barcode lookup returned unexpected status: {result}")
    print("POSTGRESQL_BARCODE_GPC_LOOKUP_PORTABLE_GREEN")


def main() -> None:
    url = _engine_url()
    engine = create_engine(url)
    try:
        if engine.dialect.name != "postgresql":
            raise AssertionError(f"Expected PostgreSQL runtime, got {engine.dialect.name}")
        _assert_runtime_create_denied(engine)
        _assert_validation_only(engine)
        _assert_xml_import_dml_only(engine)
        _assert_local_catalog_classification(engine)
        _assert_barcode_lookup_portable(engine)
        with engine.begin() as conn:
            _cleanup(conn)
    finally:
        engine.dispose()

    print("POSTGRESQL_GPC_BARCODE_DML_ONLY_GREEN")
    print("POSTGRESQL_GPC_BARCODE_AUTHORITY_SELFTEST_GREEN")


if __name__ == "__main__":
    main()

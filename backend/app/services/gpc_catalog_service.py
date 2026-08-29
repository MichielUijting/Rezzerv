"""GS1 GPC reference catalog validation and XML importer.

Alembic owns the GPC reference schema. Runtime code validates that contract and
performs DML only; it never creates or alters schema objects.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from sqlalchemy import Engine, inspect, text

from app.db import engine as runtime_engine


_REQUIRED_COLUMNS: dict[str, set[str]] = {
    "gpc_segments": {"segment_code", "description"},
    "gpc_families": {"family_code", "description", "segment_code"},
    "gpc_classes": {"class_code", "description", "family_code"},
    "gpc_bricks": {"brick_code", "description", "class_code"},
    "gpc_attribute_types": {"att_type_code", "att_type_text"},
    "gpc_attribute_values": {"att_value_code", "att_value_text"},
    "gpc_brick_attribute_types": {"brick_code", "att_type_code"},
    "gpc_attribute_type_values": {"att_type_code", "att_value_code"},
    "gpc_import_runs": {
        "id",
        "source_name",
        "source_version",
        "language_code",
        "source_sha256",
        "imported_at",
        "status",
        "counts_json",
        "message",
    },
}
_REQUIRED_INDEXES: dict[str, tuple[str, tuple[str, ...]]] = {
    "idx_gpc_families_segment": ("gpc_families", ("segment_code",)),
    "idx_gpc_classes_family": ("gpc_classes", ("family_code",)),
    "idx_gpc_bricks_class": ("gpc_bricks", ("class_code",)),
}


@dataclass
class GpcImportCounts:
    segments: int = 0
    families: int = 0
    classes: int = 0
    bricks: int = 0
    attribute_types: int = 0
    attribute_values: int = 0
    brick_attribute_types: int = 0
    attribute_type_values: int = 0


def ensure_gpc_catalog_schema(db_engine: Engine = runtime_engine) -> None:
    """Validate the Alembic-owned GPC reference schema and fail closed on drift."""
    inspector = inspect(db_engine)
    available_tables = set(inspector.get_table_names())
    missing_tables = sorted(set(_REQUIRED_COLUMNS) - available_tables)
    if missing_tables:
        raise RuntimeError(
            "Canonical GPC-schema ontbreekt; voer Alembic migrations uit: "
            + ", ".join(missing_tables)
        )

    for table_name, required_columns in _REQUIRED_COLUMNS.items():
        actual_columns = {
            str(column.get("name") or "")
            for column in inspector.get_columns(table_name)
        }
        missing_columns = sorted(required_columns - actual_columns)
        if missing_columns:
            raise RuntimeError(
                f"Canonical GPC-schema wijkt af: {table_name} mist "
                + ", ".join(missing_columns)
            )

    for index_name, (table_name, expected_columns) in _REQUIRED_INDEXES.items():
        indexes = {
            str(index.get("name") or ""): index
            for index in inspector.get_indexes(table_name)
        }
        index = indexes.get(index_name)
        actual_columns = tuple(
            str(column or "") for column in ((index or {}).get("column_names") or ())
        )
        if (
            index is None
            or actual_columns != expected_columns
            or bool(index.get("unique"))
        ):
            raise RuntimeError(
                f"Canonical GPC-index wijkt af: {index_name}; "
                f"expected={expected_columns!r}/False, "
                f"actual={actual_columns!r}/{bool((index or {}).get('unique'))}"
            )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(parent: ET.Element, name: str):
    return (child for child in list(parent) if _local_name(child.tag) == name)


def _upsert(conn, table: str, key_name: str, key_value: str, values: dict) -> None:
    existing = conn.execute(
        text(f"SELECT {key_name} FROM {table} WHERE {key_name} = :key_value"),
        {"key_value": key_value},
    ).first()
    payload = {key_name: key_value, **values}
    if existing:
        assignments = ", ".join(f"{name} = :{name}" for name in values)
        conn.execute(
            text(f"UPDATE {table} SET {assignments} WHERE {key_name} = :{key_name}"),
            payload,
        )
    else:
        columns = ", ".join(payload)
        parameters = ", ".join(f":{name}" for name in payload)
        conn.execute(text(f"INSERT INTO {table} ({columns}) VALUES ({parameters})"), payload)


def _link(
    conn,
    table: str,
    first_name: str,
    first_value: str,
    second_name: str,
    second_value: str,
) -> bool:
    existing = conn.execute(
        text(
            f"SELECT 1 FROM {table} WHERE {first_name} = :first_value "
            f"AND {second_name} = :second_value"
        ),
        {"first_value": first_value, "second_value": second_value},
    ).first()
    if existing:
        return False
    conn.execute(
        text(
            f"INSERT INTO {table} ({first_name}, {second_name}) "
            f"VALUES (:first_value, :second_value)"
        ),
        {"first_value": first_value, "second_value": second_value},
    )
    return True


def import_gpc_xml(
    xml_path: str | Path,
    *,
    language_code: str = "nl",
    source_version: str | None = None,
    db_engine: Engine = runtime_engine,
) -> dict:
    """Atomically import one GS1 GPC XML file into the migrated Rezzerv database."""
    path = Path(xml_path)
    if not path.is_file():
        raise FileNotFoundError(f"GPC XML-bestand niet gevonden: {path}")

    xml_bytes = path.read_bytes()
    source_sha256 = hashlib.sha256(xml_bytes).hexdigest()
    root = ET.fromstring(xml_bytes)
    if _local_name(root.tag) != "schema":
        raise ValueError("Ongeldig GPC XML-bestand: root-element moet <schema> zijn")

    ensure_gpc_catalog_schema(db_engine)
    counts = GpcImportCounts()
    imported_at = datetime.now(timezone.utc).isoformat()

    with db_engine.begin() as conn:
        for segment in _children(root, "segment"):
            segment_code = (segment.get("code") or "").strip()
            description = (segment.get("text") or "").strip()
            if not segment_code or not description:
                raise ValueError("GPC segment zonder code of omschrijving")
            _upsert(
                conn,
                "gpc_segments",
                "segment_code",
                segment_code,
                {"description": description},
            )
            counts.segments += 1

            for family in _children(segment, "family"):
                family_code = (family.get("code") or "").strip()
                family_text = (family.get("text") or "").strip()
                if not family_code or not family_text:
                    raise ValueError("GPC family zonder code of omschrijving")
                _upsert(
                    conn,
                    "gpc_families",
                    "family_code",
                    family_code,
                    {"description": family_text, "segment_code": segment_code},
                )
                counts.families += 1

                for class_element in _children(family, "class"):
                    class_code = (class_element.get("code") or "").strip()
                    class_text = (class_element.get("text") or "").strip()
                    if not class_code or not class_text:
                        raise ValueError("GPC class zonder code of omschrijving")
                    _upsert(
                        conn,
                        "gpc_classes",
                        "class_code",
                        class_code,
                        {"description": class_text, "family_code": family_code},
                    )
                    counts.classes += 1

                    for brick in _children(class_element, "brick"):
                        brick_code = (brick.get("code") or "").strip()
                        brick_text = (brick.get("text") or "").strip()
                        if not brick_code or not brick_text:
                            raise ValueError("GPC brick zonder code of omschrijving")
                        _upsert(
                            conn,
                            "gpc_bricks",
                            "brick_code",
                            brick_code,
                            {"description": brick_text, "class_code": class_code},
                        )
                        counts.bricks += 1

                        for attribute_type in _children(brick, "attType"):
                            type_code = (attribute_type.get("code") or "").strip()
                            type_text = (attribute_type.get("text") or "").strip()
                            if not type_code or not type_text:
                                raise ValueError("GPC attribuuttype zonder code of omschrijving")
                            _upsert(
                                conn,
                                "gpc_attribute_types",
                                "att_type_code",
                                type_code,
                                {"att_type_text": type_text},
                            )
                            counts.attribute_types += 1
                            if _link(
                                conn,
                                "gpc_brick_attribute_types",
                                "brick_code",
                                brick_code,
                                "att_type_code",
                                type_code,
                            ):
                                counts.brick_attribute_types += 1

                            for attribute_value in _children(attribute_type, "attValue"):
                                value_code = (attribute_value.get("code") or "").strip()
                                value_text = (attribute_value.get("text") or "").strip()
                                if not value_code or not value_text:
                                    raise ValueError("GPC attribuutwaarde zonder code of omschrijving")
                                _upsert(
                                    conn,
                                    "gpc_attribute_values",
                                    "att_value_code",
                                    value_code,
                                    {"att_value_text": value_text},
                                )
                                counts.attribute_values += 1
                                if _link(
                                    conn,
                                    "gpc_attribute_type_values",
                                    "att_type_code",
                                    type_code,
                                    "att_value_code",
                                    value_code,
                                ):
                                    counts.attribute_type_values += 1

        conn.execute(
            text(
                """
                INSERT INTO gpc_import_runs (
                    source_name, source_version, language_code, source_sha256,
                    imported_at, status, counts_json, message
                ) VALUES (
                    :source_name, :source_version, :language_code, :source_sha256,
                    :imported_at, 'success', :counts_json, NULL
                )
                """
            ),
            {
                "source_name": path.name,
                "source_version": source_version,
                "language_code": language_code.strip().lower() or "nl",
                "source_sha256": source_sha256,
                "imported_at": imported_at,
                "counts_json": json.dumps(asdict(counts), sort_keys=True),
            },
        )

    return {
        "source_name": path.name,
        "source_version": source_version,
        "language_code": language_code.strip().lower() or "nl",
        "source_sha256": source_sha256,
        "imported_at": imported_at,
        "counts": asdict(counts),
        "tables": sorted(
            name for name in inspect(db_engine).get_table_names() if name.startswith("gpc_")
        ),
    }

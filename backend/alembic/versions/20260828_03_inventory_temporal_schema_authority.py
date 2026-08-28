"""Move temporal inventory schema authority from runtime code to Alembic.

Revision ID: 20260828_03
Revises: 20260828_02
Create Date: 2026-08-28

This revision adds the seven temporal inventory fields, the two canonical
ordering/source indexes, adopts the canonical active locationless inventory
identity index, and backfills existing inventory_events rows. It does not change
inventory location nullability: space_id and sublocation_id remain nullable by design.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
import re
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260828_03"
down_revision: Union[str, None] = "20260828_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TEMPORAL_COLUMNS = (
    "effective_at",
    "recorded_at",
    "effective_at_precision",
    "event_priority",
    "source_reference",
    "source_line_id",
    "replayed_at",
)
_TEMPORAL_ORDER_INDEX = "idx_inventory_events_temporal_order"
_SOURCE_REFERENCE_INDEX = "idx_inventory_events_source_reference"
_TEMPORAL_ORDER_COLUMNS = (
    "household_id",
    "household_article_id",
    "effective_at",
    "event_priority",
    "id",
)
_SOURCE_REFERENCE_COLUMNS = (
    "source",
    "source_reference",
    "source_line_id",
)
_LOCATIONLESS_ACTIVE_IDENTITY_INDEX = "uq_inventory_active_locationless_household_article"
_LOCATIONLESS_ACTIVE_IDENTITY_COLUMNS = ("household_id", "household_article_id")
_LOCATIONLESS_ACTIVE_IDENTITY_PREDICATE = (
    "COALESCE(status, 'active') = 'active' "
    "AND household_article_id IS NOT NULL "
    "AND space_id IS NULL "
    "AND sublocation_id IS NULL"
)
_EVENT_PRIORITY = {
    "purchase": 10,
    "auto_repurchase": 10,
    "transfer_in": 20,
    "transfer_out": 30,
    "consume": 40,
    "adjustment": 50,
}


def _temporal_column_specs(dialect_name: str) -> dict[str, sa.Column[Any]]:
    datetime_type: sa.types.TypeEngine[Any]
    if dialect_name == "postgresql":
        datetime_type = sa.DateTime(timezone=True)
    else:
        datetime_type = sa.Text()
    return {
        "effective_at": sa.Column("effective_at", datetime_type, nullable=True),
        "recorded_at": sa.Column("recorded_at", datetime_type, nullable=True),
        "effective_at_precision": sa.Column(
            "effective_at_precision",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'datetime'"),
        ),
        "event_priority": sa.Column(
            "event_priority",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("100"),
        ),
        "source_reference": sa.Column("source_reference", sa.Text(), nullable=True),
        "source_line_id": sa.Column("source_line_id", sa.Text(), nullable=True),
        "replayed_at": sa.Column("replayed_at", datetime_type, nullable=True),
    }


def _normalized_text(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        candidate = value
    elif isinstance(value, date):
        candidate = datetime.combine(value, time.min)
    else:
        raw = str(value).strip()
        if not raw:
            return None
        normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        try:
            candidate = datetime.fromisoformat(normalized)
        except ValueError:
            return None
    if candidate.tzinfo is None:
        candidate = candidate.replace(tzinfo=timezone.utc)
    return candidate.astimezone(timezone.utc)


def _purchase_effective_at(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        candidate_date = value.date()
    elif isinstance(value, date):
        candidate_date = value
    else:
        raw = str(value).strip()
        if not raw:
            return None
        candidate_date = None
        for pattern in ("%Y-%m-%d", "%d-%m-%Y"):
            try:
                candidate_date = datetime.strptime(raw, pattern).date()
                break
            except ValueError:
                continue
        if candidate_date is None:
            return None
    return datetime.combine(candidate_date, time.min, tzinfo=timezone.utc)


def _database_datetime(bind: sa.engine.Connection, value: datetime | None) -> Any:
    if value is None:
        return None
    if bind.dialect.name == "postgresql":
        return value
    return value.isoformat()


def _backfill_inventory_events(bind: sa.engine.Connection) -> None:
    rows = bind.execute(sa.text(
        """
        SELECT id, event_type, purchase_date, created_at,
               effective_at, recorded_at, effective_at_precision,
               event_priority, source_reference
        FROM inventory_events
        """
    )).mappings().all()

    for row in rows:
        purchase_effective = _purchase_effective_at(row.get("purchase_date"))
        existing_effective = _coerce_datetime(row.get("effective_at"))
        created_at = _coerce_datetime(row.get("created_at"))
        effective_at = existing_effective or purchase_effective or created_at
        recorded_at = _coerce_datetime(row.get("recorded_at")) or created_at

        existing_precision = _normalized_text(row.get("effective_at_precision"))
        source_reference = _normalized_text(row.get("source_reference"))
        if source_reference:
            precision = existing_precision or "datetime"
        elif purchase_effective is not None:
            precision = "date"
        else:
            precision = existing_precision or "datetime"

        event_type = str(row.get("event_type") or "").strip().lower()
        priority = _EVENT_PRIORITY.get(event_type)
        if priority is None:
            priority = int(row.get("event_priority") or 100)

        bind.execute(sa.text(
            """
            UPDATE inventory_events
            SET effective_at = :effective_at,
                recorded_at = :recorded_at,
                effective_at_precision = :precision,
                event_priority = :priority
            WHERE id = :event_id
            """
        ), {
            "effective_at": _database_datetime(bind, effective_at),
            "recorded_at": _database_datetime(bind, recorded_at),
            "precision": precision,
            "priority": priority,
            "event_id": row["id"],
        })


def _index_contract(inspector: sa.Inspector) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("name") or ""): item
        for item in inspector.get_indexes("inventory_events")
    }


def _validate_temporal_index(
    index_name: str,
    index: dict[str, Any] | None,
    expected_columns: tuple[str, ...],
) -> None:
    if not index:
        raise RuntimeError(f"Inventory temporal index ontbreekt: {index_name}")
    actual_columns = tuple(index.get("column_names") or ())
    actual_unique = bool(index.get("unique"))
    if actual_columns != expected_columns or actual_unique:
        raise RuntimeError(
            f"Inventory temporal index drift: {index_name} "
            f"expected_columns={expected_columns!r} expected_unique=False "
            f"actual_columns={actual_columns!r} actual_unique={actual_unique}"
        )


def _ensure_indexes(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    indexes = _index_contract(inspector)
    expected = {
        _TEMPORAL_ORDER_INDEX: _TEMPORAL_ORDER_COLUMNS,
        _SOURCE_REFERENCE_INDEX: _SOURCE_REFERENCE_COLUMNS,
    }
    for index_name, columns in expected.items():
        actual = indexes.get(index_name)
        if actual is None:
            op.create_index(index_name, "inventory_events", list(columns), unique=False)
        else:
            _validate_temporal_index(index_name, actual, columns)


def _locationless_index_sql(bind: sa.engine.Connection) -> str | None:
    if bind.dialect.name == "sqlite":
        return bind.execute(sa.text(
            """
            SELECT sql
            FROM sqlite_master
            WHERE type = 'index' AND name = :name
            LIMIT 1
            """
        ), {"name": _LOCATIONLESS_ACTIVE_IDENTITY_INDEX}).scalar_one_or_none()
    if bind.dialect.name == "postgresql":
        return bind.execute(sa.text(
            """
            SELECT indexdef
            FROM pg_indexes
            WHERE schemaname = current_schema()
              AND tablename = 'inventory'
              AND indexname = :name
            LIMIT 1
            """
        ), {"name": _LOCATIONLESS_ACTIVE_IDENTITY_INDEX}).scalar_one_or_none()
    raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")


def _normalized_predicate_terms(index_sql: str | None) -> frozenset[str]:
    raw = str(index_sql or "")
    where_match = re.search(r"\bwhere\b", raw, flags=re.IGNORECASE)
    if not where_match:
        return frozenset()
    predicate = raw[where_match.end():].lower().replace('"', '')
    predicate = re.sub(r"::[a-z_][a-z0-9_]*", "", predicate)
    return frozenset(
        re.sub(r"[\s()]+", "", term)
        for term in re.split(r"\s+and\s+", predicate)
        if term.strip()
    )


def _validate_locationless_identity_index(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    indexes = {
        str(item.get("name") or ""): item
        for item in inspector.get_indexes("inventory")
    }
    index = indexes.get(_LOCATIONLESS_ACTIVE_IDENTITY_INDEX)
    if not index:
        raise RuntimeError(
            f"Canonical locationless inventory index ontbreekt: {_LOCATIONLESS_ACTIVE_IDENTITY_INDEX}"
        )
    if not bool(index.get("unique")) or tuple(index.get("column_names") or ()) != _LOCATIONLESS_ACTIVE_IDENTITY_COLUMNS:
        raise RuntimeError("Canonical locationless inventory index wijkt af in uniqueness/kolommen")

    index_sql = _locationless_index_sql(bind)
    expected_terms = _normalized_predicate_terms(
        f"CREATE INDEX canonical ON inventory (household_id, household_article_id) "
        f"WHERE {_LOCATIONLESS_ACTIVE_IDENTITY_PREDICATE}"
    )
    actual_terms = _normalized_predicate_terms(index_sql)
    if actual_terms != expected_terms:
        raise RuntimeError(
            "Canonical locationless inventory index predicate wijkt af: "
            f"expected={sorted(expected_terms)!r} actual={sorted(actual_terms)!r} "
            f"index={index_sql!r}"
        )


def _ensure_locationless_identity_index(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table("inventory"):
        raise RuntimeError("inventory table ontbreekt")
    columns = {
        str(column.get("name") or ""): column
        for column in inspector.get_columns("inventory")
    }
    required = {"household_id", "household_article_id", "space_id", "sublocation_id", "status"}
    missing = required - set(columns)
    if missing:
        raise RuntimeError(
            "Canonical locationless inventory schema mist kolommen: " + ", ".join(sorted(missing))
        )

    duplicate = bind.execute(sa.text(
        """
        SELECT household_id, household_article_id, COUNT(*) AS row_count
        FROM inventory
        WHERE COALESCE(status, 'active') = 'active'
          AND household_article_id IS NOT NULL
          AND space_id IS NULL
          AND sublocation_id IS NULL
        GROUP BY household_id, household_article_id
        HAVING COUNT(*) > 1
        LIMIT 1
        """
    )).mappings().first()
    if duplicate:
        raise RuntimeError(
            "Dubbele actieve locationless voorraadidentiteit gevonden voor "
            f"household_id={duplicate['household_id']} en "
            f"household_article_id={duplicate['household_article_id']}"
        )

    indexes = {
        str(item.get("name") or ""): item
        for item in inspector.get_indexes("inventory")
    }
    if _LOCATIONLESS_ACTIVE_IDENTITY_INDEX not in indexes:
        predicate = sa.text(_LOCATIONLESS_ACTIVE_IDENTITY_PREDICATE)
        op.create_index(
            _LOCATIONLESS_ACTIVE_IDENTITY_INDEX,
            "inventory",
            list(_LOCATIONLESS_ACTIVE_IDENTITY_COLUMNS),
            unique=True,
            sqlite_where=predicate,
            postgresql_where=predicate,
        )
    _validate_locationless_identity_index(bind)


def _validate_contract(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table("inventory_events"):
        raise RuntimeError("inventory_events table ontbreekt")
    columns = {
        str(column.get("name") or ""): column
        for column in inspector.get_columns("inventory_events")
    }
    missing = set(_TEMPORAL_COLUMNS) - set(columns)
    if missing:
        raise RuntimeError(f"Inventory temporal columns ontbreken: {sorted(missing)}")
    for column_name in ("effective_at_precision", "event_priority"):
        if bool(columns[column_name].get("nullable")):
            raise RuntimeError(f"inventory_events.{column_name} moet NOT NULL zijn")

    indexes = _index_contract(inspector)
    expected_indexes = {
        _TEMPORAL_ORDER_INDEX: _TEMPORAL_ORDER_COLUMNS,
        _SOURCE_REFERENCE_INDEX: _SOURCE_REFERENCE_COLUMNS,
    }
    for index_name, expected_columns in expected_indexes.items():
        _validate_temporal_index(index_name, indexes.get(index_name), expected_columns)

    if not inspector.has_table("inventory"):
        raise RuntimeError("inventory table ontbreekt")
    inventory_columns = {
        str(column.get("name") or ""): column
        for column in inspector.get_columns("inventory")
    }
    for column_name in ("space_id", "sublocation_id"):
        column = inventory_columns.get(column_name)
        if column is None:
            raise RuntimeError(f"inventory.{column_name} ontbreekt")
        if not bool(column.get("nullable")):
            raise RuntimeError(
                f"inventory.{column_name} moet nullable blijven voor locationless voorraad"
            )

    _validate_locationless_identity_index(bind)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"sqlite", "postgresql"}:
        raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")

    inspector = sa.inspect(bind)
    if not inspector.has_table("inventory_events"):
        raise RuntimeError("inventory_events table ontbreekt; Alembic maakt geen parallel ledger")

    existing_columns = {
        str(column.get("name") or "")
        for column in inspector.get_columns("inventory_events")
    }
    specs = _temporal_column_specs(bind.dialect.name)
    for column_name in _TEMPORAL_COLUMNS:
        if column_name not in existing_columns:
            op.add_column("inventory_events", specs[column_name])

    _backfill_inventory_events(bind)
    _ensure_indexes(bind)
    _ensure_locationless_identity_index(bind)
    _validate_contract(bind)


def downgrade() -> None:
    raise RuntimeError(
        "The inventory temporal schema-authority revision is intentionally "
        "non-destructive and cannot be downgraded."
    )

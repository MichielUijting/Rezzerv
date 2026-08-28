"""Chronological inventory event support.

Functional rule: inventory history is ordered by when an event happened
(`effective_at`), never by when Rezzerv happened to record it (`recorded_at`).

Alembic revision 20260828_03 owns the temporal inventory schema. This module
only validates that contract before using the ledger; it never mutates schema or
performs historical schema backfill at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable
import uuid

from sqlalchemy import inspect, text


EVENT_PRIORITY = {
    "baseline": 0,
    "purchase": 10,
    "auto_repurchase": 10,
    "transfer_in": 20,
    "transfer_out": 30,
    "consume": 40,
    "adjustment": 50,
}

_TEMPORAL_COLUMNS = {
    "effective_at",
    "recorded_at",
    "effective_at_precision",
    "event_priority",
    "source_reference",
    "source_line_id",
    "replayed_at",
}
_TEMPORAL_INDEX_CONTRACT = {
    "idx_inventory_events_temporal_order": (
        "household_id",
        "household_article_id",
        "effective_at",
        "event_priority",
        "id",
    ),
    "idx_inventory_events_source_reference": (
        "source",
        "source_reference",
        "source_line_id",
    ),
}


def _normalize_text(value: object | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _as_iso_datetime(value: datetime | str | None) -> str:
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value or "").strip()
        if not raw:
            dt = datetime.now(timezone.utc)
        else:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def ensure_temporal_inventory_schema(conn) -> None:
    """Fail closed when Alembic-owned temporal inventory schema is missing/drifted."""
    inspector = inspect(conn)
    if not inspector.has_table("inventory_events"):
        raise RuntimeError(
            "inventory_events table ontbreekt; voer Alembic upgrade naar 20260828_03/head uit"
        )

    columns = {
        str(column.get("name") or ""): column
        for column in inspector.get_columns("inventory_events")
    }
    missing = _TEMPORAL_COLUMNS - set(columns)
    if missing:
        raise RuntimeError(
            "Temporal inventory schema is niet gemigreerd; ontbrekende kolommen: "
            + ", ".join(sorted(missing))
        )
    for column_name in ("effective_at_precision", "event_priority"):
        if bool(columns[column_name].get("nullable")):
            raise RuntimeError(
                f"Temporal inventory schema drift: inventory_events.{column_name} moet NOT NULL zijn"
            )

    indexes = {
        str(index.get("name") or ""): tuple(index.get("column_names") or ())
        for index in inspector.get_indexes("inventory_events")
    }
    for index_name, expected_columns in _TEMPORAL_INDEX_CONTRACT.items():
        actual_columns = indexes.get(index_name)
        if actual_columns != expected_columns:
            raise RuntimeError(
                "Temporal inventory schema drift: "
                f"{index_name} expected={expected_columns!r} actual={actual_columns!r}"
            )

    if conn.dialect.name == "sqlite":
        incomplete = conn.execute(text(
            """
            SELECT id
            FROM inventory_events
            WHERE effective_at IS NULL OR trim(CAST(effective_at AS TEXT)) = ''
               OR recorded_at IS NULL OR trim(CAST(recorded_at AS TEXT)) = ''
               OR effective_at_precision IS NULL OR trim(effective_at_precision) = ''
               OR event_priority IS NULL
            LIMIT 1
            """
        )).scalar()
    else:
        incomplete = conn.execute(text(
            """
            SELECT id
            FROM inventory_events
            WHERE effective_at IS NULL
               OR recorded_at IS NULL
               OR effective_at_precision IS NULL OR trim(effective_at_precision) = ''
               OR event_priority IS NULL
            LIMIT 1
            """
        )).scalar()
    if incomplete is not None:
        raise RuntimeError(
            "Temporal inventory historische backfill is incompleet; "
            f"eerste inventory_event={incomplete}"
        )


@dataclass(frozen=True)
class TemporalInventoryEvent:
    household_id: str
    household_article_id: str
    article_name: str
    event_type: str
    quantity: Decimal
    effective_at: datetime | str
    effective_at_precision: str = "datetime"
    source: str = "system"
    source_reference: str | None = None
    source_line_id: str | None = None
    location_id: str | None = None
    location_label: str | None = None
    note: str | None = None


def insert_temporal_event(conn, event: TemporalInventoryEvent) -> str:
    ensure_temporal_inventory_schema(conn)
    event_id = uuid.uuid4().hex
    event_type = str(event.event_type or "").strip().lower()
    priority = EVENT_PRIORITY.get(event_type, 100)
    effective_at = _as_iso_datetime(event.effective_at)
    recorded_at = datetime.now(timezone.utc).isoformat()
    precision = str(event.effective_at_precision or "datetime").strip().lower()
    if precision not in {"date", "datetime"}:
        raise ValueError("effective_at_precision moet date of datetime zijn")

    conn.execute(text(
        """
        INSERT INTO inventory_events (
            id, household_id, article_id, household_article_id, article_name,
            location_id, location_label, event_type, quantity, source, note,
            effective_at, recorded_at, effective_at_precision, event_priority,
            source_reference, source_line_id, created_at
        ) VALUES (
            :id, :household_id, :article_id, :household_article_id, :article_name,
            :location_id, :location_label, :event_type, :quantity, :source, :note,
            :effective_at, :recorded_at, :precision, :priority,
            :source_reference, :source_line_id, CURRENT_TIMESTAMP
        )
        """
    ), {
        "id": event_id,
        "household_id": str(event.household_id),
        "article_id": str(event.household_article_id),
        "household_article_id": str(event.household_article_id),
        "article_name": str(event.article_name),
        "location_id": _normalize_text(event.location_id),
        "location_label": _normalize_text(event.location_label),
        "event_type": event_type,
        "quantity": str(event.quantity),
        "source": str(event.source or "system"),
        "note": _normalize_text(event.note),
        "effective_at": effective_at,
        "recorded_at": recorded_at,
        "precision": precision,
        "priority": priority,
        "source_reference": _normalize_text(event.source_reference),
        "source_line_id": _normalize_text(event.source_line_id),
    })
    return event_id


def ordered_events(conn, *, household_id: str, household_article_id: str) -> list[dict]:
    ensure_temporal_inventory_schema(conn)
    rows = conn.execute(text(
        """
        SELECT id, household_id, household_article_id, article_name, event_type,
               quantity, effective_at, recorded_at, effective_at_precision,
               event_priority, source, source_reference, source_line_id,
               location_id, location_label
        FROM inventory_events
        WHERE household_id = :household_id
          AND COALESCE(household_article_id, article_id) = :household_article_id
        ORDER BY effective_at ASC,
                 event_priority ASC,
                 COALESCE(source_reference, '') ASC,
                 COALESCE(source_line_id, '') ASC,
                 id ASC
        """
    ), {
        "household_id": str(household_id),
        "household_article_id": str(household_article_id),
    }).mappings().all()
    return [dict(row) for row in rows]


def event_delta(event_type: str, quantity: Decimal) -> Decimal:
    normalized = str(event_type or "").strip().lower()
    magnitude = Decimal(str(quantity or 0))
    if normalized in {"purchase", "auto_repurchase", "transfer_in", "baseline"}:
        return magnitude
    if normalized in {"consume", "transfer_out"}:
        return -abs(magnitude)
    if normalized == "adjustment":
        return magnitude
    return magnitude


def replay_running_balances(events: Iterable[dict]) -> list[dict]:
    """Pure deterministic replay, used by production code and contract tests."""
    balance = Decimal("0")
    result: list[dict] = []
    for row in events:
        old = balance
        balance += event_delta(str(row.get("event_type") or ""), Decimal(str(row.get("quantity") or 0)))
        replayed = dict(row)
        replayed["old_quantity"] = old
        replayed["new_quantity"] = balance
        result.append(replayed)
    return result


def replay_article(conn, *, household_id: str, household_article_id: str) -> dict:
    """Recompute event balances in chronological order."""
    events = ordered_events(
        conn,
        household_id=household_id,
        household_article_id=household_article_id,
    )
    replayed = replay_running_balances(events)
    replayed_at = datetime.now(timezone.utc).isoformat()
    for row in replayed:
        conn.execute(text(
            """
            UPDATE inventory_events
            SET old_quantity = :old_quantity,
                new_quantity = :new_quantity,
                replayed_at = :replayed_at
            WHERE id = :id
            """
        ), {
            "id": row["id"],
            "old_quantity": str(row["old_quantity"]),
            "new_quantity": str(row["new_quantity"]),
            "replayed_at": replayed_at,
        })

    current_quantity = replayed[-1]["new_quantity"] if replayed else Decimal("0")
    return {
        "household_id": str(household_id),
        "household_article_id": str(household_article_id),
        "event_count": len(replayed),
        "current_quantity": current_quantity,
        "first_effective_at": replayed[0].get("effective_at") if replayed else None,
        "last_effective_at": replayed[-1].get("effective_at") if replayed else None,
    }


def reconcile_inventory_total(
    conn,
    *,
    household_id: str,
    household_article_id: str,
    preferred_inventory_id: str | None = None,
) -> dict:
    """Make the current inventory projection equal the chronological ledger total."""
    replay = replay_article(
        conn,
        household_id=str(household_id),
        household_article_id=str(household_article_id),
    )
    expected = Decimal(str(replay["current_quantity"] or 0))
    current = Decimal(str(conn.execute(text(
        """
        SELECT COALESCE(SUM(aantal), 0)
        FROM inventory
        WHERE household_id = :household_id
          AND household_article_id = :household_article_id
          AND COALESCE(status, 'active') = 'active'
        """
    ), {
        "household_id": str(household_id),
        "household_article_id": str(household_article_id),
    }).scalar() or 0))
    delta = expected - current

    target_id = _normalize_text(preferred_inventory_id)
    if target_id:
        target_exists = conn.execute(text(
            """
            SELECT id FROM inventory
            WHERE id = :id
              AND household_id = :household_id
              AND household_article_id = :household_article_id
              AND COALESCE(status, 'active') = 'active'
            LIMIT 1
            """
        ), {
            "id": target_id,
            "household_id": str(household_id),
            "household_article_id": str(household_article_id),
        }).scalar()
        if not target_exists:
            target_id = None

    if not target_id:
        target_id = conn.execute(text(
            """
            SELECT id FROM inventory
            WHERE household_id = :household_id
              AND household_article_id = :household_article_id
              AND COALESCE(status, 'active') = 'active'
            ORDER BY id ASC
            LIMIT 1
            """
        ), {
            "household_id": str(household_id),
            "household_article_id": str(household_article_id),
        }).scalar()

    if delta != 0 and target_id:
        conn.execute(text(
            """
            UPDATE inventory
            SET aantal = COALESCE(aantal, 0) + :delta,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
            """
        ), {"id": str(target_id), "delta": int(delta)})

    return {
        **replay,
        "projected_before": current,
        "projection_delta": delta,
        "projected_after": expected if target_id or delta == 0 else current,
        "target_inventory_id": str(target_id) if target_id else None,
    }

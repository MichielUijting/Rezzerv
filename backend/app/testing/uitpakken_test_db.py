"""
Technical Design Reference:
- TD Section: TD-08 Test, baseline en regressie
- Module Role: Uitpakken smoke/regression test database support
- Runtime Type: test
- Status Authority: no
- Refactor Status: keep_test_support

Deze module bouwt een tijdelijke, volledig losstaande SQLite-testdatabase
voor Uitpakken-tests. De normale Rezzerv-database wordt niet gelezen,
niet gekopieerd en niet gewijzigd.
"""

from __future__ import annotations

import sqlite3
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


HOUSEHOLD_ID = 1

SPACE_BERGING_ID = 10
SPACE_KEUKEN_ID = 20
SPACE_BADKAMER_ID = 30

SUBLOCATION_KEUKEN_KOELKAST_ID = 201
SUBLOCATION_KEUKEN_VOORRAADKAST_ID = 202
SUBLOCATION_BADKAMER_KAST_ID = 301

ARTICLE_PASTA_ID = 1001
ARTICLE_MELK_ID = 1002
ARTICLE_TOILETPAPIER_ID = 1003
ARTICLE_TOMATEN_ID = 1004

BATCH_ID = 2001

LINE_PASTA_ID = 3001
LINE_MELK_ID = 3002
LINE_TOILETPAPIER_ID = 3003
LINE_TOMATEN_ID = 3004
LINE_ONBEKEND_ID = 3005


@dataclass(frozen=True)
class UitpakkenTestDatabase:
    """Handle voor de tijdelijke Uitpakken-testdatabase."""

    path: Path
    conn: sqlite3.Connection


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def configure_connection(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    return conn


@contextmanager
def temporary_uitpakken_database(
    *,
    prefix: str = "rezzerv_uitpakken_",
    seed: bool = True,
) -> Iterator[UitpakkenTestDatabase]:
    """Maak een tijdelijke SQLite-database en verwijder die automatisch.

    Deze contextmanager volgt bewust de datastrategie van de Kassa-regressie:
    een temp-bestand, minimale tabellen, vaste fixtures en geen afhankelijkheid
    van de normale ontwikkel-/productiedatabase.
    """

    with tempfile.TemporaryDirectory(prefix=prefix) as tmp_dir:
        db_path = Path(tmp_dir) / "uitpakken_test.sqlite"
        conn = configure_connection(sqlite3.connect(db_path))
        try:
            init_schema(conn)
            if seed:
                seed_base_fixtures(conn)
            conn.commit()
            yield UitpakkenTestDatabase(path=db_path, conn=conn)
        finally:
            conn.close()


def init_schema(conn: sqlite3.Connection) -> None:
    """Initialiseer alleen de tabellen die Uitpakken-tests nodig hebben."""

    conn.executescript(
        """
        create table households (
            id integer primary key,
            name text not null
        );

        create table spaces (
            id integer primary key,
            household_id integer not null,
            naam text not null,
            active integer not null default 1,
            sort_order integer,
            created_at text,
            updated_at text,
            foreign key (household_id) references households(id)
        );

        create table sublocations (
            id integer primary key,
            household_id integer not null,
            space_id integer not null,
            naam text not null,
            active integer not null default 1,
            sort_order integer,
            created_at text,
            updated_at text,
            foreign key (household_id) references households(id),
            foreign key (space_id) references spaces(id)
        );

        create table household_articles (
            id integer primary key,
            household_id integer not null,
            name text not null,
            barcode text,
            active integer not null default 1,
            created_at text,
            updated_at text,
            foreign key (household_id) references households(id)
        );

        create table household_article_settings (
            id integer primary key,
            household_article_id integer not null,
            key text not null,
            value text,
            created_at text,
            updated_at text,
            unique (household_article_id, key),
            foreign key (household_article_id) references household_articles(id)
        );

        create table purchase_import_batches (
            id integer primary key,
            household_id integer not null,
            source text,
            status text not null default 'open',
            created_at text,
            updated_at text,
            processed_at text,
            foreign key (household_id) references households(id)
        );

        create table purchase_import_lines (
            id integer primary key,
            batch_id integer not null,
            household_id integer not null,
            external_line_ref text,
            raw_label text not null,
            article_name_raw text not null,
            quantity numeric not null default 1,
            unit text,
            unit_price numeric,
            line_total numeric,
            matched_household_article_id integer,
            target_location_id integer,
            target_sublocation_id integer,
            review_decision text,
            status text not null default 'open',
            processed_at text,
            created_at text,
            updated_at text,
            foreign key (batch_id) references purchase_import_batches(id),
            foreign key (household_id) references households(id),
            foreign key (matched_household_article_id) references household_articles(id),
            foreign key (target_location_id) references spaces(id),
            foreign key (target_sublocation_id) references sublocations(id)
        );

        create table inventory_events (
            id integer primary key,
            household_id integer not null,
            household_article_id integer not null,
            source_type text not null,
            source_id integer,
            quantity_delta numeric not null,
            location_id integer,
            sublocation_id integer,
            occurred_at text not null,
            created_at text,
            foreign key (household_id) references households(id),
            foreign key (household_article_id) references household_articles(id),
            foreign key (location_id) references spaces(id),
            foreign key (sublocation_id) references sublocations(id)
        );

        create table inventory (
            id integer primary key,
            household_id integer not null,
            household_article_id integer not null,
            location_id integer,
            sublocation_id integer,
            quantity numeric not null default 0,
            updated_at text,
            unique (household_id, household_article_id, location_id, sublocation_id),
            foreign key (household_id) references households(id),
            foreign key (household_article_id) references household_articles(id),
            foreign key (location_id) references spaces(id),
            foreign key (sublocation_id) references sublocations(id)
        );
        """
    )


def seed_base_fixtures(conn: sqlite3.Connection) -> None:
    """Vul de vaste basisfixtures voor Uitpakken smoke/regressie."""

    now = utc_now()

    conn.execute(
        "insert into households (id, name) values (?, ?)",
        (HOUSEHOLD_ID, "Uitpakken Testhuishouden"),
    )

    conn.executemany(
        """
        insert into spaces (id, household_id, naam, active, sort_order, created_at, updated_at)
        values (?, ?, ?, 1, ?, ?, ?)
        """,
        [
            (SPACE_BERGING_ID, HOUSEHOLD_ID, "Berging", 1, now, now),
            (SPACE_KEUKEN_ID, HOUSEHOLD_ID, "Keuken", 2, now, now),
            (SPACE_BADKAMER_ID, HOUSEHOLD_ID, "Badkamer", 3, now, now),
        ],
    )

    conn.executemany(
        """
        insert into sublocations (id, household_id, space_id, naam, active, sort_order, created_at, updated_at)
        values (?, ?, ?, ?, 1, ?, ?, ?)
        """,
        [
            (SUBLOCATION_KEUKEN_KOELKAST_ID, HOUSEHOLD_ID, SPACE_KEUKEN_ID, "Koelkast", 1, now, now),
            (SUBLOCATION_KEUKEN_VOORRAADKAST_ID, HOUSEHOLD_ID, SPACE_KEUKEN_ID, "Voorraadkast", 2, now, now),
            (SUBLOCATION_BADKAMER_KAST_ID, HOUSEHOLD_ID, SPACE_BADKAMER_ID, "Kast", 1, now, now),
        ],
    )

    conn.executemany(
        """
        insert into household_articles (id, household_id, name, barcode, active, created_at, updated_at)
        values (?, ?, ?, ?, 1, ?, ?)
        """,
        [
            (ARTICLE_PASTA_ID, HOUSEHOLD_ID, "Test Pasta", "871000000001", now, now),
            (ARTICLE_MELK_ID, HOUSEHOLD_ID, "Test Melk", "871000000002", now, now),
            (ARTICLE_TOILETPAPIER_ID, HOUSEHOLD_ID, "Test Toiletpapier", "871000000003", now, now),
            (ARTICLE_TOMATEN_ID, HOUSEHOLD_ID, "Test Tomaten", "871000000004", now, now),
        ],
    )

    set_article_default_location(
        conn,
        ARTICLE_MELK_ID,
        location_id=SPACE_KEUKEN_ID,
        sublocation_id=SUBLOCATION_KEUKEN_KOELKAST_ID,
    )
    set_article_default_location(
        conn,
        ARTICLE_TOILETPAPIER_ID,
        location_id=SPACE_BERGING_ID,
        sublocation_id=None,
    )

    conn.execute(
        """
        insert into purchase_import_batches (id, household_id, source, status, created_at, updated_at)
        values (?, ?, ?, 'open', ?, ?)
        """,
        (BATCH_ID, HOUSEHOLD_ID, "uitpakken_regression_fixture", now, now),
    )

    conn.executemany(
        """
        insert into purchase_import_lines (
            id, batch_id, household_id, external_line_ref, raw_label, article_name_raw,
            quantity, unit, unit_price, line_total, matched_household_article_id,
            target_location_id, target_sublocation_id, review_decision, status,
            created_at, updated_at
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, null, null, null, 'open', ?, ?)
        """,
        [
            (LINE_PASTA_ID, BATCH_ID, HOUSEHOLD_ID, "fixture-line-1", "TEST PASTA 1X", "TEST PASTA", 1, "st", 1.49, 1.49, ARTICLE_PASTA_ID, now, now),
            (LINE_MELK_ID, BATCH_ID, HOUSEHOLD_ID, "fixture-line-2", "TEST MELK 1X", "TEST MELK", 1, "st", 1.19, 1.19, ARTICLE_MELK_ID, now, now),
            (LINE_TOILETPAPIER_ID, BATCH_ID, HOUSEHOLD_ID, "fixture-line-3", "TEST TOILETPAPIER 1X", "TEST TOILETPAPIER", 1, "st", 3.99, 3.99, ARTICLE_TOILETPAPIER_ID, now, now),
            (LINE_TOMATEN_ID, BATCH_ID, HOUSEHOLD_ID, "fixture-line-4", "TEST TOMATEN 1X", "TEST TOMATEN", 1, "st", 2.49, 2.49, ARTICLE_TOMATEN_ID, now, now),
            (LINE_ONBEKEND_ID, BATCH_ID, HOUSEHOLD_ID, "fixture-line-5", "TEST ONBEKEND 1X", "TEST ONBEKEND", 1, "st", 0.99, 0.99, None, now, now),
        ],
    )


def set_article_setting(
    conn: sqlite3.Connection,
    household_article_id: int,
    key: str,
    value: int | str | None,
) -> None:
    now = utc_now()
    conn.execute(
        """
        insert into household_article_settings (household_article_id, key, value, created_at, updated_at)
        values (?, ?, ?, ?, ?)
        on conflict(household_article_id, key)
        do update set value = excluded.value, updated_at = excluded.updated_at
        """,
        (household_article_id, key, None if value is None else str(value), now, now),
    )


def set_article_default_location(
    conn: sqlite3.Connection,
    household_article_id: int,
    *,
    location_id: int,
    sublocation_id: int | None,
) -> None:
    set_article_setting(conn, household_article_id, "default_location_id", location_id)
    set_article_setting(conn, household_article_id, "default_sublocation_id", sublocation_id)


def get_article_default_location(
    conn: sqlite3.Connection,
    household_article_id: int,
) -> tuple[int | None, int | None]:
    rows = fetch_all(
        conn,
        """
        select key, value
        from household_article_settings
        where household_article_id = ?
          and key in ('default_location_id', 'default_sublocation_id')
        """,
        (household_article_id,),
    )
    values = {row["key"]: row["value"] for row in rows}
    return _optional_int(values.get("default_location_id")), _optional_int(values.get("default_sublocation_id"))


def apply_article_default_to_line(conn: sqlite3.Connection, line_id: int) -> dict[str, Any]:
    line = fetch_one(conn, "select * from purchase_import_lines where id = ?", (line_id,))
    if line is None:
        return {"status": "failed", "error": "line_not_found", "line_id": line_id}

    article_id = line["matched_household_article_id"]
    if article_id is None:
        return {"status": "blocked", "error": "line_has_no_article", "line_id": line_id}

    location_id, sublocation_id = get_article_default_location(conn, int(article_id))
    if location_id is None:
        return {"status": "blocked", "error": "article_has_no_default_location", "line_id": line_id}

    return assign_target_location(
        conn,
        line_id,
        location_id=location_id,
        sublocation_id=sublocation_id,
        default_location_policy="line_only",
    )


def location_has_active_sublocations(conn: sqlite3.Connection, location_id: int) -> bool:
    row = fetch_one(
        conn,
        """
        select count(*) as count
        from sublocations
        where space_id = ?
          and active = 1
        """,
        (location_id,),
    )
    return bool(row and int(row["count"] or 0) > 0)


def validate_target_location(
    conn: sqlite3.Connection,
    *,
    location_id: int | None,
    sublocation_id: int | None,
) -> tuple[bool, str | None]:
    if location_id is None:
        return False, "missing_target_location_id"

    space = fetch_one(
        conn,
        "select id, active from spaces where id = ?",
        (location_id,),
    )
    if space is None or int(space["active"] or 0) != 1:
        return False, "invalid_target_location_id"

    if sublocation_id is not None:
        sublocation = fetch_one(
            conn,
            """
            select id, active, space_id
            from sublocations
            where id = ?
            """,
            (sublocation_id,),
        )
        if sublocation is None or int(sublocation["active"] or 0) != 1:
            return False, "invalid_target_sublocation_id"
        if int(sublocation["space_id"]) != int(location_id):
            return False, "sublocation_not_in_location"

    if location_has_active_sublocations(conn, location_id) and sublocation_id is None:
        return False, "missing_required_sublocation_id"

    return True, None


def assign_target_location(
    conn: sqlite3.Connection,
    line_id: int,
    *,
    location_id: int,
    sublocation_id: int | None = None,
    default_location_policy: str = "line_only",
) -> dict[str, Any]:
    if default_location_policy not in {"line_only", "article_default"}:
        return {"status": "failed", "error": "invalid_default_location_policy", "line_id": line_id}

    line = fetch_one(conn, "select * from purchase_import_lines where id = ?", (line_id,))
    if line is None:
        return {"status": "failed", "error": "line_not_found", "line_id": line_id}

    ok, reason = validate_target_location(conn, location_id=location_id, sublocation_id=sublocation_id)
    if not ok:
        return {"status": "blocked", "error": reason, "line_id": line_id}

    now = utc_now()
    conn.execute(
        """
        update purchase_import_lines
        set target_location_id = ?,
            target_sublocation_id = ?,
            updated_at = ?
        where id = ?
        """,
        (location_id, sublocation_id, now, line_id),
    )

    article_default_updated = False
    if default_location_policy == "article_default":
        article_id = line["matched_household_article_id"]
        if article_id is None:
            return {"status": "blocked", "error": "line_has_no_article_for_default_location", "line_id": line_id}
        set_article_default_location(
            conn,
            int(article_id),
            location_id=location_id,
            sublocation_id=sublocation_id,
        )
        article_default_updated = True

    return {
        "status": "passed",
        "line_id": line_id,
        "target_location_id": location_id,
        "target_sublocation_id": sublocation_id,
        "standard_location_updated": article_default_updated,
    }


def process_line_to_inventory(conn: sqlite3.Connection, line_id: int) -> dict[str, Any]:
    line = fetch_one(conn, "select * from purchase_import_lines where id = ?", (line_id,))
    if line is None:
        return {"status": "failed", "error": "line_not_found", "line_id": line_id}

    if str(line["status"] or "").lower() == "processed":
        return {"status": "skipped", "error": "already_processed", "line_id": line_id}

    article_id = line["matched_household_article_id"]
    if article_id is None:
        return {"status": "blocked", "error": "missing_household_article", "line_id": line_id}

    location_id = _optional_int(line["target_location_id"])
    sublocation_id = _optional_int(line["target_sublocation_id"])
    ok, reason = validate_target_location(conn, location_id=location_id, sublocation_id=sublocation_id)
    if not ok:
        return {"status": "blocked", "error": reason, "line_id": line_id}

    quantity = float(line["quantity"] or 0)
    now = utc_now()

    cursor = conn.execute(
        """
        insert into inventory_events (
            household_id, household_article_id, source_type, source_id,
            quantity_delta, location_id, sublocation_id, occurred_at, created_at
        )
        values (?, ?, 'purchase_import_line', ?, ?, ?, ?, ?, ?)
        """,
        (line["household_id"], article_id, line_id, quantity, location_id, sublocation_id, now, now),
    )

    upsert_inventory_quantity(
        conn,
        household_id=int(line["household_id"]),
        household_article_id=int(article_id),
        location_id=int(location_id),
        sublocation_id=sublocation_id,
        quantity_delta=quantity,
    )

    conn.execute(
        """
        update purchase_import_lines
        set status = 'processed',
            processed_at = ?,
            updated_at = ?
        where id = ?
        """,
        (now, now, line_id),
    )

    return {
        "status": "processed",
        "line_id": line_id,
        "inventory_event_id": cursor.lastrowid,
        "quantity_delta": quantity,
        "location_id": location_id,
        "sublocation_id": sublocation_id,
    }


def upsert_inventory_quantity(
    conn: sqlite3.Connection,
    *,
    household_id: int,
    household_article_id: int,
    location_id: int,
    sublocation_id: int | None,
    quantity_delta: float,
) -> None:
    now = utc_now()

    if sublocation_id is None:
        existing = fetch_one(
            conn,
            """
            select id, quantity
            from inventory
            where household_id = ?
              and household_article_id = ?
              and location_id = ?
              and sublocation_id is null
            """,
            (household_id, household_article_id, location_id),
        )
    else:
        existing = fetch_one(
            conn,
            """
            select id, quantity
            from inventory
            where household_id = ?
              and household_article_id = ?
              and location_id = ?
              and sublocation_id = ?
            """,
            (household_id, household_article_id, location_id, sublocation_id),
        )

    if existing:
        conn.execute(
            """
            update inventory
            set quantity = ?,
                updated_at = ?
            where id = ?
            """,
            (float(existing["quantity"] or 0) + quantity_delta, now, existing["id"]),
        )
        return

    conn.execute(
        """
        insert into inventory (
            household_id, household_article_id, location_id, sublocation_id,
            quantity, updated_at
        )
        values (?, ?, ?, ?, ?, ?)
        """,
        (household_id, household_article_id, location_id, sublocation_id, quantity_delta, now),
    )


def fetch_one(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row is not None else None


def fetch_all(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def table_count(conn: sqlite3.Connection, table_name: str) -> int:
    if not table_name.replace("_", "").isalnum():
        raise ValueError(f"Unsafe table name: {table_name}")
    row = fetch_one(conn, f"select count(*) as count from {table_name}")
    return int(row["count"] if row else 0)


def fixture_ids() -> dict[str, int]:
    return {
        "household": HOUSEHOLD_ID,
        "space_berging": SPACE_BERGING_ID,
        "space_keuken": SPACE_KEUKEN_ID,
        "space_badkamer": SPACE_BADKAMER_ID,
        "sublocation_keuken_koelkast": SUBLOCATION_KEUKEN_KOELKAST_ID,
        "sublocation_keuken_voorraadkast": SUBLOCATION_KEUKEN_VOORRAADKAST_ID,
        "sublocation_badkamer_kast": SUBLOCATION_BADKAMER_KAST_ID,
        "article_pasta": ARTICLE_PASTA_ID,
        "article_melk": ARTICLE_MELK_ID,
        "article_toiletpapier": ARTICLE_TOILETPAPIER_ID,
        "article_tomaten": ARTICLE_TOMATEN_ID,
        "batch": BATCH_ID,
        "line_pasta": LINE_PASTA_ID,
        "line_melk": LINE_MELK_ID,
        "line_toiletpapier": LINE_TOILETPAPIER_ID,
        "line_tomaten": LINE_TOMATEN_ID,
        "line_onbekend": LINE_ONBEKEND_ID,
    }


def seed_summary(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        "households": table_count(conn, "households"),
        "spaces": table_count(conn, "spaces"),
        "sublocations": table_count(conn, "sublocations"),
        "household_articles": table_count(conn, "household_articles"),
        "household_article_settings": table_count(conn, "household_article_settings"),
        "purchase_import_batches": table_count(conn, "purchase_import_batches"),
        "purchase_import_lines": table_count(conn, "purchase_import_lines"),
        "inventory_events": table_count(conn, "inventory_events"),
        "inventory": table_count(conn, "inventory"),
    }


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


__all__ = [
    "ARTICLE_MELK_ID",
    "ARTICLE_PASTA_ID",
    "ARTICLE_TOILETPAPIER_ID",
    "ARTICLE_TOMATEN_ID",
    "BATCH_ID",
    "HOUSEHOLD_ID",
    "LINE_MELK_ID",
    "LINE_ONBEKEND_ID",
    "LINE_PASTA_ID",
    "LINE_TOILETPAPIER_ID",
    "LINE_TOMATEN_ID",
    "SPACE_BADKAMER_ID",
    "SPACE_BERGING_ID",
    "SPACE_KEUKEN_ID",
    "SUBLOCATION_BADKAMER_KAST_ID",
    "SUBLOCATION_KEUKEN_KOELKAST_ID",
    "SUBLOCATION_KEUKEN_VOORRAADKAST_ID",
    "UitpakkenTestDatabase",
    "apply_article_default_to_line",
    "assign_target_location",
    "fetch_all",
    "fetch_one",
    "fixture_ids",
    "init_schema",
    "location_has_active_sublocations",
    "process_line_to_inventory",
    "seed_base_fixtures",
    "seed_summary",
    "set_article_default_location",
    "temporary_uitpakken_database",
    "validate_target_location",
]


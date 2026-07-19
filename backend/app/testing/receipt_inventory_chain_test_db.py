"""Geïsoleerde SQLite-testdatabase voor kassabon -> Uitpakken -> Voorraad."""

from __future__ import annotations

import sqlite3
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from backend.app.testing.receipt_inventory_chain_contract import (
    FIRST_RECEIPT,
    SECOND_RECEIPT,
    TEST_HOUSEHOLD_ID,
    TEST_LOCATION_NAME,
    TEST_PRODUCT_NAME,
    TEST_SCENARIO_ID,
    TEST_SUBLOCATION_NAME,
)

GLOBAL_PRODUCT_ID = 910001
PRODUCT_IDENTITY_ID = 910002
PRODUCT_TYPE_ID = 910003
HOUSEHOLD_ARTICLE_ID = 910004
LOCATION_ID = 910005
SUBLOCATION_ID = 910006
FIRST_RECEIPT_ID = 910101
SECOND_RECEIPT_ID = 910102
FIRST_RECEIPT_LINE_ID = 910201
SECOND_RECEIPT_LINE_ID = 910202
FIRST_IMPORT_BATCH_ID = 910301
SECOND_IMPORT_BATCH_ID = 910302
FIRST_IMPORT_LINE_ID = 910401
SECOND_IMPORT_LINE_ID = 910402
TEST_GTIN = "8710000091001"
TEST_PRODUCT_TYPE_NAME = "Fruit"


@dataclass(frozen=True)
class ReceiptInventoryChainDatabase:
    path: Path
    conn: sqlite3.Connection


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def configure_connection(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    return conn


@contextmanager
def temporary_receipt_inventory_chain_database(
    *,
    prefix: str = "rezzerv_receipt_inventory_chain_",
    seed: bool = True,
) -> Iterator[ReceiptInventoryChainDatabase]:
    with tempfile.TemporaryDirectory(prefix=prefix) as tmp_dir:
        db_path = Path(tmp_dir) / "receipt_inventory_chain.sqlite"
        conn = configure_connection(sqlite3.connect(db_path))
        try:
            init_schema(conn)
            if seed:
                seed_chain_fixtures(conn)
            conn.commit()
            yield ReceiptInventoryChainDatabase(path=db_path, conn=conn)
        finally:
            conn.close()


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table households (
            id text primary key,
            name text not null
        );
        create table global_products (
            id integer primary key,
            name text not null,
            primary_gtin text unique,
            source text not null,
            status text not null default 'active'
        );
        create table product_identities (
            id integer primary key,
            global_product_id integer not null,
            identity_type text not null,
            identity_value text not null,
            source text not null,
            is_primary integer not null default 0,
            unique(identity_type, identity_value),
            foreign key (global_product_id) references global_products(id)
        );
        create table product_inventory_groups (
            id integer primary key,
            name text not null unique,
            active integer not null default 1
        );
        create table product_group_memberships (
            global_product_id integer not null,
            product_inventory_group_id integer not null,
            is_primary integer not null default 1,
            primary key (global_product_id, product_inventory_group_id),
            foreign key (global_product_id) references global_products(id),
            foreign key (product_inventory_group_id) references product_inventory_groups(id)
        );
        create table household_articles (
            id integer primary key,
            household_id text not null,
            global_product_id integer not null,
            name text not null,
            active integer not null default 1,
            unique(household_id, global_product_id),
            foreign key (household_id) references households(id),
            foreign key (global_product_id) references global_products(id)
        );
        create table spaces (
            id integer primary key,
            household_id text not null,
            naam text not null,
            active integer not null default 1,
            foreign key (household_id) references households(id)
        );
        create table sublocations (
            id integer primary key,
            household_id text not null,
            space_id integer not null,
            naam text not null,
            active integer not null default 1,
            foreign key (household_id) references households(id),
            foreign key (space_id) references spaces(id)
        );
        create table receipts (
            id integer primary key,
            household_id text not null,
            external_receipt_key text not null unique,
            store_name text not null,
            status text not null default 'checked',
            created_at text not null,
            foreign key (household_id) references households(id)
        );
        create table receipt_lines (
            id integer primary key,
            receipt_id integer not null,
            line_number integer not null,
            parsed_name text not null,
            parsed_quantity numeric not null,
            barcode text,
            matched_global_product_id integer,
            status text not null default 'matched',
            unique(receipt_id, line_number),
            foreign key (receipt_id) references receipts(id),
            foreign key (matched_global_product_id) references global_products(id)
        );
        create table purchase_import_batches (
            id integer primary key,
            household_id text not null,
            receipt_id integer not null unique,
            scenario_id text not null,
            status text not null default 'open',
            created_at text not null,
            foreign key (household_id) references households(id),
            foreign key (receipt_id) references receipts(id)
        );
        create table purchase_import_lines (
            id integer primary key,
            batch_id integer not null,
            receipt_line_id integer not null unique,
            household_id text not null,
            matched_household_article_id integer not null,
            target_location_id integer,
            target_sublocation_id integer,
            quantity numeric not null,
            status text not null default 'ready',
            processed_event_id integer,
            foreign key (batch_id) references purchase_import_batches(id),
            foreign key (receipt_line_id) references receipt_lines(id),
            foreign key (household_id) references households(id),
            foreign key (matched_household_article_id) references household_articles(id),
            foreign key (target_location_id) references spaces(id),
            foreign key (target_sublocation_id) references sublocations(id)
        );
        create table inventory_events (
            id integer primary key autoincrement,
            household_id text not null,
            household_article_id integer not null,
            source_type text not null,
            source_id integer not null,
            quantity_delta numeric not null,
            location_id integer not null,
            sublocation_id integer not null,
            occurred_at text not null,
            unique(source_type, source_id),
            foreign key (household_id) references households(id),
            foreign key (household_article_id) references household_articles(id),
            foreign key (location_id) references spaces(id),
            foreign key (sublocation_id) references sublocations(id)
        );
        create table inventory (
            id integer primary key autoincrement,
            household_id text not null,
            household_article_id integer not null,
            location_id integer not null,
            sublocation_id integer not null,
            quantity numeric not null default 0,
            updated_at text not null,
            unique(household_id, household_article_id, location_id, sublocation_id),
            foreign key (household_id) references households(id),
            foreign key (household_article_id) references household_articles(id),
            foreign key (location_id) references spaces(id),
            foreign key (sublocation_id) references sublocations(id)
        );
        """
    )


def seed_chain_fixtures(conn: sqlite3.Connection) -> None:
    now = utc_now()
    conn.execute(
        "insert into households (id, name) values (?, ?)",
        (TEST_HOUSEHOLD_ID, "Geautomatiseerd testhuishouden"),
    )
    conn.execute(
        "insert into global_products (id, name, primary_gtin, source, status) values (?, ?, ?, 'test', 'active')",
        (GLOBAL_PRODUCT_ID, TEST_PRODUCT_NAME, TEST_GTIN),
    )
    conn.execute(
        "insert into product_identities (id, global_product_id, identity_type, identity_value, source, is_primary) values (?, ?, 'gtin', ?, 'test', 1)",
        (PRODUCT_IDENTITY_ID, GLOBAL_PRODUCT_ID, TEST_GTIN),
    )
    conn.execute(
        "insert into product_inventory_groups (id, name, active) values (?, ?, 1)",
        (PRODUCT_TYPE_ID, TEST_PRODUCT_TYPE_NAME),
    )
    conn.execute(
        "insert into product_group_memberships (global_product_id, product_inventory_group_id, is_primary) values (?, ?, 1)",
        (GLOBAL_PRODUCT_ID, PRODUCT_TYPE_ID),
    )
    conn.execute(
        "insert into household_articles (id, household_id, global_product_id, name, active) values (?, ?, ?, ?, 1)",
        (HOUSEHOLD_ARTICLE_ID, TEST_HOUSEHOLD_ID, GLOBAL_PRODUCT_ID, TEST_PRODUCT_NAME),
    )
    conn.execute(
        "insert into spaces (id, household_id, naam, active) values (?, ?, ?, 1)",
        (LOCATION_ID, TEST_HOUSEHOLD_ID, TEST_LOCATION_NAME),
    )
    conn.execute(
        "insert into sublocations (id, household_id, space_id, naam, active) values (?, ?, ?, ?, 1)",
        (SUBLOCATION_ID, TEST_HOUSEHOLD_ID, LOCATION_ID, TEST_SUBLOCATION_NAME),
    )

    fixtures = (
        (FIRST_RECEIPT_ID, FIRST_RECEIPT_LINE_ID, FIRST_IMPORT_BATCH_ID, FIRST_IMPORT_LINE_ID, FIRST_RECEIPT),
        (SECOND_RECEIPT_ID, SECOND_RECEIPT_LINE_ID, SECOND_IMPORT_BATCH_ID, SECOND_IMPORT_LINE_ID, SECOND_RECEIPT),
    )
    for receipt_id, receipt_line_id, batch_id, import_line_id, receipt in fixtures:
        conn.execute(
            "insert into receipts (id, household_id, external_receipt_key, store_name, status, created_at) values (?, ?, ?, 'Albert Heijn', 'checked', ?)",
            (receipt_id, TEST_HOUSEHOLD_ID, receipt.receipt_key, now),
        )
        conn.execute(
            "insert into receipt_lines (id, receipt_id, line_number, parsed_name, parsed_quantity, barcode, matched_global_product_id, status) values (?, ?, 1, ?, ?, ?, ?, 'matched')",
            (receipt_line_id, receipt_id, TEST_PRODUCT_NAME, str(receipt.quantity), TEST_GTIN, GLOBAL_PRODUCT_ID),
        )
        conn.execute(
            "insert into purchase_import_batches (id, household_id, receipt_id, scenario_id, status, created_at) values (?, ?, ?, ?, 'open', ?)",
            (batch_id, TEST_HOUSEHOLD_ID, receipt_id, TEST_SCENARIO_ID, now),
        )
        conn.execute(
            "insert into purchase_import_lines (id, batch_id, receipt_line_id, household_id, matched_household_article_id, target_location_id, target_sublocation_id, quantity, status) values (?, ?, ?, ?, ?, ?, ?, ?, 'ready')",
            (
                import_line_id,
                batch_id,
                receipt_line_id,
                TEST_HOUSEHOLD_ID,
                HOUSEHOLD_ARTICLE_ID,
                LOCATION_ID,
                SUBLOCATION_ID,
                str(receipt.quantity),
            ),
        )


def fetch_one(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row is not None else None


def seed_summary(conn: sqlite3.Connection) -> dict[str, int]:
    tables = (
        "households",
        "global_products",
        "product_identities",
        "product_inventory_groups",
        "product_group_memberships",
        "household_articles",
        "spaces",
        "sublocations",
        "receipts",
        "receipt_lines",
        "purchase_import_batches",
        "purchase_import_lines",
        "inventory_events",
        "inventory",
    )
    return {table: int(conn.execute(f"select count(*) from {table}").fetchone()[0]) for table in tables}


def validate_seed(conn: sqlite3.Connection) -> None:
    expected = {
        "households": 1,
        "global_products": 1,
        "product_identities": 1,
        "product_inventory_groups": 1,
        "product_group_memberships": 1,
        "household_articles": 1,
        "spaces": 1,
        "sublocations": 1,
        "receipts": 2,
        "receipt_lines": 2,
        "purchase_import_batches": 2,
        "purchase_import_lines": 2,
        "inventory_events": 0,
        "inventory": 0,
    }
    assert seed_summary(conn) == expected

    household_row = conn.execute("select id from households").fetchone()
    assert household_row is not None
    assert str(household_row[0]) == TEST_HOUSEHOLD_ID

    for table in (
        "household_articles",
        "spaces",
        "sublocations",
        "receipts",
        "purchase_import_batches",
        "purchase_import_lines",
    ):
        household_ids = {
            str(row[0])
            for row in conn.execute(f"select distinct household_id from {table}").fetchall()
        }
        assert household_ids == {TEST_HOUSEHOLD_ID}

    product_link = fetch_one(
        conn,
        """
        select gp.name, gp.primary_gtin, pig.name as product_type
        from global_products gp
        join product_group_memberships pgm on pgm.global_product_id = gp.id
        join product_inventory_groups pig on pig.id = pgm.product_inventory_group_id
        where gp.id = ?
        """,
        (GLOBAL_PRODUCT_ID,),
    )
    assert product_link == {
        "name": TEST_PRODUCT_NAME,
        "primary_gtin": TEST_GTIN,
        "product_type": TEST_PRODUCT_TYPE_NAME,
    }


if __name__ == "__main__":
    db_path: Path | None = None
    with temporary_receipt_inventory_chain_database() as db:
        db_path = db.path
        validate_seed(db.conn)
        print("RECEIPT_INVENTORY_CHAIN_FIXTURE_GREEN")
    assert db_path is not None and not db_path.exists()

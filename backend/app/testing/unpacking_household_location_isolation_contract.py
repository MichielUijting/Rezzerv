from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.services.unpacking_household_location_patch import (
    resolve_space_and_sublocation_ids,
    validate_purchase_import_target_location,
)


def _expect_http_error(status_code: int, callback) -> None:
    try:
        callback()
    except HTTPException as exc:
        assert exc.status_code == status_code, exc
        return
    raise AssertionError(f"Verwachte HTTP {status_code} bleef uit")


def run_contract() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE purchase_import_batches (id TEXT PRIMARY KEY, household_id TEXT NOT NULL)"))
        conn.execute(text("""
            CREATE TABLE purchase_import_lines (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                external_line_ref TEXT,
                article_name_raw TEXT,
                target_location_id TEXT,
                review_decision TEXT,
                ui_sort_order INTEGER
            )
        """))
        conn.execute(text("CREATE TABLE spaces (id TEXT PRIMARY KEY, naam TEXT NOT NULL, household_id TEXT NOT NULL)"))
        conn.execute(text("CREATE TABLE sublocations (id TEXT PRIMARY KEY, naam TEXT NOT NULL, space_id TEXT NOT NULL)"))

        conn.execute(text("""
            INSERT INTO purchase_import_batches (id, household_id)
            VALUES ('batch-a', 'household-a'), ('batch-b', 'household-b')
        """))
        conn.execute(text("""
            INSERT INTO purchase_import_lines (
                id, batch_id, external_line_ref, article_name_raw,
                target_location_id, review_decision, ui_sort_order
            ) VALUES
                ('line-a', 'batch-a', 'a-1', 'Melk', NULL, 'selected', 0),
                ('line-b', 'batch-b', 'b-1', 'Brood', NULL, 'selected', 0)
        """))
        conn.execute(text("""
            INSERT INTO spaces (id, naam, household_id)
            VALUES
                ('space-a', 'Voorraadkast', 'household-a'),
                ('space-b', 'Voorraadkast', 'household-b')
        """))
        conn.execute(text("""
            INSERT INTO sublocations (id, naam, space_id)
            VALUES
                ('sub-a', 'Boven', 'space-a'),
                ('sub-b', 'Boven', 'space-b')
        """))

        resolved, line_ref = validate_purchase_import_target_location(conn, 'line-a', 'space-a')
        assert resolved and resolved['space_id'] == 'space-a'
        assert line_ref['household_id'] == 'household-a'

        resolved, _ = validate_purchase_import_target_location(conn, 'line-a', 'sub-a')
        assert resolved and resolved['sublocation_id'] == 'sub-a'

        resolved, _ = validate_purchase_import_target_location(conn, 'line-a', 'space-b')
        assert resolved is None
        resolved, _ = validate_purchase_import_target_location(conn, 'line-a', 'sub-b')
        assert resolved is None

        _expect_http_error(
            404,
            lambda: validate_purchase_import_target_location(conn, 'missing-line', 'space-a'),
        )

        own_space, own_sub = resolve_space_and_sublocation_ids(
            conn,
            'household-a',
            space_id='space-a',
            sublocation_id='sub-a',
        )
        assert own_space == 'space-a'
        assert own_sub == 'sub-a'

        _expect_http_error(
            400,
            lambda: resolve_space_and_sublocation_ids(
                conn,
                'household-a',
                space_id='space-b',
            ),
        )
        _expect_http_error(
            400,
            lambda: resolve_space_and_sublocation_ids(
                conn,
                'household-a',
                sublocation_id='sub-b',
            ),
        )
        _expect_http_error(
            400,
            lambda: resolve_space_and_sublocation_ids(
                conn,
                None,
                space_name='Onveilig',
            ),
        )

        new_space, new_sub = resolve_space_and_sublocation_ids(
            conn,
            'household-a',
            space_name='Koele berging',
            sublocation_name='Onderste plank',
        )
        created = conn.execute(text("""
            SELECT s.household_id, sl.id AS sublocation_id
            FROM spaces s
            JOIN sublocations sl ON sl.space_id = s.id
            WHERE s.id = :space_id AND sl.id = :sublocation_id
        """), {'space_id': new_space, 'sublocation_id': new_sub}).mappings().one()
        assert created['household_id'] == 'household-a'

        b_counts = conn.execute(text("""
            SELECT
                (SELECT COUNT(*) FROM spaces WHERE household_id = 'household-b') AS spaces,
                (SELECT COUNT(*) FROM sublocations sl JOIN spaces s ON s.id = sl.space_id WHERE s.household_id = 'household-b') AS sublocations
        """)).mappings().one()
        assert int(b_counts['spaces']) == 1
        assert int(b_counts['sublocations']) == 1

    print('UNPACKING_HOUSEHOLD_LOCATION_ISOLATION_GREEN')


if __name__ == '__main__':
    run_contract()

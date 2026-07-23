"""Contract test for household isolation in inventory location resolution."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.services.inventory_location_household_patch import (
    resolve_space_id,
    resolve_sublocation_id,
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
        conn.execute(
            text(
                """
                CREATE TABLE spaces (
                    id TEXT PRIMARY KEY,
                    naam TEXT NOT NULL,
                    household_id TEXT NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE sublocations (
                    id TEXT PRIMARY KEY,
                    naam TEXT NOT NULL,
                    space_id TEXT NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO spaces (id, naam, household_id)
                VALUES
                    ('space-a', 'Voorraadkast', 'household-a'),
                    ('space-b', 'Voorraadkast', 'household-b')
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO sublocations (id, naam, space_id)
                VALUES
                    ('sub-a', 'Boven', 'space-a'),
                    ('sub-b', 'Boven', 'space-b')
                """
            )
        )

        # Eigen objecten zijn bruikbaar.
        assert resolve_space_id(conn, 'household-a', 'space-a') == 'space-a'
        assert (
            resolve_sublocation_id(
                conn,
                'household-a',
                'space-a',
                'sub-a',
            )
            == 'sub-a'
        )

        # Object-IDs uit huishouden B worden niet geaccepteerd door A.
        _expect_http_error(
            404,
            lambda: resolve_space_id(conn, 'household-a', 'space-b'),
        )
        _expect_http_error(
            404,
            lambda: resolve_sublocation_id(
                conn,
                'household-a',
                'space-a',
                'sub-b',
            ),
        )

        # Gelijke namen selecteren uitsluitend het actieve huishouden.
        assert (
            resolve_space_id(
                conn,
                'household-a',
                space_name='Voorraadkast',
            )
            == 'space-a'
        )
        assert (
            resolve_sublocation_id(
                conn,
                'household-a',
                'space-a',
                sublocation_name='Boven',
            )
            == 'sub-a'
        )

        # Een ruimte van B kan niet als ouder voor een nieuwe sublocatie van A dienen.
        _expect_http_error(
            404,
            lambda: resolve_sublocation_id(
                conn,
                'household-a',
                'space-b',
                sublocation_name='Nieuw vak',
            ),
        )

        # Nieuwe objecten worden aantoonbaar binnen A aangemaakt.
        new_space_id = resolve_space_id(
            conn,
            'household-a',
            space_name='Koele berging',
        )
        new_sublocation_id = resolve_sublocation_id(
            conn,
            'household-a',
            new_space_id,
            sublocation_name='Onderste plank',
        )

        new_space = conn.execute(
            text(
                """
                SELECT id, household_id
                FROM spaces
                WHERE id = :id
                """
            ),
            {'id': new_space_id},
        ).mappings().one()
        new_sublocation = conn.execute(
            text(
                """
                SELECT sl.id, s.household_id
                FROM sublocations sl
                JOIN spaces s ON s.id = sl.space_id
                WHERE sl.id = :id
                """
            ),
            {'id': new_sublocation_id},
        ).mappings().one()

        assert new_space['household_id'] == 'household-a'
        assert new_sublocation['household_id'] == 'household-a'

        # Zonder server-side actief huishouden wordt niets opgezocht of aangemaakt.
        _expect_http_error(
            400,
            lambda: resolve_space_id(conn, None, space_name='Onveilig'),
        )
        _expect_http_error(
            400,
            lambda: resolve_sublocation_id(
                conn,
                None,
                'space-a',
                sublocation_name='Onveilig',
            ),
        )

        b_counts = conn.execute(
            text(
                """
                SELECT
                    (SELECT COUNT(*) FROM spaces WHERE household_id = 'household-b') AS spaces,
                    (
                        SELECT COUNT(*)
                        FROM sublocations sl
                        JOIN spaces s ON s.id = sl.space_id
                        WHERE s.household_id = 'household-b'
                    ) AS sublocations
                """
            )
        ).mappings().one()
        assert b_counts['spaces'] == 1
        assert b_counts['sublocations'] == 1

    engine.dispose()
    print('INVENTORY_LOCATION_HOUSEHOLD_ISOLATION_GREEN')


if __name__ == '__main__':
    run_contract()

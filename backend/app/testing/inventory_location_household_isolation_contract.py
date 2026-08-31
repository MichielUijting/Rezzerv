"""PostgreSQL contract test for household isolation in inventory locations."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import text

from app.services.inventory_location_household_patch import (
    resolve_space_id,
    resolve_sublocation_id,
)
from app.testing.postgresql_onboarding_selftest_fixture import (
    create_postgresql_runtime_test_engine,
    reset_postgresql_test_database,
    seed_household,
)


def _expect_http_error(status_code: int, callback) -> None:
    try:
        callback()
    except HTTPException as exc:
        assert exc.status_code == status_code, exc
        return
    raise AssertionError(f"Verwachte HTTP {status_code} bleef uit")


def run_contract() -> None:
    reset_postgresql_test_database()
    engine = create_postgresql_runtime_test_engine()
    try:
        with engine.begin() as conn:
            seed_household(
                conn,
                household_id="household-a",
                name="Huishouden A",
            )
            seed_household(
                conn,
                household_id="household-b",
                name="Huishouden B",
            )
            conn.execute(
                text(
                    """
                    INSERT INTO spaces (id, naam, household_id, active)
                    VALUES
                        ('space-a', 'Voorraadkast', 'household-a', TRUE),
                        ('space-b', 'Voorraadkast', 'household-b', TRUE)
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO sublocations (id, naam, space_id, active)
                    VALUES
                        ('sub-a', 'Boven', 'space-a', TRUE),
                        ('sub-b', 'Boven', 'space-b', TRUE)
                    """
                )
            )

            assert resolve_space_id(conn, "household-a", "space-a") == "space-a"
            assert (
                resolve_sublocation_id(
                    conn,
                    "household-a",
                    "space-a",
                    "sub-a",
                )
                == "sub-a"
            )

            _expect_http_error(
                404,
                lambda: resolve_space_id(conn, "household-a", "space-b"),
            )
            _expect_http_error(
                404,
                lambda: resolve_sublocation_id(
                    conn,
                    "household-a",
                    "space-a",
                    "sub-b",
                ),
            )

            assert (
                resolve_space_id(
                    conn,
                    "household-a",
                    space_name="Voorraadkast",
                )
                == "space-a"
            )
            assert (
                resolve_sublocation_id(
                    conn,
                    "household-a",
                    "space-a",
                    sublocation_name="Boven",
                )
                == "sub-a"
            )

            _expect_http_error(
                404,
                lambda: resolve_sublocation_id(
                    conn,
                    "household-a",
                    "space-b",
                    sublocation_name="Nieuw vak",
                ),
            )

            new_space_id = resolve_space_id(
                conn,
                "household-a",
                space_name="Koele berging",
            )
            new_sublocation_id = resolve_sublocation_id(
                conn,
                "household-a",
                new_space_id,
                sublocation_name="Onderste plank",
            )

            new_space = conn.execute(
                text(
                    """
                    SELECT id, household_id
                    FROM spaces
                    WHERE id = :id
                    """
                ),
                {"id": new_space_id},
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
                {"id": new_sublocation_id},
            ).mappings().one()

            assert new_space["household_id"] == "household-a"
            assert new_sublocation["household_id"] == "household-a"

            _expect_http_error(
                400,
                lambda: resolve_space_id(conn, None, space_name="Onveilig"),
            )
            _expect_http_error(
                400,
                lambda: resolve_sublocation_id(
                    conn,
                    None,
                    "space-a",
                    sublocation_name="Onveilig",
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
            assert b_counts["spaces"] == 1
            assert b_counts["sublocations"] == 1
    finally:
        engine.dispose()

    print("INVENTORY_LOCATION_HOUSEHOLD_ISOLATION_POSTGRESQL_GREEN")
    print("INVENTORY_LOCATION_HOUSEHOLD_ISOLATION_GREEN")


if __name__ == "__main__":
    run_contract()

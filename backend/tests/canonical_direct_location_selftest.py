from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.services.canonical_direct_location_service import ensure_canonical_direct_location
from app.testing.onboarding_request_schema_fixture import install_location_schema


def run() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    with engine.begin() as conn:
        install_location_schema(conn)
        conn.execute(text("""
            INSERT INTO spaces (id, naam, household_id, active)
            VALUES
              ('legacy-direct', 'Directadsfsad', 'household-1', 0),
              ('cellar', 'Kelder', 'household-1', 1)
        """))

        direct_id = ensure_canonical_direct_location(conn, household_id="household-1")
        assert direct_id == "legacy-direct"
        row = conn.execute(text("""
            SELECT naam, active, is_direct
            FROM spaces
            WHERE id = 'legacy-direct'
        """)).mappings().one()
        assert row["naam"] == "Direct"
        assert int(row["active"]) == 1
        assert int(row["is_direct"]) == 1

        cellar = conn.execute(text("SELECT naam, active, is_direct FROM spaces WHERE id = 'cellar'")).mappings().one()
        assert cellar["naam"] == "Kelder"
        assert int(cellar["active"]) == 1
        assert int(cellar["is_direct"]) == 0

        second_id = ensure_canonical_direct_location(conn, household_id="household-1")
        assert second_id == direct_id
        assert conn.execute(text("SELECT COUNT(*) FROM spaces WHERE household_id = 'household-1' AND is_direct = 1")).scalar_one() == 1

    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE spaces SET naam = 'Niet Direct' WHERE id = 'legacy-direct'"))
    except SQLAlchemyError:
        pass
    else:
        raise AssertionError("Canonical Direct kon worden hernoemd")

    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM spaces WHERE id = 'legacy-direct'"))
    except SQLAlchemyError:
        pass
    else:
        raise AssertionError("Canonical Direct kon worden verwijderd")

    with engine.begin() as conn:
        row = conn.execute(text("SELECT naam, active FROM spaces WHERE id = 'legacy-direct'")).mappings().one()
        assert row["naam"] == "Direct"
        assert int(row["active"]) == 1

    print("CANONICAL_DIRECT_LOCATION_SELFTEST_GREEN")


if __name__ == "__main__":
    run()

from __future__ import annotations

import inspect
from datetime import date, timedelta

import pytest

from app.services import household_profile_service as service


def test_preferred_stores_are_cleaned_deduplicated_and_bounded():
    assert service._stores([" Winkel A ", "winkel a", "Winkel B"]) == [
        "Winkel A",
        "Winkel B",
    ]
    with pytest.raises(ValueError, match="Maximaal 10 voorkeurswinkels"):
        service._stores([f"Winkel {index}" for index in range(11)])


def test_resident_validation_keeps_birth_date_and_age_band_explicit():
    validated = service._validate_resident(
        first_name=" Alex ",
        last_name=" Test ",
        resident_type="adult",
        birth_date=date(1980, 1, 2),
        age_band=None,
    )
    assert validated == ("Alex", "Test", "adult", date(1980, 1, 2), None)

    with pytest.raises(ValueError, match="niet beide"):
        service._validate_resident(
            first_name="Alex",
            last_name=None,
            resident_type="adult",
            birth_date=date(1980, 1, 2),
            age_band="35_49",
        )

    with pytest.raises(ValueError, match="toekomst"):
        service._validate_resident(
            first_name="Alex",
            last_name=None,
            resident_type="adult",
            birth_date=date.today() + timedelta(days=1),
            age_band=None,
        )


def test_resident_type_and_age_band_fail_closed():
    with pytest.raises(ValueError, match="Kies volwassene"):
        service._validate_resident(
            first_name="Alex",
            last_name=None,
            resident_type="invalid",
            birth_date=None,
            age_band=None,
        )

    with pytest.raises(ValueError, match="Ongeldige leeftijdscategorie"):
        service._validate_resident(
            first_name="Alex",
            last_name=None,
            resident_type="adult",
            birth_date=None,
            age_band="unknown",
        )


def test_household_profile_sql_remains_household_scoped():
    source = inspect.getsource(service)
    assert "WHERE household_id = :household_id" in source
    assert "WHERE id = :id AND household_id = :household_id" in source
    assert "CAST(hm.household_id AS TEXT) = :household_id" in source
    assert "Gekoppelde gebruiker hoort niet bij dit huishouden" in source
    assert "resident_count" in source

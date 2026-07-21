"""Self-contained contract test for the central household context policy.

Run from the backend container or repository root with PYTHONPATH=backend:
    python -m app.testing.household_context_contract
"""

from app.services.household_context_adapter import resolve_legacy_household_context
from app.services.household_context_service import (
    HouseholdAccessDenied,
    HouseholdAuthenticationRequired,
    HouseholdMembershipRequired,
    resolve_household_context,
)
from app.services.household_object_guard import (
    assert_row_in_household,
    household_where_parameters,
)


def _expect_error(error_type, callback) -> None:
    try:
        callback()
    except error_type:
        return
    raise AssertionError(f"Verwachte fout bleef uit: {error_type.__name__}")


def run_contract() -> None:
    principal = {
        "user_id": "user-a",
        "email": "a@rezzerv.test",
        "active_household_id": "household-a",
    }
    memberships = [
        {
            "household_id": "household-a",
            "household_key": "alpha",
            "household_name": "Huishouden A",
            "role": "owner",
        }
    ]

    context = resolve_household_context(
        principal=principal,
        memberships=memberships,
    )
    assert context.user_id == "user-a"
    assert context.active_household_id == "household-a"
    assert context.role == "owner"
    assert context.display_role == "admin"

    # Een payload of padparameter mag geen toegang tot huishouden B verlenen.
    _expect_error(
        HouseholdAccessDenied,
        lambda: resolve_household_context(
            principal=principal,
            memberships=memberships,
            requested_household_id="household-b",
        ),
    )

    # Ontbrekende authenticatie en ontbrekend lidmaatschap zijn harde blokkades.
    _expect_error(
        HouseholdAuthenticationRequired,
        lambda: resolve_household_context(
            principal=None,
            memberships=memberships,
        ),
    )
    _expect_error(
        HouseholdMembershipRequired,
        lambda: resolve_household_context(
            principal=principal,
            memberships=[],
        ),
    )

    # Meerdere geverifieerde lidmaatschappen mogen alleen expliciet worden gekozen.
    multi_memberships = memberships + [
        {
            "household_id": "household-b",
            "household_key": "beta",
            "household_name": "Huishouden B",
            "role": "viewer",
        }
    ]
    context_b = resolve_household_context(
        principal=principal,
        memberships=multi_memberships,
        requested_household_id="household-b",
    )
    assert context_b.active_household_id == "household-b"
    assert context_b.role == "viewer"
    assert context_b.display_role == "kijker"

    # De legacy authadapter vertaalt alleen server-side profieldata en blijft
    # onderworpen aan dezelfde lidmaatschapscontrole.
    legacy_profile = {
        "role": "admin",
        "household_key": "alpha",
        "household_id": "household-a",
        "household_name": "Huishouden A",
    }
    legacy_context = resolve_legacy_household_context(
        email="a@rezzerv.test",
        profile=legacy_profile,
    )
    assert legacy_context.active_household_id == "household-a"
    _expect_error(
        HouseholdAccessDenied,
        lambda: resolve_legacy_household_context(
            email="a@rezzerv.test",
            profile=legacy_profile,
            requested_household_id="household-b",
        ),
    )

    # Objectmutaties hebben naast de queryfilter een tweede huishoudguard.
    assert assert_row_in_household(
        context,
        {"id": "inventory-a", "household_id": "household-a"},
    )["id"] == "inventory-a"
    _expect_error(
        HouseholdAccessDenied,
        lambda: assert_row_in_household(
            context,
            {"id": "inventory-b", "household_id": "household-b"},
        ),
    )
    assert household_where_parameters(context) == {"household_id": "household-a"}

    # De compatibiliteitsrepresentatie bevat geen ongeverifieerde payloaddata.
    payload = context.as_dict()
    assert payload["active_household_id"] == "household-a"
    assert set(payload) == {
        "user_id",
        "email",
        "active_household_id",
        "household_key",
        "household_name",
        "role",
        "display_role",
    }

    print("HOUSEHOLD_CONTEXT_CONTRACT_GREEN")


if __name__ == "__main__":
    run_contract()

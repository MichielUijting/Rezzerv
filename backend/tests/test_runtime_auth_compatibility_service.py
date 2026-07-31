from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services.runtime_auth_compatibility_service import (
    build_explicit_runtime_token,
    normalize_runtime_household_role,
    parse_explicit_runtime_token,
)


def test_unscoped_legacy_token_is_rejected() -> None:
    with pytest.raises(HTTPException) as exc_info:
        parse_explicit_runtime_token("Bearer rezzerv-dev-token")

    assert exc_info.value.status_code == 401


def test_explicit_user_bound_token_is_accepted() -> None:
    assert (
        parse_explicit_runtime_token(
            "Bearer rezzerv-dev-token::Eigenaar@Example.com"
        )
        == "eigenaar@example.com"
    )


def test_missing_or_invalid_explicit_identity_is_rejected() -> None:
    for authorization in (
        None,
        "",
        "Basic abc",
        "Bearer ",
        "Bearer rezzerv-dev-token::",
        "Bearer rezzerv-dev-token::geen-email",
    ):
        with pytest.raises(HTTPException) as exc_info:
            parse_explicit_runtime_token(authorization)
        assert exc_info.value.status_code == 401


@pytest.mark.parametrize(
    ("source_role", "role_key", "display_role"),
    (
        ("owner", "huishouden.eigenaar", "Eigenaar"),
        ("household.admin", "huishouden.eigenaar", "Eigenaar"),
        ("member", "huishouden.lid", "Lid"),
        ("household.advanced_member", "huishouden.lid", "Lid"),
        ("viewer", "huishouden.kijker", "Kijker"),
        ("household.viewer", "huishouden.kijker", "Kijker"),
    ),
)
def test_household_roles_keep_their_distinct_meaning(
    source_role: str,
    role_key: str,
    display_role: str,
) -> None:
    result = normalize_runtime_household_role(source_role)

    assert result.role_key == role_key
    assert result.display_role == display_role


def test_unknown_role_is_not_silently_downgraded_to_member() -> None:
    with pytest.raises(ValueError, match="Onbekende huishoudrol"):
        normalize_runtime_household_role("admin")


def test_token_builder_requires_and_normalizes_email() -> None:
    assert (
        build_explicit_runtime_token(" Gebruiker@Example.com ")
        == "rezzerv-dev-token::gebruiker@example.com"
    )

    with pytest.raises(ValueError):
        build_explicit_runtime_token("geen-email")

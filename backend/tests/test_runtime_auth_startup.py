from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import runtime_auth_startup
from app.api.runtime_auth_startup import (
    LEGACY_DEFAULT_ADMIN_EMAIL,
    apply_runtime_auth_override,
)


class _Result:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


class _Connection:
    def __init__(
        self,
        membership_role: str | None,
        platform_role_key: str | None,
        persisted_user: dict | None = None,
    ):
        self.membership_role = membership_role
        self.platform_role_key = platform_role_key
        self.persisted_user = persisted_user

    def execute(self, statement, params):
        sql = str(statement)
        if "FROM app_users" in sql:
            return _Result(self.persisted_user)
        if "FROM household_memberships" in sql:
            return _Result(
                {"role": self.membership_role} if self.membership_role else None
            )
        if "FROM auth_platform_user_roles" in sql:
            return _Result(
                {"role_key": self.platform_role_key}
                if self.platform_role_key
                else None
            )
        raise AssertionError(f"Onverwachte query: {sql}")


class _Begin:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc, tb):
        return False


class _Engine:
    def __init__(
        self,
        membership_role: str | None,
        platform_role_key: str | None,
        persisted_user: dict | None = None,
    ):
        self.connection = _Connection(
            membership_role,
            platform_role_key,
            persisted_user,
        )

    def begin(self):
        return _Begin(self.connection)


def _main_module(
    *,
    membership_role="member",
    platform_role_key=None,
    persisted_user=None,
):
    records = {
        LEGACY_DEFAULT_ADMIN_EMAIL: {
            "email": LEGACY_DEFAULT_ADMIN_EMAIL,
            "role": "admin",
        },
        "eigenaar@example.com": {
            "email": "eigenaar@example.com",
            "role": "admin",
        },
        "kijker@example.com": {
            "email": "kijker@example.com",
            "role": "member",
        },
        "supergebruiker@rezzerv.local": {
            "email": "supergebruiker@rezzerv.local",
            "user_id": "supergebruiker@rezzerv.local",
            "role": "member",
        },
    }

    return SimpleNamespace(
        users={key: dict(value) for key, value in records.items()},
        engine=_Engine(membership_role, platform_role_key, persisted_user),
        get_user_record=lambda email: records.get(str(email).strip().lower()),
        get_current_user_from_authorization=lambda authorization: None,
        build_auth_token=lambda email: "legacy",
    )


def test_unscoped_token_and_legacy_admin_are_disabled() -> None:
    main_module = _main_module()
    apply_runtime_auth_override(main_module)

    assert LEGACY_DEFAULT_ADMIN_EMAIL not in main_module.users
    assert main_module.get_user_record(LEGACY_DEFAULT_ADMIN_EMAIL) is None

    with pytest.raises(HTTPException) as exc_info:
        main_module.get_current_user_from_authorization(
            "Bearer rezzerv-dev-token"
        )
    assert exc_info.value.status_code == 401

    with pytest.raises(HTTPException) as exc_info:
        main_module.get_current_user_from_authorization(
            f"Bearer rezzerv-dev-token::{LEGACY_DEFAULT_ADMIN_EMAIL}"
        )
    assert exc_info.value.status_code == 401


def test_household_owner_is_not_represented_as_platform_admin() -> None:
    main_module = _main_module(membership_role="owner")
    apply_runtime_auth_override(main_module)

    user = main_module.get_current_user_from_authorization(
        "Bearer rezzerv-dev-token::eigenaar@example.com"
    )

    assert user["role"] == "owner"
    assert user["platform_role_key"] is None


def test_viewer_role_is_preserved() -> None:
    main_module = _main_module(membership_role="viewer")
    apply_runtime_auth_override(main_module)

    user = main_module.get_current_user_from_authorization(
        "Bearer rezzerv-dev-token::kijker@example.com"
    )

    assert user["role"] == "viewer"


def test_only_supergebruiker_gets_temporary_legacy_admin_representation() -> None:
    main_module = _main_module(
        membership_role="owner",
        platform_role_key="platform.supergebruiker",
    )
    apply_runtime_auth_override(main_module)

    user = main_module.get_current_user_from_authorization(
        "Bearer rezzerv-dev-token::supergebruiker@rezzerv.local"
    )

    assert user["role"] == "admin"
    assert user["platform_role_key"] == "platform.supergebruiker"


def test_persisted_supergebruiker_is_accepted_without_legacy_runtime_record(monkeypatch) -> None:
    email = "supergebruiker@rezzerv.local"
    main_module = _main_module(
        membership_role="owner",
        platform_role_key="platform.supergebruiker",
        persisted_user={"user_id": email, "email": email},
    )
    main_module.users.pop(email, None)
    main_module.get_user_record = lambda requested_email: None

    class _Inspector:
        def get_table_names(self):
            return ["app_users"]

        def get_columns(self, table_name):
            assert table_name == "app_users"
            return [{"name": "id"}, {"name": "email"}]

    monkeypatch.setattr(runtime_auth_startup, "inspect", lambda conn: _Inspector())
    apply_runtime_auth_override(main_module)

    user = main_module.get_current_user_from_authorization(
        f"Bearer rezzerv-dev-token::{email}"
    )

    assert user["email"] == email
    assert user["user_id"] == email
    assert user["role"] == "admin"
    assert user["platform_role_key"] == "platform.supergebruiker"


def test_override_is_idempotent_and_token_builder_is_explicit() -> None:
    main_module = _main_module()
    apply_runtime_auth_override(main_module)
    first_getter = main_module.get_current_user_from_authorization

    apply_runtime_auth_override(main_module)

    assert main_module.get_current_user_from_authorization is first_getter
    assert (
        main_module.build_auth_token("Gebruiker@Example.com")
        == "rezzerv-dev-token::gebruiker@example.com"
    )

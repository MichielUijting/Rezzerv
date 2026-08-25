from app.services.authorization_foundation_service import (
    PLATFORM_ADMIN_PERMISSIONS,
    ROLE_PERMISSIONS,
    V2_SUPERUSER_TARGET_PERMISSIONS,
    permissions_for_session_role,
)


def test_member_matrix_matches_household_v2_decisions():
    permissions = permissions_for_session_role("member")
    assert "inventory.correct" in permissions
    assert "receipts.delete" in permissions
    assert "shopping_list.manage" in permissions
    assert "stores.manage" in permissions
    assert "loyalty.manage" in permissions
    assert "articles.update" not in permissions
    assert "locations.update" not in permissions
    assert "insights.export" not in permissions
    assert "catalog.update" not in permissions
    assert "admin.access" not in permissions
    assert not any(key.startswith("platform.") for key in permissions)


def test_admin_inherits_member_and_adds_household_admin_rights():
    member = permissions_for_session_role("member")
    admin = permissions_for_session_role("admin")
    assert member <= admin
    assert "articles.update" in admin
    assert "locations.manage" in admin
    assert "permissions.manage" in admin
    assert "admin.access" in admin
    assert "catalog.update" not in admin
    assert "catalog.manage" not in admin
    assert not any(key.startswith("platform.") for key in admin)


def test_superuser_system_role_combines_h0_household_and_functional_v2_platform_rights():
    permissions = permissions_for_session_role("owner", platform_superuser=True)
    platform_permissions = {key for key in permissions if key.startswith("platform.")}

    assert "admin.access" in permissions
    assert "catalog.update" in permissions
    assert "catalog.manage" in permissions
    assert platform_permissions == set(V2_SUPERUSER_TARGET_PERMISSIONS)
    assert "platform.catalog.manage" in platform_permissions
    assert "platform.gpc.manage" in platform_permissions
    assert "platform.external_sources.manage" in platform_permissions
    assert "platform.support_access.mutate" in platform_permissions
    assert not (set(PLATFORM_ADMIN_PERMISSIONS) & platform_permissions)
    assert "platform.special_roles.manage" not in platform_permissions


def test_legacy_frontteam_household_role_is_not_platform_authority():
    permissions = permissions_for_session_role("frontteam")
    assert "inventory.view" in permissions
    assert "articles.manage" in permissions
    assert "catalog.manage" in permissions
    assert "admin.access" in permissions
    assert not any(key.startswith("platform.") for key in permissions)


def test_active_frontteam_platform_role_is_separate_from_household_role():
    permissions = ROLE_PERMISSIONS["platform.frontteam"]
    assert "platform.frontteam_messages.create" in permissions
    assert "platform.external_products.view" in permissions
    assert "platform.external_products.search" in permissions
    assert "platform.external_products.link_existing" in permissions
    assert "platform.special_roles.manage" not in permissions

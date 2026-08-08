from app.services.authorization_foundation_service import permissions_for_session_role


def test_member_matrix_matches_po_decisions():
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
    assert "gpc.update" not in permissions
    assert "admin.access" not in permissions
    assert "frontteam.external_databases.access" not in permissions


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
    assert "frontteam.external_databases.access" not in admin


def test_owner_is_superuser_household_role_without_frontteam_access():
    owner = permissions_for_session_role("owner", platform_superuser=True)
    assert "admin.access" in owner
    assert "catalog.update" in owner
    assert "catalog.manage" in owner
    assert "platform.audit.view" in owner
    assert "platform.permissions.manage" in owner
    assert "frontteam.external_databases.access" not in owner


def test_frontteam_role_has_household_and_external_database_rights_only():
    permissions = permissions_for_session_role("frontteam")
    assert "inventory.view" in permissions
    assert "articles.manage" in permissions
    assert "catalog.manage" in permissions
    assert "admin.access" in permissions
    assert "frontteam.external_databases.access" in permissions
    assert not any(key.startswith("platform.") for key in permissions)

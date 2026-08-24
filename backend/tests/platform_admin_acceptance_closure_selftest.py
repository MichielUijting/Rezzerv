from __future__ import annotations

import json
import re
from pathlib import Path

from app.services.authorization_foundation_service import (
    ACTIVE_SUPERUSER_PLATFORM_PERMISSIONS,
    PLATFORM_ADMIN_PERMISSIONS,
    ROLE_PERMISSIONS,
    V2_SUPERUSER_TARGET_PERMISSIONS,
)


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"

EXPECTED_CAPABILITIES = (
    ("diagnostics", "platform.diagnostics.view", "/platform/diagnostiek", "PlatformDiagnosticsPage"),
    ("logs", "platform.logs.view", "/platform/logs", "PlatformLogsPage"),
    ("audit", "platform.audit.view", "/platform/audit", "PlatformAuditPage"),
    ("integrations", "platform.integrations.manage", "/platform/integraties", "PlatformIntegrationsPage"),
    ("background-jobs", "platform.background_jobs.manage", "/platform/achtergrondtaken", "PlatformBackgroundJobsPage"),
    ("recovery", "platform.recovery.manage", "/platform/herstel", "PlatformRecoveryPage"),
    ("technical-configuration", "platform.technical_configuration.manage", "/platform/technische-configuratie", "PlatformTechnicalConfigurationPage"),
    ("test-fixtures", "platform.test_fixtures.manage", "/platform/testfixtures", "PlatformTestFixturesPage"),
    ("feature-flags", "platform.feature_flags.manage", "/platform/featureflags", "PlatformFeatureFlagsPage"),
    ("sessions", "platform.sessions.revoke", "/platform/sessies", "PlatformSessionsPage"),
    ("users", "platform.users.suspend", "/platform/gebruikers", "PlatformUsersPage"),
    ("permissions", "platform.permissions.manage", "/platform/autorisaties", "PlatformAuthorizationsPage"),
)

EXPECTED_PLATFORM_ADMIN_PERMISSIONS = frozenset(item[1] for item in EXPECTED_CAPABILITIES)

EXPECTED_REGRESSION_SPECS = (
    "tests/e2e/session-none-context.frontend-regression.spec.js",
    "tests/e2e/platform-test-fixtures.frontend-regression.spec.js",
    "tests/e2e/platform-background-jobs.frontend-regression.spec.js",
    "tests/e2e/platform-recovery.frontend-regression.spec.js",
    "tests/e2e/platform-integrations.frontend-regression.spec.js",
    "tests/e2e/platform-feature-flags.frontend-regression.spec.js",
    "tests/e2e/platform-sessions.frontend-regression.spec.js",
    "tests/e2e/platform-users.frontend-regression.spec.js",
    "tests/e2e/platform-authorizations.frontend-regression.spec.js",
    "tests/e2e/platform-logs.frontend-regression.spec.js",
)


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _assert_navigation_matrix() -> None:
    source = _read("frontend/src/features/platform/platformNavigation.js")
    items_source = source.split("export const PLATFORM_NAVIGATION_ITEMS", 1)[1]
    pattern = re.compile(
        r"\{\s*key:\s*'([^']+)',\s*group:\s*'([^']+)',\s*permission:\s*'([^']+)',"
        r".*?route:\s*'([^']+)'",
        re.DOTALL,
    )
    actual = tuple((key, permission, route) for key, _group, permission, route in pattern.findall(items_source))
    expected = tuple((key, permission, route) for key, permission, route, _page in EXPECTED_CAPABILITIES)
    assert actual == expected, f"canonical platform navigation drifted: {actual!r}"


def _assert_authorization_matrix() -> None:
    assert frozenset(PLATFORM_ADMIN_PERMISSIONS) == EXPECTED_PLATFORM_ADMIN_PERMISSIONS
    assert frozenset(ROLE_PERMISSIONS["platform.platform_admin"]) == EXPECTED_PLATFORM_ADMIN_PERMISSIONS

    ip_owner = frozenset(ROLE_PERMISSIONS["platform.ip_owner"])
    assert EXPECTED_PLATFORM_ADMIN_PERMISSIONS <= ip_owner
    assert "platform.special_roles.manage" in ip_owner
    assert "platform.special_roles.manage" not in ROLE_PERMISSIONS["platform.platform_admin"]

    superuser = frozenset(ROLE_PERMISSIONS["platform.superuser"])
    assert superuser == frozenset(ACTIVE_SUPERUSER_PLATFORM_PERMISSIONS)
    assert superuser == frozenset(V2_SUPERUSER_TARGET_PERMISSIONS)
    assert not (superuser & EXPECTED_PLATFORM_ADMIN_PERMISSIONS)
    assert "platform.special_roles.manage" not in superuser


def _assert_every_capability_has_concrete_page() -> None:
    source = _read("frontend/src/features/platform/PlatformCapabilityPage.jsx")
    for key, _permission, _route, page in EXPECTED_CAPABILITIES:
        assert f"import {page} from './{page}.jsx'" in source, f"missing import for {page}"
        dispatch = re.compile(
            rf"if \(item\?\.key === '{re.escape(key)}'\) \{{\s*return <{re.escape(page)} />\s*\}}",
            re.DOTALL,
        )
        assert dispatch.search(source), f"canonical capability {key} still falls through the generic shell"


def _assert_none_native_route_boundary() -> None:
    source = _read("frontend/src/app/router/AppRouter.jsx")
    required_fragments = (
        "const platformRoutes = PLATFORM_NAVIGATION_ITEMS.map((item) => ({",
        "path: item.route,",
        "permission={item.permission}",
        "allowNone",
        "<PlatformCapabilityPage item={item} />",
        "...platformRoutes,",
        "{ path: '/superuser', element: <ProtectedSuperuser><SuperuserDashboardPage /></ProtectedSuperuser> },",
    )
    for fragment in required_fragments:
        assert fragment in source, f"platform route boundary drifted: missing {fragment!r}"

    platform_route_block = source.split("const platformRoutes =", 1)[1].split("const router =", 1)[0]
    assert "ProtectedPermission" in platform_route_block
    assert "permission={item.permission}" in platform_route_block
    assert "allowNone" in platform_route_block
    assert "ProtectedSuperuser" not in platform_route_block


def _assert_frontend_authority_hygiene() -> None:
    pages = tuple(item[3] for item in EXPECTED_CAPABILITIES)
    forbidden = ("'Authorization'", '"Authorization"', "Bearer ", "x-admin-key")
    for page in pages:
        source = _read(f"frontend/src/features/platform/{page}.jsx")
        for marker in forbidden:
            assert marker not in source, f"{page} fabricates forbidden browser authority marker {marker!r}"


def _assert_full_regression_allow_list() -> None:
    package = json.loads(_read("frontend/package.json"))
    command = package["scripts"]["test:e2e:frontend-regression"]
    for spec in EXPECTED_REGRESSION_SPECS:
        assert spec in command, f"canonical full frontend regression omits {spec}"


def main() -> None:
    _assert_navigation_matrix()
    _assert_authorization_matrix()
    _assert_every_capability_has_concrete_page()
    _assert_none_native_route_boundary()
    _assert_frontend_authority_hygiene()
    _assert_full_regression_allow_list()
    print("PLATFORM_ADMIN_9_1_7_ACCEPTANCE_CLOSURE_GREEN")


if __name__ == "__main__":
    main()

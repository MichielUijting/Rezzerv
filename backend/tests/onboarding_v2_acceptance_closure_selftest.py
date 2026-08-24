from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

PRODUCT_CONFIG_SESSION_FORBIDDEN = {
    "inventory_tracking_level",
    "location_tracking_level",
    "shopping_enabled",
    "almost_out_enabled",
    "almost_out_notifications_enabled",
    "receipt_processing_enabled",
    "recipes_enabled",
    "unpacking_enabled",
    "simple_inventory_enabled",
    "product_config",
    "product_configuration",
}

EVIDENCE_FILES = [
    # A — account foundation
    "backend/tests/consumer_account_registration_selftest.py",
    # B — use-case foundation
    "backend/tests/onboarding_use_case_foundation_selftest.py",
    # C — Inhuis halen
    "backend/tests/inhuis_halen_onboarding_selftest.py",
    # D — Wat Inhuis
    "backend/tests/wat_inhuis_onboarding_selftest.py",
    # E — Waar Inhuis + shared/locationless foundations
    "backend/tests/waar_inhuis_onboarding_selftest.py",
    "backend/tests/shared_household_minimum_selftest.py",
    "backend/tests/test_locationless_inventory_identity_guard.py",
    # F/G — dynamic product projection
    "backend/tests/dynamic_navigation_product_projection_selftest.py",
    "frontend/tests/dynamic-home-navigation.contract.mjs",
    "frontend/tests/dynamic-settings-navigation.contract.mjs",
    # H — circular expansion
    "backend/tests/circular_capability_expansion_selftest.py",
    "frontend/tests/circular-capability-expansion.contract.mjs",
    # I.1 — invitation foundation
    "backend/tests/household_invitation_foundation_selftest.py",
    "backend/tests/household_invitation_target_policy_selftest.py",
    # I.2 — acceptance/context
    "backend/tests/household_invitation_acceptance_selftest.py",
    "frontend/tests/invitation-acceptance.contract.mjs",
    # I.3 — delivery/security
    "backend/tests/household_invitation_delivery_selftest.py",
    "backend/tests/household_invitation_delivery_redaction_selftest.py",
    # I.4 — UI + legacy closure
    "backend/tests/household_member_legacy_closure_selftest.py",
    "frontend/src/features/settings/SettingsHouseholdPage.invitations.contract.test.js",
]


def read(relative_path: str) -> str:
    path = ROOT / relative_path
    assert path.is_file(), f"Required closure evidence missing: {relative_path}"
    return path.read_text(encoding="utf-8")


def assert_evidence_set_exists() -> None:
    for relative_path in EVIDENCE_FILES:
        path = ROOT / relative_path
        assert path.is_file(), f"Required A→I acceptance evidence missing: {relative_path}"


def _function_string_constants(relative_path: str, function_name: str) -> set[str]:
    source = read(relative_path)
    module = ast.parse(source, filename=relative_path)
    function = next(
        (
            node
            for node in ast.walk(module)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
        ),
        None,
    )
    assert function is not None, f"Function {function_name} missing from {relative_path}"
    return {
        node.value
        for node in ast.walk(function)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def assert_public_session_excludes_product_configuration() -> None:
    constants = _function_string_constants(
        "backend/app/services/server_session_service.py",
        "public_session_payload",
    )
    leaked = sorted(PRODUCT_CONFIG_SESSION_FORBIDDEN.intersection(constants))
    assert not leaked, f"Product configuration leaked into public /api/session payload: {leaked}"


def assert_invitation_registration_stays_invitation_specific() -> None:
    source = read("frontend/src/features/auth/InvitationAcceptancePage.jsx")
    assert "/api/auth/register" not in source, "Invitation registration must not call generic registration"
    assert "/api/household/invitations/accept/" in source, "Invitation acceptance endpoint missing"
    assert "/register" in source, "Invitation-specific registration endpoint missing"


def assert_invited_membership_role_is_canonical_member() -> None:
    source = read("backend/app/services/household_invitation_acceptance_service.py")
    assert "INVITATION_ROLE_KEY" in source, "Invitation role constant is not used during acceptance"
    assert "create_canonical_membership_role" in source, "Canonical membership role creation is missing"
    assert "role_key != INVITATION_ROLE_KEY" in source, "Canonical invited-member role is not asserted"


def assert_session_household_switch_is_server_authoritative() -> None:
    source = read("backend/app/api/session_household_routes.py")
    assert '@router.get("/api/session/households")' in source, "Server household list route missing"
    assert '@router.post("/api/session/household")' in source, "Server household switch route missing"
    assert "rotate_active_household(" in source, "Household switch must delegate to server-side rotation"
    assert "resolve_server_session(" in source, "Household switch must resolve the authoritative session"


def assert_legacy_member_creation_is_permanently_closed() -> None:
    source = read("backend/app/api/legacy_household_member_creation_closure.py")
    assert '"/api/household/members"' in source, "Legacy member-create path is no longer explicitly targeted"
    assert "status_code=410" in source or "status_code = 410" in source, "Legacy member create must remain HTTP 410"
    assert '"/api/household/invitations"' in source, "Legacy closure must point clients to invitation API"


def assert_public_invitation_route_exists() -> None:
    source = read("frontend/src/app/router/AppRouter.jsx")
    assert "/uitnodiging/:token" in source, "Public invitation acceptance route missing"


def assert_closure_document_records_the_operational_boundary() -> None:
    source = read("docs/product/ONBOARDING_V2_ACCEPTANCE_CLOSURE.md")
    required_fragments = [
        "A→I acceptance matrix",
        "application-complete",
        "Product relevance is not authorization",
        "REZZERV_EMAIL_ENABLED=true",
        "reverse-proxy/application access-log handling",
        "browser referrer policy",
        "ONBOARDING_V2_I5_ACCEPTANCE_CLOSURE_GREEN",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in source]
    assert not missing, f"Closure document misses required operational boundary text: {missing}"


def main() -> None:
    assert (ROOT / "docs/product/INHUIS_PRODUCTONTWERP_ONBOARDING_V2.md").is_file()
    assert_evidence_set_exists()
    assert_public_session_excludes_product_configuration()
    assert_invitation_registration_stays_invitation_specific()
    assert_invited_membership_role_is_canonical_member()
    assert_session_household_switch_is_server_authoritative()
    assert_legacy_member_creation_is_permanently_closed()
    assert_public_invitation_route_exists()
    assert_closure_document_records_the_operational_boundary()
    print("ONBOARDING_V2_I5_ACCEPTANCE_CLOSURE_SELFTEST_GREEN")


if __name__ == "__main__":
    main()

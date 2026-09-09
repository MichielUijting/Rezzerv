from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "frontend" / "tests" / "e2e" / "p0-platform-authority.fullstack.spec.js"
FIXTURE = ROOT / "scripts" / "acceptance" / "l4_07_platform_browser_authority.py"
WORKFLOW = ROOT / ".github" / "workflows" / "p0-platform-authority-fullstack-postgresql-validation.yml"


def test_l4_07_has_real_superuser_and_ip_owner_browser_authorities():
    spec = SPEC.read_text(encoding="utf-8")
    assert "home-tile-superuser" in spec
    assert "superuser-dashboard" in spec
    assert "Superuser alleen-lezen status" in spec
    assert "platform-authorizations-page" in spec
    assert "Platformbeheerder toekennen" in spec
    assert "Definitief toekennen" in spec
    assert "P0_L4_07_SUPERUSER_READ_ONLY_BROWSER_GREEN" in spec
    assert "P0_L4_07_IP_OWNER_ROLE_GRANT_THROUGH_UI_GREEN" in spec
    assert "page.route(" not in spec
    assert "context.route(" not in spec
    for method in ("post", "put", "patch", "delete"):
        assert f"page.request.{method}(" not in spec


def test_l4_07_fixture_and_workflow_prove_role_boundary_and_audit():
    fixture = FIXTURE.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    for role in ("platform.platform_admin", "platform.superuser", "platform.ip_owner"):
        assert role in fixture
    assert "platform.special_roles.manage" in fixture
    assert "P0_L4_07_SUPERUSER_ROLE_BOUNDARY_GREEN" in fixture
    assert "P0_L4_07_IP_OWNER_ROLE_GRANT_AUDIT_GREEN" in fixture
    assert "P0_L4_07_STANDALONE_TARGET_NO_HOUSEHOLD_GREEN" in fixture
    assert "P0_PLATFORM_AUTHORITY_FULLSTACK_POSTGRESQL_GREEN" in workflow
    assert "p0-l4-07-superuser-browser-proof.json" in workflow
    assert "p0-l4-07-ip-owner-browser-proof.json" in workflow

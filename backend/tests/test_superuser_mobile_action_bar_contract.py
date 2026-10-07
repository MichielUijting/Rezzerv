from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_superuser_mobile_action_bar_setting_has_platform_read_and_superuser_write_contract():
    source = _read("backend/app/api/superuser_routes.py")
    assert 'MOBILE_ACTION_BAR_LOCK_KEY = "mobile_action_bar_locked"' in source
    assert "DEFAULT_MOBILE_ACTION_BAR_LOCKED = True" in source
    assert '@router.get("/api/platform/mobile-action-bar")' in source
    assert '@router.put("/api/superuser/mobile-action-bar")' in source
    assert '"fixed_keys": ["winkelen", "kassa", "kassabonnen", "voorraad"]' in source
    assert '_require_platform_superuser' in source
    assert 'action="superuser.mobile_action_bar.updated"' in source


def test_mobile_action_bar_setting_reuses_alembic_owned_platform_settings_table():
    source = _read("backend/app/api/superuser_routes.py")
    migration = _read("backend/alembic/versions/20260926_01_platform_home_settings.py")
    assert "_write_platform_setting" in source
    assert "platform_home_settings" in source
    assert 'op.create_table(\n        "platform_home_settings"' in migration

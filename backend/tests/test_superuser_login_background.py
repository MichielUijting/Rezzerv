from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.superuser_routes import LOGIN_BACKGROUND_MAX_BYTES, _validate_jpeg


def test_login_background_accepts_jpeg_signature():
    _validate_jpeg(b"\xff\xd8\xff" + b"inhuis" + b"\xff\xd9")


def test_login_background_rejects_non_jpeg():
    with pytest.raises(HTTPException) as exc:
        _validate_jpeg(b"not-a-jpeg")
    assert exc.value.status_code == 415


def test_login_background_rejects_oversize_jpeg():
    with pytest.raises(HTTPException) as exc:
        _validate_jpeg(b"\xff\xd8\xff" + (b"x" * LOGIN_BACKGROUND_MAX_BYTES) + b"\xff\xd9")
    assert exc.value.status_code == 413


def test_login_background_mutations_are_superuser_guarded():
    source = (Path(__file__).parents[1] / "app" / "api" / "superuser_routes.py").read_text(encoding="utf-8")
    update_block = source.split('async def update_login_background', 1)[1].split('def delete_login_background', 1)[0]
    delete_block = source.split('def delete_login_background', 1)[1].split('@router.get("/api/superuser/bootstrap")', 1)[0]
    assert "_require_platform_superuser" in update_block
    assert "_require_platform_superuser" in delete_block

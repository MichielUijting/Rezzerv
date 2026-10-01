from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.integrations.retailer_accounts.ah import (
    AH_CLIENT_ID,
    AH_REDIRECT_URI,
    build_ah_login_url,
)


def test_ah_uses_single_secure_oauth_authorize_route() -> None:
    url = build_ah_login_url()
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "login.ah.nl"
    assert parsed.path == "/secure/oauth/authorize"
    assert query == {
        "client_id": ["appie"],
        "response_type": ["code"],
        "redirect_uri": [AH_REDIRECT_URI],
    }
    assert AH_CLIENT_ID == "appie"


def test_legacy_ah_login_route_is_absent() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "integrations"
        / "retailer_accounts"
        / "ah.py"
    ).read_text(encoding="utf-8")

    assert '"/login?"' not in source
    assert "appie-ios" not in source

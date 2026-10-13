"""Credential-safe Picnic protocol tests, no live network, no customer data."""
import hashlib

import httpx
import pytest

from app.integrations.picnic_auth_protocol import PicnicAuthClient, PicnicAuthError
from app.integrations.picnic_http_transport import PicnicHttpTransport, PICNIC_API_BASE


def test_login_and_two_factor_never_store_password_or_sms():
    calls = []
    def transport(method, path, data, token):
        calls.append((method, path, data, token))
        if path == "/user/login":
            return {"second_factor_authentication_required": True}, {"X-Picnic-Auth": "pendingkey1234"}
        if path == "/user/2fa/generate":
            return {}, {}
        return {}, {"x-picnic-auth": "verifiedkey1234"}
    client = PicnicAuthClient(transport)
    result = client.login("tester@example.test", "secret-pass")
    assert result.requires_2fa is True
    assert result.auth_key == "pendingkey1234"
    assert calls[0] == ("POST", "/user/login", {
        "key": "tester@example.test",
        "secret": hashlib.md5(b"secret-pass").hexdigest(),
        "client_id": 30100,
    }, None)
    client.request_sms(result.auth_key)
    assert calls[1] == ("POST", "/user/2fa/generate", {"channel": "SMS"}, "pendingkey1234")
    assert client.verify_sms(result.auth_key, "123456") == "verifiedkey1234"
    assert calls[2] == ("POST", "/user/2fa/verify", {"otp": "123456"}, "pendingkey1234")
    assert not any("secret-pass" in repr(c) for c in calls)


def test_malformed_sms_and_missing_token_fail_closed():
    client = PicnicAuthClient(lambda *args: ({}, {}))
    with pytest.raises(PicnicAuthError):
        client.login("tester@example.test", "pass")
    with pytest.raises(PicnicAuthError):
        client.verify_sms("pendingkey1234", "123abc")


def test_login_errors_do_not_echo_provider_secrets():
    def transport(*args):
        raise RuntimeError("password=secret-pass key=internal-private-value")
    with pytest.raises(PicnicAuthError) as e:
        PicnicAuthClient(transport).login("tester@example.test", "secret-pass")
    assert "secret-pass" not in str(e.value)
    assert "internal-private-value" not in str(e.value)


def test_transport_blocks_non_allowlisted_requests_without_network():
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(200, headers={"x-picnic-auth": "verifiedkey1234"}, json={"second_factor_authentication_required": False})
    httpclient = httpx.Client(transport=httpx.MockTransport(handler))
    transport = PicnicHttpTransport(httpclient)
    with pytest.raises(PicnicAuthError):
        transport.send("POST", "/order/checkout", {}, "verifiedkey1234")
    with pytest.raises(PicnicAuthError):
        transport.send("GET", "https://example.test/steal", None, "verifiedkey1234")
    with pytest.raises(PicnicAuthError):
        transport.send("GET", "/deliveries/../../user", None, "verifiedkey1234")
    assert calls == []
    result, headers = transport.send("POST", "/user/login", {"key": "user", "secret": "hashed"}, None)
    assert result["second_factor_authentication_required"] is False
    assert headers["x-picnic-auth"] == "verifiedkey1234"
    assert str(calls[0].url).startswith(PICNIC_API_BASE)
    assert calls[0].headers.get("x-picnic-auth") is None
    assert len(calls) == 1


def test_unknown_api_2fa_response_fails_closed():
    with pytest.raises(PicnicAuthError):
        PicnicAuthClient(lambda *args: ({}, {"x-picnic-auth": "verifiedkey1234"})).login("test", "pass")

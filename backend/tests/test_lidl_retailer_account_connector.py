from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.integrations.retailer_accounts.lidl import (
    LidlAccountSession,
    LidlAuthAttempt,
    LidlReceiptClient,
    LidlReceiptSummary,
    build_lidl_login_attempt,
    extract_lidl_authorization_code,
)
from app.integrations.retailer_receipts import normalize_retailer_receipt
from app.services.retailer_account_runtime_store import (
    delete_lidl_auth_attempt,
    delete_lidl_session,
    get_lidl_auth_attempt,
    get_lidl_session,
    lidl_session_status,
    set_lidl_auth_attempt,
    set_lidl_session,
)


def test_build_lidl_login_attempt_uses_pkce_and_no_account_credentials() -> None:
    attempt = build_lidl_login_attempt()
    parsed = urlparse(attempt.login_url)
    query = parse_qs(parsed.query)

    assert parsed.netloc == "accounts.lidl.com"
    assert query["client_id"] == ["LidlPlusNativeClient"]
    assert query["redirect_uri"] == ["com.lidlplus.app://callback"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["Country"] == ["NL"]
    assert query["language"] == ["nl-NL"]
    assert query["state"] == [attempt.state]
    assert attempt.code_verifier not in attempt.login_url
    assert "password" not in attempt.login_url.lower()


def test_extract_lidl_authorization_code_requires_matching_state() -> None:
    assert (
        extract_lidl_authorization_code(
            "com.lidlplus.app://callback?code=abc123&state=state-1",
            expected_state="state-1",
        )
        == "abc123"
    )
    with pytest.raises(ValueError):
        extract_lidl_authorization_code(
            "com.lidlplus.app://callback?code=abc123&state=wrong",
            expected_state="state-1",
        )


def test_exchange_code_uses_pkce_without_password() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = request.content.decode()
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "access_token": "access-value",
                "refresh_token": "refresh-value",
                "expires_in": 3600,
            },
        )

    client = LidlReceiptClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    attempt = LidlAuthAttempt(
        code_verifier="verifier-value",
        state="state-value",
        nonce="nonce-value",
        login_url="https://accounts.lidl.com/connect/authorize",
        created_at=datetime.now(timezone.utc),
    )
    session = client.exchange_code(
        "com.lidlplus.app://callback?code=code-value&state=state-value",
        attempt,
    )

    assert seen["path"] == "/connect/token"
    assert "grant_type=authorization_code" in str(seen["body"])
    assert "code_verifier=verifier-value" in str(seen["body"])
    assert "client_id=LidlPlusNativeClient" in str(seen["body"])
    assert "password" not in str(seen["body"]).lower()
    assert seen["authorization"] is None
    assert session.access_token == "access-value"
    assert session.refresh_token == "refresh-value"


def test_expired_session_refreshes_before_receipt_list() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/connect/token":
            return httpx.Response(
                200,
                json={
                    "access_token": "new-access",
                    "refresh_token": "new-refresh",
                    "expires_in": 3600,
                },
            )
        assert request.headers["authorization"] == "Bearer new-access"
        return httpx.Response(
            200,
            json={
                "tickets": [
                    {
                        "id": "receipt-1",
                        "date": "2026-09-20T12:30:00",
                        "totalAmount": "7,25",
                    }
                ],
                "totalCount": 1,
                "size": 25,
            },
        )

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = LidlReceiptClient(http_client=http)
    expired = LidlAccountSession(
        access_token="old-access",
        refresh_token="old-refresh",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )

    active, receipts = client.list_receipts(expired, limit=20)

    assert paths == ["/connect/token", "/api/v2/NL/tickets"]
    assert active.access_token == "new-access"
    assert receipts == [
        LidlReceiptSummary(
            receipt_id="receipt-1",
            date_time="2026-09-20T12:30:00",
            total_amount=7.25,
        )
    ]


def test_lidl_receipt_details_map_gtin_and_discounts_to_canonical_contract() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/NL/tickets/receipt-1"
        return httpx.Response(
            200,
            json={
                "id": "receipt-1",
                "date": "2026-09-20T12:30:00",
                "totalAmount": "5,48",
                "totalDiscount": "0,50",
                "itemsLine": [
                    {
                        "name": "VOLLE MELK",
                        "quantity": "2",
                        "currentUnitPrice": "1,49",
                        "originalAmount": "2,98",
                        "codeInput": "8712345678901",
                        "discounts": [{"description": "Lidl Plus", "amount": "0,50"}],
                    },
                    {
                        "name": "BROOD",
                        "quantity": "1",
                        "currentUnitPrice": "2,50",
                        "originalAmount": "2,50",
                        "codeInput": "12345678",
                        "discounts": [],
                    },
                ],
            },
        )

    client = LidlReceiptClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    session = LidlAccountSession("access", "refresh")
    summary = LidlReceiptSummary("receipt-1", "2026-09-20T12:30:00", 5.48)

    _, envelope = client.get_receipt_envelope(session, summary)
    assert envelope.provider == "lidl"
    assert envelope.receipt["products"][0]["codeInput"] == "8712345678901"
    assert envelope.receipt["products"][0]["discountAmount"] == 0.5

    canonical = normalize_retailer_receipt(
        envelope,
        scan_id="scan-1",
        document_sha256="a" * 64,
    )
    assert canonical.receipt.transaction.purchase_date.isoformat() == "2026-09-20"
    assert str(canonical.receipt.totals.grand_total) == "5.48"
    assert canonical.receipt.lines[0].identifiers.gtin == "8712345678901"
    assert [line.description for line in canonical.receipt.lines] == ["VOLLE MELK", "BROOD"]


def test_runtime_lidl_state_is_household_scoped_and_exposes_no_tokens() -> None:
    delete_lidl_session("household-a")
    delete_lidl_session("household-b")
    delete_lidl_auth_attempt("household-a")
    delete_lidl_auth_attempt("household-b")

    session = LidlAccountSession("secret-access", "secret-refresh")
    attempt = build_lidl_login_attempt()
    set_lidl_session("household-a", session)
    set_lidl_auth_attempt("household-a", attempt)

    assert get_lidl_session("household-a") == session
    assert get_lidl_session("household-b") is None
    assert get_lidl_auth_attempt("household-a") == attempt
    assert get_lidl_auth_attempt("household-b") is None

    status = lidl_session_status("household-a")
    assert status["connected"] is True
    assert "secret-access" not in str(status)
    assert "secret-refresh" not in str(status)
    assert attempt.code_verifier not in str(status)

    delete_lidl_session("household-a")
    delete_lidl_auth_attempt("household-a")

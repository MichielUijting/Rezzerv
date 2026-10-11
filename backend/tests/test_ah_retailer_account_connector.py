from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx

from app.integrations.retailer_accounts.ah import (
    AHAccountSession,
    AHReceiptClient,
    AHReceiptSummary,
    build_ah_login_url,
    extract_ah_authorization_code,
)
from app.integrations.retailer_receipts.normalizer import normalize_retailer_receipt
from app.services.retailer_account_runtime_store import (
    ah_session_status,
    delete_ah_session,
    get_ah_session,
    set_ah_session,
)


def test_ah_login_url_uses_browser_oauth_contract() -> None:
    parsed = urlparse(build_ah_login_url())
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "login.ah.nl"
    assert parsed.path == "/login"
    assert query["client_id"] == ["appie-ios"]
    assert query["response_type"] == ["code"]
    assert query["redirect_uri"] == ["appie://login-exit"]


def test_extract_ah_authorization_code_accepts_raw_code_and_redirect() -> None:
    assert extract_ah_authorization_code("abc123") == "abc123"
    assert (
        extract_ah_authorization_code("appie://login-exit?code=abc%2B123")
        == "abc+123"
    )


def test_exchange_code_never_requires_password() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["json"] = request.content.decode()
        return httpx.Response(
            200,
            json={
                "access_token": "access-value",
                "refresh_token": "refresh-value",
                "expires_in": 7200,
            },
        )

    http = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.ah.nl",
    )
    client = AHReceiptClient(http_client=http, base_url="https://api.ah.nl")
    session = client.exchange_code("appie://login-exit?code=one-time-code")

    assert seen["path"] == "/mobile-auth/v1/auth/token"
    assert '"clientId":"appie-ios"' in str(seen["json"])
    assert '"code":"one-time-code"' in str(seen["json"])
    assert "password" not in str(seen["json"]).lower()
    assert session.access_token == "access-value"
    assert session.refresh_token == "refresh-value"


def test_expired_session_refreshes_before_graphql_receipt_list() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/mobile-auth/v1/auth/token/refresh":
            return httpx.Response(
                200,
                json={
                    "access_token": "new-access",
                    "refresh_token": "new-refresh",
                    "expires_in": 7200,
                },
            )
        assert request.headers["authorization"] == "Bearer new-access"
        return httpx.Response(
            200,
            json={
                "data": {
                    "posReceiptsPage": {
                        "posReceipts": [
                            {
                                "id": "receipt-1",
                                "dateTime": "2026-03-20T16:27:00",
                                "totalAmount": {"amount": 5.02},
                            }
                        ]
                    }
                }
            },
        )

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = AHReceiptClient(http_client=http)
    expired = AHAccountSession(
        access_token="old-access",
        refresh_token="old-refresh",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )

    active, receipts = client.list_receipts(expired)

    assert paths == ["/mobile-auth/v1/auth/token/refresh", "/graphql"]
    assert active.access_token == "new-access"
    assert receipts == [
        AHReceiptSummary(
            receipt_id="receipt-1",
            date_time="2026-03-20T16:27:00",
            total_amount=5.02,
        )
    ]


def test_ah_receipt_details_map_to_existing_retailer_envelope_and_canonical_contract() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/graphql"
        return httpx.Response(
            200,
            json={
                "data": {
                    "posReceiptDetails": {
                        "id": "receipt-1",
                        "memberId": "member-1",
                        "products": [
                            {
                                "id": 111,
                                "quantity": 1,
                                "name": "POEDERSUIKER",
                                "price": {"amount": 1.19},
                                "amount": {"amount": 1.19},
                            },
                            {
                                "id": 222,
                                "quantity": 1,
                                "name": "AH POFFERTJE",
                                "price": {"amount": 2.19},
                                "amount": {"amount": 2.19},
                            },
                        ],
                        "discounts": [
                            {"name": "BONUS BOX PREMIUM", "amount": {"amount": -0.15}}
                        ],
                        "payments": [
                            {"method": "PIN", "amount": {"amount": 5.02}}
                        ],
                    }
                }
            },
        )

    client = AHReceiptClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    session = AHAccountSession("access", "refresh")
    summary = AHReceiptSummary("receipt-1", "2026-03-20T16:27:00", 5.02)

    _, envelope = client.get_receipt_envelope(session, summary)

    assert envelope.provider == "ah"
    assert envelope.external_receipt_id == "receipt-1"
    assert envelope.receipt["discountTotal"] == 0.15
    assert envelope.receipt["products"][0]["retailerSku"] == 111

    canonical = normalize_retailer_receipt(
        envelope,
        scan_id="scan-1",
        document_sha256="a" * 64,
    )
    assert canonical.receipt.transaction.purchase_date.isoformat() == "2026-03-20"
    assert str(canonical.receipt.totals.grand_total) == "5.02"
    assert [line.description for line in canonical.receipt.lines] == [
        "POEDERSUIKER",
        "AH POFFERTJE",
    ]


def test_runtime_session_store_is_household_scoped_and_exposes_no_tokens() -> None:
    delete_ah_session("household-a")
    delete_ah_session("household-b")
    session = AHAccountSession("secret-access", "secret-refresh")
    set_ah_session("household-a", session)

    assert get_ah_session("household-a") == session
    assert get_ah_session("household-b") is None
    status = ah_session_status("household-a")
    assert status["connected"] is True
    assert "secret-access" not in str(status)
    assert "secret-refresh" not in str(status)

    delete_ah_session("household-a")


def test_ah_discount_reconciliation_keeps_nonphysical_discounts_out_of_stock_lines() -> None:
    from app.integrations.retailer_receipts import RetailerReceiptEnvelope

    source = RetailerReceiptEnvelope(
        provider="ah",
        external_receipt_id="synthetic-discount-receipt",
        receipt={
            "id": "synthetic-discount-receipt",
            "dateTime": "2026-10-01T12:00:00",
            "totalAmount": 3.23,
            "discountTotal": 0.15,
            "products": [
                {"name": "Artikel A", "quantity": 1, "unitPrice": 1.19, "lineTotal": 1.19},
                {"name": "Artikel B", "quantity": 1, "unitPrice": 2.19, "lineTotal": 2.19},
            ],
            "discounts": [{"name": "Bonus", "amount": {"amount": -0.15}}],
            "payments": [{"method": "PIN", "amount": {"amount": 3.23}}],
        },
    )
    result = normalize_retailer_receipt(
        source, scan_id="synthetic-1", document_sha256="a" * 64,
    )
    assert str(result.receipt.totals.discount_total) == '0.15'
    assert str(result.receipt.totals.grand_total) == '3.23'
    assert len(result.receipt.lines) == 2
    assert all(line.line_type == "product" for line in result.receipt.lines)
    assert result.quality.requires_review is False


def test_ah_unreconciled_total_is_flagged_for_review() -> None:
    from app.integrations.retailer_receipts import RetailerReceiptEnvelope

    source = RetailerReceiptEnvelope(
        provider="ah",
        external_receipt_id="synthetic-mismatch",
        receipt={
            "id": "synthetic-mismatch",
            "dateTime": "2026-10-01T12:00:00",
            "totalAmount": 5.02,
            "discountTotal": 0.15,
            "products": [
                {"name": "Artikel A", "quantity": 1, "lineTotal": 1.19},
                {"name": "Artikel B", "quantity": 1, "lineTotal": 2.19},
            ],
        },
    )
    result = normalize_retailer_receipt(
        source, scan_id="synthetic-2", document_sha256="b" * 64,
    )
    assert result.quality.requires_review is True
    assert any(
        warning["code"] == "AH_TOTAL_RECONCILIATION_REQUIRED"
        for warning in result.receipt.warnings
    )
    assert str(result.receipt.totals.grand_total) == '5.02'
    assert len(result.receipt.lines) == 2


def test_ah_empty_products_exposes_only_safe_structure_counts() -> None:
    """Empty AH receipt details must be diagnosable without exposing source data."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"posReceiptDetails": {
            "id": "private-receipt",
            "memberId": "private-member",
            "products": [],
            "items": [{"name": "PRIVATE ARTICLE", "amount": {"amount": 123}}],
            "discounts": [{"name": "PRIVATE DISCOUNT"}],
            "payments": [{"method": "PRIVATE PAYMENT"}],
            "access_token": "private-token",
        }}})

    client = AHReceiptClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    _, envelope = client.get_receipt_envelope(
        AHAccountSession("private-access", "private-refresh"),
        AHReceiptSummary("private-receipt", "2026-10-01T12:00:00", 1.0),
    )
    report = envelope.receipt["_ah_structure_diagnostic"]
    assert report == {
        "products_type": "list",
        "raw_products_count": 0,
        "mapped_products_count": 0,
        "alternate_fields": ["items"],
        "discounts_count": 1,
        "payments_count": 1,
    }
    assert "private" not in str(report).lower()

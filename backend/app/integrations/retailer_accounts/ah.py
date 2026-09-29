"""
Albert Heijn digital receipt account connector.

This module deliberately contains no persistent credential storage. Runtime
sessions are supplied by the caller and never written to Git, logs or fixtures.
The upstream AH API is undocumented and may change without notice.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from app.integrations.retailer_receipts import RetailerReceiptEnvelope

AH_API_BASE_URL = "https://api.ah.nl"
AH_LOGIN_BASE_URL = "https://login.ah.nl"
AH_CLIENT_ID = "appie-ios"
AH_REDIRECT_URI = "appie://login-exit"
AH_USER_AGENT = "Appie/9.28 (iPhone17,3; iPhone; CPU OS 26_1 like Mac OS X)"
AH_CLIENT_VERSION = "9.28"
AH_APPLICATION = "AHWEBSHOP"

_RECEIPTS_QUERY = """query FetchPosReceipts($offset: Int!, $limit: Int!) {
  posReceiptsPage(pagination: {offset: $offset, limit: $limit}) {
    posReceipts { id dateTime totalAmount { amount } }
  }
}"""

_RECEIPT_DETAILS_QUERY = """query FetchReceipt($id: String!) {
  posReceiptDetails(id: $id) {
    id
    memberId
    products {
      id
      quantity
      name
      price { amount }
      amount { amount }
    }
    discounts { name amount { amount } }
    payments { method amount { amount } }
  }
}"""


@dataclass(frozen=True)
class AHAccountSession:
    access_token: str
    refresh_token: str
    expires_at: datetime | None = None
    member_id: str | None = None

    def is_expired(self, *, skew_seconds: int = 60) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) >= self.expires_at - timedelta(seconds=skew_seconds)


@dataclass(frozen=True)
class AHReceiptSummary:
    receipt_id: str
    date_time: str | None
    total_amount: float | None


def build_ah_login_url() -> str:
    return f"{AH_LOGIN_BASE_URL}/login?" + urlencode(
        {
            "client_id": AH_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": AH_REDIRECT_URI,
        }
    )


def extract_ah_authorization_code(value: str) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        raise ValueError("AH autorisatiecode ontbreekt")
    if "://" not in candidate:
        return candidate
    parsed = urlparse(candidate)
    values = parse_qs(parsed.query).get("code") or []
    code = values[0].strip() if values else ""
    if not code:
        raise ValueError("AH redirect bevat geen autorisatiecode")
    return code


class AHReceiptClient:
    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        base_url: str = AH_API_BASE_URL,
    ) -> None:
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=20.0)
        self._base_url = base_url.rstrip("/")

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _headers(self, access_token: str | None = None) -> dict[str, str]:
        headers = {
            "User-Agent": AH_USER_AGENT,
            "x-client-name": AH_CLIENT_ID,
            "x-client-version": AH_CLIENT_VERSION,
            "x-application": AH_APPLICATION,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        return headers

    def _post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        response = self._client.post(
            f"{self._base_url}{path}",
            json=payload,
            headers=self._headers(access_token),
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("AH API gaf geen geldig object terug")
        return data

    @staticmethod
    def _session_from_token_payload(payload: dict[str, Any]) -> AHAccountSession:
        access_token = str(payload.get("access_token") or "").strip()
        refresh_token = str(payload.get("refresh_token") or "").strip()
        if not access_token or not refresh_token:
            raise ValueError("AH tokenantwoord bevat geen bruikbare tokens")
        expires_in = payload.get("expires_in")
        expires_at = None
        try:
            if expires_in is not None:
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        except (TypeError, ValueError):
            expires_at = None
        return AHAccountSession(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            member_id=str(payload.get("member_id") or payload.get("memberId") or "").strip() or None,
        )

    def exchange_code(self, code_or_redirect: str) -> AHAccountSession:
        code = extract_ah_authorization_code(code_or_redirect)
        payload = self._post_json(
            "/mobile-auth/v1/auth/token",
            {"clientId": AH_CLIENT_ID, "code": code},
        )
        return self._session_from_token_payload(payload)

    def refresh_session(self, session: AHAccountSession) -> AHAccountSession:
        payload = self._post_json(
            "/mobile-auth/v1/auth/token/refresh",
            {"clientId": AH_CLIENT_ID, "refreshToken": session.refresh_token},
        )
        refreshed = self._session_from_token_payload(payload)
        if refreshed.member_id is None and session.member_id is not None:
            refreshed = replace(refreshed, member_id=session.member_id)
        return refreshed

    def ensure_fresh_session(self, session: AHAccountSession) -> AHAccountSession:
        return self.refresh_session(session) if session.is_expired() else session

    def _graphql(
        self,
        session: AHAccountSession,
        query: str,
        variables: dict[str, Any],
    ) -> tuple[AHAccountSession, dict[str, Any]]:
        active = self.ensure_fresh_session(session)
        payload = self._post_json(
            "/graphql",
            {"query": query, "variables": variables},
            access_token=active.access_token,
        )
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0] if isinstance(errors[0], dict) else {}
            message = first.get("message") if isinstance(first, dict) else None
            raise ValueError(f"AH GraphQL-fout: {message or 'onbekende fout'}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError("AH GraphQL-antwoord bevat geen data")
        return active, data

    def list_receipts(
        self,
        session: AHAccountSession,
        *,
        limit: int = 100,
    ) -> tuple[AHAccountSession, list[AHReceiptSummary]]:
        active, data = self._graphql(
            session,
            _RECEIPTS_QUERY,
            {"offset": 0, "limit": max(1, min(int(limit), 100))},
        )
        page = data.get("posReceiptsPage") or {}
        rows = page.get("posReceipts") if isinstance(page, dict) else []
        result: list[AHReceiptSummary] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            receipt_id = str(row.get("id") or "").strip()
            if not receipt_id:
                continue
            total = row.get("totalAmount") or {}
            amount = total.get("amount") if isinstance(total, dict) else None
            result.append(
                AHReceiptSummary(
                    receipt_id=receipt_id,
                    date_time=str(row.get("dateTime") or "").strip() or None,
                    total_amount=float(amount) if amount is not None else None,
                )
            )
        return active, result

    def get_receipt_envelope(
        self,
        session: AHAccountSession,
        summary: AHReceiptSummary,
    ) -> tuple[AHAccountSession, RetailerReceiptEnvelope]:
        active, data = self._graphql(
            session,
            _RECEIPT_DETAILS_QUERY,
            {"id": summary.receipt_id},
        )
        details = data.get("posReceiptDetails")
        if not isinstance(details, dict) or not details.get("id"):
            raise ValueError(f"AH kassabon {summary.receipt_id} bevat geen details")

        products: list[dict[str, Any]] = []
        for row in details.get("products") or []:
            if not isinstance(row, dict):
                continue
            unit_price = row.get("price") or {}
            amount = row.get("amount") or {}
            products.append(
                {
                    "name": row.get("name"),
                    "quantity": row.get("quantity"),
                    "unitPrice": unit_price.get("amount") if isinstance(unit_price, dict) else None,
                    "lineTotal": amount.get("amount") if isinstance(amount, dict) else None,
                    "retailerSku": row.get("id"),
                }
            )

        discounts = details.get("discounts") or []
        discount_total = 0.0
        for discount in discounts:
            if not isinstance(discount, dict):
                continue
            amount = discount.get("amount") or {}
            value = amount.get("amount") if isinstance(amount, dict) else None
            if value is not None:
                discount_total += abs(float(value))

        receipt_payload: dict[str, Any] = {
            "id": str(details.get("id")),
            "dateTime": summary.date_time,
            "totalAmount": summary.total_amount,
            "products": products,
            "discountTotal": discount_total or None,
            "discounts": discounts,
            "payments": details.get("payments") or [],
        }
        return active, RetailerReceiptEnvelope(
            provider="ah",
            external_receipt_id=summary.receipt_id,
            receipt=receipt_payload,
        )

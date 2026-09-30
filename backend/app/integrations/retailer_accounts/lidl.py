"""Lidl Plus digital receipt account connector.

No Lidl username or password is accepted or stored by this module. Login happens
at Lidl using OAuth2 Authorization Code + PKCE. Runtime tokens are supplied by
the caller and never written to Git, logs or fixtures.

The Lidl Plus consumer API is undocumented and may change without notice.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from app.integrations.retailer_receipts import RetailerReceiptEnvelope

LIDL_AUTH_BASE_URL = "https://accounts.lidl.com"
LIDL_TICKETS_BASE_URL = "https://tickets.lidlplus.com"
LIDL_CLIENT_ID = "LidlPlusNativeClient"
LIDL_REDIRECT_URI = "com.lidlplus.app://callback"
LIDL_SCOPE = "openid profile offline_access lpprofile lpapis"
LIDL_COUNTRY = "NL"
LIDL_LANGUAGE = "nl"
LIDL_APP_VERSION = "16.43.4"


@dataclass(frozen=True)
class LidlAuthAttempt:
    code_verifier: str
    state: str
    nonce: str
    login_url: str
    created_at: datetime


@dataclass(frozen=True)
class LidlAccountSession:
    access_token: str
    refresh_token: str
    expires_at: datetime | None = None
    country: str = LIDL_COUNTRY
    language: str = LIDL_LANGUAGE

    def is_expired(self, *, skew_seconds: int = 60) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) >= self.expires_at - timedelta(seconds=skew_seconds)


@dataclass(frozen=True)
class LidlReceiptSummary:
    receipt_id: str
    date_time: str | None
    total_amount: float | None


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def build_lidl_login_attempt(
    *,
    country: str = LIDL_COUNTRY,
    language: str = LIDL_LANGUAGE,
) -> LidlAuthAttempt:
    country_code = str(country or LIDL_COUNTRY).strip().upper()
    language_code = str(language or LIDL_LANGUAGE).strip().lower()
    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    params = {
        "client_id": LIDL_CLIENT_ID,
        "redirect_uri": LIDL_REDIRECT_URI,
        "response_type": "code",
        "scope": LIDL_SCOPE,
        "code_challenge": _pkce_challenge(verifier),
        "code_challenge_method": "S256",
        "Country": country_code,
        "language": f"{language_code}-{country_code}",
        "nonce": nonce,
        "state": state,
    }
    return LidlAuthAttempt(
        code_verifier=verifier,
        state=state,
        nonce=nonce,
        login_url=f"{LIDL_AUTH_BASE_URL}/connect/authorize?{urlencode(params)}",
        created_at=datetime.now(timezone.utc),
    )


def extract_lidl_authorization_code(callback_url: str, *, expected_state: str) -> str:
    candidate = str(callback_url or "").strip()
    if not candidate:
        raise ValueError("Lidl callback ontbreekt")
    parsed = urlparse(candidate)
    if parsed.scheme != "com.lidlplus.app" or parsed.netloc != "callback":
        raise ValueError("Gebruik de volledige Lidl callback com.lidlplus.app://callback?code=...")
    values = parse_qs(parsed.query)
    code = str((values.get("code") or [""])[0]).strip()
    state = str((values.get("state") or [""])[0]).strip()
    if not code:
        raise ValueError("Lidl callback bevat geen autorisatiecode")
    if not state or not secrets.compare_digest(state, str(expected_state or "")):
        raise ValueError("Lidl callback hoort niet bij de actieve Inhuis-login")
    return code


class LidlReceiptClient:
    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        auth_base_url: str = LIDL_AUTH_BASE_URL,
        tickets_base_url: str = LIDL_TICKETS_BASE_URL,
        country: str = LIDL_COUNTRY,
        language: str = LIDL_LANGUAGE,
    ) -> None:
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=20.0)
        self._auth_base_url = auth_base_url.rstrip("/")
        self._tickets_base_url = tickets_base_url.rstrip("/")
        self._country = str(country or LIDL_COUNTRY).strip().upper()
        self._language = str(language or LIDL_LANGUAGE).strip().lower()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    @staticmethod
    def _session_from_token_payload(
        payload: dict[str, Any],
        *,
        country: str,
        language: str,
        prior_refresh_token: str | None = None,
    ) -> LidlAccountSession:
        access_token = str(payload.get("access_token") or "").strip()
        refresh_token = str(payload.get("refresh_token") or prior_refresh_token or "").strip()
        if not access_token or not refresh_token:
            raise ValueError("Lidl tokenantwoord bevat geen bruikbare tokens")
        expires_at = None
        try:
            if payload.get("expires_in") is not None:
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(payload["expires_in"]))
        except (TypeError, ValueError):
            expires_at = None
        return LidlAccountSession(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            country=country,
            language=language,
        )

    def _token_request(self, form: dict[str, str]) -> dict[str, Any]:
        # Lidl's native client is an OAuth public client. We deliberately do not
        # embed passwords, account credentials or private client secrets in Inhuis.
        response = self._client.post(
            f"{self._auth_base_url}/connect/token",
            data={**form, "client_id": LIDL_CLIENT_ID},
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Lidl tokenantwoord is ongeldig")
        return data

    def exchange_code(
        self,
        callback_url: str,
        attempt: LidlAuthAttempt,
    ) -> LidlAccountSession:
        code = extract_lidl_authorization_code(callback_url, expected_state=attempt.state)
        payload = self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": LIDL_REDIRECT_URI,
                "code_verifier": attempt.code_verifier,
            }
        )
        return self._session_from_token_payload(
            payload,
            country=self._country,
            language=self._language,
        )

    def refresh_session(self, session: LidlAccountSession) -> LidlAccountSession:
        payload = self._token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": session.refresh_token,
            }
        )
        return self._session_from_token_payload(
            payload,
            country=session.country,
            language=session.language,
            prior_refresh_token=session.refresh_token,
        )

    def ensure_fresh_session(self, session: LidlAccountSession) -> LidlAccountSession:
        return self.refresh_session(session) if session.is_expired() else session

    def _headers(self, session: LidlAccountSession) -> tuple[LidlAccountSession, dict[str, str]]:
        active = self.ensure_fresh_session(session)
        return active, {
            "Authorization": f"Bearer {active.access_token}",
            "App-Version": LIDL_APP_VERSION,
            "Operating-System": "Android",
            "App": "com.lidl.eci.lidlplus",
            "Accept-Language": active.language,
            "User-Agent": "Inhuis Lidl receipt connector",
            "Accept": "application/json",
        }

    @staticmethod
    def _amount(value: Any) -> float | None:
        if value in (None, ""):
            return None
        if isinstance(value, dict):
            for key in ("amount", "value", "total"):
                if value.get(key) not in (None, ""):
                    value = value[key]
                    break
        if isinstance(value, str):
            value = value.strip().replace("€", "").replace("EUR", "").strip().replace(",", ".")
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def list_receipts(
        self,
        session: LidlAccountSession,
        *,
        limit: int = 20,
    ) -> tuple[LidlAccountSession, list[LidlReceiptSummary]]:
        wanted = max(1, min(int(limit), 100))
        active = session
        result: list[LidlReceiptSummary] = []
        page_number = 1
        while len(result) < wanted:
            active, headers = self._headers(active)
            response = self._client.get(
                f"{self._tickets_base_url}/api/v2/{active.country}/tickets",
                params={"pageNumber": page_number, "onlyFavorite": "false"},
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Lidl bonnenlijst is ongeldig")
            rows = payload.get("tickets") or []
            if not isinstance(rows, list) or not rows:
                break
            for row in rows:
                if not isinstance(row, dict):
                    continue
                receipt_id = str(row.get("id") or row.get("ticketId") or "").strip()
                if not receipt_id:
                    continue
                result.append(
                    LidlReceiptSummary(
                        receipt_id=receipt_id,
                        date_time=str(
                            row.get("date")
                            or row.get("dateTime")
                            or row.get("purchaseDate")
                            or row.get("purchaseDateTime")
                            or ""
                        ).strip() or None,
                        total_amount=self._amount(
                            row.get("totalAmount")
                            or row.get("total")
                            or row.get("amount")
                        ),
                    )
                )
                if len(result) >= wanted:
                    break
            total_count = payload.get("totalCount")
            page_size = payload.get("size")
            try:
                if total_count is not None and page_size and page_number * int(page_size) >= int(total_count):
                    break
            except (TypeError, ValueError):
                pass
            page_number += 1
            if page_number > 10:
                break
        return active, result

    @staticmethod
    def _product_rows(details: dict[str, Any]) -> list[dict[str, Any]]:
        for key in ("itemsLine", "items", "products", "lines"):
            rows = details.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        ticket = details.get("ticket")
        if isinstance(ticket, dict):
            return LidlReceiptClient._product_rows(ticket)
        return []

    @staticmethod
    def _discount_total(row: dict[str, Any]) -> float | None:
        discounts = row.get("discounts")
        if not isinstance(discounts, list):
            return None
        total = 0.0
        found = False
        for discount in discounts:
            if not isinstance(discount, dict):
                continue
            amount = LidlReceiptClient._amount(discount.get("amount"))
            if amount is not None:
                total += abs(amount)
                found = True
        return total if found else None

    def get_receipt_envelope(
        self,
        session: LidlAccountSession,
        summary: LidlReceiptSummary,
    ) -> tuple[LidlAccountSession, RetailerReceiptEnvelope]:
        active, headers = self._headers(session)
        response = self._client.get(
            f"{self._tickets_base_url}/api/v3/{active.country}/tickets/{summary.receipt_id}",
            headers=headers,
        )
        response.raise_for_status()
        details = response.json()
        if not isinstance(details, dict):
            raise ValueError(f"Lidl kassabon {summary.receipt_id} bevat geen geldige details")

        rows = self._product_rows(details)
        if not rows:
            if details.get("htmlPrintedReceipt"):
                raise ValueError(
                    f"Lidl kassabon {summary.receipt_id} gebruikt alleen het historische HTML-formaat; "
                    "deze variant wordt nog niet automatisch geïmporteerd"
                )
            raise ValueError(f"Lidl kassabon {summary.receipt_id} bevat geen artikelregels")

        products: list[dict[str, Any]] = []
        for row in rows:
            name = row.get("name") or row.get("description") or row.get("productName")
            quantity = row.get("quantity") or row.get("count") or 1
            unit_price = row.get("currentUnitPrice") or row.get("unitPrice") or row.get("price")
            line_total = (
                row.get("finalAmount")
                or row.get("lineTotal")
                or row.get("amount")
                or row.get("originalAmount")
            )
            products.append(
                {
                    "name": name,
                    "quantity": quantity,
                    "unitPrice": unit_price,
                    "lineTotal": line_total,
                    "codeInput": row.get("codeInput") or row.get("ean") or row.get("barcode"),
                    "retailerSku": row.get("articleId") or row.get("articleNumber") or row.get("id"),
                    "discountAmount": self._discount_total(row),
                    "discounts": row.get("discounts") or [],
                    "deposit": row.get("deposit"),
                }
            )

        receipt_payload: dict[str, Any] = {
            "id": str(details.get("id") or details.get("ticketId") or summary.receipt_id),
            "dateTime": (
                details.get("date")
                or details.get("dateTime")
                or details.get("purchaseDate")
                or details.get("purchaseDateTime")
                or summary.date_time
            ),
            "totalAmount": (
                details.get("totalAmount")
                or details.get("total")
                or details.get("amount")
                or summary.total_amount
            ),
            "discountTotal": details.get("totalDiscount") or details.get("discountTotal"),
            "store": details.get("store") or {},
            "products": products,
        }
        return active, RetailerReceiptEnvelope(
            provider="lidl",
            external_receipt_id=summary.receipt_id,
            receipt=receipt_payload,
        )

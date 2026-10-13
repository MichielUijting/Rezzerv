"""Picnic account authentication protocol; unofficial, household-safe by caller.

The API protocol follows MRVDH/picnic-api, not a Picnic-supported public API.
No password persistence, URL tokens, request logging or automatic live calls.
Only the obtained auth key is returned; persistence is a separate encrypted step.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Callable, Any, Mapping


class PicnicAuthError(ValueError):
    """Generic public exception: never reveal Picnic response or credentials."""


_AUTH_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.=-]{8,4096}$")
_PHONE_CODE_PATTERN = re.compile(r"^[0-9]{4,10}$")


def _auth_key(value: Any) -> str:
    if not isinstance(value, str) or not _AUTH_KEY_PATTERN.fullmatch(value):
        raise PicnicAuthError("Picnic gaf geen bruikbare sessiesleutel terug.")
    return value


def _verification_code(value: str) -> str:
    if not isinstance(value, str) or not _PHONE_CODE_PATTERN.fullmatch(value):
        raise PicnicAuthError("Voer een geldige numerieke Picnic-sms-code in.")
    return value


@dataclass(frozen=True)
class PicnicLoginResult:
    auth_key: str
    requires_2fa: bool


@dataclass(frozen=True)
class PicnicAuthClient:
    """Injected HTTP boundary, with restricted protocol methods.

    transport(method, path, payload, auth_key) -> (response_body, response_headers).
    The caller is responsible for restrictive endpoint settings and timeouts.
    """

    transport: Callable[[str, str, Any, str | None], tuple[Mapping[str, Any] | None, Mapping[str, str]]]

    def login(self, username: str, password: str) -> PicnicLoginResult:
        if not isinstance(username, str) or not username.strip() or len(username) > 254:
            raise PicnicAuthError("Picnic-gebruikersnaam ontbreekt.")
        if not isinstance(password, str) or not password or len(password) > 1024:
            raise PicnicAuthError("Picnic-wachtwoord ontbreekt.")
        digest = hashlib.md5(password.encode("utf-8")).hexdigest()  # Picnic legacy protocol, not password storage.
        try:
            payload, headers = self.transport("POST", "/user/login", {
                "key": username.strip(),
                "secret": digest,
                "client_id": 30100,
            }, None)
            token = _auth_key(_header(headers, "x-picnic-auth"))
            if not isinstance(payload, Mapping):
                raise PicnicAuthError("Picnic gaf geen geldige aanmeldstatus terug.")
            requires_2fa = payload.get("second_factor_authentication_required")
            if not isinstance(requires_2fa, bool):
                raise PicnicAuthError("Picnic gaf geen herkenbare verificatiestatus terug.")
            return PicnicLoginResult(auth_key=token, requires_2fa=requires_2fa)
        except PicnicAuthError:
            raise
        except Exception as exc:
            raise PicnicAuthError("Picnic-aanmelding kon niet worden voltooid.") from None

    def request_sms(self, auth_key: str) -> None:
        token = _auth_key(auth_key)
        try:
            self.transport("POST", "/user/2fa/generate", {"channel": "SMS"}, token)
        except Exception:
            raise PicnicAuthError("Picnic-sms-code kon niet worden aangevraagd.") from None

    def verify_sms(self, auth_key: str, code: str) -> str:
        token = _auth_key(auth_key)
        otp = _verification_code(code)
        try:
            _payload, headers = self.transport("POST", "/user/2fa/verify", {"otp": otp}, token)
            return _auth_key(_header(headers, "x-picnic-auth"))
        except PicnicAuthError:
            raise
        except Exception:
            raise PicnicAuthError("Picnic-sms-verificatie is mislukt.") from None


def _header(headers: Mapping[str, str], name: str) -> str | None:
    if not isinstance(headers, Mapping):
        return None
    return next((str(v) for k, v in headers.items() if str(k).lower() == name), None)

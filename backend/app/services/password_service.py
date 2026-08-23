from __future__ import annotations

import hashlib
import hmac
import secrets

PBKDF2_ALGORITHM = "sha256"
PBKDF2_ITERATIONS = 600_000
PBKDF2_SCHEME = "pbkdf2_sha256"
PBKDF2_SALT_BYTES = 16


def hash_password(password: str) -> str:
    supplied = str(password or "")
    if not supplied:
        raise ValueError("Wachtwoord is verplicht")
    salt = secrets.token_bytes(PBKDF2_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        supplied.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return f"{PBKDF2_SCHEME}${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def is_password_hash(value: str | None) -> bool:
    return str(value or "").startswith(f"{PBKDF2_SCHEME}$")


def verify_password_hash(encoded: str | None, supplied_password: str) -> bool:
    value = str(encoded or "")
    if not is_password_hash(value):
        return False
    try:
        scheme, iterations_raw, salt_hex, digest_hex = value.split("$", 3)
        if scheme != PBKDF2_SCHEME:
            return False
        iterations = int(iterations_raw)
        if iterations <= 0:
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (TypeError, ValueError):
        return False
    actual = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        str(supplied_password or "").encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(expected, actual)


def verify_password(
    stored_password: str | None,
    supplied_password: str,
    *,
    stored_password_hash: str | None = None,
) -> bool:
    """Verify v2 hashes while retaining login compatibility for legacy accounts."""

    if is_password_hash(stored_password_hash):
        return verify_password_hash(stored_password_hash, supplied_password)
    if is_password_hash(stored_password):
        return verify_password_hash(stored_password, supplied_password)
    legacy = str(stored_password or "")
    supplied = str(supplied_password or "")
    return bool(legacy) and hmac.compare_digest(legacy, supplied)

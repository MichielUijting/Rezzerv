from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os

import sqlalchemy as sa
from sqlalchemy import text

from app.services.password_reset_delivery_service import (
    PasswordResetEmailConfiguration,
    build_password_changed_email_payload,
    build_password_reset_email_payload,
    send_password_reset_email,
)
from app.services.password_reset_service import (
    PASSWORD_RESET_MAX_PER_USER,
    PasswordResetInvalidTokenError,
    PasswordResetPasswordReuseError,
    confirm_password_reset,
    hash_password_reset_token,
    request_password_reset,
)
from app.services.password_service import hash_password, verify_password


os.environ.setdefault("REZZERV_ENV", "test")


def _engine():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    sa.Table(
        "app_users",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    sa.Table(
        "server_sessions",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table(
        "account_password_reset_tokens",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("request_ip_hash", sa.String(64), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(engine)
    return engine


def _seed_account(connection, *, password: str = "OudWachtwoord123!") -> str:
    encoded = hash_password(password)
    connection.execute(
        text(
            """
            INSERT INTO app_users (id, email, password, password_hash, updated_at)
            VALUES (:id, :email, :password, :password_hash, :updated_at)
            """
        ),
        {
            "id": "user-1",
            "email": "reset@example.test",
            "password": encoded,
            "password_hash": encoded,
            "updated_at": datetime.now(timezone.utc),
        },
    )
    return encoded


def _email_configuration() -> PasswordResetEmailConfiguration:
    return PasswordResetEmailConfiguration(
        enabled=True,
        api_key="re_test_key",
        api_base_url="https://api.resend.com",
        from_email="security@example.test",
        from_name="Inhuis",
        app_base_url="https://app.example.test",
    )


def main() -> None:
    engine = _engine()
    base_now = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
    try:
        with engine.begin() as connection:
            original_hash = _seed_account(connection)

            unknown = request_password_reset(
                connection,
                email="unknown@example.test",
                client_ip="203.0.113.10",
                now=base_now,
            )
            assert not unknown.account_found
            assert unknown.raw_token is None

            first = request_password_reset(
                connection,
                email="RESET@example.test",
                client_ip="203.0.113.10",
                now=base_now,
            )
            assert first.account_found and not first.rate_limited
            assert first.raw_token and first.token_hash
            assert first.token_hash == hash_password_reset_token(first.raw_token)
            assert first.expires_at == base_now + timedelta(minutes=30)
            stored = connection.execute(
                text(
                    "SELECT token_hash, request_ip_hash FROM account_password_reset_tokens WHERE user_id = 'user-1'"
                )
            ).mappings().one()
            assert stored["token_hash"] == first.token_hash
            assert first.raw_token not in str(stored)
            assert str(stored["request_ip_hash"]) != "203.0.113.10"

            second = request_password_reset(
                connection,
                email="reset@example.test",
                client_ip="203.0.113.10",
                now=base_now + timedelta(minutes=1),
            )
            assert second.raw_token and second.raw_token != first.raw_token
            first_row = connection.execute(
                text(
                    "SELECT revoked_at FROM account_password_reset_tokens WHERE token_hash = :token_hash"
                ),
                {"token_hash": first.token_hash},
            ).mappings().one()
            assert first_row["revoked_at"] is not None

            try:
                confirm_password_reset(
                    connection,
                    raw_token=first.raw_token,
                    new_password="NieuwWachtwoord456!",
                    now=base_now + timedelta(minutes=2),
                )
            except PasswordResetInvalidTokenError:
                pass
            else:
                raise AssertionError("Een vervangen reset-token bleef bruikbaar")

            try:
                confirm_password_reset(
                    connection,
                    raw_token=second.raw_token,
                    new_password="OudWachtwoord123!",
                    now=base_now + timedelta(minutes=2),
                )
            except PasswordResetPasswordReuseError:
                pass
            else:
                raise AssertionError("Huidig wachtwoord kon als reset-wachtwoord worden hergebruikt")

            connection.execute(
                text(
                    """
                    INSERT INTO server_sessions (id, user_id, expires_at, revoked_at, updated_at)
                    VALUES ('session-a', 'user-1', :expires, NULL, :now),
                           ('session-b', 'user-1', :expires, NULL, :now)
                    """
                ),
                {"expires": base_now + timedelta(hours=2), "now": base_now},
            )
            confirmed = confirm_password_reset(
                connection,
                raw_token=second.raw_token,
                new_password="NieuwWachtwoord456!",
                now=base_now + timedelta(minutes=2),
            )
            assert confirmed.revoked_sessions == 2
            assert connection.execute(
                text("SELECT COUNT(*) FROM server_sessions WHERE revoked_at IS NULL")
            ).scalar_one() == 0
            updated = connection.execute(
                text("SELECT password, password_hash FROM app_users WHERE id = 'user-1'")
            ).mappings().one()
            assert updated["password"] != original_hash
            assert updated["password"] == updated["password_hash"]
            assert verify_password(updated["password"], "NieuwWachtwoord456!")

            try:
                confirm_password_reset(
                    connection,
                    raw_token=second.raw_token,
                    new_password="NogEenWachtwoord789!",
                    now=base_now + timedelta(minutes=3),
                )
            except PasswordResetInvalidTokenError:
                pass
            else:
                raise AssertionError("Een gebruikt reset-token kon opnieuw worden gebruikt")

        # Rate limit is proved on a fresh account lifecycle so invalidated tokens
        # still count as requests in the 15-minute abuse window.
        rate_engine = _engine()
        try:
            with rate_engine.begin() as connection:
                _seed_account(connection)
                for attempt in range(PASSWORD_RESET_MAX_PER_USER):
                    result = request_password_reset(
                        connection,
                        email="reset@example.test",
                        client_ip=f"203.0.113.{20 + attempt}",
                        now=base_now + timedelta(seconds=attempt),
                    )
                    assert result.raw_token
                limited = request_password_reset(
                    connection,
                    email="reset@example.test",
                    client_ip="203.0.113.99",
                    now=base_now + timedelta(minutes=1),
                )
                assert limited.account_found and limited.rate_limited
                assert limited.raw_token is None
        finally:
            rate_engine.dispose()

        expired_engine = _engine()
        try:
            with expired_engine.begin() as connection:
                _seed_account(connection)
                expired = request_password_reset(
                    connection,
                    email="reset@example.test",
                    client_ip="203.0.113.40",
                    now=base_now,
                )
                try:
                    confirm_password_reset(
                        connection,
                        raw_token=str(expired.raw_token),
                        new_password="NieuwWachtwoord456!",
                        now=base_now + timedelta(minutes=31),
                    )
                except PasswordResetInvalidTokenError:
                    pass
                else:
                    raise AssertionError("Verlopen reset-token bleef bruikbaar")
        finally:
            expired_engine.dispose()

        config = _email_configuration()
        reset_payload = build_password_reset_email_payload(
            recipient_email="reset@example.test",
            raw_token="top-secret-reset-token",
            configuration=config,
        )
        reset_text = str(reset_payload["text"])
        assert "/wachtwoord-herstellen#token=" in reset_text
        assert "?token=" not in reset_text
        changed_payload = build_password_changed_email_payload(
            recipient_email="reset@example.test",
            configuration=config,
        )
        assert "token" not in str(changed_payload).lower()

        failed = send_password_reset_email(
            recipient_email="reset@example.test",
            raw_token="top-secret-reset-token",
            configuration=config,
            transport=lambda payload, configuration: (_ for _ in ()).throw(
                RuntimeError("transport leaked top-secret-reset-token")
            ),
        )
        assert not failed.sent
        assert "top-secret-reset-token" not in failed.message
        assert "[redacted]" in failed.message

        print("PASSWORD_RESET_SECURITY_SELFTEST_GREEN")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

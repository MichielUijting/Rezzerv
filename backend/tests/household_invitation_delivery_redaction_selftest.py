"""Validate that provider errors can never persist or expose invitation bearer tokens."""

from __future__ import annotations

from app.services.household_invitation_delivery_service import (
    InvitationDeliveryTransportError,
    InvitationEmailConfiguration,
    send_household_invitation_email,
)


def run() -> int:
    raw_token = "BearerTokenThatMustNeverEscape_1234567890"
    configuration = InvitationEmailConfiguration(
        enabled=True,
        api_key="re_test_key",
        api_base_url="https://api.resend.example",
        from_email="uitnodigingen@inhu.is",
        from_name="Inhuis",
        app_base_url="https://app.inhu.is",
    )

    def hostile_provider(payload, _configuration):
        raise InvitationDeliveryTransportError(
            f"provider echoed the complete request: {payload}"
        )

    result = send_household_invitation_email(
        recipient_email="invitee@example.com",
        household_name="Huis A",
        raw_token=raw_token,
        expires_at="2026-09-01T00:00:00+00:00",
        configuration=configuration,
        transport=hostile_provider,
    )
    assert result.status == "failed"
    assert raw_token not in result.message
    assert "/uitnodiging/BearerToken" not in result.message
    assert "[redacted]" in result.message
    print("PASS hostile_provider_error_cannot_echo_bearer_token")
    print("HOUSEHOLD_INVITATION_DELIVERY_REDACTION_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())

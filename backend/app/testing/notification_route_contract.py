from __future__ import annotations

from app.testing.notification_route_audit import audit_routes


def main() -> None:
    payload = audit_routes()
    summary = payload["summary"]
    assert summary == {
        "route_registrations": 0,
        "reads": 0,
        "mutations": 0,
        "mutation_without_auth_marker": 0,
    }, summary
    assert payload["routes"] == [], payload["routes"]
    assert payload["mutation_without_auth_marker"] == [], payload["mutation_without_auth_marker"]
    print("M2C2N_NOTIFICATION_ROUTE_CONTRACT_GREEN")


if __name__ == "__main__":
    main()

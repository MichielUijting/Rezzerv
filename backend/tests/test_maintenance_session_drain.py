"""Authorization-independent domain checks for deliberate maintenance sign-out."""
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from app.services.maintenance_session_drain import revoke_remaining_sessions
from app.services.maintenance_state_contract import MaintenanceTransitionError

NOW = datetime(2026, 10, 26, 16, 0, tzinfo=timezone.utc)


class RowResult:
    def __init__(self, *, mapping=None, scalar=None, count=0):
        self.mapping = mapping
        self.scalar = scalar
        self.rowcount = count

    def mappings(self):
        return self

    def one(self):
        return self.mapping

    def scalar_one_or_none(self):
        return self.scalar


def connection(state="announced", generation=2, notice_age=timedelta(minutes=3)):
    conn = Mock()
    conn.execute.side_effect = [
        RowResult(mapping={"state": state, "generation": generation}),
        RowResult(scalar=NOW - notice_age),
        RowResult(count=3),
        RowResult(),
    ]
    return conn


def execute(conn, **kwargs):
    return revoke_remaining_sessions(
        conn, expected_generation=kwargs.get("generation", 2),
        current_session_id="admin-session", actor_user_id="admin-user", now=NOW,
    )


@pytest.mark.parametrize("state", ["normal", "locked", "verifying", "blocked"])
def test_no_revoke_outside_announced_or_draining(state):
    conn = connection(state=state)
    with pytest.raises(MaintenanceTransitionError):
        execute(conn)
    assert conn.execute.call_count == 1


def test_stale_generation_cannot_sign_out():
    conn = connection(generation=3)
    with pytest.raises(MaintenanceTransitionError):
        execute(conn)
    assert conn.execute.call_count == 1


def test_warning_grace_period_is_enforced_without_writes():
    conn = connection(notice_age=timedelta(seconds=119))
    with pytest.raises(MaintenanceTransitionError):
        execute(conn)
    assert conn.execute.call_count == 2


@pytest.mark.parametrize("state", ["announced", "draining"])
def test_only_other_sessions_are_revoked_and_audit_is_recorded(state):
    conn = connection(state=state)
    result = execute(conn)
    assert result == {"sessions_revoked": 3, "current_session_preserved": True,
                      "operations_untouched": True}
    assert conn.execute.call_count == 4
    update = conn.execute.call_args_list[2]
    assert "UPDATE server_sessions" in str(update.args[0])
    assert "id<>:current_session_id" in str(update.args[0])
    assert update.args[1]["current_session_id"] == "admin-session"
    audit = conn.execute.call_args_list[3]
    assert "maintenance_audit" in str(audit.args[0])
    assert '"revoked_count": 3' in audit.args[1]["evidence"]

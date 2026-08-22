from __future__ import annotations

HYBRID_REGRESSION_BACKGROUND_JOB_PERMISSION = "platform.background_jobs.manage"
HYBRID_REGRESSION_FIXTURE_PERMISSION = "platform.test_fixtures.manage"
HYBRID_REGRESSION_REQUIRED_PERMISSIONS = (
    HYBRID_REGRESSION_BACKGROUND_JOB_PERMISSION,
    HYBRID_REGRESSION_FIXTURE_PERMISSION,
)
HYBRID_REGRESSION_ROUTES = frozenset(
    {
        ("POST", "/api/testing/regression/almost-out-prediction"),
        ("POST", "/api/testing/regression/almost-out-self-test"),
    }
)


def required_hybrid_regression_permissions(method: str, path: str) -> tuple[str, ...]:
    request_key = (str(method or "").upper(), str(path or ""))
    if request_key not in HYBRID_REGRESSION_ROUTES:
        return ()
    return HYBRID_REGRESSION_REQUIRED_PERMISSIONS

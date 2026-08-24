from __future__ import annotations

import logging

import pytest

from app.api.platform_logs_routes import PLATFORM_LOGS_VIEW_PERMISSION
from app.services.authorization_foundation_service import ROLE_PERMISSIONS
from app.services.platform_log_service import (
    PLATFORM_LOG_MAX_LIMIT,
    PLATFORM_LOG_MESSAGE_MAX_CHARS,
    clear_platform_log_buffer_for_tests,
    install_platform_log_capture,
    list_platform_logs,
    normalize_platform_log_level,
    sanitize_platform_log_message,
)


def test_platform_logs_permission_uses_existing_role_matrix_without_expanding_v1_1_superuser():
    assert PLATFORM_LOGS_VIEW_PERMISSION == "platform.logs.view"
    assert PLATFORM_LOGS_VIEW_PERMISSION in ROLE_PERMISSIONS["platform.platform_admin"]
    assert PLATFORM_LOGS_VIEW_PERMISSION in ROLE_PERMISSIONS["platform.ip_owner"]
    assert PLATFORM_LOGS_VIEW_PERMISSION not in ROLE_PERMISSIONS["platform.superuser"]
    assert PLATFORM_LOGS_VIEW_PERMISSION not in ROLE_PERMISSIONS["platform.support_read"]
    assert PLATFORM_LOGS_VIEW_PERMISSION not in ROLE_PERMISSIONS["platform.frontteam"]
    assert PLATFORM_LOGS_VIEW_PERMISSION not in ROLE_PERMISSIONS["household.admin"]


def test_platform_runtime_log_capture_is_idempotent_preserves_threshold_and_projects_safe_fields_only():
    clear_platform_log_buffer_for_tests()
    rezzerv_logger = logging.getLogger("rezzerv")
    original_parent_level = rezzerv_logger.level
    first = install_platform_log_capture()
    second = install_platform_log_capture()
    assert first is second
    assert rezzerv_logger.level == original_parent_level

    logger = logging.getLogger("rezzerv.api.e12-test")
    original_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        logger.warning(
            "request failed password=hunter2 token=abc123 "
            "url=postgresql://dbuser:dbpass@db.internal/rezzerv "
            "Cookie: sessionid=cookie-secret; second=also-secret"
        )
        try:
            raise RuntimeError("raw exception detail must not become traceback payload")
        except RuntimeError:
            logger.exception("operation failed authorization=Bearer super-secret")
    finally:
        logger.setLevel(original_level)

    items = list_platform_logs(limit=10)
    assert len(items) == 2
    newest, oldest = items

    assert newest["level"] == "ERROR"
    assert newest["logger"] == "rezzerv.api.e12-test"
    assert newest["exception_type"] == "RuntimeError"
    assert "super-secret" not in newest["message"]
    assert "[REDACTED]" in newest["message"]
    assert "raw exception detail" not in repr(newest)
    assert "traceback" not in repr(newest).lower()

    assert oldest["level"] == "WARNING"
    rendered = repr(oldest)
    for secret in ("hunter2", "abc123", "dbuser", "dbpass", "cookie-secret", "also-secret"):
        assert secret not in rendered
    assert set(oldest) == {"id", "created_at", "level", "logger", "message", "exception_type"}


def test_platform_log_filters_are_bounded_newest_first_and_case_normalized():
    clear_platform_log_buffer_for_tests()
    install_platform_log_capture()
    logger = logging.getLogger("rezzerv.api.e12-filter")
    original_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        logger.info("first info")
        logger.error("middle error")
        logger.info("last info")
    finally:
        logger.setLevel(original_level)

    all_items = list_platform_logs(limit=9999)
    assert len(all_items) == 3
    assert [item["message"] for item in all_items] == ["last info", "middle error", "first info"]
    assert len(all_items) <= PLATFORM_LOG_MAX_LIMIT

    info_items = list_platform_logs(limit=10, level="info")
    assert [item["message"] for item in info_items] == ["last info", "first info"]
    assert all(item["level"] == "INFO" for item in info_items)
    assert normalize_platform_log_level(" warning ") == "WARNING"
    assert normalize_platform_log_level("") is None
    with pytest.raises(ValueError, match="Onbekend logniveau"):
        normalize_platform_log_level("TRACE")


def test_platform_log_sanitizer_masks_common_secret_shapes_and_truncates():
    message = sanitize_platform_log_message(
        "Bearer bearer-secret "
        "?access_token=query-secret&x=1 "
        "api_key=key-secret secret=secret-value session_id=session-secret "
        "Set-Cookie: a=cookie-a; b=cookie-b"
    )
    for secret in (
        "bearer-secret",
        "query-secret",
        "key-secret",
        "secret-value",
        "session-secret",
        "cookie-a",
        "cookie-b",
    ):
        assert secret not in message
    assert "[REDACTED]" in message

    long_message = sanitize_platform_log_message("x" * (PLATFORM_LOG_MESSAGE_MAX_CHARS + 50))
    assert len(long_message) == PLATFORM_LOG_MESSAGE_MAX_CHARS
    assert long_message.endswith("…")

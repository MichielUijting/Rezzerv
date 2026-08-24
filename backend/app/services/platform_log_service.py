from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import itertools
import logging
import re
import threading
from typing import Any


PLATFORM_LOG_MAX_ENTRIES = 500
PLATFORM_LOG_DEFAULT_LIMIT = 50
PLATFORM_LOG_MAX_LIMIT = 200
PLATFORM_LOG_MESSAGE_MAX_CHARS = 2000
PLATFORM_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
PLATFORM_LOGGER_PREFIX = "rezzerv"


_COOKIE_HEADER_RE = re.compile(r"(?i)\b(cookie|set-cookie)(\s*[:=]\s*)[^\r\n]+")
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_URL_CREDENTIAL_RE = re.compile(r"(?i)([a-z][a-z0-9+.-]*://)([^\s/@:]+):([^\s/@]+)@")
_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&](?:access_token|refresh_token|token|api[_-]?key|password|secret|session(?:_id)?)=)[^&#\s]+"
)
_KEY_VALUE_SECRET_RE = re.compile(
    r"(?i)\b(authorization|password|passwd|pwd|access_token|refresh_token|token|api[_-]?key|apikey|secret|session(?:_id)?)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)


_lock = threading.RLock()
_entries: deque[dict[str, Any]] = deque(maxlen=PLATFORM_LOG_MAX_ENTRIES)
_sequence = itertools.count(1)
_capture_handler: logging.Handler | None = None


def sanitize_platform_log_message(value: Any) -> str:
    """Return a bounded projection suitable for the in-app Platformlogs view.

    This is deliberately a display sanitiser, not a general secret-management
    primitive. Platformlogs never stores tracebacks, request bodies or headers;
    common credential shapes are additionally masked before the message enters
    the runtime ring buffer.
    """

    message = str(value or "").replace("\x00", "").strip()
    message = _COOKIE_HEADER_RE.sub(r"\1\2[REDACTED]", message)
    message = _BEARER_RE.sub("Bearer [REDACTED]", message)
    message = _URL_CREDENTIAL_RE.sub(r"\1[REDACTED]:[REDACTED]@", message)
    message = _QUERY_SECRET_RE.sub(r"\1[REDACTED]", message)
    message = _KEY_VALUE_SECRET_RE.sub(r"\1\2[REDACTED]", message)
    if len(message) > PLATFORM_LOG_MESSAGE_MAX_CHARS:
        message = message[: PLATFORM_LOG_MESSAGE_MAX_CHARS - 1] + "…"
    return message


def _exception_type(record: logging.LogRecord) -> str | None:
    if not record.exc_info or not record.exc_info[0]:
        return None
    return str(getattr(record.exc_info[0], "__name__", "Exception") or "Exception")


def _append_record(record: logging.LogRecord) -> None:
    if not str(record.name or "").startswith(PLATFORM_LOGGER_PREFIX):
        return
    item = {
        "id": next(_sequence),
        "created_at": datetime.fromtimestamp(record.created, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "level": str(record.levelname or "INFO").upper(),
        "logger": str(record.name or PLATFORM_LOGGER_PREFIX),
        "message": sanitize_platform_log_message(record.getMessage()),
        "exception_type": _exception_type(record),
    }
    with _lock:
        _entries.append(item)


class PlatformRuntimeLogHandler(logging.Handler):
    _rezzerv_platform_log_handler = True

    def emit(self, record: logging.LogRecord) -> None:
        try:
            _append_record(record)
        except Exception:
            # Logging must never be able to break the application request path.
            return


def install_platform_log_capture() -> logging.Handler:
    """Attach one observer without changing any existing production log threshold."""

    global _capture_handler
    logger = logging.getLogger(PLATFORM_LOGGER_PREFIX)
    with _lock:
        for handler in logger.handlers:
            if getattr(handler, "_rezzerv_platform_log_handler", False):
                _capture_handler = handler
                return handler
        # NOTSET means the handler observes every record that the existing logger
        # hierarchy already emits. It does not enable DEBUG/INFO records itself.
        handler = PlatformRuntimeLogHandler(level=logging.NOTSET)
        logger.addHandler(handler)
        _capture_handler = handler
        return handler


def normalize_platform_log_level(level: str | None) -> str | None:
    normalized = str(level or "").strip().upper()
    if not normalized:
        return None
    if normalized not in PLATFORM_LOG_LEVELS:
        raise ValueError("Onbekend logniveau")
    return normalized


def list_platform_logs(*, limit: int = PLATFORM_LOG_DEFAULT_LIMIT, level: str | None = None) -> list[dict[str, Any]]:
    normalized_limit = max(1, min(int(limit), PLATFORM_LOG_MAX_LIMIT))
    normalized_level = normalize_platform_log_level(level)
    with _lock:
        snapshot = list(_entries)
    if normalized_level:
        snapshot = [item for item in snapshot if item["level"] == normalized_level]
    snapshot.reverse()
    return [dict(item) for item in snapshot[:normalized_limit]]


def clear_platform_log_buffer_for_tests() -> None:
    with _lock:
        _entries.clear()


# Installation is idempotent and deliberately happens while the API router is
# imported, before FastAPI startup callbacks begin emitting operational records.
install_platform_log_capture()

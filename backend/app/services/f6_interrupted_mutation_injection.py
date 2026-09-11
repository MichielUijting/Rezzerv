"""Test-only one-shot interruption hook for F6-04 recovery authorities.

Production behaviour is unchanged unless both environment variables below are
explicitly configured in the backend container. Each configured target fails
exactly once per container through an atomic marker in /tmp; the next identical
user action is allowed to continue.
"""
from __future__ import annotations

import hashlib
import os

F6_04_INTERRUPTION_ENV = "REZZERV_TEST_ONLY_F6_INTERRUPTED_MUTATION_ONCE"
F6_04_TARGETS_ENV = "REZZERV_TEST_ONLY_F6_INTERRUPTED_MUTATION_TARGETS"
F6_04_MARKER = "F6-04-INTERRUPTED-MUTATION"


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _configured_targets() -> set[str]:
    return {
        item.strip().lower()
        for item in str(os.getenv(F6_04_TARGETS_ENV, "") or "").split(",")
        if item.strip()
    }


def f6_04_interruption_enabled(target: str) -> bool:
    normalized = str(target or "").strip().lower()
    return bool(normalized) and _truthy(os.getenv(F6_04_INTERRUPTION_ENV)) and normalized in _configured_targets()


def _marker_path(target: str) -> str:
    digest = hashlib.sha256(str(target).encode("utf-8")).hexdigest()
    return f"/tmp/rezzerv-f6-04-{digest}.marker"


def inject_f6_04_interruption_once(target: str) -> bool:
    """Raise exactly once for a configured F6-04 target; return False otherwise."""

    normalized = str(target or "").strip().lower()
    if not f6_04_interruption_enabled(normalized):
        return False

    marker_path = _marker_path(normalized)
    try:
        fd = os.open(marker_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False

    with os.fdopen(fd, "w", encoding="utf-8") as marker:
        marker.write(normalized + "\n")

    print(f"{F6_04_MARKER}: target={normalized}", flush=True)
    raise RuntimeError(f"F6-04 interrupted mutation: {normalized}")

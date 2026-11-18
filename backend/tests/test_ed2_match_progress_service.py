"""Pure job/progress tests: no live database or Docker operations."""
from contextlib import contextmanager
from types import SimpleNamespace
import pytest

from app.services import ed2_match_progress_service as job_service


def test_progress_publishes_real_counts_and_finishes(monkeypatch):
    monkeypatch.setattr(job_service, "_JOB", None)
    class InlineThread:
        def __init__(self, *, target, args, **kwargs):
            self.target, self.args = target, args
        def start(self):
            self.target(*self.args)
    monkeypatch.setattr(job_service, "Thread", InlineThread)
    @contextmanager
    def begin():
        yield object()
    calls = []
    def batch(conn, actor_id, progress):
        calls.append(actor_id)
        progress("controleren", 0, 3)
        progress("controleren", 1, 3)
        assert job_service.current_matching_progress()["checked"] == 1
        progress("controleren", 3, 3)
        return ({"ok": True, "linked": 0, "barcode_written": False},
                {"ok": True, "linked": 0, "barcode_written": False,
                 "matching_overview": {"items": [], "total": 0}})
    state = job_service.start_matching_progress(SimpleNamespace(begin=begin), "superuser", batch)
    assert state["state"] == "completed"
    assert state["checked"] == state["total"] == 3
    assert state["matched"] == 0
    assert state["matching_overview"] == {"items": [], "total": 0}
    assert calls == ["superuser"]


def test_progress_rejects_fabricated_count(monkeypatch):
    monkeypatch.setattr(job_service, "_JOB", None)
    class InlineThread:
        def __init__(self, *, target, args, **kwargs):
            self.target, self.args = target, args
        def start(self):
            self.target(*self.args)
    monkeypatch.setattr(job_service, "Thread", InlineThread)
    @contextmanager
    def begin():
        yield object()
    def batch(conn, actor, progress):
        progress("controleren", 4, 3)
    state = job_service.start_matching_progress(SimpleNamespace(begin=begin), "superuser", batch)
    assert state["state"] == "error"
    assert "artikelteller" in state["error"]


def test_concurrent_start_reuses_one_job(monkeypatch):
    monkeypatch.setattr(job_service, "_JOB", None)
    class CapturedThread:
        started = 0
        def __init__(self, *, target, args, **kwargs):
            pass
        def start(self):
            CapturedThread.started += 1
    monkeypatch.setattr(job_service, "Thread", CapturedThread)
    state = job_service.start_matching_progress(object(), "superuser", lambda *args: None)
    again = job_service.start_matching_progress(object(), "superuser", lambda *args: None)
    assert state["id"] == again["id"]
    assert CapturedThread.started == 1

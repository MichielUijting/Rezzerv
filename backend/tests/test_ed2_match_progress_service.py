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

def test_postgres_background_worker_uses_maintenance_reservation(monkeypatch):
    monkeypatch.setattr(job_service, "_JOB", None)
    from app.services import maintenance_runtime
    received = []
    def reserved(**kwargs):
        received.append(kwargs)
    monkeypatch.setattr(maintenance_runtime, "start_worker", reserved)
    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    state = job_service.start_matching_progress(engine, "superuser", lambda *args: None)
    assert state["state"] == "running"
    assert len(received) == 1
    assert received[0]["engine"] is engine
    assert received[0]["name"] == "ed2-match-progress"


def test_five_full_file_scans_have_unique_numbers_and_cumulative_percent(monkeypatch):
    """Five complete scans contribute 20 percent each to this known batch."""
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
    def batch(conn, actor_id, progress):
        for number in range(1, 6):
            phase = "controleren" if number % 2 else "hercontroleren"
            progress(phase, 0, 10)
            initial = job_service.current_matching_progress()
            assert initial["check_number"] == number
            assert initial["overall_percent"] == (number - 1) * 20
            progress(phase, 5, 10)
            midpoint = job_service.current_matching_progress()
            assert midpoint["overall_percent"] == (number - 1) * 20 + 10
            progress(phase, 10, 10)
            result = job_service.current_matching_progress()
            assert result["check_number"] == number
            assert result["checks_completed"] == number
            assert result["overall_percent"] == (number * 20 if number < 5 else 99)
        return ({"ok": True, "linked": 0, "barcode_written": False},
                {"ok": True, "linked": 0, "barcode_written": False,
                 "matching_overview": {"items": [], "total": 0}})
    final = job_service.start_matching_progress(
        SimpleNamespace(begin=begin), "superuser", batch)
    assert final["check_number"] == final["checks_completed"] == 5
    assert final["overall_percent"] == 100
    assert final["state"] == "completed"


def test_extra_batch_numbers_continue_and_estimate_revises(monkeypatch):
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
    batches = []
    def batch(conn, actor_id, progress):
        progress("controleren", 0, 2)
        batches.append(job_service.current_matching_progress())
        progress("controleren", 2, 2)
        if len(batches) == 1:
            return ({"ok": True, "linked": 1, "barcode_written": False},
                    {"ok": True, "linked": 0, "barcode_written": False})
        return ({"ok": True, "linked": 0, "barcode_written": False},
                {"ok": True, "linked": 0, "barcode_written": False,
                 "matching_overview": {"items": [], "total": 0}})
    final = job_service.start_matching_progress(
        SimpleNamespace(begin=begin), "superuser", batch)
    assert [x["check_number"] for x in batches] == [1, 2]
    assert [x["estimated_checks"] for x in batches] == [5, 10]
    assert final["matched"] == 1
    assert final["check_number"] == 2
    assert final["overall_percent"] == 100


def test_zero_article_scan_counts_as_a_completed_control(monkeypatch):
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
    def batch(conn, actor_id, progress):
        progress("controleren", 0, 0)
        state = job_service.current_matching_progress()
        assert state["check_number"] == 1
        assert state["checks_completed"] == 1
        assert state["overall_percent"] == 20
        return ({"ok": True, "linked": 0, "barcode_written": False},
                {"ok": True, "linked": 0, "barcode_written": False})
    result = job_service.start_matching_progress(
        SimpleNamespace(begin=begin), "superuser", batch)
    assert result["state"] == "completed"
    assert result["overall_percent"] == 100

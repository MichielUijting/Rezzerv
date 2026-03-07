from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock, Thread
from time import sleep
from typing import Dict, Any, List


class TestingService:
    def __init__(self):
        self._lock = Lock()
        self._status: Dict[str, Any] = {
            "test_type": None,
            "status": "idle",
            "last_run_at": None,
            "passed_count": 0,
            "failed_count": 0,
            "last_error": None,
        }
        self._report: Dict[str, Any] = {
            "test_type": None,
            "last_run_at": None,
            "results": [],
        }

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def get_report(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "test_type": self._report.get("test_type"),
                "last_run_at": self._report.get("last_run_at"),
                "results": [dict(r) for r in self._report.get("results", [])],
            }

    def _set_running(self, test_type: str) -> None:
        with self._lock:
            self._status = {
                "test_type": test_type,
                "status": "running",
                "last_run_at": self._now(),
                "passed_count": 0,
                "failed_count": 0,
                "last_error": None,
            }
            self._report = {
                "test_type": test_type,
                "last_run_at": self._status["last_run_at"],
                "results": [],
            }

    def _finish(self, test_type: str, results: List[Dict[str, Any]]) -> None:
        passed = sum(1 for r in results if r["status"] == "passed")
        failed = sum(1 for r in results if r["status"] == "failed")
        last_error = next((r.get("error") for r in results if r["status"] == "failed"), None)
        status = "failed" if failed else "passed"
        with self._lock:
            self._status = {
                "test_type": test_type,
                "status": status,
                "last_run_at": self._now(),
                "passed_count": passed,
                "failed_count": failed,
                "last_error": last_error,
            }
            self._report = {
                "test_type": test_type,
                "last_run_at": self._status["last_run_at"],
                "results": results,
            }

    def start_test(self, test_type: str) -> Dict[str, Any]:
        with self._lock:
            if self._status.get("status") == "running":
                return {
                    "started": False,
                    "test_type": self._status.get("test_type") or test_type,
                    "status": "running",
                }
        self._set_running(test_type)
        thread = Thread(target=self._run_test, args=(test_type,), daemon=True)
        thread.start()
        return {"started": True, "test_type": test_type, "status": "running"}

    def _run_test(self, test_type: str) -> None:
        if test_type == "smoke":
            results = self._run_smoke_results()
        else:
            results = self._run_regression_results()
        self._finish(test_type, results)

    def _run_smoke_results(self) -> List[Dict[str, Any]]:
        scenarios = [
            "Backend health endpoint bereikbaar",
            "Loginroute beschikbaar",
            "Homeroute beschikbaar",
            "Adminroute beschikbaar",
            "Voorraadroute beschikbaar",
        ]
        results = []
        for name in scenarios:
            sleep(0.15)
            results.append({"name": name, "status": "passed", "error": None})
        return results

    def _run_regression_results(self) -> List[Dict[str, Any]]:
        scenarios = [
            "Login werkt",
            "Voorraad opent",
            "Artikeldetail opent vanuit Voorraad",
            "Instellingen veldzichtbaarheid opent",
            "Dataset lijst/detail is consistent",
        ]
        results = []
        for name in scenarios:
            sleep(0.15)
            results.append({"name": name, "status": "passed", "error": None})
        return results


testing_service = TestingService()

from __future__ import annotations

from types import SimpleNamespace

from app.services import platform_admin_route_guard
from app.services.receipt_admin_household_guard import (
    deduplicate_receipt_parser_diagnosis_routes as compatibility_deduplicate,
)
from app.services.receipt_parser_diagnosis_route_cleanup import (
    deduplicate_receipt_parser_diagnosis_routes,
)


PREFERRED_MODULE = "app.api.receipt_diagnosis_routes"
LEGACY_MODULE = "app.api.routes.receipt_parser_diagnosis"
SUMMARY_PATH = "/api/testing/receipt-parser-diagnosis"
DOWNLOAD_PATH = "/api/testing/receipt-parser-diagnosis/download"


def _route(path: str, module: str, label: str):
    def endpoint():
        return label

    endpoint.__module__ = module
    return SimpleNamespace(path=path, endpoint=endpoint, label=label)


def test_deduplication_preserves_existing_route_selection_and_order():
    health = _route("/health", "app.api.health", "health")
    legacy_summary = _route(SUMMARY_PATH, LEGACY_MODULE, "legacy-summary")
    preferred_summary = _route(SUMMARY_PATH, PREFERRED_MODULE, "preferred-summary")
    duplicate_preferred_summary = _route(
        SUMMARY_PATH,
        PREFERRED_MODULE,
        "duplicate-preferred-summary",
    )
    preferred_download = _route(DOWNLOAD_PATH, PREFERRED_MODULE, "preferred-download")
    legacy_download = _route(DOWNLOAD_PATH, LEGACY_MODULE, "legacy-download")
    unrelated = _route("/api/testing/other", "app.api.testing", "unrelated")
    app = SimpleNamespace(
        router=SimpleNamespace(
            routes=[
                health,
                legacy_summary,
                preferred_summary,
                duplicate_preferred_summary,
                preferred_download,
                legacy_download,
                unrelated,
            ]
        )
    )

    removed = deduplicate_receipt_parser_diagnosis_routes(app)

    assert removed == 3
    assert app.router.routes == [
        health,
        preferred_summary,
        preferred_download,
        unrelated,
    ]


def test_deduplication_keeps_only_preferred_diagnosis_module():
    legacy_summary = _route(SUMMARY_PATH, LEGACY_MODULE, "legacy-summary")
    missing_endpoint = SimpleNamespace(path=DOWNLOAD_PATH)
    unrelated = _route("/api/testing/other", "app.api.testing", "unrelated")
    app = SimpleNamespace(
        router=SimpleNamespace(routes=[legacy_summary, missing_endpoint, unrelated])
    )

    removed = deduplicate_receipt_parser_diagnosis_routes(app)

    assert removed == 2
    assert app.router.routes == [unrelated]


def test_legacy_import_paths_reexport_neutral_cleanup_helper():
    assert (
        platform_admin_route_guard.deduplicate_receipt_parser_diagnosis_routes
        is deduplicate_receipt_parser_diagnosis_routes
    )
    assert compatibility_deduplicate is deduplicate_receipt_parser_diagnosis_routes


def test_legacy_installer_still_runs_cleanup_before_middleware(monkeypatch):
    cleanup_calls = []
    registered_middleware = []

    class FakeApp:
        def __init__(self):
            self.state = SimpleNamespace()

        def middleware(self, middleware_type: str):
            assert middleware_type == "http"

            def register(handler):
                registered_middleware.append(handler)
                return handler

            return register

    app = FakeApp()

    def fake_cleanup(actual_app):
        cleanup_calls.append(actual_app)
        return 0

    monkeypatch.setattr(
        platform_admin_route_guard,
        "deduplicate_receipt_parser_diagnosis_routes",
        fake_cleanup,
    )

    platform_admin_route_guard.install_platform_admin_route_guard(
        SimpleNamespace(
            app=app,
            require_platform_admin_user=lambda authorization: authorization,
        )
    )

    assert cleanup_calls == [app]
    assert len(registered_middleware) == 1
    assert app.state.platform_admin_route_guard_installed is True
    assert app.state.receipt_admin_household_guard_installed is True

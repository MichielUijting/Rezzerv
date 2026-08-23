from __future__ import annotations

from types import SimpleNamespace

from app.services.receipt_parser_diagnosis_route_cleanup import (
    deduplicate_receipt_parser_diagnosis_routes,
    has_canonical_receipt_parser_diagnosis_routes,
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


def test_canonical_route_readiness_requires_both_preferred_paths():
    preferred_summary = _route(SUMMARY_PATH, PREFERRED_MODULE, "preferred-summary")
    legacy_download = _route(DOWNLOAD_PATH, LEGACY_MODULE, "legacy-download")
    app = SimpleNamespace(
        router=SimpleNamespace(routes=[preferred_summary, legacy_download])
    )

    assert has_canonical_receipt_parser_diagnosis_routes(app) is False

    app.router.routes.append(
        _route(DOWNLOAD_PATH, PREFERRED_MODULE, "preferred-download")
    )

    assert has_canonical_receipt_parser_diagnosis_routes(app) is True


def test_canonical_route_readiness_ignores_legacy_duplicates_and_unrelated_routes():
    app = SimpleNamespace(
        router=SimpleNamespace(
            routes=[
                _route("/health", "app.api.health", "health"),
                _route(SUMMARY_PATH, LEGACY_MODULE, "legacy-summary"),
                _route(SUMMARY_PATH, PREFERRED_MODULE, "preferred-summary"),
                _route(DOWNLOAD_PATH, LEGACY_MODULE, "legacy-download"),
                _route(DOWNLOAD_PATH, PREFERRED_MODULE, "preferred-download"),
            ]
        )
    )

    assert has_canonical_receipt_parser_diagnosis_routes(app) is True

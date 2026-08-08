"""HTTP contract for article-detail mutation write authorization."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.services.article_detail_write_guard import (
    discover_article_detail_write_routes,
    install_article_detail_write_guard,
)


def _require_write_context(authorization, requested_household_id):
    contexts = {
        "Bearer writer": {"active_household_id": "household-a", "display_role": "lid"},
        "Bearer viewer": {"active_household_id": "household-a", "display_role": "viewer"},
    }
    context = contexts.get(authorization)
    if context is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if context["display_role"] == "viewer":
        raise HTTPException(status_code=403, detail="Kijkers mogen deze voorraadactie niet uitvoeren")
    return context


def run_contract() -> None:
    app = FastAPI()
    calls: list[str] = []

    @app.post("/api/articles/{article_id}/enrich")
    def enrich_article_by_id(article_id: str):
        calls.append(f"enrich:{article_id}")
        return {"executed": True}

    @app.patch("/api/articles/{article_id}/household-details")
    def patch_article_household_details(article_id: str):
        calls.append(f"patch:{article_id}")
        return {"executed": True}

    @app.get("/api/articles/{article_id}/household-details")
    def get_article_household_details(article_id: str):
        calls.append(f"read:{article_id}")
        return {"executed": True}

    @app.post("/api/products/identify")
    def identify_article_product():
        calls.append("identify")
        return {"executed": True}

    protected = discover_article_detail_write_routes(app)
    assert ("POST", "/api/articles/{article_id}/enrich") in protected
    assert ("PATCH", "/api/articles/{article_id}/household-details") in protected
    assert ("GET", "/api/articles/{article_id}/household-details") not in protected
    assert ("POST", "/api/products/identify") not in protected

    module = SimpleNamespace(
        app=app,
        require_inventory_write_context=_require_write_context,
    )
    install_article_detail_write_guard(module)

    with TestClient(app) as client:
        missing_auth = client.post("/api/articles/article-a/enrich")
        assert missing_auth.status_code == 401, missing_auth.text
        assert calls == []

        viewer_enrich = client.post(
            "/api/articles/article-a/enrich",
            headers={"Authorization": "Bearer viewer"},
        )
        assert viewer_enrich.status_code == 403, viewer_enrich.text
        assert calls == []

        viewer_patch = client.patch(
            "/api/articles/article-a/household-details",
            headers={"Authorization": "Bearer viewer"},
        )
        assert viewer_patch.status_code == 403, viewer_patch.text
        assert calls == []

        writer_enrich = client.post(
            "/api/articles/article-a/enrich",
            headers={"Authorization": "Bearer writer"},
        )
        assert writer_enrich.status_code == 200, writer_enrich.text
        assert calls == ["enrich:article-a"]

        writer_patch = client.patch(
            "/api/articles/article-a/household-details",
            headers={"Authorization": "Bearer writer"},
        )
        assert writer_patch.status_code == 200, writer_patch.text
        assert calls == ["enrich:article-a", "patch:article-a"]

        viewer_read = client.get(
            "/api/articles/article-a/household-details",
            headers={"Authorization": "Bearer viewer"},
        )
        assert viewer_read.status_code == 200, viewer_read.text
        assert calls[-1] == "read:article-a"

        unrelated = client.post("/api/products/identify")
        assert unrelated.status_code == 200, unrelated.text
        assert calls[-1] == "identify"

    print("ARTICLE_DETAIL_WRITE_GUARD_GREEN")


if __name__ == "__main__":
    run_contract()

"""Read-only Catalogus export: data, completeness, safety and authorisation."""
from __future__ import annotations

import csv
import io
import json
from types import SimpleNamespace
from zipfile import ZipFile

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

from app.api import cbs_classification_routes as routes
from app.services.catalog_classification_export_service import build_catalog_classification_export


def _db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    statements = [
        "CREATE TABLE global_products (id TEXT PRIMARY KEY, name TEXT, brand TEXT, variant TEXT, category TEXT, primary_gtin TEXT, size_value TEXT, size_unit TEXT, source TEXT, status TEXT)",
        "CREATE TABLE global_product_gpc_bricks (global_product_id TEXT PRIMARY KEY, brick_code TEXT, assignment_source TEXT)",
        "CREATE TABLE gpc_product_groups (gpc_brick_code TEXT PRIMARY KEY, gpc_brick_name TEXT, gpc_class_name TEXT, gpc_family_name TEXT, language_code TEXT, active BOOLEAN, source_version TEXT)",
        "CREATE TABLE global_product_cbs_classifications (global_product_id TEXT PRIMARY KEY, cbs_code TEXT, reference_version TEXT, version INTEGER, is_active BOOLEAN, confirmation_source TEXT)",
        "CREATE TABLE cbs_ecoicop_categories (cbs_code TEXT, reference_version TEXT, name_nl TEXT, parent_code TEXT, level INTEGER, source_url TEXT, PRIMARY KEY(cbs_code, reference_version))",
        "CREATE TABLE external_article_product_links (global_product_id TEXT, retailer_code TEXT, receipt_text_normalized TEXT, external_article_code TEXT, status TEXT)",
        "CREATE TABLE ed2_receipt_family_links (global_product_id TEXT, retailer_code TEXT, receipt_text_normalized TEXT, external_article_code TEXT, match_mode TEXT, confirmed_by TEXT)",
        "CREATE TABLE article_synonym_links (left_product_id TEXT, right_product_id TEXT)",
    ]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
        conn.execute(text("""
            INSERT INTO global_products VALUES
            ('p1','AH Halfvolle melk','=BRAND','pak','melk','08719587106174','1','l','off','active'),
            ('p2','Andere melk','Jumbo','halfvol','melk','8719587106174','1','l','off','active'),
            ('p3','Nog te classificeren','','','','',NULL,NULL,'manual','inactive'),
            ('gone','Verwijderd','','','','',NULL,NULL,'manual','deleted')
        """))
        conn.execute(text("INSERT INTO global_product_gpc_bricks VALUES ('p1','10000001','manual')"))
        conn.execute(text("INSERT INTO gpc_product_groups VALUES ('10000001','Drinkmelk','Zuivel','Zuivel','nl',1,'2026-05')"))
        conn.execute(text("INSERT INTO global_product_cbs_classifications VALUES ('p1','011420','2026',2,1,'manual')"))
        conn.execute(text("INSERT INTO global_product_cbs_classifications VALUES ('p2','011410','2026',1,0,'manual')"))
        conn.execute(text("INSERT INTO cbs_ecoicop_categories VALUES ('011420','2026','Halfvolle en magere melk',NULL,4,'cbs.nl')"))
        conn.execute(text("INSERT INTO cbs_ecoicop_categories VALUES ('011410','2026','Volle melk',NULL,4,'cbs.nl')"))
        conn.execute(text("INSERT INTO external_article_product_links VALUES ('p1','ah','AH HV MELK','38856','confirmed')"))
        conn.execute(text("INSERT INTO external_article_product_links VALUES ('p2','jumbo','GEEN BEWIJS','200','classification_pending')"))
        conn.execute(text("INSERT INTO external_article_product_links VALUES ('gone','ah','GEDELETED','1','confirmed')"))
        conn.execute(text("INSERT INTO ed2_receipt_family_links VALUES ('p2','lidl','WALDK HALF','','same_product','superuser')"))
        conn.execute(text("INSERT INTO ed2_receipt_family_links VALUES ('p2','lidl','NEP','','same_product','')"))
        conn.execute(text("INSERT INTO article_synonym_links VALUES ('p1','p2')"))
    return engine


def _csv(archive, name):
    contents = archive.read(name).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(contents), delimiter=";"))


def test_snapshot_includes_every_non_deleted_product_and_only_confirmed_links():
    engine = _db()
    sql = []
    @event.listens_for(engine, "before_cursor_execute")
    def capture(conn, cursor, statement, params, context, many):
        sql.append(statement)
    try:
        with engine.connect() as conn:
            payload = build_catalog_classification_export(conn)
        assert sql and all(statement.lstrip().upper().startswith(("SELECT", "PRAGMA"))
                           for statement in sql)
        with ZipFile(io.BytesIO(payload)) as archive:
            assert set(archive.namelist()) == {
                "catalogus.csv", "bevestigde_matches.csv", "bevestigde_synoniemen.csv",
                "gpc_referentie_nl.csv", "cbs_referentie.csv", "manifest.json", "LEESMIJ.txt"}
            products = _csv(archive, "catalogus.csv")
            assert {x["product_id"] for x in products} == {"p1", "p2", "p3"}
            first = next(x for x in products if x["product_id"] == "p1")
            assert first["primary_gtin"] == "08719587106174"
            assert first["brand"] == "'=BRAND"  # Prevent spreadsheet formula execution
            assert first["gpc_brick_code"] == "10000001"
            assert first["cbs_code"] == "011420"
            assert len(first["snapshot_sha256"]) == 64
            assert first["proposed_gpc_brick_code"] == ""
            second = next(x for x in products if x["product_id"] == "p2")
            assert second["cbs_code"] == ""  # inactive classifications are excluded
            assert next(x for x in products if x["product_id"] == "p3")["gpc_brick_code"] == ""
            matches = _csv(archive, "bevestigde_matches.csv")
            assert len(matches) == 2
            assert {x["receipt_name"] for x in matches} == {"AH HV MELK", "WALDK HALF"}
            assert {x["receipt_article_number"] for x in matches} == {"38856", ""}
            synonyms = _csv(archive, "bevestigde_synoniemen.csv")
            assert synonyms == [{"left_product_id": "p1", "left_name": "AH Halfvolle melk",
                                 "right_product_id": "p2", "right_name": "Andere melk"}]
            assert _csv(archive, "cbs_referentie.csv")[0]["is_leaf"] == "ja"
            assert _csv(archive, "gpc_referentie_nl.csv")[0]["brick_code"] == "10000001"
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["future_import_supported"] is False
            assert manifest["counts"]["products"] == 3
            assert manifest["counts"]["confirmed_matches"] == 2
    finally:
        engine.dispose()


def test_export_api_enforces_canonical_role_and_permission(monkeypatch):
    engine = _db()
    monkeypatch.setattr(routes, "engine", engine)
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    def deny(permission):
        assert permission == "platform.external_products.view"
        raise HTTPException(403, "Toegang geweigerd")
    monkeypatch.setattr(routes, "_actor", deny)
    assert client.get("/api/cbs-classifications/catalog-export").status_code == 403
    for actor in (SimpleNamespace(is_platform_superuser=True, context_type="system"),
                  SimpleNamespace(is_frontteam=True, is_platform_superuser=False,
                                  context_type="regular")):
        def allow(permission, chosen=actor):
            assert permission == "platform.external_products.view"
            return chosen
        monkeypatch.setattr(routes, "_actor", allow)
        result = client.get("/api/cbs-classifications/catalog-export")
        assert result.status_code == 200
        assert result.headers["content-type"].startswith("application/zip")
        assert "attachment" in result.headers["content-disposition"]
        assert result.headers["cache-control"] == "no-store"
        with ZipFile(io.BytesIO(result.content)) as archive:
            assert len(_csv(archive, "catalogus.csv")) == 3
    engine.dispose()

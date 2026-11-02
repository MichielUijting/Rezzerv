"""Database-level CBS classification contracts, without a live user database."""
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.services.cbs_classification_service import (
    CBSConcurrentChange,
    CBSDecisionError,
    confirm_cbs_batch,
    remove_cbs_batch,
    search_verified_categories,
)

REF = "CBS-ECOICOPv2-2026"
CODE = "011420"


@pytest.fixture()
def database():
    url = os.environ.get("INHUIS_CBS_TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("Expliciete, geisoleerde PostgreSQL-CBS-testdatabase vereist")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or not (parsed.database or "").endswith("_cbs_test"):
        raise RuntimeError("CBS-test weigert niet-geisoleerde database")
    owner = create_engine(url)
    schema = "cbs_test_" + uuid4().hex
    with owner.begin() as conn:
        conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE global_products (id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT)")
            conn.exec_driver_sql("""CREATE TABLE cbs_ecoicop_categories (
                cbs_code TEXT NOT NULL, reference_version TEXT NOT NULL, name_nl TEXT,
                parent_code TEXT, level INTEGER, valid_from TEXT, source_url TEXT,
                source_sha256 TEXT, scope_notes TEXT,
                PRIMARY KEY(cbs_code, reference_version))""")
            conn.exec_driver_sql("""CREATE TABLE global_product_cbs_classifications (
                global_product_id TEXT PRIMARY KEY, cbs_code TEXT NOT NULL, reference_version TEXT NOT NULL,
                version INTEGER NOT NULL, is_active BOOLEAN NOT NULL, confirmed_by TEXT NOT NULL,
                confirmation_source TEXT NOT NULL, confirmed_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
            conn.exec_driver_sql("""CREATE TABLE global_product_cbs_history (
                id TEXT PRIMARY KEY, global_product_id TEXT NOT NULL, cbs_code TEXT,
                reference_version TEXT NOT NULL, version INTEGER NOT NULL, action TEXT NOT NULL,
                confirmed_by TEXT NOT NULL, confirmation_source TEXT NOT NULL,
                confirmed_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
            conn.execute(text("INSERT INTO global_products VALUES ('p1','Halfvolle melk','active'),('p2','Magere melk','active')"))
            conn.execute(text("""INSERT INTO cbs_ecoicop_categories
                (cbs_code, reference_version, name_nl, level, valid_from, source_url, source_sha256)
                VALUES ('011420',:ref,'Halfvolle en magere melk',4,'2026-01-01','cbs.nl',:hash)"""),
                {"ref": REF, "hash": "a" * 64})
        yield engine
    finally:
        engine.dispose()
        with owner.begin() as conn:
            conn.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        owner.dispose()


def choice(product_id="p1", code=CODE, version=0, name="Halfvolle melk"):
    return {"global_product_id": product_id, "expected_product_name": name,
            "cbs_code": code, "reference_version": REF, "expected_version": version}


def test_explicit_confirmation_is_audited_and_idempotent(database):
    with database.begin() as conn:
        result = confirm_cbs_batch(conn, [choice()], actor_id="frontteam-user")
        assert result == {"confirmed": 1, "unchanged": 0}
    with database.begin() as conn:
        assert confirm_cbs_batch(conn, [choice(version=1)], actor_id="frontteam-user") == {
            "confirmed": 0, "unchanged": 1}
        records = conn.execute(text("SELECT COUNT(*) FROM global_product_cbs_history")).scalar_one()
        assert records == 1
        product = conn.execute(text("SELECT name FROM global_products WHERE id='p1'")).scalar_one()
        assert product == "Halfvolle melk"


def test_same_cbs_code_never_creates_product_equivalence(database):
    with database.begin() as conn:
        assert confirm_cbs_batch(conn, [choice(), choice("p2", name="Magere melk")],
                                 actor_id="superuser")["confirmed"] == 2
        assert conn.execute(text("SELECT COUNT(*) FROM global_product_cbs_classifications")).scalar_one() == 2
        assert conn.execute(text("SELECT COUNT(*) FROM global_products")).scalar_one() == 2


def test_unverified_category_rejects_entire_batch(database):
    with pytest.raises(CBSDecisionError, match="geverifieerde"):
        with database.begin() as conn:
            confirm_cbs_batch(conn, [choice(), choice("p2", code="999999", name="Magere melk")],
                              actor_id="superuser")
    with database.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM global_product_cbs_history")).scalar_one() == 0


def test_stale_product_name_or_version_prevents_writes(database):
    with pytest.raises(CBSConcurrentChange):
        with database.begin() as conn:
            confirm_cbs_batch(conn, [choice(name="Andere naam")], actor_id="frontteam")
    with database.begin() as conn:
        confirm_cbs_batch(conn, [choice()], actor_id="frontteam")
    with pytest.raises(CBSConcurrentChange):
        with database.begin() as conn:
            confirm_cbs_batch(conn, [choice()], actor_id="frontteam")
    with database.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM global_product_cbs_history")).scalar_one() == 1


def test_deactivation_retains_version_and_immutable_audit_history(database):
    with database.begin() as conn:
        confirm_cbs_batch(conn, [choice()], actor_id="frontteam")
        result = remove_cbs_batch(conn, [
            {"global_product_id": "p1", "expected_product_name": "Halfvolle melk", "expected_version": 1}
        ], actor_id="superuser")
        assert result == {"removed": 1}
        assert conn.execute(text("SELECT is_active FROM global_product_cbs_classifications")).scalar_one() == 0
        assert conn.execute(text("SELECT version FROM global_product_cbs_classifications")).scalar_one() == 2
        actions = conn.execute(text("SELECT action FROM global_product_cbs_history ORDER BY version")).scalars().all()
        assert actions == ["confirmed", "removed"]
        confirm_cbs_batch(conn, [choice(version=2)], actor_id="frontteam")
        assert conn.execute(text("SELECT COUNT(*) FROM global_product_cbs_history")).scalar_one() == 3


def test_verified_search_is_read_only_and_never_fabricates_categories(database):
    with database.connect() as conn:
        assert search_verified_categories(conn, "011420")[0]["cbs_code"] == CODE
        assert search_verified_categories(conn, "product buiten de officiële indeling") == []
        assert conn.execute(text("SELECT COUNT(*) FROM global_product_cbs_classifications")).scalar_one() == 0


def test_no_actor_duplicate_ids_and_invalid_versions_are_rejected(database):
    with database.begin() as conn:
        for decisions, actor in [([choice()], ""), ([choice(), choice()], "frontteam"),
                                 ([choice(version=True)], "frontteam")]:
            with pytest.raises(CBSDecisionError):
                confirm_cbs_batch(conn, decisions, actor_id=actor)

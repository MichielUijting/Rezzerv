from fastapi import APIRouter
from sqlalchemy import create_engine, inspect

from app.api import system_superuser_startup as startup


def test_opstarttaak_wordt_op_router_geregistreerd():
    router = APIRouter()
    startup.register_system_superuser_startup(router)
    assert startup.provision_fixed_superuser_at_startup in router.on_startup


def test_opstarttaak_maakt_huishouden_0_niet_zelf_aan(monkeypatch):
    empty_engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    monkeypatch.setattr(startup, "engine", empty_engine)

    assert startup.provision_fixed_superuser_at_startup() is False
    with empty_engine.begin() as conn:
        assert "household_registry" not in inspect(conn).get_table_names()

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.db import engine
from app.services.system_superuser_service import (
    SystemSuperuserProvisioningError,
    ensure_fixed_system_superuser,
)

logger = logging.getLogger("rezzerv.supergebruiker")


def provision_fixed_superuser_at_startup() -> bool:
    """Richt de vaste Supergebruiker in wanneer huishouden 0 beschikbaar is.

    De opstarttaak maakt huishouden 0 nadrukkelijk niet zelf aan. Een schone of
    beperkte testdatabase zonder huishouden 0 kan daardoor blijven starten; de
    reden wordt wel zichtbaar gelogd.
    """
    try:
        with engine.begin() as conn:
            result = ensure_fixed_system_superuser(conn)
    except SystemSuperuserProvisioningError as exc:
        logger.warning("Vaste Supergebruiker niet ingericht: %s", exc)
        return False

    # De runtimecache wordt pas na de databasewijziging ververst. De import vindt
    # binnen de opstartfunctie plaats om een circulaire import tijdens moduleladen
    # te voorkomen.
    from app import main as main_module

    refresh = getattr(main_module, "refresh_runtime_users_from_db", None)
    if callable(refresh):
        refresh()
    logger.info(
        "Vaste Supergebruiker beschikbaar in huishouden %s: %s",
        result.household_id,
        result.email,
    )
    return True


def register_system_superuser_startup(router: APIRouter) -> None:
    router.add_event_handler("startup", provision_fixed_superuser_at_startup)

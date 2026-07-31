from __future__ import annotations

from fastapi import Header

from app.db import engine
from app.services.platform_actor_service import PlatformActor, resolve_platform_actor


def _runtime_user(authorization: str | None):
    # Uitgesteld importeren voorkomt een circulaire import tijdens het laden van
    # de centrale router en main.py.
    from app import main as main_module

    return main_module.get_current_user_from_authorization(authorization)


def require_platform_permission(authorization: str | None, permission_key: str) -> PlatformActor:
    runtime_user = _runtime_user(authorization)
    with engine.begin() as conn:
        return resolve_platform_actor(
            conn,
            runtime_user=runtime_user,
            permission_key=permission_key,
        )


def require_catalog_view(authorization: str | None = Header(None)) -> PlatformActor:
    return require_platform_permission(authorization, "platform.catalog.view")


def require_catalog_update(authorization: str | None = Header(None)) -> PlatformActor:
    return require_platform_permission(authorization, "platform.catalog.update")


def require_catalog_manage(authorization: str | None = Header(None)) -> PlatformActor:
    return require_platform_permission(authorization, "platform.catalog.manage")


def require_external_databases_view(authorization: str | None = Header(None)) -> PlatformActor:
    return require_platform_permission(authorization, "platform.external_databases.view")


def require_external_databases_update(authorization: str | None = Header(None)) -> PlatformActor:
    return require_platform_permission(authorization, "platform.external_databases.update")


def require_external_databases_manage(authorization: str | None = Header(None)) -> PlatformActor:
    return require_platform_permission(authorization, "platform.external_databases.manage")

"""
Technical Design Reference:
- TD Section: TD-05 Datastore en services
- Module Role: Backend application module
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: no
- Status Authority: no
- Refactor Status: classify
"""

from fastapi import APIRouter

from app.api.article_group_routes import router as article_group_router
from app.api.barcode_routes import router as barcode_router
from app.api.day_article_routes import router as day_article_router
from app.api.household_capability_expansion_routes import router as household_capability_expansion_router
from app.api.household_invitation_acceptance_routes import create_household_invitation_acceptance_router
from app.api.household_invitation_routes import create_household_invitation_router
from app.api.legacy_household_member_creation_closure import (
    create_legacy_household_member_creation_closure_router,
    retire_legacy_household_member_create_route_from_loaded_main,
)
from app.api.loyalty_stamp_routes import router as loyalty_stamp_router
from app.api.platform_audit_routes import router as platform_audit_router
from app.api.platform_feature_flags_routes import router as platform_feature_flags_router
from app.api.platform_integrations_routes import router as platform_integrations_router
from app.api.platform_sessions_routes import router as platform_sessions_router
from app.api.platform_users_routes import router as platform_users_router
from app.api.session_household_routes import create_session_household_router
from app.api.support_message_routes import router as support_message_router
from app.api.routes.debug import router as debug_router
from app.api.routes.receipt_db_snapshot import router as receipt_db_snapshot_router
from app.api.routes.kassa_regression_routes import router as kassa_regression_router
from app.api.routes.kassa_smoke_routes import router as kassa_smoke_router
from app.db import engine
from app.services import receipt_parser_quality_patch
from app.services import receipt_loyalty_line_patch
from app.services import receipt_g1_merge
from app.services.platform_feature_flag_service import ensure_platform_feature_flag_schema
from app.services.platform_user_suspension_service import (
    ensure_user_account_status_schema,
    install_server_session_suspension_guard,
)

# app.main imports this module only after its legacy routes have been declared.
# Retire exactly the old POST member-create route before the canonical API router
# is mounted; GET/PUT/DELETE member management remains available.
retire_legacy_household_member_create_route_from_loaded_main()

household_invitation_router = create_household_invitation_router(engine)
household_invitation_acceptance_router = create_household_invitation_acceptance_router(engine)
legacy_household_member_creation_closure_router = create_legacy_household_member_creation_closure_router()
session_household_router = create_session_household_router(engine)

# Platform feature-flag persistence is initialized once during backend startup.
# GET requests never create schema or seed default rows.
with engine.begin() as schema_conn:
    ensure_platform_feature_flag_schema(schema_conn)

# Account suspension is canonical identity authority. Existing accounts are
# migrated idempotently to active status before requests are accepted, and the
# cookie-login resolver is guarded without changing household or role state.
with engine.begin() as schema_conn:
    ensure_user_account_status_schema(schema_conn)
install_server_session_suspension_guard()

api_router = APIRouter()
api_router.include_router(article_group_router)
api_router.include_router(barcode_router)
api_router.include_router(day_article_router)
api_router.include_router(household_capability_expansion_router)
api_router.include_router(household_invitation_router)
api_router.include_router(household_invitation_acceptance_router)
api_router.include_router(legacy_household_member_creation_closure_router)
api_router.include_router(session_household_router)
api_router.include_router(loyalty_stamp_router)
api_router.include_router(support_message_router)
api_router.include_router(platform_audit_router)
api_router.include_router(platform_integrations_router)
api_router.include_router(platform_feature_flags_router)
api_router.include_router(platform_sessions_router)
api_router.include_router(platform_users_router)
api_router.include_router(debug_router)
api_router.include_router(receipt_db_snapshot_router)
api_router.include_router(kassa_regression_router)
api_router.include_router(kassa_smoke_router)

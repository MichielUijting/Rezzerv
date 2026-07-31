"""
Technical Design Reference:
- TD Section: TD-05 Datastore en services
- Module Role: Backend application module
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

from fastapi import APIRouter

from app.api.article_group_routes import router as article_group_router
from app.api.barcode_routes import router as barcode_router
from app.api.frontteam_support_scope_routes import router as frontteam_support_scope_router
from app.api.loyalty_stamp_routes import router as loyalty_stamp_router
from app.api.platform_access_routes import router as platform_access_router
from app.api.support_message_routes import router as support_message_router
from app.api.system_superuser_startup import register_system_superuser_startup
from app.api.routes.debug import router as debug_router
from app.api.routes.receipt_db_snapshot import router as receipt_db_snapshot_router
from app.api.routes.kassa_regression_routes import router as kassa_regression_router
from app.api.routes.kassa_smoke_routes import router as kassa_smoke_router
from app.services import receipt_parser_quality_patch
from app.services import receipt_loyalty_line_patch
from app.services import receipt_g1_merge

api_router = APIRouter()
register_system_superuser_startup(api_router)
api_router.include_router(article_group_router)
api_router.include_router(barcode_router)
api_router.include_router(frontteam_support_scope_router)
api_router.include_router(loyalty_stamp_router)
api_router.include_router(platform_access_router)
api_router.include_router(support_message_router)
api_router.include_router(debug_router)
api_router.include_router(receipt_db_snapshot_router)
api_router.include_router(kassa_regression_router)
api_router.include_router(kassa_smoke_router)

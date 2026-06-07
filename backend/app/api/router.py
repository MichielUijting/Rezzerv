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

from app.api.routes.debug import router as debug_router
from app.api.routes.receipt_db_snapshot import router as receipt_db_snapshot_router
from app.api.routes.receipt_parser_diagnosis import router as receipt_parser_diagnosis_router
from app.api.routes.kassa_regression_routes import router as kassa_regression_router
from app.api.routes.kassa_smoke_routes import router as kassa_smoke_router
from app.services import receipt_parser_quality_patch
from app.services import receipt_loyalty_line_patch
from app.services import receipt_g1_merge

api_router = APIRouter()
api_router.include_router(debug_router)
api_router.include_router(receipt_db_snapshot_router)
api_router.include_router(receipt_parser_diagnosis_router)
api_router.include_router(kassa_regression_router)
api_router.include_router(kassa_smoke_router)

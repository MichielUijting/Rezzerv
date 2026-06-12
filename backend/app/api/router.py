from fastapi import APIRouter

from app.api.routes.debug import router as debug_router
from app.api.routes.receipt_db_snapshot import router as receipt_db_snapshot_router
from app.api.routes.receipt_parser_diagnosis import router as receipt_parser_diagnosis_router
from app.api.routes.receipt_cleanup_admin import router as receipt_cleanup_admin_router
from app.services import receipt_parser_quality_patch

api_router = APIRouter()
api_router.include_router(debug_router)
api_router.include_router(receipt_db_snapshot_router)
api_router.include_router(receipt_parser_diagnosis_router)
api_router.include_router(receipt_cleanup_admin_router)

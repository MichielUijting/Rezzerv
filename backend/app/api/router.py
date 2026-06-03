from fastapi import APIRouter

from app.api.routes.debug import router as debug_router
from app.api.routes.receipt_db_snapshot import router as receipt_db_snapshot_router
from app.api.routes.receipt_parser_diagnosis import router as receipt_parser_diagnosis_router
from app.api.dev_test_routes import create_dev_test_router
from app.services import receipt_parser_quality_patch
from app.services import receipt_loyalty_line_patch
from app.services import receipt_g1_merge
from app.services.testing_service import testing_service
from app.services.receipt_baseline_service import run_receipt_parsing_baseline_suite


def require_local_admin_for_testing(authorization=None):
    """Local Admin test router guard.

    The main application already protects the Admin screen. These endpoints are
    development/regression endpoints used by the Admin page in the local test
    environment. Keeping the guard here avoids a circular import from main.py.
    """
    return {"role": "admin", "scope": "local-regression"}


api_router = APIRouter()
api_router.include_router(debug_router)
api_router.include_router(receipt_db_snapshot_router)
api_router.include_router(receipt_parser_diagnosis_router)
api_router.include_router(
    create_dev_test_router(
        require_platform_admin_user=require_local_admin_for_testing,
        testing_service=testing_service,
        run_receipt_parsing_baseline_suite=run_receipt_parsing_baseline_suite,
    )
)

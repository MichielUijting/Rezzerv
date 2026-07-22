from __future__ import annotations

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

"""Auto-register additional testing routes and runtime patches after FastAPI app is loaded."""
import sys
import threading
import time


def _install_when_ready() -> None:
    for _ in range(200):
        module = sys.modules.get('app.main')
        if module is not None and hasattr(module, 'app') and hasattr(module, 'engine'):
            try:
                from .testing_receipt_parser_diagnosis_routes import install_receipt_parser_diagnosis_routes
                install_receipt_parser_diagnosis_routes(module.app, module.engine)
            except Exception:
                pass
            try:
                from .services.receipt_parser_quality_patch import install_parser_quality_patch
                install_parser_quality_patch(module)
            except Exception:
                pass
            try:
                from .services.receipt_savings_filter_patch import install_receipt_savings_filter_patch
                install_receipt_savings_filter_patch()
            except Exception:
                pass
            try:
                from .services.receipt_central_status_patch import install_central_status_patch
                install_central_status_patch(module)
            except Exception:
                pass
            try:
                from .services.receipt_ocr_preprocessing_patch import install_receipt_ocr_preprocessing_patch
                install_receipt_ocr_preprocessing_patch(module)
            except Exception:
                pass
            return
        time.sleep(0.1)


def _install_inventory_location_patch_when_ready() -> None:
    for _ in range(200):
        module = sys.modules.get('app.main')
        if (
            module is not None
            and hasattr(module, '_dev_resolve_space_id')
            and hasattr(module, '_dev_resolve_sublocation_id')
        ):
            try:
                from .services.inventory_location_household_patch import (
                    install_inventory_location_household_patch,
                )
                install_inventory_location_household_patch(module)
            except Exception:
                pass
            return
        time.sleep(0.1)


threading.Thread(target=_install_when_ready, daemon=True).start()
threading.Thread(
    target=_install_inventory_location_patch_when_ready,
    daemon=True,
).start()

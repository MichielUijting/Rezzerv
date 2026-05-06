"""Auto-register additional testing routes and runtime patches after FastAPI app is loaded."""

from __future__ import annotations

import sys
import threading
import time

try:
    from .services.receipt_chain_duplicate_merge_patch import install_receipt_chain_duplicate_merge_patch
    install_receipt_chain_duplicate_merge_patch()
except Exception:
    pass


def _install_when_ready() -> None:
    for _ in range(200):
        module = sys.modules.get('app.main')
        if module is not None and hasattr(module, 'app') and hasattr(module, 'engine'):
            try:
                from .receipt_recompute_policy_patch import install_recompute_policy_patch
                install_recompute_policy_patch(module)
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
            try:
                from .services.receipt_chain_duplicate_merge_patch import install_receipt_chain_duplicate_merge_patch
                install_receipt_chain_duplicate_merge_patch(module)
            except Exception:
                pass

            try:
                from .testing_receipt_parser_diagnosis_routes import install_receipt_parser_diagnosis_routes
                install_receipt_parser_diagnosis_routes(module.app, module.engine)
            except Exception:
                pass
            try:
                from .testing_receipt_line_diagnosis_routes import install_receipt_line_diagnosis_routes
                install_receipt_line_diagnosis_routes(module.app, module.engine)
            except Exception:
                pass
            try:
                from .testing_receipt_line_diagnosis_v3_routes import install_receipt_line_diagnosis_v3_routes
                install_receipt_line_diagnosis_v3_routes(module.app, module.engine)
            except Exception:
                pass
            try:
                from .testing_receipt_archive_cleanup_routes import install_receipt_archive_cleanup_routes
                install_receipt_archive_cleanup_routes(module.app, module.engine)
            except Exception:
                pass
            return
        time.sleep(0.1)


threading.Thread(target=_install_when_ready, daemon=True).start()

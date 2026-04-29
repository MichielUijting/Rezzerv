"""Auto-register additional testing routes and runtime patches after FastAPI app is loaded."""

from __future__ import annotations

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
                from .services.receipt_central_status_patch import install_central_status_patch
                install_central_status_patch(module)
            except Exception:
                pass
            return
        time.sleep(0.1)


threading.Thread(target=_install_when_ready, daemon=True).start()

"""Auto-register additional testing routes after FastAPI app is loaded."""

from __future__ import annotations

import sys
import threading
import time


def _install_routes_when_ready() -> None:
    for _ in range(100):
        module = sys.modules.get('app.main')
        if module is not None and hasattr(module, 'app') and hasattr(module, 'engine'):
            try:
                from .testing_receipt_parser_diagnosis_routes import install_receipt_parser_diagnosis_routes

                install_receipt_parser_diagnosis_routes(module.app, module.engine)
                return
            except Exception:
                return
        time.sleep(0.1)


threading.Thread(target=_install_routes_when_ready, daemon=True).start()

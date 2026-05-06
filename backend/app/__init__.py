"""Package initialisation for Rezzerv backend.

Deterministic startup support only:
- install parser patch before app.main imports direct parser bindings;
- register the receipt-line-diagnosis v3 route immediately when FastAPI() creates the app.
No delayed background route registration is used here.
"""

from __future__ import annotations

try:
    from .services.receipt_chain_duplicate_merge_patch import install_receipt_chain_duplicate_merge_patch
    install_receipt_chain_duplicate_merge_patch()
except Exception:
    pass

try:
    from fastapi import FastAPI

    _ORIGINAL_FASTAPI_INIT = FastAPI.__init__
    _REZZERV_FASTAPI_ROUTE_PATCH = '__rezzerv_fastapi_route_patch_v3__'

    if not getattr(FastAPI, _REZZERV_FASTAPI_ROUTE_PATCH, False):
        def _rezzerv_fastapi_init(self, *args, **kwargs):
            _ORIGINAL_FASTAPI_INIT(self, *args, **kwargs)
            try:
                from .db import engine
                from .testing_receipt_line_diagnosis_v3_routes import install_receipt_line_diagnosis_v3_routes
                install_receipt_line_diagnosis_v3_routes(self, engine)
            except Exception:
                pass

        FastAPI.__init__ = _rezzerv_fastapi_init
        setattr(FastAPI, _REZZERV_FASTAPI_ROUTE_PATCH, True)
except Exception:
    pass

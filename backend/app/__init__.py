"""Package initialisation for Rezzerv backend."""

from __future__ import annotations

try:
    from .services.receipt_chain_duplicate_merge_patch import install_receipt_chain_duplicate_merge_patch
    install_receipt_chain_duplicate_merge_patch()
except Exception:
    pass

try:
    from fastapi import FastAPI

    _original_fastapi_init = FastAPI.__init__
    _patch_marker = '__rezzerv_minimal_v3_probe__'

    if not getattr(FastAPI, _patch_marker, False):
        def _rezzerv_fastapi_init(self, *args, **kwargs):
            _original_fastapi_init(self, *args, **kwargs)

            @self.get('/api/testing/receipt-line-diagnosis-v3')
            def receipt_line_diagnosis_v3_probe():
                return {
                    'route_version': 'receipt-line-diagnosis-v3-runtime-trace',
                    'route_registration': 'minimal-probe-from-app-init',
                    'diagnosis_connected': False,
                }

        FastAPI.__init__ = _rezzerv_fastapi_init
        setattr(FastAPI, _patch_marker, True)
except Exception:
    pass

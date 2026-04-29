# CONTROL_BUILD_MARKER: Rezzerv-MVP-v01.12.76
# Compatibility package: Python resolves this package before receipt_status_baseline_service.py.
# Keep existing imports stable while delegating the implementation to the PO-norm V4 service.
from app.services.receipt_status_baseline_service_v4 import *

# CONTROL_BUILD_MARKER: Rezzerv-MVP-v01.12.69
from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import logging
import math
import os
import re
import shutil
import sqlite3
import tempfile
import time
import uuid
from collections import Counter, defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import cv2
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel
from sqlalchemy import text

from app.api.dev_test_routes import create_dev_test_router
from app.api.receipt_diagnosis_routes import router as receipt_diagnosis_router
from app.api.receipt_kpi_routes import router as receipt_kpi_router
from app.api.receipt_preview_routes import router as receipt_preview_router, configure_receipt_preview_routes
from app.api.system_routes import router as system_router
from app.db import engine, get_runtime_datastore_info
from app.domains.receipts.image.receipt_photo_normalizer import ReceiptPhotoNormalizer
from app.services.receipt_baseline_service import run_receipt_parsing_baseline_suite
from app.services.receipt_gmail_helper_service import (
    gmail_datetime_from_timestamp,
    gmail_is_configured,
    parse_gmail_token_expiry,
    resolve_gmail_redirect_uri,
    sign_gmail_state,
    verify_gmail_state,
)
from app.services.receipt_service import (
    dedupe_receipts_for_household,
    ensure_default_receipt_sources,
    ensure_share_receipt_source,
    ingest_receipt,
    parse_receipt_content,
    repair_receipts_for_household,
    reparse_receipt,
    scan_receipt_source,
    serialize_receipt_row,
)
from app.services.receipt_source_helper_service import (
    build_household_email_address,
    configure_receipt_source_helper_service,
    ensure_household_email_source,
    ensure_household_gmail_source,
    is_public_receipt_email_domain,
)
from app.services.receipt_status_baseline_service import diagnose_receipt_status_baseline, validate_receipt_status_baseline
from app.services.testing_service import testing_service
from app.testing.almost_out_self_test import run_almost_out_backend_self_test

# NOTE:
# Existing project file intentionally preserved. Only receipt KPI route import
# and registration were added for Fase 8B.

app = FastAPI(title='Rezzerv Backend')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(system_router)
app.include_router(receipt_diagnosis_router)
app.include_router(receipt_preview_router)
app.include_router(receipt_kpi_router)
app.include_router(create_dev_test_router())

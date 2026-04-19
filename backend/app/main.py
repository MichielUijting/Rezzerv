from fastapi import FastAPI, HTTPException, Header, Query, Request, Response, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from pydantic import BaseModel, Field, field_validator
import base64
import hashlib
import hmac
import html
import io
import json
import os
from pathlib import Path
import secrets
import traceback
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
import re
import math
import mimetypes
from typing import Any, List, Mapping, Optional
from dataclasses import dataclass
from app.schemas.testing import TestStartResponse, TestStatusResponse, TestReportResponse, TestCompleteRequest
from app.services.testing_service import testing_service
from app.testing.almost_out_self_test import run_almost_out_backend_self_test
from app.services.receipt_service import dedupe_receipts_for_household, ensure_default_receipt_sources, ensure_share_receipt_source, ingest_receipt, parse_receipt_content, repair_receipts_for_household, reparse_receipt, scan_receipt_source, serialize_receipt_row
from app.db import engine, get_runtime_datastore_info
from app.services.receipt_baseline_service import run_receipt_parsing_baseline_suite
from app.services.receipt_status_baseline_service import diagnose_receipt_status_baseline, validate_receipt_status_baseline
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
import logging
from sqlalchemy import text, bindparam

app = FastAPI()
logger = logging.getLogger('rezzerv.api')
RECEIPT_STORAGE_ROOT = Path(os.getenv('RECEIPT_STORAGE_ROOT', '/app/data/receipts/raw'))

GMAIL_OAUTH_CLIENT_ID = os.getenv('REZZERV_GMAIL_CLIENT_ID', '').strip()
GMAIL_OAUTH_CLIENT_SECRET = os.getenv('REZZERV_GMAIL_CLIENT_SECRET', '').strip()
GMAIL_OAUTH_REDIRECT_URI = os.getenv('REZZERV_GMAIL_REDIRECT_URI', '').strip()
GMAIL_OAUTH_SCOPES = tuple(
    scope.strip()
    for scope in os.getenv(
        'REZZERV_GMAIL_SCOPES',
        'https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.labels',
    ).split()
    if scope.strip()
)
GMAIL_STATE_SECRET = (os.getenv('REZZERV_GMAIL_STATE_SECRET', 'rezzerv-gmail-dev-secret') or 'rezzerv-gmail-dev-secret').encode('utf-8')
GMAIL_DEFAULT_LABEL_NAME = os.getenv('REZZERV_GMAIL_LABEL_NAME', 'Rezzerv/Bonnen').strip() or 'Rezzerv/Bonnen'
GMAIL_SYNC_BATCH_SIZE = max(1, min(int(os.getenv('REZZERV_GMAIL_SYNC_BATCH_SIZE', '25') or '25'), 100))
RECEIPT_EMAIL_DOMAIN = (os.getenv('REZZERV_RECEIPT_EMAIL_DOMAIN', 'rezzerv.local') or 'rezzerv.local').strip() or 'rezzerv.local'
RESEND_API_KEY = (os.getenv('REZZERV_RESEND_API_KEY', '') or '').strip()
RESEND_API_BASE_URL = (os.getenv('REZZERV_RESEND_API_BASE_URL', 'https://api.resend.com') or 'https://api.resend.com').rstrip('/')
REZZERV_NOTIFICATION_FROM_EMAIL = (os.getenv('REZZERV_NOTIFICATION_FROM_EMAIL', '') or '').strip()
REZZERV_NOTIFICATION_FROM_NAME = (os.getenv('REZZERV_NOTIFICATION_FROM_NAME', 'Rezzerv') or 'Rezzerv').strip() or 'Rezzerv'
REZZERV_APP_BASE_URL = (os.getenv('REZZERV_APP_BASE_URL', 'http://localhost:5174') or 'http://localhost:5174').rstrip('/')
REZZERV_EMAIL_ENABLED = str(os.getenv('REZZERV_EMAIL_ENABLED', 'false') or 'false').strip().lower() in {'1', 'true', 'yes', 'on'}
RECEIPT_INBOUND_PATH = '/api/receipts/inbound'
VERSION_FILE_PATH = Path(__file__).resolve().parents[2] / 'VERSION.txt'
VERSION_TAG = VERSION_FILE_PATH.read_text(encoding='utf-8').strip() if VERSION_FILE_PATH.exists() else 'dev'
SUPPORTED_RECEIPT_ARCHIVE_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.webp', '.eml', '.html', '.htm', '.txt'}
ZIP_MIME_TYPES = {'application/zip', 'application/x-zip-compressed', 'multipart/x-zip', 'application/octet-stream'}
PRODUCT_SOURCE_ORDER = tuple(
    source.strip()
    for source in os.getenv('REZZERV_PRODUCT_SOURCE_ORDER', 'open_food_facts,public_reference_catalog,gs1_my_product_manager_share').split(',')
    if source.strip()
) or ('open_food_facts', 'public_reference_catalog')
PRODUCT_SOURCE_CONTINUE_ON_FAILURE = str(os.getenv('REZZERV_PRODUCT_SOURCE_CONTINUE_ON_FAILURE', 'true') or 'true').strip().lower() in {'1', 'true', 'yes', 'on'}
PUBLIC_PRODUCT_CATALOG_PATH = Path(__file__).resolve().parent / 'data' / 'public_product_catalog.json'

GS1_MY_PRODUCT_MANAGER_SHARE_BASE_URL = os.getenv('REZZERV_GS1_MPM_SHARE_BASE_URL', '').strip()
GS1_MY_PRODUCT_MANAGER_SHARE_API_KEY = os.getenv('REZZERV_GS1_MPM_SHARE_API_KEY', '').strip()



@app.exception_handler(Exception)
async def unhandled_api_exception_handler(request: Request, exc: Exception):
    if request.url.path.startswith('/api/'):
        logger.exception('Onverwerkte API-fout op %s', request.url.path)
        return JSONResponse(status_code=500, content={'detail': 'Interne serverfout in de API'})
    raise exc

def normalize_api_error_message(value: Any, fallback: str = 'Verzoek mislukt') -> str:
    if value is None:
        return fallback
    message = str(value).strip()
    return message or fallback


def mask_secret(value: Any, visible_suffix: int = 4) -> str:
    secret = str(value or '').strip()
    if not secret:
        return 'ontbreekt'
    if len(secret) <= visible_suffix:
        return '*' * len(secret)
    return ('*' * max(0, len(secret) - visible_suffix)) + secret[-visible_suffix:]


def outbound_email_delivery_enabled() -> bool:
    return bool(REZZERV_EMAIL_ENABLED)


def resend_api_key_ready() -> bool:
    key = str(RESEND_API_KEY or '').strip()
    return bool(key) and not key.upper().startswith('PASTE_')


def outbound_email_sender_ready() -> tuple[bool, str]:
    from_email = str(REZZERV_NOTIFICATION_FROM_EMAIL or '').strip().lower()
    if not from_email:
        return False, 'afzenderadres ontbreekt'
    if '@' not in from_email:
        return False, 'afzenderadres is ongeldig'
    if from_email.endswith('.local'):
        return False, 'afzenderadres gebruikt nog een .local-domein en is daarom niet bruikbaar voor Resend'
    return True, ''


def build_outbound_email_configuration_warnings() -> list[str]:
    warnings: list[str] = []
    from_email = str(REZZERV_NOTIFICATION_FROM_EMAIL or '').strip().lower()
    app_base_url = str(REZZERV_APP_BASE_URL or '').strip()
    if not from_email or '@' not in from_email:
        warnings.append('afzenderadres ontbreekt of is ongeldig')
    elif from_email.endswith('.local'):
        warnings.append('afzenderadres gebruikt nog een .local-domein en is meestal niet bruikbaar voor Resend')
    if app_base_url.startswith('http://localhost'):
        warnings.append('app-url verwijst nog naar localhost')
    return warnings


def build_outbound_email_configuration_summary() -> str:
    warnings = build_outbound_email_configuration_warnings()
    email_state = 'ingeschakeld' if outbound_email_delivery_enabled() else 'uitgeschakeld'
    key_state = 'aanwezig' if resend_api_key_ready() else 'ontbreekt of placeholder'
    summary_parts = [
        f'e-mail: {email_state}',
        f'API-sleutel: {key_state} ({mask_secret(RESEND_API_KEY)})',
        f"afzender: {REZZERV_NOTIFICATION_FROM_EMAIL or '(niet ingesteld)'}",
        f'api: {RESEND_API_BASE_URL}/emails',
        f'app-url: {REZZERV_APP_BASE_URL}/login',
    ]
    if warnings:
        summary_parts.append('waarschuwingen: ' + '; '.join(warnings))
    return 'Configuratie: ' + ' | '.join(summary_parts)


def build_resend_error_message(status_code: int, reason: Any, external_detail: Any = None, headers: Any = None) -> str:
    normalized_detail = normalize_api_error_message(external_detail, 'Onbekende fout vanuit Resend.')
    request_id = ''
    cf_ray = ''
    server_header = ''
    if headers is not None:
        try:
            request_id = str(headers.get('x-request-id') or headers.get('X-Request-Id') or '').strip()
        except Exception:
            request_id = ''
        try:
            cf_ray = str(headers.get('cf-ray') or headers.get('CF-RAY') or '').strip()
        except Exception:
            cf_ray = ''
        try:
            server_header = str(headers.get('server') or headers.get('Server') or '').strip()
        except Exception:
            server_header = ''
    reason_text = str(reason or "").strip()
    detail_parts = [
        'Uitnodigingsmail niet verzonden.',
        f'Resend antwoordde met HTTP {status_code} {reason_text}.' if reason_text else f'Resend antwoordde met HTTP {status_code}.',
        f'Externe melding: {normalized_detail}',
        build_outbound_email_configuration_summary(),
    ]
    if request_id:
        detail_parts.append(f'Resend request-id: {request_id}')
    if cf_ray:
        detail_parts.append(f'Cloudflare-ray: {cf_ray}')
    if server_header:
        detail_parts.append(f'Server: {server_header}')
    if "browser's signature" in normalized_detail.lower():
        detail_parts.append('Diagnosehint: Resend of een tussenliggende beveiligingslaag blokkeert dit verzoek als verdacht browser/signature-verkeer. Controleer of het afzenderadres een geverifieerd domein gebruikt, of de API-sleutel in de backend-container actief is, en of firewall, proxy, VPN, adblocker of browserbeveiliging verkeer naar api.resend.com wijzigt.')
    return ' '.join(part for part in detail_parts if part)

# Runtime opslag voor auth-context. De bron van waarheid wordt vanaf 01.09.96 uit SQLite geladen.
DEFAULT_AUTH_USERS = {
    "admin@rezzerv.local": {
        "password": "Rezzerv123",
        "role": "admin",
        "household_key": "default-household",
        "household_id": "1",
        "household_name": "Mijn huishouden",
    },
    "lid@rezzerv.local": {
        "password": "Rezzerv123",
        "role": "member",
        "household_key": "default-household",
        "household_id": "1",
        "household_name": "Mijn huishouden",
    },
}
households = {}
users = {email: dict(profile) for email, profile in DEFAULT_AUTH_USERS.items()}

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5180",
        "http://127.0.0.1:5180",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LoginRequest(BaseModel):
    email: str
    password: str


class HouseholdMemberCreateRequest(BaseModel):
    email: str
    password: Optional[str] = None
    role: str = "member"

    @field_validator("email")
    @classmethod
    def validate_email(cls, value):
        normalized = str(value or "").strip().lower()
        if not normalized or "@" not in normalized:
            raise ValueError("E-mailadres is verplicht")
        return normalized

    @field_validator("role")
    @classmethod
    def validate_role(cls, value):
        normalized = str(value or "member").strip().lower()
        if normalized in {"admin", "owner"}:
            return "owner"
        if normalized in {"lid", "member"}:
            return "member"
        if normalized in {"viewer", "gast", "read_only", "read-only"}:
            return "viewer"
        raise ValueError("Rol moet admin, lid of kijker zijn")


class HouseholdMemberUpdateRequest(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, value):
        normalized = str(value or "").strip().lower()
        if normalized in {"admin", "owner"}:
            return "owner"
        if normalized in {"lid", "member"}:
            return "member"
        if normalized in {"viewer", "gast", "read_only", "read-only"}:
            return "viewer"
        raise ValueError("Rol moet admin, lid of kijker zijn")


class HouseholdNameUpdateRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value):
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Huishoudnaam is verplicht")
        if len(normalized) > 120:
            raise ValueError("Huishoudnaam mag maximaal 120 tekens bevatten")
        return normalized


class HouseholdPermissionPolicyUpdateRequest(BaseModel):
    member_allowed: bool = False

class SpaceCreate(BaseModel):
    naam: str
    household_id: Optional[str] = None
    active: bool = True

    @field_validator("naam")
    @classmethod
    def validate_naam(cls, value):
        normalized = ' '.join(str(value or '').strip().split())
        if not normalized:
            raise ValueError("Ruimtenaam is verplicht")
        if len(normalized) > 120:
            raise ValueError("Ruimtenaam mag maximaal 120 tekens bevatten")
        return normalized

class SpaceUpdateRequest(BaseModel):
    naam: str
    active: bool = True

    @field_validator("naam")
    @classmethod
    def validate_naam(cls, value):
        normalized = ' '.join(str(value or '').strip().split())
        if not normalized:
            raise ValueError("Ruimtenaam is verplicht")
        if len(normalized) > 120:
            raise ValueError("Ruimtenaam mag maximaal 120 tekens bevatten")
        return normalized

class SublocationCreate(BaseModel):
    naam: str
    space_id: str
    active: bool = True

    @field_validator("naam")
    @classmethod
    def validate_naam(cls, value):
        normalized = ' '.join(str(value or '').strip().split())
        if not normalized:
            raise ValueError("Sublocatienaam is verplicht")
        if len(normalized) > 120:
            raise ValueError("Sublocatienaam mag maximaal 120 tekens bevatten")
        return normalized

class SublocationUpdateRequest(BaseModel):
    naam: str
    space_id: str
    active: bool = True

    @field_validator("naam")
    @classmethod
    def validate_naam(cls, value):
        normalized = ' '.join(str(value or '').strip().split())
        if not normalized:
            raise ValueError("Sublocatienaam is verplicht")
        if len(normalized) > 120:
            raise ValueError("Sublocatienaam mag maximaal 120 tekens bevatten")
        return normalized

class InventoryCreate(BaseModel):
    naam: str
    aantal: int
    space_id: str
    sublocation_id: Optional[str] = None


class InventoryUpdate(BaseModel):
    naam: str
    aantal: int
    space_id: Optional[str] = None
    sublocation_id: Optional[str] = None
    space_name: Optional[str] = None
    sublocation_name: Optional[str] = None


class ManualPurchaseCreateRequest(BaseModel):
    article_name: str
    quantity: int = 1
    household_id: Optional[str] = None
    space_id: Optional[str] = None
    sublocation_id: Optional[str] = None
    space_name: Optional[str] = None
    sublocation_name: Optional[str] = None
    purchase_date: Optional[str] = None
    supplier: Optional[str] = None
    article_number: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = "EUR"
    note: Optional[str] = None

    @field_validator("article_name")
    @classmethod
    def validate_article_name(cls, value):
        normalized = normalize_household_article_name(value)
        if not normalized:
            raise ValueError("Artikelnaam is verplicht")
        return normalized

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value):
        quantity = int(value or 0)
        if quantity <= 0:
            raise ValueError("Aantal moet groter zijn dan 0")
        return quantity

    @field_validator("purchase_date")
    @classmethod
    def validate_purchase_date(cls, value):
        return normalize_purchase_date(value)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value):
        normalized = str(value or "EUR").strip().upper()
        return normalized[:8] or "EUR"

    @field_validator("article_number")
    @classmethod
    def validate_article_number(cls, value):
        normalized = str(value or "").strip()
        return normalized[:128] or None


class InventoryEventMutationRequest(BaseModel):
    household_id: Optional[str] = None
    inventory_id: Optional[str] = None
    article_name: Optional[str] = None
    quantity: int
    event_type: str
    space_id: Optional[str] = None
    sublocation_id: Optional[str] = None
    space_name: Optional[str] = None
    sublocation_name: Optional[str] = None
    note: Optional[str] = None

    @field_validator("article_name")
    @classmethod
    def validate_article_name(cls, value):
        normalized = normalize_household_article_name(value)
        return normalized or None

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value):
        if value is None:
            raise ValueError("quantity is verplicht")
        return int(value)

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value):
        normalized = str(value or "").strip().lower()
        if normalized not in {"purchase", "consume", "adjustment"}:
            raise ValueError("event_type moet purchase, consume of adjustment zijn")
        return normalized


class InventoryTransferRequest(BaseModel):
    household_id: Optional[str] = None
    inventory_id: Optional[str] = None
    article_name: Optional[str] = None
    quantity: int
    from_space_id: Optional[str] = None
    from_sublocation_id: Optional[str] = None
    from_space_name: Optional[str] = None
    from_sublocation_name: Optional[str] = None
    to_space_id: Optional[str] = None
    to_sublocation_id: Optional[str] = None
    to_space_name: Optional[str] = None
    to_sublocation_name: Optional[str] = None
    note: Optional[str] = None

    @field_validator("article_name")
    @classmethod
    def validate_article_name(cls, value):
        normalized = normalize_household_article_name(value)
        return normalized or None

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value):
        quantity = int(value or 0)
        if quantity <= 0:
            raise ValueError("Aantal moet groter zijn dan 0")
        return quantity


class BarcodeLookupRequest(BaseModel):
    barcode: str
    household_id: Optional[str] = None

    @field_validator("barcode")
    @classmethod
    def validate_barcode(cls, value):
        return normalize_barcode_value(value)


class BarcodePurchaseCreateRequest(ManualPurchaseCreateRequest):
    barcode: str

    @field_validator("barcode")
    @classmethod
    def validate_barcode(cls, value):
        return normalize_barcode_value(value)


class ProductIdentifyRequest(BaseModel):
    article_name: str
    barcode: str
    household_id: Optional[str] = None

    @field_validator('article_name')
    @classmethod
    def validate_article_name(cls, value):
        normalized = normalize_household_article_name(value)
        if not normalized:
            raise ValueError('article_name is verplicht')
        return normalized

    @field_validator('barcode')
    @classmethod
    def validate_barcode(cls, value):
        return normalize_barcode_value(value)


class ProductEnrichRequest(BaseModel):
    article_name: str
    household_id: Optional[str] = None
    force_refresh: bool = False

    @field_validator('article_name')
    @classmethod
    def validate_article_name(cls, value):
        normalized = normalize_household_article_name(value)
        if not normalized:
            raise ValueError('article_name is verplicht')
        return normalized


class ArticleArchiveRequest(BaseModel):
    article_name: str
    reason: Optional[str] = None


class HouseholdArticleArchiveRequest(BaseModel):
    reason: Optional[str] = None


class HouseholdArticleDeleteRequest(BaseModel):
    reason: Optional[str] = None
    force: bool = False


class ArticleHouseholdDetailsUpdateRequest(BaseModel):
    custom_name: str | None = None
    article_type: str | None = None
    category: str | None = None
    brand_or_maker: str | None = None
    short_description: str | None = None
    notes: str | None = None
    min_stock: float | None = None
    ideal_stock: float | None = None
    favorite_store: str | None = None
    barcode: str | None = None
    article_number: str | None = None
    source: str | None = None

    @field_validator('custom_name', 'article_type', 'category', 'brand_or_maker', 'short_description', 'notes', 'favorite_store', mode='before')
    @classmethod
    def normalize_text_fields(cls, value):
        if value is None:
            return None
        return str(value).strip()


class HouseholdArticleSettingsUpdateRequest(BaseModel):
    min_stock: float | None = None
    ideal_stock: float | None = None
    favorite_store: str | None = None
    average_price: float | None = None
    status: str | None = None
    default_location_id: str | None = None
    default_sublocation_id: str | None = None
    auto_restock: bool | None = None
    packaging_unit: str | None = None
    packaging_quantity: float | None = None
    notes: str | None = None

    @field_validator('favorite_store', 'default_location_id', 'default_sublocation_id', 'packaging_unit', 'notes', mode='before')
    @classmethod
    def normalize_optional_text_fields(cls, value):
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator('status', mode='before')
    @classmethod
    def normalize_status(cls, value):
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if not normalized:
            return None
        allowed = {'active', 'inactive'}
        if normalized not in allowed:
            raise ValueError('status moet active of inactive zijn')
        return normalized


class ArticleExternalProductLinkUpdateRequest(BaseModel):
    barcode: str | None = None
    article_number: str | None = None

    @field_validator('barcode', mode='before')
    @classmethod
    def normalize_barcode_input(cls, value):
        if value in (None, ''):
            return None
        return normalize_barcode_value(value)

    @field_validator('article_number', mode='before')
    @classmethod
    def normalize_article_number_input(cls, value):
        if value is None:
            return None
        return str(value).strip() or None


class DiagnosticRequest(BaseModel):
    household_id: Optional[str] = None


class StoreConnectionCreate(BaseModel):
    household_id: str | int
    store_provider_code: str

    @field_validator("household_id", mode="before")
    @classmethod
    def normalize_household_id(cls, value):
        if value is None:
            raise ValueError("household_id is verplicht")
        return str(value)



class PullPurchasesRequest(BaseModel):
    mock_profile: str = "default"



class ReviewLineRequest(BaseModel):
    review_decision: str

    @field_validator("review_decision")
    @classmethod
    def validate_review_decision(cls, value):
        allowed = {"pending", "selected", "ignored"}
        if value not in allowed:
            raise ValueError("Ongeldige reviewbeslissing")
        return value


class MapLineRequest(BaseModel):
    household_article_id: Optional[str | int] = None

    @field_validator("household_article_id", mode="before")
    @classmethod
    def normalize_article_id(cls, value):
        if value is None or str(value).strip() == "":
            return None
        return str(value)


class TargetLocationRequest(BaseModel):
    target_location_id: Optional[str] = None

    @field_validator("target_location_id", mode="before")
    @classmethod
    def normalize_target_location_id(cls, value):
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


class CreateArticleFromLineRequest(BaseModel):
    article_name: str

    @field_validator("article_name")
    @classmethod
    def validate_article_name(cls, value):
        normalized = normalize_household_article_name(value)
        if not normalized:
            raise ValueError("Artikelnaam is verplicht")
        return normalized



class ProcessBatchRequest(BaseModel):
    processed_by: str = "ui"
    mode: str = "selected_only"
    auto_consume_article_ids: List[str] = Field(default_factory=list)

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value):
        if value not in {"selected_only", "ready_only"}:
            raise ValueError("Alleen selected_only of ready_only wordt ondersteund")
        return value


class ReceiptSourceScanRequest(BaseModel):
    source_id: str


class ReceiptSourceCreateRequest(BaseModel):
    household_id: str
    type: str
    label: Optional[str] = None
    source_path: Optional[str] = None
    store_name: Optional[str] = None
    account_label: Optional[str] = None
    external_reference: Optional[str] = None
    is_active: bool = True


class ReceiptDeleteRequest(BaseModel):
    receipt_table_ids: List[str] = Field(default_factory=list)


class ReceiptHeaderUpdateRequest(BaseModel):
    store_name: Optional[str] = None
    purchase_at: Optional[str] = None
    total_amount: Optional[float] = None
    reference: Optional[str] = None
    notes: Optional[str] = None


class ReceiptLineUpdateRequest(BaseModel):
    article_name: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    line_total: Optional[float] = None
    matched_article_id: Optional[str] = None
    is_validated: Optional[bool] = None
    is_deleted: Optional[bool] = None


class ReceiptLineCreateRequest(BaseModel):
    article_name: str
    quantity: Optional[float] = 1.0
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    line_total: Optional[float] = None
    matched_article_id: Optional[str] = None
    is_validated: bool = True

    @field_validator('article_name')
    @classmethod
    def validate_article_name(cls, value):
        normalized = ' '.join(str(value or '').strip().split())
        if not normalized:
            raise ValueError('Artikelnaam is verplicht')
        if len(normalized) > 180:
            raise ValueError('Artikelnaam mag maximaal 180 tekens bevatten')
        return normalized


STORE_PROVIDER_DEFINITIONS = {
    "lidl": {
        "name": "Lidl",
        "status": "active",
        "import_mode": "mock",
    },
    "jumbo": {
        "name": "Jumbo",
        "status": "active",
        "import_mode": "mock",
    },
}


MOCK_PURCHASES_BY_PROVIDER = {
    "lidl": {
        "default": [
            {
                "external_line_ref": "lidl-line-1",
                "external_article_code": "LIDL-1001",
                "article_name_raw": "Halfvolle melk",
                "brand_raw": "Lidl",
                "quantity_raw": 1,
                "unit_raw": "liter",
                "line_price_raw": 1.29,
                "currency_code": "EUR",
            },
            {
                "external_line_ref": "lidl-line-2",
                "external_article_code": "LIDL-2001",
                "article_name_raw": "Banaan",
                "brand_raw": "Lidl",
                "quantity_raw": 1,
                "unit_raw": "kg",
                "line_price_raw": 1.89,
                "currency_code": "EUR",
            },
            {
                "external_line_ref": "lidl-line-3",
                "external_article_code": "LIDL-3001",
                "article_name_raw": "Volkoren pasta",
                "brand_raw": "Lidl",
                "quantity_raw": 500,
                "unit_raw": "g",
                "line_price_raw": 0.99,
                "currency_code": "EUR",
            },
            {
                "external_line_ref": "lidl-line-4",
                "external_article_code": "LIDL-4001",
                "article_name_raw": "Tomatenblokjes",
                "brand_raw": "Lidl",
                "quantity_raw": 2,
                "unit_raw": "stuks",
                "line_price_raw": 1.18,
                "currency_code": "EUR",
            },
        ]
    },
    "jumbo": {
        "default": [
            {
                "external_line_ref": "jumbo-line-1",
                "external_article_code": "JUMBO-1001",
                "article_name_raw": "Magere yoghurt",
                "brand_raw": "Jumbo",
                "quantity_raw": 1,
                "unit_raw": "liter",
                "line_price_raw": 1.59,
                "currency_code": "EUR",
            },
            {
                "external_line_ref": "jumbo-line-2",
                "external_article_code": "JUMBO-2001",
                "article_name_raw": "Appelsap",
                "brand_raw": "Jumbo",
                "quantity_raw": 1,
                "unit_raw": "liter",
                "line_price_raw": 1.99,
                "currency_code": "EUR",
            },
            {
                "external_line_ref": "jumbo-line-3",
                "external_article_code": "JUMBO-3001",
                "article_name_raw": "Pindakaas",
                "brand_raw": "Calvé",
                "quantity_raw": 1,
                "unit_raw": "pot",
                "line_price_raw": 3.49,
                "currency_code": "EUR",
            },
            {
                "external_line_ref": "jumbo-line-4",
                "external_article_code": "JUMBO-4001",
                "article_name_raw": "Tomaten",
                "brand_raw": "Jumbo",
                "quantity_raw": 6,
                "unit_raw": "stuks",
                "line_price_raw": 2.19,
                "currency_code": "EUR",
            },
        ]
    },
}


MOCK_BATCH_METADATA_BY_PROVIDER = {
    "lidl": {
        "default": {
            "purchase_date": "10-03-2026",
            "store_name": "Lidl",
            "store_label": "Lidl, Hoofdstraat 12, Utrecht",
        }
    },
    "jumbo": {
        "default": {
            "purchase_date": "10-03-2026",
            "store_name": "Jumbo",
            "store_label": "Jumbo, Marktplein 8, Utrecht",
        }
    },
}


MOCK_ARTICLE_OPTIONS = [
    {"id": "1", "name": "Tomaten", "brand": "Mutti", "consumable": True},
    {"id": "2", "name": "Spaghetti", "brand": "Barilla", "consumable": True},
    {"id": "3", "name": "Koffie", "brand": "Douwe Egberts", "consumable": True},
    {"id": "4", "name": "Melk", "brand": "Campina", "consumable": True},
    {"id": "5", "name": "Banaan", "brand": "Huismerk", "consumable": True},
    {"id": "6", "name": "Volkoren pasta", "brand": "Barilla", "consumable": True},
]

KNOWN_CONSUMABLE_ARTICLE_NAMES = {
    "tomaten",
    "spaghetti",
    "koffie",
    "melk",
    "banaan",
    "volkoren pasta",
    "mosterd",
    "halfvolle melk",
    "appelsap",
    "pindakaas",
    "tomatenblokjes",
    "pasta",
}


MOCK_ARTICLE_LOOKUP = {item["id"]: item for item in MOCK_ARTICLE_OPTIONS}


STORE_IMPORT_SIMPLIFICATION_KEY = "store_import_simplification_level"
STORE_IMPORT_SIMPLIFICATION_ALLOWED = {"voorzichtig", "gebalanceerd", "maximaal_gemak"}
STORE_IMPORT_SIMPLIFICATION_DEFAULT = "gebalanceerd"
HOUSEHOLD_AUTO_CONSUME_KEY = "consumable_auto_deduction_mode"
HOUSEHOLD_AUTO_CONSUME_LEGACY_KEY = "auto_consume_on_repurchase"
ARTICLE_AUTO_CONSUME_OVERRIDES_KEY = "article_auto_consume_overrides"
ARTICLE_AUTO_CONSUME_FOLLOW_HOUSEHOLD = "follow_household"
ARTICLE_AUTO_CONSUME_NONE = "none"
ARTICLE_AUTO_CONSUME_PURCHASED_QUANTITY = "consume_purchased_quantity"
ARTICLE_AUTO_CONSUME_ALL_EXISTING = "consume_all_existing_before_purchase"
ARTICLE_AUTO_CONSUME_ALWAYS_ON = "always_on"
ARTICLE_AUTO_CONSUME_ALWAYS_OFF = "always_off"
ARTICLE_AUTO_CONSUME_ALLOWED = {ARTICLE_AUTO_CONSUME_FOLLOW_HOUSEHOLD, ARTICLE_AUTO_CONSUME_NONE, ARTICLE_AUTO_CONSUME_PURCHASED_QUANTITY, ARTICLE_AUTO_CONSUME_ALL_EXISTING, ARTICLE_AUTO_CONSUME_ALWAYS_ON, ARTICLE_AUTO_CONSUME_ALWAYS_OFF}
HOUSEHOLD_AUTO_CONSUME_ALLOWED = {ARTICLE_AUTO_CONSUME_NONE, ARTICLE_AUTO_CONSUME_PURCHASED_QUANTITY, ARTICLE_AUTO_CONSUME_ALL_EXISTING}
ARTICLE_FIELD_VISIBILITY_KEY = "article_field_visibility"
ARTICLE_FIELD_VISIBILITY_DEFAULT = {
    "overview": {},
    "stock": {},
    "locations": {},
    "history": {},
    "analytics": {},
}
ALMOST_OUT_PREDICTION_ENABLED_KEY = "almost_out_prediction_enabled"
ALMOST_OUT_PREDICTION_DAYS_KEY = "almost_out_prediction_days"
ALMOST_OUT_POLICY_MODE_KEY = "almost_out_policy_mode"
ALMOST_OUT_POLICY_ADVISORY = "advisory"
ALMOST_OUT_POLICY_OVERRIDE = "override"
ALMOST_OUT_POLICY_ALLOWED = {ALMOST_OUT_POLICY_ADVISORY, ALMOST_OUT_POLICY_OVERRIDE}
ALMOST_OUT_PREDICTION_DEFAULT_DAYS = 0

USER_PRIVACY_SETTINGS_KEY = "privacy_data_sharing"
USER_PRIVACY_SETTINGS_DEFAULT = {
    "share_with_retailers": False,
    "share_with_partners": False,
    "allow_smart_features": False,
    "allow_statistics": False,
    "allow_personal_offers": False,
    "allow_loyalty_import": False,
}
PERMISSION_ARTICLE_CREATE = "article.create"
PERMISSION_ARTICLE_UPDATE = "article.update"
SUPPORTED_HOUSEHOLD_PERMISSION_KEYS = {PERMISSION_ARTICLE_CREATE, PERMISSION_ARTICLE_UPDATE}
ROLE_PERMISSION_DEFAULTS = {
    "admin": {PERMISSION_ARTICLE_CREATE: True, PERMISSION_ARTICLE_UPDATE: True},
    "lid": {PERMISSION_ARTICLE_CREATE: False, PERMISSION_ARTICLE_UPDATE: False},
    "viewer": {PERMISSION_ARTICLE_CREATE: False, PERMISSION_ARTICLE_UPDATE: False},
}
HOUSEHOLD_MEMBER_PERMISSION_DEFAULTS = {
    PERMISSION_ARTICLE_CREATE: False,
    PERMISSION_ARTICLE_UPDATE: False,
}


def ensure_household_settings_schema():
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS household_settings (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                setting_key TEXT NOT NULL,
                setting_value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        ))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_household_settings_unique ON household_settings (household_id, setting_key)"
        ))


def ensure_user_settings_schema():
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                id TEXT PRIMARY KEY,
                user_email TEXT NOT NULL,
                setting_key TEXT NOT NULL,
                setting_value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        ))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_settings_unique ON user_settings (user_email, setting_key)"
        ))


def ensure_household_permission_policies_schema():
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS household_permission_policies (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                permission_key TEXT NOT NULL,
                member_allowed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(household_id, permission_key)
            )
            """
        ))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_household_permission_policies_unique ON household_permission_policies (household_id, permission_key)"
        ))


def ensure_household_role_change_audit_schema():
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS household_role_change_audit (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                changed_user_email TEXT NOT NULL,
                old_role TEXT,
                new_role TEXT,
                changed_by_user_email TEXT NOT NULL,
                action_type TEXT NOT NULL DEFAULT 'role_changed',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_household_role_change_audit_household_created ON household_role_change_audit (household_id, created_at DESC)"
        ))


def log_household_role_change(conn, household_id: str, changed_user_email: str, old_role: str | None, new_role: str | None, changed_by_user_email: str, action_type: str = 'role_changed') -> None:
    conn.execute(
        text(
            """
            INSERT INTO household_role_change_audit (
                id, household_id, changed_user_email, old_role, new_role, changed_by_user_email, action_type, created_at
            ) VALUES (
                :id, :household_id, :changed_user_email, :old_role, :new_role, :changed_by_user_email, :action_type, CURRENT_TIMESTAMP
            )
            """
        ),
        {
            'id': str(uuid.uuid4()),
            'household_id': str(household_id),
            'changed_user_email': str(changed_user_email or '').strip().lower(),
            'old_role': str(old_role or '').strip().lower() or None,
            'new_role': str(new_role or '').strip().lower() or None,
            'changed_by_user_email': str(changed_by_user_email or '').strip().lower(),
            'action_type': str(action_type or 'role_changed').strip().lower() or 'role_changed',
        },
    )


def list_household_role_change_audit(conn, household_id: str, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        text(
            """
            SELECT changed_user_email, old_role, new_role, changed_by_user_email, action_type, created_at
            FROM household_role_change_audit
            WHERE household_id = :household_id
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT :limit
            """
        ).bindparams(bindparam('limit', type_=None)),
        {'household_id': str(household_id), 'limit': int(max(1, min(limit, 50)))},
    ).mappings().all()
    return [
        {
            'changed_user_email': str(row.get('changed_user_email') or '').strip().lower(),
            'old_role': map_membership_role_to_display_role(row.get('old_role')) if row.get('old_role') else '',
            'new_role': map_membership_role_to_display_role(row.get('new_role')) if row.get('new_role') else '',
            'changed_by_user_email': str(row.get('changed_by_user_email') or '').strip().lower(),
            'action_type': str(row.get('action_type') or '').strip().lower(),
            'created_at': row.get('created_at'),
        }
        for row in rows
    ]


def normalize_permission_key(value: str | None) -> str:
    normalized = str(value or '').strip()
    if normalized not in SUPPORTED_HOUSEHOLD_PERMISSION_KEYS:
        raise HTTPException(status_code=400, detail='Onbekende permissie-instelling')
    return normalized


def get_household_member_permission_policies(conn, household_id: str) -> dict:
    policies = dict(HOUSEHOLD_MEMBER_PERMISSION_DEFAULTS)
    rows = conn.execute(
        text(
            """
            SELECT permission_key, member_allowed
            FROM household_permission_policies
            WHERE household_id = :household_id
            """
        ),
        {'household_id': str(household_id)},
    ).mappings().all()
    for row in rows:
        permission_key = str(row.get('permission_key') or '').strip()
        if permission_key not in SUPPORTED_HOUSEHOLD_PERMISSION_KEYS:
            continue
        policies[permission_key] = bool(row.get('member_allowed'))
    return policies


def set_household_member_permission_policy(conn, household_id: str, permission_key: str, member_allowed: bool) -> dict:
    normalized_permission_key = normalize_permission_key(permission_key)
    normalized_household_id = str(household_id)
    normalized_allowed = 1 if bool(member_allowed) else 0
    conn.execute(
        text(
            """
            INSERT INTO household_permission_policies (id, household_id, permission_key, member_allowed, created_at, updated_at)
            VALUES (:id, :household_id, :permission_key, :member_allowed, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(household_id, permission_key) DO UPDATE SET
                member_allowed = excluded.member_allowed,
                updated_at = CURRENT_TIMESTAMP
            """
        ),
        {
            'id': str(uuid.uuid4()),
            'household_id': normalized_household_id,
            'permission_key': normalized_permission_key,
            'member_allowed': normalized_allowed,
        },
    )
    return get_household_member_permission_policies(conn, normalized_household_id)


def get_effective_permissions_for_context(conn, context: dict) -> dict:
    display_role = str(context.get('display_role') or '').strip().lower()
    defaults = ROLE_PERMISSION_DEFAULTS.get(display_role, {})
    permissions = {key: bool(defaults.get(key, False)) for key in SUPPORTED_HOUSEHOLD_PERMISSION_KEYS}
    if display_role == 'admin':
        return permissions
    policies = get_household_member_permission_policies(conn, str(context.get('active_household_id') or ''))
    for permission_key, member_allowed in policies.items():
        if permission_key in SUPPORTED_HOUSEHOLD_PERMISSION_KEYS:
            permissions[permission_key] = bool(member_allowed)
    return permissions


def build_capabilities_payload(conn, context: dict) -> dict:
    effective_permissions = get_effective_permissions_for_context(conn, context)
    member_permission_policies = get_household_member_permission_policies(conn, str(context.get('active_household_id') or ''))
    display_role = str(context.get('display_role') or '').strip().lower() or 'lid'
    return {
        'role': display_role,
        'household_id': str(context.get('active_household_id') or ''),
        'permissions': effective_permissions,
        'member_permission_policies': member_permission_policies,
        'supported_permissions': sorted(SUPPORTED_HOUSEHOLD_PERMISSION_KEYS),
        'can_manage_member_permissions': display_role == 'admin',
        'can_manage_members': display_role == 'admin',
        'is_viewer': display_role == 'viewer',
    }


def require_household_permission(conn, context: dict, permission_key: str):
    normalized_permission_key = normalize_permission_key(permission_key)
    permissions = get_effective_permissions_for_context(conn, context)
    if not bool(permissions.get(normalized_permission_key)):
        raise HTTPException(status_code=403, detail='Je hebt geen toegang tot deze actie binnen dit huishouden')
    return permissions


def ensure_household_articles_schema():
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS household_articles (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                naam TEXT NOT NULL,
                consumable INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT
            )
            """
        ))
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(household_articles)")).fetchall()}
        if "consumable" not in columns:
            conn.execute(text("ALTER TABLE household_articles ADD COLUMN consumable INTEGER"))
        if "barcode" not in columns:
            conn.execute(text("ALTER TABLE household_articles ADD COLUMN barcode TEXT"))
        if "article_number" not in columns:
            conn.execute(text("ALTER TABLE household_articles ADD COLUMN article_number TEXT"))
        if "external_source" not in columns:
            conn.execute(text("ALTER TABLE household_articles ADD COLUMN external_source TEXT"))
        if "custom_name" not in columns:
            conn.execute(text("ALTER TABLE household_articles ADD COLUMN custom_name TEXT"))
        if "article_type" not in columns:
            conn.execute(text("ALTER TABLE household_articles ADD COLUMN article_type TEXT"))
        if "category" not in columns:
            conn.execute(text("ALTER TABLE household_articles ADD COLUMN category TEXT"))
        if "brand_or_maker" not in columns:
            conn.execute(text("ALTER TABLE household_articles ADD COLUMN brand_or_maker TEXT"))
        if "short_description" not in columns:
            conn.execute(text("ALTER TABLE household_articles ADD COLUMN short_description TEXT"))
        if "notes" not in columns:
            conn.execute(text("ALTER TABLE household_articles ADD COLUMN notes TEXT"))
        if "min_stock" not in columns:
            conn.execute(text("ALTER TABLE household_articles ADD COLUMN min_stock NUMERIC"))
        if "ideal_stock" not in columns:
            conn.execute(text("ALTER TABLE household_articles ADD COLUMN ideal_stock NUMERIC"))
        if "favorite_store" not in columns:
            conn.execute(text("ALTER TABLE household_articles ADD COLUMN favorite_store TEXT"))
        if 'source' not in columns:
            conn.execute(text("ALTER TABLE household_articles ADD COLUMN source TEXT"))
        if 'global_product_id' not in columns:
            conn.execute(text("ALTER TABLE household_articles ADD COLUMN global_product_id TEXT"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_household_articles_household_name ON household_articles (household_id, naam)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_household_articles_household_barcode ON household_articles (household_id, barcode)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_household_articles_household_article_number ON household_articles (household_id, article_number)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_household_articles_global_product ON household_articles (global_product_id)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_household_articles_household_global_product ON household_articles (household_id, global_product_id) WHERE global_product_id IS NOT NULL AND trim(global_product_id) <> ''"))


def ensure_product_enrichment_schema():
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS product_identities (
                id TEXT PRIMARY KEY,
                household_article_id TEXT NOT NULL,
                identity_type TEXT NOT NULL,
                identity_value TEXT NOT NULL,
                source TEXT NOT NULL,
                confidence_score NUMERIC NOT NULL DEFAULT 1.0,
                is_primary INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS product_enrichments (
                id TEXT PRIMARY KEY,
                household_article_id TEXT NOT NULL,
                source_name TEXT NOT NULL,
                source_record_id TEXT,
                title TEXT,
                brand TEXT,
                category TEXT,
                size_value NUMERIC,
                size_unit TEXT,
                ingredients_json TEXT,
                allergens_json TEXT,
                nutrition_json TEXT,
                image_url TEXT,
                source_url TEXT,
                quality_score NUMERIC,
                fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT,
                raw_payload_json TEXT,
                lookup_status TEXT,
                last_lookup_at TEXT,
                last_lookup_source TEXT,
                last_lookup_message TEXT,
                normalized_barcode TEXT
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS product_enrichment_audit (
                id TEXT PRIMARY KEY,
                household_article_id TEXT,
                source_name TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT,
                payload_hash TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                normalized_barcode TEXT,
                source_request_key TEXT,
                http_status INTEGER,
                response_excerpt TEXT
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS product_enrichment_attempts (
                id TEXT PRIMARY KEY,
                global_product_id TEXT,
                household_article_id TEXT,
                source_name TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                normalized_barcode TEXT,
                source_request_key TEXT,
                http_status INTEGER,
                response_excerpt TEXT,
                message TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        ))
        enrichment_columns = {row['name'] for row in conn.execute(text("PRAGMA table_info(product_enrichments)")).mappings().all()}
        if 'lookup_status' not in enrichment_columns:
            conn.execute(text("ALTER TABLE product_enrichments ADD COLUMN lookup_status TEXT"))
        if 'last_lookup_at' not in enrichment_columns:
            conn.execute(text("ALTER TABLE product_enrichments ADD COLUMN last_lookup_at TEXT"))
        if 'last_lookup_source' not in enrichment_columns:
            conn.execute(text("ALTER TABLE product_enrichments ADD COLUMN last_lookup_source TEXT"))
        if 'last_lookup_message' not in enrichment_columns:
            conn.execute(text("ALTER TABLE product_enrichments ADD COLUMN last_lookup_message TEXT"))
        if 'normalized_barcode' not in enrichment_columns:
            conn.execute(text("ALTER TABLE product_enrichments ADD COLUMN normalized_barcode TEXT"))
        audit_columns = {row['name'] for row in conn.execute(text("PRAGMA table_info(product_enrichment_audit)")).mappings().all()}
        if 'normalized_barcode' not in audit_columns:
            conn.execute(text("ALTER TABLE product_enrichment_audit ADD COLUMN normalized_barcode TEXT"))
        if 'source_request_key' not in audit_columns:
            conn.execute(text("ALTER TABLE product_enrichment_audit ADD COLUMN source_request_key TEXT"))
        if 'http_status' not in audit_columns:
            conn.execute(text("ALTER TABLE product_enrichment_audit ADD COLUMN http_status INTEGER"))
        if 'response_excerpt' not in audit_columns:
            conn.execute(text("ALTER TABLE product_enrichment_audit ADD COLUMN response_excerpt TEXT"))
        attempt_columns = {row['name'] for row in conn.execute(text("PRAGMA table_info(product_enrichment_attempts)")).mappings().all()}
        if 'global_product_id' not in attempt_columns:
            conn.execute(text("ALTER TABLE product_enrichment_attempts ADD COLUMN global_product_id TEXT"))
        if 'household_article_id' not in attempt_columns:
            conn.execute(text("ALTER TABLE product_enrichment_attempts ADD COLUMN household_article_id TEXT"))
        if 'normalized_barcode' not in attempt_columns:
            conn.execute(text("ALTER TABLE product_enrichment_attempts ADD COLUMN normalized_barcode TEXT"))
        if 'source_request_key' not in attempt_columns:
            conn.execute(text("ALTER TABLE product_enrichment_attempts ADD COLUMN source_request_key TEXT"))
        if 'http_status' not in attempt_columns:
            conn.execute(text("ALTER TABLE product_enrichment_attempts ADD COLUMN http_status INTEGER"))
        if 'response_excerpt' not in attempt_columns:
            conn.execute(text("ALTER TABLE product_enrichment_attempts ADD COLUMN response_excerpt TEXT"))
        if 'message' not in attempt_columns:
            conn.execute(text("ALTER TABLE product_enrichment_attempts ADD COLUMN message TEXT"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_product_identities_unique_value ON product_identities (identity_type, identity_value)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_product_identities_article ON product_identities (household_article_id, is_primary)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_product_enrichments_unique_source ON product_enrichments (household_article_id, source_name)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_product_enrichments_article ON product_enrichments (household_article_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_product_enrichments_lookup_status ON product_enrichments (lookup_status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_product_enrichment_audit_article ON product_enrichment_audit (household_article_id, created_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_product_enrichment_attempts_global_product ON product_enrichment_attempts (global_product_id, created_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_product_enrichment_attempts_article ON product_enrichment_attempts (household_article_id, created_at)"))




def get_table_columns(conn, table_name: str) -> set[str]:
    return {row['name'] for row in conn.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()}


def ensure_table_column(conn, table_name: str, column_name: str, column_sql: str):
    columns = get_table_columns(conn, table_name)
    if column_name not in columns:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"))
    return get_table_columns(conn, table_name)


def safe_update_product_enrichment_row(conn, row_id: str, global_product_id: str | None, household_article_id: str | None = None):
    normalized_row_id = str(row_id or '').strip()
    normalized_global_product_id = str(global_product_id or '').strip()
    normalized_household_article_id = str(household_article_id or '').strip() or None
    if not normalized_row_id or not normalized_global_product_id:
        return
    columns = get_table_columns(conn, 'product_enrichments')
    row = conn.execute(text("SELECT id, source_name FROM product_enrichments WHERE id = :id LIMIT 1"), {'id': normalized_row_id}).mappings().first()
    if not row:
        return
    source_name = str(row.get('source_name') or '').strip()
    duplicate = conn.execute(text(
        """
        SELECT id
        FROM product_enrichments
        WHERE global_product_id = :global_product_id
          AND source_name = :source_name
          AND id <> :row_id
        ORDER BY datetime(COALESCE(last_lookup_at, fetched_at, '1970-01-01')) DESC, id DESC
        LIMIT 1
        """
    ), {
        'global_product_id': normalized_global_product_id,
        'source_name': source_name,
        'row_id': normalized_row_id,
    }).mappings().first()
    if duplicate:
        conn.execute(text("DELETE FROM product_enrichments WHERE id = :id"), {'id': normalized_row_id})
        return
    set_parts = ["global_product_id = :global_product_id"]
    params = {'row_id': normalized_row_id, 'global_product_id': normalized_global_product_id}
    if normalized_household_article_id and 'household_article_id' in columns:
        set_parts.append("household_article_id = COALESCE(:household_article_id, household_article_id)")
        params['household_article_id'] = normalized_household_article_id
    if 'updated_at' in columns:
        set_parts.append("updated_at = CURRENT_TIMESTAMP")
    conn.execute(text(f"UPDATE product_enrichments SET {', '.join(set_parts)} WHERE id = :row_id"), params)


def dedupe_product_enrichments_for_global_product(conn, global_product_id: str):
    normalized_global_product_id = str(global_product_id or '').strip()
    if not normalized_global_product_id:
        return
    duplicates = conn.execute(text(
        """
        SELECT source_name, GROUP_CONCAT(id) AS ids
        FROM product_enrichments
        WHERE global_product_id = :global_product_id
          AND COALESCE(trim(global_product_id), '') <> ''
        GROUP BY source_name
        HAVING COUNT(*) > 1
        """
    ), {'global_product_id': normalized_global_product_id}).mappings().all()
    for duplicate in duplicates:
        ids = [value for value in str(duplicate.get('ids') or '').split(',') if value]
        if len(ids) <= 1:
            continue
        keep_id = conn.execute(text(
            """
            SELECT id
            FROM product_enrichments
            WHERE id IN :ids
            ORDER BY datetime(COALESCE(last_lookup_at, fetched_at, '1970-01-01')) DESC,
                     CASE WHEN COALESCE(lookup_status, '') = 'found' THEN 0 ELSE 1 END ASC,
                     id DESC
            LIMIT 1
            """
        ).bindparams(bindparam('ids', expanding=True)), {'ids': ids}).scalar()
        for drop_id in ids:
            if drop_id != keep_id:
                conn.execute(text("DELETE FROM product_enrichments WHERE id = :id"), {'id': drop_id})


def ensure_global_product_catalog_schema():
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS global_products (
                id TEXT PRIMARY KEY,
                primary_gtin TEXT,
                name TEXT NOT NULL,
                brand TEXT,
                variant TEXT,
                category TEXT,
                size_value NUMERIC,
                size_unit TEXT,
                source TEXT NOT NULL DEFAULT 'user',
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT
            )
            """
        ))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_global_products_primary_gtin ON global_products (primary_gtin) WHERE primary_gtin IS NOT NULL AND trim(primary_gtin) <> ''"))
        product_identity_columns = ensure_table_column(conn, 'product_identities', 'global_product_id', 'TEXT')
        enrichment_columns = ensure_table_column(conn, 'product_enrichments', 'global_product_id', 'TEXT')
        if 'updated_at' not in enrichment_columns:
            enrichment_columns = ensure_table_column(conn, 'product_enrichments', 'updated_at', 'TEXT')
        audit_columns = ensure_table_column(conn, 'product_enrichment_audit', 'global_product_id', 'TEXT')
        attempt_columns = ensure_table_column(conn, 'product_enrichment_attempts', 'global_product_id', 'TEXT')
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_product_identities_global_product ON product_identities (global_product_id, is_primary)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_product_enrichments_global_product ON product_enrichments (global_product_id, source_name)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_product_enrichment_audit_global_product ON product_enrichment_audit (global_product_id, created_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_product_enrichment_attempts_global_product ON product_enrichment_attempts (global_product_id, created_at)"))

        article_rows = conn.execute(text(
            """
            SELECT id, household_id, naam, barcode, brand_or_maker, category
            FROM household_articles
            WHERE COALESCE(trim(barcode), '') <> ''
            """
        )).mappings().all()
        for row in article_rows:
            normalized_barcode = normalize_barcode_value(row.get('barcode'))
            if not normalized_barcode:
                continue
            article_id = str(row.get('id'))
            global_product_id = ensure_global_product_record(
                conn,
                normalized_barcode,
                row.get('naam'),
                source='receipt',
                brand=row.get('brand_or_maker'),
                category=row.get('category'),
            )
            set_household_article_global_product_id(conn, article_id, global_product_id)
            conn.execute(text(
                """
                UPDATE product_identities
                SET global_product_id = :global_product_id
                WHERE household_article_id = :household_article_id
                  AND identity_type = 'gtin'
                  AND identity_value = :identity_value
                """
            ), {
                'global_product_id': global_product_id,
                'household_article_id': article_id,
                'identity_value': normalized_barcode,
            })
            enrichment_ids = conn.execute(text(
                """
                SELECT id
                FROM product_enrichments
                WHERE household_article_id = :household_article_id
                  AND COALESCE(normalized_barcode, '') = :identity_value
                ORDER BY datetime(COALESCE(last_lookup_at, fetched_at, '1970-01-01')) DESC, id DESC
                """
            ), {
                'household_article_id': article_id,
                'identity_value': normalized_barcode,
            }).scalars().all()
            for enrichment_id in enrichment_ids:
                safe_update_product_enrichment_row(conn, str(enrichment_id), global_product_id, article_id)
            conn.execute(text(
                """
                UPDATE product_enrichment_audit
                SET global_product_id = :global_product_id
                WHERE household_article_id = :household_article_id
                  AND COALESCE(normalized_barcode, '') = :identity_value
                """
            ), {
                'global_product_id': global_product_id,
                'household_article_id': article_id,
                'identity_value': normalized_barcode,
            })
            conn.execute(text(
                """
                UPDATE product_enrichment_attempts
                SET global_product_id = :global_product_id
                WHERE household_article_id = :household_article_id
                  AND COALESCE(normalized_barcode, '') = :identity_value
                """
            ), {
                'global_product_id': global_product_id,
                'household_article_id': article_id,
                'identity_value': normalized_barcode,
            })
            dedupe_product_enrichments_for_global_product(conn, global_product_id)

        enrichment_rows = conn.execute(text(
            """
            SELECT id, household_article_id, normalized_barcode, title, brand, category, size_value, size_unit, source_name
            FROM product_enrichments
            WHERE COALESCE(trim(normalized_barcode), '') <> ''
            ORDER BY datetime(COALESCE(fetched_at, '1970-01-01')) ASC, id ASC
            """
        )).mappings().all()
        for row in enrichment_rows:
            normalized_barcode = normalize_barcode_value(row.get('normalized_barcode'))
            if not normalized_barcode:
                continue
            global_product_id = ensure_global_product_record(
                conn,
                normalized_barcode,
                row.get('title') or f'Product {normalized_barcode}',
                source=row.get('source_name') or 'user',
                brand=row.get('brand'),
                category=row.get('category'),
                size_value=row.get('size_value'),
                size_unit=row.get('size_unit'),
            )
            safe_update_product_enrichment_row(conn, str(row.get('id')), global_product_id, row.get('household_article_id'))
            conn.execute(text(
                """
                UPDATE product_enrichment_audit
                SET global_product_id = :global_product_id
                WHERE household_article_id = :household_article_id
                  AND COALESCE(normalized_barcode, '') = :normalized_barcode
                """
            ), {
                'global_product_id': global_product_id,
                'household_article_id': str(row.get('household_article_id')),
                'normalized_barcode': normalized_barcode,
            })
            conn.execute(text(
                """
                UPDATE product_enrichment_attempts
                SET global_product_id = :global_product_id
                WHERE household_article_id = :household_article_id
                  AND COALESCE(normalized_barcode, '') = :normalized_barcode
                """
            ), {
                'global_product_id': global_product_id,
                'household_article_id': str(row.get('household_article_id')),
                'normalized_barcode': normalized_barcode,
            })
            if row.get('household_article_id'):
                set_household_article_global_product_id(conn, str(row.get('household_article_id')), global_product_id)
            sync_global_product_from_enrichment(conn, global_product_id, {
                'title': row.get('title'),
                'brand': row.get('brand'),
                'category': row.get('category'),
                'size_value': row.get('size_value'),
                'size_unit': row.get('size_unit'),
                'source_name': row.get('source_name'),
            })
            dedupe_product_enrichments_for_global_product(conn, global_product_id)

        article_rows_without_link = conn.execute(text(
            """
            SELECT id
            FROM household_articles
            WHERE COALESCE(trim(global_product_id), '') = ''
            ORDER BY datetime(created_at) ASC, id ASC
            """
        )).mappings().all()
        for row in article_rows_without_link:
            ensure_household_article_global_product_link(conn, str(row.get('id')))


def normalize_global_product_source(value: str | None) -> str:
    normalized = str(value or '').strip().lower()
    allowed = {'openfoodfacts', 'open_food_facts', 'public_reference', 'public_reference_catalog', 'gs1', 'gs1_my_product_manager_share', 'user', 'ai', 'receipt', 'manual'}
    if normalized not in allowed:
        return 'user'
    if normalized == 'open_food_facts':
        return 'openfoodfacts'
    if normalized == 'public_reference_catalog':
        return 'public_reference'
    if normalized == 'gs1_my_product_manager_share':
        return 'gs1'
    if normalized == 'manual':
        return 'user'
    return normalized


def normalize_global_product_status(value: str | None) -> str:
    normalized = str(value or '').strip().lower()
    return normalized if normalized in {'active', 'merged', 'archived'} else 'active'


def ensure_global_product_record(conn, gtin: str | None, article_name: str | None, source: str = 'user', brand: str | None = None, category: str | None = None, size_value = None, size_unit: str | None = None) -> str | None:
    normalized_gtin = normalize_barcode_value(gtin) if gtin else None
    normalized_name = normalize_household_article_name(article_name) or (f'Product {normalized_gtin}' if normalized_gtin else '')
    if not normalized_name:
        return None
    existing = None
    if normalized_gtin:
        existing = conn.execute(text(
            """
            SELECT id, name, brand, category, size_value, size_unit
            FROM global_products
            WHERE primary_gtin = :primary_gtin
            LIMIT 1
            """
        ), {'primary_gtin': normalized_gtin}).mappings().first()
    if existing:
        conn.execute(text(
            """
            UPDATE global_products
            SET name = CASE WHEN COALESCE(trim(name), '') = '' THEN :name ELSE name END,
                brand = COALESCE(brand, :brand),
                category = COALESCE(category, :category),
                size_value = COALESCE(size_value, :size_value),
                size_unit = COALESCE(size_unit, :size_unit),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
            """
        ), {'id': existing.get('id'), 'name': normalized_name, 'brand': brand, 'category': category, 'size_value': size_value, 'size_unit': size_unit})
        return str(existing.get('id'))
    product_id = str(uuid.uuid4())
    conn.execute(text(
        """
        INSERT INTO global_products (id, primary_gtin, name, brand, category, size_value, size_unit, source, status, created_at, updated_at)
        VALUES (:id, :primary_gtin, :name, :brand, :category, :size_value, :size_unit, :source, :status, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
    ), {
        'id': product_id,
        'primary_gtin': normalized_gtin,
        'name': normalized_name,
        'brand': brand,
        'category': category,
        'size_value': size_value,
        'size_unit': size_unit,
        'source': normalize_global_product_source(source),
        'status': normalize_global_product_status('active'),
    })
    return product_id


def resolve_global_product_id_for_article(conn, household_article_id: str, barcode: str | None = None) -> str | None:
    article_row = conn.execute(text(
        """
        SELECT global_product_id, barcode, naam, brand_or_maker, category
        FROM household_articles
        WHERE id = :household_article_id
        LIMIT 1
        """
    ), {'household_article_id': str(household_article_id)}).mappings().first()
    normalized_barcode = normalize_barcode_value(barcode) if barcode else None
    if not normalized_barcode and article_row and article_row.get('barcode'):
        normalized_barcode = normalize_barcode_value(article_row.get('barcode'))

    current_global_product_id = str((article_row or {}).get('global_product_id') or '').strip()
    if current_global_product_id:
        if normalized_barcode:
            current_product = conn.execute(text(
                """
                SELECT id, primary_gtin
                FROM global_products
                WHERE id = :global_product_id
                LIMIT 1
                """
            ), {'global_product_id': current_global_product_id}).mappings().first()
            current_gtin = str((current_product or {}).get('primary_gtin') or '').strip()
            if current_gtin == normalized_barcode:
                return current_global_product_id
        else:
            return current_global_product_id

    if normalized_barcode:
        product_row = conn.execute(text(
            """
            SELECT id
            FROM global_products
            WHERE primary_gtin = :primary_gtin
            LIMIT 1
            """
        ), {'primary_gtin': normalized_barcode}).mappings().first()
        if product_row and product_row.get('id'):
            resolved = str(product_row.get('id'))
            set_household_article_global_product_id(conn, str(household_article_id), resolved)
            return resolved

    row = conn.execute(text(
        """
        SELECT global_product_id, identity_value, identity_type
        FROM product_identities
        WHERE household_article_id = :household_article_id AND global_product_id IS NOT NULL
        ORDER BY is_primary DESC, datetime(created_at) DESC, id DESC
        LIMIT 1
        """
    ), {'household_article_id': str(household_article_id)}).mappings().first()
    if row and row.get('global_product_id'):
        identity_type = str(row.get('identity_type') or '').strip().lower()
        identity_value = str(row.get('identity_value') or '').strip()
        if normalized_barcode and identity_type == 'gtin' and identity_value and identity_value != normalized_barcode:
            pass
        else:
            resolved = str(row.get('global_product_id'))
            set_household_article_global_product_id(conn, str(household_article_id), resolved)
            return resolved

    if not normalized_barcode:
        if article_row:
            resolved = ensure_global_product_record(conn, None, article_row.get('naam'), source='user', brand=article_row.get('brand_or_maker'), category=article_row.get('category'))
            if resolved:
                set_household_article_global_product_id(conn, str(household_article_id), resolved)
            return resolved
        return None

    resolved = ensure_global_product_record(conn, normalized_barcode, (article_row or {}).get('naam'), source='user', brand=(article_row or {}).get('brand_or_maker'), category=(article_row or {}).get('category'))
    if resolved:
        set_household_article_global_product_id(conn, str(household_article_id), resolved)
    return resolved


def sync_global_product_from_enrichment(conn, global_product_id: str | None, enrichment: dict | None):
    if not global_product_id or not enrichment:
        return
    conn.execute(text(
        """
        UPDATE global_products
        SET name = CASE WHEN COALESCE(trim(:title), '') <> '' THEN :title ELSE name END,
            brand = COALESCE(:brand, brand),
            category = COALESCE(:category, category),
            size_value = COALESCE(:size_value, size_value),
            size_unit = COALESCE(:size_unit, size_unit),
            source = COALESCE(:source, source),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :global_product_id
        """
    ), {
        'global_product_id': str(global_product_id),
        'title': normalize_household_article_name(enrichment.get('title')) if isinstance(enrichment, dict) else None,
        'brand': (enrichment or {}).get('brand'),
        'category': (enrichment or {}).get('category'),
        'size_value': (enrichment or {}).get('size_value'),
        'size_unit': (enrichment or {}).get('size_unit'),
        'source': normalize_global_product_source((enrichment or {}).get('source_name')),
    })


def get_household_article_ids_for_global_product(conn, global_product_id: str | None) -> list[str]:
    normalized_global_product_id = str(global_product_id or '').strip()
    if not normalized_global_product_id:
        return []
    rows = conn.execute(text(
        """
        SELECT id
        FROM household_articles
        WHERE global_product_id = :global_product_id
        ORDER BY datetime(created_at) ASC, id ASC
        """
    ), {'global_product_id': normalized_global_product_id}).mappings().all()
    return [str(row.get('id')) for row in rows if row.get('id')]


def apply_enrichment_defaults_to_linked_household_articles(conn, global_product_id: str | None, enrichment: dict | None):
    if not global_product_id or not isinstance(enrichment, dict):
        return
    for household_article_id in get_household_article_ids_for_global_product(conn, global_product_id):
        apply_household_article_defaults_from_enrichment(conn, household_article_id, enrichment)


def set_household_article_global_product_id(conn, household_article_id: str | None, global_product_id: str | None) -> str | None:
    normalized_article_id = str(household_article_id or '').strip()
    normalized_global_product_id = str(global_product_id or '').strip()
    if not normalized_article_id or not normalized_global_product_id:
        return None
    existing = conn.execute(text("SELECT household_id, global_product_id FROM household_articles WHERE id = :household_article_id LIMIT 1"), {'household_article_id': normalized_article_id}).mappings().first()
    if not existing:
        return None
    current_global_product_id = str(existing.get('global_product_id') or '').strip()
    if current_global_product_id == normalized_global_product_id:
        return normalized_global_product_id
    conflict = conn.execute(text(
        """
        SELECT id
        FROM household_articles
        WHERE household_id = :household_id
          AND global_product_id = :global_product_id
          AND id <> :household_article_id
        LIMIT 1
        """
    ), {
        'household_id': str(existing.get('household_id') or ''),
        'global_product_id': normalized_global_product_id,
        'household_article_id': normalized_article_id,
    }).mappings().first()
    if conflict:
        return current_global_product_id or None
    conn.execute(text(
        """
        UPDATE household_articles
        SET global_product_id = :global_product_id,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :household_article_id
        """
    ), {'global_product_id': normalized_global_product_id, 'household_article_id': normalized_article_id})
    return normalized_global_product_id


def ensure_household_article_global_product_link(conn, household_article_id: str | None, barcode: str | None = None) -> str | None:
    normalized_article_id = str(household_article_id or '').strip()
    if not normalized_article_id:
        return None
    article_row = conn.execute(text(
        """
        SELECT id, household_id, naam, barcode, brand_or_maker, category, global_product_id
        FROM household_articles
        WHERE id = :household_article_id
        LIMIT 1
        """
    ), {'household_article_id': normalized_article_id}).mappings().first()
    if not article_row:
        return None
    normalized_barcode = None
    try:
        normalized_barcode = normalize_barcode_value(barcode or article_row.get('barcode')) if (barcode or article_row.get('barcode')) else None
    except Exception:
        normalized_barcode = None
    existing_global_product_id = str(article_row.get('global_product_id') or '').strip()
    if existing_global_product_id and not normalized_barcode:
        return existing_global_product_id
    if existing_global_product_id and normalized_barcode:
        existing_product = conn.execute(text(
            """
            SELECT primary_gtin
            FROM global_products
            WHERE id = :global_product_id
            LIMIT 1
            """
        ), {'global_product_id': existing_global_product_id}).mappings().first()
        existing_gtin = str((existing_product or {}).get('primary_gtin') or '').strip()
        if existing_gtin == normalized_barcode:
            return existing_global_product_id
    global_product_id = resolve_global_product_id_for_article(conn, normalized_article_id, normalized_barcode)
    if not global_product_id:
        global_product_id = ensure_global_product_record(
            conn,
            normalized_barcode,
            article_row.get('naam'),
            source='user',
            brand=article_row.get('brand_or_maker'),
            category=article_row.get('category'),
        )
    if global_product_id:
        set_household_article_global_product_id(conn, normalized_article_id, global_product_id)
    return global_product_id


def ensure_release_b_household_article_global_product_integrity():
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_household_articles_household_global_product_lookup ON household_articles (household_id, global_product_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_product_identities_global_product_identity ON product_identities (global_product_id, identity_type, identity_value)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_product_enrichments_global_product_lookup ON product_enrichments (global_product_id, source_name, fetched_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_product_enrichment_attempts_article_lookup ON product_enrichment_attempts (household_article_id, global_product_id, created_at)"))

        orphan_rows = conn.execute(text(
            """
            SELECT ha.id
            FROM household_articles ha
            LEFT JOIN global_products gp ON gp.id = ha.global_product_id
            WHERE COALESCE(trim(ha.global_product_id), '') <> ''
              AND gp.id IS NULL
            ORDER BY ha.id ASC
            """
        )).mappings().all()
        for row in orphan_rows:
            conn.execute(text("UPDATE household_articles SET global_product_id = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = :id"), {'id': str(row.get('id'))})

        article_rows = conn.execute(text(
            """
            SELECT id, barcode
            FROM household_articles
            ORDER BY datetime(created_at) ASC, id ASC
            """
        )).mappings().all()
        for row in article_rows:
            resolved_global_product_id = ensure_household_article_global_product_link(conn, str(row.get('id')), row.get('barcode'))
            if not resolved_global_product_id:
                continue
            params = {
                'household_article_id': str(row.get('id')),
                'global_product_id': str(resolved_global_product_id),
            }
            conn.execute(text(
                """
                UPDATE product_identities
                SET global_product_id = :global_product_id,
                    updated_at = CURRENT_TIMESTAMP
                WHERE household_article_id = :household_article_id
                  AND COALESCE(trim(global_product_id), '') <> :global_product_id
                """
            ), params)
            conn.execute(text(
                """
                UPDATE product_enrichments
                SET global_product_id = :global_product_id
                WHERE household_article_id = :household_article_id
                  AND COALESCE(trim(global_product_id), '') <> :global_product_id
                """
            ), params)
            conn.execute(text(
                """
                UPDATE product_enrichment_audit
                SET global_product_id = :global_product_id
                WHERE household_article_id = :household_article_id
                  AND COALESCE(trim(global_product_id), '') <> :global_product_id
                """
            ), params)
            conn.execute(text(
                """
                UPDATE product_enrichment_attempts
                SET global_product_id = :global_product_id
                WHERE household_article_id = :household_article_id
                  AND COALESCE(trim(global_product_id), '') <> :global_product_id
                """
            ), params)


def ensure_release_c_product_enrichment_centralization():
    with engine.begin() as conn:
        ensure_table_column(conn, 'product_enrichments', 'global_product_id', 'TEXT')
        enrichment_columns = get_table_columns(conn, 'product_enrichments')
        if 'updated_at' not in enrichment_columns:
            ensure_table_column(conn, 'product_enrichments', 'updated_at', 'TEXT')
        ensure_table_column(conn, 'product_enrichment_audit', 'global_product_id', 'TEXT')
        ensure_table_column(conn, 'product_enrichment_attempts', 'global_product_id', 'TEXT')

        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_product_enrichments_global_product_latest ON product_enrichments (global_product_id, source_name, last_lookup_at, fetched_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_product_enrichment_audit_global_product_latest ON product_enrichment_audit (global_product_id, created_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_product_enrichment_attempts_global_product_latest ON product_enrichment_attempts (global_product_id, created_at)"))

        conn.execute(text(
            """
            UPDATE product_enrichment_audit
            SET global_product_id = (
                SELECT ha.global_product_id
                FROM household_articles ha
                WHERE ha.id = product_enrichment_audit.household_article_id
                LIMIT 1
            )
            WHERE COALESCE(trim(global_product_id), '') = ''
              AND EXISTS (
                SELECT 1
                FROM household_articles ha
                WHERE ha.id = product_enrichment_audit.household_article_id
                  AND COALESCE(trim(ha.global_product_id), '') <> ''
              )
            """
        ))
        conn.execute(text(
            """
            UPDATE product_enrichment_attempts
            SET global_product_id = (
                SELECT ha.global_product_id
                FROM household_articles ha
                WHERE ha.id = product_enrichment_attempts.household_article_id
                LIMIT 1
            )
            WHERE COALESCE(trim(global_product_id), '') = ''
              AND EXISTS (
                SELECT 1
                FROM household_articles ha
                WHERE ha.id = product_enrichment_attempts.household_article_id
                  AND COALESCE(trim(ha.global_product_id), '') <> ''
              )
            """
        ))

        rows = conn.execute(text(
            """
            SELECT pe.id, pe.household_article_id, pe.global_product_id, pe.normalized_barcode
            FROM product_enrichments pe
            ORDER BY datetime(COALESCE(pe.last_lookup_at, pe.fetched_at, '1970-01-01')) DESC, pe.id DESC
            """
        )).mappings().all()
        for row in rows:
            article_id = str(row.get('household_article_id') or '').strip()
            global_product_id = str(row.get('global_product_id') or '').strip()
            if not global_product_id and article_id:
                linked = conn.execute(text("SELECT global_product_id FROM household_articles WHERE id = :id LIMIT 1"), {'id': article_id}).scalar()
                global_product_id = str(linked or '').strip()
            if not global_product_id:
                barcode = normalize_barcode_value(row.get('normalized_barcode'))
                if barcode:
                    global_product_id = ensure_global_product_record(conn, barcode, f'Product {barcode}', source='user')
                    if article_id:
                        set_household_article_global_product_id(conn, article_id, global_product_id)
            if global_product_id:
                safe_update_product_enrichment_row(conn, str(row.get('id')), global_product_id, article_id)
                conn.execute(text("UPDATE product_enrichment_audit SET global_product_id = :global_product_id WHERE household_article_id = :household_article_id AND COALESCE(trim(global_product_id), '') = ''"), {'global_product_id': global_product_id, 'household_article_id': article_id})
                conn.execute(text("UPDATE product_enrichment_attempts SET global_product_id = :global_product_id WHERE household_article_id = :household_article_id AND COALESCE(trim(global_product_id), '') = ''"), {'global_product_id': global_product_id, 'household_article_id': article_id})
                dedupe_product_enrichments_for_global_product(conn, global_product_id)

        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_product_enrichments_global_product_source_unique ON product_enrichments (global_product_id, source_name) WHERE global_product_id IS NOT NULL AND trim(global_product_id) <> ''"))


def normalize_household_article_name(value: str | None) -> str:
    return " ".join(str(value or "").strip().split())


def normalize_bool_setting(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "on", "aan", "waar"}


def normalize_household_auto_consume_mode(value) -> str:
    if isinstance(value, bool):
        return ARTICLE_AUTO_CONSUME_PURCHASED_QUANTITY if value else ARTICLE_AUTO_CONSUME_NONE
    normalized = str(value or "").strip().lower()
    if normalized.startswith(""") and normalized.endswith("""):
        normalized = normalized[1:-1].strip().lower()
    try:
        parsed = json.loads(str(value)) if isinstance(value, str) else None
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = None
    if parsed is not None and parsed != value:
        return normalize_household_auto_consume_mode(parsed)
    if normalized in {"true", "1", "yes", "on", "aan", "waar"}:
        return ARTICLE_AUTO_CONSUME_PURCHASED_QUANTITY
    if normalized in HOUSEHOLD_AUTO_CONSUME_ALLOWED:
        return normalized
    return ARTICLE_AUTO_CONSUME_NONE


def normalize_article_auto_consume_mode(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == ARTICLE_AUTO_CONSUME_ALWAYS_ON:
        return ARTICLE_AUTO_CONSUME_PURCHASED_QUANTITY
    if normalized == ARTICLE_AUTO_CONSUME_ALWAYS_OFF:
        return ARTICLE_AUTO_CONSUME_NONE
    if normalized in {ARTICLE_AUTO_CONSUME_NONE, ARTICLE_AUTO_CONSUME_PURCHASED_QUANTITY, ARTICLE_AUTO_CONSUME_ALL_EXISTING}:
        return normalized
    return ARTICLE_AUTO_CONSUME_FOLLOW_HOUSEHOLD


def normalize_article_auto_consume_overrides_map(value) -> dict:
    if not isinstance(value, dict):
        return {}
    normalized = {}
    for article_id, mode in value.items():
        if not isinstance(article_id, str) or not article_id.strip():
            continue
        normalized[article_id.strip()] = normalize_article_auto_consume_mode(mode)
    return normalized


def infer_consumable_from_name(article_name: str | None) -> bool:
    normalized = normalize_household_article_name(article_name).lower()
    if not normalized:
        return False
    if normalized in KNOWN_CONSUMABLE_ARTICLE_NAMES:
        return True
    keywords = [
        "melk", "pasta", "koffie", "mosterd", "sap", "saus", "soep", "rijst", "banaan", "tomaat", "brood",
        "kaas", "yoghurt", "thee", "pindakaas", "jam", "suiker", "zout", "bloem", "eieren", "water",
    ]
    return any(keyword in normalized for keyword in keywords)


def get_household_auto_consume_setting_row(conn, household_id: str):
    return conn.execute(
        text(
            "SELECT setting_value FROM household_settings WHERE household_id = :household_id AND setting_key = :setting_key"
        ),
        {"household_id": str(household_id), "setting_key": HOUSEHOLD_AUTO_CONSUME_KEY},
    ).mappings().first()


def get_household_auto_consume_mode(conn, household_id: str) -> str:
    row = get_household_auto_consume_setting_row(conn, household_id)
    return normalize_household_auto_consume_mode(row["setting_value"] if row else ARTICLE_AUTO_CONSUME_NONE)


def has_household_auto_consume_mode(conn, household_id: str) -> bool:
    return get_household_auto_consume_setting_row(conn, household_id) is not None


def set_household_auto_consume_mode(conn, household_id: str, mode: str) -> str:
    normalized = normalize_household_auto_consume_mode(mode)
    conn.execute(
        text(
            """
            INSERT INTO household_settings (id, household_id, setting_key, setting_value, updated_at)
            VALUES (:id, :household_id, :setting_key, :setting_value, CURRENT_TIMESTAMP)
            ON CONFLICT(household_id, setting_key)
            DO UPDATE SET setting_value = excluded.setting_value, updated_at = CURRENT_TIMESTAMP
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "household_id": str(household_id),
            "setting_key": HOUSEHOLD_AUTO_CONSUME_KEY,
            "setting_value": normalized,
        },
    )
    return normalized


def get_household_auto_consume_on_repurchase(conn, household_id: str) -> bool:
    return get_household_auto_consume_mode(conn, household_id) != ARTICLE_AUTO_CONSUME_NONE


def has_household_auto_consume_on_repurchase(conn, household_id: str) -> bool:
    return has_household_auto_consume_mode(conn, household_id)


def set_household_auto_consume_on_repurchase(conn, household_id: str, enabled: bool) -> bool:
    mode = ARTICLE_AUTO_CONSUME_PURCHASED_QUANTITY if normalize_bool_setting(enabled) else ARTICLE_AUTO_CONSUME_NONE
    return set_household_auto_consume_mode(conn, household_id, mode) != ARTICLE_AUTO_CONSUME_NONE


def get_household_article_auto_consume_overrides(conn, household_id: str) -> dict:
    row = conn.execute(
        text(
            "SELECT setting_value FROM household_settings WHERE household_id = :household_id AND setting_key = :setting_key"
        ),
        {"household_id": str(household_id), "setting_key": ARTICLE_AUTO_CONSUME_OVERRIDES_KEY},
    ).mappings().first()
    if not row or not row.get("setting_value"):
        return {}
    try:
        parsed = json.loads(row["setting_value"])
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return normalize_article_auto_consume_overrides_map(parsed)


def set_household_article_auto_consume_override(conn, household_id: str, article_id: str, mode: str) -> str:
    overrides = get_household_article_auto_consume_overrides(conn, household_id)
    normalized_mode = normalize_article_auto_consume_mode(mode)
    overrides[str(article_id)] = normalized_mode
    conn.execute(
        text(
            """
            INSERT INTO household_settings (id, household_id, setting_key, setting_value, updated_at)
            VALUES (:id, :household_id, :setting_key, :setting_value, CURRENT_TIMESTAMP)
            ON CONFLICT(household_id, setting_key)
            DO UPDATE SET setting_value = excluded.setting_value, updated_at = CURRENT_TIMESTAMP
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "household_id": str(household_id),
            "setting_key": ARTICLE_AUTO_CONSUME_OVERRIDES_KEY,
            "setting_value": json.dumps(overrides),
        },
    )
    return normalized_mode


def has_household_article_auto_consume_override(conn, household_id: str, article_id: str) -> bool:
    overrides = get_household_article_auto_consume_overrides(conn, household_id)
    return str(article_id) in overrides


def get_household_article_auto_consume_override(conn, household_id: str, article_id: str) -> str:
    overrides = get_household_article_auto_consume_overrides(conn, household_id)
    return normalize_article_auto_consume_mode(overrides.get(str(article_id)))


def get_article_consumable_state(conn, household_id: str, article_id: str | None, article_name: str | None = None):
    normalized_article_id = str(article_id or "").strip()
    normalized_name = normalize_household_article_name(article_name)
    if normalized_article_id in MOCK_ARTICLE_LOOKUP:
        return bool(MOCK_ARTICLE_LOOKUP[normalized_article_id].get("consumable"))
    if normalized_article_id.startswith("live::"):
        normalized_name = normalize_household_article_name(normalized_article_id.split("::", 1)[1])
    row = None
    if normalized_name:
        row = conn.execute(
            text(
                """
                SELECT consumable, naam
                FROM household_articles
                WHERE household_id = :household_id AND lower(trim(naam)) = lower(trim(:naam))
                LIMIT 1
                """
            ),
            {"household_id": str(household_id), "naam": normalized_name},
        ).mappings().first()
    if row and row.get("consumable") is not None:
        return bool(row["consumable"])
    inferred = infer_consumable_from_name(normalized_name)
    if row and row.get("naam"):
        conn.execute(
            text(
                "UPDATE household_articles SET consumable = :consumable, updated_at = CURRENT_TIMESTAMP WHERE household_id = :household_id AND lower(trim(naam)) = lower(trim(:naam))"
            ),
            {"consumable": 1 if inferred else 0, "household_id": str(household_id), "naam": row["naam"]},
        )
    return inferred


def find_existing_household_article_name(conn, household_id: str, article_name: str) -> str | None:
    normalized = normalize_household_article_name(article_name)
    if not normalized:
        return None

    row = conn.execute(
        text(
            """
            SELECT naam FROM household_articles
            WHERE household_id = :household_id AND lower(trim(naam)) = lower(trim(:naam))
            LIMIT 1
            """
        ),
        {"household_id": str(household_id), "naam": normalized},
    ).mappings().first()
    if row and row.get("naam"):
        return row["naam"]

    row = conn.execute(
        text(
            """
            SELECT naam FROM inventory
            WHERE household_id = :household_id AND lower(trim(naam)) = lower(trim(:naam))
            LIMIT 1
            """
        ),
        {"household_id": str(household_id), "naam": normalized},
    ).mappings().first()
    if row and row.get("naam"):
        return row["naam"]
    return None


def ensure_household_article(conn, household_id: str, article_name: str, consumable: bool | None = None) -> str:
    normalized = normalize_household_article_name(article_name)
    if not normalized:
        raise HTTPException(status_code=400, detail="Artikelnaam is verplicht")

    existing_name = find_existing_household_article_name(conn, household_id, normalized)
    final_name = existing_name or normalized
    resolved_consumable = infer_consumable_from_name(final_name) if consumable is None else bool(consumable)
    if not existing_name:
        article_id = str(uuid.uuid4())
        conn.execute(
            text(
                """
                INSERT INTO household_articles (id, household_id, naam, consumable, updated_at)
                VALUES (:id, :household_id, :naam, :consumable, CURRENT_TIMESTAMP)
                """
            ),
            {"id": article_id, "household_id": str(household_id), "naam": normalized, "consumable": 1 if resolved_consumable else 0},
        )
    else:
        conn.execute(
            text(
                """
                UPDATE household_articles
                SET consumable = COALESCE(consumable, :consumable), updated_at = CURRENT_TIMESTAMP
                WHERE household_id = :household_id AND lower(trim(naam)) = lower(trim(:naam))
                """
            ),
            {"household_id": str(household_id), "naam": final_name, "consumable": 1 if resolved_consumable else 0},
        )
        existing_row = get_household_article_row_by_name(conn, household_id, final_name)
        article_id = str(existing_row.get('id')) if existing_row and existing_row.get('id') else None
    if article_id:
        ensure_household_article_global_product_link(conn, article_id)
        return str(article_id)
    raise HTTPException(status_code=500, detail="Huishoudartikel kon niet worden aangemaakt")





def normalize_optional_text_field(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).strip().split())
    return normalized or None


def normalize_optional_numeric_field(value: Any) -> float | None:
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail='Ongeldige numerieke waarde ontvangen')


def get_latest_external_article_link(conn, household_id: str, article_name: str) -> dict:
    normalized_name = normalize_household_article_name(article_name)
    if not normalized_name:
        return {'barcode': None, 'article_number': None, 'source': None}
    article_row = get_household_article_row_by_name(conn, household_id, normalized_name)
    if article_row and (article_row.get('barcode') or article_row.get('article_number')):
        return {
            'barcode': article_row.get('barcode') or None,
            'article_number': article_row.get('article_number') or None,
            'source': article_row.get('external_source') or ('household' if article_row.get('barcode') else None),
        }
    row = conn.execute(
        text(
            """
            SELECT barcode, article_number, source
            FROM inventory_events
            WHERE household_id = :household_id
              AND lower(trim(article_name)) = lower(trim(:article_name))
              AND (COALESCE(barcode, '') <> '' OR COALESCE(article_number, '') <> '')
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT 1
            """
        ),
        {'household_id': str(household_id), 'article_name': normalized_name},
    ).mappings().first()
    return {
        'barcode': row.get('barcode') if row else None,
        'article_number': row.get('article_number') if row else None,
        'source': row.get('source') if row else None,
    }


def get_household_article_row_by_name(conn, household_id: str, article_name: str):
    normalized_name = normalize_household_article_name(article_name)
    if not normalized_name:
        return None
    return conn.execute(
        text(
            """
            SELECT id, household_id, naam, consumable, barcode, article_number, external_source, custom_name, article_type, category,
                   brand_or_maker, short_description, notes, min_stock, ideal_stock, favorite_store, average_price, status,
                   created_at, updated_at, global_product_id
            FROM household_articles
            WHERE household_id = :household_id AND lower(trim(naam)) = lower(trim(:naam))
            LIMIT 1
            """
        ),
        {'household_id': str(household_id), 'naam': normalized_name},
    ).mappings().first()


def get_household_article_row_by_id(conn, household_id: str, article_id: str | None):
    normalized_article_id = str(article_id or '').strip()
    if not normalized_article_id:
        return None
    return conn.execute(
        text(
            """
            SELECT id, household_id, naam, consumable, barcode, article_number, external_source, custom_name, article_type, category,
                   brand_or_maker, short_description, notes, min_stock, ideal_stock, favorite_store, average_price, status,
                   created_at, updated_at, global_product_id
            FROM household_articles
            WHERE household_id = :household_id AND id = :article_id
            LIMIT 1
            """
        ),
        {'household_id': str(household_id), 'article_id': normalized_article_id},
    ).mappings().first()


def get_inventory_article_name_by_id(conn, household_id: str, inventory_id: str | None) -> str | None:
    normalized_inventory_id = str(inventory_id or '').strip()
    if not normalized_inventory_id:
        return None
    row = conn.execute(
        text(
            """
            SELECT naam
            FROM inventory
            WHERE household_id = :household_id AND id = :inventory_id
            LIMIT 1
            """
        ),
        {'household_id': str(household_id), 'inventory_id': normalized_inventory_id},
    ).mappings().first()
    if row and row.get('naam'):
        return str(row['naam']).strip()
    return None


def resolve_household_article_reference(conn, household_id: str, article_id: str | None = None, article_name: str | None = None, create_if_missing: bool = False):
    normalized_article_id = str(article_id or '').strip()
    normalized_name = normalize_household_article_name(article_name)

    if normalized_article_id.startswith('live::') and not normalized_name:
        normalized_name = normalize_household_article_name(normalized_article_id.split('::', 1)[1])

    row = None
    inventory_article_name = None
    if normalized_article_id and not normalized_article_id.startswith('live::'):
        row = get_household_article_row_by_id(conn, household_id, normalized_article_id)
        if row:
            return row
        inventory_article_name = get_inventory_article_name_by_id(conn, household_id, normalized_article_id)
        if inventory_article_name:
            inventory_name = normalize_household_article_name(inventory_article_name)
            if inventory_name:
                inventory_row = get_household_article_row_by_name(conn, household_id, inventory_name)
                if inventory_row:
                    return inventory_row
                if not normalized_name:
                    normalized_name = inventory_name
                elif normalize_household_article_name(normalized_name) != inventory_name:
                    normalized_name = inventory_name

    if normalized_name:
        row = get_household_article_row_by_name(conn, household_id, normalized_name)
        if row:
            return row
        if create_if_missing:
            ensure_household_article(conn, household_id, normalized_name)
            row = get_household_article_row_by_name(conn, household_id, normalized_name)
            if row:
                return row
            fallback_inventory_name = find_existing_household_article_name(conn, household_id, normalized_name)
            if fallback_inventory_name and fallback_inventory_name != normalized_name:
                row = get_household_article_row_by_name(conn, household_id, fallback_inventory_name)
                if row:
                    return row
            # Uiterste fallback: maak een minimale artikelregel direct aan zodat detailschermen niet stuklopen.
            direct_id = str(uuid.uuid4())
            resolved_consumable = infer_consumable_from_name(normalized_name)
            conn.execute(
                text(
                    """
                    INSERT OR IGNORE INTO household_articles (id, household_id, naam, consumable, created_at, updated_at)
                    VALUES (:id, :household_id, :naam, :consumable, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                ),
                {
                    'id': direct_id,
                    'household_id': str(household_id),
                    'naam': normalized_name,
                    'consumable': 1 if resolved_consumable else 0,
                },
            )
            row = get_household_article_row_by_name(conn, household_id, normalized_name)
            if row:
                return row

    if normalized_article_id.startswith('live::') and not row:
        fallback_name = normalize_household_article_name(normalized_article_id.split('::', 1)[1])
        if fallback_name:
            if create_if_missing:
                ensure_household_article(conn, household_id, fallback_name)
            return get_household_article_row_by_name(conn, household_id, fallback_name)

    return None


def normalize_identity_lookup_value(value: str | None) -> str | None:
    normalized = ''.join(ch for ch in str(value or '').strip().upper() if ch.isalnum())
    return normalized[:120] if normalized else None


def normalize_product_identity_type(value: str | None) -> str:
    normalized = str(value or '').strip().lower()
    if normalized in {'barcode', 'ean', 'gtin', 'upc'}:
        return 'gtin'
    if normalized in {'store_sku', 'text_match', 'external_article_number', 'article_number'}:
        return 'external_article_number' if normalized in {'external_article_number', 'article_number'} else normalized
    return 'gtin'


def normalize_product_identity_value(identity_type: str | None, identity_value: str | None) -> str | None:
    normalized_type = normalize_product_identity_type(identity_type)
    if normalized_type == 'gtin':
        return normalize_barcode_value(identity_value) if identity_value else None
    return normalize_identity_lookup_value(identity_value)


@dataclass
class EnrichmentLookupResult:
    source_name: str
    status: str
    normalized_barcode: str | None
    message: str | None
    payload: dict | None
    source_record_id: str | None = None
    source_url: str | None = None
    http_status: int | None = None
    response_excerpt: str | None = None


class OpenFoodFactsAdapter:
    source_name = 'open_food_facts'

    def lookup_by_barcode(self, barcode: str) -> EnrichmentLookupResult:
        normalized_barcode = normalize_barcode_value(barcode)
        url = f"https://world.openfoodfacts.org/api/v2/product/{normalized_barcode}.json?fields=code,product_name,product_name_nl,brands,categories,quantity,image_front_small_url,image_front_url,nutriments,ingredients_text_nl,ingredients_text,allergens_from_ingredients,allergens_tags"
        request_obj = urllib.request.Request(
            url,
            headers={
                'Accept': 'application/json',
                'User-Agent': f'Rezzerv/{VERSION_TAG} (product enrichment)',
            },
            method='GET',
        )
        try:
            with urllib.request.urlopen(request_obj, timeout=4.0) as response:
                http_status = getattr(response, 'status', None) or response.getcode()
                payload = json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return EnrichmentLookupResult(
                    source_name=self.source_name,
                    status='not_found',
                    normalized_barcode=normalized_barcode,
                    message='Geen product gevonden voor barcode',
                    payload=None,
                    http_status=exc.code,
                    response_excerpt=(exc.reason or 'HTTP 404') if hasattr(exc, 'reason') else 'HTTP 404',
                )
            return EnrichmentLookupResult(
                source_name=self.source_name,
                status='failed',
                normalized_barcode=normalized_barcode,
                message=f'HTTP-fout bij productlookup: {exc.code}',
                payload=None,
                http_status=exc.code,
                response_excerpt=(exc.reason or '')[:250] if hasattr(exc, 'reason') else None,
            )
        except Exception as exc:
            return EnrichmentLookupResult(
                source_name=self.source_name,
                status='failed',
                normalized_barcode=normalized_barcode,
                message=f'Technische fout bij productlookup: {exc}',
                payload=None,
                response_excerpt=str(exc)[:250],
            )
        if int(payload.get('status') or 0) != 1:
            return EnrichmentLookupResult(
                source_name=self.source_name,
                status='not_found',
                normalized_barcode=normalized_barcode,
                message='Geen product gevonden voor barcode',
                payload=None,
                http_status=int(payload.get('status_verbose') == 'product found' or 200),
                response_excerpt=json.dumps({'status': payload.get('status'), 'status_verbose': payload.get('status_verbose')}, ensure_ascii=False)[:250],
            )
        product = payload.get('product') or {}
        title = str(product.get('product_name_nl') or product.get('product_name') or '').strip()
        if not title:
            return EnrichmentLookupResult(
                source_name=self.source_name,
                status='failed',
                normalized_barcode=normalized_barcode,
                message='Productrespons bevat geen bruikbare titel',
                payload=None,
                http_status=200,
                response_excerpt=json.dumps({'code': product.get('code')}, ensure_ascii=False)[:250],
            )
        brand = str(product.get('brands') or '').split(',')[0].strip() or None
        category = str(product.get('categories') or '').split(',')[0].strip() or None
        quantity_label = str(product.get('quantity') or '').strip()
        size_value = None
        size_unit = None
        match = re.match(r'^\s*(\d+(?:[\.,]\d+)?)\s*([a-zA-Z]+)\s*$', quantity_label)
        if match:
            size_value = float(match.group(1).replace(',', '.'))
            size_unit = match.group(2)
        ingredients = str(product.get('ingredients_text_nl') or product.get('ingredients_text') or '').strip()
        allergens_tags = product.get('allergens_tags') or []
        if isinstance(allergens_tags, str):
            allergens_tags = [allergens_tags]
        allergens = [str(item).split(':')[-1] for item in allergens_tags if str(item).strip()]
        nutriments = product.get('nutriments') if isinstance(product.get('nutriments'), dict) else {}
        image_url = str(product.get('image_front_small_url') or product.get('image_front_url') or '').strip() or None
        enrichment_payload = {
            'source_name': self.source_name,
            'source_record_id': str(product.get('code') or normalized_barcode),
            'title': title,
            'brand': brand,
            'category': category,
            'size_value': size_value,
            'size_unit': size_unit,
            'ingredients_json': [ingredients] if ingredients else [],
            'allergens_json': allergens,
            'nutrition_json': {
                key: nutriments.get(key)
                for key in ('energy-kcal_100g', 'fat_100g', 'carbohydrates_100g', 'proteins_100g', 'salt_100g', 'sugars_100g')
                if nutriments.get(key) is not None
            },
            'image_url': image_url,
            'source_url': f'https://world.openfoodfacts.org/product/{normalized_barcode}',
            'quality_score': 0.9,
            'raw_payload_json': product,
            'normalized_barcode': normalized_barcode,
        }
        return EnrichmentLookupResult(
            source_name=self.source_name,
            status='found',
            normalized_barcode=normalized_barcode,
            message=None,
            payload=enrichment_payload,
            source_record_id=str(product.get('code') or normalized_barcode),
            source_url=f'https://world.openfoodfacts.org/product/{normalized_barcode}',
            http_status=http_status if 'http_status' in locals() else 200,
            response_excerpt=json.dumps({'code': product.get('code'), 'product_name': title}, ensure_ascii=False)[:250],
        )



def normalize_catalog_match_text(value: str | None) -> str:
    normalized = normalize_household_article_name(value).lower()
    cleaned = []
    for ch in normalized:
        if ch.isalnum() or ch.isspace():
            cleaned.append(ch)
        else:
            cleaned.append(' ')
    return ' '.join(''.join(cleaned).split())


def infer_public_catalog_entry_by_article_name(article_name: str | None) -> tuple[str | None, dict | None]:
    normalized_query = normalize_catalog_match_text(article_name)
    if not normalized_query:
        return None, None
    query_tokens = [token for token in normalized_query.split() if len(token) >= 3]
    catalog = load_public_reference_catalog()
    best_barcode = None
    best_entry = None
    best_score = 0
    for barcode, entry in catalog.items():
        title = str(entry.get('title') or '').strip()
        brand = str(entry.get('brand') or '').strip()
        haystack = normalize_catalog_match_text(f"{title} {brand}")
        if not haystack:
            continue
        score = 0
        if normalized_query == haystack:
            score += 100
        elif normalized_query in haystack:
            score += 40
        for token in query_tokens:
            if token in haystack:
                score += 20
        if len(query_tokens) == 1 and query_tokens[0] in haystack:
            score += 10
        if score > best_score:
            best_score = score
            best_barcode = barcode
            best_entry = entry
    if best_score < 20:
        return None, None
    return best_barcode, best_entry


def resolve_article_barcode_with_backfill(conn, household_id: str, article_row: dict | None, article_name: str | None, external_link: dict | None = None) -> tuple[str | None, dict, dict | None]:
    resolved_external_link = dict(external_link or {})
    barcode_value = None
    if article_row and article_row.get('barcode'):
        barcode_value = article_row.get('barcode')
    elif resolved_external_link.get('barcode'):
        barcode_value = resolved_external_link.get('barcode')
    catalog_entry = None
    if not barcode_value:
        inferred_barcode, catalog_entry = infer_public_catalog_entry_by_article_name(article_name)
        if inferred_barcode:
            barcode_value = inferred_barcode
            resolved_external_link = {
                'barcode': inferred_barcode,
                'article_number': resolved_external_link.get('article_number') or None,
                'source': 'public_reference_catalog_backfill',
            }
            if article_row and article_row.get('naam'):
                try:
                    update_household_article_barcode(conn, household_id, str(article_row.get('naam')), inferred_barcode)
                except HTTPException:
                    pass
                except Exception:
                    logger.exception('Barcode-backfill uit public reference catalog mislukt voor %s', article_row.get('naam'))
    return barcode_value, resolved_external_link, catalog_entry


def load_public_reference_catalog() -> dict[str, dict]:
    if not PUBLIC_PRODUCT_CATALOG_PATH.exists():
        return {}
    try:
        payload = json.loads(PUBLIC_PRODUCT_CATALOG_PATH.read_text(encoding='utf-8'))
    except Exception:
        logger.exception('Kon public reference catalog niet laden')
        return {}
    if not isinstance(payload, dict):
        return {}
    normalized: dict[str, dict] = {}
    for raw_key, raw_value in payload.items():
        barcode = normalize_barcode_value(raw_key)
        if not barcode or not isinstance(raw_value, dict):
            continue
        normalized[barcode] = raw_value
    return normalized


class PublicReferenceCatalogAdapter:
    source_name = 'public_reference_catalog'

    def __init__(self):
        self._catalog = load_public_reference_catalog()

    def lookup_by_barcode(self, barcode: str) -> EnrichmentLookupResult:
        normalized_barcode = normalize_barcode_value(barcode)
        if not normalized_barcode:
            return EnrichmentLookupResult(
                source_name=self.source_name,
                status='skipped',
                normalized_barcode=None,
                message='Geen bruikbare barcode beschikbaar voor public reference catalog',
                payload=None,
            )
        entry = self._catalog.get(normalized_barcode)
        if not entry:
            return EnrichmentLookupResult(
                source_name=self.source_name,
                status='not_found',
                normalized_barcode=normalized_barcode,
                message='Geen product gevonden in public reference catalog',
                payload=None,
                response_excerpt=normalized_barcode,
            )
        payload = {
            'source_name': self.source_name,
            'source_record_id': str(entry.get('source_record_id') or normalized_barcode),
            'title': str(entry.get('title') or '').strip() or None,
            'brand': str(entry.get('brand') or '').strip() or None,
            'category': str(entry.get('category') or '').strip() or None,
            'size_value': entry.get('size_value'),
            'size_unit': str(entry.get('size_unit') or '').strip() or None,
            'ingredients_json': entry.get('ingredients_json') or [],
            'allergens_json': entry.get('allergens_json') or [],
            'nutrition_json': entry.get('nutrition_json') or {},
            'image_url': str(entry.get('image_url') or '').strip() or None,
            'source_url': str(entry.get('source_url') or '').strip() or None,
            'quality_score': entry.get('quality_score') if entry.get('quality_score') is not None else 0.6,
            'raw_payload_json': entry.get('raw_payload_json') or {'normalized_barcode': normalized_barcode},
            'normalized_barcode': normalized_barcode,
        }
        if not payload.get('title'):
            return EnrichmentLookupResult(
                source_name=self.source_name,
                status='failed',
                normalized_barcode=normalized_barcode,
                message='Public reference catalog bevat geen bruikbare titel',
                payload=None,
                response_excerpt=json.dumps({'barcode': normalized_barcode}, ensure_ascii=False)[:250],
            )
        return EnrichmentLookupResult(
            source_name=self.source_name,
            status='found',
            normalized_barcode=normalized_barcode,
            message=None,
            payload=payload,
            source_record_id=str(payload.get('source_record_id') or normalized_barcode),
            source_url=payload.get('source_url'),
            http_status=200,
            response_excerpt=json.dumps({'barcode': normalized_barcode, 'title': payload.get('title')}, ensure_ascii=False)[:250],
        )




class Gs1MyProductManagerShareAdapter:
    source_name = 'gs1_my_product_manager_share'

    def lookup_by_barcode(self, barcode: str) -> EnrichmentLookupResult:
        normalized_barcode = normalize_barcode_value(barcode)
        if not normalized_barcode:
            return EnrichmentLookupResult(
                source_name=self.source_name,
                status='skipped',
                normalized_barcode=None,
                message='Geen bruikbare barcode beschikbaar voor GS1/My Product Manager Share',
                payload=None,
            )
        if not GS1_MY_PRODUCT_MANAGER_SHARE_BASE_URL:
            return EnrichmentLookupResult(
                source_name=self.source_name,
                status='skipped',
                normalized_barcode=normalized_barcode,
                message='GS1/My Product Manager Share is nog niet geconfigureerd',
                payload=None,
                response_excerpt='missing_base_url',
            )
        if not GS1_MY_PRODUCT_MANAGER_SHARE_API_KEY:
            return EnrichmentLookupResult(
                source_name=self.source_name,
                status='skipped',
                normalized_barcode=normalized_barcode,
                message='GS1/My Product Manager Share mist API-sleutel',
                payload=None,
                response_excerpt='missing_api_key',
            )
        base_url = GS1_MY_PRODUCT_MANAGER_SHARE_BASE_URL.rstrip('/')
        url = f"{base_url}/products/{normalized_barcode}"
        request_obj = urllib.request.Request(
            url,
            headers={
                'Accept': 'application/json',
                'Authorization': f'Bearer {GS1_MY_PRODUCT_MANAGER_SHARE_API_KEY}',
                'User-Agent': f'Rezzerv/{VERSION_TAG} (GS1 enrichment)',
            },
            method='GET',
        )
        try:
            with urllib.request.urlopen(request_obj, timeout=4.0) as response:
                http_status = getattr(response, 'status', None) or response.getcode()
                payload = json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return EnrichmentLookupResult(
                    source_name=self.source_name,
                    status='not_found',
                    normalized_barcode=normalized_barcode,
                    message='Geen product gevonden in GS1/My Product Manager Share',
                    payload=None,
                    http_status=exc.code,
                    response_excerpt=(exc.reason or 'HTTP 404')[:250] if hasattr(exc, 'reason') else 'HTTP 404',
                )
            return EnrichmentLookupResult(
                source_name=self.source_name,
                status='failed',
                normalized_barcode=normalized_barcode,
                message=f'HTTP-fout bij GS1 productlookup: {exc.code}',
                payload=None,
                http_status=exc.code,
                response_excerpt=(exc.reason or '')[:250] if hasattr(exc, 'reason') else None,
            )
        except Exception as exc:
            return EnrichmentLookupResult(
                source_name=self.source_name,
                status='failed',
                normalized_barcode=normalized_barcode,
                message=f'Technische fout bij GS1 productlookup: {exc}',
                payload=None,
                response_excerpt=str(exc)[:250],
            )
        product = payload.get('product') if isinstance(payload, dict) else None
        if not isinstance(product, dict):
            return EnrichmentLookupResult(
                source_name=self.source_name,
                status='not_found',
                normalized_barcode=normalized_barcode,
                message='GS1/My Product Manager Share gaf geen bruikbaar product terug',
                payload=None,
                http_status=http_status if 'http_status' in locals() else 200,
                response_excerpt=json.dumps(payload, ensure_ascii=False)[:250],
            )
        title = str(product.get('title') or product.get('name') or '').strip()
        if not title:
            return EnrichmentLookupResult(
                source_name=self.source_name,
                status='failed',
                normalized_barcode=normalized_barcode,
                message='GS1 productrespons bevat geen bruikbare titel',
                payload=None,
                http_status=http_status if 'http_status' in locals() else 200,
                response_excerpt=json.dumps(product, ensure_ascii=False)[:250],
            )
        enrichment_payload = {
            'source_name': self.source_name,
            'source_record_id': str(product.get('id') or product.get('gtin') or normalized_barcode),
            'title': title,
            'brand': str(product.get('brand') or '').strip() or None,
            'category': str(product.get('category') or '').strip() or None,
            'size_value': product.get('size_value'),
            'size_unit': str(product.get('size_unit') or '').strip() or None,
            'ingredients_json': product.get('ingredients_json') or [],
            'allergens_json': product.get('allergens_json') or [],
            'nutrition_json': product.get('nutrition_json') or {},
            'image_url': str(product.get('image_url') or '').strip() or None,
            'source_url': str(product.get('source_url') or url).strip() or url,
            'quality_score': product.get('quality_score') if product.get('quality_score') is not None else 0.95,
            'raw_payload_json': payload,
            'normalized_barcode': normalized_barcode,
        }
        return EnrichmentLookupResult(
            source_name=self.source_name,
            status='found',
            normalized_barcode=normalized_barcode,
            message=None,
            payload=enrichment_payload,
            source_record_id=str(enrichment_payload.get('source_record_id') or normalized_barcode),
            source_url=enrichment_payload.get('source_url'),
            http_status=http_status if 'http_status' in locals() else 200,
            response_excerpt=json.dumps({'gtin': normalized_barcode, 'title': title}, ensure_ascii=False)[:250],
        )


def get_configured_product_sources() -> list[dict]:
    configured = []
    for source_name in PRODUCT_SOURCE_ORDER:
        key = str(source_name or '').strip().lower()
        if not key:
            continue
        info = {'source_name': key, 'enabled': True, 'configured': True, 'notes': None}
        if key == 'gs1_my_product_manager_share':
            info['configured'] = bool(GS1_MY_PRODUCT_MANAGER_SHARE_BASE_URL and GS1_MY_PRODUCT_MANAGER_SHARE_API_KEY)
            info['notes'] = None if info['configured'] else 'Nog niet geconfigureerd (base URL en/of API-sleutel ontbreekt)'
        configured.append(info)
    return configured

def choose_product_source_adapters() -> list:
    available = {
        'open_food_facts': OpenFoodFactsAdapter,
        'public_reference_catalog': PublicReferenceCatalogAdapter,
        'gs1_my_product_manager_share': Gs1MyProductManagerShareAdapter,
    }
    adapters: list = []
    seen: set[str] = set()
    for source_name in PRODUCT_SOURCE_ORDER:
        key = str(source_name or '').strip().lower()
        adapter_cls = available.get(key)
        if not adapter_cls or key in seen:
            continue
        adapters.append(adapter_cls())
        seen.add(key)
    if not adapters:
        adapters.append(OpenFoodFactsAdapter())
    return adapters


def write_product_enrichment_audit(conn, household_article_id: str | None, source_name: str, action: str, status: str, message: str | None = None, payload_hash: str | None = None, normalized_barcode: str | None = None, source_request_key: str | None = None, http_status: int | None = None, response_excerpt: str | None = None, global_product_id: str | None = None):
    resolved_global_product_id = global_product_id or (resolve_global_product_id_for_article(conn, household_article_id, normalized_barcode) if household_article_id else None)
    resolved_household_article_id = str(household_article_id) if household_article_id else None
    normalized_response_excerpt = (str(response_excerpt or '').strip() or None)
    normalized_message = str(message or '').strip() or None
    conn.execute(
        text(
            """
            INSERT INTO product_enrichment_audit (
                id, household_article_id, global_product_id, source_name, action, status, message, payload_hash, created_at,
                normalized_barcode, source_request_key, http_status, response_excerpt
            )
            VALUES (
                :id, :household_article_id, :global_product_id, :source_name, :action, :status, :message, :payload_hash, CURRENT_TIMESTAMP,
                :normalized_barcode, :source_request_key, :http_status, :response_excerpt
            )
            """
        ),
        {
            'id': str(uuid.uuid4()),
            'household_article_id': resolved_household_article_id,
            'global_product_id': resolved_global_product_id,
            'source_name': str(source_name or '').strip() or 'unknown',
            'action': str(action or '').strip() or 'lookup',
            'status': str(status or '').strip() or 'success',
            'message': normalized_message,
            'payload_hash': payload_hash,
            'normalized_barcode': str(normalized_barcode or '').strip() or None,
            'source_request_key': str(source_request_key or '').strip() or None,
            'http_status': int(http_status) if http_status is not None else None,
            'response_excerpt': normalized_response_excerpt,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO product_enrichment_attempts (
                id, global_product_id, household_article_id, source_name, action, status, normalized_barcode,
                source_request_key, http_status, response_excerpt, message, created_at
            )
            VALUES (
                :id, :global_product_id, :household_article_id, :source_name, :action, :status, :normalized_barcode,
                :source_request_key, :http_status, :response_excerpt, :message, CURRENT_TIMESTAMP
            )
            """
        ),
        {
            'id': str(uuid.uuid4()),
            'global_product_id': resolved_global_product_id,
            'household_article_id': resolved_household_article_id,
            'source_name': str(source_name or '').strip() or 'unknown',
            'action': str(action or '').strip() or 'lookup',
            'status': str(status or '').strip() or 'success',
            'normalized_barcode': str(normalized_barcode or '').strip() or None,
            'source_request_key': str(source_request_key or '').strip() or None,
            'http_status': int(http_status) if http_status is not None else None,
            'response_excerpt': normalized_response_excerpt,
            'message': normalized_message,
        },
    )


def get_primary_product_identity(conn, household_article_id: str):
    row = conn.execute(
        text(
            """
            SELECT id, household_article_id, global_product_id, identity_type, identity_value, source, confidence_score, is_primary, created_at, updated_at
            FROM product_identities
            WHERE household_article_id = :household_article_id
            ORDER BY is_primary DESC, datetime(created_at) DESC, id DESC
            LIMIT 1
            """
        ),
        {'household_article_id': str(household_article_id)},
    ).mappings().first()
    if row:
        return row
    article_row = conn.execute(text("SELECT barcode FROM household_articles WHERE id = :household_article_id LIMIT 1"), {'household_article_id': str(household_article_id)}).mappings().first()
    normalized_barcode = normalize_barcode_value((article_row or {}).get('barcode')) if article_row and article_row.get('barcode') else None
    if not normalized_barcode:
        return None
    global_product_id = resolve_global_product_id_for_article(conn, household_article_id, normalized_barcode)
    if not global_product_id:
        return None
    return {
        'id': None,
        'household_article_id': str(household_article_id),
        'global_product_id': global_product_id,
        'identity_type': 'gtin',
        'identity_value': normalized_barcode,
        'source': 'catalog',
        'confidence_score': 1.0,
        'is_primary': True,
        'created_at': None,
        'updated_at': None,
    }


def upsert_product_identity(conn, household_article_id: str, identity_type: str, identity_value: str, source: str, confidence_score: float = 1.0, is_primary: bool = False):
    normalized_type = normalize_product_identity_type(identity_type)
    normalized_value = normalize_product_identity_value(normalized_type, identity_value)
    if not normalized_value:
        raise HTTPException(status_code=400, detail='Artikelidentiteit is verplicht')
    global_product_id = resolve_global_product_id_for_article(conn, household_article_id, normalized_value if normalized_type == 'gtin' else None)
    if normalized_type == 'gtin' and not global_product_id:
        article_row = conn.execute(text("SELECT naam, brand_or_maker, category FROM household_articles WHERE id = :household_article_id LIMIT 1"), {'household_article_id': str(household_article_id)}).mappings().first()
        global_product_id = ensure_global_product_record(conn, normalized_value, (article_row or {}).get('naam'), source=source, brand=(article_row or {}).get('brand_or_maker'), category=(article_row or {}).get('category'))
    existing = conn.execute(
        text(
            """
            SELECT id, household_article_id, global_product_id
            FROM product_identities
            WHERE identity_type = :identity_type AND identity_value = :identity_value
            LIMIT 1
            """
        ),
        {'identity_type': normalized_type, 'identity_value': normalized_value},
    ).mappings().first()

    if existing and str(existing.get('household_article_id') or '') != str(household_article_id):
        if normalized_type == 'gtin':
            if existing.get('global_product_id') and not global_product_id:
                global_product_id = str(existing.get('global_product_id'))
            return {
                'id': existing.get('id'),
                'household_article_id': str(household_article_id),
                'global_product_id': global_product_id,
                'identity_type': normalized_type,
                'identity_value': normalized_value,
                'source': str(source or '').strip() or 'manual',
                'confidence_score': float(confidence_score or 0),
                'is_primary': bool(is_primary),
                'created_at': existing.get('created_at') if isinstance(existing, dict) else None,
                'updated_at': None,
            }
        raise HTTPException(status_code=409, detail='Deze artikelidentiteit is al gekoppeld aan een ander artikel')

    if is_primary:
        conn.execute(text("UPDATE product_identities SET is_primary = 0, updated_at = CURRENT_TIMESTAMP WHERE household_article_id = :household_article_id"), {'household_article_id': str(household_article_id)})

    if existing:
        conn.execute(
            text(
                """
                UPDATE product_identities
                SET source = :source,
                    confidence_score = :confidence_score,
                    is_primary = :is_primary,
                    global_product_id = COALESCE(:global_product_id, global_product_id),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {
                'id': existing.get('id'),
                'source': str(source or '').strip() or 'manual',
                'confidence_score': float(confidence_score or 0),
                'is_primary': 1 if is_primary else 0,
                'global_product_id': global_product_id,
            },
        )
    else:
        conn.execute(
            text(
                """
                INSERT INTO product_identities (id, household_article_id, global_product_id, identity_type, identity_value, source, confidence_score, is_primary, created_at, updated_at)
                VALUES (:id, :household_article_id, :global_product_id, :identity_type, :identity_value, :source, :confidence_score, :is_primary, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            ),
            {
                'id': str(uuid.uuid4()),
                'household_article_id': str(household_article_id),
                'global_product_id': global_product_id,
                'identity_type': normalized_type,
                'identity_value': normalized_value,
                'source': str(source or '').strip() or 'manual',
                'confidence_score': float(confidence_score or 0),
                'is_primary': 1 if is_primary else 0,
            },
        )
    return get_primary_product_identity(conn, household_article_id)


def lookup_openfoodfacts_product_details(barcode: str) -> dict | None:
    result = OpenFoodFactsAdapter().lookup_by_barcode(barcode)
    return result.payload if result.status == 'found' else None


def persist_product_enrichment_lookup_result(conn, household_article_id: str, result: EnrichmentLookupResult):
    normalized_article_id = str(household_article_id or '').strip()
    if not normalized_article_id:
        raise HTTPException(status_code=400, detail='household_article_id is verplicht voor productverrijking')
    global_product_id = resolve_global_product_id_for_article(conn, normalized_article_id, result.normalized_barcode)
    if not global_product_id:
        article_row = conn.execute(text("SELECT naam, brand_or_maker, category FROM household_articles WHERE id = :household_article_id LIMIT 1"), {'household_article_id': normalized_article_id}).mappings().first()
        global_product_id = ensure_global_product_record(
            conn,
            result.normalized_barcode,
            (article_row or {}).get('naam'),
            source=result.source_name or 'user',
            brand=(article_row or {}).get('brand_or_maker'),
            category=(article_row or {}).get('category'),
        )
        if global_product_id:
            set_household_article_global_product_id(conn, normalized_article_id, global_product_id)
    if result.normalized_barcode:
        try:
            upsert_product_identity(conn, normalized_article_id, 'gtin', result.normalized_barcode, result.source_name or 'api', confidence_score=1.0, is_primary=True)
        except HTTPException:
            pass
    if global_product_id:
        persist_global_product_lookup_result(conn, global_product_id, result)
        return get_latest_product_enrichment(conn, normalized_article_id)
    message = result.message or None
    existing = conn.execute(
        text(
            """
            SELECT id FROM product_enrichments
            WHERE household_article_id = :household_article_id AND source_name = :source_name
            LIMIT 1
            """
        ),
        {'household_article_id': normalized_article_id, 'source_name': result.source_name},
    ).mappings().first()
    params = {
        'household_article_id': normalized_article_id,
        'global_product_id': None,
        'source_name': result.source_name,
        'lookup_status': result.status,
        'last_lookup_source': result.source_name,
        'last_lookup_message': message,
        'normalized_barcode': result.normalized_barcode,
    }
    if existing:
        conn.execute(
            text(
                """
                UPDATE product_enrichments
                SET household_article_id = COALESCE(household_article_id, :household_article_id),
                    global_product_id = COALESCE(:global_product_id, global_product_id),
                    source_record_id = NULL,
                    title = NULL,
                    brand = NULL,
                    category = NULL,
                    size_value = NULL,
                    size_unit = NULL,
                    ingredients_json = '[]',
                    allergens_json = '[]',
                    nutrition_json = '{}',
                    image_url = NULL,
                    source_url = NULL,
                    quality_score = NULL,
                    raw_payload_json = '{}',
                    fetched_at = CURRENT_TIMESTAMP,
                    lookup_status = :lookup_status,
                    last_lookup_at = CURRENT_TIMESTAMP,
                    last_lookup_source = :last_lookup_source,
                    last_lookup_message = :last_lookup_message,
                    normalized_barcode = :normalized_barcode
                WHERE id = :id
                """
            ),
            {'id': existing.get('id'), **params},
        )
    else:
        conn.execute(
            text(
                """
                INSERT INTO product_enrichments (
                    id, household_article_id, global_product_id, source_name, source_record_id, title, brand, category, size_value, size_unit,
                    ingredients_json, allergens_json, nutrition_json, image_url, source_url, quality_score, fetched_at, raw_payload_json,
                    lookup_status, last_lookup_at, last_lookup_source, last_lookup_message, normalized_barcode
                ) VALUES (
                    :id, :household_article_id, :global_product_id, :source_name, NULL, NULL, NULL, NULL, NULL, NULL,
                    '[]', '[]', '{}', NULL, NULL, NULL, CURRENT_TIMESTAMP, '{}',
                    :lookup_status, CURRENT_TIMESTAMP, :last_lookup_source, :last_lookup_message, :normalized_barcode
                )
                """
            ),
            {'id': str(uuid.uuid4()), **params},
        )
    write_product_enrichment_audit(
        conn, normalized_article_id, result.source_name, 'lookup', result.status, message,
        normalized_barcode=result.normalized_barcode,
        source_request_key=f'{result.source_name}:{result.normalized_barcode}' if result.normalized_barcode else result.source_name,
        http_status=result.http_status,
        response_excerpt=result.response_excerpt,
        global_product_id=None,
    )
    return get_latest_product_enrichment(conn, normalized_article_id)


def get_current_article_barcode(conn, household_article_id: str | None) -> str | None:
    normalized_article_id = str(household_article_id or '').strip()
    if not normalized_article_id:
        return None
    row = conn.execute(
        text("SELECT barcode FROM household_articles WHERE id = :household_article_id LIMIT 1"),
        {'household_article_id': normalized_article_id},
    ).mappings().first()
    try:
        return normalize_barcode_value((row or {}).get('barcode')) if row and row.get('barcode') else None
    except Exception:
        return None


def resolve_active_enrichment_row(conn, household_article_id: str):
    normalized_article_id = str(household_article_id or '').strip()
    if not normalized_article_id:
        return None
    current_barcode = get_current_article_barcode(conn, normalized_article_id)
    global_product_id = resolve_global_product_id_for_article(conn, normalized_article_id, current_barcode)
    candidates = []
    if global_product_id and current_barcode:
        candidates.append(conn.execute(
            text(
                """
                SELECT *
                FROM product_enrichments
                WHERE global_product_id = :global_product_id
                  AND COALESCE(normalized_barcode, '') = :normalized_barcode
                ORDER BY CASE WHEN lookup_status = 'found' THEN 0 ELSE 1 END,
                         datetime(COALESCE(last_lookup_at, fetched_at)) DESC,
                         id DESC
                LIMIT 1
                """
            ),
            {'global_product_id': global_product_id, 'normalized_barcode': current_barcode},
        ).mappings().first())
    if global_product_id:
        candidates.append(conn.execute(
            text(
                """
                SELECT *
                FROM product_enrichments
                WHERE global_product_id = :global_product_id
                ORDER BY CASE WHEN lookup_status = 'found' THEN 0 ELSE 1 END,
                         datetime(COALESCE(last_lookup_at, fetched_at)) DESC,
                         id DESC
                LIMIT 1
                """
            ),
            {'global_product_id': global_product_id},
        ).mappings().first())
    if current_barcode:
        candidates.append(conn.execute(
            text(
                """
                SELECT *
                FROM product_enrichments
                WHERE household_article_id = :household_article_id
                  AND COALESCE(normalized_barcode, '') = :normalized_barcode
                ORDER BY CASE WHEN lookup_status = 'found' THEN 0 ELSE 1 END,
                         datetime(COALESCE(last_lookup_at, fetched_at)) DESC,
                         id DESC
                LIMIT 1
                """
            ),
            {'household_article_id': normalized_article_id, 'normalized_barcode': current_barcode},
        ).mappings().first())
    candidates.append(conn.execute(
        text(
            """
            SELECT *
            FROM product_enrichments
            WHERE household_article_id = :household_article_id
            ORDER BY CASE WHEN lookup_status = 'found' THEN 0 ELSE 1 END,
                     datetime(COALESCE(last_lookup_at, fetched_at)) DESC,
                     id DESC
            LIMIT 1
            """
        ),
        {'household_article_id': normalized_article_id},
    ).mappings().first())
    for row in candidates:
        if row:
            if current_barcode and row.get('normalized_barcode') and str(row.get('normalized_barcode')).strip() != current_barcode:
                continue
            return row
    return None

def get_article_enrichment_status(conn, household_article_id: str) -> dict:
    row = resolve_active_enrichment_row(conn, household_article_id)
    if row:
        return {
            'status': row.get('lookup_status') or ('found' if row.get('source_name') else 'skipped'),
            'source': row.get('last_lookup_source') or row.get('source_name'),
            'message': row.get('last_lookup_message') or None,
            'lookup_attempted_at': row.get('last_lookup_at') or None,
            'normalized_barcode': row.get('normalized_barcode') or None,
        }
    global_product_id = resolve_global_product_id_for_article(conn, household_article_id)
    audit = None
    if global_product_id:
        audit = conn.execute(
            text(
                """
                SELECT source_name, status, message, created_at, normalized_barcode
                FROM product_enrichment_audit
                WHERE global_product_id = :global_product_id
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT 1
                """
            ),
            {'global_product_id': global_product_id},
        ).mappings().first()
    if not audit:
        audit = conn.execute(
            text(
                """
                SELECT source_name, status, message, created_at, normalized_barcode
                FROM product_enrichment_audit
                WHERE household_article_id = :household_article_id
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT 1
                """
            ),
            {'household_article_id': str(household_article_id)},
        ).mappings().first()
    if audit:
        return {
            'status': audit.get('status') or 'skipped',
            'source': audit.get('source_name') or None,
            'message': audit.get('message') or None,
            'lookup_attempted_at': audit.get('created_at') or None,
            'normalized_barcode': audit.get('normalized_barcode') or None,
        }
    return {'status': 'skipped', 'source': None, 'message': None, 'lookup_attempted_at': None, 'normalized_barcode': None}

def upsert_product_enrichment(conn, household_article_id: str, enrichment: dict, lookup_status: str = 'found', normalized_barcode: str | None = None, lookup_source: str | None = None, lookup_message: str | None = None, audit_result: EnrichmentLookupResult | None = None):
    normalized_article_id = str(household_article_id or '').strip()
    if not normalized_article_id:
        raise HTTPException(status_code=400, detail='household_article_id is verplicht voor productverrijking')
    source_name = str(enrichment.get('source_name') or '').strip() or 'unknown'
    resolved_barcode = str(normalized_barcode or enrichment.get('normalized_barcode') or '').strip() or None
    global_product_id = resolve_global_product_id_for_article(conn, normalized_article_id, resolved_barcode)
    if not global_product_id:
        article_row = conn.execute(text("SELECT naam, brand_or_maker, category FROM household_articles WHERE id = :household_article_id LIMIT 1"), {'household_article_id': normalized_article_id}).mappings().first()
        global_product_id = ensure_global_product_record(
            conn,
            resolved_barcode,
            (article_row or {}).get('naam') or enrichment.get('title'),
            source=source_name,
            brand=enrichment.get('brand') or (article_row or {}).get('brand_or_maker'),
            category=enrichment.get('category') or (article_row or {}).get('category'),
            size_value=enrichment.get('size_value'),
            size_unit=enrichment.get('size_unit'),
        )
        if global_product_id:
            set_household_article_global_product_id(conn, normalized_article_id, global_product_id)
    if resolved_barcode:
        try:
            upsert_product_identity(conn, normalized_article_id, 'gtin', resolved_barcode, source_name or 'api', confidence_score=1.0, is_primary=True)
        except HTTPException:
            pass
    if global_product_id:
        upsert_global_product_enrichment(
            conn,
            global_product_id,
            {**enrichment, 'source_name': source_name, 'normalized_barcode': resolved_barcode or enrichment.get('normalized_barcode')},
            lookup_status=lookup_status,
            normalized_barcode=resolved_barcode,
            lookup_source=lookup_source,
            lookup_message=lookup_message,
            audit_result=audit_result,
        )
        return get_latest_product_enrichment(conn, normalized_article_id)
    # Fallback only when no productrecord can be resolved.
    source_name = str(enrichment.get('source_name') or '').strip() or 'unknown'
    payload_hash = hashlib.sha256(json.dumps(enrichment, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
    params = {
        'household_article_id': normalized_article_id,
        'global_product_id': None,
        'source_name': source_name,
        'source_record_id': enrichment.get('source_record_id'),
        'title': enrichment.get('title'),
        'brand': enrichment.get('brand'),
        'category': enrichment.get('category'),
        'size_value': enrichment.get('size_value'),
        'size_unit': enrichment.get('size_unit'),
        'ingredients_json': json.dumps(enrichment.get('ingredients_json') or [], ensure_ascii=False),
        'allergens_json': json.dumps(enrichment.get('allergens_json') or [], ensure_ascii=False),
        'nutrition_json': json.dumps(enrichment.get('nutrition_json') or {}, ensure_ascii=False),
        'image_url': enrichment.get('image_url'),
        'source_url': enrichment.get('source_url'),
        'quality_score': enrichment.get('quality_score'),
        'raw_payload_json': json.dumps(enrichment.get('raw_payload_json') or {}, ensure_ascii=False),
        'lookup_status': lookup_status or 'found',
        'last_lookup_source': lookup_source or source_name,
        'last_lookup_message': lookup_message,
        'normalized_barcode': resolved_barcode,
    }
    existing = conn.execute(text("SELECT id FROM product_enrichments WHERE household_article_id = :household_article_id AND source_name = :source_name LIMIT 1"), {'household_article_id': normalized_article_id, 'source_name': source_name}).mappings().first()
    if existing:
        conn.execute(text("""
            UPDATE product_enrichments
            SET global_product_id = COALESCE(:global_product_id, global_product_id), source_record_id = :source_record_id,
                title = :title, brand = :brand, category = :category, size_value = :size_value, size_unit = :size_unit,
                ingredients_json = :ingredients_json, allergens_json = :allergens_json, nutrition_json = :nutrition_json,
                image_url = :image_url, source_url = :source_url, quality_score = :quality_score, raw_payload_json = :raw_payload_json,
                fetched_at = CURRENT_TIMESTAMP, lookup_status = :lookup_status, last_lookup_at = CURRENT_TIMESTAMP,
                last_lookup_source = :last_lookup_source, last_lookup_message = :last_lookup_message, normalized_barcode = :normalized_barcode
            WHERE id = :id
        """), {'id': existing.get('id'), **params})
    else:
        conn.execute(text("""
            INSERT INTO product_enrichments (
                id, household_article_id, global_product_id, source_name, source_record_id, title, brand, category, size_value, size_unit,
                ingredients_json, allergens_json, nutrition_json, image_url, source_url, quality_score, fetched_at, raw_payload_json,
                lookup_status, last_lookup_at, last_lookup_source, last_lookup_message, normalized_barcode
            ) VALUES (
                :id, :household_article_id, :global_product_id, :source_name, :source_record_id, :title, :brand, :category, :size_value, :size_unit,
                :ingredients_json, :allergens_json, :nutrition_json, :image_url, :source_url, :quality_score, CURRENT_TIMESTAMP, :raw_payload_json,
                :lookup_status, CURRENT_TIMESTAMP, :last_lookup_source, :last_lookup_message, :normalized_barcode
            )
        """), {'id': str(uuid.uuid4()), **params})
    apply_household_article_defaults_from_enrichment(conn, normalized_article_id, enrichment)
    write_product_enrichment_audit(conn, normalized_article_id, source_name, 'lookup', 'found', payload_hash=payload_hash, normalized_barcode=params.get('normalized_barcode'), source_request_key=f"{source_name}:{params.get('normalized_barcode')}" if params.get('normalized_barcode') else source_name, http_status=(audit_result.http_status if audit_result else None), response_excerpt=(audit_result.response_excerpt if audit_result else None), global_product_id=None)


def get_latest_product_enrichment(conn, household_article_id: str):
    row = resolve_active_enrichment_row(conn, household_article_id)
    if not row:
        return None
    return {
        'source_name': row.get('source_name'),
        'source_record_id': row.get('source_record_id'),
        'title': row.get('title'),
        'brand': row.get('brand'),
        'category': row.get('category'),
        'size_value': float(row['size_value']) if row.get('size_value') is not None else None,
        'size_unit': row.get('size_unit') or None,
        'ingredients': json.loads(row.get('ingredients_json') or '[]'),
        'allergens': json.loads(row.get('allergens_json') or '[]'),
        'nutrition': json.loads(row.get('nutrition_json') or '{}'),
        'image_url': row.get('image_url') or None,
        'source_url': row.get('source_url') or None,
        'quality_score': float(row['quality_score']) if row.get('quality_score') is not None else None,
        'fetched_at': row.get('fetched_at'),
        'lookup_status': row.get('lookup_status') or ('found' if row.get('source_name') else None),
        'last_lookup_at': row.get('last_lookup_at') or None,
        'last_lookup_source': row.get('last_lookup_source') or row.get('source_name') or None,
        'last_lookup_message': row.get('last_lookup_message') or None,
        'normalized_barcode': row.get('normalized_barcode') or None,
    }

def get_recent_product_enrichment_attempts(conn, household_article_id: str, limit: int = 10) -> list[dict]:
    global_product_id = resolve_global_product_id_for_article(conn, household_article_id)
    rows = []
    if global_product_id:
        rows = conn.execute(
            text(
                """
                SELECT source_name, action, status, message, created_at, normalized_barcode, http_status, response_excerpt
                FROM product_enrichment_audit
                WHERE global_product_id = :global_product_id
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT :limit
                """
            ),
            {'global_product_id': global_product_id, 'limit': int(limit)},
        ).mappings().all()
    if not rows:
        rows = conn.execute(
            text(
                """
                SELECT source_name, action, status, message, created_at, normalized_barcode, http_status, response_excerpt
                FROM product_enrichment_audit
                WHERE household_article_id = :household_article_id
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT :limit
                """
            ),
            {'household_article_id': str(household_article_id), 'limit': int(limit)},
        ).mappings().all()
    return [
        {
            'source_name': row.get('source_name'),
            'action': row.get('action'),
            'status': row.get('status'),
            'message': row.get('message') or None,
            'created_at': row.get('created_at') or None,
            'normalized_barcode': row.get('normalized_barcode') or None,
            'http_status': row.get('http_status'),
            'response_excerpt': row.get('response_excerpt') or None,
        }
        for row in rows
    ]

def ensure_article_product_enrichment(conn, household_article_id: str, barcode: str | None, force_refresh: bool = False):
    normalized_article_id = str(household_article_id or '').strip()
    existing = get_latest_product_enrichment(conn, normalized_article_id)
    if existing and not force_refresh and existing.get('lookup_status') == 'found':
        return existing
    normalized_barcode = None
    try:
        normalized_barcode = normalize_barcode_value(barcode) if barcode else None
    except Exception:
        normalized_barcode = None
    if not normalized_barcode:
        result = EnrichmentLookupResult(
            source_name='product_enrichment',
            status='skipped',
            normalized_barcode=None,
            message='Geen barcode beschikbaar voor verrijking',
            payload=None,
        )
        persist_product_enrichment_lookup_result(conn, normalized_article_id, result)
        return get_latest_product_enrichment(conn, normalized_article_id)
    try:
        upsert_product_identity(conn, normalized_article_id, 'gtin', normalized_barcode, 'api', confidence_score=1.0, is_primary=True)
    except HTTPException:
        pass
    global_product_id, _global_enrichment = ensure_global_product_enrichment(
        conn,
        normalized_barcode,
        force_refresh=force_refresh,
        product_name_hint=(conn.execute(text("SELECT naam FROM household_articles WHERE id = :household_article_id LIMIT 1"), {'household_article_id': normalized_article_id}).mappings().first() or {}).get('naam'),
    )
    if global_product_id:
        set_household_article_global_product_id(conn, normalized_article_id, global_product_id)
        latest = get_latest_global_product_enrichment(conn, global_product_id)
        if latest and latest.get('lookup_status') == 'found':
            apply_household_article_defaults_from_enrichment(conn, normalized_article_id, latest)
        return get_latest_product_enrichment(conn, normalized_article_id)
    return get_latest_product_enrichment(conn, normalized_article_id)


def get_article_product_details(conn, household_id: str, article_name: str | None = None, auto_enrich: bool = True, article_id: str | None = None) -> dict:
    article_row = resolve_household_article_reference(conn, household_id, article_id=article_id, article_name=article_name, create_if_missing=True)
    if not article_row:
        raise HTTPException(status_code=404, detail='Artikel niet gevonden')
    resolved_article_name = article_row.get('naam') or article_name or ''
    external_link = get_latest_external_article_link(conn, household_id, resolved_article_name)
    barcode_value, external_link, _catalog_entry = resolve_article_barcode_with_backfill(conn, household_id, article_row, resolved_article_name, external_link)
    if barcode_value:
        try:
            upsert_product_identity(conn, article_row.get('id'), 'gtin', barcode_value, external_link.get('source') or 'receipt', confidence_score=1.0, is_primary=True)
        except HTTPException:
            pass
    identity = get_primary_product_identity(conn, article_row.get('id'))
    enrichment = get_latest_product_enrichment(conn, article_row.get('id'))
    if auto_enrich and barcode_value and (not enrichment or enrichment.get('lookup_status') != 'found'):
        enrichment = ensure_article_product_enrichment(conn, article_row.get('id'), barcode_value)
    enrichment_status = get_article_enrichment_status(conn, article_row.get('id'))

    global_product_id = resolve_global_product_id_for_article(conn, article_row.get('id'), barcode_value)
    internal_catalog = {
        'status': 'niet gevonden',
        'match_found': False,
        'global_product_id': None,
        'reused_from_catalog': False,
    }
    if global_product_id:
        internal_catalog = {
            'status': 'gevonden',
            'match_found': True,
            'global_product_id': global_product_id,
            'reused_from_catalog': bool(enrichment and enrichment.get('source_name')),
        }

    source_chain = [
        {
            'source_name': 'internal_catalog',
            'configured': True,
            'enabled': True,
            'notes': 'Rezzerv controleert eerst de interne productcatalogus.',
        },
        *get_configured_product_sources(),
    ]

    return {
        'article_id': article_row.get('id'),
        'article_name': resolved_article_name,
        'identity': {
            'identity_type': identity.get('identity_type') if identity else ('gtin' if barcode_value else None),
            'identity_value': identity.get('identity_value') if identity else (barcode_value or None),
            'normalized_barcode': identity.get('identity_value') if identity and identity.get('identity_type') == 'gtin' else (normalize_barcode_value(barcode_value) if barcode_value else None),
            'source': identity.get('source') if identity else (external_link.get('source') or ('household' if article_row.get('barcode') else None)),
            'confidence_score': float(identity['confidence_score']) if identity and identity.get('confidence_score') is not None else (1.0 if barcode_value else None),
            'is_primary': bool(identity.get('is_primary')) if identity else bool(barcode_value),
        },
        'internal_catalog': internal_catalog,
        'enrichment_status': enrichment_status,
        'enrichment': enrichment,
        'source_chain': source_chain,
        'recent_enrichment_attempts': get_recent_product_enrichment_attempts(conn, article_row.get('id')),
    }


def apply_household_article_defaults_from_enrichment(conn, household_article_id: str | None, enrichment: dict | None):
    normalized_article_id = str(household_article_id or '').strip()
    if not normalized_article_id or not isinstance(enrichment, dict):
        return
    title = normalize_optional_text_field(enrichment.get('title'))
    brand = normalize_optional_text_field(enrichment.get('brand'))
    category = normalize_optional_text_field(enrichment.get('category'))
    size_value = enrichment.get('size_value')
    size_unit = normalize_optional_text_field(enrichment.get('size_unit'))
    short_description = title
    if size_value not in (None, ''):
        size_label = f"{size_value}{(' ' + size_unit) if size_unit else ''}"
        short_description = f"{title} ({size_label})" if title else size_label
    article_type = 'Voedsel & drank' if title or brand or category else None
    conn.execute(text(
        """
        UPDATE household_articles
        SET custom_name = CASE
                WHEN COALESCE(trim(:custom_name), '') <> '' THEN :custom_name
                ELSE custom_name
            END,
            article_type = CASE
                WHEN COALESCE(trim(:article_type), '') <> '' THEN :article_type
                ELSE article_type
            END,
            category = CASE
                WHEN COALESCE(trim(:category), '') <> '' THEN :category
                ELSE category
            END,
            brand_or_maker = CASE
                WHEN COALESCE(trim(:brand), '') <> '' THEN :brand
                ELSE brand_or_maker
            END,
            short_description = CASE
                WHEN COALESCE(trim(:short_description), '') <> '' THEN :short_description
                ELSE short_description
            END,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :household_article_id
        """
    ), {
        'household_article_id': normalized_article_id,
        'custom_name': title,
        'brand': brand,
        'category': category,
        'short_description': short_description,
        'article_type': article_type,
    })


def merge_household_article_details_with_product_defaults(row: dict, product_details: dict | None) -> dict:
    enrichment = (product_details or {}).get('enrichment') if isinstance(product_details, dict) else {}
    enrichment = enrichment or {}
    merged = dict(row or {})
    title = normalize_optional_text_field(enrichment.get('title'))
    size_value = enrichment.get('size_value')
    size_unit = normalize_optional_text_field(enrichment.get('size_unit'))
    short_description = None
    if size_value not in (None, ''):
        size_label = f"{size_value}{(' ' + size_unit) if size_unit else ''}"
        short_description = f"{title} ({size_label})" if title else size_label
    else:
        short_description = title or None
    if title:
        merged['custom_name'] = title
    if enrichment.get('brand'):
        merged['brand_or_maker'] = enrichment.get('brand')
    if enrichment.get('category'):
        merged['category'] = enrichment.get('category')
    if short_description:
        merged['short_description'] = short_description
    if enrichment.get('title') or enrichment.get('brand') or enrichment.get('category'):
        merged['article_type'] = 'Voedsel & drank'
    return merged


def get_household_article_details(conn, household_id: str, article_name: str | None = None, article_id: str | None = None) -> dict:
    row = resolve_household_article_reference(conn, household_id, article_id=article_id, article_name=article_name, create_if_missing=True)
    if not row:
        raise HTTPException(status_code=404, detail='Artikel niet gevonden')
    final_name = row.get('naam') or normalize_household_article_name(article_name) or ''
    external_link = get_latest_external_article_link(conn, household_id, final_name)
    barcode_value, external_link, _catalog_entry = resolve_article_barcode_with_backfill(conn, household_id, row, final_name, external_link)
    barcode_value = row.get('barcode') or barcode_value
    article_number_value = row.get('article_number') or external_link.get('article_number') or None
    source_value = row.get('source') or external_link.get('source') or ('barcode_link' if barcode_value else None)
    product_details = get_article_product_details(conn, household_id, final_name, auto_enrich=True, article_id=row.get('id'))
    merged_row = merge_household_article_details_with_product_defaults(dict(row or {}), product_details)
    return {
        'id': row.get('id'),
        'article_id': row.get('id'),
        'article_name': final_name,
        'custom_name': merged_row.get('custom_name') or None,
        'article_type': merged_row.get('article_type') or None,
        'category': merged_row.get('category') or None,
        'brand_or_maker': merged_row.get('brand_or_maker') or None,
        'short_description': merged_row.get('short_description') or None,
        'notes': merged_row.get('notes') or None,
        'min_stock': float(row['min_stock']) if row.get('min_stock') is not None else None,
        'ideal_stock': float(row['ideal_stock']) if row.get('ideal_stock') is not None else None,
        'favorite_store': merged_row.get('favorite_store') or None,
        'consumable': bool(row.get('consumable')) if row.get('consumable') is not None else None,
        'barcode': barcode_value or None,
        'article_number': article_number_value,
        'source': source_value,
        'global_product_id': ensure_household_article_global_product_link(conn, row.get('id'), barcode_value),
        'updated_at': row.get('updated_at'),
        'created_at': row.get('created_at'),
        'product_details': product_details,
    }





def get_household_article_inventory_rows(conn, household_id: str, household_article_id: str) -> list[dict]:
    article_row = get_household_article_row_by_id(conn, household_id, household_article_id)
    if not article_row:
        raise HTTPException(status_code=404, detail='Artikel niet gevonden')
    article_name = str(article_row.get('naam') or '').strip()
    rows = conn.execute(
        text(
            """
            SELECT
              i.id,
              i.naam AS article_name,
              i.aantal AS quantity,
              i.household_id,
              i.space_id,
              i.sublocation_id,
              COALESCE(s.naam, '') AS space_name,
              COALESCE(sl.naam, '') AS sublocation_name,
              COALESCE(i.status, 'active') AS status
            FROM inventory i
            LEFT JOIN spaces s ON s.id = i.space_id
            LEFT JOIN sublocations sl ON sl.id = i.sublocation_id
            WHERE i.household_id = :household_id
              AND lower(trim(i.naam)) = lower(trim(:article_name))
              AND COALESCE(i.status, 'active') = 'active'
              AND COALESCE(i.aantal, 0) > 0
            ORDER BY datetime(COALESCE(i.updated_at, i.created_at)) DESC, i.id ASC
            """
        ),
        {"household_id": str(household_id), "article_name": article_name},
    ).mappings().all()
    return [
        {
            "id": row["id"],
            "household_article_id": str(article_row.get("id") or ""),
            "article_id": str(article_row.get("id") or ""),
            "article_name": row["article_name"],
            "quantity": float(row["quantity"]) if row.get("quantity") is not None else 0,
            "aantal": float(row["quantity"]) if row.get("quantity") is not None else 0,
            "space_id": row["space_id"] or "",
            "sublocation_id": row["sublocation_id"] or "",
            "space_name": row["space_name"] or "",
            "locatie": row["space_name"] or "",
            "sublocation_name": row["sublocation_name"] or "",
            "sublocatie": row["sublocation_name"] or "",
            "location_label": " / ".join(part for part in [row["space_name"] or "", row["sublocation_name"] or ""] if part),
            "status": row["status"] or "active",
        }
        for row in rows
    ]


def get_household_article_event_rows(conn, household_id: str, household_article_id: str) -> list[dict]:
    article_row = get_household_article_row_by_id(conn, household_id, household_article_id)
    if not article_row:
        raise HTTPException(status_code=404, detail='Artikel niet gevonden')
    article_name = str(article_row.get('naam') or '').strip()
    rows = conn.execute(
        text(
            """
            SELECT
              id,
              article_id,
              article_name,
              location_id,
              location_label,
              event_type,
              quantity,
              old_quantity,
              new_quantity,
              source,
              note,
              created_at
            FROM inventory_events
            WHERE household_id = :household_id
              AND (
                article_id = :household_article_id
                OR lower(trim(article_name)) = lower(trim(:article_name))
              )
            ORDER BY datetime(created_at) DESC, id DESC
            """
        ),
        {
            "household_id": str(household_id),
            "household_article_id": str(household_article_id),
            "article_name": article_name,
        },
    ).mappings().all()
    return [
        {
            "id": row["id"],
            "household_article_id": str(article_row.get("id") or ""),
            "article_id": str(article_row.get("id") or ""),
            "article_name": row["article_name"],
            "location_id": row["location_id"],
            "location_label": row["location_label"],
            "event_type": row["event_type"],
            "quantity": row["quantity"],
            "old_quantity": row["old_quantity"],
            "new_quantity": row["new_quantity"],
            "source": row["source"],
            "note": row["note"],
            "created_at": normalize_datetime(row["created_at"]),
        }
        for row in rows
    ]



HOUSEHOLD_ARTICLE_SETTINGS_ALLOWED_KEYS = (
    'default_location_id',
    'default_sublocation_id',
    'auto_restock',
    'packaging_unit',
    'packaging_quantity',
)


def _parse_json_setting_value(raw_value: Any):
    if raw_value is None:
        return None
    if isinstance(raw_value, (dict, list, bool, int, float)):
        return raw_value
    text_value = str(raw_value).strip()
    if text_value == '':
        return None
    try:
        return json.loads(text_value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return text_value


def _normalize_settings_bool(value: Any) -> bool | None:
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {'1', 'true', 'yes', 'on'}:
        return True
    if normalized in {'0', 'false', 'no', 'off'}:
        return False
    raise HTTPException(status_code=400, detail='Ongeldige boolean waarde ontvangen')


def validate_household_article_location_setting(conn, household_id: str, location_id: str | None, sublocation_id: str | None) -> tuple[str | None, str | None]:
    normalized_location_id = str(location_id or '').strip() or None
    normalized_sublocation_id = str(sublocation_id or '').strip() or None

    if normalized_location_id:
        space_row = conn.execute(
            text("SELECT id, household_id FROM spaces WHERE id = :id LIMIT 1"),
            {'id': normalized_location_id},
        ).mappings().first()
        if not space_row or str(space_row.get('household_id') or '') != str(household_id):
            raise HTTPException(status_code=400, detail='Standaardruimte is ongeldig voor dit huishouden')

    if normalized_sublocation_id:
        sublocation_row = conn.execute(
            text("""
                SELECT sl.id, sl.space_id, s.household_id
                FROM sublocations sl
                LEFT JOIN spaces s ON s.id = sl.space_id
                WHERE sl.id = :id
                LIMIT 1
            """),
            {'id': normalized_sublocation_id},
        ).mappings().first()
        if not sublocation_row or str(sublocation_row.get('household_id') or '') != str(household_id):
            raise HTTPException(status_code=400, detail='Standaardsublocatie is ongeldig voor dit huishouden')
        parent_space_id = str(sublocation_row.get('space_id') or '').strip() or None
        if normalized_location_id and parent_space_id and parent_space_id != normalized_location_id:
            raise HTTPException(status_code=400, detail='Standaardsublocatie hoort niet bij de gekozen standaardruimte')
        if not normalized_location_id:
            normalized_location_id = parent_space_id

    return normalized_location_id, normalized_sublocation_id


def get_household_article_settings(conn, household_id: str, household_article_id: str) -> dict:
    article_row = get_household_article_row_by_id(conn, household_id, household_article_id)
    if not article_row:
        raise HTTPException(status_code=404, detail='Artikel niet gevonden')

    settings_rows = conn.execute(
        text("""
            SELECT setting_key, setting_value
            FROM household_article_settings
            WHERE household_article_id = :household_article_id
        """),
        {'household_article_id': str(household_article_id)},
    ).mappings().all()
    settings_map = {str(row.get('setting_key') or ''): _parse_json_setting_value(row.get('setting_value')) for row in settings_rows}

    note_row = conn.execute(
        text("""
            SELECT note, updated_at, created_at
            FROM household_article_notes
            WHERE household_article_id = :household_article_id
            LIMIT 1
        """),
        {'household_article_id': str(household_article_id)},
    ).mappings().first()

    default_location_id = str(settings_map.get('default_location_id') or '').strip() or None
    default_sublocation_id = str(settings_map.get('default_sublocation_id') or '').strip() or None
    location_payload = build_resolved_location_payload(conn, household_id, default_location_id, default_sublocation_id)

    return {
        'household_article_id': str(article_row.get('id') or household_article_id),
        'article_id': str(article_row.get('id') or household_article_id),
        'article_name': article_row.get('naam') or '',
        'settings': {
            'min_stock': float(article_row['min_stock']) if article_row.get('min_stock') is not None else None,
            'ideal_stock': float(article_row['ideal_stock']) if article_row.get('ideal_stock') is not None else None,
            'favorite_store': normalize_optional_text_field(article_row.get('favorite_store')),
            'average_price': float(article_row['average_price']) if article_row.get('average_price') is not None else None,
            'status': normalize_optional_text_field(article_row.get('status')) or 'active',
            'default_location_id': location_payload.get('space_id') if location_payload else default_location_id,
            'default_location_name': location_payload.get('space_name') if location_payload else None,
            'default_sublocation_id': location_payload.get('sublocation_id') if location_payload else default_sublocation_id,
            'default_sublocation_name': location_payload.get('sublocation_name') if location_payload else None,
            'auto_restock': bool(settings_map.get('auto_restock')) if settings_map.get('auto_restock') is not None else False,
            'packaging_unit': normalize_optional_text_field(settings_map.get('packaging_unit')),
            'packaging_quantity': float(settings_map['packaging_quantity']) if settings_map.get('packaging_quantity') not in (None, '') else None,
            'notes': (normalize_optional_text_field(note_row.get('note')) if note_row else None),
            'notes_updated_at': normalize_datetime(note_row.get('updated_at') or note_row.get('created_at')) if note_row else None,
        },
    }


def update_household_article_settings(conn, household_id: str, household_article_id: str, payload: HouseholdArticleSettingsUpdateRequest) -> dict:
    article_row = get_household_article_row_by_id(conn, household_id, household_article_id)
    if not article_row:
        raise HTTPException(status_code=404, detail='Artikel niet gevonden')

    min_stock = normalize_optional_numeric_field(payload.min_stock)
    ideal_stock = normalize_optional_numeric_field(payload.ideal_stock)
    average_price = normalize_optional_numeric_field(payload.average_price)
    favorite_store = normalize_optional_text_field(payload.favorite_store)
    status = normalize_optional_text_field(payload.status) or 'active'
    packaging_unit = normalize_optional_text_field(payload.packaging_unit)
    packaging_quantity = normalize_optional_numeric_field(payload.packaging_quantity)
    notes = normalize_optional_text_field(payload.notes)
    auto_restock = _normalize_settings_bool(payload.auto_restock)

    if min_stock is not None and ideal_stock is not None and min_stock > ideal_stock:
        raise HTTPException(status_code=400, detail='Minimumvoorraad mag niet groter zijn dan streefvoorraad')
    if average_price is not None and average_price < 0:
        raise HTTPException(status_code=400, detail='Prijsindicatie mag niet negatief zijn')
    if packaging_quantity is not None and packaging_quantity <= 0:
        raise HTTPException(status_code=400, detail='Verpakkingshoeveelheid moet groter zijn dan 0')
    if status not in {'active', 'inactive'}:
        raise HTTPException(status_code=400, detail='Status moet active of inactive zijn')

    default_location_id, default_sublocation_id = validate_household_article_location_setting(
        conn,
        household_id,
        payload.default_location_id,
        payload.default_sublocation_id,
    )

    conn.execute(
        text("""
            UPDATE household_articles
            SET min_stock = :min_stock,
                ideal_stock = :ideal_stock,
                favorite_store = :favorite_store,
                average_price = :average_price,
                status = :status,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :household_article_id AND household_id = :household_id
        """),
        {
            'min_stock': min_stock,
            'ideal_stock': ideal_stock,
            'favorite_store': favorite_store,
            'average_price': average_price,
            'status': status,
            'household_article_id': str(household_article_id),
            'household_id': str(household_id),
        },
    )

    settings_payload = {
        'default_location_id': default_location_id,
        'default_sublocation_id': default_sublocation_id,
        'auto_restock': auto_restock if auto_restock is not None else False,
        'packaging_unit': packaging_unit,
        'packaging_quantity': packaging_quantity,
    }
    for setting_key in HOUSEHOLD_ARTICLE_SETTINGS_ALLOWED_KEYS:
        setting_value = settings_payload.get(setting_key)
        conn.execute(
            text("""
                INSERT INTO household_article_settings (id, household_article_id, setting_key, setting_value, created_at, updated_at)
                VALUES (:id, :household_article_id, :setting_key, :setting_value, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(household_article_id, setting_key)
                DO UPDATE SET setting_value = excluded.setting_value, updated_at = CURRENT_TIMESTAMP
            """),
            {
                'id': str(uuid.uuid4()),
                'household_article_id': str(household_article_id),
                'setting_key': setting_key,
                'setting_value': json.dumps(setting_value),
            },
        )

    if notes is None:
        conn.execute(
            text("DELETE FROM household_article_notes WHERE household_article_id = :household_article_id"),
            {'household_article_id': str(household_article_id)},
        )
    else:
        conn.execute(
            text("""
                INSERT INTO household_article_notes (id, household_article_id, note, created_at, updated_at)
                VALUES (:id, :household_article_id, :note, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(household_article_id)
                DO UPDATE SET note = excluded.note, updated_at = CURRENT_TIMESTAMP
            """),
            {
                'id': str(uuid.uuid4()),
                'household_article_id': str(household_article_id),
                'note': notes,
            },
        )

    return get_household_article_settings(conn, household_id, household_article_id)


def build_household_article_detail_service(conn, household_id: str, household_article_id: str) -> dict:
    details = get_household_article_details(conn, household_id, article_id=household_article_id)
    resolved_household_article_id = str(details.get("article_id") or details.get("id") or household_article_id)
    inventory_rows = get_household_article_inventory_rows(conn, household_id, resolved_household_article_id)
    event_rows = get_household_article_event_rows(conn, household_id, resolved_household_article_id)
    settings_payload = get_household_article_settings(conn, household_id, resolved_household_article_id)
    price_summary = build_household_article_price_summary(conn, household_id, resolved_household_article_id, details.get("global_product_id"))
    return {
        **details,
        "household_article_id": resolved_household_article_id,
        "inventory": inventory_rows,
        "locations": inventory_rows,
        "events": event_rows,
        "product": details.get("product_details") or {},
        "settings": settings_payload.get("settings") or {},
        "price_history": price_summary.get("price_history") or [],
        "price_summary": {key: value for key, value in price_summary.items() if key != "price_history"},
    }



def resolve_household_article_detail_service(conn, household_id: str, article_id: str | None = None, article_name: str | None = None, *, create_if_missing: bool = False) -> dict:
    resolved_row = resolve_household_article_reference(
        conn,
        household_id,
        article_id=article_id,
        article_name=article_name,
        create_if_missing=create_if_missing,
    )
    if not resolved_row:
        raise HTTPException(status_code=404, detail='Artikel niet gevonden')
    return build_household_article_detail_service(conn, household_id, str(resolved_row.get('id') or ''))



def build_household_article_resource(conn, household_id: str, household_article_id: str) -> dict:
    return build_household_article_detail_service(conn, household_id, household_article_id)



def round_up_quantity_to_packaging(quantity: float, packaging_quantity: float | None) -> float:
    normalized_quantity = float(quantity or 0)
    normalized_packaging = normalize_optional_numeric_field(packaging_quantity)
    if normalized_quantity <= 0:
        return 0.0
    if normalized_packaging is None or normalized_packaging <= 0:
        return normalized_quantity
    rounded = math.ceil(normalized_quantity / normalized_packaging) * normalized_packaging
    return float(round(rounded, 6))


ALMOST_OUT_DATA_STATE_OK = 'ok'
ALMOST_OUT_DATA_STATE_NO_MIN_STOCK = 'no_min_stock'
ALMOST_OUT_DATA_STATE_INCONSISTENT = 'inconsistent_data'


def calculate_inventory_total_quantity_from_rows(inventory_rows: list[dict[str, Any]]) -> float:
    total = 0.0
    for row in inventory_rows or []:
        try:
            total += float(row.get('quantity') or 0)
        except (TypeError, ValueError):
            continue
    return float(round(total, 6))


def calculate_inventory_event_net_quantity(event_rows: list[dict[str, Any]]) -> float:
    total = 0.0
    for row in event_rows or []:
        try:
            total += float(row.get('quantity') or 0)
        except (TypeError, ValueError):
            continue
    return float(round(total, 6))


def get_household_product_member_article_rows(conn, household_id: str, household_article_id: str, global_product_id: str | None = None) -> list[dict[str, Any]]:
    normalized_household_id = str(household_id or '').strip()
    normalized_article_id = str(household_article_id or '').strip()
    normalized_global_product_id = str(global_product_id or '').strip()
    if normalized_global_product_id:
        rows = conn.execute(
            text(
                """
                SELECT id, household_id, naam, custom_name, global_product_id, status
                FROM household_articles
                WHERE household_id = :household_id
                  AND global_product_id = :global_product_id
                  AND COALESCE(status, 'active') = 'active'
                ORDER BY lower(trim(COALESCE(custom_name, naam))) ASC, id ASC
                """
            ),
            {'household_id': normalized_household_id, 'global_product_id': normalized_global_product_id},
        ).mappings().all()
        if rows:
            return [dict(row) for row in rows]

    article_row = get_household_article_row_by_id(conn, normalized_household_id, normalized_article_id)
    if not article_row:
        raise HTTPException(status_code=404, detail='Artikel niet gevonden')
    return [dict(article_row)]



def get_household_product_inventory_rows(conn, household_id: str, household_article_id: str, global_product_id: str | None = None) -> list[dict]:
    member_rows = get_household_product_member_article_rows(conn, household_id, household_article_id, global_product_id)
    household_article_ids = []
    article_names = []
    for row in member_rows:
        article_id = str(row.get('id') or '').strip()
        article_name = str(row.get('naam') or '').strip()
        if article_id:
            household_article_ids.append(article_id)
        if article_name:
            article_names.append(article_name)
    if not article_names:
        return []
    rows = conn.execute(
        text(
            """
            SELECT
              i.id,
              i.naam AS article_name,
              i.aantal AS quantity,
              i.household_id,
              i.space_id,
              i.sublocation_id,
              COALESCE(s.naam, '') AS space_name,
              COALESCE(sl.naam, '') AS sublocation_name,
              COALESCE(i.status, 'active') AS status
            FROM inventory i
            LEFT JOIN spaces s ON s.id = i.space_id
            LEFT JOIN sublocations sl ON sl.id = i.sublocation_id
            WHERE i.household_id = :household_id
              AND lower(trim(i.naam)) IN :article_names
              AND COALESCE(i.status, 'active') = 'active'
              AND COALESCE(i.aantal, 0) > 0
            ORDER BY datetime(COALESCE(i.updated_at, i.created_at)) DESC, i.id ASC
            """
        ).bindparams(bindparam('article_names', expanding=True)),
        {
            'household_id': str(household_id),
            'article_names': [name.strip().lower() for name in article_names if name.strip()],
        },
    ).mappings().all()
    primary_article_id = household_article_ids[0] if household_article_ids else str(household_article_id or '').strip()
    return [
        {
            'id': row['id'],
            'household_article_id': primary_article_id,
            'article_id': primary_article_id,
            'product_scope_article_ids': household_article_ids,
            'article_name': row['article_name'],
            'quantity': float(row['quantity']) if row.get('quantity') is not None else 0,
            'aantal': float(row['quantity']) if row.get('quantity') is not None else 0,
            'space_id': row['space_id'] or '',
            'sublocation_id': row['sublocation_id'] or '',
            'space_name': row['space_name'] or '',
            'locatie': row['space_name'] or '',
            'sublocation_name': row['sublocation_name'] or '',
            'sublocatie': row['sublocation_name'] or '',
            'location_label': ' / '.join(part for part in [row['space_name'] or '', row['sublocation_name'] or ''] if part),
            'status': row['status'] or 'active',
        }
        for row in rows
    ]



def get_household_product_event_rows(conn, household_id: str, household_article_id: str, global_product_id: str | None = None) -> list[dict]:
    member_rows = get_household_product_member_article_rows(conn, household_id, household_article_id, global_product_id)
    household_article_ids = []
    article_names = []
    for row in member_rows:
        article_id = str(row.get('id') or '').strip()
        article_name = str(row.get('naam') or '').strip()
        if article_id:
            household_article_ids.append(article_id)
        if article_name:
            article_names.append(article_name)
    if not household_article_ids and not article_names:
        return []
    rows = conn.execute(
        text(
            """
            SELECT
              id,
              article_id,
              article_name,
              location_id,
              location_label,
              event_type,
              quantity,
              old_quantity,
              new_quantity,
              source,
              note,
              created_at,
              purchase_date,
              supplier_name,
              price,
              currency,
              article_number,
              barcode
            FROM inventory_events
            WHERE household_id = :household_id
              AND (
                article_id IN :article_ids
                OR lower(trim(article_name)) IN :article_names
              )
            ORDER BY datetime(created_at) DESC, id DESC
            """
        ).bindparams(
            bindparam('article_ids', expanding=True),
            bindparam('article_names', expanding=True),
        ),
        {
            'household_id': str(household_id),
            'article_ids': household_article_ids or [''],
            'article_names': [name.strip().lower() for name in article_names if name.strip()] or [''],
        },
    ).mappings().all()
    return [dict(row) for row in rows]



def compute_household_product_prediction(conn, household_id: str, household_article_id: str, article_name: str, *, current_quantity: float, prediction_days: int, global_product_id: str | None = None) -> dict | None:
    member_rows = get_household_product_member_article_rows(conn, household_id, household_article_id, global_product_id)
    article_ids = [str(row.get('id') or '').strip() for row in member_rows if str(row.get('id') or '').strip()]
    article_names = [str(row.get('naam') or '').strip() for row in member_rows if str(row.get('naam') or '').strip()]
    if not article_ids and not article_names:
        return None

    purchase_rows = conn.execute(
        text(
            """
            SELECT article_id, article_name, quantity, purchase_date, created_at
            FROM inventory_events
            WHERE household_id = :household_id
              AND COALESCE(quantity, 0) > 0
              AND event_type IN ('purchase', 'auto_repurchase')
              AND (
                    article_id IN :article_ids
                    OR lower(trim(article_name)) IN :article_names
                  )
            ORDER BY datetime(COALESCE(purchase_date, created_at)) ASC, created_at ASC, id ASC
            """
        ).bindparams(
            bindparam('article_ids', expanding=True),
            bindparam('article_names', expanding=True),
        ),
        {
            'household_id': str(household_id),
            'article_ids': article_ids or [''],
            'article_names': [name.strip().lower() for name in article_names if name.strip()] or [''],
        },
    ).mappings().all()

    timestamps: list[datetime] = []
    purchase_quantities: list[float] = []
    for row in purchase_rows:
        dt = _parse_event_datetime_to_utc(row.get('purchase_date')) or _parse_event_datetime_to_utc(row.get('created_at'))
        if dt is None:
            continue
        timestamps.append(dt)
        quantity = normalize_optional_numeric_field(row.get('quantity'))
        if quantity is not None and quantity > 0:
            purchase_quantities.append(float(quantity))

    if len(timestamps) < 2:
        return None

    interval_days: list[float] = []
    for previous, current in zip(timestamps, timestamps[1:]):
        delta_days = (current - previous).total_seconds() / 86400.0
        if delta_days > 0:
            interval_days.append(delta_days)
    if not interval_days:
        return None

    average_purchase_interval_days = sum(interval_days) / len(interval_days)
    last_purchase_at = timestamps[-1]
    now = datetime.now(timezone.utc)
    days_since_last_purchase = max((now - last_purchase_at).total_seconds() / 86400.0, 0.0)
    predicted_days_until_depletion = max(average_purchase_interval_days - days_since_last_purchase, 0.0)
    predicted_depletion_at = now + timedelta(days=predicted_days_until_depletion)
    average_purchase_quantity = (sum(purchase_quantities) / len(purchase_quantities)) if purchase_quantities else None

    return {
        'prediction_available': True,
        'prediction_basis': 'average_purchase_interval',
        'prediction_scope': 'global_product' if str(global_product_id or '').strip() else 'household_article',
        'average_purchase_interval_days': float(round(average_purchase_interval_days, 3)),
        'average_purchase_quantity': float(round(average_purchase_quantity, 3)) if average_purchase_quantity is not None else None,
        'last_purchase_at': last_purchase_at.isoformat(),
        'days_since_last_purchase': float(round(days_since_last_purchase, 3)),
        'predicted_days_until_depletion': float(round(predicted_days_until_depletion, 3)),
        'predicted_depletion_date': predicted_depletion_at.date().isoformat(),
        'predicted_depletion_at': predicted_depletion_at.isoformat(),
        'prediction_threshold_days': int(prediction_days),
        'prediction_triggered': predicted_days_until_depletion <= float(prediction_days),
        'current_quantity_at_evaluation': float(round(current_quantity, 6)),
        'purchase_event_count': len(timestamps),
    }



def evaluate_household_article_almost_out(conn, household_id: str, article_row: Mapping[str, Any], household_settings: dict[str, Any] | None = None, article_settings_map: dict[str, Any] | None = None) -> dict[str, Any]:
    household_article_id = str(article_row.get('id') or '').strip()
    article_name = str(article_row.get('naam') or '').strip()
    global_product_id = str(article_row.get('global_product_id') or '').strip()
    if not household_article_id or not article_name:
        raise ValueError('Household article id en naam zijn verplicht voor almost-out evaluatie')

    household_settings = household_settings or get_household_almost_out_settings(conn, household_id)
    article_settings_map = article_settings_map or {}
    prediction_enabled = bool(household_settings.get('prediction_enabled'))
    prediction_days = int(household_settings.get('prediction_days') or 0)
    policy_mode = normalize_almost_out_policy_mode(household_settings.get('policy_mode'))

    min_stock = normalize_optional_numeric_field(article_row.get('min_stock'))
    ideal_stock = normalize_optional_numeric_field(article_row.get('ideal_stock'))
    if ideal_stock is None and min_stock is not None:
        ideal_stock = float(min_stock) + 1.0

    inventory_rows = get_household_product_inventory_rows(conn, household_id, household_article_id, global_product_id)
    event_rows = get_household_product_event_rows(conn, household_id, household_article_id, global_product_id)
    current_quantity = calculate_inventory_total_quantity_from_rows(inventory_rows)
    event_net_quantity = calculate_inventory_event_net_quantity(event_rows)
    has_event_history = len(event_rows) > 0
    data_state = ALMOST_OUT_DATA_STATE_OK
    data_state_message = None
    if min_stock is None:
        data_state = ALMOST_OUT_DATA_STATE_NO_MIN_STOCK
        data_state_message = 'Artikel heeft geen minimumvoorraad en valt daarom buiten almost-out signalering.'
    elif current_quantity < 0:
        data_state = ALMOST_OUT_DATA_STATE_INCONSISTENT
        data_state_message = 'Actuele voorraad is negatief en daarom inconsistent.'
    elif has_event_history and abs(current_quantity - event_net_quantity) > 1e-9:
        data_state = ALMOST_OUT_DATA_STATE_INCONSISTENT
        data_state_message = 'Actuele voorraad wijkt af van netto inventory-events.'

    stock_triggered = (data_state == ALMOST_OUT_DATA_STATE_OK and min_stock is not None and current_quantity <= float(min_stock))

    prediction_payload = None
    prediction_triggered = False
    if data_state != ALMOST_OUT_DATA_STATE_INCONSISTENT and prediction_enabled and prediction_days > 0:
        prediction_payload = compute_household_product_prediction(
            conn,
            household_id,
            household_article_id,
            article_name,
            current_quantity=current_quantity,
            prediction_days=prediction_days,
            global_product_id=global_product_id,
        )
        prediction_triggered = bool(prediction_payload and prediction_payload.get('prediction_triggered'))

    include_item = False
    trigger_type = None
    effective_policy_mode = policy_mode
    if data_state == ALMOST_OUT_DATA_STATE_INCONSISTENT:
        include_item = False
    elif policy_mode == ALMOST_OUT_POLICY_OVERRIDE:
        if prediction_payload:
            include_item = prediction_triggered
            trigger_type = 'predicted' if prediction_triggered else None
        else:
            include_item = stock_triggered
            trigger_type = 'stock' if stock_triggered else None
            effective_policy_mode = 'override_fallback_to_stock'
    else:
        if stock_triggered:
            include_item = True
            trigger_type = 'stock'
        elif prediction_triggered:
            include_item = True
            trigger_type = 'predicted'

    packaging_unit = normalize_optional_text_field(article_settings_map.get('packaging_unit'))
    packaging_quantity = normalize_optional_numeric_field(article_settings_map.get('packaging_quantity'))
    fallback_ideal_stock = float(ideal_stock) if ideal_stock is not None else ((float(min_stock) + 1.0) if min_stock is not None else 1.0)
    amount_to_buy = max(fallback_ideal_stock - current_quantity, 0.0)
    amount_to_buy = round_up_quantity_to_packaging(amount_to_buy, packaging_quantity)

    default_location_id = normalize_optional_text_field(article_settings_map.get('default_location_id'))
    default_sublocation_id = normalize_optional_text_field(article_settings_map.get('default_sublocation_id'))
    default_location = build_resolved_location_payload(conn, household_id, default_location_id, default_sublocation_id) if (default_location_id or default_sublocation_id) else None
    primary_inventory_row = inventory_rows[0] if inventory_rows else None

    item_payload = {
        'household_article_id': household_article_id,
        'article_id': household_article_id,
        'article_name': article_name,
        'display_name': normalize_optional_text_field(article_row.get('custom_name')) or article_name,
        'household_article_name': normalize_optional_text_field(article_row.get('custom_name')) or article_name,
        'product_name': normalize_optional_text_field(article_row.get('product_name')) or article_name,
        'global_product_id': global_product_id or None,
        'product_anchor': 'global_product' if global_product_id else 'household_article',
        'current_quantity': current_quantity,
        'huidige_voorraad': current_quantity,
        'min_stock': float(min_stock) if min_stock is not None else None,
        'minimumvoorraad': float(min_stock) if min_stock is not None else None,
        'ideal_stock': float(fallback_ideal_stock),
        'streefvoorraad': float(fallback_ideal_stock),
        'amount_to_buy': float(round(amount_to_buy, 6)),
        'aantal_te_kopen': float(round(amount_to_buy, 6)),
        'favorite_store': normalize_optional_text_field(article_row.get('favorite_store')),
        'packaging_unit': packaging_unit,
        'verpakkingseenheid': packaging_unit,
        'packaging_quantity': packaging_quantity,
        'verpakkingshoeveelheid': packaging_quantity,
        'status': 'active',
        'default_location': default_location,
        'primary_location': {
            'space_id': primary_inventory_row.get('space_id') if primary_inventory_row else None,
            'space_name': primary_inventory_row.get('space_name') if primary_inventory_row else None,
            'sublocation_id': primary_inventory_row.get('sublocation_id') if primary_inventory_row else None,
            'sublocation_name': primary_inventory_row.get('sublocation_name') if primary_inventory_row else None,
            'location_label': primary_inventory_row.get('location_label') if primary_inventory_row else None,
        } if primary_inventory_row else None,
        'inventory_rows': inventory_rows,
        'event_rows': event_rows,
        'event_net_quantity': event_net_quantity,
        'has_event_history': has_event_history,
        'data_state': data_state,
        'data_state_message': data_state_message,
        'include_in_almost_out': bool(include_item),
        'trigger_type': trigger_type,
        'stock_triggered': bool(stock_triggered),
        'prediction_triggered': bool(prediction_triggered),
        'prediction_enabled': prediction_enabled,
        'prediction_days': prediction_days,
        'policy_mode': effective_policy_mode,
        'base_policy_mode': policy_mode,
        'business_rules': {
            'threshold_rule': 'current_quantity <= min_stock',
            'multi_location_rule': 'sum_inventory_rows',
            'null_min_stock_rule': 'exclude_from_almost_out',
            'inconsistent_data_rule': 'block_from_almost_out',
        },
    }
    if prediction_payload:
        item_payload.update(prediction_payload)
    else:
        item_payload.update({
            'prediction_available': False,
            'prediction_basis': None,
            'average_purchase_interval_days': None,
            'average_purchase_quantity': None,
            'last_purchase_at': None,
            'days_since_last_purchase': None,
            'predicted_days_until_depletion': None,
            'predicted_depletion_date': None,
            'predicted_depletion_at': None,
            'prediction_threshold_days': prediction_days if prediction_enabled else None,
            'purchase_event_count': 0,
        })
    return item_payload


def build_almost_out_items(conn, household_id: str) -> list[dict]:
    household_settings = get_household_almost_out_settings(conn, household_id)
    article_rows = conn.execute(
        text(
            """
            SELECT ha.id, ha.household_id, ha.naam, ha.custom_name, ha.min_stock, ha.ideal_stock, ha.favorite_store, ha.status,
                   ha.global_product_id,
                   COALESCE(gp.name, '') AS product_name
            FROM household_articles ha
            LEFT JOIN global_products gp ON gp.id = ha.global_product_id
            WHERE ha.household_id = :household_id
              AND COALESCE(ha.status, 'active') = 'active'
            ORDER BY lower(trim(COALESCE(ha.custom_name, ha.naam))) ASC, ha.id ASC
            """
        ),
        {'household_id': str(household_id)},
    ).mappings().all()

    if not article_rows:
        return []

    article_ids = [str(row.get('id') or '').strip() for row in article_rows if str(row.get('id') or '').strip()]
    settings_map_by_article: dict[str, dict[str, Any]] = {}
    if article_ids:
        settings_rows = conn.execute(
            text(
                """
                SELECT household_article_id, setting_key, setting_value
                FROM household_article_settings
                WHERE household_article_id IN :article_ids
                """
            ).bindparams(bindparam('article_ids', expanding=True)),
            {'article_ids': article_ids},
        ).mappings().all()
        for row in settings_rows:
            article_id = str(row.get('household_article_id') or '').strip()
            if not article_id:
                continue
            bucket = settings_map_by_article.setdefault(article_id, {})
            bucket[str(row.get('setting_key') or '').strip()] = _parse_json_setting_value(row.get('setting_value'))

    items: list[dict] = []
    for article_row in article_rows:
        evaluation = evaluate_household_article_almost_out(
            conn,
            household_id,
            article_row,
            household_settings=household_settings,
            article_settings_map=settings_map_by_article.get(str(article_row.get('id') or '').strip(), {}),
        )
        if evaluation.get('include_in_almost_out'):
            items.append(evaluation)

    return items


def get_household_article_details_for_inventory(conn, household_id: str, inventory_id: str) -> dict:
    normalized_reference_id = str(inventory_id or '').strip()
    if not normalized_reference_id:
        raise HTTPException(status_code=400, detail='Voorraad-id is verplicht')

    resolved_row = resolve_household_article_reference(conn, household_id, article_id=normalized_reference_id, create_if_missing=False)
    if not resolved_row:
        raise HTTPException(status_code=404, detail='Artikel niet gevonden')

    details = build_household_article_resource(conn, household_id, str(resolved_row.get('id') or ''))
    details['inventory_id'] = None if normalized_reference_id == str(resolved_row.get('id') or '') else normalized_reference_id
    return details

def update_household_article_external_link(conn, household_id: str, article_name: str, *, barcode: str | None = None, article_number: str | None = None, source: str | None = None) -> dict:
    normalized_name = normalize_household_article_name(article_name)
    if not normalized_name:
        raise HTTPException(status_code=400, detail='Artikelnaam is verplicht')
    ensure_household_article(conn, household_id, normalized_name)
    normalized_barcode = None
    if barcode is not None and str(barcode).strip() != '':
        normalized_barcode = normalize_barcode_value(barcode)
    normalized_article_number = normalize_optional_text_field(article_number)
    normalized_source = normalize_optional_text_field(source) or ('manual' if (normalized_barcode or normalized_article_number) else None)
    if normalized_barcode:
        existing_barcode_row = get_household_article_by_barcode(conn, household_id, normalized_barcode)
        if existing_barcode_row and str(existing_barcode_row.get('naam') or '').strip().lower() != normalized_name.lower():
            raise HTTPException(status_code=409, detail='Barcode is al gekoppeld aan een ander artikel')
    conn.execute(
        text(
            """
            UPDATE household_articles
            SET barcode = :barcode,
                article_number = :article_number,
                external_source = :external_source,
                updated_at = CURRENT_TIMESTAMP
            WHERE household_id = :household_id AND lower(trim(naam)) = lower(trim(:naam))
            """
        ),
        {
            'barcode': normalized_barcode,
            'article_number': normalized_article_number,
            'external_source': normalized_source,
            'household_id': str(household_id),
            'naam': normalized_name,
        },
    )
    row = get_household_article_row_by_name(conn, household_id, normalized_name)
    if row:
        if normalized_barcode:
            upsert_product_identity(conn, str(row.get('id')), 'gtin', normalized_barcode, normalized_source or 'manual', confidence_score=1.0, is_primary=True)
            ensure_household_article_global_product_link(conn, str(row.get('id')), normalized_barcode)
            ensure_article_product_enrichment(conn, str(row.get('id')), normalized_barcode, force_refresh=True)
        else:
            ensure_household_article_global_product_link(conn, str(row.get('id')))
    return get_household_article_details(conn, household_id, normalized_name)


def update_household_article_details_by_id(conn, household_id: str, household_article_id: str, payload: ArticleHouseholdDetailsUpdateRequest) -> dict:
    resolved_article_id = str(household_article_id or '').strip()
    if not resolved_article_id:
        raise HTTPException(status_code=400, detail='household_article_id is verplicht')
    article_row = get_household_article_row_by_id(conn, household_id, resolved_article_id)
    if not article_row:
        raise HTTPException(status_code=404, detail='Artikel niet gevonden')

    custom_name = normalize_optional_text_field(payload.custom_name)
    article_type = normalize_optional_text_field(payload.article_type)
    notes = normalize_optional_text_field(payload.notes)
    favorite_store = normalize_optional_text_field(payload.favorite_store)
    min_stock = normalize_optional_numeric_field(payload.min_stock)
    ideal_stock = normalize_optional_numeric_field(payload.ideal_stock)
    barcode = normalize_barcode_value(payload.barcode) if payload.barcode not in (None, '') else None
    article_number = normalize_optional_text_field(payload.article_number)
    source = normalize_optional_text_field(payload.source) or ('manual' if (barcode or article_number) else None)
    if min_stock is not None and ideal_stock is not None and min_stock > ideal_stock:
        raise HTTPException(status_code=400, detail='Minimumvoorraad mag niet groter zijn dan streefvoorraad')
    if barcode:
        existing_barcode_row = get_household_article_by_barcode(conn, household_id, barcode)
        if existing_barcode_row and str(existing_barcode_row.get('id') or '').strip() != resolved_article_id:
            raise HTTPException(status_code=409, detail='Barcode is al gekoppeld aan een ander artikel')

    conn.execute(
        text(
            """
            UPDATE household_articles
            SET custom_name = :custom_name,
                article_type = :article_type,
                notes = :notes,
                min_stock = :min_stock,
                ideal_stock = :ideal_stock,
                favorite_store = :favorite_store,
                barcode = COALESCE(:barcode, barcode),
                article_number = COALESCE(:article_number, article_number),
                external_source = COALESCE(:source, external_source),
                updated_at = CURRENT_TIMESTAMP
            WHERE household_id = :household_id AND id = :household_article_id
            """
        ),
        {
            'custom_name': custom_name,
            'article_type': article_type,
            'notes': notes,
            'min_stock': min_stock,
            'ideal_stock': ideal_stock,
            'favorite_store': favorite_store,
            'barcode': barcode,
            'article_number': article_number,
            'source': source,
            'household_id': str(household_id),
            'household_article_id': resolved_article_id,
        },
    )
    refreshed_row = get_household_article_row_by_id(conn, household_id, resolved_article_id)
    if refreshed_row:
        refreshed_article_id = str(refreshed_row.get('id') or '')
        if barcode:
            clear_primary_barcode_identity_for_article(conn, refreshed_article_id)
            upsert_product_identity(conn, refreshed_article_id, 'gtin', barcode, source or 'manual', confidence_score=1.0, is_primary=True)
            ensure_household_article_global_product_link(conn, refreshed_article_id, barcode)
            ensure_article_product_enrichment(conn, refreshed_article_id, barcode, force_refresh=True)
        else:
            clear_primary_barcode_identity_for_article(conn, refreshed_article_id)
            conn.execute(text(
                """
                UPDATE product_enrichments
                SET lookup_status = CASE WHEN lookup_status = 'found' THEN 'skipped' ELSE lookup_status END,
                    last_lookup_message = CASE
                        WHEN COALESCE(trim(last_lookup_message), '') = '' THEN 'Barcode verwijderd; eerdere verrijking is alleen nog historisch'
                        ELSE last_lookup_message
                    END,
                    last_lookup_at = CURRENT_TIMESTAMP,
                    normalized_barcode = NULL
                WHERE household_article_id = :household_article_id AND global_product_id IS NULL
                """
            ), {'household_article_id': refreshed_article_id})
            ensure_household_article_global_product_link(conn, refreshed_article_id)
            if article_number:
                write_product_enrichment_audit(conn, refreshed_article_id, source or 'manual', 'identify', 'skipped', message='Extern artikelnummer opgeslagen zonder barcode')
    return get_household_article_details(conn, household_id, str((refreshed_row or article_row).get('naam') or '').strip())


def update_household_article_details(conn, household_id: str, article_name: str, payload: ArticleHouseholdDetailsUpdateRequest) -> dict:
    normalized_name = normalize_household_article_name(article_name)
    if not normalized_name:
        raise HTTPException(status_code=400, detail='Artikelnaam is verplicht')
    article_row = get_household_article_row_by_name(conn, household_id, normalized_name)
    if not article_row:
        ensure_household_article(conn, household_id, normalized_name)
        article_row = get_household_article_row_by_name(conn, household_id, normalized_name)
    if not article_row:
        raise HTTPException(status_code=404, detail='Artikel niet gevonden')
    return update_household_article_details_by_id(conn, household_id, str(article_row.get('id') or ''), payload)


def archive_household_article_by_id(conn, household_id: str, household_article_id: str, reason: str | None = None) -> dict:
    resolved_article_id = str(household_article_id or '').strip()
    article_row = get_household_article_row_by_id(conn, household_id, resolved_article_id)
    if not article_row:
        raise HTTPException(status_code=404, detail='Artikel niet gevonden')
    resolved_reason = normalize_optional_text_field(reason) or 'Handmatig gearchiveerd vanuit Artikeldetail'
    inventory_rows = conn.execute(text(
        """
        SELECT i.id, i.household_article_id, i.naam, i.aantal, i.space_id, i.sublocation_id,
               COALESCE(s.naam, '') AS space_name,
               COALESCE(sl.naam, '') AS sublocation_name
        FROM inventory i
        LEFT JOIN spaces s ON s.id = i.space_id
        LEFT JOIN sublocations sl ON sl.id = i.sublocation_id
        WHERE i.household_id = :household_id
          AND i.household_article_id = :household_article_id
          AND COALESCE(i.status, 'active') = 'active'
        ORDER BY i.updated_at DESC, i.created_at ASC, i.id ASC
        """
    ), {'household_id': household_id, 'household_article_id': resolved_article_id}).mappings().all()
    archived_ids = []
    archived_quantity = 0
    for row in inventory_rows:
        old_quantity = int(row.get('aantal') or 0)
        archived_quantity += old_quantity
        conn.execute(text(
            """
            UPDATE inventory
            SET status = 'archived',
                archived_at = CURRENT_TIMESTAMP,
                archive_reason = :reason,
                aantal = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
            """
        ), {'id': row['id'], 'reason': resolved_reason})
        create_inventory_event(
            conn,
            household_id=household_id,
            article_id=str(row.get('id') or ''),
            article_name=str(row.get('naam') or article_row.get('naam') or ''),
            resolved_location={
                'location_id': row.get('sublocation_id') or row.get('space_id'),
                'space_id': row.get('space_id'),
                'sublocation_id': row.get('sublocation_id'),
                'location_label': ' / '.join(part for part in [row.get('space_name') or '', row.get('sublocation_name') or ''] if part),
            },
            event_type='archive',
            quantity=0,
            source='article_archive',
            note=resolved_reason,
            old_quantity=old_quantity,
            new_quantity=0,
        )
        archived_ids.append(str(row.get('id') or ''))
    conn.execute(text("UPDATE household_articles SET status = 'archived', updated_at = CURRENT_TIMESTAMP WHERE household_id = :household_id AND id = :household_article_id"), {'household_id': household_id, 'household_article_id': resolved_article_id})
    return {
        'status': 'ok',
        'household_article_id': resolved_article_id,
        'article_name': str(article_row.get('naam') or ''),
        'archived_inventory_ids': archived_ids,
        'archived_count': len(archived_ids),
        'archived_quantity': archived_quantity,
        'archive_reason': resolved_reason,
    }


def delete_household_article_by_id(conn, household_id: str, household_article_id: str, reason: str | None = None, force: bool = False) -> dict:
    resolved_article_id = str(household_article_id or '').strip()
    article_row = get_household_article_row_by_id(conn, household_id, resolved_article_id)
    if not article_row:
        raise HTTPException(status_code=404, detail='Artikel niet gevonden')
    active_inventory = conn.execute(text("SELECT COUNT(*) FROM inventory WHERE household_id = :household_id AND household_article_id = :household_article_id AND COALESCE(status, 'active') = 'active' AND COALESCE(aantal, 0) > 0"), {'household_id': household_id, 'household_article_id': resolved_article_id}).scalar() or 0
    if active_inventory and not force:
        raise HTTPException(status_code=409, detail='Artikel heeft nog actieve voorraad; archiveer eerst of gebruik force')
    history_count = conn.execute(text("SELECT COUNT(*) FROM inventory_history WHERE household_id = :household_id AND household_article_id = :household_article_id"), {'household_id': household_id, 'household_article_id': resolved_article_id}).scalar() or 0
    if history_count and not force:
        raise HTTPException(status_code=409, detail='Artikel heeft nog voorraadhistorie; verwijderen zonder force is niet toegestaan')
    if active_inventory:
        archive_household_article_by_id(conn, household_id, resolved_article_id, reason or 'Force delete voorbereiding: archiveren')
    conn.execute(text("DELETE FROM household_article_settings WHERE household_article_id = :household_article_id"), {'household_article_id': resolved_article_id})
    conn.execute(text("DELETE FROM household_articles WHERE household_id = :household_id AND id = :household_article_id"), {'household_id': household_id, 'household_article_id': resolved_article_id})
    return {
        'status': 'ok',
        'deleted': True,
        'household_article_id': resolved_article_id,
        'article_name': str(article_row.get('naam') or ''),
        'reason': normalize_optional_text_field(reason),
        'forced': bool(force),
    }


def normalize_barcode_value(value: str | None) -> str:
    normalized = "".join(ch for ch in str(value or "").strip() if ch.isalnum())
    if len(normalized) < 4:
        raise ValueError("Barcode is verplicht")
    return normalized[:64]


def normalize_purchase_date(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    candidate = normalized.replace("/", "-")
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            parsed = datetime.strptime(candidate, fmt)
            return parsed.date().isoformat()
        except ValueError:
            continue
    raise ValueError("purchase_date moet een geldige datum zijn")


def user_can_write_inventory(context: dict) -> bool:
    return str(context.get("display_role") or "").strip().lower() != "viewer"


def get_global_product_row_by_barcode(conn, barcode: str | None):
    normalized_barcode = normalize_barcode_value(barcode) if barcode else None
    if not normalized_barcode:
        return None
    return conn.execute(
        text(
            """
            SELECT id, primary_gtin, name, brand, category, size_value, size_unit, source, status, created_at, updated_at
            FROM global_products
            WHERE primary_gtin = :primary_gtin
            LIMIT 1
            """
        ),
        {'primary_gtin': normalized_barcode},
    ).mappings().first()


def get_global_product_row_by_identity(conn, identity_value: str | None, identity_types: tuple[str, ...] | None = None):
    normalized_lookup = normalize_identity_lookup_value(identity_value)
    if not normalized_lookup:
        return None
    resolved_types = tuple(normalize_product_identity_type(value) for value in (identity_types or ('external_article_number', 'store_sku', 'gtin')))
    rows = conn.execute(
        text(
            """
            SELECT gp.id, gp.primary_gtin, gp.name, gp.brand, gp.category, gp.size_value, gp.size_unit, gp.source, gp.status, gp.created_at, gp.updated_at,
                   pi.identity_type, pi.identity_value
            FROM product_identities pi
            JOIN global_products gp ON gp.id = pi.global_product_id
            WHERE pi.global_product_id IS NOT NULL
            ORDER BY CASE WHEN pi.is_primary THEN 0 ELSE 1 END, datetime(pi.updated_at) DESC, pi.id DESC
            """
        )
    ).mappings().all()
    for row in rows:
        identity_type = normalize_product_identity_type(row.get('identity_type'))
        if identity_type not in resolved_types:
            continue
        stored_lookup = normalize_product_identity_value(identity_type, row.get('identity_value'))
        if stored_lookup == normalized_lookup:
            payload = dict(row)
            payload['identity_type'] = identity_type
            payload['identity_value'] = row.get('identity_value')
            return payload
    return None


def find_global_product_match_for_receipt_line(conn, barcode: str | None, article_name: str | None, brand: str | None = None, external_article_code: str | None = None):
    normalized_barcode = normalize_barcode_value(barcode) if barcode else None
    if normalized_barcode:
        by_barcode = get_global_product_row_by_barcode(conn, normalized_barcode)
        if by_barcode:
            payload = dict(by_barcode)
            payload['match_method'] = 'gtin:primary'
            payload['confidence_score'] = 1.0
            return payload
    normalized_external_article_code = normalize_identity_lookup_value(external_article_code or barcode)
    if normalized_external_article_code:
        by_identity = get_global_product_row_by_identity(conn, normalized_external_article_code)
        if by_identity:
            payload = dict(by_identity)
            identity_type = normalize_product_identity_type(by_identity.get('identity_type'))
            payload['match_method'] = f'identity:{identity_type}'
            payload['confidence_score'] = 0.95
            return payload
    normalized_name = normalize_household_article_name(article_name)
    normalized_brand = normalize_optional_text_field(brand)
    if not normalized_name:
        return None
    params = {'name': normalized_name}
    brand_clause = ''
    if normalized_brand:
        params['brand'] = normalized_brand
        brand_clause = " AND lower(trim(COALESCE(brand, ''))) = lower(trim(:brand))"
    row = conn.execute(
        text(
            f"""
            SELECT id, primary_gtin, name, brand, category, size_value, size_unit, source, status, created_at, updated_at
            FROM global_products
            WHERE lower(trim(name)) = lower(trim(:name)){brand_clause}
            ORDER BY CASE WHEN primary_gtin IS NOT NULL AND trim(primary_gtin) <> '' THEN 0 ELSE 1 END,
                     datetime(updated_at) DESC,
                     id DESC
            LIMIT 1
            """
        ),
        params,
    ).mappings().first()
    if not row:
        return None
    payload = dict(row)
    payload['match_method'] = 'text:name_brand' if normalized_brand else 'text:name'
    payload['confidence_score'] = 0.8 if normalized_brand else 0.75
    return payload


def find_household_article_for_global_product(conn, household_id: str, global_product_id: str | None):
    normalized_global_product_id = str(global_product_id or '').strip()
    if not normalized_global_product_id:
        return None
    row = conn.execute(
        text(
            """
            SELECT
              ha.id,
              ha.household_id,
              ha.naam,
              ha.consumable,
              ha.barcode,
              ha.article_number,
              ha.external_source,
              ha.custom_name,
              ha.article_type,
              ha.category,
              ha.brand_or_maker,
              ha.short_description,
              ha.notes,
              ha.min_stock,
              ha.ideal_stock,
              ha.favorite_store,
              ha.average_price,
              ha.status,
              ha.created_at,
              ha.updated_at,
              ha.global_product_id,
              COALESCE(inv.total_quantity, 0) AS inventory_total_quantity
            FROM household_articles ha
            LEFT JOIN (
              SELECT household_id, naam, SUM(CASE WHEN COALESCE(status, 'active') = 'active' THEN COALESCE(aantal, 0) ELSE 0 END) AS total_quantity
              FROM inventory
              GROUP BY household_id, naam
            ) inv
              ON inv.household_id = ha.household_id
             AND lower(trim(inv.naam)) = lower(trim(ha.naam))
            WHERE ha.household_id = :household_id AND ha.global_product_id = :global_product_id
            ORDER BY
              CASE WHEN COALESCE(inv.total_quantity, 0) > 0 THEN 0 ELSE 1 END,
              CASE WHEN lower(trim(COALESCE(ha.status, 'active'))) = 'active' THEN 0 ELSE 1 END,
              datetime(ha.created_at) ASC,
              datetime(ha.updated_at) DESC,
              ha.id ASC
            LIMIT 1
            """
        ),
        {'household_id': str(household_id), 'global_product_id': normalized_global_product_id},
    ).mappings().first()
    return dict(row) if row else None


def resolve_receipt_line_product_links(conn, household_id: str | None, article_name: str | None, *, barcode: str | None = None, brand: str | None = None, matched_article_id: str | None = None, create_global_product: bool = True, create_household_article: bool = False, external_article_code: str | None = None):
    normalized_household_id = str(household_id or '').strip()
    normalized_barcode = normalize_barcode_value(barcode) if barcode else None
    normalized_article_name = normalize_household_article_name(article_name)
    normalized_brand = normalize_optional_text_field(brand)
    normalized_external_article_code = normalize_identity_lookup_value(external_article_code or barcode)
    resolved_article_option_id = str(matched_article_id or '').strip() or None
    resolved_global_product_id = None
    match_method = None
    confidence_score = None
    conflict_reason = None

    if resolved_article_option_id:
        article_option = resolve_review_article_option(conn, resolved_article_option_id, normalized_household_id or None)
        resolved_article_id = str((article_option or {}).get('id') or '').strip()
        if resolved_article_id:
            resolved_global_product_id = ensure_household_article_global_product_link(conn, resolved_article_id, normalized_barcode)
            if resolved_global_product_id:
                match_method = 'article_linked'
                confidence_score = 1.0
            elif create_global_product:
                resolved_global_product_id = ensure_global_product_record(
                    conn,
                    normalized_barcode,
                    normalized_article_name or (article_option or {}).get('name'),
                    source='receipt',
                    brand=normalized_brand,
                )
                if resolved_global_product_id:
                    set_household_article_global_product_id(conn, resolved_article_id, resolved_global_product_id)
                    match_method = 'created_new:article_link'
                    confidence_score = 1.0 if normalized_barcode else 0.7

    if not resolved_global_product_id:
        matched_product = find_global_product_match_for_receipt_line(
            conn,
            normalized_barcode,
            normalized_article_name,
            normalized_brand,
            external_article_code=normalized_external_article_code,
        )
        if matched_product and matched_product.get('id'):
            resolved_global_product_id = str(matched_product.get('id'))
            match_method = matched_product.get('match_method')
            confidence_score = matched_product.get('confidence_score')

    if not resolved_global_product_id and create_global_product and normalized_article_name:
        resolved_global_product_id = ensure_global_product_record(
            conn,
            normalized_barcode,
            normalized_article_name,
            source='receipt',
            brand=normalized_brand,
        )
        if resolved_global_product_id:
            match_method = 'created_new'
            confidence_score = 1.0 if normalized_barcode else 0.7
            if normalized_external_article_code:
                conflict_reason = 'no_exact_identity_match_before_create'

    if normalized_household_id and resolved_global_product_id and not resolved_article_option_id:
        existing_household_article = find_household_article_for_global_product(
            conn,
            normalized_household_id,
            resolved_global_product_id,
        )
        if existing_household_article and existing_household_article.get('id'):
            resolved_article_option_id = str(existing_household_article.get('id'))

    if create_household_article and normalized_household_id and resolved_global_product_id and not resolved_article_option_id:
        ensured_article_option_id = ensure_household_article_for_global_product(
            conn,
            normalized_household_id,
            resolved_global_product_id,
            article_name_hint=normalized_article_name,
            barcode=normalized_barcode,
            brand=normalized_brand,
        )
        if ensured_article_option_id:
            resolved_article_option_id = ensured_article_option_id

    return {
        'matched_global_product_id': resolved_global_product_id or None,
        'matched_household_article_id': resolved_article_option_id or None,
        'match_method': match_method or ('unmatched' if not resolved_global_product_id else 'matched'),
        'confidence_score': confidence_score,
        'conflict_reason': conflict_reason,
    }


def backfill_purchase_import_live_aliases(conn, *, household_id: str | None = None, limit: int | None = None):
    normalized_household_id = str(household_id or '').strip() or None
    resolved_limit = None
    try:
        if limit is not None:
            resolved_limit = max(1, int(limit))
    except Exception:
        resolved_limit = None

    query = """
        SELECT pil.id, pib.household_id, pil.article_name_raw, pil.matched_household_article_id
        FROM purchase_import_lines pil
        JOIN purchase_import_batches pib ON pib.id = pil.batch_id
        WHERE pil.matched_household_article_id LIKE 'live::%'
    """
    params: dict[str, object] = {}
    if normalized_household_id:
        query += " AND pib.household_id = :household_id"
        params['household_id'] = normalized_household_id
    query += " ORDER BY datetime(pil.created_at) ASC, pil.id ASC"
    if resolved_limit is not None:
        query += " LIMIT :limit"
        params['limit'] = resolved_limit

    rows = conn.execute(text(query), params).mappings().all()
    report = {
        'scanned': len(rows),
        'updated': 0,
        'skipped': 0,
        'errors': 0,
        'remaining_live_aliases': 0,
        'lines': [],
    }
    for row in rows:
        line_id = str(row.get('id') or '').strip()
        row_household_id = str(row.get('household_id') or '').strip()
        if not line_id or not row_household_id:
            report['skipped'] += 1
            report['lines'].append({
                'line_id': line_id or None,
                'article_name_raw': row.get('article_name_raw'),
                'status': 'skipped',
                'reason': 'missing_line_or_household_id',
            })
            continue
        try:
            synced = sync_purchase_import_line_product_links(conn, line_id, row_household_id) or {}
            refreshed = conn.execute(
                text("""
                    SELECT matched_household_article_id, matched_global_product_id, match_status
                    FROM purchase_import_lines
                    WHERE id = :id
                    LIMIT 1
                """),
                {'id': line_id},
            ).mappings().first() or {}
            matched_household_article_id = str(refreshed.get('matched_household_article_id') or '').strip()
            matched_global_product_id = str(refreshed.get('matched_global_product_id') or '').strip()
            still_live = matched_household_article_id.startswith('live::')
            if matched_household_article_id and not still_live:
                report['updated'] += 1
                line_status = 'updated'
            else:
                report['skipped'] += 1
                line_status = 'unchanged'
            report['lines'].append({
                'line_id': line_id,
                'article_name_raw': row.get('article_name_raw'),
                'matched_household_article_id': matched_household_article_id or None,
                'matched_global_product_id': matched_global_product_id or None,
                'match_status': refreshed.get('match_status'),
                'status': line_status,
            })
        except Exception as exc:
            report['errors'] += 1
            report['lines'].append({
                'line_id': line_id,
                'article_name_raw': row.get('article_name_raw'),
                'status': 'error',
                'reason': str(exc),
            })

    remaining_query = """
        SELECT COUNT(*) AS total
        FROM purchase_import_lines pil
        JOIN purchase_import_batches pib ON pib.id = pil.batch_id
        WHERE pil.matched_household_article_id LIKE 'live::%'
    """
    remaining_params: dict[str, object] = {}
    if normalized_household_id:
        remaining_query += " AND pib.household_id = :household_id"
        remaining_params['household_id'] = normalized_household_id
    remaining = conn.execute(text(remaining_query), remaining_params).mappings().first() or {}
    report['remaining_live_aliases'] = int(remaining.get('total') or 0)
    return report


def sync_receipt_table_line_product_links(conn, receipt_table_id: str, line_id: str, *, create_global_product: bool = True, create_household_article: bool = False):
    receipt_header = conn.execute(
        text(
            """
            SELECT id, household_id, store_name
            FROM receipt_tables
            WHERE id = :receipt_table_id
            LIMIT 1
            """
        ),
        {'receipt_table_id': str(receipt_table_id)},
    ).mappings().first()
    if not receipt_header:
        return None
    line = conn.execute(
        text(
            """
            SELECT id,
                   barcode,
                   COALESCE(corrected_raw_label, raw_label) AS article_name,
                   matched_article_id,
                   matched_global_product_id
            FROM receipt_table_lines
            WHERE id = :line_id AND receipt_table_id = :receipt_table_id
            LIMIT 1
            """
        ),
        {'line_id': str(line_id), 'receipt_table_id': str(receipt_table_id)},
    ).mappings().first()
    if not line:
        return None
    resolved = resolve_receipt_line_product_links(
        conn,
        receipt_header.get('household_id'),
        line.get('article_name'),
        barcode=line.get('barcode'),
        brand=receipt_header.get('store_name'),
        matched_article_id=line.get('matched_article_id'),
        create_global_product=create_global_product,
        create_household_article=create_household_article,
        external_article_code=line.get('barcode'),
    )
    conn.execute(
        text(
            """
            UPDATE receipt_table_lines
            SET matched_global_product_id = :matched_global_product_id,
                matched_article_id = CASE
                    WHEN :matched_household_article_id IS NOT NULL THEN :matched_household_article_id
                    ELSE matched_article_id
                END,
                article_match_status = CASE
                    WHEN :matched_household_article_id IS NOT NULL THEN 'matched'
                    WHEN :matched_global_product_id IS NOT NULL THEN 'product_matched'
                    ELSE 'unmatched'
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :line_id AND receipt_table_id = :receipt_table_id
            """
        ),
        {
            'line_id': str(line_id),
            'receipt_table_id': str(receipt_table_id),
            'matched_global_product_id': resolved.get('matched_global_product_id'),
            'matched_household_article_id': resolved.get('matched_household_article_id'),
        },
    )
    return resolved


def sync_purchase_import_line_product_links(conn, line_id: str | None, household_id: str | None):
    normalized_line_id = str(line_id or '').strip()
    normalized_household_id = str(household_id or '').strip()
    if not normalized_line_id or not normalized_household_id:
        return None
    line = conn.execute(
        text(
            """
            SELECT id, article_name_raw, brand_raw, external_article_code,
                   matched_household_article_id, matched_global_product_id,
                   suggested_household_article_id
            FROM purchase_import_lines
            WHERE id = :id
            LIMIT 1
            """
        ),
        {'id': normalized_line_id},
    ).mappings().first()
    if not line:
        return None

    matched_household_article_id = str(line.get('matched_household_article_id') or '').strip()
    matched_global_product_id = str(line.get('matched_global_product_id') or '').strip()
    barcode = str(line.get('external_article_code') or '').strip() or None
    article_name_hint = line.get('article_name_raw') or None
    brand = line.get('brand_raw') or None

    if matched_household_article_id:
        resolved_household_article_id = resolve_household_article_selection_to_id(
            conn,
            normalized_household_id,
            matched_household_article_id,
            create_if_missing=True,
        )
        if resolved_household_article_id:
            matched_household_article_id = resolved_household_article_id
        resolved_global_product_id = ensure_household_article_global_product_link(conn, matched_household_article_id, barcode)
        if resolved_global_product_id and resolved_global_product_id != matched_global_product_id:
            matched_global_product_id = resolved_global_product_id
    elif matched_global_product_id:
        matched_household_article_id = ensure_household_article_for_global_product(
            conn,
            normalized_household_id,
            matched_global_product_id,
            article_name_hint=article_name_hint,
            barcode=barcode,
            brand=brand,
        )

    if matched_household_article_id and not matched_global_product_id:
        article_row = resolve_review_article_option(conn, matched_household_article_id, normalized_household_id)
        article_id = str((article_row or {}).get('id') or '').strip()
        if article_id:
            matched_global_product_id = ensure_household_article_global_product_link(conn, article_id, barcode)

    if not matched_global_product_id:
        resolved_links = resolve_receipt_line_product_links(
            conn,
            normalized_household_id,
            article_name_hint,
            barcode=barcode,
            brand=brand,
            matched_article_id=matched_household_article_id or None,
            create_global_product=True,
            create_household_article=False,
            external_article_code=barcode,
        )
        if resolved_links:
            matched_global_product_id = resolved_links.get('matched_global_product_id') or matched_global_product_id
            matched_household_article_id = resolved_links.get('matched_household_article_id') or matched_household_article_id

    conn.execute(
        text(
            """
            UPDATE purchase_import_lines
            SET matched_household_article_id = :matched_household_article_id,
                matched_global_product_id = :matched_global_product_id,
                suggested_household_article_id = COALESCE(suggested_household_article_id, :matched_household_article_id),
                match_status = CASE
                    WHEN :matched_household_article_id IS NOT NULL THEN 'matched'
                    ELSE 'unmatched'
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
            """
        ),
        {
            'id': normalized_line_id,
            'matched_household_article_id': matched_household_article_id or None,
            'matched_global_product_id': matched_global_product_id or None,
        },
    )
    return {
        'matched_household_article_id': matched_household_article_id or None,
        'matched_global_product_id': matched_global_product_id or None,
    }


def ensure_household_article_for_global_product(conn, household_id: str, global_product_id: str | None, article_name_hint: str | None = None, barcode: str | None = None, brand: str | None = None):
    normalized_household_id = str(household_id or '').strip()
    normalized_global_product_id = str(global_product_id or '').strip()
    if not normalized_household_id or not normalized_global_product_id:
        return None
    existing = find_household_article_for_global_product(conn, normalized_household_id, normalized_global_product_id)
    if existing and existing.get('id'):
        return str(existing.get('id'))
    product_row = conn.execute(
        text(
            """
            SELECT id, primary_gtin, name, brand, category
            FROM global_products
            WHERE id = :id
            LIMIT 1
            """
        ),
        {'id': normalized_global_product_id},
    ).mappings().first()
    if not product_row:
        return None
    fallback_name = normalize_household_article_name(article_name_hint)
    product_name = normalize_household_article_name(product_row.get('name')) or fallback_name
    if not product_name:
        product_name = f"Product {normalized_global_product_id[:8]}"
    option_id = ensure_household_article(conn, normalized_household_id, product_name, consumable=infer_consumable_from_name(product_name))
    article_row = get_household_article_row_by_name(conn, normalized_household_id, product_name)
    if article_row and article_row.get('id'):
        article_id = str(article_row.get('id'))
        set_household_article_global_product_id(conn, article_id, normalized_global_product_id)
        resolved_gtin = product_row.get('primary_gtin')
        normalized_barcode = normalize_barcode_value(barcode) if barcode else (normalize_barcode_value(resolved_gtin) if resolved_gtin else None)
        conn.execute(
            text(
                """
                UPDATE household_articles
                SET barcode = COALESCE(:barcode, barcode),
                    brand_or_maker = COALESCE(brand_or_maker, :brand),
                    category = COALESCE(category, :category),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {
                'id': article_id,
                'barcode': normalized_barcode,
                'brand': normalize_optional_text_field(brand) or product_row.get('brand'),
                'category': product_row.get('category'),
            },
        )
        if normalized_barcode:
            upsert_product_identity(conn, article_id, 'gtin', normalized_barcode, 'receipt', confidence_score=1.0, is_primary=True)
            ensure_household_article_global_product_link(conn, article_id, normalized_barcode)
    return option_id


def get_latest_global_product_enrichment(conn, global_product_id: str | None):
    if not global_product_id:
        return None
    row = conn.execute(
        text(
            """
            SELECT *
            FROM product_enrichments
            WHERE global_product_id = :global_product_id
            ORDER BY CASE WHEN lookup_status = 'found' THEN 0 ELSE 1 END, datetime(fetched_at) DESC, id DESC
            LIMIT 1
            """
        ),
        {'global_product_id': str(global_product_id)},
    ).mappings().first()
    if not row:
        return None
    return {
        'source_name': row.get('source_name'),
        'source_record_id': row.get('source_record_id'),
        'title': row.get('title'),
        'brand': row.get('brand'),
        'category': row.get('category'),
        'size_value': float(row['size_value']) if row.get('size_value') is not None else None,
        'size_unit': row.get('size_unit') or None,
        'ingredients': json.loads(row.get('ingredients_json') or '[]'),
        'allergens': json.loads(row.get('allergens_json') or '[]'),
        'nutrition': json.loads(row.get('nutrition_json') or '{}'),
        'image_url': row.get('image_url') or None,
        'source_url': row.get('source_url') or None,
        'quality_score': float(row['quality_score']) if row.get('quality_score') is not None else None,
        'fetched_at': row.get('fetched_at'),
        'lookup_status': row.get('lookup_status') or ('found' if row.get('source_name') else None),
        'last_lookup_at': row.get('last_lookup_at') or None,
        'last_lookup_source': row.get('last_lookup_source') or row.get('source_name') or None,
        'last_lookup_message': row.get('last_lookup_message') or None,
        'normalized_barcode': row.get('normalized_barcode') or None,
    }


def upsert_global_product_enrichment(conn, global_product_id: str, enrichment: dict, lookup_status: str = 'found', normalized_barcode: str | None = None, lookup_source: str | None = None, lookup_message: str | None = None, audit_result: EnrichmentLookupResult | None = None):
    source_name = str(enrichment.get('source_name') or '').strip() or 'unknown'
    resolved_barcode = str(normalized_barcode or enrichment.get('normalized_barcode') or '').strip() or None
    existing = conn.execute(
        text(
            """
            SELECT id, household_article_id
            FROM product_enrichments
            WHERE global_product_id = :global_product_id AND source_name = :source_name
            LIMIT 1
            """
        ),
        {'global_product_id': str(global_product_id), 'source_name': source_name},
    ).mappings().first()
    payload_hash = hashlib.sha256(json.dumps(enrichment, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
    sentinel_household_article_id = str(global_product_id)
    params = {
        'household_article_id': sentinel_household_article_id,
        'global_product_id': str(global_product_id),
        'source_name': source_name,
        'source_record_id': enrichment.get('source_record_id'),
        'title': enrichment.get('title'),
        'brand': enrichment.get('brand'),
        'category': enrichment.get('category'),
        'size_value': enrichment.get('size_value'),
        'size_unit': enrichment.get('size_unit'),
        'ingredients_json': json.dumps(enrichment.get('ingredients_json') or [], ensure_ascii=False),
        'allergens_json': json.dumps(enrichment.get('allergens_json') or [], ensure_ascii=False),
        'nutrition_json': json.dumps(enrichment.get('nutrition_json') or {}, ensure_ascii=False),
        'image_url': enrichment.get('image_url'),
        'source_url': enrichment.get('source_url'),
        'quality_score': enrichment.get('quality_score'),
        'raw_payload_json': json.dumps(enrichment.get('raw_payload_json') or {}, ensure_ascii=False),
        'lookup_status': lookup_status or 'found',
        'last_lookup_source': lookup_source or source_name,
        'last_lookup_message': lookup_message,
        'normalized_barcode': resolved_barcode,
    }
    if existing:
        conn.execute(text(
            """
            UPDATE product_enrichments
            SET household_article_id = :household_article_id,
                global_product_id = :global_product_id,
                source_record_id = :source_record_id,
                title = :title,
                brand = :brand,
                category = :category,
                size_value = :size_value,
                size_unit = :size_unit,
                ingredients_json = :ingredients_json,
                allergens_json = :allergens_json,
                nutrition_json = :nutrition_json,
                image_url = :image_url,
                source_url = :source_url,
                quality_score = :quality_score,
                raw_payload_json = :raw_payload_json,
                fetched_at = CURRENT_TIMESTAMP,
                lookup_status = :lookup_status,
                last_lookup_at = CURRENT_TIMESTAMP,
                last_lookup_source = :last_lookup_source,
                last_lookup_message = :last_lookup_message,
                normalized_barcode = :normalized_barcode
            WHERE id = :id
            """
        ), {'id': existing.get('id'), **params})
    else:
        conn.execute(text(
            """
            INSERT INTO product_enrichments (
                id, household_article_id, global_product_id, source_name, source_record_id, title, brand, category, size_value, size_unit,
                ingredients_json, allergens_json, nutrition_json, image_url, source_url, quality_score, fetched_at, raw_payload_json,
                lookup_status, last_lookup_at, last_lookup_source, last_lookup_message, normalized_barcode
            ) VALUES (
                :id, :household_article_id, :global_product_id, :source_name, :source_record_id, :title, :brand, :category, :size_value, :size_unit,
                :ingredients_json, :allergens_json, :nutrition_json, :image_url, :source_url, :quality_score, CURRENT_TIMESTAMP, :raw_payload_json,
                :lookup_status, CURRENT_TIMESTAMP, :last_lookup_source, :last_lookup_message, :normalized_barcode
            )
            """
        ), {'id': str(uuid.uuid4()), **params})
    sync_global_product_from_enrichment(conn, global_product_id, {**enrichment, 'source_name': source_name})
    apply_enrichment_defaults_to_linked_household_articles(conn, global_product_id, enrichment)
    write_product_enrichment_audit(conn, sentinel_household_article_id, source_name, 'lookup', 'found', payload_hash=payload_hash, normalized_barcode=resolved_barcode, source_request_key=f"{source_name}:{resolved_barcode}" if resolved_barcode else source_name, http_status=(audit_result.http_status if audit_result else None), response_excerpt=(audit_result.response_excerpt if audit_result else None), global_product_id=str(global_product_id))
    return get_latest_global_product_enrichment(conn, global_product_id)


def persist_global_product_lookup_result(conn, global_product_id: str, result: EnrichmentLookupResult):
    if result.status == 'found' and result.payload:
        return upsert_global_product_enrichment(conn, global_product_id, result.payload, lookup_status='found', normalized_barcode=result.normalized_barcode, lookup_source=result.source_name, lookup_message=result.message or None, audit_result=result)
    existing = conn.execute(text(
        """
        SELECT id, household_article_id
        FROM product_enrichments
        WHERE global_product_id = :global_product_id AND source_name = :source_name
        LIMIT 1
        """
    ), {'global_product_id': str(global_product_id), 'source_name': result.source_name}).mappings().first()
    sentinel_household_article_id = str(global_product_id)
    params = {
        'household_article_id': sentinel_household_article_id,
        'global_product_id': str(global_product_id),
        'source_name': result.source_name,
        'lookup_status': result.status,
        'last_lookup_source': result.source_name,
        'last_lookup_message': result.message or None,
        'normalized_barcode': result.normalized_barcode,
    }
    if existing:
        conn.execute(text(
            """
            UPDATE product_enrichments
            SET household_article_id = :household_article_id,
                global_product_id = :global_product_id,
                lookup_status = :lookup_status,
                last_lookup_at = CURRENT_TIMESTAMP,
                last_lookup_source = :last_lookup_source,
                last_lookup_message = :last_lookup_message,
                normalized_barcode = :normalized_barcode
            WHERE id = :id
            """
        ), {'id': existing.get('id'), **params})
    else:
        conn.execute(text(
            """
            INSERT INTO product_enrichments (
                id, household_article_id, global_product_id, source_name, lookup_status, last_lookup_at, last_lookup_source, last_lookup_message, normalized_barcode, fetched_at
            ) VALUES (
                :id, :household_article_id, :global_product_id, :source_name, :lookup_status, CURRENT_TIMESTAMP, :last_lookup_source, :last_lookup_message, :normalized_barcode, CURRENT_TIMESTAMP
            )
            """
        ), {'id': str(uuid.uuid4()), **params})
    write_product_enrichment_audit(conn, sentinel_household_article_id, result.source_name, 'lookup', result.status if result.status in {'found', 'not_found', 'failed', 'skipped'} else 'failed', message=result.message or None, normalized_barcode=result.normalized_barcode, source_request_key=f"{result.source_name}:{result.normalized_barcode}" if result.normalized_barcode else result.source_name, http_status=result.http_status, response_excerpt=result.response_excerpt, global_product_id=str(global_product_id))
    return get_latest_global_product_enrichment(conn, global_product_id)


def ensure_global_product_enrichment(conn, barcode: str | None, force_refresh: bool = False, product_name_hint: str | None = None):
    normalized_barcode = normalize_barcode_value(barcode) if barcode else None
    if not normalized_barcode:
        return None, None
    global_product_id = ensure_global_product_record(conn, normalized_barcode, product_name_hint, source='barcode_scan')
    existing = get_latest_global_product_enrichment(conn, global_product_id)
    if existing and not force_refresh and existing.get('lookup_status') == 'found':
        return global_product_id, existing
    latest = existing
    final_failed = None
    for adapter in choose_product_source_adapters():
        result = adapter.lookup_by_barcode(normalized_barcode)
        latest = persist_global_product_lookup_result(conn, global_product_id, result)
        if result.status == 'found':
            return global_product_id, latest
        if result.status == 'failed':
            final_failed = latest
            if not PRODUCT_SOURCE_CONTINUE_ON_FAILURE:
                return global_product_id, latest
    return global_product_id, final_failed or latest or get_latest_global_product_enrichment(conn, global_product_id)


def lookup_product_catalog_by_barcode(conn, barcode: str | None, force_refresh: bool = False, product_name_hint: str | None = None):
    normalized_barcode = normalize_barcode_value(barcode) if barcode else None
    if not normalized_barcode:
        return {'barcode': None, 'global_product_id': None, 'lookup_status': 'skipped', 'product': None, 'enrichment': None}
    global_product_row = get_global_product_row_by_barcode(conn, normalized_barcode)
    global_product_id = str(global_product_row.get('id')) if global_product_row and global_product_row.get('id') else ensure_global_product_record(conn, normalized_barcode, product_name_hint, source='barcode_scan')
    enrichment = get_latest_global_product_enrichment(conn, global_product_id)
    if force_refresh or not enrichment or enrichment.get('lookup_status') != 'found':
        global_product_id, enrichment = ensure_global_product_enrichment(conn, normalized_barcode, force_refresh=force_refresh, product_name_hint=product_name_hint)
        global_product_row = conn.execute(text("SELECT id, primary_gtin, name, brand, category, size_value, size_unit, source, status FROM global_products WHERE id = :id LIMIT 1"), {'id': str(global_product_id)}).mappings().first()
    product_name = None
    product_brand = None
    product_category = None
    product_source = None
    if enrichment and enrichment.get('lookup_status') == 'found':
        product_name = enrichment.get('title') or None
        product_brand = enrichment.get('brand') or None
        product_category = enrichment.get('category') or None
        product_source = enrichment.get('source_name') or None
    if global_product_row:
        product_name = product_name or global_product_row.get('name') or None
        product_brand = product_brand or global_product_row.get('brand') or None
        product_category = product_category or global_product_row.get('category') or None
        product_source = product_source or global_product_row.get('source') or None
    product_payload = None
    if global_product_id:
        product_payload = {
            'id': str(global_product_id),
            'name': product_name or (f'Product {normalized_barcode}' if normalized_barcode else None),
            'barcode': normalized_barcode,
            'brand': product_brand,
            'category': product_category,
            'source': product_source or 'catalog',
        }
        if enrichment and enrichment.get('size_value') is not None:
            product_payload['size_value'] = enrichment.get('size_value')
        if enrichment and enrichment.get('size_unit'):
            product_payload['size_unit'] = enrichment.get('size_unit')
        if enrichment and enrichment.get('source_url'):
            product_payload['source_url'] = enrichment.get('source_url')
        if enrichment and enrichment.get('image_url'):
            product_payload['image_url'] = enrichment.get('image_url')
    return {
        'barcode': normalized_barcode,
        'global_product_id': str(global_product_id) if global_product_id else None,
        'lookup_status': (enrichment or {}).get('lookup_status') or ('found' if product_name else 'pending'),
        'product': product_payload,
        'enrichment': enrichment,
    }


def require_inventory_write_context(authorization: str | None, requested_household_id: str | None = None) -> dict:
    context = require_household_context(authorization, requested_household_id=requested_household_id)
    if not user_can_write_inventory(context):
        raise HTTPException(status_code=403, detail="Kijkers mogen deze voorraadactie niet uitvoeren")
    return context


def resolve_household_article_for_barcode(conn, household_id: str, barcode: str, *, product_name_hint: str | None = None, create_global_product: bool = True, create_household_article: bool = False):
    normalized_household_id = str(household_id or '').strip()
    normalized_barcode = normalize_barcode_value(barcode)
    direct_article = get_household_article_by_barcode(conn, normalized_household_id, normalized_barcode)
    catalog_match = lookup_product_catalog_by_barcode(
        conn,
        normalized_barcode,
        force_refresh=False,
        product_name_hint=product_name_hint,
    )
    resolved_global_product_id = str(catalog_match.get('global_product_id') or '').strip() or None
    global_article = None
    if resolved_global_product_id:
        global_article = find_household_article_for_global_product(conn, normalized_household_id, resolved_global_product_id)
        if not global_article and create_household_article:
            option_id = ensure_household_article_for_global_product(
                conn,
                normalized_household_id,
                resolved_global_product_id,
                article_name_hint=product_name_hint or ((catalog_match.get('product') or {}).get('name')),
                barcode=normalized_barcode,
                brand=((catalog_match.get('product') or {}).get('brand')),
            )
            if option_id:
                global_article_name = option_id.split('::', 1)[1] if option_id.startswith('article::') else None
                if global_article_name:
                    global_article = get_household_article_row_by_name(conn, normalized_household_id, global_article_name)
    preferred_article = direct_article or global_article
    if direct_article and global_article:
        direct_global_product_id = str(direct_article.get('global_product_id') or '').strip() or None
        global_article_id = str(global_article.get('id') or '').strip() or None
        direct_article_id = str(direct_article.get('id') or '').strip() or None
        same_product = bool(resolved_global_product_id) and direct_global_product_id == resolved_global_product_id
        direct_qty = float(direct_article.get('inventory_total_quantity') or 0)
        global_qty = float(global_article.get('inventory_total_quantity') or 0)
        if global_article_id and direct_article_id != global_article_id:
            if same_product or (global_qty > direct_qty) or (direct_qty <= 0 and global_qty >= 0):
                preferred_article = global_article
    if preferred_article and resolved_global_product_id and preferred_article.get('id'):
        set_household_article_global_product_id(conn, str(preferred_article.get('id')), resolved_global_product_id)
        if normalized_barcode:
            conn.execute(text("""
                UPDATE household_articles
                SET barcode = COALESCE(:barcode, barcode),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """), {'id': str(preferred_article.get('id')), 'barcode': normalized_barcode})
    return {
        'article': dict(preferred_article) if preferred_article else None,
        'direct_article': dict(direct_article) if direct_article else None,
        'global_article': dict(global_article) if global_article else None,
        'catalog_match': catalog_match,
        'global_product_id': resolved_global_product_id,
        'barcode': normalized_barcode,
    }


def get_household_article_by_barcode(conn, household_id: str, barcode: str):
    normalized_barcode = normalize_barcode_value(barcode)
    if not normalized_barcode:
        return None
    row = conn.execute(
        text(
            """
            SELECT
              ha.id,
              ha.household_id,
              ha.naam,
              ha.consumable,
              ha.barcode,
              ha.article_number,
              ha.external_source,
              ha.custom_name,
              ha.article_type,
              ha.category,
              ha.brand_or_maker,
              ha.short_description,
              ha.notes,
              ha.min_stock,
              ha.ideal_stock,
              ha.favorite_store,
              ha.average_price,
              ha.status,
              ha.created_at,
              ha.updated_at,
              ha.global_product_id,
              COALESCE(inv.total_quantity, 0) AS inventory_total_quantity
            FROM household_articles ha
            LEFT JOIN (
              SELECT household_id, naam, SUM(CASE WHEN COALESCE(status, 'active') = 'active' THEN COALESCE(aantal, 0) ELSE 0 END) AS total_quantity
              FROM inventory
              GROUP BY household_id, naam
            ) inv
              ON inv.household_id = ha.household_id
             AND lower(trim(inv.naam)) = lower(trim(ha.naam))
            WHERE ha.household_id = :household_id
              AND ha.barcode = :barcode
            ORDER BY
              CASE WHEN COALESCE(inv.total_quantity, 0) > 0 THEN 0 ELSE 1 END,
              CASE WHEN lower(trim(COALESCE(ha.status, 'active'))) = 'active' THEN 0 ELSE 1 END,
              datetime(ha.created_at) ASC,
              datetime(ha.updated_at) DESC,
              ha.id ASC
            LIMIT 1
            """
        ),
        {"household_id": str(household_id), "barcode": normalized_barcode},
    ).mappings().first()
    return dict(row) if row else None



def lookup_openfoodfacts_product(barcode: str) -> dict | None:
    normalized_barcode = normalize_barcode_value(barcode)
    url = f"https://world.openfoodfacts.org/api/v2/product/{normalized_barcode}.json"
    request_obj = urllib.request.Request(
        url,
        headers={
            'Accept': 'application/json',
            'User-Agent': f'Rezzerv/{VERSION_TAG} (barcode lookup)',
        },
        method='GET',
    )
    try:
        with urllib.request.urlopen(request_obj, timeout=4.0) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except Exception:
        return None

    if int(payload.get('status') or 0) != 1:
        return None

    product = payload.get('product') or {}
    product_name = str(product.get('product_name_nl') or product.get('product_name') or '').strip()
    if not product_name:
        return None

    brand = str(product.get('brands') or '').split(',')[0].strip()
    quantity = str(product.get('quantity') or '').strip()
    packaging = str(product.get('packaging') or '').strip()

    return {
        'name': product_name,
        'brand': brand or None,
        'article_number': None,
        'quantity_label': quantity or None,
        'packaging': packaging or None,
        'source': 'openfoodfacts',
    }


def update_household_article_barcode(conn, household_id: str, article_name: str, barcode: str | None):
    normalized_name = normalize_household_article_name(article_name)
    normalized_barcode = normalize_barcode_value(barcode) if barcode else None
    if not normalized_name:
        return
    if normalized_barcode:
        existing = get_household_article_by_barcode(conn, household_id, normalized_barcode)
        if existing and str(existing.get("naam") or "").strip().lower() != normalized_name.lower():
            raise HTTPException(status_code=409, detail="Barcode is al gekoppeld aan een ander artikel")
    conn.execute(
        text(
            """
            UPDATE household_articles
            SET barcode = :barcode, external_source = CASE WHEN :barcode IS NULL THEN external_source ELSE COALESCE(external_source, 'manual') END, updated_at = CURRENT_TIMESTAMP
            WHERE household_id = :household_id
              AND lower(trim(naam)) = lower(trim(:naam))
            """
        ),
        {"barcode": normalized_barcode, "household_id": str(household_id), "naam": normalized_name},
    )


def reassign_household_article_barcode(conn, household_id: str, article_name: str, barcode: str | None):
    normalized_name = normalize_household_article_name(article_name)
    normalized_barcode = normalize_barcode_value(barcode) if barcode else None
    if not normalized_name or not normalized_barcode:
        return False
    existing = get_household_article_by_barcode(conn, household_id, normalized_barcode)
    if existing and str(existing.get("naam") or "").strip().lower() != normalized_name.lower():
        conn.execute(
            text(
                """
                UPDATE household_articles
                SET barcode = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE household_id = :household_id
                  AND barcode = :barcode
                  AND lower(trim(naam)) <> lower(trim(:naam))
                """
            ),
            {"household_id": str(household_id), "barcode": normalized_barcode, "naam": normalized_name},
        )
    update_household_article_barcode(conn, household_id, normalized_name, normalized_barcode)
    return True


def build_incidental_purchase_note(*, source_label: str, article_name: str, supplier: str | None = None, purchase_date: str | None = None, price: float | None = None, currency: str | None = None, barcode: str | None = None, article_number: str | None = None, note: str | None = None) -> str:
    parts = [source_label, normalize_household_article_name(article_name)]
    if supplier:
        parts.append(f"via {str(supplier).strip()}")
    if purchase_date:
        parts.append(f"op {purchase_date}")
    if price is not None:
        amount = f"{float(price):.2f}"
        parts.append(f"voor {amount} {str(currency or 'EUR').upper()}")
    if barcode:
        parts.append(f"barcode {barcode}")
    if article_number:
        parts.append(f"artikelnummer {article_number}")
    base = " ".join(part for part in parts if part).strip()
    if note and str(note).strip():
        return f"{base} — {str(note).strip()}"
    return base


def build_purchase_response_payload(conn, *, inventory_id: str, event_id: str, household_id: str):
    inventory_row = conn.execute(
        text(
            """
            SELECT
              i.id,
              i.naam AS article_name,
              i.aantal AS quantity,
              i.household_id,
              i.space_id,
              i.sublocation_id,
              COALESCE(s.naam, '') AS space_name,
              COALESCE(sl.naam, '') AS sublocation_name,
              COALESCE(i.status, 'active') AS status
            FROM inventory i
            LEFT JOIN spaces s ON s.id = i.space_id
            LEFT JOIN sublocations sl ON sl.id = i.sublocation_id
            WHERE i.id = :id
            """
        ),
        {"id": inventory_id},
    ).mappings().first()
    event_row = conn.execute(
        text(
            """
            SELECT id, event_type, quantity, old_quantity, new_quantity, source, note, purchase_date, supplier_name, article_number, price, currency, barcode, created_at
            FROM inventory_events
            WHERE id = :id AND household_id = :household_id
            LIMIT 1
            """
        ),
        {"id": event_id, "household_id": str(household_id)},
    ).mappings().first()
    return {
        "status": "ok",
        "inventory": dict(inventory_row) if inventory_row else {"id": inventory_id},
        "event": dict(event_row) if event_row else {"id": event_id},
    }



def get_household_article_price_history(conn, household_id: str, household_article_id: str, global_product_id: str | None = None) -> list[dict[str, Any]]:
    event_rows = get_household_product_event_rows(conn, household_id, household_article_id, global_product_id)
    history: list[dict[str, Any]] = []
    for row in event_rows:
        event_type = str(row.get("event_type") or "").strip().lower()
        if event_type not in {"purchase", "auto_repurchase"}:
            continue
        price_value = normalize_optional_numeric_field(row.get("price"))
        quantity_value = normalize_optional_numeric_field(row.get("quantity")) or 0
        if price_value is None and quantity_value <= 0:
            continue
        recorded_at = row.get("purchase_date") or row.get("created_at")
        history.append({
            "event_id": str(row.get("id") or "").strip(),
            "event_type": event_type,
            "price": float(price_value) if price_value is not None else None,
            "currency": normalize_optional_text_field(row.get("currency")) or "EUR",
            "store_name": normalize_optional_text_field(row.get("supplier_name")),
            "purchase_date": normalize_datetime(recorded_at),
            "quantity": float(quantity_value),
            "source": normalize_optional_text_field(row.get("source")) or "unknown",
            "article_number": normalize_optional_text_field(row.get("article_number")),
            "barcode": normalize_optional_text_field(row.get("barcode")),
        })
    history.sort(key=lambda item: (item.get("purchase_date") or "", item.get("event_id") or ""))
    return history


def build_household_article_price_summary(conn, household_id: str, household_article_id: str, global_product_id: str | None = None) -> dict[str, Any]:
    price_history = get_household_article_price_history(conn, household_id, household_article_id, global_product_id)
    priced_entries = [entry for entry in price_history if entry.get("price") is not None]
    latest_entry = priced_entries[-1] if priced_entries else (price_history[-1] if price_history else None)
    average_price = None
    if priced_entries:
        average_price = round(sum(float(entry["price"]) for entry in priced_entries) / len(priced_entries), 4)
    return {
        "history_count": len(price_history),
        "priced_history_count": len(priced_entries),
        "average_price": average_price,
        "latest_price": float(latest_entry["price"]) if latest_entry and latest_entry.get("price") is not None else None,
        "latest_store": latest_entry.get("store_name") if latest_entry else None,
        "latest_purchase_date": latest_entry.get("purchase_date") if latest_entry else None,
        "currency": latest_entry.get("currency") if latest_entry else ("EUR" if priced_entries else None),
        "price_history": price_history,
    }


def sync_household_article_price_metrics(conn, household_id: str, household_article_id: str, global_product_id: str | None = None) -> dict[str, Any]:
    normalized_household_article_id = str(household_article_id or "").strip()
    if not normalized_household_article_id:
        return {"average_price": None, "latest_store": None, "latest_price": None, "latest_purchase_date": None, "currency": None, "price_history": []}
    summary = build_household_article_price_summary(conn, household_id, normalized_household_article_id, global_product_id)
    conn.execute(
        text(
            """
            UPDATE household_articles
            SET average_price = :average_price,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :household_article_id AND household_id = :household_id
            """
        ),
        {
            "average_price": summary.get("average_price"),
            "household_article_id": normalized_household_article_id,
            "household_id": str(household_id),
        },
    )
    return summary


def fetch_inventory_row(conn, *, inventory_id: str, household_id: str):
    row = conn.execute(
        text(
            """
            SELECT
              i.id,
              i.naam AS article_name,
              i.aantal AS quantity,
              i.household_id,
              i.space_id,
              i.sublocation_id,
              COALESCE(i.status, 'active') AS status,
              COALESCE(s.naam, '') AS space_name,
              COALESCE(sl.naam, '') AS sublocation_name
            FROM inventory i
            LEFT JOIN spaces s ON s.id = i.space_id
            LEFT JOIN sublocations sl ON sl.id = i.sublocation_id
            WHERE i.id = :id
              AND i.household_id = :household_id
            LIMIT 1
            """
        ),
        {"id": str(inventory_id), "household_id": str(household_id)},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Onbekende inventory-regel")
    return dict(row)



def fetch_inventory_row_by_article_and_location(conn, *, household_id: str, article_name: str, resolved_location: dict):
    safe_location = require_resolved_location(resolved_location)
    row = conn.execute(
        text(
            """
            SELECT
              i.id,
              i.naam AS article_name,
              i.aantal AS quantity,
              i.household_id,
              i.space_id,
              i.sublocation_id,
              COALESCE(i.status, 'active') AS status,
              COALESCE(s.naam, '') AS space_name,
              COALESCE(sl.naam, '') AS sublocation_name
            FROM inventory i
            LEFT JOIN spaces s ON s.id = i.space_id
            LEFT JOIN sublocations sl ON sl.id = i.sublocation_id
            WHERE i.household_id = :household_id
              AND lower(trim(i.naam)) = lower(trim(:article_name))
              AND COALESCE(i.space_id, '') = COALESCE(:space_id, '')
              AND COALESCE(i.sublocation_id, '') = COALESCE(:sublocation_id, '')
              AND COALESCE(i.status, 'active') = 'active'
            LIMIT 1
            """
        ),
        {
            "household_id": str(household_id),
            "article_name": article_name,
            "space_id": safe_location.get('space_id'),
            "sublocation_id": safe_location.get('sublocation_id'),
        },
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Geen voorraadregel gevonden voor het artikel op deze locatie")
    return dict(row)



def update_inventory_row_quantity(conn, *, inventory_id: str, new_quantity: int):
    conn.execute(
        text(
            """
            UPDATE inventory
            SET aantal = :new_quantity, updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
            """
        ),
        {"id": str(inventory_id), "new_quantity": int(new_quantity)},
    )



def delete_inventory_row_if_empty(conn, *, inventory_id: str):
    conn.execute(
        text(
            """
            DELETE FROM inventory
            WHERE id = :id
              AND COALESCE(aantal, 0) = 0
            """
        ),
        {"id": str(inventory_id)},
    )



def build_location_payload_from_inventory_row(row: dict):
    return {
        'location_id': row.get('sublocation_id') or row.get('space_id'),
        'space_id': row.get('space_id'),
        'sublocation_id': row.get('sublocation_id'),
        'location_label': ' / '.join(part for part in [row.get('space_name') or '', row.get('sublocation_name') or ''] if part),
    }



def build_inventory_row_response(conn, *, inventory_id: str, household_id: str):
    row = conn.execute(
        text(
            """
            SELECT
              i.id,
              i.naam AS article_name,
              i.aantal AS quantity,
              i.household_id,
              i.space_id,
              i.sublocation_id,
              COALESCE(i.status, 'active') AS status,
              COALESCE(s.naam, '') AS space_name,
              COALESCE(sl.naam, '') AS sublocation_name
            FROM inventory i
            LEFT JOIN spaces s ON s.id = i.space_id
            LEFT JOIN sublocations sl ON sl.id = i.sublocation_id
            WHERE i.id = :id
              AND i.household_id = :household_id
            LIMIT 1
            """
        ),
        {"id": str(inventory_id), "household_id": str(household_id)},
    ).mappings().first()
    if not row:
        return None
    return dict(row)



def build_inventory_event_response(conn, *, event_id: str, household_id: str):
    row = conn.execute(
        text(
            """
            SELECT id, article_id, article_name, location_id, location_label, event_type, quantity, old_quantity, new_quantity, source, note, created_at
            FROM inventory_events
            WHERE id = :id
              AND household_id = :household_id
            LIMIT 1
            """
        ),
        {"id": str(event_id), "household_id": str(household_id)},
    ).mappings().first()
    return dict(row) if row else None



def apply_inventory_row_consumption(conn, *, inventory_id: str, household_id: str, quantity: int):
    row = fetch_inventory_row(conn, inventory_id=inventory_id, household_id=household_id)
    current_quantity = int(row.get('quantity') or 0)
    consume_quantity = int(quantity or 0)
    if consume_quantity <= 0:
        raise HTTPException(status_code=400, detail="Aantal moet groter zijn dan 0")
    if consume_quantity > current_quantity:
        raise HTTPException(status_code=400, detail="Verbruik zou negatieve voorraad veroorzaken")
    new_quantity = current_quantity - consume_quantity
    update_inventory_row_quantity(conn, inventory_id=inventory_id, new_quantity=new_quantity)
    if new_quantity == 0:
        delete_inventory_row_if_empty(conn, inventory_id=inventory_id)
    updated = dict(row)
    updated['quantity'] = new_quantity
    return updated



def normalize_store_import_simplification_level(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in STORE_IMPORT_SIMPLIFICATION_ALLOWED:
        return STORE_IMPORT_SIMPLIFICATION_DEFAULT
    return normalized


def get_household_store_import_simplification_level(conn, household_id: str) -> str:
    row = conn.execute(
        text(
            "SELECT setting_value FROM household_settings WHERE household_id = :household_id AND setting_key = :setting_key"
        ),
        {"household_id": str(household_id), "setting_key": STORE_IMPORT_SIMPLIFICATION_KEY},
    ).mappings().first()
    return normalize_store_import_simplification_level(row["setting_value"] if row else None)


def set_household_store_import_simplification_level(conn, household_id: str, value: str) -> str:
    normalized = normalize_store_import_simplification_level(value)
    conn.execute(
        text(
            """
            INSERT INTO household_settings (id, household_id, setting_key, setting_value, updated_at)
            VALUES (:id, :household_id, :setting_key, :setting_value, CURRENT_TIMESTAMP)
            ON CONFLICT(household_id, setting_key)
            DO UPDATE SET setting_value = excluded.setting_value, updated_at = CURRENT_TIMESTAMP
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "household_id": str(household_id),
            "setting_key": STORE_IMPORT_SIMPLIFICATION_KEY,
            "setting_value": normalized,
        },
    )
    return normalized



def normalize_almost_out_prediction_enabled(value: Any) -> bool:
    return normalize_bool_setting(value)


def normalize_almost_out_prediction_days(value: Any) -> int:
    if value in (None, ''):
        return ALMOST_OUT_PREDICTION_DEFAULT_DAYS
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return ALMOST_OUT_PREDICTION_DEFAULT_DAYS
    return max(normalized, 0)


def normalize_almost_out_policy_mode(value: Any) -> str:
    normalized = str(value or '').strip().lower()
    if normalized not in ALMOST_OUT_POLICY_ALLOWED:
        return ALMOST_OUT_POLICY_ADVISORY
    return normalized


def get_household_almost_out_prediction_enabled(conn, household_id: str) -> bool:
    row = conn.execute(
        text(
            "SELECT setting_value FROM household_settings WHERE household_id = :household_id AND setting_key = :setting_key"
        ),
        {"household_id": str(household_id), "setting_key": ALMOST_OUT_PREDICTION_ENABLED_KEY},
    ).mappings().first()
    return normalize_almost_out_prediction_enabled(row["setting_value"] if row else False)


def get_household_almost_out_prediction_days(conn, household_id: str) -> int:
    row = conn.execute(
        text(
            "SELECT setting_value FROM household_settings WHERE household_id = :household_id AND setting_key = :setting_key"
        ),
        {"household_id": str(household_id), "setting_key": ALMOST_OUT_PREDICTION_DAYS_KEY},
    ).mappings().first()
    return normalize_almost_out_prediction_days(row["setting_value"] if row else ALMOST_OUT_PREDICTION_DEFAULT_DAYS)


def get_household_almost_out_policy_mode(conn, household_id: str) -> str:
    row = conn.execute(
        text(
            "SELECT setting_value FROM household_settings WHERE household_id = :household_id AND setting_key = :setting_key"
        ),
        {"household_id": str(household_id), "setting_key": ALMOST_OUT_POLICY_MODE_KEY},
    ).mappings().first()
    return normalize_almost_out_policy_mode(row["setting_value"] if row else ALMOST_OUT_POLICY_ADVISORY)


def set_household_almost_out_settings(conn, household_id: str, *, prediction_enabled: bool, prediction_days: int, policy_mode: str) -> dict:
    normalized_enabled = normalize_almost_out_prediction_enabled(prediction_enabled)
    normalized_days = normalize_almost_out_prediction_days(prediction_days)
    normalized_policy_mode = normalize_almost_out_policy_mode(policy_mode)
    settings_to_write = {
        ALMOST_OUT_PREDICTION_ENABLED_KEY: 'true' if normalized_enabled else 'false',
        ALMOST_OUT_PREDICTION_DAYS_KEY: str(normalized_days),
        ALMOST_OUT_POLICY_MODE_KEY: normalized_policy_mode,
    }
    for setting_key, setting_value in settings_to_write.items():
        conn.execute(
            text(
                """
                INSERT INTO household_settings (id, household_id, setting_key, setting_value, updated_at)
                VALUES (:id, :household_id, :setting_key, :setting_value, CURRENT_TIMESTAMP)
                ON CONFLICT(household_id, setting_key)
                DO UPDATE SET setting_value = excluded.setting_value, updated_at = CURRENT_TIMESTAMP
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "household_id": str(household_id),
                "setting_key": setting_key,
                "setting_value": setting_value,
            },
        )
    return {
        'prediction_enabled': normalized_enabled,
        'prediction_days': normalized_days,
        'policy_mode': normalized_policy_mode,
    }


def get_household_almost_out_settings(conn, household_id: str) -> dict:
    return {
        'prediction_enabled': get_household_almost_out_prediction_enabled(conn, household_id),
        'prediction_days': get_household_almost_out_prediction_days(conn, household_id),
        'policy_mode': get_household_almost_out_policy_mode(conn, household_id),
    }


def _parse_event_datetime_to_utc(value: Any) -> datetime | None:
    if value in (None, ''):
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        if not raw:
            return None
        candidates = [raw]
        if 'T' not in raw and ' ' in raw:
            candidates.append(raw.replace(' ', 'T'))
        for candidate in list(candidates):
            if candidate.endswith('Z'):
                candidates.append(candidate[:-1] + '+00:00')
        dt = None
        for candidate in candidates:
            try:
                dt = datetime.fromisoformat(candidate)
                break
            except ValueError:
                continue
        if dt is None:
            for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
                try:
                    dt = datetime.strptime(raw, fmt)
                    break
                except ValueError:
                    continue
        if dt is None:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_household_article_prediction(conn, household_id: str, household_article_id: str, article_name: str, *, current_quantity: float, prediction_days: int) -> dict | None:
    normalized_article_id = str(household_article_id or '').strip()
    normalized_article_name = str(article_name or '').strip()
    if not normalized_article_id or not normalized_article_name or prediction_days <= 0:
        return None

    purchase_rows = conn.execute(
        text(
            """
            SELECT article_id, article_name, quantity, purchase_date, created_at
            FROM inventory_events
            WHERE household_id = :household_id
              AND COALESCE(quantity, 0) > 0
              AND event_type IN ('purchase', 'auto_repurchase')
              AND (
                    article_id = :article_id
                    OR lower(trim(article_name)) = lower(trim(:article_name))
                  )
            ORDER BY datetime(COALESCE(purchase_date, created_at)) ASC, created_at ASC, id ASC
            """
        ),
        {'household_id': str(household_id), 'article_id': normalized_article_id, 'article_name': normalized_article_name},
    ).mappings().all()

    timestamps: list[datetime] = []
    purchase_quantities: list[float] = []
    for row in purchase_rows:
        dt = _parse_event_datetime_to_utc(row.get('purchase_date')) or _parse_event_datetime_to_utc(row.get('created_at'))
        if dt is None:
            continue
        timestamps.append(dt)
        quantity = normalize_optional_numeric_field(row.get('quantity'))
        if quantity is not None and quantity > 0:
            purchase_quantities.append(float(quantity))

    if len(timestamps) < 2:
        return None

    interval_days: list[float] = []
    for previous, current in zip(timestamps, timestamps[1:]):
        delta_days = (current - previous).total_seconds() / 86400.0
        if delta_days > 0:
            interval_days.append(delta_days)
    if not interval_days:
        return None

    average_purchase_interval_days = sum(interval_days) / len(interval_days)
    last_purchase_at = timestamps[-1]
    now = datetime.now(timezone.utc)
    days_since_last_purchase = max((now - last_purchase_at).total_seconds() / 86400.0, 0.0)
    predicted_days_until_depletion = max(average_purchase_interval_days - days_since_last_purchase, 0.0)
    predicted_depletion_at = now + timedelta(days=predicted_days_until_depletion)
    average_purchase_quantity = (sum(purchase_quantities) / len(purchase_quantities)) if purchase_quantities else None

    return {
        'prediction_available': True,
        'prediction_basis': 'average_purchase_interval',
        'average_purchase_interval_days': float(round(average_purchase_interval_days, 3)),
        'average_purchase_quantity': float(round(average_purchase_quantity, 3)) if average_purchase_quantity is not None else None,
        'last_purchase_at': last_purchase_at.isoformat(),
        'days_since_last_purchase': float(round(days_since_last_purchase, 3)),
        'predicted_days_until_depletion': float(round(predicted_days_until_depletion, 3)),
        'predicted_depletion_date': predicted_depletion_at.date().isoformat(),
        'predicted_depletion_at': predicted_depletion_at.isoformat(),
        'prediction_threshold_days': int(prediction_days),
        'prediction_triggered': predicted_days_until_depletion <= float(prediction_days),
        'current_quantity_at_evaluation': float(round(current_quantity, 6)),
        'purchase_event_count': len(timestamps),
    }




def normalize_article_field_visibility_map(value) -> dict:
    normalized = {key: {} for key in ARTICLE_FIELD_VISIBILITY_DEFAULT.keys()}
    if not isinstance(value, dict):
        return normalized

    for tab_key in normalized.keys():
        tab_value = value.get(tab_key)
        if not isinstance(tab_value, dict):
            continue
        cleaned_tab = {}
        for field_key, is_visible in tab_value.items():
            if isinstance(field_key, str) and isinstance(is_visible, bool):
                cleaned_tab[field_key] = is_visible
        normalized[tab_key] = cleaned_tab
    return normalized


def get_household_article_field_visibility(conn, household_id: str) -> dict:
    row = conn.execute(
        text(
            "SELECT setting_value FROM household_settings WHERE household_id = :household_id AND setting_key = :setting_key"
        ),
        {"household_id": str(household_id), "setting_key": ARTICLE_FIELD_VISIBILITY_KEY},
    ).mappings().first()

    if not row or not row.get("setting_value"):
        return normalize_article_field_visibility_map({})

    try:
        parsed = json.loads(row["setting_value"])
    except (TypeError, ValueError, json.JSONDecodeError):
        return normalize_article_field_visibility_map({})

    return normalize_article_field_visibility_map(parsed)


def set_household_article_field_visibility(conn, household_id: str, value) -> dict:
    normalized = normalize_article_field_visibility_map(value)
    conn.execute(
        text(
            """
            INSERT INTO household_settings (id, household_id, setting_key, setting_value, updated_at)
            VALUES (:id, :household_id, :setting_key, :setting_value, CURRENT_TIMESTAMP)
            ON CONFLICT(household_id, setting_key)
            DO UPDATE SET setting_value = excluded.setting_value, updated_at = CURRENT_TIMESTAMP
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "household_id": str(household_id),
            "setting_key": ARTICLE_FIELD_VISIBILITY_KEY,
            "setting_value": json.dumps(normalized),
        },
    )
    return normalized

def normalize_user_privacy_settings_map(value) -> dict:
    normalized = dict(USER_PRIVACY_SETTINGS_DEFAULT)
    if not isinstance(value, dict):
        return normalized
    for key in list(normalized.keys()):
        normalized[key] = bool(value.get(key, normalized[key]))
    return normalized


def get_user_privacy_settings(conn, user_email: str) -> dict:
    normalized_email = str(user_email or '').strip().lower()
    row = conn.execute(
        text(
            "SELECT setting_value FROM user_settings WHERE user_email = :user_email AND setting_key = :setting_key"
        ),
        {"user_email": normalized_email, "setting_key": USER_PRIVACY_SETTINGS_KEY},
    ).mappings().first()
    if not row or not row.get("setting_value"):
        return normalize_user_privacy_settings_map({})
    try:
        parsed = json.loads(row["setting_value"])
    except (TypeError, ValueError, json.JSONDecodeError):
        return normalize_user_privacy_settings_map({})
    return normalize_user_privacy_settings_map(parsed)


def set_user_privacy_settings(conn, user_email: str, value) -> dict:
    normalized_email = str(user_email or '').strip().lower()
    normalized = normalize_user_privacy_settings_map(value)
    conn.execute(
        text(
            """
            INSERT INTO user_settings (id, user_email, setting_key, setting_value, updated_at)
            VALUES (:id, :user_email, :setting_key, :setting_value, CURRENT_TIMESTAMP)
            ON CONFLICT(user_email, setting_key)
            DO UPDATE SET setting_value = excluded.setting_value, updated_at = CURRENT_TIMESTAMP
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "user_email": normalized_email,
            "setting_key": USER_PRIVACY_SETTINGS_KEY,
            "setting_value": json.dumps(normalized),
        },
    )
    return normalized



def ensure_release_1113_schema():
    with engine.begin() as conn:
        household_article_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(household_articles)")).fetchall()}
        if 'average_price' not in household_article_columns:
            conn.execute(text("ALTER TABLE household_articles ADD COLUMN average_price NUMERIC"))
        if 'status' not in household_article_columns:
            conn.execute(text("ALTER TABLE household_articles ADD COLUMN status TEXT DEFAULT 'active'"))
        conn.execute(text("UPDATE household_articles SET status = COALESCE(NULLIF(trim(status), ''), 'active')"))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS household_article_settings (
                id TEXT PRIMARY KEY,
                household_article_id TEXT NOT NULL,
                setting_key TEXT NOT NULL,
                setting_value TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_household_article_settings_unique ON household_article_settings (household_article_id, setting_key)"))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS household_article_notes (
                id TEXT PRIMARY KEY,
                household_article_id TEXT NOT NULL,
                note TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_household_article_notes_unique ON household_article_notes (household_article_id)"))


def ensure_release_965_schema():
    with engine.begin() as conn:
        conn.execute(
            text(
                '''
                CREATE TABLE IF NOT EXISTS household_registry (
                    id TEXT PRIMARY KEY,
                    naam TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                '''
            )
        )
        conn.execute(
            text(
                '''
                CREATE TABLE IF NOT EXISTS app_users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                '''
            )
        )
        conn.execute(
            text(
                '''
                CREATE TABLE IF NOT EXISTS household_memberships (
                    id TEXT PRIMARY KEY,
                    household_id TEXT NOT NULL,
                    user_email TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'member',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(household_id, user_email)
                )
                '''
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_household_memberships_household ON household_memberships (household_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_household_memberships_email ON household_memberships (user_email)"))


def bootstrap_auth_registry():
    with engine.begin() as conn:
        default_household_id = '1'
        default_household_name = DEFAULT_AUTH_USERS['admin@rezzerv.local'].get('household_name') or 'Mijn huishouden'
        conn.execute(
            text(
                '''
                INSERT INTO household_registry (id, naam, created_at)
                VALUES (:id, :naam, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO NOTHING
                '''
            ),
            {'id': default_household_id, 'naam': default_household_name},
        )
        for email, profile in DEFAULT_AUTH_USERS.items():
            normalized_email = str(email).strip().lower()
            conn.execute(
                text(
                    '''
                    INSERT INTO app_users (id, email, password, created_at, updated_at)
                    VALUES (:id, :email, :password, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT(email) DO NOTHING
                    '''
                ),
                {'id': str(uuid.uuid4()), 'email': normalized_email, 'password': profile['password']},
            )
            conn.execute(
                text(
                    '''
                    INSERT INTO household_memberships (id, household_id, user_email, role, created_at, updated_at)
                    VALUES (:id, :household_id, :user_email, :role, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT(household_id, user_email) DO NOTHING
                    '''
                ),
                {
                    'id': str(uuid.uuid4()),
                    'household_id': str(profile.get('household_id') or default_household_id),
                    'user_email': normalized_email,
                    'role': map_user_role_to_membership_role(profile.get('role')),
                },
            )


def refresh_runtime_users_from_db():
    global users, households
    runtime_users = {}
    runtime_households = {}
    with engine.begin() as conn:
        household_rows = conn.execute(text("SELECT id, naam, created_at FROM household_registry ORDER BY naam ASC, id ASC")).mappings().all()
        for row in household_rows:
            runtime_households[str(row['id'])] = {
                'id': str(row['id']),
                'naam': row.get('naam') or 'Mijn huishouden',
                'created_at': row.get('created_at') or datetime.utcnow().isoformat(),
            }

        membership_rows = conn.execute(
            text(
                '''
                SELECT au.email,
                       au.password,
                       hm.household_id,
                       hm.role,
                       hr.naam AS household_name
                FROM app_users au
                LEFT JOIN household_memberships hm ON hm.user_email = au.email
                LEFT JOIN household_registry hr ON hr.id = hm.household_id
                ORDER BY au.email ASC, CASE WHEN hm.role = 'owner' THEN 0 ELSE 1 END ASC, hm.created_at ASC
                '''
            )
        ).mappings().all()

    for row in membership_rows:
        email = str(row.get('email') or '').strip().lower()
        if not email or email in runtime_users:
            continue
        household_id = str(row.get('household_id') or DEFAULT_AUTH_USERS.get(email, {}).get('household_id') or '1')
        household_name = row.get('household_name') or DEFAULT_AUTH_USERS.get(email, {}).get('household_name') or 'Mijn huishouden'
        runtime_users[email] = {
            'password': row.get('password') or DEFAULT_AUTH_USERS.get(email, {}).get('password') or 'Rezzerv123',
            'role': 'admin' if str(row.get('role') or '').strip().lower() == 'owner' else 'member',
            'household_key': household_id,
            'household_id': household_id,
            'household_name': household_name,
        }

    for email, profile in DEFAULT_AUTH_USERS.items():
        runtime_users.setdefault(email, dict(profile))
        runtime_households.setdefault(
            str(profile.get('household_id') or '1'),
            {
                'id': str(profile.get('household_id') or '1'),
                'naam': profile.get('household_name') or 'Mijn huishouden',
                'created_at': datetime.utcnow().isoformat(),
            },
        )

    users = runtime_users
    households = runtime_households


def get_user_record(email: str | None):
    normalized_email = str(email or '').strip().lower()
    if not normalized_email:
        return None
    return users.get(normalized_email)


def list_household_members(conn, household_id: str) -> list[dict]:
    rows = conn.execute(
        text(
            '''
            SELECT hm.user_email AS email,
                   hm.role,
                   au.created_at AS user_created_at,
                   hm.created_at AS membership_created_at
            FROM household_memberships hm
            JOIN app_users au ON au.email = hm.user_email
            WHERE hm.household_id = :household_id
            ORDER BY CASE WHEN hm.role = 'owner' THEN 0 ELSE 1 END ASC,
                     lower(hm.user_email) ASC
            '''
        ),
        {'household_id': str(household_id)},
    ).mappings().all()
    return [
        {
            'email': str(row.get('email') or '').strip().lower(),
            'role': str(row.get('role') or 'member'),
            'display_role': map_membership_role_to_display_role(row.get('role')),
            'user_created_at': row.get('user_created_at'),
            'membership_created_at': row.get('membership_created_at'),
        }
        for row in rows
        if str(row.get('email') or '').strip()
    ]


def count_household_admins(conn, household_id: str) -> int:
    row = conn.execute(
        text("SELECT COUNT(*) AS total FROM household_memberships WHERE household_id = :household_id AND role = 'owner'"),
        {'household_id': str(household_id)},
    ).mappings().first()
    return int(row.get('total') or 0) if row else 0


def get_household_name_by_id(conn, household_id: str) -> str:
    row = conn.execute(text("SELECT naam FROM household_registry WHERE id = :id LIMIT 1"), {'id': str(household_id)}).mappings().first()
    return str(row.get('naam') or 'Mijn huishouden') if row else 'Mijn huishouden'


def update_household_name(conn, household_id: str, new_name: str) -> str:
    normalized_name = str(new_name or '').strip()
    if not normalized_name:
        raise HTTPException(status_code=400, detail='Huishoudnaam is verplicht')
    if len(normalized_name) > 120:
        raise HTTPException(status_code=400, detail='Huishoudnaam mag maximaal 120 tekens bevatten')
    conn.execute(
        text("""
            INSERT INTO household_registry (id, naam, created_at)
            VALUES (:id, :naam, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET naam = excluded.naam
        """),
        {'id': str(household_id), 'naam': normalized_name},
    )
    return normalized_name


def build_household_members_payload(conn, household_id: str, current_email: str) -> dict:
    household_name = get_household_name_by_id(conn, household_id)
    members = list_household_members(conn, household_id)
    current_normalized = str(current_email or '').strip().lower()
    admin_count = count_household_admins(conn, household_id)
    return {
        'household_id': str(household_id),
        'household_name': household_name,
        'member_count': len(members),
        'role_change_audit': list_household_role_change_audit(conn, household_id),
        'members': [
            {
                **member,
                'is_current_user': member['email'] == current_normalized,
                'can_remove': not (member['display_role'] == 'admin' and admin_count <= 1),
                'can_change_role': not (member['display_role'] == 'admin' and admin_count <= 1 and member['email'] == current_normalized),
            }
            for member in members
        ],
    }


def build_auth_token(email: str) -> str:
    return f"rezzerv-dev-token::{str(email or '').strip().lower()}"


def get_current_user_from_authorization(authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")

    token = authorization.split(" ", 1)[1].strip()
    if token == "rezzerv-dev-token":
        email = "admin@rezzerv.local"
    elif token.startswith("rezzerv-dev-token::"):
        email = token.split("::", 1)[1].strip().lower()
    else:
        raise HTTPException(status_code=401, detail="Unauthorized")

    user = get_user_record(email)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    return {"email": email, **user}


def normalize_optional_household_id(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def map_user_role_to_membership_role(user_role: str | None) -> str:
    normalized = str(user_role or '').strip().lower()
    return 'owner' if normalized == 'admin' else 'member'


def map_membership_role_to_display_role(membership_role: str | None) -> str:
    normalized = str(membership_role or '').strip().lower()
    if normalized == 'owner':
        return 'admin'
    if normalized == 'viewer':
        return 'viewer'
    return 'lid'


def resolve_user_household_memberships(user: dict) -> list[dict]:
    email = str(user.get('email') or '').strip().lower()
    memberships: list[dict] = []
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text(
                    '''
                    SELECT hm.household_id,
                           hm.role,
                           hr.naam AS household_name,
                           hr.created_at AS household_created_at
                    FROM household_memberships hm
                    LEFT JOIN household_registry hr ON hr.id = hm.household_id
                    WHERE hm.user_email = :email
                    ORDER BY CASE WHEN hm.role = 'owner' THEN 0 ELSE 1 END ASC,
                             hm.created_at ASC,
                             hm.household_id ASC
                    '''
                ),
                {'email': email},
            ).mappings().all()
    except Exception:
        rows = []

    for row in rows:
        household_id = str(row.get('household_id') or '').strip()
        if not household_id:
            continue
        membership_role = str(row.get('role') or 'member').strip().lower() or 'member'
        memberships.append(
            {
                'household_id': household_id,
                'household_name': row.get('household_name') or user.get('household_name') or 'Mijn huishouden',
                'household_created_at': row.get('household_created_at'),
                'role': membership_role,
                'display_role': map_membership_role_to_display_role(membership_role),
                'is_default': len(memberships) == 0,
            }
        )

    if memberships:
        return memberships

    household = ensure_household(user['email'])
    membership_role = map_user_role_to_membership_role(user.get('role'))
    household_id = str(household.get('id') or user.get('household_id') or '1')
    household_name = str(household.get('naam') or user.get('household_name') or 'Mijn huishouden')
    return [
        {
            'household_id': household_id,
            'household_name': household_name,
            'household_created_at': household.get('created_at'),
            'role': membership_role,
            'display_role': map_membership_role_to_display_role(membership_role),
            'is_default': True,
        }
    ]


def resolve_household_context_for_user(user: dict, requested_household_id: str | None = None) -> dict:
    memberships = resolve_user_household_memberships(user)
    if not memberships:
        raise HTTPException(status_code=403, detail='Geen gekoppeld huishouden gevonden voor deze gebruiker')

    normalized_requested_household_id = normalize_optional_household_id(requested_household_id)
    selected_membership = memberships[0]
    if normalized_requested_household_id is not None:
        selected_membership = next(
            (membership for membership in memberships if str(membership.get('household_id')) == normalized_requested_household_id),
            None,
        )
        if selected_membership is None:
            raise HTTPException(status_code=403, detail='Geen toegang tot het gevraagde huishouden')

    return {
        'user_id': str(user.get('id') or user['email']),
        'email': user['email'],
        'active_household_id': str(selected_membership['household_id']),
        'active_household_name': selected_membership['household_name'],
        'active_household_created_at': selected_membership.get('household_created_at'),
        'role': selected_membership['role'],
        'display_role': selected_membership['display_role'],
        'memberships': memberships,
        'membership_count': len(memberships),
        'can_switch_households': len(memberships) > 1,
    }


def require_household_context(authorization: str | None, requested_household_id: str | None = None) -> dict:
    user = get_current_user_from_authorization(authorization)
    return resolve_household_context_for_user(user, requested_household_id=requested_household_id)


def require_household_admin_context(authorization: str | None, requested_household_id: str | None = None) -> dict:
    context = require_household_context(authorization, requested_household_id=requested_household_id)
    if str(context.get('display_role') or '').strip().lower() != 'admin':
        raise HTTPException(status_code=403, detail='Alleen de beheerder van het huishouden mag deze actie uitvoeren')
    return context


def require_platform_admin_user(authorization: str | None) -> dict:
    user = get_current_user_from_authorization(authorization)
    if str(user.get('role') or '').strip().lower() != 'admin':
        raise HTTPException(status_code=403, detail='Alleen de beheerder van het huishouden mag deze actie uitvoeren')
    return user


def require_entity_household_access(conn, table_name: str, entity_id: str, authorization: str | None, *, entity_field: str = 'id', admin_only: bool = False) -> dict:
    row = conn.execute(
        text(f"SELECT household_id FROM {table_name} WHERE {entity_field} = :entity_id LIMIT 1"),
        {'entity_id': entity_id},
    ).mappings().first()
    if not row or not row.get('household_id'):
        raise HTTPException(status_code=404, detail='Onbekende resource')
    household_id = str(row['household_id'])
    if admin_only:
        return require_household_admin_context(authorization, household_id)
    return require_household_context(authorization, household_id)



def require_receipt_write_context(conn, receipt_table_id: str, authorization: str | None) -> dict:
    context = require_entity_household_access(conn, 'receipt_tables', receipt_table_id, authorization, admin_only=False)
    display_role = str(context.get('display_role') or '').strip().lower()
    if display_role not in {'admin', 'lid'}:
        raise HTTPException(status_code=403, detail='Alleen admin en lid mogen kassabonnen aanpassen')
    return context


def _receipt_line_display_clause(alias: str = 'rtl') -> str:
    return f"COALESCE({alias}.corrected_raw_label, {alias}.raw_label)"


def _receipt_line_quantity_clause(alias: str = 'rtl') -> str:
    return f"COALESCE({alias}.corrected_quantity, {alias}.quantity)"


def _receipt_line_unit_clause(alias: str = 'rtl') -> str:
    return f"COALESCE({alias}.corrected_unit, {alias}.unit)"


def _receipt_line_unit_price_clause(alias: str = 'rtl') -> str:
    return f"COALESCE({alias}.corrected_unit_price, {alias}.unit_price)"


def _receipt_line_total_clause(alias: str = 'rtl') -> str:
    return f"COALESCE({alias}.corrected_line_total, {alias}.line_total)"


def _receipt_line_active_filter(alias: str = 'rtl') -> str:
    return f"COALESCE({alias}.is_deleted, 0) = 0"

def resolve_authorized_household_id(
    authorization: str | None,
    requested_household_id: str | None = None,
    *,
    fallback: str = 'demo-household',
    require_authorization: bool = False,
) -> str:
    normalized_requested_household_id = normalize_optional_household_id(requested_household_id)
    if authorization:
        context = require_household_context(authorization, normalized_requested_household_id)
        return str(context.get('active_household_id') or fallback)
    if require_authorization:
        raise HTTPException(status_code=401, detail='Unauthorized')
    return str(normalized_requested_household_id or fallback)


def get_household_payload_for_user(user: dict):
    context = resolve_household_context_for_user(user)
    with engine.begin() as conn:
        capability_payload = build_capabilities_payload(conn, context)
    return {
        'id': context['active_household_id'],
        'naam': context['active_household_name'],
        'created_at': context.get('active_household_created_at'),
        'current_user_id': context['user_id'],
        'current_user_email': context['email'],
        'role': context['role'],
        'display_role': context['display_role'],
        'active_household_id': context['active_household_id'],
        'active_household_name': context['active_household_name'],
        'membership_count': context['membership_count'],
        'can_switch_households': context['can_switch_households'],
        'memberships': context['memberships'],
        'is_household_admin': context['display_role'] == 'admin',
        'can_edit_store_import_simplification_level': context['display_role'] == 'admin',
        'permissions': capability_payload['permissions'],
        'member_permission_policies': capability_payload['member_permission_policies'],
        'supported_permissions': capability_payload['supported_permissions'],
        'can_manage_member_permissions': capability_payload['can_manage_member_permissions'],
    }


def get_request_household_id(authorization: str | None, fallback: str = 'demo-household') -> str:
    return resolve_authorized_household_id(authorization, fallback=fallback, require_authorization=False)


class HouseholdAutomationSettingsUpdateRequest(BaseModel):
    mode: str = ARTICLE_AUTO_CONSUME_NONE

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value):
        normalized = normalize_household_auto_consume_mode(value)
        if normalized not in HOUSEHOLD_AUTO_CONSUME_ALLOWED:
            raise ValueError("Ongeldige huishoudautomatisering")
        return normalized

    @property
    def auto_consume_on_repurchase(self) -> bool:
        return self.mode != ARTICLE_AUTO_CONSUME_NONE


class HouseholdAlmostOutSettingsUpdateRequest(BaseModel):
    prediction_enabled: bool = False
    prediction_days: int = 0
    policy_mode: str = ALMOST_OUT_POLICY_ADVISORY

    @field_validator("prediction_days", mode='before')
    @classmethod
    def normalize_prediction_days(cls, value):
        if value in (None, ''):
            return 0
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            raise ValueError('prediction_days moet een geheel getal zijn')
        if normalized < 0:
            raise ValueError('prediction_days mag niet negatief zijn')
        return normalized

    @field_validator("policy_mode")
    @classmethod
    def validate_policy_mode(cls, value):
        normalized = str(value or '').strip().lower()
        if normalized not in ALMOST_OUT_POLICY_ALLOWED:
            raise ValueError('Ongeldige almost-out beleidsmodus')
        return normalized


class ArticleAutomationOverrideUpdateRequest(BaseModel):
    mode: str = ARTICLE_AUTO_CONSUME_FOLLOW_HOUSEHOLD

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value):
        normalized = normalize_article_auto_consume_mode(value)
        if normalized not in ARTICLE_AUTO_CONSUME_ALLOWED:
            raise ValueError("Ongeldige override-modus")
        return normalized


class StoreImportSimplificationUpdateRequest(BaseModel):
    store_import_simplification_level: str

    @field_validator("store_import_simplification_level")
    @classmethod
    def validate_level(cls, value):
        normalized = normalize_store_import_simplification_level(value)
        if normalized not in STORE_IMPORT_SIMPLIFICATION_ALLOWED:
            raise ValueError("Ongeldig vereenvoudigingsniveau")
        return normalized


class ArticleFieldVisibilityUpdateRequest(BaseModel):
    overview: dict = {}
    stock: dict = {}
    locations: dict = {}
    history: dict = {}
    analytics: dict = {}

    def normalized_visibility(self) -> dict:
        return normalize_article_field_visibility_map(self.model_dump())


class UserPrivacySettingsUpdateRequest(BaseModel):
    share_with_retailers: bool = False
    share_with_partners: bool = False
    allow_smart_features: bool = False
    allow_statistics: bool = False
    allow_personal_offers: bool = False
    allow_loyalty_import: bool = False

    def normalized_settings(self) -> dict:
        return normalize_user_privacy_settings_map(self.model_dump())


def build_live_article_option_id(article_name: str) -> str:
    return f"live::{(article_name or '').strip()}"


def get_household_article_option_by_id(conn, household_article_id: str | None, household_id: str | None = None):
    normalized_article_id = str(household_article_id or '').strip()
    if not normalized_article_id:
        return None
    params = {"id": normalized_article_id}
    household_clause = ""
    if household_id:
        params["household_id"] = str(household_id)
        household_clause = " AND household_id = :household_id"
    row = conn.execute(
        text(
            f"""
            SELECT id, household_id, naam, consumable, brand_or_maker
            FROM household_articles
            WHERE id = :id{household_clause}
            LIMIT 1
            """
        ),
        params,
    ).mappings().first()
    if not row or not row.get("naam"):
        return None
    return {
        "id": str(row.get("id")),
        "name": str(row.get("naam") or '').strip(),
        "brand": str(row.get("brand_or_maker") or '').strip(),
        "consumable": bool(row.get("consumable")) if row.get("consumable") is not None else infer_consumable_from_name(str(row.get("naam") or '')),
    }


def resolve_household_article_selection_to_id(conn, household_id: str | None, article_selection_id: str | None, *, create_if_missing: bool = False) -> str | None:
    normalized_selection = str(article_selection_id or '').strip()
    normalized_household_id = str(household_id or '').strip()
    if not normalized_selection:
        return None

    direct_row = get_household_article_option_by_id(conn, normalized_selection, normalized_household_id or None)
    if direct_row and direct_row.get('id'):
        return str(direct_row['id'])

    article_option = resolve_review_article_option(conn, normalized_selection, normalized_household_id or None)
    article_name = str((article_option or {}).get('name') or '').strip()
    if not article_name or not normalized_household_id:
        return None

    existing_row = get_household_article_row_by_name(conn, normalized_household_id, article_name)
    if existing_row and existing_row.get('id'):
        return str(existing_row.get('id'))

    if not create_if_missing:
        return None

    try:
        return ensure_household_article(
            conn,
            normalized_household_id,
            article_name,
            consumable=(article_option or {}).get('consumable'),
        )
    except Exception:
        return None


def get_store_review_article_options(conn):
    items = [dict(item) for item in MOCK_ARTICLE_OPTIONS]
    seen_names = {item["name"].strip().lower() for item in items if item.get("name")}

    household_rows = conn.execute(
        text(
            """
            SELECT id, naam AS article_name, consumable, brand_or_maker
            FROM household_articles
            WHERE trim(COALESCE(naam, '')) <> ''
            ORDER BY lower(naam) ASC, id ASC
            """
        )
    ).mappings().all()

    for row in household_rows:
        article_name = (row["article_name"] or "").strip()
        if not article_name:
            continue
        normalized = article_name.lower()
        if normalized in seen_names:
            continue
        items.append({
            "id": str(row.get("id")),
            "name": article_name,
            "brand": str(row.get("brand_or_maker") or '').strip(),
            "consumable": bool(row["consumable"]) if row.get("consumable") is not None else infer_consumable_from_name(article_name),
        })
        seen_names.add(normalized)

    inventory_names = conn.execute(
        text(
            """
            SELECT DISTINCT naam AS article_name
            FROM inventory
            WHERE trim(COALESCE(naam, '')) <> ''
            ORDER BY lower(naam) ASC
            """
        )
    ).mappings().all()

    for row in inventory_names:
        article_name = (row["article_name"] or "").strip()
        if not article_name:
            continue
        normalized = article_name.lower()
        if normalized in seen_names:
            continue
        items.append({
            "id": build_live_article_option_id(article_name),
            "name": article_name,
            "brand": "",
            "consumable": infer_consumable_from_name(article_name),
        })
        seen_names.add(normalized)

    return items


def find_generic_existing_article_match(conn, household_id: str | None, article_name: str | None) -> str | None:
    normalized_name = normalize_household_article_name(article_name)
    if not normalized_name:
        return None

    tokens = [part for part in normalized_name.lower().split() if part]
    if len(tokens) < 2:
        return None

    generic_candidate = tokens[-1]
    if len(generic_candidate) < 4:
        return None

    row = conn.execute(
        text(
            """
            SELECT article_name
            FROM (
                SELECT naam AS article_name FROM household_articles WHERE household_id = :household_id
                UNION
                SELECT naam AS article_name FROM inventory WHERE household_id = :household_id
            ) src
            WHERE lower(trim(article_name)) = lower(trim(:article_name))
            LIMIT 1
            """
        ),
        {"household_id": str(household_id or '1'), "article_name": generic_candidate},
    ).mappings().first()

    if row and row.get("article_name"):
        return str(row["article_name"]).strip()
    return None


def resolve_processing_article(conn, household_id: str | None, article: dict | None) -> dict | None:
    if not article:
        return article

    article_id = str(article.get('id') or '')
    article_name = str(article.get('name') or '').strip()
    if not article_name:
        return article

    # Wanneer een winkelregel aan een mock-artikel als 'Volkoren pasta' is gekoppeld,
    # maar het huishouden al een generiek bestaand artikel 'Pasta' heeft, willen we de
    # voorraadmutatie en historie aan dat bestaande artikel hangen. Dat voorkomt dat de
    # aankoop buiten beeld landt op een nieuw/quasi-los artikel.
    if article_id.startswith('live::'):
        return article

    generic_match = find_generic_existing_article_match(conn, household_id, article_name)
    if generic_match and generic_match.lower() != article_name.lower():
        consumable = get_article_consumable_state(conn, household_id or '1', build_live_article_option_id(generic_match), generic_match)
        return {
            'id': build_live_article_option_id(generic_match),
            'name': generic_match,
            'brand': article.get('brand') or '',
            'consumable': consumable,
        }

    return article


def resolve_review_article_option(conn, article_id: str | None, household_id: str | None = None):
    if not article_id:
        return None
    article_id = str(article_id)
    if article_id in MOCK_ARTICLE_LOOKUP:
        return dict(MOCK_ARTICLE_LOOKUP[article_id])

    household_match = get_household_article_option_by_id(conn, article_id, household_id)
    if household_match:
        return household_match

    if article_id.startswith("live::"):
        article_name = article_id.split("::", 1)[1].strip()
        if article_name:
            existing_row = get_household_article_row_by_name(conn, household_id or '1', article_name)
            if existing_row and existing_row.get('id'):
                return {
                    "id": str(existing_row.get('id')),
                    "name": str(existing_row.get('naam') or article_name).strip(),
                    "brand": str(existing_row.get('brand_or_maker') or '').strip(),
                    "consumable": bool(existing_row.get('consumable')) if existing_row.get('consumable') is not None else infer_consumable_from_name(article_name),
                }
            consumable = get_article_consumable_state(conn, household_id or '1', article_id, article_name)
            return {"id": article_id, "name": article_name, "brand": "", "consumable": consumable}
        return None

    inventory_match = conn.execute(
        text(
            """
            SELECT article_name AS naam, consumable
            FROM (
                SELECT naam AS article_name, consumable FROM household_articles
                UNION
                SELECT naam AS article_name, NULL AS consumable FROM inventory
            ) src
            WHERE lower(article_name) = lower(:article_name)
            LIMIT 1
            """
        ),
        {"article_name": article_id},
    ).mappings().first()
    if inventory_match and inventory_match.get("naam"):
        article_name = inventory_match["naam"].strip()
        existing_row = get_household_article_row_by_name(conn, household_id or '1', article_name)
        if existing_row and existing_row.get('id'):
            return {
                "id": str(existing_row.get('id')),
                "name": str(existing_row.get('naam') or article_name).strip(),
                "brand": str(existing_row.get('brand_or_maker') or '').strip(),
                "consumable": bool(existing_row.get('consumable')) if existing_row.get('consumable') is not None else infer_consumable_from_name(article_name),
            }
        consumable = inventory_match.get("consumable")
        if consumable is None:
            consumable = get_article_consumable_state(conn, household_id or '1', build_live_article_option_id(article_name), article_name)
        return {"id": build_live_article_option_id(article_name), "name": article_name, "brand": "", "consumable": bool(consumable)}

    return None

def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def seed_store_providers():
    with engine.begin() as conn:
        for provider_code, provider in STORE_PROVIDER_DEFINITIONS.items():
            existing = conn.execute(
                text("SELECT id FROM store_providers WHERE code = :code"),
                {"code": provider_code},
            ).first()
            if existing:
                conn.execute(
                    text(
                        """
                        UPDATE store_providers
                        SET name = :name, status = :status, import_mode = :import_mode
                        WHERE code = :code
                        """
                    ),
                    {
                        "code": provider_code,
                        "name": provider["name"],
                        "status": provider["status"],
                        "import_mode": provider["import_mode"],
                    },
                )
                continue

            conn.execute(
                text(
                    """
                    INSERT INTO store_providers (id, code, name, status, import_mode)
                    VALUES (:id, :code, :name, :status, :import_mode)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "code": provider_code,
                    "name": provider["name"],
                    "status": provider["status"],
                    "import_mode": provider["import_mode"],
                },
            )



def get_provider_mock_lines(provider_code: str, mock_profile: str):
    provider_profiles = MOCK_PURCHASES_BY_PROVIDER.get(provider_code, {})
    lines = provider_profiles.get(mock_profile)
    if not lines:
        raise HTTPException(status_code=400, detail="Onbekend mock_profile")
    return [dict(line) for line in lines]


def get_provider_mock_batch_metadata(provider_code: str, mock_profile: str):
    provider_meta = MOCK_BATCH_METADATA_BY_PROVIDER.get(provider_code, {})
    meta = provider_meta.get(mock_profile, {})
    definition = STORE_PROVIDER_DEFINITIONS.get(provider_code, {})
    provider_name = definition.get("name") or provider_code.title()
    return {
        "purchase_date": meta.get("purchase_date") or "Onbekend",
        "store_name": meta.get("store_name") or provider_name,
        "store_label": meta.get("store_label") or provider_name,
    }


def build_store_import_note(provider_code: str, batch_id: str, line_id: str, raw_article_name: str):
    return f"store_import;provider={provider_code};batch={batch_id};line={line_id};raw={raw_article_name}"




def ensure_release_2_schema():
    with engine.begin() as conn:
        line_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(purchase_import_lines)")).fetchall()}
        batch_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(purchase_import_batches)")).fetchall()}

        if "matched_household_article_id" not in line_columns:
            conn.execute(text("ALTER TABLE purchase_import_lines ADD COLUMN matched_household_article_id TEXT"))
        if "review_decision" not in line_columns:
            conn.execute(text("ALTER TABLE purchase_import_lines ADD COLUMN review_decision TEXT DEFAULT 'pending'"))
        if "reviewed_at" not in line_columns:
            conn.execute(text("ALTER TABLE purchase_import_lines ADD COLUMN reviewed_at DATETIME"))
        if "reviewed_by" not in line_columns:
            conn.execute(text("ALTER TABLE purchase_import_lines ADD COLUMN reviewed_by TEXT"))
        if "ui_sort_order" not in line_columns:
            conn.execute(text("ALTER TABLE purchase_import_lines ADD COLUMN ui_sort_order INTEGER"))
        if "matched_global_product_id" not in line_columns:
            conn.execute(text("ALTER TABLE purchase_import_lines ADD COLUMN matched_global_product_id TEXT"))

        if "import_status" not in batch_columns:
            conn.execute(text("ALTER TABLE purchase_import_batches ADD COLUMN import_status TEXT DEFAULT 'new'"))


def ensure_release_3_schema():
    with engine.begin() as conn:
        line_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(purchase_import_lines)")).fetchall()}
        batch_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(purchase_import_batches)")).fetchall()}

        if "processing_status" not in line_columns:
            conn.execute(text("ALTER TABLE purchase_import_lines ADD COLUMN processing_status TEXT DEFAULT 'pending'"))
        if "processed_at" not in line_columns:
            conn.execute(text("ALTER TABLE purchase_import_lines ADD COLUMN processed_at DATETIME"))
        if "processed_event_id" not in line_columns:
            conn.execute(text("ALTER TABLE purchase_import_lines ADD COLUMN processed_event_id TEXT"))
        if "processing_error" not in line_columns:
            conn.execute(text("ALTER TABLE purchase_import_lines ADD COLUMN processing_error TEXT"))
        if "final_location_id" not in line_columns:
            conn.execute(text("ALTER TABLE purchase_import_lines ADD COLUMN final_location_id TEXT"))

        if "processed_at" not in batch_columns:
            conn.execute(text("ALTER TABLE purchase_import_batches ADD COLUMN processed_at DATETIME"))

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS inventory_events (
                    id TEXT PRIMARY KEY,
                    household_id TEXT NOT NULL,
                    article_id TEXT,
                    article_name TEXT NOT NULL,
                    location_id TEXT,
                    location_label TEXT,
                    event_type TEXT NOT NULL,
                    quantity NUMERIC NOT NULL,
                    old_quantity NUMERIC,
                    new_quantity NUMERIC,
                    source TEXT NOT NULL,
                    note TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        inventory_event_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(inventory_events)")).fetchall()}
        if "old_quantity" not in inventory_event_columns:
            conn.execute(text("ALTER TABLE inventory_events ADD COLUMN old_quantity NUMERIC"))
        if "new_quantity" not in inventory_event_columns:
            conn.execute(text("ALTER TABLE inventory_events ADD COLUMN new_quantity NUMERIC"))



def ensure_release_4_schema():
    with engine.begin() as conn:
        line_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(purchase_import_lines)")).fetchall()}

        if "suggested_household_article_id" not in line_columns:
            conn.execute(text("ALTER TABLE purchase_import_lines ADD COLUMN suggested_household_article_id TEXT"))
        if "suggested_location_id" not in line_columns:
            conn.execute(text("ALTER TABLE purchase_import_lines ADD COLUMN suggested_location_id TEXT"))
        if "suggestion_confidence" not in line_columns:
            conn.execute(text("ALTER TABLE purchase_import_lines ADD COLUMN suggestion_confidence TEXT"))
        if "suggestion_reason" not in line_columns:
            conn.execute(text("ALTER TABLE purchase_import_lines ADD COLUMN suggestion_reason TEXT"))
        if "is_auto_prefilled" not in line_columns:
            conn.execute(text("ALTER TABLE purchase_import_lines ADD COLUMN is_auto_prefilled INTEGER DEFAULT 0"))

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS store_import_memory (
                    id TEXT PRIMARY KEY,
                    household_id TEXT NOT NULL,
                    store_provider_code TEXT NOT NULL,
                    raw_article_name TEXT NOT NULL,
                    raw_brand TEXT,
                    normalized_key TEXT NOT NULL,
                    matched_household_article_id TEXT NOT NULL,
                    preferred_location_id TEXT,
                    times_confirmed INTEGER NOT NULL DEFAULT 1,
                    last_used_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_store_import_memory_unique ON store_import_memory (household_id, store_provider_code, normalized_key)"))


def ensure_release_803_schema():
    with engine.begin() as conn:
        line_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(purchase_import_lines)")).fetchall()}
        if "processing_diagnostics" not in line_columns:
            conn.execute(text("ALTER TABLE purchase_import_lines ADD COLUMN processing_diagnostics TEXT"))


def ensure_release_813_schema():
    with engine.begin() as conn:
        line_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(purchase_import_lines)")).fetchall()}
        if "article_override_mode" not in line_columns:
            conn.execute(text("ALTER TABLE purchase_import_lines ADD COLUMN article_override_mode TEXT DEFAULT 'auto'"))
        if "location_override_mode" not in line_columns:
            conn.execute(text("ALTER TABLE purchase_import_lines ADD COLUMN location_override_mode TEXT DEFAULT 'auto'"))
        conn.execute(text("UPDATE purchase_import_lines SET article_override_mode = COALESCE(article_override_mode, 'auto')"))
        conn.execute(text("UPDATE purchase_import_lines SET location_override_mode = COALESCE(location_override_mode, 'auto')"))


def ensure_release_814_schema():
    with engine.begin() as conn:
        inventory_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(inventory)")).fetchall()}
        if "status" not in inventory_columns:
            conn.execute(text("ALTER TABLE inventory ADD COLUMN status TEXT DEFAULT 'active'"))
        if "archived_at" not in inventory_columns:
            conn.execute(text("ALTER TABLE inventory ADD COLUMN archived_at DATETIME"))
        if "archive_reason" not in inventory_columns:
            conn.execute(text("ALTER TABLE inventory ADD COLUMN archive_reason TEXT"))
        conn.execute(text("UPDATE inventory SET status = COALESCE(status, 'active')"))


def ensure_release_902_schema():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS receipt_sources (
                    id TEXT PRIMARY KEY,
                    household_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    label TEXT NOT NULL,
                    source_path TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    last_scan_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS raw_receipts (
                    id TEXT PRIMARY KEY,
                    household_id TEXT NOT NULL,
                    source_id TEXT,
                    original_filename TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    storage_path TEXT NOT NULL,
                    sha256_hash TEXT NOT NULL,
                    imported_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    duplicate_of_raw_receipt_id TEXT,
                    raw_status TEXT NOT NULL DEFAULT 'imported',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS receipt_tables (
                    id TEXT PRIMARY KEY,
                    raw_receipt_id TEXT NOT NULL UNIQUE,
                    household_id TEXT NOT NULL,
                    store_name TEXT,
                    store_branch TEXT,
                    purchase_at DATETIME,
                    total_amount NUMERIC(12,2),
                    discount_total NUMERIC(12,2),
                    currency TEXT NOT NULL DEFAULT 'EUR',
                    parse_status TEXT NOT NULL DEFAULT 'parsed',
                    confidence_score NUMERIC(5,4),
                    line_count INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS receipt_table_lines (
                    id TEXT PRIMARY KEY,
                    receipt_table_id TEXT NOT NULL,
                    line_index INTEGER NOT NULL,
                    raw_label TEXT NOT NULL,
                    normalized_label TEXT,
                    quantity NUMERIC(12,3),
                    unit TEXT,
                    unit_price NUMERIC(12,4),
                    line_total NUMERIC(12,2),
                    discount_amount NUMERIC(12,2),
                    barcode TEXT,
                    article_match_status TEXT NOT NULL DEFAULT 'unmatched',
                    matched_article_id TEXT,
                    matched_global_product_id TEXT,
                    confidence_score NUMERIC(5,4),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS receipt_processing_runs (
                    id TEXT PRIMARY KEY,
                    source_id TEXT,
                    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    finished_at DATETIME,
                    files_found INTEGER NOT NULL DEFAULT 0,
                    files_imported INTEGER NOT NULL DEFAULT 0,
                    files_skipped INTEGER NOT NULL DEFAULT 0,
                    files_failed INTEGER NOT NULL DEFAULT 0
                )
                """
            )
        )

        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_receipt_sources_household_active ON receipt_sources (household_id, is_active)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_receipts_household_hash ON raw_receipts (household_id, sha256_hash)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_raw_receipts_source_imported ON raw_receipts (source_id, imported_at DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_receipt_tables_household_created ON receipt_tables (household_id, created_at DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_receipt_tables_status_created ON receipt_tables (parse_status, created_at DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_receipt_lines_receipt_lineindex ON receipt_table_lines (receipt_table_id, line_index)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_receipt_table_lines_receipt_line ON receipt_table_lines (receipt_table_id, line_index)"))


def ensure_release_932_schema():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS receipt_email_messages (
                    raw_receipt_id TEXT PRIMARY KEY,
                    household_id TEXT NOT NULL,
                    sender_email TEXT,
                    sender_name TEXT,
                    subject TEXT,
                    received_at DATETIME,
                    body_text TEXT,
                    body_html TEXT,
                    selected_part_type TEXT,
                    selected_filename TEXT,
                    selected_mime_type TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_receipt_email_messages_household_received ON receipt_email_messages (household_id, received_at DESC)"))


def ensure_release_933_schema():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS receipt_gmail_accounts (
                    household_id TEXT PRIMARY KEY,
                    source_id TEXT,
                    google_email TEXT,
                    google_user_sub TEXT,
                    label_name TEXT NOT NULL,
                    label_id TEXT,
                    access_token TEXT,
                    refresh_token TEXT,
                    token_expires_at DATETIME,
                    sync_status TEXT NOT NULL DEFAULT 'not_connected',
                    last_synced_at DATETIME,
                    last_error TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS receipt_gmail_imports (
                    id TEXT PRIMARY KEY,
                    household_id TEXT NOT NULL,
                    gmail_message_id TEXT NOT NULL,
                    gmail_thread_id TEXT,
                    gmail_history_id TEXT,
                    gmail_internal_date DATETIME,
                    raw_receipt_id TEXT,
                    receipt_table_id TEXT,
                    import_status TEXT NOT NULL DEFAULT 'imported',
                    error_message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_receipt_gmail_imports_household_message ON receipt_gmail_imports (household_id, gmail_message_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_receipt_gmail_accounts_sync ON receipt_gmail_accounts (sync_status, last_synced_at DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_receipt_gmail_imports_household_created ON receipt_gmail_imports (household_id, created_at DESC)"))




def ensure_release_935_schema():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS receipt_inbound_events (
                    id TEXT PRIMARY KEY,
                    household_id TEXT,
                    source_id TEXT,
                    provider TEXT NOT NULL,
                    provider_email_id TEXT NOT NULL,
                    provider_message_id TEXT,
                    route_address TEXT,
                    sender_email TEXT,
                    sender_name TEXT,
                    subject TEXT,
                    received_at DATETIME,
                    webhook_received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    import_status TEXT NOT NULL DEFAULT 'received',
                    raw_receipt_id TEXT,
                    receipt_table_id TEXT,
                    error_message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_receipt_inbound_provider_email ON receipt_inbound_events (provider, provider_email_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_receipt_inbound_household_received ON receipt_inbound_events (household_id, received_at DESC, created_at DESC)"))


def ensure_release_940_schema():
    with engine.begin() as conn:
        raw_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(raw_receipts)")).fetchall()}
        receipt_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(receipt_tables)")).fetchall()}
        if 'deleted_at' not in raw_columns:
            conn.execute(text("ALTER TABLE raw_receipts ADD COLUMN deleted_at DATETIME"))
        if 'deleted_at' not in receipt_columns:
            conn.execute(text("ALTER TABLE receipt_tables ADD COLUMN deleted_at DATETIME"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_raw_receipts_household_deleted ON raw_receipts (household_id, deleted_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_receipt_tables_household_deleted ON receipt_tables (household_id, deleted_at)"))



def ensure_release_941_receipt_edit_schema():
    with engine.begin() as conn:
        receipt_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(receipt_tables)")).fetchall()}
        line_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(receipt_table_lines)")).fetchall()}
        receipt_additions = {
            'reference': 'TEXT',
            'notes': 'TEXT',
            'corrected_by_user_email': 'TEXT',
            'approved_by_user_email': 'TEXT',
            'approved_at': 'DATETIME',
            'reviewed_at': 'DATETIME',
            'totals_overridden': 'INTEGER NOT NULL DEFAULT 0',
            'totals_override_by_user_email': 'TEXT',
            'totals_override_at': 'DATETIME',
        }
        for column_name, column_type in receipt_additions.items():
            if column_name not in receipt_columns:
                conn.execute(text(f"ALTER TABLE receipt_tables ADD COLUMN {column_name} {column_type}"))
        line_additions = {
            'corrected_raw_label': 'TEXT',
            'corrected_quantity': 'NUMERIC(12,3)',
            'corrected_unit': 'TEXT',
            'corrected_unit_price': 'NUMERIC(12,4)',
            'corrected_line_total': 'NUMERIC(12,2)',
            'is_deleted': 'INTEGER NOT NULL DEFAULT 0',
            'is_validated': 'INTEGER NOT NULL DEFAULT 0',
            'matched_global_product_id': 'TEXT',
        }
        for column_name, column_type in line_additions.items():
            if column_name not in line_columns:
                conn.execute(text(f"ALTER TABLE receipt_table_lines ADD COLUMN {column_name} {column_type}"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_receipt_lines_receipt_active ON receipt_table_lines (receipt_table_id, is_deleted, line_index)"))
def ensure_receipt_storage_root():
    RECEIPT_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)


def normalize_store_memory_key(article_name: str | None, brand: str | None):
    name = (article_name or "").strip().lower()
    brand_value = (brand or "").strip().lower()
    return f"{name}||{brand_value}"


def apply_prefill_to_batch(conn, batch_id: str, household_id: str, store_provider_code: str):
    simplification_level = get_household_store_import_simplification_level(conn, household_id)
    lines = conn.execute(
        text(
            """
            SELECT id, article_name_raw, brand_raw
            FROM purchase_import_lines
            WHERE batch_id = :batch_id
              AND COALESCE(processing_status, 'pending') != 'processed'
            ORDER BY COALESCE(ui_sort_order, 999999), created_at ASC, id ASC
            """
        ),
        {"batch_id": batch_id},
    ).mappings().all()

    article_prefills = 0
    location_prefills = 0
    fully_prefilled = 0

    for line in lines:
        memory = conn.execute(
            text(
                """
                SELECT matched_household_article_id, preferred_location_id, times_confirmed
                FROM store_import_memory
                WHERE household_id = :household_id
                  AND store_provider_code = :store_provider_code
                  AND normalized_key = :normalized_key
                ORDER BY last_used_at DESC
                LIMIT 1
                """
            ),
            {
                "household_id": household_id,
                "store_provider_code": store_provider_code,
                "normalized_key": normalize_store_memory_key(line["article_name_raw"], line["brand_raw"]),
            },
        ).mappings().first()

        if not memory:
            continue

        matched_article_id = memory["matched_household_article_id"]
        preferred_location_id = memory["preferred_location_id"]
        times_confirmed = int(memory["times_confirmed"] or 0)
        can_suggest_article = bool(matched_article_id)
        can_suggest_location = bool(preferred_location_id)
        can_auto_fill = simplification_level in {"gebalanceerd", "maximaal_gemak"} and can_suggest_article and can_suggest_location and times_confirmed >= 1

        if simplification_level == "voorzichtig":
            suggestion_reason = "Voorstel op basis van eerdere keuze — niveau Voorzichtig"
            suggestion_confidence = "medium" if (can_suggest_article or can_suggest_location) else None
        elif simplification_level == "maximaal_gemak":
            suggestion_reason = "Automatisch voorbereid — niveau Maximaal gemak"
            suggestion_confidence = "high" if can_auto_fill else "medium"
        else:
            suggestion_reason = "Automatisch voorbereid — niveau Gebalanceerd" if can_auto_fill else "Controleer voorstel — niveau Gebalanceerd"
            suggestion_confidence = "high" if can_auto_fill else "medium"

        conn.execute(
            text(
                """
                UPDATE purchase_import_lines
                SET suggested_household_article_id = :suggested_article_id,
                    suggested_location_id = :suggested_location_id,
                    suggestion_confidence = :suggestion_confidence,
                    suggestion_reason = :suggestion_reason,
                    is_auto_prefilled = CASE WHEN :can_auto_fill = 1 AND COALESCE(article_override_mode, 'auto') = 'auto' AND COALESCE(location_override_mode, 'auto') = 'auto' THEN 1 ELSE 0 END,
                    matched_household_article_id = CASE
                        WHEN COALESCE(article_override_mode, 'auto') = 'auto' AND :can_auto_fill = 1 THEN :matched_household_article_id
                        WHEN COALESCE(article_override_mode, 'auto') = 'auto' THEN NULL
                        ELSE matched_household_article_id
                    END,
                    target_location_id = CASE
                        WHEN COALESCE(location_override_mode, 'auto') = 'auto' AND :can_auto_fill = 1 THEN :target_location_id
                        WHEN COALESCE(location_override_mode, 'auto') = 'auto' THEN NULL
                        ELSE target_location_id
                    END,
                    match_status = CASE
                        WHEN COALESCE(article_override_mode, 'auto') = 'auto' THEN CASE WHEN :can_auto_fill = 1 AND :matched_household_article_id IS NOT NULL THEN 'matched' ELSE 'unmatched' END
                        ELSE CASE WHEN matched_household_article_id IS NOT NULL THEN 'matched' ELSE 'unmatched' END
                    END,
                    review_decision = CASE
                        WHEN COALESCE(article_override_mode, 'auto') = 'auto' AND COALESCE(location_override_mode, 'auto') = 'auto' THEN CASE WHEN :can_auto_fill = 1 THEN 'selected' ELSE 'pending' END
                        WHEN matched_household_article_id IS NULL OR target_location_id IS NULL THEN 'pending'
                        ELSE review_decision
                    END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {
                "id": line["id"],
                "suggested_article_id": matched_article_id if can_suggest_article else None,
                "suggested_location_id": preferred_location_id if can_suggest_location else None,
                "suggestion_confidence": suggestion_confidence,
                "suggestion_reason": suggestion_reason,
                "is_auto_prefilled": 1 if can_auto_fill else 0,
                "matched_household_article_id": matched_article_id if can_auto_fill else None,
                "target_location_id": preferred_location_id if can_auto_fill else None,
                "can_auto_fill": 1 if can_auto_fill else 0,
            },
        )
        if can_suggest_article:
            article_prefills += 1
        if can_suggest_location:
            location_prefills += 1
        if can_auto_fill:
            fully_prefilled += 1

    return {
        "article_prefills": article_prefills,
        "location_prefills": location_prefills,
        "fully_prefilled": fully_prefilled,
        "simplification_level": simplification_level,
    }


def remember_store_import_choice(conn, household_id: str, store_provider_code: str, raw_article_name: str, raw_brand: str | None, matched_household_article_id: str, preferred_location_id: str | None):
    normalized_key = normalize_store_memory_key(raw_article_name, raw_brand)
    existing = conn.execute(
        text(
            """
            SELECT id, times_confirmed
            FROM store_import_memory
            WHERE household_id = :household_id
              AND store_provider_code = :store_provider_code
              AND normalized_key = :normalized_key
            """
        ),
        {
            "household_id": household_id,
            "store_provider_code": store_provider_code,
            "normalized_key": normalized_key,
        },
    ).mappings().first()
    if existing:
        conn.execute(
            text(
                """
                UPDATE store_import_memory
                SET matched_household_article_id = :matched_household_article_id,
                    preferred_location_id = :preferred_location_id,
                    times_confirmed = :times_confirmed,
                    last_used_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {
                "id": existing["id"],
                "matched_household_article_id": matched_household_article_id,
                "preferred_location_id": preferred_location_id,
                "times_confirmed": int(existing["times_confirmed"] or 0) + 1,
            },
        )
    else:
        conn.execute(
            text(
                """
                INSERT INTO store_import_memory (
                    id, household_id, store_provider_code, raw_article_name, raw_brand,
                    normalized_key, matched_household_article_id, preferred_location_id,
                    times_confirmed, last_used_at, created_at, updated_at
                ) VALUES (
                    :id, :household_id, :store_provider_code, :raw_article_name, :raw_brand,
                    :normalized_key, :matched_household_article_id, :preferred_location_id,
                    1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "household_id": household_id,
                "store_provider_code": store_provider_code,
                "raw_article_name": raw_article_name,
                "raw_brand": raw_brand,
                "normalized_key": normalized_key,
                "matched_household_article_id": matched_household_article_id,
                "preferred_location_id": preferred_location_id,
            },
        )


def compute_batch_status(conn, batch_id: str) -> str:
    rows = conn.execute(
        text(
            """
            SELECT review_decision, processing_status
            FROM purchase_import_lines
            WHERE batch_id = :batch_id
            """
        ),
        {"batch_id": batch_id},
    ).fetchall()

    if not rows:
        return "new"

    decisions = [(row[0] or "pending") for row in rows]
    selected_rows = [row for row in rows if (row[0] or "pending") == "selected"]
    selected_processing = [(row[1] or "pending") for row in selected_rows]

    if selected_rows:
        if all(status == "processed" for status in selected_processing):
            return "processed"
        if all(status == "failed" for status in selected_processing):
            return "failed"
        if any(status in {"processed", "failed"} for status in selected_processing):
            return "partially_processed"

    if all(decision != "pending" for decision in decisions):
        return "reviewed"
    if any(decision != "pending" for decision in decisions):
        return "in_review"
    return "new"


def update_batch_status(conn, batch_id: str) -> str:
    status = compute_batch_status(conn, batch_id)
    conn.execute(
        text(
            """
            UPDATE purchase_import_batches
            SET import_status = :status
            WHERE id = :id
            """
        ),
        {"status": status, "id": batch_id},
    )
    return status


def resolve_target_location(conn, target_location_id: str | None):
    if not target_location_id:
        return None

    sublocation = conn.execute(
        text(
            """
            SELECT sl.id AS location_id, sl.space_id, s.naam AS space_name, sl.naam AS sublocation_name
            FROM sublocations sl
            JOIN spaces s ON s.id = sl.space_id
            WHERE sl.id = :id
            """
        ),
        {"id": target_location_id},
    ).mappings().first()
    if sublocation:
        return {
            "location_id": sublocation["location_id"],
            "space_id": sublocation["space_id"],
            "sublocation_id": sublocation["location_id"],
            "location_label": f"{sublocation['space_name']} / {sublocation['sublocation_name']}",
        }

    space = conn.execute(
        text("SELECT id, naam FROM spaces WHERE id = :id"),
        {"id": target_location_id},
    ).mappings().first()
    if space:
        return {
            "location_id": space["id"],
            "space_id": space["id"],
            "sublocation_id": None,
            "location_label": space["naam"],
        }
    return None


def build_purchase_import_line_reference(conn, line_id: str) -> dict:
    row = conn.execute(
        text(
            """
            SELECT pil.id,
                   pil.batch_id,
                   pil.external_line_ref,
                   pil.article_name_raw,
                   pil.target_location_id,
                   pil.review_decision,
                   COALESCE(pil.ui_sort_order, 0) AS ui_sort_order
            FROM purchase_import_lines pil
            WHERE pil.id = :id
            LIMIT 1
            """
        ),
        {"id": line_id},
    ).mappings().first()
    if not row:
        return {"line_id": str(line_id)}
    line_ref = str(row.get("external_line_ref") or '').strip()
    display_ref = line_ref or f"regel {int(row.get('ui_sort_order') or 0) + 1}"
    article_name = str(row.get("article_name_raw") or '').strip()
    return {
        "line_id": str(row.get("id") or line_id),
        "batch_id": str(row.get("batch_id") or ''),
        "external_line_ref": line_ref,
        "ui_line_number": int(row.get('ui_sort_order') or 0) + 1,
        "article_name": article_name,
        "target_location_id": str(row.get("target_location_id") or ''),
        "review_decision": str(row.get("review_decision") or 'pending'),
        "display_label": f"{display_ref}: {article_name}" if article_name else display_ref,
    }


def validate_purchase_import_target_location(conn, line_id: str, target_location_id: str | None):
    line_ref = build_purchase_import_line_reference(conn, line_id)
    if not target_location_id:
        return None, line_ref
    resolved = resolve_target_location(conn, target_location_id)
    return resolved, line_ref



def resolve_space_and_sublocation_ids(conn, household_id: str, space_id: str | None = None, sublocation_id: str | None = None, space_name: str | None = None, sublocation_name: str | None = None):
    household_id = str(household_id or 'demo-household')
    normalized_space_name = ' '.join(str(space_name or '').strip().split()) or None
    normalized_sublocation_name = ' '.join(str(sublocation_name or '').strip().split()) or None

    resolved_space_id = space_id
    resolved_sublocation_id = sublocation_id

    if resolved_space_id:
        space_row = conn.execute(
            text("SELECT id FROM spaces WHERE id = :id AND household_id = :household_id"),
            {"id": resolved_space_id, "household_id": household_id},
        ).mappings().first()
        if not space_row:
            raise HTTPException(status_code=400, detail="Onbekende space_id")
    elif normalized_space_name:
        space_row = conn.execute(
            text("SELECT id FROM spaces WHERE household_id = :household_id AND lower(trim(naam)) = lower(trim(:naam)) LIMIT 1"),
            {"household_id": household_id, "naam": normalized_space_name},
        ).mappings().first()
        if space_row:
            resolved_space_id = space_row['id']
        else:
            resolved_space_id = conn.execute(
                text("INSERT INTO spaces (id, naam, household_id) VALUES (lower(hex(randomblob(16))), :naam, :household_id) RETURNING id"),
                {"naam": normalized_space_name, "household_id": household_id},
            ).scalar_one()

    if resolved_sublocation_id:
        sub_row = conn.execute(
            text("SELECT id, space_id FROM sublocations WHERE id = :id"),
            {"id": resolved_sublocation_id},
        ).mappings().first()
        if not sub_row:
            raise HTTPException(status_code=400, detail="Onbekende sublocation_id")
        if resolved_space_id and str(sub_row['space_id']) != str(resolved_space_id):
            raise HTTPException(status_code=400, detail="sublocation_id hoort niet bij de gekozen ruimte")
        resolved_space_id = resolved_space_id or sub_row['space_id']
    elif normalized_sublocation_name:
        if not resolved_space_id:
            raise HTTPException(status_code=400, detail="Ruimte is verplicht voor een sublocatie")
        sub_row = conn.execute(
            text("SELECT id FROM sublocations WHERE space_id = :space_id AND lower(trim(naam)) = lower(trim(:naam)) LIMIT 1"),
            {"space_id": resolved_space_id, "naam": normalized_sublocation_name},
        ).mappings().first()
        if sub_row:
            resolved_sublocation_id = sub_row['id']
        else:
            resolved_sublocation_id = conn.execute(
                text("INSERT INTO sublocations (id, naam, space_id) VALUES (lower(hex(randomblob(16))), :naam, :space_id) RETURNING id"),
                {"naam": normalized_sublocation_name, "space_id": resolved_space_id},
            ).scalar_one()

    return resolved_space_id, resolved_sublocation_id

def normalize_store_import_quantity(quantity_raw, unit_raw):
    try:
        quantity = float(quantity_raw or 0)
    except (TypeError, ValueError):
        quantity = 0

    if quantity <= 0:
        return 0

    unit = (unit_raw or '').strip().lower()
    if unit in {'stuk', 'stuks', 'pcs', 'piece', 'pieces'}:
        return max(1, int(round(quantity)))
    if unit in {'g', 'gram', 'grams', 'kg', 'kilogram', 'kilograms', 'ml', 'milliliter', 'milliliters', 'l', 'liter', 'liters'}:
        return 1
    return 1



def build_resolved_location_payload(conn, household_id: str, space_id: str | None, sublocation_id: str | None):
    safe_space_id, safe_sublocation_id = resolve_space_and_sublocation_ids(
        conn,
        household_id,
        space_id=space_id,
        sublocation_id=sublocation_id,
    )
    row = conn.execute(
        text(
            """
            SELECT COALESCE(s.naam, '') AS space_name, COALESCE(sl.naam, '') AS sublocation_name
            FROM spaces s
            LEFT JOIN sublocations sl ON sl.id = :sublocation_id
            WHERE s.id = :space_id
            LIMIT 1
            """
        ),
        {"space_id": safe_space_id, "sublocation_id": safe_sublocation_id},
    ).mappings().first() or {}
    return {
        "space_id": safe_space_id,
        "sublocation_id": safe_sublocation_id,
        "space_name": row.get("space_name") or None,
        "sublocation_name": row.get("sublocation_name") or None,
        "location_id": safe_sublocation_id or safe_space_id,
        "location_label": " / ".join(part for part in [row.get("space_name") or "", row.get("sublocation_name") or ""] if part),
    }



def get_article_total_quantity(conn, household_id: str, article_name: str) -> int:
    row = conn.execute(
        text(
            """
            SELECT COALESCE(SUM(aantal), 0) AS total_quantity
            FROM inventory
            WHERE household_id = :household_id
              AND lower(trim(naam)) = lower(trim(:naam))
              AND COALESCE(status, 'active') = 'active'
            """
        ),
        {"household_id": str(household_id), "naam": article_name},
    ).mappings().first()
    return int(row["total_quantity"] or 0) if row else 0


def require_resolved_location(resolved_location: dict | None):
    if not resolved_location:
        raise HTTPException(status_code=400, detail="Geen geldige locatie beschikbaar voor voorraadmutatie")
    if not resolved_location.get("space_id") and not resolved_location.get("sublocation_id"):
        raise HTTPException(status_code=400, detail="Voorraadmutatie vereist een expliciete ruimte of sublocatie")
    return resolved_location


def create_inventory_event(
    conn,
    *,
    household_id: str,
    article_id: str,
    article_name: str,
    resolved_location: dict,
    event_type: str,
    quantity: float,
    source: str,
    note: str,
    old_quantity=None,
    new_quantity=None,
    purchase_date: str | None = None,
    supplier_name: str | None = None,
    article_number: str | None = None,
    price: float | None = None,
    currency: str | None = None,
    barcode: str | None = None,
):
    safe_location = require_resolved_location(resolved_location)
    event_id = str(uuid.uuid4())
    conn.execute(
        text(
            """
            INSERT INTO inventory_events (
                id, household_id, article_id, article_name, location_id, location_label,
                event_type, quantity, old_quantity, new_quantity, source, note,
                purchase_date, supplier_name, article_number, price, currency, barcode, created_at
            ) VALUES (
                :id, :household_id, :article_id, :article_name, :location_id, :location_label,
                :event_type, :quantity, :old_quantity, :new_quantity, :source, :note,
                :purchase_date, :supplier_name, :article_number, :price, :currency, :barcode, CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "id": event_id,
            "household_id": str(household_id),
            "article_id": article_id,
            "article_name": article_name,
            "location_id": safe_location["location_id"],
            "location_label": safe_location["location_label"],
            "event_type": event_type,
            "quantity": quantity,
            "old_quantity": old_quantity,
            "new_quantity": new_quantity,
            "source": source,
            "note": note,
            "purchase_date": purchase_date,
            "supplier_name": supplier_name,
            "article_number": article_number,
            "price": price,
            "currency": currency,
            "barcode": barcode,
        },
    )
    return event_id


def apply_inventory_purchase(conn, household_id: str, article_name: str, quantity: float, resolved_location: dict):
    safe_location = require_resolved_location(resolved_location)
    space_id = safe_location["space_id"]
    sublocation_id = safe_location["sublocation_id"]

    existing = conn.execute(
        text(
            """
            SELECT id, aantal
            FROM inventory
            WHERE household_id = :household_id
              AND naam = :naam
              AND COALESCE(space_id, '') = COALESCE(:space_id, '')
              AND COALESCE(sublocation_id, '') = COALESCE(:sublocation_id, '')
            """
        ),
        {
            "household_id": household_id,
            "naam": article_name,
            "space_id": space_id,
            "sublocation_id": sublocation_id,
        },
    ).mappings().first()

    quantity_int = int(quantity)

    if existing:
        conn.execute(
            text(
                """
                UPDATE inventory
                SET aantal = aantal + :quantity, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {"quantity": quantity_int, "id": existing["id"]},
        )
        return existing["id"]

    inventory_id = str(uuid.uuid4())
    conn.execute(
        text(
            """
            INSERT INTO inventory (id, naam, aantal, household_id, space_id, sublocation_id, status, updated_at)
            VALUES (:id, :naam, :aantal, :household_id, :space_id, :sublocation_id, 'active', CURRENT_TIMESTAMP)
            """
        ),
        {
            "id": inventory_id,
            "naam": article_name,
            "aantal": quantity_int,
            "household_id": household_id,
            "space_id": space_id,
            "sublocation_id": sublocation_id,
        },
    )
    return inventory_id


def apply_manual_inventory_adjustment(
    conn,
    *,
    inventory_id: str,
    household_id: str,
    old_article_name: str,
    new_article_name: str,
    old_quantity: int,
    new_quantity: int,
    resolved_location: dict,
):
    safe_location = require_resolved_location(resolved_location)
    space_id = safe_location["space_id"]
    sublocation_id = safe_location["sublocation_id"]

    old_total = get_article_total_quantity(conn, household_id, old_article_name)

    conn.execute(
        text(
            """
            UPDATE inventory
            SET naam = :naam,
                aantal = :aantal,
                space_id = :space_id,
                sublocation_id = :sublocation_id,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
            """
        ),
        {
            "id": inventory_id,
            "naam": new_article_name,
            "aantal": int(new_quantity),
            "space_id": space_id,
            "sublocation_id": sublocation_id,
        },
    )

    new_total = get_article_total_quantity(conn, household_id, new_article_name)
    delta = int(new_quantity) - int(old_quantity)
    article_id = build_live_article_option_id(new_article_name)

    if delta > 0:
        mutation_label = 'handmatige ophoging'
    elif delta < 0:
        mutation_label = 'handmatige verlaging'
    else:
        mutation_label = 'handmatige correctie'

    note = f"{mutation_label.title()} via Voorraad: {old_total} → {new_total} (regel {old_quantity} → {new_quantity})"
    event_id = create_inventory_event(
        conn,
        household_id=household_id,
        article_id=article_id,
        article_name=new_article_name,
        resolved_location=safe_location,
        event_type='manual_adjustment',
        quantity=delta,
        old_quantity=old_total,
        new_quantity=new_total,
        source='manual_inventory',
        note=note,
    )

    updated = conn.execute(
        text(
            """
            SELECT
              i.id,
              i.naam AS artikel,
              i.aantal AS aantal,
              i.space_id AS space_id,
              i.sublocation_id AS sublocation_id,
              ha.id AS household_article_id,
              COALESCE(ha.custom_name, i.naam, '') AS household_article_name,
              COALESCE(gp.name, ha.naam, i.naam, '') AS product_name,
              COALESCE(s.naam, '') AS locatie,
              COALESCE(sl.naam, '') AS sublocatie,
              COALESCE(i.status, 'active') AS status
            FROM inventory i
            LEFT JOIN spaces s ON s.id = i.space_id
            LEFT JOIN sublocations sl ON sl.id = i.sublocation_id
            LEFT JOIN household_articles ha ON ha.household_id = i.household_id AND lower(trim(ha.naam)) = lower(trim(i.naam))
            LEFT JOIN global_products gp ON gp.id = ha.global_product_id
            WHERE i.id = :id
            """
        ),
        {"id": inventory_id},
    ).mappings().first()

    logger.info(
        'manual_inventory_update inventory_id=%s household_id=%s article_name=%s old_total=%s new_total=%s old_row_quantity=%s new_row_quantity=%s space_id=%s sublocation_id=%s history_event_created=%s',
        inventory_id,
        household_id,
        new_article_name,
        old_total,
        new_total,
        old_quantity,
        new_quantity,
        space_id,
        sublocation_id,
        event_id,
    )

    return dict(updated) if updated else {"id": inventory_id, "artikel": new_article_name, "aantal": new_quantity}, event_id


def create_inventory_purchase_event(conn, household_id: str, article_id: str, article_name: str, quantity: float, resolved_location: dict, note: str, *, supplier_name: str | None = None, price: float | None = None, currency: str | None = None, purchase_date: str | None = None, article_number: str | None = None, barcode: str | None = None):
    old_total = get_article_total_quantity(conn, household_id, article_name)
    projected_new_total = old_total + int(quantity)
    return create_inventory_event(
        conn,
        household_id=household_id,
        article_id=article_id,
        article_name=article_name,
        resolved_location=resolved_location,
        event_type='purchase',
        quantity=quantity,
        old_quantity=old_total,
        new_quantity=projected_new_total,
        source='store_import',
        note=note,
        purchase_date=purchase_date,
        supplier_name=supplier_name,
        article_number=article_number,
        price=price,
        currency=currency,
        barcode=barcode,
    )


def apply_inventory_consumption(
    conn,
    household_id: str,
    article_name: str,
    quantity: float,
    resolved_location: dict,
    *,
    mode: str = ARTICLE_AUTO_CONSUME_PURCHASED_QUANTITY,
    protected_quantity_on_purchase_row: int = 0,
    protected_purchase_inventory_id: str | None = None,
):
    safe_location = require_resolved_location(resolved_location)
    space_id = safe_location["space_id"]
    sublocation_id = safe_location["sublocation_id"]
    quantity_int = int(quantity)
    if quantity_int <= 0:
        return {"applied_quantity": 0, "affected_inventory_ids": []}

    normalized_mode = normalize_household_auto_consume_mode(mode)
    protected_quantity_int = max(0, int(protected_quantity_on_purchase_row or 0))

    if normalized_mode == ARTICLE_AUTO_CONSUME_ALL_EXISTING:
        rows = conn.execute(
            text(
                """
                SELECT id, aantal,
                       CASE
                         WHEN :protected_purchase_inventory_id IS NOT NULL
                          AND id = :protected_purchase_inventory_id
                         THEN 1 ELSE 0
                       END AS is_purchase_row
                FROM inventory
                WHERE household_id = :household_id
                  AND lower(trim(naam)) = lower(trim(:naam))
                ORDER BY is_purchase_row ASC, aantal ASC, id ASC
                """
            ),
            {
                "household_id": household_id,
                "naam": article_name,
                "space_id": space_id,
                "sublocation_id": sublocation_id,
                "protected_purchase_inventory_id": str(protected_purchase_inventory_id) if protected_purchase_inventory_id else None,
            },
        ).mappings().all()

        remaining_to_consume = quantity_int
        affected_ids = []

        for row in rows:
            if remaining_to_consume <= 0:
                break
            current_quantity = int(row["aantal"] or 0)
            if current_quantity <= 0:
                continue
            is_purchase_row = bool(row["is_purchase_row"])
            protected_for_row = protected_quantity_int if is_purchase_row else 0
            available_to_consume = max(0, current_quantity - protected_for_row)
            if available_to_consume <= 0:
                continue
            consume_here = min(available_to_consume, remaining_to_consume)
            new_row_quantity = current_quantity - consume_here
            if new_row_quantity > 0:
                conn.execute(
                    text(
                        """
                        UPDATE inventory
                        SET aantal = :aantal, updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                        """
                    ),
                    {"aantal": new_row_quantity, "id": row["id"]},
                )
            else:
                conn.execute(text("DELETE FROM inventory WHERE id = :id"), {"id": row["id"]})
            remaining_to_consume -= consume_here
            affected_ids.append(row["id"])

        return {
            "applied_quantity": quantity_int - remaining_to_consume,
            "affected_inventory_ids": affected_ids,
        }

    existing = conn.execute(
        text(
            """
            SELECT id, aantal
            FROM inventory
            WHERE household_id = :household_id
              AND naam = :naam
              AND COALESCE(space_id, '') = COALESCE(:space_id, '')
              AND COALESCE(sublocation_id, '') = COALESCE(:sublocation_id, '')
            """
        ),
        {
            "household_id": household_id,
            "naam": article_name,
            "space_id": space_id,
            "sublocation_id": sublocation_id,
        },
    ).mappings().first()

    if not existing:
        return {"applied_quantity": 0, "affected_inventory_ids": []}

    new_row_quantity = max(0, int(existing["aantal"] or 0) - quantity_int)
    if new_row_quantity > 0:
        conn.execute(
            text(
                """
                UPDATE inventory
                SET aantal = :aantal, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {"aantal": new_row_quantity, "id": existing["id"]},
        )
    else:
        conn.execute(text("DELETE FROM inventory WHERE id = :id"), {"id": existing["id"]})
    return {"applied_quantity": quantity_int, "affected_inventory_ids": [existing["id"]]}


def create_auto_repurchase_event(conn, household_id: str, article_id: str, article_name: str, resolved_location: dict, quantity: float = 1):
    quantity_int = int(quantity)
    if quantity_int <= 0:
        return None
    old_total = get_article_total_quantity(conn, household_id, article_name)
    if old_total <= 0:
        return None
    applied_quantity = min(old_total, quantity_int)
    if applied_quantity <= 0:
        return None
    new_total = max(0, old_total - applied_quantity)
    quantity_label = '1 eenheid' if applied_quantity == 1 else f'{applied_quantity} eenheden'
    return create_inventory_event(
        conn,
        household_id=household_id,
        article_id=article_id,
        article_name=article_name,
        resolved_location=resolved_location,
        event_type='auto_repurchase',
        quantity=-applied_quantity,
        old_quantity=old_total,
        new_quantity=new_total,
        source='auto_repurchase',
        note=f'Automatisch {quantity_label} afgeboekt bij herhaalaankoop.',
    )


def resolve_auto_consume_effective_mode(household_mode: str, article_override: str, consumable: bool) -> str:
    effective_mode = household_mode
    if article_override == ARTICLE_AUTO_CONSUME_PURCHASED_QUANTITY:
        effective_mode = ARTICLE_AUTO_CONSUME_PURCHASED_QUANTITY
    elif article_override == ARTICLE_AUTO_CONSUME_ALL_EXISTING:
        effective_mode = ARTICLE_AUTO_CONSUME_ALL_EXISTING
    elif article_override == ARTICLE_AUTO_CONSUME_NONE:
        effective_mode = ARTICLE_AUTO_CONSUME_NONE
    if not consumable:
        return ARTICLE_AUTO_CONSUME_NONE
    return effective_mode if effective_mode in HOUSEHOLD_AUTO_CONSUME_ALLOWED else ARTICLE_AUTO_CONSUME_NONE


def compute_auto_deduction_quantity(mode: str, pre_purchase_total: float, purchased_quantity: float) -> int:
    normalized_mode = normalize_household_auto_consume_mode(mode)
    pre_purchase_total_int = max(0, int(pre_purchase_total or 0))
    purchased_quantity_int = max(0, int(purchased_quantity or 0))
    if pre_purchase_total_int <= 0:
        return 0
    if normalized_mode == ARTICLE_AUTO_CONSUME_NONE:
        return 0
    if normalized_mode == ARTICLE_AUTO_CONSUME_PURCHASED_QUANTITY:
        return purchased_quantity_int
    if normalized_mode == ARTICLE_AUTO_CONSUME_ALL_EXISTING:
        return pre_purchase_total_int
    return 0


def determine_auto_consume_decision(conn, household_id: str, article_id: str, article_name: str, pre_purchase_total: float, purchased_quantity: float):
    consumable = get_article_consumable_state(conn, household_id, article_id, article_name)
    household_mode = get_household_auto_consume_mode(conn, household_id)
    article_override = get_household_article_auto_consume_override(conn, household_id, article_id)
    effective_mode = resolve_auto_consume_effective_mode(household_mode, article_override, consumable)
    requested_deduction_quantity = compute_auto_deduction_quantity(effective_mode, pre_purchase_total, purchased_quantity)
    should_auto_consume = requested_deduction_quantity > 0
    if not consumable:
        decision_reason = 'article not consumable'
    elif pre_purchase_total <= 0:
        decision_reason = 'existing stock missing'
    elif article_override == ARTICLE_AUTO_CONSUME_NONE:
        decision_reason = 'article override none'
    elif article_override == ARTICLE_AUTO_CONSUME_PURCHASED_QUANTITY:
        decision_reason = 'article override consume_purchased_quantity'
    elif article_override == ARTICLE_AUTO_CONSUME_ALL_EXISTING:
        decision_reason = 'article override consume_all_existing_before_purchase'
    elif household_mode == ARTICLE_AUTO_CONSUME_NONE:
        decision_reason = 'household mode none'
    else:
        decision_reason = f'effective mode {effective_mode}'
    return {
        'consumable': consumable,
        'household_mode': household_mode,
        'article_override': article_override,
        'effective_mode': effective_mode,
        'requested_deduction_quantity': requested_deduction_quantity,
        'should_auto_consume': should_auto_consume,
        'decision_reason': decision_reason,
    }


def ensure_store_provider(provider_code: str):
    with engine.begin() as conn:
        provider = conn.execute(
            text(
                """
                SELECT id, code, name, status, import_mode
                FROM store_providers
                WHERE code = :code AND status = 'active'
                """
            ),
            {"code": provider_code},
        ).mappings().first()
    if not provider:
        raise HTTPException(status_code=404, detail="Onbekende of inactieve store provider")
    return dict(provider)


def unpack_receipt_amounts_match(receipt):
    try:
        total_amount = float(receipt.get('total_amount'))
        line_total_sum = receipt.get('line_total_sum')
        discount_total = receipt.get('discount_total_effective', receipt.get('discount_total'))
        net_line_total_sum = receipt.get('net_line_total_sum')
        if net_line_total_sum is None:
            net_line_total_sum = (float(line_total_sum or 0) + float(discount_total or 0))
        else:
            net_line_total_sum = float(net_line_total_sum)
        line_count = int(receipt.get('line_count') or 0)
    except Exception:
        return False
    if line_count <= 0:
        return False
    return abs(total_amount - net_line_total_sum) < 0.01


def is_receipt_store_name_correct(store_name: Any) -> bool:
    normalized = str(store_name or '').strip()
    if not normalized:
        return False
    lowered = normalized.lower()
    if lowered in {'onbekend', 'unknown', 'n.v.t.', 'nvt', 'onbekende winkel'}:
        return False
    return True


def evaluate_receipt_unpack_criteria(receipt) -> dict[str, Any]:
    try:
        line_count = int(receipt.get('line_count') or 0)
    except Exception:
        line_count = 0
    store_name_correct = is_receipt_store_name_correct(receipt.get('store_name'))
    article_count_correct = line_count >= 1
    total_price_correct = receipt.get('total_amount') is not None
    line_sum_matches_total = unpack_receipt_amounts_match(receipt)
    if store_name_correct and article_count_correct and total_price_correct and line_sum_matches_total:
        inbox_status = 'Gecontroleerd'
        parse_status = 'approved'
    elif store_name_correct and article_count_correct and total_price_correct:
        inbox_status = 'Controle nodig'
        parse_status = 'review_needed'
    else:
        inbox_status = 'Handmatig'
        parse_status = 'manual'
    return {
        'store_name_correct': store_name_correct,
        'article_count_correct': article_count_correct,
        'total_price_correct': total_price_correct,
        'line_sum_matches_total': line_sum_matches_total,
        'inbox_status': inbox_status,
        'parse_status': parse_status,
        'line_count': line_count,
    }


def recompute_receipt_review_state(conn, receipt_table_id: str):
    receipt = conn.execute(
        text(
            """
        SELECT id, store_name, purchase_at, total_amount, parse_status,
               COALESCE(discount_total, 0) AS discount_total,
               COALESCE(totals_overridden, 0) AS totals_overridden
        FROM receipt_tables
        WHERE id = :id
        LIMIT 1
        """
        ),
        {'id': receipt_table_id},
    ).mappings().first()
    if not receipt:
        return
    current_status = str(receipt.get('parse_status') or '').strip().lower()
    valid_line_count = conn.execute(
        text(
            """
        SELECT COUNT(*)
        FROM receipt_table_lines
        WHERE receipt_table_id = :receipt_table_id
          AND COALESCE(is_deleted, 0) = 0
          AND TRIM(COALESCE(corrected_raw_label, raw_label, '')) <> ''
        """
        ),
        {'receipt_table_id': receipt_table_id},
    ).scalar()
    try:
        valid_line_count = int(valid_line_count or 0)
    except Exception:
        valid_line_count = 0
    line_total_sum = conn.execute(
        text(
            """
        SELECT COALESCE(SUM(COALESCE(corrected_line_total, line_total, 0)), 0)
        FROM receipt_table_lines
        WHERE receipt_table_id = :receipt_table_id
          AND COALESCE(is_deleted, 0) = 0
        """
        ),
        {'receipt_table_id': receipt_table_id},
    ).scalar()
    criteria = evaluate_receipt_unpack_criteria({
        **dict(receipt),
        'line_count': valid_line_count,
        'line_total_sum': line_total_sum,
        'discount_total_effective': receipt.get('discount_total'),
    })
    next_status = str(criteria.get('parse_status') or current_status or 'manual').strip().lower() or 'manual'
    conn.execute(
        text(
            """
        UPDATE receipt_tables
        SET parse_status = :parse_status,
            line_count = :line_count,
            totals_overridden = 0,
            totals_override_by_user_email = NULL,
            totals_override_at = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :id
        """
        ),
        {'id': receipt_table_id, 'parse_status': next_status, 'line_count': valid_line_count},
    )

def derive_unpack_receipt_status(receipt):
    criteria = evaluate_receipt_unpack_criteria(receipt)
    return str(criteria.get('inbox_status') or 'Handmatig')


def ensure_receipt_unpack_provider(conn):
    provider = conn.execute(
        text("SELECT id, code, name FROM store_providers WHERE code = 'receipt' LIMIT 1")
    ).mappings().first()
    if provider:
        return dict(provider)
    provider_id = str(uuid.uuid4())
    conn.execute(
        text("""
        INSERT INTO store_providers (id, code, name, status, import_mode)
        VALUES (:id, 'receipt', 'Kassabon', 'active', 'receipt')
        """),
        {'id': provider_id},
    )
    return {'id': provider_id, 'code': 'receipt', 'name': 'Kassabon'}


def ensure_receipt_unpack_connection(conn, household_id: str, provider_id: str):
    connection = conn.execute(
        text("""
        SELECT id
        FROM household_store_connections
        WHERE household_id = :household_id AND store_provider_id = :provider_id
        ORDER BY linked_at DESC, id DESC
        LIMIT 1
        """),
        {'household_id': household_id, 'provider_id': provider_id},
    ).mappings().first()
    if connection:
        return str(connection['id'])
    connection_id = str(uuid.uuid4())
    conn.execute(
        text("""
        INSERT INTO household_store_connections (
            id, household_id, store_provider_id, connection_status, linked_at
        ) VALUES (
            :id, :household_id, :provider_id, 'active', CURRENT_TIMESTAMP
        )
        """),
        {'id': connection_id, 'household_id': household_id, 'provider_id': provider_id},
    )
    return connection_id


def _receipt_purchase_date_label(receipt):
    value = receipt.get('purchase_at') or receipt.get('created_at') or ''
    value = str(value)
    if len(value) >= 10:
        return value[:10]
    return value or 'Onbekend'


def sync_unpack_batch_lines_for_receipt(conn, batch_id: str, receipt, *, refresh_prefill: bool = True) -> int:
    receipt_table_id = str((receipt or {}).get('receipt_table_id') or (receipt or {}).get('id') or '').strip()
    if not batch_id or not receipt_table_id:
        return 0

    existing_refs = {
        str(row[0] or '').strip()
        for row in conn.execute(
            text("SELECT external_line_ref FROM purchase_import_lines WHERE batch_id = :batch_id"),
            {'batch_id': batch_id},
        ).fetchall()
        if str(row[0] or '').strip()
    }

    line_rows = conn.execute(
        text("""
        SELECT id, line_index,
               COALESCE(corrected_raw_label, raw_label) AS raw_label,
               COALESCE(corrected_quantity, quantity) AS quantity,
               COALESCE(corrected_unit, unit) AS unit,
               COALESCE(corrected_line_total, line_total) AS line_total,
               barcode
        FROM receipt_table_lines
        WHERE receipt_table_id = :receipt_table_id
          AND COALESCE(is_deleted, 0) = 0
        ORDER BY line_index ASC, id ASC
        """),
        {'receipt_table_id': receipt_table_id},
    ).mappings().all()

    inserted = 0
    household_id = str((receipt or {}).get('household_id') or '').strip()
    for offset, line in enumerate(line_rows, start=1):
        raw_label = str(line.get('raw_label') or '').strip()
        if not raw_label:
            continue
        external_line_ref = f"receipt-line:{line.get('id') or offset}"
        try:
            quantity_value = float(line.get('quantity')) if line.get('quantity') is not None else 1.0
        except Exception:
            quantity_value = 1.0
        try:
            line_price_value = float(line.get('line_total')) if line.get('line_total') is not None else None
        except Exception:
            line_price_value = None

        resolved_links = resolve_receipt_line_product_links(
            conn,
            household_id,
            raw_label,
            barcode=line.get('barcode'),
            brand=(receipt or {}).get('store_name'),
            create_global_product=True,
            create_household_article=bool(household_id),
            external_article_code=line.get('barcode'),
        )
        matched_global_product_id = str((resolved_links or {}).get('matched_global_product_id') or '').strip() or None
        matched_household_article_id = str((resolved_links or {}).get('matched_household_article_id') or '').strip() or None

        if external_line_ref in existing_refs:
            conn.execute(
                text("""
                UPDATE purchase_import_lines
                SET external_article_code = :external_article_code,
                    article_name_raw = :article_name_raw,
                    brand_raw = :brand_raw,
                    quantity_raw = :quantity_raw,
                    unit_raw = :unit_raw,
                    line_price_raw = :line_price_raw,
                    currency_code = :currency_code,
                    matched_global_product_id = :matched_global_product_id,
                    matched_household_article_id = CASE
                        WHEN COALESCE(article_override_mode, 'auto') = 'auto' THEN :matched_household_article_id
                        ELSE matched_household_article_id
                    END,
                    suggested_household_article_id = CASE
                        WHEN COALESCE(article_override_mode, 'auto') = 'auto' THEN COALESCE(:matched_household_article_id, suggested_household_article_id)
                        ELSE suggested_household_article_id
                    END,
                    match_status = CASE
                        WHEN COALESCE(article_override_mode, 'auto') = 'auto' AND :matched_household_article_id IS NOT NULL THEN 'matched'
                        WHEN COALESCE(article_override_mode, 'auto') = 'auto' THEN 'unmatched'
                        ELSE match_status
                    END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE batch_id = :batch_id AND external_line_ref = :external_line_ref
                """),
                {
                    'batch_id': batch_id,
                    'external_line_ref': external_line_ref,
                    'external_article_code': line.get('barcode'),
                    'article_name_raw': raw_label,
                    'brand_raw': (receipt or {}).get('store_name') or '',
                    'quantity_raw': quantity_value,
                    'unit_raw': line.get('unit') or '',
                    'line_price_raw': line_price_value,
                    'currency_code': (receipt or {}).get('currency') or 'EUR',
                    'matched_global_product_id': matched_global_product_id,
                    'matched_household_article_id': matched_household_article_id,
                },
            )
            conn.execute(
                text("""
                UPDATE receipt_table_lines
                SET matched_global_product_id = :matched_global_product_id,
                    article_match_status = CASE WHEN :matched_global_product_id IS NOT NULL THEN 'product_matched' ELSE 'unmatched' END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :line_id
                """),
                {'line_id': line.get('id'), 'matched_global_product_id': matched_global_product_id},
            )
            continue

        conn.execute(
            text("""
            INSERT INTO purchase_import_lines (
                id, batch_id, external_line_ref, external_article_code, article_name_raw,
                brand_raw, quantity_raw, unit_raw, line_price_raw, currency_code,
                match_status, review_decision, ui_sort_order, matched_global_product_id,
                matched_household_article_id, suggested_household_article_id, created_at
            ) VALUES (
                :id, :batch_id, :external_line_ref, :external_article_code, :article_name_raw,
                :brand_raw, :quantity_raw, :unit_raw, :line_price_raw, :currency_code,
                :match_status, 'selected', :ui_sort_order, :matched_global_product_id,
                :matched_household_article_id, :suggested_household_article_id, CURRENT_TIMESTAMP
            )
            """),
            {
                'id': str(uuid.uuid4()),
                'batch_id': batch_id,
                'external_line_ref': external_line_ref,
                'external_article_code': line.get('barcode'),
                'article_name_raw': raw_label,
                'brand_raw': (receipt or {}).get('store_name') or '',
                'quantity_raw': quantity_value,
                'unit_raw': line.get('unit') or '',
                'line_price_raw': line_price_value,
                'currency_code': (receipt or {}).get('currency') or 'EUR',
                'ui_sort_order': int(line.get('line_index') or offset),
                'match_status': 'matched' if matched_household_article_id else 'unmatched',
                'matched_global_product_id': matched_global_product_id,
                'matched_household_article_id': matched_household_article_id,
                'suggested_household_article_id': matched_household_article_id,
            },
        )
        conn.execute(
            text("""
            UPDATE receipt_table_lines
            SET matched_global_product_id = :matched_global_product_id,
                article_match_status = CASE WHEN :matched_global_product_id IS NOT NULL THEN 'product_matched' ELSE 'unmatched' END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :line_id
            """),
            {'line_id': line.get('id'), 'matched_global_product_id': matched_global_product_id},
        )
        existing_refs.add(external_line_ref)
        inserted += 1

    if inserted and refresh_prefill:
        household_id = str((receipt or {}).get('household_id') or '').strip()
        if household_id:
            apply_prefill_to_batch(conn, batch_id, household_id, 'receipt')
    update_batch_status(conn, batch_id)
    return inserted


def ensure_unpack_batch_for_receipt(conn, receipt):
    receipt_table_id = str(receipt.get('receipt_table_id') or receipt.get('id') or '').strip()
    household_id = str(receipt.get('household_id') or '').strip()
    if not receipt_table_id or not household_id:
        raise HTTPException(status_code=400, detail='Bon-id of huishouden ontbreekt voor Uitpakken')

    existing = conn.execute(
        text("""
        SELECT id AS batch_id
        FROM purchase_import_batches
        WHERE household_id = :household_id
          AND source_type = 'receipt'
          AND source_reference = :source_reference
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """),
        {'household_id': household_id, 'source_reference': f'receipt:{receipt_table_id}'},
    ).mappings().first()
    if existing:
        existing_batch_id = str(existing['batch_id'])
        sync_unpack_batch_lines_for_receipt(conn, existing_batch_id, receipt)
        return existing_batch_id

    provider = ensure_receipt_unpack_provider(conn)
    connection_id = ensure_receipt_unpack_connection(conn, household_id, str(provider['id']))

    batch_id = str(uuid.uuid4())
    raw_payload = json.dumps({
        'provider_code': 'receipt',
        'receipt_table_id': receipt_table_id,
        'batch_metadata': {
            'purchase_date': _receipt_purchase_date_label(receipt),
            'store_name': receipt.get('store_name') or receipt.get('store_branch') or 'Kassabon',
            'store_label': receipt.get('store_name') or receipt.get('store_branch') or 'Kassabon',
        },
    })
    conn.execute(
        text("""
        INSERT INTO purchase_import_batches (
            id, household_id, store_provider_id, connection_id, source_type,
            source_reference, import_status, raw_payload, created_at
        ) VALUES (
            :id, :household_id, :store_provider_id, :connection_id, 'receipt',
            :source_reference, 'new', :raw_payload, CURRENT_TIMESTAMP
        )
        """),
        {
            'id': batch_id,
            'household_id': household_id,
            'store_provider_id': str(provider['id']),
            'connection_id': connection_id,
            'source_reference': f'receipt:{receipt_table_id}',
            'raw_payload': raw_payload,
        },
    )

    sync_unpack_batch_lines_for_receipt(conn, batch_id, receipt, refresh_prefill=False)
    apply_prefill_to_batch(conn, batch_id, household_id, 'receipt')
    update_batch_status(conn, batch_id)
    return batch_id


def normalize_datetime(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def sanitize_source_slug(value: str) -> str:
    candidate = re.sub(r'[^A-Za-z0-9._-]+', '-', (value or '').strip().lower())
    candidate = candidate.strip('-._') or 'source'
    return candidate[:80]


def build_receipt_source_response(row):
    item = serialize_receipt_row(dict(row))
    source_type = str(item.get('type') or '')
    supports_scan = source_type in {'local_folder', 'scan_folder', 'watched_folder'}
    status_label = 'Actief' if item.get('is_active') else 'Inactief'
    if source_type == 'email':
        status_label = 'E-mailroute'
    elif source_type == 'gmail_label':
        status_label = 'Gmail-label'
    elif source_type == 'customer_card':
        status_label = 'Voorbereidende koppeling'
    if source_type == 'barcode_fallback':
        status_label = 'Vangnetroute'
    if source_type == 'manual_upload':
        status_label = 'Handmatig'
    item['supports_scan'] = supports_scan
    item['status_label'] = status_label
    return item


def ensure_receipt_source_path(household_id: str, source_type: str, label: str, requested_path: Optional[str] = None) -> Optional[str]:
    if source_type not in {'local_folder', 'scan_folder', 'watched_folder'}:
        return (requested_path or '').strip() or None
    sources_root = RECEIPT_STORAGE_ROOT.parent / 'sources' / str(household_id)
    sources_root.mkdir(parents=True, exist_ok=True)
    if requested_path and str(requested_path).strip():
        candidate = Path(str(requested_path).strip())
        if not candidate.is_absolute():
            candidate = (sources_root / candidate).resolve()
        else:
            candidate = candidate.resolve()
    elif source_type == 'local_folder':
        candidate = (sources_root / 'local-folder').resolve()
    elif source_type == 'scan_folder':
        candidate = (sources_root / 'scan-folder').resolve()
    else:
        candidate = (sources_root / sanitize_source_slug(label)).resolve()
    candidate.mkdir(parents=True, exist_ok=True)
    return str(candidate)


def list_receipt_sources_for_household(household_id: str):
    ensure_default_receipt_sources(engine, RECEIPT_STORAGE_ROOT, household_id)
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, household_id, type, label, source_path, is_active, last_scan_at, created_at, updated_at
                FROM receipt_sources
                WHERE household_id = :household_id
                ORDER BY
                    CASE type
                        WHEN 'local_folder' THEN 1
                        WHEN 'scan_folder' THEN 2
                        WHEN 'watched_folder' THEN 3
                        WHEN 'email' THEN 4
                        WHEN 'gmail_label' THEN 5
                        WHEN 'customer_card' THEN 6
                        WHEN 'barcode_fallback' THEN 7
                        ELSE 9
                    END,
                    label COLLATE NOCASE ASC
                """
            ),
            {'household_id': household_id},
        ).mappings().all()
    return [build_receipt_source_response(row) for row in rows]


def create_receipt_source(payload: ReceiptSourceCreateRequest):
    household_id = str(payload.household_id or '').strip() or '1'
    source_type = str(payload.type or '').strip()
    allowed_types = {'watched_folder', 'email', 'customer_card', 'barcode_fallback'}
    if source_type not in allowed_types:
        raise HTTPException(status_code=400, detail='Onbekend of niet-toegestaan bron type')

    base_label = (payload.label or '').strip()
    source_path = (payload.source_path or '').strip() or None
    if source_type == 'watched_folder':
        label = base_label or 'Bewaakte map'
        source_path = ensure_receipt_source_path(household_id, source_type, label, source_path)
    elif source_type == 'email':
        email_value = (payload.external_reference or payload.source_path or '').strip()
        label = base_label or ('E-mailbon' if not email_value else f'E-mailbon — {email_value}')
        source_path = email_value or None
    elif source_type == 'customer_card':
        store_name = (payload.store_name or '').strip()
        account_label = (payload.account_label or '').strip()
        external_reference = (payload.external_reference or '').strip()
        parts = [part for part in [store_name, account_label or external_reference] if part]
        label = base_label or ('Klantenkaart' if not parts else ' — '.join(parts))
        source_path = external_reference or account_label or None
    else:
        label = base_label or 'Barcode / handmatig'
        source_path = None

    source_id = uuid.uuid4().hex
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO receipt_sources (id, household_id, type, label, source_path, is_active)
                VALUES (:id, :household_id, :type, :label, :source_path, :is_active)
                """
            ),
            {
                'id': source_id,
                'household_id': household_id,
                'type': source_type,
                'label': label,
                'source_path': source_path,
                'is_active': 1 if payload.is_active else 0,
            },
        )
        row = conn.execute(
            text(
                """
                SELECT id, household_id, type, label, source_path, is_active, last_scan_at, created_at, updated_at
                FROM receipt_sources
                WHERE id = :id
                LIMIT 1
                """
            ),
            {'id': source_id},
        ).mappings().first()
    return build_receipt_source_response(row)


def is_public_receipt_email_domain(domain: str) -> bool:
    domain_value = str(domain or '').strip().lower()
    if not domain_value:
        return False
    if domain_value in {'localhost', 'rezzerv.local'}:
        return False
    if domain_value.endswith('.local') or domain_value.endswith('.localhost') or domain_value.endswith('.invalid'):
        return False
    return '.' in domain_value


def build_household_email_address(household_id: str) -> str:
    normalized_household_id = sanitize_source_slug(str(household_id or '1'))
    return f"bon+{normalized_household_id}@{RECEIPT_EMAIL_DOMAIN}"


def ensure_household_email_source(household_id: str):
    effective_household_id = str(household_id or '1').strip() or '1'
    ensure_default_receipt_sources(engine, RECEIPT_STORAGE_ROOT, effective_household_id)
    route_address = build_household_email_address(effective_household_id)
    source_id = f'{effective_household_id}-email-route'
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, household_id, type, label, source_path, is_active, last_scan_at, created_at, updated_at
                FROM receipt_sources
                WHERE household_id = :household_id AND type = 'email'
                ORDER BY CASE WHEN id = :preferred_id THEN 0 ELSE 1 END, created_at ASC
                LIMIT 1
                """
            ),
            {'household_id': effective_household_id, 'preferred_id': source_id},
        ).mappings().first()
        if row:
            source_id = row['id']
            conn.execute(
                text(
                    """
                    UPDATE receipt_sources
                    SET label = :label, source_path = :source_path, is_active = 1, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    """
                ),
                {'id': source_id, 'label': 'E-mail', 'source_path': route_address},
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO receipt_sources (id, household_id, type, label, source_path, is_active)
                    VALUES (:id, :household_id, 'email', :label, :source_path, 1)
                    """
                ),
                {'id': source_id, 'household_id': effective_household_id, 'label': 'E-mail', 'source_path': route_address},
            )
        refreshed = conn.execute(
            text(
                """
                SELECT id, household_id, type, label, source_path, is_active, last_scan_at, created_at, updated_at
                FROM receipt_sources
                WHERE id = :id
                LIMIT 1
                """
            ),
            {'id': source_id},
        ).mappings().first()
    item = build_receipt_source_response(refreshed)
    item['route_address'] = route_address
    item['route_domain'] = RECEIPT_EMAIL_DOMAIN
    item['route_is_public'] = is_public_receipt_email_domain(RECEIPT_EMAIL_DOMAIN)
    item['delivery_mode'] = 'forwarding_ready' if item['route_is_public'] else 'local_demo'
    item.update(build_receipt_inbound_status(effective_household_id))
    return item


def ensure_household_gmail_source(household_id: str):
    effective_household_id = str(household_id or '1').strip() or '1'
    ensure_default_receipt_sources(engine, RECEIPT_STORAGE_ROOT, effective_household_id)
    label_name = GMAIL_DEFAULT_LABEL_NAME
    source_id = f'{effective_household_id}-gmail-label'
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, household_id, type, label, source_path, is_active, last_scan_at, created_at, updated_at
                FROM receipt_sources
                WHERE household_id = :household_id AND type = 'gmail_label'
                ORDER BY CASE WHEN id = :preferred_id THEN 0 ELSE 1 END, created_at ASC
                LIMIT 1
                """
            ),
            {'household_id': effective_household_id, 'preferred_id': source_id},
        ).mappings().first()
        if row:
            source_id = row['id']
            conn.execute(
                text(
                    """
                    UPDATE receipt_sources
                    SET label = :label, source_path = :source_path, is_active = 1, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    """
                ),
                {'id': source_id, 'label': 'E-mail', 'source_path': label_name},
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO receipt_sources (id, household_id, type, label, source_path, is_active)
                    VALUES (:id, :household_id, 'gmail_label', :label, :source_path, 1)
                    """
                ),
                {'id': source_id, 'household_id': effective_household_id, 'label': 'E-mail', 'source_path': label_name},
            )
        refreshed = conn.execute(
            text(
                """
                SELECT id, household_id, type, label, source_path, is_active, last_scan_at, created_at, updated_at
                FROM receipt_sources
                WHERE id = :id
                LIMIT 1
                """
            ),
            {'id': source_id},
        ).mappings().first()
    item = build_receipt_source_response(refreshed)
    item['gmail_label_name'] = label_name
    return item


def gmail_is_configured() -> bool:
    return bool(GMAIL_OAUTH_CLIENT_ID and GMAIL_OAUTH_CLIENT_SECRET)


def resolve_gmail_redirect_uri(request: Request | None = None) -> str:
    if GMAIL_OAUTH_REDIRECT_URI:
        return GMAIL_OAUTH_REDIRECT_URI
    if request is None:
        raise HTTPException(status_code=503, detail='De Gmail redirect-URI is nog niet geconfigureerd.')
    return f"{str(request.base_url).rstrip('/')}/api/receipts/gmail/callback"


def sign_gmail_state(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')
    signature = hmac.new(GMAIL_STATE_SECRET, serialized, hashlib.sha256).hexdigest()
    encoded = base64.urlsafe_b64encode(serialized).decode('ascii').rstrip('=')
    return f'{encoded}.{signature}'


def verify_gmail_state(state_token: str) -> dict[str, Any]:
    if not state_token or '.' not in state_token:
        raise HTTPException(status_code=400, detail='Ongeldige Gmail-state ontvangen.')
    encoded, provided_signature = state_token.rsplit('.', 1)
    padding = '=' * (-len(encoded) % 4)
    try:
        serialized = base64.urlsafe_b64decode(f'{encoded}{padding}'.encode('ascii'))
    except Exception as exc:
        raise HTTPException(status_code=400, detail='Gmail-state kon niet worden gelezen.') from exc
    expected_signature = hmac.new(GMAIL_STATE_SECRET, serialized, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(provided_signature, expected_signature):
        raise HTTPException(status_code=400, detail='Gmail-state is ongeldig of verlopen.')
    try:
        payload = json.loads(serialized.decode('utf-8'))
    except Exception as exc:
        raise HTTPException(status_code=400, detail='Gmail-state bevat ongeldige gegevens.') from exc
    if str(payload.get('provider') or '') != 'gmail':
        raise HTTPException(status_code=400, detail='Onbekende OAuth-provider.')
    return payload


def gmail_datetime_from_timestamp(value: Any) -> str | None:
    try:
        if value is None or value == '':
            return None
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
        else:
            value_str = str(value).strip()
            if not value_str:
                return None
            if value_str.isdigit():
                dt = datetime.fromtimestamp(int(value_str) / 1000, tz=timezone.utc)
            else:
                dt = datetime.fromisoformat(value_str.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except Exception:
        return None


def parse_gmail_token_expiry(expires_in: Any) -> str | None:
    try:
        seconds = int(expires_in)
    except Exception:
        return None
    dt = datetime.now(timezone.utc) + timedelta(seconds=max(0, seconds - 60))
    return dt.replace(microsecond=0).isoformat()


def gmail_json_request(url: str, method: str = 'GET', *, headers: Optional[dict[str, str]] = None, data: Any = None, timeout: float = 30.0) -> dict[str, Any]:
    request_headers = {'Accept': 'application/json', **(headers or {})}
    payload = None
    if data is not None:
        if isinstance(data, (bytes, bytearray)):
            payload = bytes(data)
        else:
            payload = json.dumps(data).encode('utf-8')
            request_headers.setdefault('Content-Type', 'application/json')
    request_obj = urllib.request.Request(url, data=payload, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request_obj, timeout=timeout) as response:
            body = response.read()
            if not body:
                return {}
            return json.loads(body.decode('utf-8'))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='ignore')
        detail = None
        try:
            parsed = json.loads(body)
            detail = parsed.get('error_description') or (parsed.get('error') if isinstance(parsed.get('error'), str) else None)
            if isinstance(parsed.get('error'), dict):
                detail = parsed['error'].get('message') or detail
        except Exception:
            detail = body.strip() or exc.reason
        raise HTTPException(status_code=502, detail=f'Gmail-API fout: {detail or exc.reason}') from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=f'Gmail-API is niet bereikbaar: {exc.reason}') from exc


def gmail_form_request(url: str, data: dict[str, Any]) -> dict[str, Any]:
    encoded = urllib.parse.urlencode({key: value for key, value in data.items() if value is not None}).encode('utf-8')
    request_obj = urllib.request.Request(url, data=encoded, headers={'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(request_obj, timeout=30.0) as response:
            body = response.read()
            return json.loads(body.decode('utf-8')) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='ignore')
        detail = None
        try:
            parsed = json.loads(body)
            detail = parsed.get('error_description') or parsed.get('error')
        except Exception:
            detail = body.strip() or exc.reason
        raise HTTPException(status_code=502, detail=f'Google OAuth fout: {detail or exc.reason}') from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=f'Google OAuth is niet bereikbaar: {exc.reason}') from exc


def upsert_receipt_gmail_account(household_id: str, values: dict[str, Any]):
    effective_household_id = str(household_id or '1').strip() or '1'
    gmail_source = ensure_household_gmail_source(effective_household_id)
    current = get_receipt_gmail_account(effective_household_id, create_if_missing=False)
    merged = {
        'household_id': effective_household_id,
        'source_id': gmail_source['id'],
        'google_email': current.get('google_email'),
        'google_user_sub': current.get('google_user_sub'),
        'label_name': current.get('label_name') or GMAIL_DEFAULT_LABEL_NAME,
        'label_id': current.get('label_id'),
        'access_token': current.get('access_token'),
        'refresh_token': current.get('refresh_token'),
        'token_expires_at': current.get('token_expires_at'),
        'sync_status': current.get('sync_status') or 'not_connected',
        'last_synced_at': current.get('last_synced_at'),
        'last_error': current.get('last_error'),
    }
    merged.update({key: value for key, value in values.items() if key in merged})
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO receipt_gmail_accounts (
                    household_id, source_id, google_email, google_user_sub, label_name, label_id,
                    access_token, refresh_token, token_expires_at, sync_status, last_synced_at, last_error, updated_at
                ) VALUES (
                    :household_id, :source_id, :google_email, :google_user_sub, :label_name, :label_id,
                    :access_token, :refresh_token, :token_expires_at, :sync_status, :last_synced_at, :last_error, CURRENT_TIMESTAMP
                )
                ON CONFLICT(household_id) DO UPDATE SET
                    source_id = excluded.source_id,
                    google_email = excluded.google_email,
                    google_user_sub = excluded.google_user_sub,
                    label_name = excluded.label_name,
                    label_id = excluded.label_id,
                    access_token = excluded.access_token,
                    refresh_token = excluded.refresh_token,
                    token_expires_at = excluded.token_expires_at,
                    sync_status = excluded.sync_status,
                    last_synced_at = excluded.last_synced_at,
                    last_error = excluded.last_error,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            merged,
        )
    return get_receipt_gmail_account(effective_household_id, create_if_missing=True)


def build_receipt_gmail_account_response(row: dict[str, Any] | None, household_id: str) -> dict[str, Any]:
    gmail_source = ensure_household_gmail_source(household_id)
    item = serialize_receipt_row(dict(row or {}))
    item['household_id'] = str(household_id or '1')
    item['source_id'] = item.get('source_id') or gmail_source['id']
    item['label_name'] = item.get('label_name') or GMAIL_DEFAULT_LABEL_NAME
    item['configured'] = gmail_is_configured()
    item['connected'] = bool(item.get('refresh_token') or item.get('access_token'))
    item['source_label'] = gmail_source.get('label', 'E-mail')
    item['sync_status'] = item.get('sync_status') or ('ready' if item['connected'] else 'not_connected')
    return item


def get_receipt_gmail_account(household_id: str, create_if_missing: bool = True) -> dict[str, Any]:
    effective_household_id = str(household_id or '1').strip() or '1'
    if create_if_missing:
        ensure_household_gmail_source(effective_household_id)
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT household_id, source_id, google_email, google_user_sub, label_name, label_id,
                       access_token, refresh_token, token_expires_at, sync_status, last_synced_at, last_error,
                       created_at, updated_at
                FROM receipt_gmail_accounts
                WHERE household_id = :household_id
                LIMIT 1
                """
            ),
            {'household_id': effective_household_id},
        ).mappings().first()
    if not row and create_if_missing:
        row = upsert_receipt_gmail_account(effective_household_id, {'label_name': GMAIL_DEFAULT_LABEL_NAME, 'sync_status': 'not_connected'})
        return row
    return build_receipt_gmail_account_response(row, effective_household_id)


def build_gmail_connect_url(household_id: str, redirect_uri: str, frontend_origin: str | None = None) -> str:
    state_payload = {
        'provider': 'gmail',
        'household_id': str(household_id or '1'),
        'frontend_origin': (frontend_origin or '').strip() or None,
        'nonce': secrets.token_urlsafe(12),
    }
    query = {
        'client_id': GMAIL_OAUTH_CLIENT_ID,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': ' '.join(GMAIL_OAUTH_SCOPES),
        'access_type': 'offline',
        'prompt': 'consent',
        'include_granted_scopes': 'true',
        'state': sign_gmail_state(state_payload),
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(query)}"


def exchange_gmail_code_for_tokens(code: str, redirect_uri: str) -> dict[str, Any]:
    return gmail_form_request(
        'https://oauth2.googleapis.com/token',
        {
            'code': code,
            'client_id': GMAIL_OAUTH_CLIENT_ID,
            'client_secret': GMAIL_OAUTH_CLIENT_SECRET,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
        },
    )


def refresh_gmail_access_token(account: dict[str, Any]) -> dict[str, Any]:
    refresh_token = str(account.get('refresh_token') or '').strip()
    if not refresh_token:
        raise HTTPException(status_code=400, detail='Deze Gmail-koppeling heeft geen refresh-token. Koppel Gmail opnieuw.')
    tokens = gmail_form_request(
        'https://oauth2.googleapis.com/token',
        {
            'client_id': GMAIL_OAUTH_CLIENT_ID,
            'client_secret': GMAIL_OAUTH_CLIENT_SECRET,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token',
        },
    )
    return upsert_receipt_gmail_account(
        account['household_id'],
        {
            'access_token': tokens.get('access_token'),
            'refresh_token': tokens.get('refresh_token') or refresh_token,
            'token_expires_at': parse_gmail_token_expiry(tokens.get('expires_in')),
            'sync_status': 'connected',
            'last_error': None,
        },
    )


def get_valid_gmail_access_token(account: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    access_token = str(account.get('access_token') or '').strip()
    expires_at = gmail_datetime_from_timestamp(account.get('token_expires_at'))
    now_utc = datetime.now(timezone.utc)
    if access_token and expires_at:
        try:
            parsed = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if parsed > now_utc + timedelta(seconds=30):
                return access_token, account
        except Exception:
            pass
    refreshed = refresh_gmail_access_token(account)
    refreshed_token = str(refreshed.get('access_token') or '').strip()
    if not refreshed_token:
        raise HTTPException(status_code=400, detail='De Gmail access-token ontbreekt na verversen. Koppel Gmail opnieuw.')
    return refreshed_token, refreshed


def gmail_api_request(account: dict[str, Any], path: str, *, method: str = 'GET', params: Optional[dict[str, Any]] = None, data: Any = None, retry_on_unauthorized: bool = True) -> tuple[dict[str, Any], dict[str, Any]]:
    token, current_account = get_valid_gmail_access_token(account)
    url = f"https://gmail.googleapis.com/gmail/v1/{path.lstrip('/')}"
    if params:
        query = urllib.parse.urlencode({key: value for key, value in params.items() if value is not None and value != ''}, doseq=True)
        if query:
            url = f'{url}?{query}'
    try:
        response = gmail_json_request(url, method=method, headers={'Authorization': f'Bearer {token}'}, data=data)
        return response, current_account
    except HTTPException as exc:
        if retry_on_unauthorized and '401' in str(exc.detail):
            refreshed = refresh_gmail_access_token(current_account)
            return gmail_api_request(refreshed, path, method=method, params=params, data=data, retry_on_unauthorized=False)
        raise


def gmail_get_profile(account: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    return gmail_api_request(account, 'users/me/profile')


def ensure_gmail_label(account: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    label_name = str(account.get('label_name') or GMAIL_DEFAULT_LABEL_NAME).strip() or GMAIL_DEFAULT_LABEL_NAME
    labels_payload, current_account = gmail_api_request(account, 'users/me/labels')
    labels = labels_payload.get('labels') or []
    for label in labels:
        if str(label.get('name') or '').strip().lower() == label_name.lower():
            label_id = str(label.get('id') or '').strip()
            updated = upsert_receipt_gmail_account(current_account['household_id'], {'label_name': label_name, 'label_id': label_id, 'sync_status': 'connected', 'last_error': None})
            return label_id, updated
    created_label, updated_account = gmail_api_request(
        current_account,
        'users/me/labels',
        method='POST',
        data={
            'name': label_name,
            'messageListVisibility': 'show',
            'labelListVisibility': 'labelShow',
        },
    )
    label_id = str(created_label.get('id') or '').strip()
    updated = upsert_receipt_gmail_account(updated_account['household_id'], {'label_name': label_name, 'label_id': label_id, 'sync_status': 'connected', 'last_error': None})
    return label_id, updated


def has_processed_gmail_message(household_id: str, gmail_message_id: str) -> bool:
    with engine.begin() as conn:
        existing = conn.execute(
            text('SELECT id FROM receipt_gmail_imports WHERE household_id = :household_id AND gmail_message_id = :gmail_message_id LIMIT 1'),
            {'household_id': household_id, 'gmail_message_id': gmail_message_id},
        ).first()
    return bool(existing)


def store_gmail_import_result(household_id: str, gmail_message_id: str, values: dict[str, Any]):
    payload = {
        'id': values.get('id') or uuid.uuid4().hex,
        'household_id': household_id,
        'gmail_message_id': gmail_message_id,
        'gmail_thread_id': values.get('gmail_thread_id'),
        'gmail_history_id': values.get('gmail_history_id'),
        'gmail_internal_date': values.get('gmail_internal_date'),
        'raw_receipt_id': values.get('raw_receipt_id'),
        'receipt_table_id': values.get('receipt_table_id'),
        'import_status': values.get('import_status') or 'imported',
        'error_message': values.get('error_message'),
    }
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO receipt_gmail_imports (
                    id, household_id, gmail_message_id, gmail_thread_id, gmail_history_id, gmail_internal_date,
                    raw_receipt_id, receipt_table_id, import_status, error_message, updated_at
                ) VALUES (
                    :id, :household_id, :gmail_message_id, :gmail_thread_id, :gmail_history_id, :gmail_internal_date,
                    :raw_receipt_id, :receipt_table_id, :import_status, :error_message, CURRENT_TIMESTAMP
                )
                ON CONFLICT(household_id, gmail_message_id) DO UPDATE SET
                    gmail_thread_id = excluded.gmail_thread_id,
                    gmail_history_id = excluded.gmail_history_id,
                    gmail_internal_date = excluded.gmail_internal_date,
                    raw_receipt_id = excluded.raw_receipt_id,
                    receipt_table_id = excluded.receipt_table_id,
                    import_status = excluded.import_status,
                    error_message = excluded.error_message,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            payload,
        )


def decode_gmail_raw_message(raw_value: str) -> bytes:
    if not raw_value:
        raise ValueError('De Gmail-API gaf geen ruwe e-mailinhoud terug.')
    padding = '=' * (-len(raw_value) % 4)
    try:
        return base64.urlsafe_b64decode(f'{raw_value}{padding}'.encode('ascii'))
    except Exception as exc:
        raise ValueError('De Gmail-API gaf ongeldige e-mailinhoud terug.') from exc


def sync_gmail_receipts(household_id: str) -> dict[str, Any]:
    effective_household_id = str(household_id or '1').strip() or '1'
    account = get_receipt_gmail_account(effective_household_id, create_if_missing=True)
    if not gmail_is_configured():
        raise HTTPException(status_code=503, detail='De Gmail-koppeling is nog niet geconfigureerd in Rezzerv.')
    if not account.get('connected'):
        raise HTTPException(status_code=400, detail='Gmail is nog niet gekoppeld voor dit huishouden.')

    label_id, account = ensure_gmail_label(account)
    messages_payload, account = gmail_api_request(
        account,
        'users/me/messages',
        params={'labelIds': [label_id], 'maxResults': GMAIL_SYNC_BATCH_SIZE},
    )
    messages = messages_payload.get('messages') or []
    imported = 0
    duplicates = 0
    skipped = 0
    failed = 0
    latest_receipt_table_id = None
    latest_raw_receipt_id = None

    for message_item in messages:
        gmail_message_id = str(message_item.get('id') or '').strip()
        if not gmail_message_id:
            continue
        if has_processed_gmail_message(effective_household_id, gmail_message_id):
            skipped += 1
            continue
        gmail_message_payload, account = gmail_api_request(
            account,
            f'users/me/messages/{urllib.parse.quote(gmail_message_id)}',
            params={'format': 'raw'},
        )
        try:
            email_bytes = decode_gmail_raw_message(str(gmail_message_payload.get('raw') or ''))
            result = import_email_receipt_payload(effective_household_id, email_bytes, fallback_filename=f'gmail-{gmail_message_id}.eml', source_id=account.get('source_id'))
            latest_receipt_table_id = result.get('receipt_table_id') or latest_receipt_table_id
            latest_raw_receipt_id = result.get('raw_receipt_id') or latest_raw_receipt_id
            if result.get('duplicate'):
                duplicates += 1
            else:
                imported += 1
            store_gmail_import_result(
                effective_household_id,
                gmail_message_id,
                {
                    'gmail_thread_id': gmail_message_payload.get('threadId'),
                    'gmail_history_id': gmail_message_payload.get('historyId'),
                    'gmail_internal_date': gmail_datetime_from_timestamp(gmail_message_payload.get('internalDate')),
                    'raw_receipt_id': result.get('raw_receipt_id'),
                    'receipt_table_id': result.get('receipt_table_id'),
                    'import_status': 'duplicate' if result.get('duplicate') else str(result.get('parse_status') or 'imported'),
                    'error_message': None,
                },
            )
        except Exception as exc:
            failed += 1
            store_gmail_import_result(
                effective_household_id,
                gmail_message_id,
                {
                    'gmail_thread_id': gmail_message_payload.get('threadId'),
                    'gmail_history_id': gmail_message_payload.get('historyId'),
                    'gmail_internal_date': gmail_datetime_from_timestamp(gmail_message_payload.get('internalDate')),
                    'import_status': 'failed',
                    'error_message': normalize_api_error_message(str(exc) or 'Gmail-bericht kon niet worden verwerkt.'),
                },
            )

    synced_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    upsert_receipt_gmail_account(
        effective_household_id,
        {
            'label_name': account.get('label_name') or GMAIL_DEFAULT_LABEL_NAME,
            'label_id': label_id,
            'sync_status': 'ready',
            'last_synced_at': synced_at,
            'last_error': None,
        },
    )
    return {
        'connected': True,
        'label_name': account.get('label_name') or GMAIL_DEFAULT_LABEL_NAME,
        'label_id': label_id,
        'messages_seen': len(messages),
        'imported': imported,
        'duplicates': duplicates,
        'skipped': skipped,
        'failed': failed,
        'last_synced_at': synced_at,
        'latest_receipt_table_id': latest_receipt_table_id,
        'latest_raw_receipt_id': latest_raw_receipt_id,
    }




def resend_is_configured() -> bool:
    return resend_api_key_ready()


def resend_json_request(path: str, method: str = 'GET', *, data: Any = None, timeout: float = 30.0) -> dict[str, Any]:
    if not resend_is_configured():
        raise HTTPException(status_code=503, detail='De Resend API-sleutel is nog niet geconfigureerd in Rezzerv.')
    url = f"{RESEND_API_BASE_URL}/{path.lstrip('/')}"
    request_headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {RESEND_API_KEY}',
        'User-Agent': f'Rezzerv/{VERSION_TAG} (backend; household-invite)',
    }
    payload = None
    if data is not None:
        payload = json.dumps(data).encode('utf-8')
        request_headers['Content-Type'] = 'application/json'
    request_obj = urllib.request.Request(url, data=payload, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request_obj, timeout=timeout) as response:
            body = response.read()
            if not body:
                return {}
            return json.loads(body.decode('utf-8'))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='ignore')
        detail = None
        try:
            parsed = json.loads(body)
            detail = parsed.get('message') or parsed.get('error') or parsed.get('detail') or parsed.get('msg')
        except Exception:
            detail = body or exc.reason
        raise HTTPException(status_code=exc.code, detail=build_resend_error_message(exc.code, exc.reason, detail, exc.headers))
    except urllib.error.URLError as exc:
        reason_text = normalize_api_error_message(exc.reason, 'Resend is momenteel niet bereikbaar.')
        detail = f'Uitnodigingsmail niet verzonden. Netwerkfout richting Resend: {reason_text}. {build_outbound_email_configuration_summary()}'
        raise HTTPException(status_code=502, detail=detail)


def outbound_email_is_configured() -> bool:
    sender_ready, _ = outbound_email_sender_ready()
    return outbound_email_delivery_enabled() and resend_api_key_ready() and sender_ready


def send_household_invitation_email(recipient_email: str, household_name: str, display_role: str, password_value: str | None = None) -> dict[str, Any]:
    normalized_email = str(recipient_email or '').strip().lower()
    if not normalized_email:
        return {'status': 'skipped', 'message': 'Uitnodigingsmail overgeslagen: e-mailadres ontbreekt.'}
    if not outbound_email_delivery_enabled():
        return {
            'status': 'disabled',
            'message': 'Uitnodigingsmail is lokaal nog niet geconfigureerd. Zet REZZERV_EMAIL_ENABLED=true en vul daarna een geldige Resend-configuratie in. ' + build_outbound_email_configuration_summary(),
        }
    if not resend_api_key_ready():
        return {
            'status': 'config_invalid',
            'message': 'Uitnodigingsmail niet verzonden. REZZERV_RESEND_API_KEY ontbreekt of gebruikt nog een placeholder. ' + build_outbound_email_configuration_summary(),
        }
    sender_ready, sender_reason = outbound_email_sender_ready()
    if not sender_ready:
        return {
            'status': 'config_invalid',
            'message': f'Uitnodigingsmail niet verzonden. {sender_reason[:1].upper() + sender_reason[1:]}. Resend accepteert alleen geverifieerde afzenderdomeinen. ' + build_outbound_email_configuration_summary(),
        }
    config_warnings = build_outbound_email_configuration_warnings()
    if config_warnings:
        logger.warning('Uitnodigingsmail-configuratie bevat waarschuwingen: %s', '; '.join(config_warnings))

    normalized_display_role = str(display_role or '').strip().lower()
    if normalized_display_role == 'admin':
        display_role_text = 'admin'
    elif normalized_display_role == 'viewer':
        display_role_text = 'kijker'
    else:
        display_role_text = 'lid'
    login_url = f"{REZZERV_APP_BASE_URL}/login"
    subject = f"Je bent uitgenodigd voor Rezzerv als {display_role_text}"
    html_password = ''
    text_password = ''
    if str(password_value or '').strip():
        safe_password = html.escape(str(password_value or '').strip())
        html_password = f"<p><strong>Tijdelijk wachtwoord:</strong> {safe_password}</p>"
        text_password = f"Tijdelijk wachtwoord: {str(password_value or '').strip()}\nWijzig dit tijdelijke wachtwoord zodra daarvoor een functie beschikbaar is."
    html_body = (
        f"<p>Hallo,</p>"
        f"<p>Je bent toegevoegd aan <strong>{html.escape(str(household_name or 'Mijn huishouden'))}</strong> in Rezzerv als <strong>{display_role_text}</strong>.</p>"
        f"{html_password}"
        f"<p>Log in via <a href=\"{html.escape(login_url)}\">{html.escape(login_url)}</a> met je e-mailadres <strong>{html.escape(normalized_email)}</strong>.</p>"
        + ("<p>Gebruik je bestaande wachtwoord om in te loggen.</p>" if not html_password else "")
        + "<p>Groet,<br>Rezzerv</p>"
    )
    text_parts = [
        'Hallo,',
        '',
        f'Je bent toegevoegd aan {str(household_name or "Mijn huishouden")} in Rezzerv als {display_role_text}.',
        f'Log in via {login_url} met je e-mailadres {normalized_email}.',
    ]
    if text_password:
        text_parts.extend(['', text_password])
    else:
        text_parts.extend(['', 'Gebruik je bestaande wachtwoord om in te loggen.'])
    text_parts.extend(['', 'Groet,', 'Rezzerv'])
    resend_json_request(
        '/emails',
        method='POST',
        data={
            'from': f'{REZZERV_NOTIFICATION_FROM_NAME} <{REZZERV_NOTIFICATION_FROM_EMAIL}>',
            'to': [normalized_email],
            'subject': subject,
            'html': html_body,
            'text': '\n'.join(text_parts),
        },
    )
    return {'status': 'sent', 'message': f'Uitnodigingsmail verzonden naar {normalized_email}.'}


def download_remote_bytes(download_url: str, timeout: float = 60.0) -> bytes:
    request_obj = urllib.request.Request(download_url, headers={'Accept': '*/*'})
    try:
        with urllib.request.urlopen(request_obj, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f'Het downloaden van de ontvangen e-mail is mislukt ({exc.code}).')
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=normalize_api_error_message(exc.reason, 'De ontvangen e-mail kon niet worden gedownload.'))


def extract_email_addresses(values: Any) -> list[str]:
    candidates: list[str] = []
    if values is None:
        return candidates
    if isinstance(values, (list, tuple, set)):
        for item in values:
            candidates.extend(extract_email_addresses(item))
        return candidates
    parsed_addresses = [address for _, address in getaddresses([str(values)]) if address]
    if parsed_addresses:
        return [address.strip().lower() for address in parsed_addresses if address.strip()]
    raw_value = str(values).strip().lower()
    return [raw_value] if raw_value else []


def get_receipt_source_by_address(address: str) -> dict[str, Any] | None:
    normalized_address = str(address or '').strip().lower()
    if not normalized_address:
        return None
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, household_id, type, label, source_path, is_active, last_scan_at, created_at, updated_at
                FROM receipt_sources
                WHERE type = 'email' AND lower(source_path) = :source_path
                LIMIT 1
                """
            ),
            {'source_path': normalized_address},
        ).mappings().first()
    return build_receipt_source_response(row) if row else None


def resolve_household_email_source(recipient_addresses: list[str]) -> dict[str, Any]:
    for recipient in recipient_addresses:
        source = get_receipt_source_by_address(recipient)
        if source:
            source['route_address'] = recipient
            return source
    for recipient in recipient_addresses:
        local_part, _, domain_part = recipient.partition('@')
        if not local_part or not domain_part:
            continue
        if domain_part.strip().lower() != RECEIPT_EMAIL_DOMAIN.lower():
            continue
        if '+' not in local_part:
            continue
        _, household_hint = local_part.split('+', 1)
        normalized_household = sanitize_source_slug(household_hint)
        if not normalized_household:
            continue
        source = ensure_household_email_source(normalized_household)
        if str(source.get('route_address') or '').strip().lower() == recipient:
            return source
    raise HTTPException(status_code=400, detail='Deze inkomende e-mail past niet bij een bekend Rezzerv-adres.')


def get_resend_received_email(email_id: str) -> dict[str, Any]:
    response = resend_json_request(f'/emails/receiving/{urllib.parse.quote(str(email_id).strip())}')
    if isinstance(response, dict) and isinstance(response.get('data'), dict):
        return response['data']
    if isinstance(response, dict):
        return response
    raise HTTPException(status_code=502, detail='Resend leverde geen bruikbare e-mailgegevens op.')


def normalize_resend_received_at(value: Any) -> str | None:
    if value is None or value == '':
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return normalize_datetime(parsed)
    except Exception:
        return None



def get_receipt_inbound_event(provider: str, provider_email_id: str) -> dict[str, Any] | None:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, household_id, source_id, provider, provider_email_id, provider_message_id,
                       route_address, sender_email, sender_name, subject, received_at, webhook_received_at,
                       import_status, raw_receipt_id, receipt_table_id, error_message, created_at, updated_at
                FROM receipt_inbound_events
                WHERE provider = :provider AND provider_email_id = :provider_email_id
                LIMIT 1
                """
            ),
            {'provider': str(provider), 'provider_email_id': str(provider_email_id)},
        ).mappings().first()
    return dict(row) if row else None


def upsert_receipt_inbound_event(values: dict[str, Any]) -> dict[str, Any]:
    normalized_values = {
        'id': values.get('id') or str(uuid.uuid4()),
        'household_id': values.get('household_id'),
        'source_id': values.get('source_id'),
        'provider': str(values.get('provider') or 'resend').strip() or 'resend',
        'provider_email_id': str(values.get('provider_email_id') or '').strip(),
        'provider_message_id': values.get('provider_message_id'),
        'route_address': values.get('route_address'),
        'sender_email': values.get('sender_email'),
        'sender_name': values.get('sender_name'),
        'subject': values.get('subject'),
        'received_at': values.get('received_at'),
        'import_status': str(values.get('import_status') or 'received').strip() or 'received',
        'raw_receipt_id': values.get('raw_receipt_id'),
        'receipt_table_id': values.get('receipt_table_id'),
        'error_message': values.get('error_message'),
    }
    if not normalized_values['provider_email_id']:
        raise ValueError('provider_email_id is verplicht voor inbound events')
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO receipt_inbound_events (
                    id, household_id, source_id, provider, provider_email_id, provider_message_id,
                    route_address, sender_email, sender_name, subject, received_at,
                    import_status, raw_receipt_id, receipt_table_id, error_message, updated_at
                ) VALUES (
                    :id, :household_id, :source_id, :provider, :provider_email_id, :provider_message_id,
                    :route_address, :sender_email, :sender_name, :subject, :received_at,
                    :import_status, :raw_receipt_id, :receipt_table_id, :error_message, CURRENT_TIMESTAMP
                )
                ON CONFLICT(provider, provider_email_id) DO UPDATE SET
                    household_id = excluded.household_id,
                    source_id = excluded.source_id,
                    provider_message_id = excluded.provider_message_id,
                    route_address = excluded.route_address,
                    sender_email = excluded.sender_email,
                    sender_name = excluded.sender_name,
                    subject = excluded.subject,
                    received_at = excluded.received_at,
                    import_status = excluded.import_status,
                    raw_receipt_id = excluded.raw_receipt_id,
                    receipt_table_id = excluded.receipt_table_id,
                    error_message = excluded.error_message,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            normalized_values,
        )
        row = conn.execute(
            text(
                """
                SELECT id, household_id, source_id, provider, provider_email_id, provider_message_id,
                       route_address, sender_email, sender_name, subject, received_at, webhook_received_at,
                       import_status, raw_receipt_id, receipt_table_id, error_message, created_at, updated_at
                FROM receipt_inbound_events
                WHERE provider = :provider AND provider_email_id = :provider_email_id
                LIMIT 1
                """
            ),
            {'provider': normalized_values['provider'], 'provider_email_id': normalized_values['provider_email_id']},
        ).mappings().first()
    return dict(row) if row else normalized_values


def get_latest_receipt_inbound_event(household_id: str) -> dict[str, Any] | None:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, household_id, source_id, provider, provider_email_id, provider_message_id,
                       route_address, sender_email, sender_name, subject, received_at, webhook_received_at,
                       import_status, raw_receipt_id, receipt_table_id, error_message, created_at, updated_at
                FROM receipt_inbound_events
                WHERE household_id = :household_id
                ORDER BY COALESCE(received_at, webhook_received_at, created_at) DESC, created_at DESC
                LIMIT 1
                """
            ),
            {'household_id': str(household_id)},
        ).mappings().first()
    return dict(row) if row else None


def build_receipt_inbound_status(household_id: str) -> dict[str, Any]:
    latest = get_latest_receipt_inbound_event(str(household_id))
    return {
        'provider': 'resend',
        'resend_configured': resend_is_configured(),
        'webhook_endpoint_path': RECEIPT_INBOUND_PATH,
        'latest': latest,
    }


def mark_receipt_source_scanned(source_id: str):
    with engine.begin() as conn:
        conn.execute(
            text('UPDATE receipt_sources SET last_scan_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = :id'),
            {'id': str(source_id)},
        )


def import_resend_inbound_event(event_payload: dict[str, Any]) -> dict[str, Any]:
    if str(event_payload.get('type') or '').strip() != 'email.received':
        return {'ignored': True, 'reason': 'unsupported_event_type'}
    event_data = event_payload.get('data') if isinstance(event_payload.get('data'), dict) else {}
    email_id = str(event_data.get('email_id') or '').strip()
    if not email_id:
        raise HTTPException(status_code=400, detail='De inbound webhook mist een email_id.')
    existing = get_receipt_inbound_event('resend', email_id)
    if existing and (existing.get('receipt_table_id') or existing.get('raw_receipt_id') or existing.get('import_status') in {'imported', 'duplicate', 'failed'}):
        return {
            'duplicate': True,
            'provider': 'resend',
            'provider_email_id': email_id,
            'import_status': existing.get('import_status') or 'duplicate',
            'receipt_table_id': existing.get('receipt_table_id'),
            'raw_receipt_id': existing.get('raw_receipt_id'),
        }

    if not existing:
        upsert_receipt_inbound_event({'provider': 'resend', 'provider_email_id': email_id, 'import_status': 'received'})

    received_email = get_resend_received_email(email_id)
    recipient_addresses = extract_email_addresses(event_data.get('to') or received_email.get('to') or [])
    source = resolve_household_email_source(recipient_addresses)
    effective_household_id = str(source.get('household_id') or '1').strip() or '1'
    route_address = str(source.get('route_address') or source.get('source_path') or '').strip().lower()
    raw_info = received_email.get('raw') if isinstance(received_email.get('raw'), dict) else {}
    raw_download_url = str(raw_info.get('download_url') or '').strip()
    if not raw_download_url:
        raise HTTPException(status_code=502, detail='Resend leverde geen downloadbare ruwe e-mail voor deze inbound gebeurtenis.')
    raw_email_bytes = download_remote_bytes(raw_download_url)
    sender_name = None
    sender_email = None
    from_addresses = getaddresses([str(received_email.get('from') or event_data.get('from') or '')])
    if from_addresses:
        sender_name, sender_email = from_addresses[0]
        sender_name = (sender_name or '').strip() or None
        sender_email = (sender_email or '').strip().lower() or None
    try:
        result = import_email_receipt_payload(
            effective_household_id,
            raw_email_bytes,
            fallback_filename=f'resend-{email_id}.eml',
            source_id=str(source.get('id') or ''),
        )
    except ValueError:
        fallback_subject = str(received_email.get('subject') or event_data.get('subject') or 'E-mailbon').strip() or 'E-mailbon'
        fallback_store_name = sender_name or (sender_email.split('@', 1)[1].split('.', 1)[0].replace('-', ' ').replace('_', ' ').title() if sender_email and '@' in sender_email else None) or fallback_subject[:120]
        fallback_text = '\n'.join(
            part
            for part in [
                fallback_subject,
                str(received_email.get('html') or '').strip(),
                str(received_email.get('text') or '').strip(),
            ]
            if part
        ).encode('utf-8')
        result = ingest_receipt(
            engine=engine,
            receipt_storage_root=RECEIPT_STORAGE_ROOT,
            household_id=effective_household_id,
            filename=f'resend-{email_id}.txt',
            file_bytes=fallback_text or fallback_subject.encode('utf-8'),
            source_id=str(source.get('id') or ''),
            mime_type='text/plain',
            reject_non_receipt=False,
            create_failed_receipt_table=True,
            failed_store_name=fallback_store_name,
            failed_purchase_at=normalize_resend_received_at(received_email.get('created_at') or event_data.get('created_at')),
        )
    import_status = 'duplicate' if result.get('duplicate') else ('imported' if result.get('receipt_table_id') or result.get('raw_receipt_id') else 'failed')
    inbound_row = upsert_receipt_inbound_event(
        {
            'household_id': effective_household_id,
            'source_id': source.get('id'),
            'provider': 'resend',
            'provider_email_id': email_id,
            'provider_message_id': received_email.get('message_id') or event_data.get('message_id'),
            'route_address': route_address,
            'sender_email': sender_email,
            'sender_name': sender_name,
            'subject': received_email.get('subject') or event_data.get('subject'),
            'received_at': normalize_resend_received_at(received_email.get('created_at') or event_data.get('created_at')),
            'import_status': import_status,
            'raw_receipt_id': result.get('raw_receipt_id'),
            'receipt_table_id': result.get('receipt_table_id'),
            'error_message': None,
        }
    )
    mark_receipt_source_scanned(str(source.get('id') or ''))
    response = dict(result)
    response['provider'] = 'resend'
    response['provider_email_id'] = email_id
    response['import_status'] = import_status
    response['route_address'] = route_address
    response['latest_inbound'] = inbound_row
    return response

def parse_email_receipt_payload(email_bytes: bytes, fallback_filename: str = 'receipt.eml') -> dict[str, Any]:
    try:
        message = BytesParser(policy=policy.default).parsebytes(email_bytes)
    except Exception as exc:
        raise ValueError('Het e-mailbestand kon niet worden gelezen.') from exc

    sender_name = None
    sender_email = None
    from_addresses = getaddresses(message.get_all('from', []))
    if from_addresses:
        sender_name, sender_email = from_addresses[0]
        sender_name = (sender_name or '').strip() or None
        sender_email = (sender_email or '').strip().lower() or None

    subject = str(message.get('subject') or '').strip() or None
    received_at = None
    date_header = message.get('date')
    if date_header:
        try:
            parsed = parsedate_to_datetime(date_header)
            received_at = normalize_datetime(parsed) if parsed else None
        except Exception:
            received_at = None

    body_text = None
    body_html = None
    attachments: list[dict[str, Any]] = []

    if message.is_multipart():
        for part in message.walk():
            content_type = str(part.get_content_type() or 'application/octet-stream')
            filename = part.get_filename()
            disposition = (part.get_content_disposition() or '').lower()
            payload = part.get_payload(decode=True) or b''
            if not payload and content_type.startswith('text/'):
                try:
                    payload = part.get_content().encode('utf-8')
                except Exception:
                    payload = b''
            if (filename or disposition in {'attachment', 'inline'}) and payload:
                attachments.append({
                    'filename': filename or 'bijlage',
                    'mime_type': content_type,
                    'payload': payload,
                    'disposition': disposition,
                })
                continue
            if content_type == 'text/plain' and body_text is None:
                try:
                    body_text = part.get_content()
                except Exception:
                    body_text = payload.decode('utf-8', errors='ignore') if payload else None
            elif content_type == 'text/html' and body_html is None:
                try:
                    body_html = part.get_content()
                except Exception:
                    body_html = payload.decode('utf-8', errors='ignore') if payload else None
    else:
        content_type = str(message.get_content_type() or 'text/plain')
        try:
            single_content = message.get_content()
        except Exception:
            single_content = email_bytes.decode('utf-8', errors='ignore')
        if content_type == 'text/html':
            body_html = single_content
        else:
            body_text = single_content

    attachments.sort(key=lambda item: len(item.get('payload') or b''), reverse=True)

    selected = None
    for predicate in (
        lambda item: item['mime_type'] == 'application/pdf',
        lambda item: str(item['mime_type']).startswith('image/'),
    ):
        for attachment in attachments:
            if predicate(attachment) and attachment.get('payload'):
                selected = {
                    'selected_part_type': 'attachment',
                    'selected_filename': attachment['filename'],
                    'selected_mime_type': attachment['mime_type'],
                    'selected_bytes': attachment['payload'],
                }
                break
        if selected:
            break

    if not selected and body_html:
        subject_slug = sanitize_source_slug(subject or Path(fallback_filename).stem or 'receipt-email')
        selected = {
            'selected_part_type': 'html_body',
            'selected_filename': f'{subject_slug}.html',
            'selected_mime_type': 'text/html',
            'selected_bytes': body_html.encode('utf-8'),
        }

    if not selected and body_text:
        subject_slug = sanitize_source_slug(subject or Path(fallback_filename).stem or 'receipt-email')
        selected = {
            'selected_part_type': 'text_body',
            'selected_filename': f'{subject_slug}.txt',
            'selected_mime_type': 'text/plain',
            'selected_bytes': body_text.encode('utf-8'),
        }

    if not selected:
        raise ValueError('In deze e-mail is geen bruikbare bonbijlage of mailinhoud gevonden.')

    return {
        'sender_name': sender_name,
        'sender_email': sender_email,
        'subject': subject,
        'received_at': received_at,
        'body_text': body_text,
        'body_html': body_html,
        **selected,
    }


def derive_email_receipt_store_name(payload: dict[str, Any]) -> str | None:
    sender_name = str(payload.get('sender_name') or '').strip()
    if sender_name:
        return sender_name[:120]
    sender_email = str(payload.get('sender_email') or '').strip().lower()
    if sender_email and '@' in sender_email:
        domain = sender_email.split('@', 1)[1].split('.', 1)[0].replace('-', ' ').replace('_', ' ').strip()
        if domain:
            return domain.title()[:120]
    subject = str(payload.get('subject') or '').strip()
    if subject:
        return subject[:120]
    return None


def _looks_like_email_upload(filename: str | None, mime_type: str | None) -> bool:
    suffix = Path(str(filename or '')).suffix.lower()
    normalized_mime = str(mime_type or '').split(';', 1)[0].strip().lower()
    return normalized_mime == 'message/rfc822' or suffix == '.eml'


def _looks_like_zip_upload(filename: str | None, mime_type: str | None, file_bytes: bytes | None = None) -> bool:
    suffix = Path(str(filename or '')).suffix.lower()
    normalized_mime = str(mime_type or '').split(';', 1)[0].strip().lower()
    if suffix == '.zip':
        return True
    if normalized_mime in ZIP_MIME_TYPES:
        if file_bytes is None:
            return True
        return bytes(file_bytes[:4]) == b'PK\x03\x04'
    return bytes((file_bytes or b'')[:4]) == b'PK\x03\x04'


def _guess_member_mime_type(filename: str) -> str | None:
    guessed, _ = mimetypes.guess_type(str(filename or ''))
    return guessed


def _extract_supported_receipts_from_zip(filename: str, file_bytes: bytes) -> list[dict[str, Any]]:
    members: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            for info in sorted(archive.infolist(), key=lambda item: item.filename.lower()):
                if info.is_dir():
                    continue
                member_name = str(info.filename or '').replace('\\', '/').strip()
                leaf_name = Path(member_name).name
                if not member_name or not leaf_name:
                    continue
                if member_name.startswith('__MACOSX/') or leaf_name.startswith('._'):
                    continue
                suffix = Path(leaf_name).suffix.lower()
                if suffix not in SUPPORTED_RECEIPT_ARCHIVE_EXTENSIONS:
                    continue
                payload = archive.read(info)
                if not payload:
                    continue
                members.append({
                    'filename': leaf_name,
                    'archive_path': member_name,
                    'bytes': payload,
                    'mime_type': _guess_member_mime_type(leaf_name),
                })
    except zipfile.BadZipFile as exc:
        raise ValueError('Het geuploade zip-bestand kon niet worden geopend.') from exc
    if not members:
        raise ValueError(f'Het zip-bestand {filename or "upload.zip"} bevat geen ondersteunde kassabonnen.')
    return members


def import_uploaded_receipt_payload(
    household_id: str,
    filename: str,
    file_bytes: bytes,
    source_id: str | None = None,
    mime_type: str | None = None,
    reject_non_receipt: bool = False,
    create_failed_receipt_table: bool = False,
    failed_store_name: str | None = None,
    failed_purchase_at: str | None = None,
) -> dict[str, Any]:
    if _looks_like_zip_upload(filename, mime_type, file_bytes):
        member_results: list[dict[str, Any]] = []
        for member in _extract_supported_receipts_from_zip(filename, file_bytes):
            try:
                imported = import_uploaded_receipt_payload(
                    household_id=household_id,
                    filename=member['filename'],
                    file_bytes=member['bytes'],
                    source_id=source_id,
                    mime_type=member.get('mime_type'),
                    reject_non_receipt=reject_non_receipt,
                    create_failed_receipt_table=create_failed_receipt_table,
                    failed_store_name=failed_store_name,
                    failed_purchase_at=failed_purchase_at,
                )
                item = dict(imported)
                item['filename'] = member['filename']
                item['archive_path'] = member['archive_path']
                item['import_status'] = 'duplicate' if imported.get('duplicate') else ('imported' if imported.get('receipt_table_id') or imported.get('raw_receipt_id') else 'failed')
                member_results.append(item)
            except Exception as exc:
                logger.exception('Zip-import mislukt voor lid %s uit %s', member['archive_path'], filename)
                member_results.append({
                    'filename': member['filename'],
                    'archive_path': member['archive_path'],
                    'import_status': 'failed',
                    'error_message': str(exc),
                })
        successful = [item for item in member_results if item.get('receipt_table_id') or item.get('raw_receipt_id') or item.get('duplicate')]
        imported_items = [item for item in member_results if item.get('import_status') == 'imported']
        duplicate_items = [item for item in member_results if item.get('import_status') == 'duplicate']
        failed_items = [item for item in member_results if item.get('import_status') == 'failed']
        if reject_non_receipt and not successful:
            raise ValueError('Geen van de bestanden in het zip-bestand is als bruikbare kassabon herkend.')
        latest_success = successful[-1] if successful else {}
        return {
            'batch': True,
            'filename': filename,
            'file_count': len(member_results),
            'processed_count': len(member_results),
            'imported_count': len(imported_items),
            'duplicate_count': len(duplicate_items),
            'failed_count': len(failed_items),
            'receipt_table_id': latest_success.get('receipt_table_id'),
            'raw_receipt_id': latest_success.get('raw_receipt_id'),
            'parse_status': 'batch_processed',
            'results': member_results,
        }
    if _looks_like_email_upload(filename, mime_type):
        result = import_email_receipt_payload(
            household_id=str(household_id),
            email_bytes=file_bytes,
            fallback_filename=filename or 'receipt.eml',
            source_id=source_id,
        )
        if reject_non_receipt and not result.get('receipt_table_id'):
            raise ValueError('Gedeelde inhoud is niet als bruikbare kassabon herkend.')
        return result
    return ingest_receipt(
        engine=engine,
        receipt_storage_root=RECEIPT_STORAGE_ROOT,
        household_id=str(household_id),
        filename=filename,
        file_bytes=file_bytes,
        source_id=source_id,
        mime_type=mime_type,
        reject_non_receipt=reject_non_receipt,
        create_failed_receipt_table=create_failed_receipt_table,
        failed_store_name=failed_store_name,
        failed_purchase_at=failed_purchase_at,
    )


def store_receipt_email_metadata(raw_receipt_id: str, household_id: str, payload: dict[str, Any]):
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO receipt_email_messages (
                    raw_receipt_id, household_id, sender_email, sender_name, subject, received_at, body_text, body_html,
                    selected_part_type, selected_filename, selected_mime_type, updated_at
                ) VALUES (
                    :raw_receipt_id, :household_id, :sender_email, :sender_name, :subject, :received_at, :body_text, :body_html,
                    :selected_part_type, :selected_filename, :selected_mime_type, CURRENT_TIMESTAMP
                )
                ON CONFLICT(raw_receipt_id) DO UPDATE SET
                    household_id = excluded.household_id,
                    sender_email = excluded.sender_email,
                    sender_name = excluded.sender_name,
                    subject = excluded.subject,
                    received_at = excluded.received_at,
                    body_text = excluded.body_text,
                    body_html = excluded.body_html,
                    selected_part_type = excluded.selected_part_type,
                    selected_filename = excluded.selected_filename,
                    selected_mime_type = excluded.selected_mime_type,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {
                'raw_receipt_id': raw_receipt_id,
                'household_id': household_id,
                'sender_email': payload.get('sender_email'),
                'sender_name': payload.get('sender_name'),
                'subject': payload.get('subject'),
                'received_at': payload.get('received_at'),
                'body_text': payload.get('body_text'),
                'body_html': payload.get('body_html'),
                'selected_part_type': payload.get('selected_part_type'),
                'selected_filename': payload.get('selected_filename'),
                'selected_mime_type': payload.get('selected_mime_type'),
            },
        )


def import_email_receipt_payload(household_id: str, email_bytes: bytes, fallback_filename: str = 'receipt.eml', source_id: str | None = None) -> dict[str, Any]:
    default_email_source = ensure_household_email_source(household_id)
    payload = parse_email_receipt_payload(email_bytes, fallback_filename=fallback_filename)
    effective_source_id = str(source_id or default_email_source['id']).strip() or default_email_source['id']
    selected_part_type = str(payload.get('selected_part_type') or '').strip().lower()
    selected_mime_type = str(payload.get('selected_mime_type') or '').strip().lower()
    ingest_filename = payload['selected_filename']
    ingest_bytes = payload['selected_bytes']
    ingest_mime_type = payload['selected_mime_type']
    body_only_email = selected_part_type in {'html_body', 'text_body'} and selected_mime_type in {'text/html', 'text/plain'}
    if body_only_email:
        ingest_filename = fallback_filename or 'receipt.eml'
        ingest_bytes = email_bytes
        ingest_mime_type = 'message/rfc822'
    result = ingest_receipt(
        engine=engine,
        receipt_storage_root=RECEIPT_STORAGE_ROOT,
        household_id=str(household_id),
        filename=ingest_filename,
        file_bytes=ingest_bytes,
        source_id=effective_source_id,
        mime_type=ingest_mime_type,
        reject_non_receipt=False,
        create_failed_receipt_table=True,
        failed_store_name=derive_email_receipt_store_name(payload),
        failed_purchase_at=payload.get('received_at'),
    )
    raw_receipt_id = result.get('raw_receipt_id')
    if raw_receipt_id:
        store_receipt_email_metadata(raw_receipt_id, str(household_id), payload)
    receipt_table_id = result.get('receipt_table_id')
    if receipt_table_id:
        derived_store_name = derive_email_receipt_store_name(payload)
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE receipt_tables
                    SET store_name = COALESCE(store_name, :store_name),
                        purchase_at = COALESCE(purchase_at, :purchase_at),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    """
                ),
                {'id': receipt_table_id, 'store_name': derived_store_name, 'purchase_at': payload.get('received_at')},
            )
            stored_receipt = conn.execute(
                text(
                    """
                    SELECT parse_status, line_count, total_amount, purchase_at
                    FROM receipt_tables
                    WHERE id = :id
                    LIMIT 1
                    """
                ),
                {'id': receipt_table_id},
            ).mappings().first()
        should_reparse = bool(
            stored_receipt
            and (
                str(payload.get('selected_part_type') or '').strip().lower() in {'html_body', 'text_body'}
                or str(stored_receipt.get('parse_status') or '').strip().lower() in {'failed', 'review_needed'}
                or int(stored_receipt.get('line_count') or 0) <= 0
                or stored_receipt.get('total_amount') is None
                or stored_receipt.get('purchase_at') is None
            )
        )
        if should_reparse:
            repaired = reparse_receipt(engine, RECEIPT_STORAGE_ROOT, str(receipt_table_id))
            if repaired:
                result['parse_status'] = repaired.get('parse_status') or result.get('parse_status')
    result['source_id'] = effective_source_id
    result['source_label'] = default_email_source.get('label', 'E-mail')
    result['sender_email'] = payload.get('sender_email')
    result['sender_name'] = payload.get('sender_name')
    result['subject'] = payload.get('subject')
    result['received_at'] = payload.get('received_at')
    return result


def ensure_household(email: str):
    user = get_user_record(email) or {}
    household_id = str(user.get("household_id") or len(households) + 1)
    if household_id not in households:
        households[household_id] = {
            "id": household_id,
            "naam": user.get("household_name") or "Mijn huishouden",
            "created_at": datetime.utcnow().isoformat(),
        }
    return households[household_id]


def ensure_release_963_schema():
    with engine.begin() as conn:
        receipt_columns = {row['name'] for row in conn.execute(text("PRAGMA table_info(receipt_tables)")).mappings().all()}
        if 'discount_total' not in receipt_columns:
            conn.execute(text("ALTER TABLE receipt_tables ADD COLUMN discount_total NUMERIC(12,2)"))


def ensure_release_1221_schema():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS receipt_import_batches (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                source_filename TEXT,
                total_files INTEGER NOT NULL DEFAULT 0,
                processed_files INTEGER NOT NULL DEFAULT 0,
                imported_files INTEGER NOT NULL DEFAULT 0,
                duplicate_files INTEGER NOT NULL DEFAULT 0,
                failed_files INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'queued',
                error_message TEXT,
                latest_receipt_table_id TEXT,
                latest_raw_receipt_id TEXT,
                results_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                finished_at DATETIME
            )
        """))


def _serialize_receipt_import_batch(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    total = int(row.get('total_files') or 0)
    processed = int(row.get('processed_files') or 0)
    imported = int(row.get('imported_files') or 0)
    duplicates = int(row.get('duplicate_files') or 0)
    failed = int(row.get('failed_files') or 0)
    percentage = 0
    if total > 0:
        percentage = max(0, min(100, int(round((processed / total) * 100))))
    results = []
    raw_results = row.get('results_json')
    if raw_results:
        try:
            parsed = json.loads(raw_results)
            if isinstance(parsed, list):
                results = parsed
        except Exception:
            results = []
    return {
        'batch_id': str(row.get('id') or ''),
        'household_id': str(row.get('household_id') or ''),
        'source_filename': row.get('source_filename'),
        'total_files': total,
        'processed_files': processed,
        'imported_files': imported,
        'duplicate_files': duplicates,
        'failed_files': failed,
        'status': str(row.get('status') or 'queued'),
        'error_message': row.get('error_message'),
        'latest_receipt_table_id': row.get('latest_receipt_table_id'),
        'latest_raw_receipt_id': row.get('latest_raw_receipt_id'),
        'percentage': percentage,
        'results': results,
        'created_at': normalize_datetime(row.get('created_at')),
        'updated_at': normalize_datetime(row.get('updated_at')),
        'finished_at': normalize_datetime(row.get('finished_at')),
    }


def create_receipt_import_batch(household_id: str, source_filename: str, total_files: int) -> dict[str, Any]:
    batch_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO receipt_import_batches (
                id, household_id, source_filename, total_files, processed_files, imported_files, duplicate_files, failed_files, status, updated_at
            ) VALUES (
                :id, :household_id, :source_filename, :total_files, 0, 0, 0, 0, 'queued', CURRENT_TIMESTAMP
            )
        """), {'id': batch_id, 'household_id': str(household_id), 'source_filename': source_filename, 'total_files': int(total_files)})
        row = conn.execute(text('SELECT * FROM receipt_import_batches WHERE id = :id LIMIT 1'), {'id': batch_id}).mappings().first()
    return _serialize_receipt_import_batch(row) or {'batch_id': batch_id, 'total_files': int(total_files), 'processed_files': 0, 'percentage': 0, 'status': 'queued'}


def update_receipt_import_batch(batch_id: str, **values: Any) -> dict[str, Any] | None:
    if not batch_id:
        return None
    assignments = []
    params: dict[str, Any] = {'id': batch_id}
    for key, value in values.items():
        if key not in {
            'processed_files', 'imported_files', 'duplicate_files', 'failed_files', 'status', 'error_message',
            'latest_receipt_table_id', 'latest_raw_receipt_id', 'results_json', 'finished_at'
        }:
            continue
        assignments.append(f"{key} = :{key}")
        params[key] = value
    if not assignments:
        return get_receipt_import_batch(batch_id)
    assignments.append('updated_at = CURRENT_TIMESTAMP')
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE receipt_import_batches SET {', '.join(assignments)} WHERE id = :id"), params)
        row = conn.execute(text('SELECT * FROM receipt_import_batches WHERE id = :id LIMIT 1'), {'id': batch_id}).mappings().first()
    return _serialize_receipt_import_batch(row)


def get_receipt_import_batch(batch_id: str) -> dict[str, Any] | None:
    if not batch_id:
        return None
    with engine.begin() as conn:
        row = conn.execute(text('SELECT * FROM receipt_import_batches WHERE id = :id LIMIT 1'), {'id': batch_id}).mappings().first()
    return _serialize_receipt_import_batch(row)


def _run_receipt_zip_import_batch(batch_id: str, household_id: str, source_id: str, source_filename: str, members: list[dict[str, Any]]):
    update_receipt_import_batch(batch_id, status='running', results_json='[]', error_message=None)
    processed = 0
    imported = 0
    duplicates = 0
    failed = 0
    latest_receipt_table_id = None
    latest_raw_receipt_id = None
    member_results: list[dict[str, Any]] = []
    for member in members:
        try:
            imported_result = import_uploaded_receipt_payload(
                household_id=household_id,
                filename=member['filename'],
                file_bytes=member['bytes'],
                source_id=source_id,
                mime_type=member.get('mime_type'),
            )
            item = dict(imported_result)
            item['filename'] = member['filename']
            item['archive_path'] = member['archive_path']
            item['import_status'] = 'duplicate' if imported_result.get('duplicate') else ('imported' if imported_result.get('receipt_table_id') or imported_result.get('raw_receipt_id') else 'failed')
            member_results.append(item)
            if item['import_status'] == 'imported':
                imported += 1
            elif item['import_status'] == 'duplicate':
                duplicates += 1
            else:
                failed += 1
            latest_receipt_table_id = imported_result.get('receipt_table_id') or latest_receipt_table_id
            latest_raw_receipt_id = imported_result.get('raw_receipt_id') or latest_raw_receipt_id
        except Exception as exc:
            logger.exception('Zip-import mislukt voor lid %s uit %s', member.get('archive_path'), source_filename)
            failed += 1
            member_results.append({
                'filename': member.get('filename'),
                'archive_path': member.get('archive_path'),
                'import_status': 'failed',
                'error_message': str(exc),
            })
        processed += 1
        update_receipt_import_batch(
            batch_id,
            processed_files=processed,
            imported_files=imported,
            duplicate_files=duplicates,
            failed_files=failed,
            status='running',
            latest_receipt_table_id=latest_receipt_table_id,
            latest_raw_receipt_id=latest_raw_receipt_id,
            results_json=json.dumps(member_results),
        )
    final_status = 'completed_with_errors' if failed else 'completed'
    update_receipt_import_batch(
        batch_id,
        processed_files=processed,
        imported_files=imported,
        duplicate_files=duplicates,
        failed_files=failed,
        status=final_status,
        latest_receipt_table_id=latest_receipt_table_id,
        latest_raw_receipt_id=latest_raw_receipt_id,
        results_json=json.dumps(member_results),
        finished_at=datetime.utcnow().isoformat(),
    )


def start_receipt_zip_import_batch(batch_id: str, household_id: str, source_id: str, source_filename: str, members: list[dict[str, Any]]):
    worker = threading.Thread(
        target=_run_receipt_zip_import_batch,
        args=(batch_id, str(household_id), str(source_id), str(source_filename), list(members)),
        daemon=True,
        name=f'receipt-zip-import-{batch_id[:8]}',
    )
    worker.start()
    return worker


def backfill_receipt_unpack_statuses(conn, household_id: Optional[str] = None, limit: Optional[int] = None) -> dict[str, Any]:
    query = """
        SELECT
            rt.id,
            rt.household_id,
            rt.store_name,
            rt.purchase_at,
            rt.total_amount,
            rt.discount_total,
            rt.parse_status,
            (
                SELECT COUNT(*)
                FROM receipt_table_lines rtl_count
                WHERE rtl_count.receipt_table_id = rt.id
                  AND COALESCE(rtl_count.is_deleted, 0) = 0
                  AND TRIM(COALESCE(rtl_count.corrected_raw_label, rtl_count.raw_label, '')) <> ''
            ) AS line_count,
            (
                SELECT COALESCE(SUM(COALESCE(rtl.corrected_line_total, rtl.line_total, 0)), 0)
                FROM receipt_table_lines rtl
                WHERE rtl.receipt_table_id = rt.id
                  AND COALESCE(rtl.is_deleted, 0) = 0
            ) AS line_total_sum
        FROM receipt_tables rt
    """
    params: dict[str, Any] = {}
    conditions: list[str] = []
    if household_id is not None:
        conditions.append("rt.household_id = :household_id")
        params['household_id'] = str(household_id)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY rt.created_at DESC"
    if limit is not None:
        query += " LIMIT :limit"
        params['limit'] = int(limit)
    rows = conn.execute(text(query), params).mappings().all()
    report: dict[str, Any] = {
        'scanned': 0,
        'updated': 0,
        'unchanged': 0,
        'errors': 0,
        'status_counts': {'Gecontroleerd': 0, 'Controle nodig': 0, 'Handmatig': 0},
        'parse_status_counts': {},
        'lines': {},
    }
    for row in rows:
        receipt_id = str(row.get('id') or '').strip()
        if not receipt_id:
            continue
        report['scanned'] += 1
        try:
            criteria = evaluate_receipt_unpack_criteria(dict(row))
            inbox_status = str(criteria.get('inbox_status') or 'Handmatig')
            next_parse_status = str(criteria.get('parse_status') or 'manual').strip().lower() or 'manual'
            report['status_counts'][inbox_status] = int(report['status_counts'].get(inbox_status, 0) or 0) + 1
            report['parse_status_counts'][next_parse_status] = int(report['parse_status_counts'].get(next_parse_status, 0) or 0) + 1
            current_parse_status = str(row.get('parse_status') or '').strip().lower()
            current_line_count = int(row.get('line_count') or 0)
            computed_line_count = int(criteria.get('line_count') or 0)
            changed = current_parse_status != next_parse_status or current_line_count != computed_line_count
            if changed:
                conn.execute(
                    text("""
                        UPDATE receipt_tables
                        SET parse_status = :parse_status,
                            line_count = :line_count,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                    """),
                    {'id': receipt_id, 'parse_status': next_parse_status, 'line_count': computed_line_count},
                )
                report['updated'] += 1
            else:
                report['unchanged'] += 1
            report['lines'][receipt_id] = {
                'store_name': row.get('store_name'),
                'line_count': computed_line_count,
                'total_amount': row.get('total_amount'),
                'line_total_sum': row.get('line_total_sum'),
                'status': inbox_status,
                'parse_status': next_parse_status,
            }
        except Exception as exc:
            report['errors'] += 1
            report['lines'][receipt_id] = {'error': str(exc)}
    return report


@app.on_event("startup")
async def log_runtime_datastore_configuration():
    datastore_info = get_runtime_datastore_info()
    logger.info("Datastore: %s", datastore_info.get('datastore', 'onbekend'))
    logger.info("Database: %s", datastore_info.get('database') or datastore_info.get('database_url') or 'onbekend')
    if datastore_info.get('storage'):
        logger.info("Storage: %s", datastore_info['storage'])
    try:
        with engine.begin() as conn:
            report = backfill_purchase_import_live_aliases(conn)
        logger.info(
            "Purchase-import live alias backfill: scanned=%s updated=%s skipped=%s errors=%s remaining=%s",
            report.get('scanned'),
            report.get('updated'),
            report.get('skipped'),
            report.get('errors'),
            report.get('remaining_live_aliases'),
        )
    except Exception as exc:
        logger.warning("Purchase-import live alias backfill failed: %s", exc)
    try:
        with engine.begin() as conn:
            receipt_report = backfill_receipt_unpack_statuses(conn)
        logger.info(
            "Receipt status backfill: scanned=%s updated=%s unchanged=%s errors=%s counts=%s",
            receipt_report.get('scanned'),
            receipt_report.get('updated'),
            receipt_report.get('unchanged'),
            receipt_report.get('errors'),
            receipt_report.get('status_counts'),
        )
    except Exception as exc:
        logger.warning("Receipt status backfill failed: %s", exc)


ensure_release_1221_schema()


@app.get("/api/health")
def health():
    datastore_info = get_runtime_datastore_info()
    payload = {"status": "ok", "datastore": datastore_info.get('datastore', 'onbekend')}
    if datastore_info.get('database'):
        payload['database'] = datastore_info['database']
    if datastore_info.get('storage'):
        payload['storage'] = datastore_info['storage']
    return payload


@app.get("/api/version")
def api_version():
    return {
        "version": VERSION_TAG,
        "source": "VERSION.txt",
    }


@app.post("/api/admin/backfill-purchase-import-live-aliases")
def run_purchase_import_live_alias_backfill(household_id: Optional[str] = None, limit: Optional[int] = None):
    with engine.begin() as conn:
        report = backfill_purchase_import_live_aliases(conn, household_id=household_id, limit=limit)
    return report


@app.post("/api/admin/recompute-receipt-statuses")
def run_receipt_status_backfill(household_id: Optional[str] = None, limit: Optional[int] = None):
    with engine.begin() as conn:
        report = backfill_receipt_unpack_statuses(conn, household_id=household_id, limit=limit)
    return report


@app.post("/api/admin/validate-receipt-status-baseline")
def run_receipt_status_baseline_validation(household_id: Optional[str] = None):
    with engine.begin() as conn:
        report = validate_receipt_status_baseline(conn, household_id=household_id)
    return report


@app.post("/api/admin/diagnose-receipt-status-baseline")
def run_receipt_status_baseline_diagnosis(household_id: Optional[str] = None):
    with engine.begin() as conn:
        report = diagnose_receipt_status_baseline(conn, household_id=household_id)
    return report


@app.post("/api/receipts/share-import")
async def import_shared_receipt(
    household_id: str = Form(...),
    file: UploadFile = File(...),
    source_context: str = Form('shared_file'),
    source_label: Optional[str] = Form(None),
    x_rezzerv_share_source: Optional[str] = Header(default=None),
):
    effective_household_id = str(household_id or '1')
    ensure_default_receipt_sources(engine, RECEIPT_STORAGE_ROOT, effective_household_id)
    resolved_context = str(x_rezzerv_share_source or source_context or 'shared_file')
    share_source = ensure_share_receipt_source(engine, effective_household_id, resolved_context)
    if source_label:
        with engine.begin() as conn:
            conn.execute(
                text('UPDATE receipt_sources SET label = :label, updated_at = CURRENT_TIMESTAMP WHERE id = :id'),
                {'id': share_source['id'], 'label': str(source_label).strip()[:120] or share_source['label']},
            )
            refreshed = conn.execute(
                text('SELECT id, household_id, type, label, source_path, is_active, last_scan_at, created_at, updated_at FROM receipt_sources WHERE id = :id LIMIT 1'),
                {'id': share_source['id']},
            ).mappings().first()
            if refreshed:
                share_source = dict(refreshed)
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail='Gedeelde inhoud is leeg.')
    try:
        result = import_uploaded_receipt_payload(
            household_id=effective_household_id,
            filename=file.filename or 'shared-receipt',
            file_bytes=file_bytes,
            source_id=share_source['id'],
            mime_type=file.content_type,
            reject_non_receipt=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    result['source_id'] = share_source['id']
    result['source_label'] = share_source.get('label')
    return result


@app.post("/api/receipts/share-target")
async def import_share_target_receipt(
    household_id: str = Query('1'),
    receipt: UploadFile = File(...),
    title: Optional[str] = Form(None),
    text_value: Optional[str] = Form(None, alias='text'),
    url: Optional[str] = Form(None),
):
    effective_household_id = str(household_id or '1').strip() or '1'
    ensure_default_receipt_sources(engine, RECEIPT_STORAGE_ROOT, effective_household_id)
    share_source = ensure_share_receipt_source(engine, effective_household_id, 'shared_app')
    file_bytes = await receipt.read()
    if not file_bytes:
        return RedirectResponse(url='/kassa?share_status=error&message=Gedeelde%20inhoud%20is%20leeg.', status_code=303)
    resolved_label = None
    for candidate in (title, text_value, url):
        if candidate and str(candidate).strip():
            resolved_label = str(candidate).strip()[:120]
            break
    if resolved_label:
        with engine.begin() as conn:
            conn.execute(
                text('UPDATE receipt_sources SET label = :label, updated_at = CURRENT_TIMESTAMP WHERE id = :id'),
                {'id': share_source['id'], 'label': resolved_label},
            )
    try:
        result = import_uploaded_receipt_payload(
            household_id=effective_household_id,
            filename=receipt.filename or 'shared-receipt',
            file_bytes=file_bytes,
            source_id=share_source['id'],
            mime_type=receipt.content_type,
            reject_non_receipt=True,
        )
    except ValueError as exc:
        from urllib.parse import quote
        return RedirectResponse(url=f"/kassa?share_status=error&message={quote(str(exc))}", status_code=303)

    from urllib.parse import quote
    receipt_id = str(result.get('receipt_table_id') or '')
    duplicate_flag = '1' if result.get('duplicate') else '0'
    parse_status = quote(str(result.get('parse_status') or 'partial'))
    return RedirectResponse(
        url=f"/kassa?share_status=success&receipt_table_id={receipt_id}&duplicate={duplicate_flag}&parse_status={parse_status}",
        status_code=303,
    )


@app.post("/api/receipts/import")
async def import_receipt(
    household_id: str = Form(...),
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
):
    context = require_household_context(authorization, household_id)
    effective_household_id = str(context['active_household_id']).strip() or "1"
    ensure_default_receipt_sources(engine, RECEIPT_STORAGE_ROOT, effective_household_id)
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Leeg bestand")
    source_filename = file.filename or "receipt"
    source_id = f"{effective_household_id}-manual-upload"
    if _looks_like_zip_upload(source_filename, file.content_type, file_bytes):
        try:
            members = _extract_supported_receipts_from_zip(source_filename, file_bytes)
            batch = create_receipt_import_batch(effective_household_id, source_filename, len(members))
            start_receipt_zip_import_batch(str(batch.get('batch_id') or ''), effective_household_id, source_id, source_filename, members)
            response_payload = {
                'batch': True,
                'async': True,
                'batch_id': batch.get('batch_id'),
                'filename': source_filename,
                'file_count': int(batch.get('total_files') or 0),
                'processed_count': int(batch.get('processed_files') or 0),
                'imported_count': int(batch.get('imported_files') or 0),
                'duplicate_count': int(batch.get('duplicate_files') or 0),
                'failed_count': int(batch.get('failed_files') or 0),
                'percentage': int(batch.get('percentage') or 0),
                'status': batch.get('status') or 'queued',
            }
            return JSONResponse(status_code=202, content=response_payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            logger.exception('Onverwachte fout bij zip-bonimport voor household %s', effective_household_id)
            raise HTTPException(status_code=500, detail='Het zip-bestand kon niet volledig als batch worden verwerkt.') from exc
    try:
        result = import_uploaded_receipt_payload(
            household_id=effective_household_id,
            filename=source_filename,
            file_bytes=file_bytes,
            source_id=source_id,
            mime_type=file.content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception('Onverwachte fout bij handmatige bonimport voor household %s', effective_household_id)
        raise HTTPException(status_code=500, detail='De geplakte of gekozen inhoud kon niet volledig als kassabon worden verwerkt.') from exc
    status_code = 200 if result.get("duplicate") else 201
    return JSONResponse(status_code=status_code, content=result)


@app.get("/api/receipts/import-batches/{batch_id}")
def get_receipt_import_batch_status(batch_id: str, householdId: str = Query(...), authorization: Optional[str] = Header(None)):
    effective_household_id = resolve_authorized_household_id(authorization, householdId, require_authorization=True)
    batch = get_receipt_import_batch(batch_id)
    if not batch or str(batch.get('household_id') or '') != str(effective_household_id):
        raise HTTPException(status_code=404, detail='Onbekende receipt import batch')
    return batch


@app.post("/api/receipts/delete")
def delete_receipts(payload: ReceiptDeleteRequest, authorization: Optional[str] = Header(None)):
    receipt_ids = [str(value).strip() for value in (payload.receipt_table_ids or []) if str(value).strip()]
    if not receipt_ids:
        raise HTTPException(status_code=400, detail="receipt_table_ids is verplicht")
    placeholders = ", ".join([f":id_{idx}" for idx, _ in enumerate(receipt_ids)])
    params = {f"id_{idx}": value for idx, value in enumerate(receipt_ids)}
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT rt.id AS receipt_table_id, rt.raw_receipt_id, rt.household_id
                FROM receipt_tables rt
                WHERE rt.id IN ({placeholders})
                  AND rt.deleted_at IS NULL
                """
            ),
            params,
        ).mappings().all()
        if not rows:
            return {'deleted_receipt_table_ids': [], 'deleted_count': 0}
        household_ids = {str(row.get('household_id') or '') for row in rows}
        if len(household_ids) != 1:
            raise HTTPException(status_code=400, detail='Bonnen moeten uit hetzelfde huishouden komen')
        require_household_context(authorization, next(iter(household_ids)))
        deleted_receipt_ids = [str(row['receipt_table_id']) for row in rows]
        raw_ids = [str(row['raw_receipt_id']) for row in rows if row.get('raw_receipt_id')]
        receipt_params = {f"rid_{idx}": value for idx, value in enumerate(deleted_receipt_ids)}
        receipt_placeholders = ", ".join([f":rid_{idx}" for idx, _ in enumerate(deleted_receipt_ids)])
        conn.execute(text(f"UPDATE receipt_tables SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id IN ({receipt_placeholders})"), receipt_params)
        if raw_ids:
            raw_params = {f"raw_{idx}": value for idx, value in enumerate(raw_ids)}
            raw_placeholders = ", ".join([f":raw_{idx}" for idx, _ in enumerate(raw_ids)])
            conn.execute(text(f"UPDATE raw_receipts SET deleted_at = CURRENT_TIMESTAMP, sha256_hash = sha256_hash || ':deleted:' || id || ':' || strftime('%s','now') WHERE id IN ({raw_placeholders})"), raw_params)
    return {'deleted_receipt_table_ids': deleted_receipt_ids, 'deleted_count': len(deleted_receipt_ids)}


@app.get("/api/receipt-sources")
def list_receipt_sources(householdId: str = Query(...), authorization: Optional[str] = Header(None)):
    effective_household_id = resolve_authorized_household_id(authorization, householdId, require_authorization=True)
    return {'items': list_receipt_sources_for_household(effective_household_id)}


@app.post("/api/receipt-sources")
def register_receipt_source(payload: ReceiptSourceCreateRequest, authorization: Optional[str] = Header(None)):
    context = require_household_admin_context(authorization, payload.household_id)
    payload.household_id = str(context['active_household_id'])
    return create_receipt_source(payload)


@app.get("/api/receipt-sources/email-route")
def get_receipt_email_route(householdId: str = Query(...), authorization: Optional[str] = Header(None)):
    effective_household_id = resolve_authorized_household_id(authorization, householdId, require_authorization=True)
    return ensure_household_email_source(effective_household_id)




@app.post("/api/receipts/inbound")
async def receive_receipt_inbound_email(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail='De inbound webhook bevat geen geldige JSON-payload.')
    result = import_resend_inbound_event(payload if isinstance(payload, dict) else {})
    return result

@app.get("/api/receipt-sources/gmail-status")
def get_receipt_gmail_status(householdId: str = Query(...), authorization: Optional[str] = Header(None)):
    effective_household_id = resolve_authorized_household_id(authorization, householdId, require_authorization=True)
    status = get_receipt_gmail_account(effective_household_id, create_if_missing=True)
    status['gmail_route_address'] = build_household_email_address(effective_household_id)
    status['configured'] = gmail_is_configured()
    return status


@app.get("/api/receipts/gmail/connect-url")
def get_receipt_gmail_connect_url(
    request: Request,
    householdId: str = Query(...),
    frontendOrigin: str = Query(''),
    authorization: Optional[str] = Header(None),
):
    if not gmail_is_configured():
        raise HTTPException(status_code=503, detail='De Gmail-koppeling is nog niet geconfigureerd in Rezzerv. Voeg eerst Google OAuth clientgegevens toe.')
    effective_household_id = resolve_authorized_household_id(authorization, householdId, require_authorization=True)
    redirect_uri = resolve_gmail_redirect_uri(request)
    return {
        'configured': True,
        'authorization_url': build_gmail_connect_url(effective_household_id, redirect_uri, frontend_origin=frontendOrigin),
        'redirect_uri': redirect_uri,
        'label_name': GMAIL_DEFAULT_LABEL_NAME,
    }


@app.get("/api/receipts/gmail/callback")
def handle_receipt_gmail_callback(
    request: Request,
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
):
    state_payload = verify_gmail_state(state or '')
    frontend_origin = str(state_payload.get('frontend_origin') or '').strip() or '*'

    def render_popup(status: str, message: str, connected_email: str | None = None):
        payload = {
            'type': 'rezzerv-gmail-oauth',
            'status': status,
            'message': message,
            'connected_email': connected_email,
        }
        message_text = html.escape(message)
        return HTMLResponse(
            content=f"""
<!doctype html>
<html lang="nl">
  <head>
    <meta charset="utf-8" />
    <title>Rezzerv Gmail koppeling</title>
  </head>
  <body>
    <p>{message_text}</p>
    <script>
      (function() {{
        var payload = JSON.parse({json.dumps(json.dumps(payload))});
        if (window.opener && window.opener.postMessage) {{
          try {{
            window.opener.postMessage(payload, {json.dumps(frontend_origin)});
          }} catch (error) {{
            window.opener.postMessage(payload, '*');
          }}
        }}
        window.setTimeout(function() {{ window.close(); }}, 200);
      }})();
    </script>
  </body>
</html>
""",
            media_type='text/html',
        )

    if error:
        message = normalize_api_error_message(error_description or error, 'Google OAuth werd geannuleerd.')
        upsert_receipt_gmail_account(str(state_payload.get('household_id') or '1'), {'sync_status': 'error', 'last_error': message})
        return render_popup('error', message)
    if not code:
        return render_popup('error', 'Google OAuth leverde geen autorisatiecode op.')

    redirect_uri = resolve_gmail_redirect_uri(request)
    tokens = exchange_gmail_code_for_tokens(code, redirect_uri)
    effective_household_id = str(state_payload.get('household_id') or '1').strip() or '1'
    account = upsert_receipt_gmail_account(
        effective_household_id,
        {
            'access_token': tokens.get('access_token'),
            'refresh_token': tokens.get('refresh_token'),
            'token_expires_at': parse_gmail_token_expiry(tokens.get('expires_in')),
            'sync_status': 'connected',
            'last_error': None,
            'label_name': GMAIL_DEFAULT_LABEL_NAME,
        },
    )
    profile, _ = gmail_get_profile(account)
    connected_email = str(profile.get('emailAddress') or '').strip() or None
    account = upsert_receipt_gmail_account(
        effective_household_id,
        {
            'google_email': connected_email,
            'google_user_sub': account.get('google_user_sub'),
            'sync_status': 'connected',
            'last_error': None,
        },
    )
    label_id, _ = ensure_gmail_label(account)
    upsert_receipt_gmail_account(effective_household_id, {'label_id': label_id, 'sync_status': 'connected', 'last_error': None})
    return render_popup('success', 'Gmail is gekoppeld aan Rezzerv.', connected_email=connected_email)


@app.post("/api/receipts/gmail/sync")
def sync_receipt_gmail_mailbox(householdId: str = Query(...), authorization: Optional[str] = Header(None)):
    context = require_household_admin_context(authorization, householdId)
    effective_household_id = str(context['active_household_id'])
    result = sync_gmail_receipts(effective_household_id)
    return result


@app.post("/api/receipts/email-import")
async def import_email_receipt(
    household_id: str = Form(...),
    email_file: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
):
    context = require_household_admin_context(authorization, household_id)
    effective_household_id = str(context['active_household_id']).strip() or '1'
    email_bytes = await email_file.read()
    if not email_bytes:
        raise HTTPException(status_code=400, detail='Het e-mailbestand is leeg.')
    try:
        result = import_email_receipt_payload(effective_household_id, email_bytes, fallback_filename=email_file.filename or 'receipt.eml')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    status_code = 200 if result.get('duplicate') else 201
    return JSONResponse(status_code=status_code, content=result)


@app.post("/api/receipts/source-scan")
def source_scan_receipts(payload: ReceiptSourceScanRequest, authorization: Optional[str] = Header(None)):
    source_id = (payload.source_id or "").strip()
    if not source_id:
        raise HTTPException(status_code=400, detail="source_id is verplicht")
    with engine.begin() as conn:
        require_entity_household_access(conn, "receipt_sources", source_id, authorization, admin_only=True)
    try:
        result = scan_receipt_source(engine, RECEIPT_STORAGE_ROOT, source_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Onbekende receipt-bron")
    return result


@app.get("/api/unpack-start-batches")
def list_unpack_start_batches(householdId: str = Query(...), authorization: Optional[str] = Header(None)):
    effective_household_id = resolve_authorized_household_id(authorization, householdId, require_authorization=True)
    ensure_default_receipt_sources(engine, RECEIPT_STORAGE_ROOT, effective_household_id)
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    rt.id AS receipt_table_id,
                    rt.household_id,
                    rt.store_name,
                    rt.store_branch,
                    rt.purchase_at,
                    rt.total_amount,
                    rt.discount_total,
                    rt.reference,
                    rt.notes,
                    rt.approved_at,
                    rt.approved_by_user_email,
                    COALESCE(rt.totals_overridden, 0) AS totals_overridden,
                    rt.totals_override_by_user_email,
                    rt.totals_override_at,
                    rt.currency,
                    rt.parse_status,
                    COALESCE((
                        SELECT COUNT(*)
                        FROM receipt_table_lines rtl_count
                        WHERE rtl_count.receipt_table_id = rt.id
                          AND COALESCE(rtl_count.is_deleted, 0) = 0
                    ), rt.line_count, 0) AS line_count,
                    COALESCE(rs.label, 'Manual upload') AS source_label,
                    rr.sha256_hash,
                    rt.created_at,
                    COALESCE((
                        SELECT SUM(COALESCE(COALESCE(rtl.corrected_line_total, rtl.line_total), 0))
                        FROM receipt_table_lines rtl
                        WHERE rtl.receipt_table_id = rt.id
                          AND COALESCE(rtl.is_deleted, 0) = 0
                    ), 0) AS line_total_sum,
                    COALESCE(rt.discount_total, 0) AS discount_total_effective,
                    COALESCE((
                        SELECT SUM(COALESCE(COALESCE(rtl.corrected_line_total, rtl.line_total), 0))
                        FROM receipt_table_lines rtl
                        WHERE rtl.receipt_table_id = rt.id
                    ), 0) + COALESCE(rt.discount_total, 0) AS net_line_total_sum
                FROM receipt_tables rt
                JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                LEFT JOIN receipt_sources rs ON rs.id = rr.source_id
                WHERE rt.household_id = :household_id
                  AND rt.deleted_at IS NULL
                  AND rr.deleted_at IS NULL
                ORDER BY COALESCE(rt.purchase_at, rt.created_at) DESC, rt.created_at DESC, rt.id DESC
                """
            ),
            {'household_id': effective_household_id},
        ).mappings().all()

        def normalize_key_part(value):
            return re.sub(r'\s+', ' ', str(value or '').strip().lower())

        items = []
        seen_keys = set()
        for row in rows:
            serialized = serialize_receipt_row(dict(row))
            store_name = normalize_key_part(serialized.get('store_name'))
            purchase_at = normalize_key_part(serialized.get('purchase_at'))
            total_amount = serialized.get('total_amount')
            try:
                total_key = f"{float(total_amount):.2f}" if total_amount is not None else ''
            except Exception:
                total_key = normalize_key_part(total_amount)
            line_count = str(serialized.get('line_count') or 0)
            source_label = normalize_key_part(serialized.get('source_label'))
            sha_key = normalize_key_part(serialized.get('sha256_hash'))
            fingerprint_key = (store_name, purchase_at, total_key, line_count, source_label)
            dedupe_key = sha_key or '|'.join(fingerprint_key)
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)

            inbox_status = derive_unpack_receipt_status(serialized)
            if inbox_status not in {'Gecontroleerd', 'Controle nodig'}:
                continue

            batch_id = ensure_unpack_batch_for_receipt(conn, serialized)
            purchase_at_value = serialized.get('purchase_at') or serialized.get('created_at') or ''
            purchase_label = str(purchase_at_value)[:10] if purchase_at_value else '-'
            store_label = serialized.get('store_name') or serialized.get('store_branch') or serialized.get('source_label') or 'Kassabon'
            items.append({
                'batch_id': batch_id,
                'receipt_table_id': serialized.get('receipt_table_id'),
                'store_provider_code': 'receipt',
                'store_provider_name': store_label,
                'purchase_date': purchase_label,
                'created_at': serialized.get('created_at'),
                'summary': {'total': int(serialized.get('line_count') or 0)},
                'inbox_status': inbox_status,
            })

    items.sort(key=lambda item: str(item.get('created_at') or ''), reverse=True)
    return {'items': items}


@app.get("/api/receipts")
def list_receipts(householdId: str = Query(...), authorization: Optional[str] = Header(None)):
    effective_household_id = resolve_authorized_household_id(authorization, householdId, require_authorization=True)
    ensure_default_receipt_sources(engine, RECEIPT_STORAGE_ROOT, effective_household_id)
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    rt.id AS receipt_table_id,
                    rt.raw_receipt_id,
                    rt.store_name,
                    rt.store_branch,
                    rt.purchase_at,
                    rt.total_amount,
                    rt.discount_total,
                    rt.reference,
                    rt.notes,
                    rt.approved_at,
                    rt.approved_by_user_email,
                    rt.currency,
                    rt.parse_status,
                    COALESCE((
                        SELECT COUNT(*)
                        FROM receipt_table_lines rtl_count
                        WHERE rtl_count.receipt_table_id = rt.id
                          AND COALESCE(rtl_count.is_deleted, 0) = 0
                    ), rt.line_count, 0) AS line_count,
                    COALESCE(rs.label, 'Manual upload') AS source_label,
                    rem.sender_email,
                    rem.sender_name,
                    rem.subject AS email_subject,
                    rem.received_at AS email_received_at,
                    rr.original_filename,
                    rr.sha256_hash,
                    rt.created_at,
                    COALESCE((
                        SELECT SUM(COALESCE(COALESCE(rtl.corrected_line_total, rtl.line_total), 0))
                        FROM receipt_table_lines rtl
                        WHERE rtl.receipt_table_id = rt.id
                          AND COALESCE(rtl.is_deleted, 0) = 0
                    ), 0) AS line_total_sum,
                    COALESCE(rt.discount_total, 0) AS discount_total_effective,
                    COALESCE((
                        SELECT SUM(COALESCE(COALESCE(rtl.corrected_line_total, rtl.line_total), 0))
                        FROM receipt_table_lines rtl
                        WHERE rtl.receipt_table_id = rt.id
                    ), 0) + COALESCE(rt.discount_total, 0) AS net_line_total_sum
                FROM receipt_tables rt
                JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                LEFT JOIN receipt_sources rs ON rs.id = rr.source_id
                LEFT JOIN receipt_email_messages rem ON rem.raw_receipt_id = rr.id
                WHERE rt.household_id = :household_id
                  AND rt.deleted_at IS NULL
                  AND rr.deleted_at IS NULL
                ORDER BY COALESCE(rt.purchase_at, rt.created_at) DESC, rt.created_at DESC, rt.id DESC
                """
            ),
            {"household_id": effective_household_id},
        ).mappings().all()

    def normalize_key_part(value):
        return re.sub(r'\s+', ' ', str(value or '').strip().lower())

    deduped_items = []
    seen_keys = set()
    for row in rows:
        store_name = normalize_key_part(row.get('store_name'))
        purchase_at = normalize_key_part(row.get('purchase_at'))
        total_amount = row.get('total_amount')
        try:
            total_key = f"{float(total_amount):.2f}" if total_amount is not None else ''
        except Exception:
            total_key = normalize_key_part(total_amount)
        line_count = str(row.get('line_count') or 0)
        source_label = normalize_key_part(row.get('source_label'))
        sha_key = normalize_key_part(row.get('sha256_hash'))
        fingerprint_key = (store_name, purchase_at, total_key, line_count, source_label)
        dedupe_key = sha_key or '|'.join(fingerprint_key)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        serialized = serialize_receipt_row(dict(row))
        serialized['inbox_status'] = derive_unpack_receipt_status(serialized)
        serialized.pop('original_filename', None)
        serialized.pop('sha256_hash', None)
        deduped_items.append(serialized)
    return {"items": deduped_items}


@app.get("/api/receipts/{receipt_table_id}/preview")
def get_receipt_preview(receipt_table_id: str, authorization: Optional[str] = Header(None)):
    with engine.begin() as conn:
        require_entity_household_access(conn, "receipt_tables", receipt_table_id, authorization, admin_only=False)
        record = conn.execute(
            text(
                """
                SELECT
                    rt.id AS receipt_table_id,
                    rr.original_filename,
                    rr.mime_type,
                    rr.storage_path,
                    rem.body_html,
                    rem.body_text,
                    rem.selected_part_type
                FROM receipt_tables rt
                JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                LEFT JOIN receipt_email_messages rem ON rem.raw_receipt_id = rr.id
                WHERE rt.id = :receipt_table_id
                  AND rt.deleted_at IS NULL
                  AND rr.deleted_at IS NULL
                LIMIT 1
                """
            ),
            {"receipt_table_id": receipt_table_id},
        ).mappings().first()
    if not record:
        raise HTTPException(status_code=404, detail="Bon niet gevonden")

    selected_part_type = str(record.get("selected_part_type") or "").strip().lower()
    body_html = record.get("body_html")
    body_text = record.get("body_text")
    if selected_part_type in {"html_body", "text_body"} and body_html:
        return HTMLResponse(content=str(body_html), headers={"Content-Disposition": "inline"})
    if selected_part_type == "text_body" and body_text:
        return Response(content=str(body_text), media_type="text/plain", headers={"Content-Disposition": "inline"})

    storage_path = Path(record["storage_path"] or "")
    if not storage_path.exists() or not storage_path.is_file():
        raise HTTPException(status_code=404, detail="Originele bon ontbreekt")

    try:
        storage_path.resolve().relative_to(RECEIPT_STORAGE_ROOT.resolve())
    except Exception:
        raise HTTPException(status_code=403, detail="Bonbestand ligt buiten de toegestane opslag")

    mime_type = str(record["mime_type"] or "application/octet-stream")
    filename = str(record["original_filename"] or storage_path.name)
    headers = {"Content-Disposition": f'inline; filename="{Path(filename).name}"'}
    return FileResponse(path=storage_path, media_type=mime_type, filename=Path(filename).name, headers=headers)


@app.get("/api/receipts/{receipt_table_id}")
def get_receipt_detail(receipt_table_id: str, authorization: Optional[str] = Header(None)):
    with engine.begin() as conn:
        require_entity_household_access(conn, "receipt_tables", receipt_table_id, authorization, admin_only=False)
        header = conn.execute(
            text(
                """
                SELECT
                    rt.id,
                    rt.raw_receipt_id,
                    rt.store_name,
                    rt.store_branch,
                    rt.purchase_at,
                    rt.total_amount,
                    rt.discount_total,
                    rt.reference,
                    rt.notes,
                    rt.approved_at,
                    rt.approved_by_user_email,
                    rt.currency,
                    rt.parse_status,
                    rt.confidence_score,
                    COALESCE((
                        SELECT COUNT(*)
                        FROM receipt_table_lines rtl_count
                        WHERE rtl_count.receipt_table_id = rt.id
                          AND COALESCE(rtl_count.is_deleted, 0) = 0
                    ), rt.line_count, 0) AS line_count,
                    rt.created_at,
                    rt.updated_at,
                    COALESCE(rs.label, 'Manual upload') AS source_label,
                    rr.original_filename,
                    rr.mime_type,
                    rr.imported_at,
                    rem.sender_email,
                    rem.sender_name,
                    rem.subject AS email_subject,
                    rem.received_at AS email_received_at,
                    rem.selected_part_type,
                    rem.selected_filename AS email_selected_filename,
                    rem.selected_mime_type AS email_selected_mime_type,
                    COALESCE((
                        SELECT SUM(COALESCE(COALESCE(rtl.corrected_line_total, rtl.line_total), 0))
                        FROM receipt_table_lines rtl
                        WHERE rtl.receipt_table_id = rt.id
                          AND COALESCE(rtl.is_deleted, 0) = 0
                    ), 0) AS line_total_sum,
                    COALESCE(rt.discount_total, 0) AS discount_total_effective,
                    COALESCE((
                        SELECT SUM(COALESCE(COALESCE(rtl.corrected_line_total, rtl.line_total), 0))
                        FROM receipt_table_lines rtl
                        WHERE rtl.receipt_table_id = rt.id
                    ), 0) + COALESCE(rt.discount_total, 0) AS net_line_total_sum
                FROM receipt_tables rt
                JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                LEFT JOIN receipt_sources rs ON rs.id = rr.source_id
                LEFT JOIN receipt_email_messages rem ON rem.raw_receipt_id = rr.id
                WHERE rt.id = :receipt_table_id
                  AND rt.deleted_at IS NULL
                  AND rr.deleted_at IS NULL
                LIMIT 1
                """
            ),
            {"receipt_table_id": receipt_table_id},
        ).mappings().first()
        if not header:
            raise HTTPException(status_code=404, detail="Receipt table niet gevonden")
        lines = conn.execute(
            text(
                """
                SELECT
                    id,
                    line_index,
                    raw_label,
                    corrected_raw_label,
                    COALESCE(corrected_raw_label, raw_label) AS display_label,
                    normalized_label,
                    quantity,
                    corrected_quantity,
                    COALESCE(corrected_quantity, quantity) AS display_quantity,
                    unit,
                    corrected_unit,
                    COALESCE(corrected_unit, unit) AS display_unit,
                    unit_price,
                    corrected_unit_price,
                    COALESCE(corrected_unit_price, unit_price) AS display_unit_price,
                    line_total,
                    corrected_line_total,
                    COALESCE(corrected_line_total, line_total) AS display_line_total,
                    discount_amount,
                    barcode,
                    article_match_status,
                    matched_article_id,
                    matched_global_product_id,
                    confidence_score,
                    COALESCE(is_deleted, 0) AS is_deleted,
                    COALESCE(is_validated, 0) AS is_validated
                FROM receipt_table_lines
                WHERE receipt_table_id = :receipt_table_id
                ORDER BY line_index ASC, created_at ASC
                """
            ),
            {"receipt_table_id": receipt_table_id},
        ).mappings().all()
    payload = serialize_receipt_row(dict(header))
    payload['inbox_status'] = derive_unpack_receipt_status(payload)
    payload["lines"] = [serialize_receipt_row(dict(line)) for line in lines]
    return payload




@app.patch("/api/receipts/{receipt_table_id}")
def update_receipt_header(receipt_table_id: str, payload: ReceiptHeaderUpdateRequest, authorization: Optional[str] = Header(None)):
    with engine.begin() as conn:
        context = require_receipt_write_context(conn, receipt_table_id, authorization)
        current = conn.execute(
            text("SELECT id, store_name, purchase_at, total_amount, reference, notes, currency FROM receipt_tables WHERE id = :id LIMIT 1"),
            {'id': receipt_table_id},
        ).mappings().first()
        if not current:
            raise HTTPException(status_code=404, detail='Bon niet gevonden')
        values = {
            'store_name': current.get('store_name'),
            'purchase_at': current.get('purchase_at'),
            'total_amount': current.get('total_amount'),
            'reference': current.get('reference'),
            'notes': current.get('notes'),
        }
        if payload.store_name is not None:
            values['store_name'] = ' '.join(str(payload.store_name or '').strip().split()) or None
        if payload.purchase_at is not None:
            values['purchase_at'] = str(payload.purchase_at or '').strip() or None
        if payload.total_amount is not None:
            values['total_amount'] = float(payload.total_amount)
        if payload.reference is not None:
            values['reference'] = str(payload.reference or '').strip() or None
        if payload.notes is not None:
            values['notes'] = str(payload.notes or '').strip() or None
        conn.execute(
            text("""
            UPDATE receipt_tables
            SET store_name = :store_name,
                purchase_at = :purchase_at,
                total_amount = :total_amount,
                reference = :reference,
                notes = :notes,
                corrected_by_user_email = :user_email,
                reviewed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
            """),
            {**values, 'id': receipt_table_id, 'user_email': str(context.get('email') or '').strip().lower()},
        )
        recompute_receipt_review_state(conn, receipt_table_id)
    return get_receipt_detail(receipt_table_id, authorization)


@app.patch("/api/receipts/{receipt_table_id}/lines/{line_id}")
def update_receipt_line(receipt_table_id: str, line_id: str, payload: ReceiptLineUpdateRequest, authorization: Optional[str] = Header(None)):
    with engine.begin() as conn:
        context = require_receipt_write_context(conn, receipt_table_id, authorization)
        row = conn.execute(
            text("SELECT id, receipt_table_id, raw_label, normalized_label, quantity, unit, unit_price, line_total, matched_article_id, matched_global_product_id, COALESCE(is_deleted, 0) AS is_deleted, COALESCE(is_validated, 0) AS is_validated FROM receipt_table_lines WHERE id = :id AND receipt_table_id = :receipt_table_id LIMIT 1"),
            {'id': line_id, 'receipt_table_id': receipt_table_id},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail='Bonregel niet gevonden')
        normalized_article_name = None if payload.article_name is None else (' '.join(str(payload.article_name or '').strip().split()) or None)
        values = {
            'raw_label': row.get('raw_label') if payload.article_name is None else normalized_article_name,
            'normalized_label': row.get('normalized_label') if payload.article_name is None else (normalize_household_article_name(normalized_article_name).lower() if normalized_article_name else None),
            'corrected_raw_label': normalized_article_name,
            'corrected_quantity': row.get('quantity') if payload.quantity is None else float(payload.quantity),
            'corrected_unit': row.get('unit') if payload.unit is None else (str(payload.unit or '').strip() or None),
            'corrected_unit_price': row.get('unit_price') if payload.unit_price is None else float(payload.unit_price),
            'corrected_line_total': row.get('line_total') if payload.line_total is None else float(payload.line_total),
            'matched_article_id': row.get('matched_article_id') if payload.matched_article_id is None else (str(payload.matched_article_id or '').strip() or None),
            'is_deleted': int(bool(row.get('is_deleted'))) if payload.is_deleted is None else int(bool(payload.is_deleted)),
            'is_validated': int(bool(row.get('is_validated'))) if payload.is_validated is None else int(bool(payload.is_validated)),
        }
        conn.execute(
            text("""
            UPDATE receipt_table_lines
            SET raw_label = :raw_label,
                normalized_label = :normalized_label,
                corrected_raw_label = :corrected_raw_label,
                corrected_quantity = :corrected_quantity,
                corrected_unit = :corrected_unit,
                corrected_unit_price = :corrected_unit_price,
                corrected_line_total = :corrected_line_total,
                matched_article_id = :matched_article_id,
                is_deleted = :is_deleted,
                is_validated = :is_validated,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id AND receipt_table_id = :receipt_table_id
            """),
            {**values, 'id': line_id, 'receipt_table_id': receipt_table_id},
        )
        conn.execute(text("UPDATE receipt_tables SET corrected_by_user_email = :user_email, reviewed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = :id"), {'id': receipt_table_id, 'user_email': str(context.get('email') or '').strip().lower()})
        sync_receipt_table_line_product_links(conn, receipt_table_id, line_id, create_global_product=True, create_household_article=False)
        recompute_receipt_review_state(conn, receipt_table_id)
        receipt_header = conn.execute(
            text("""
            SELECT id AS receipt_table_id, household_id, store_name, store_branch, purchase_at, created_at, currency
            FROM receipt_tables
            WHERE id = :id
            LIMIT 1
            """),
            {'id': receipt_table_id},
        ).mappings().first()
        if receipt_header:
            ensure_unpack_batch_for_receipt(conn, dict(receipt_header))
    return get_receipt_detail(receipt_table_id, authorization)


@app.post("/api/receipts/{receipt_table_id}/lines")
def create_receipt_line(receipt_table_id: str, payload: ReceiptLineCreateRequest, authorization: Optional[str] = Header(None)):
    with engine.begin() as conn:
        context = require_receipt_write_context(conn, receipt_table_id, authorization)
        existing = conn.execute(text("SELECT id FROM receipt_tables WHERE id = :id LIMIT 1"), {'id': receipt_table_id}).mappings().first()
        if not existing:
            raise HTTPException(status_code=404, detail='Bon niet gevonden')
        next_index = conn.execute(text("SELECT COALESCE(MAX(line_index), 0) + 1 AS next_index FROM receipt_table_lines WHERE receipt_table_id = :receipt_table_id"), {'receipt_table_id': receipt_table_id}).scalar()
        quantity = float(payload.quantity if payload.quantity is not None else 1.0)
        unit_price = float(payload.unit_price) if payload.unit_price is not None else None
        line_total = float(payload.line_total) if payload.line_total is not None else (round(quantity * unit_price, 2) if unit_price is not None else None)
        conn.execute(
            text("""
            INSERT INTO receipt_table_lines (
                id, receipt_table_id, line_index, raw_label, corrected_raw_label, normalized_label,
                quantity, corrected_quantity, unit, corrected_unit, unit_price, corrected_unit_price,
                line_total, corrected_line_total, article_match_status, matched_article_id, matched_global_product_id,
                confidence_score, is_deleted, is_validated, created_at, updated_at
            ) VALUES (
                :id, :receipt_table_id, :line_index, :raw_label, :corrected_raw_label, :normalized_label,
                :quantity, :corrected_quantity, :unit, :corrected_unit, :unit_price, :corrected_unit_price,
                :line_total, :corrected_line_total, 'manual', :matched_article_id, NULL,
                1.0, 0, :is_validated, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """),
            {
                'id': str(uuid.uuid4()),
                'receipt_table_id': receipt_table_id,
                'line_index': int(next_index or 1),
                'raw_label': payload.article_name,
                'corrected_raw_label': payload.article_name,
                'normalized_label': payload.article_name.lower(),
                'quantity': quantity,
                'corrected_quantity': quantity,
                'unit': payload.unit,
                'corrected_unit': payload.unit,
                'unit_price': unit_price,
                'corrected_unit_price': unit_price,
                'line_total': line_total,
                'corrected_line_total': line_total,
                'matched_article_id': (str(payload.matched_article_id or '').strip() or None),
                'is_validated': int(bool(payload.is_validated)),
            },
        )
        conn.execute(text("UPDATE receipt_tables SET corrected_by_user_email = :user_email, reviewed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = :id"), {'id': receipt_table_id, 'user_email': str(context.get('email') or '').strip().lower()})
        inserted_line_id = conn.execute(text("SELECT id FROM receipt_table_lines WHERE receipt_table_id = :receipt_table_id ORDER BY line_index DESC, created_at DESC, id DESC LIMIT 1"), {'receipt_table_id': receipt_table_id}).scalar()
        if inserted_line_id:
            sync_receipt_table_line_product_links(conn, receipt_table_id, str(inserted_line_id), create_global_product=True, create_household_article=False)
        recompute_receipt_review_state(conn, receipt_table_id)
    return get_receipt_detail(receipt_table_id, authorization)


@app.post("/api/receipts/{receipt_table_id}/approve")
def approve_receipt_table(receipt_table_id: str, authorization: Optional[str] = Header(None)):
    with engine.begin() as conn:
        context = require_receipt_write_context(conn, receipt_table_id, authorization)
        header = conn.execute(
            text("SELECT id, store_name, purchase_at, total_amount FROM receipt_tables WHERE id = :id LIMIT 1"),
            {'id': receipt_table_id},
        ).mappings().first()
        if not header:
            raise HTTPException(status_code=404, detail='Bon niet gevonden')
        store_name = str(header.get('store_name') or '').strip()
        purchase_at = str(header.get('purchase_at') or '').strip()
        if not store_name:
            raise HTTPException(status_code=400, detail='Winkel is verplicht voordat je de bon kunt goedkeuren')
        if not purchase_at:
            raise HTTPException(status_code=400, detail='Aankoopdatum is verplicht voordat je de bon kunt goedkeuren')
        valid_line_count = conn.execute(
            text("""
            SELECT COUNT(*)
            FROM receipt_table_lines
            WHERE receipt_table_id = :receipt_table_id
              AND COALESCE(is_deleted, 0) = 0
              AND TRIM(COALESCE(corrected_raw_label, raw_label, '')) <> ''
            """),
            {'receipt_table_id': receipt_table_id},
        ).scalar()
        if int(valid_line_count or 0) < 1:
            raise HTTPException(status_code=400, detail='Voeg minimaal één geldige bonregel toe voordat je goedkeurt')
        line_total_sum = conn.execute(
            text("SELECT COALESCE(SUM(COALESCE(corrected_line_total, line_total, 0)), 0) FROM receipt_table_lines WHERE receipt_table_id = :receipt_table_id AND COALESCE(is_deleted, 0) = 0"),
            {'receipt_table_id': receipt_table_id},
        ).scalar()
        discount_total = conn.execute(
            text("SELECT COALESCE(discount_total, 0) FROM receipt_tables WHERE id = :receipt_table_id LIMIT 1"),
            {'receipt_table_id': receipt_table_id},
        ).scalar()
        total_amount = header.get('total_amount')
        user_email = str(context.get('email') or '').strip().lower()
        totals_match = True
        if total_amount is not None:
            try:
                totals_match = abs(float(total_amount) - (float(line_total_sum or 0) + float(discount_total or 0))) < 0.01
            except Exception:
                totals_match = False
        next_status = 'approved' if totals_match else 'approved_override'
        conn.execute(
            text("""
            UPDATE receipt_tables
            SET parse_status = :parse_status,
                line_count = :line_count,
                approved_by_user_email = :user_email,
                approved_at = CURRENT_TIMESTAMP,
                corrected_by_user_email = :user_email,
                reviewed_at = CURRENT_TIMESTAMP,
                totals_overridden = :totals_overridden,
                totals_override_by_user_email = CASE WHEN :totals_overridden = 1 THEN :user_email ELSE NULL END,
                totals_override_at = CASE WHEN :totals_overridden = 1 THEN CURRENT_TIMESTAMP ELSE NULL END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
            """),
            {
                'id': receipt_table_id,
                'line_count': int(valid_line_count or 0),
                'user_email': user_email,
                'parse_status': next_status,
                'totals_overridden': 0 if totals_match else 1,
            },
        )
        line_ids = [
            str(row[0])
            for row in conn.execute(
                text("SELECT id FROM receipt_table_lines WHERE receipt_table_id = :receipt_table_id AND COALESCE(is_deleted, 0) = 0 ORDER BY line_index ASC, created_at ASC"),
                {'receipt_table_id': receipt_table_id},
            ).fetchall()
            if row[0]
        ]
        for current_line_id in line_ids:
            sync_receipt_table_line_product_links(conn, receipt_table_id, current_line_id, create_global_product=True, create_household_article=False)
        receipt_header = conn.execute(
            text("""
            SELECT id AS receipt_table_id, household_id, store_name, store_branch, purchase_at, created_at, currency
            FROM receipt_tables
            WHERE id = :id
            LIMIT 1
            """),
            {'id': receipt_table_id},
        ).mappings().first()
        if receipt_header:
            ensure_unpack_batch_for_receipt(conn, dict(receipt_header))
    return get_receipt_detail(receipt_table_id, authorization)


@app.post("/api/receipts/{receipt_table_id}/reparse")
def reparse_receipt_table(receipt_table_id: str, authorization: Optional[str] = Header(None)):
    with engine.begin() as conn:
        require_entity_household_access(conn, "receipt_tables", receipt_table_id, authorization, admin_only=True)
    result = reparse_receipt(engine, RECEIPT_STORAGE_ROOT, receipt_table_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Receipt table niet gevonden")
    return result


@app.post("/api/receipts/reparse-suspicious")
def reparse_suspicious_receipts(householdId: str = Query(...), limit: int = Query(25, ge=1, le=100), authorization: Optional[str] = Header(None)):
    context = require_household_admin_context(authorization, householdId)
    effective_household_id = str(context['active_household_id'])
    ensure_default_receipt_sources(engine, RECEIPT_STORAGE_ROOT, effective_household_id)
    return repair_receipts_for_household(engine, RECEIPT_STORAGE_ROOT, effective_household_id, limit=limit)


@app.post("/api/auth/login")
def login(payload: LoginRequest):
    normalized_email = str(payload.email or '').strip().lower()
    user = get_user_record(normalized_email)

    if user and user["password"] == payload.password:
        household = ensure_household(normalized_email)
        effective_household_id = str(household.get("id") or "1")
        ensure_default_receipt_sources(engine, RECEIPT_STORAGE_ROOT, effective_household_id)
        dedupe_receipts_for_household(engine, effective_household_id)

        return {
            "token": build_auth_token(normalized_email),
            "user": {"email": normalized_email, "role": user.get("role", "member")}
        }

    raise HTTPException(status_code=401, detail="Ongeldige inloggegevens")


@app.get("/api/auth/context")
def get_auth_context(authorization: Optional[str] = Header(None), householdId: Optional[str] = Query(None)):
    context = require_household_context(authorization, householdId)
    with engine.begin() as conn:
        capability_payload = build_capabilities_payload(conn, context)
    return {**context, **capability_payload}


@app.get("/api/auth/capabilities")
def get_auth_capabilities(authorization: Optional[str] = Header(None), householdId: Optional[str] = Query(None)):
    context = require_household_context(authorization, householdId)
    with engine.begin() as conn:
        return build_capabilities_payload(conn, context)


@app.get("/api/household")
def get_household(authorization: Optional[str] = Header(None)):
    user = get_current_user_from_authorization(authorization)
    household = get_household_payload_for_user(user)
    with engine.begin() as conn:
        household["store_import_simplification_level"] = get_household_store_import_simplification_level(conn, household["id"])
    return household


@app.get("/api/household/members")
def get_household_members(authorization: Optional[str] = Header(None), householdId: Optional[str] = Query(None)):
    context = require_household_context(authorization, householdId)
    household_id = str(context['active_household_id'])
    current_email = str(context.get('email') or '').strip().lower()
    with engine.begin() as conn:
        payload = build_household_members_payload(conn, household_id, current_email)
        capability_payload = build_capabilities_payload(conn, context)
    payload['is_household_admin'] = context['display_role'] == 'admin'
    payload['current_user_email'] = current_email
    payload['current_user_display_role'] = context['display_role']
    payload['permissions'] = capability_payload['permissions']
    payload['member_permission_policies'] = capability_payload['member_permission_policies']
    payload['supported_permissions'] = capability_payload['supported_permissions']
    payload['can_manage_member_permissions'] = capability_payload['can_manage_member_permissions']
    return payload


@app.get("/api/household/role-audit")
def get_household_role_audit(authorization: Optional[str] = Header(None), householdId: Optional[str] = Query(None)):
    context = require_household_context(authorization, householdId)
    household_id = str(context['active_household_id'])
    with engine.begin() as conn:
        return {
            'household_id': household_id,
            'role_change_audit': list_household_role_change_audit(conn, household_id),
        }


@app.put("/api/household/permissions/{permission_key:path}")
def update_household_permission_policy(permission_key: str, payload: HouseholdPermissionPolicyUpdateRequest, authorization: Optional[str] = Header(None)):
    context = require_household_admin_context(authorization)
    household_id = str(context['active_household_id'])
    current_email = str(context.get('email') or '').strip().lower()
    normalized_permission_key = normalize_permission_key(permission_key)
    with engine.begin() as conn:
        set_household_member_permission_policy(conn, household_id, normalized_permission_key, payload.member_allowed)
        payload_result = build_household_members_payload(conn, household_id, current_email)
        capability_payload = build_capabilities_payload(conn, context)
    payload_result['is_household_admin'] = True
    payload_result['current_user_email'] = current_email
    payload_result['current_user_display_role'] = context['display_role']
    payload_result['permissions'] = capability_payload['permissions']
    payload_result['member_permission_policies'] = capability_payload['member_permission_policies']
    payload_result['supported_permissions'] = capability_payload['supported_permissions']
    payload_result['can_manage_member_permissions'] = capability_payload['can_manage_member_permissions']
    payload_result['permission_policy_status'] = 'saved'
    payload_result['permission_policy_message'] = 'Lidrechten opgeslagen.'
    return payload_result


@app.put("/api/household/name")
def rename_household(payload: HouseholdNameUpdateRequest, authorization: Optional[str] = Header(None)):
    context = require_household_admin_context(authorization)
    household_id = str(context['active_household_id'])
    current_email = str(context.get('email') or '').strip().lower()
    with engine.begin() as conn:
        update_household_name(conn, household_id, payload.name)
        payload_result = build_household_members_payload(conn, household_id, current_email)
        capability_payload = build_capabilities_payload(conn, context)
    refresh_runtime_users_from_db()
    payload_result['is_household_admin'] = True
    payload_result['current_user_email'] = current_email
    payload_result['current_user_display_role'] = context['display_role']
    payload_result['permissions'] = capability_payload['permissions']
    payload_result['member_permission_policies'] = capability_payload['member_permission_policies']
    payload_result['supported_permissions'] = capability_payload['supported_permissions']
    payload_result['can_manage_member_permissions'] = capability_payload['can_manage_member_permissions']
    payload_result['household_rename_status'] = 'saved'
    payload_result['household_rename_message'] = f'Huishoudnaam opgeslagen: {payload.name}.'
    return payload_result


@app.post("/api/household/members")
def create_household_member(payload: HouseholdMemberCreateRequest, authorization: Optional[str] = Header(None)):
    context = require_household_admin_context(authorization)
    household_id = str(context['active_household_id'])
    household_name = str(context.get('active_household_name') or 'Mijn huishouden')
    normalized_email = payload.email
    password_value = ''
    existing_user = None
    with engine.begin() as conn:
        existing_membership = conn.execute(
            text("SELECT id FROM household_memberships WHERE household_id = :household_id AND user_email = :email LIMIT 1"),
            {'household_id': household_id, 'email': normalized_email},
        ).mappings().first()
        if existing_membership:
            raise HTTPException(status_code=409, detail='Gebruiker is al gekoppeld aan dit huishouden')

        existing_user = conn.execute(
            text("SELECT id FROM app_users WHERE email = :email LIMIT 1"),
            {'email': normalized_email},
        ).mappings().first()
        password_value = str(payload.password or '').strip()
        if existing_user:
            if password_value:
                raise HTTPException(status_code=409, detail='Gebruiker bestaat al. Laat wachtwoord leeg om dit account te koppelen.')
        else:
            if not password_value:
                raise HTTPException(status_code=400, detail='Wachtwoord is verplicht voor een nieuw account')
            conn.execute(
                text(
                    '''
                    INSERT INTO app_users (id, email, password, created_at, updated_at)
                    VALUES (:id, :email, :password, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    '''
                ),
                {'id': str(uuid.uuid4()), 'email': normalized_email, 'password': password_value},
            )

        conn.execute(
            text(
                '''
                INSERT INTO household_memberships (id, household_id, user_email, role, created_at, updated_at)
                VALUES (:id, :household_id, :user_email, :role, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                '''
            ),
            {
                'id': str(uuid.uuid4()),
                'household_id': household_id,
                'user_email': normalized_email,
                'role': payload.role,
            },
        )
        log_household_role_change(conn, household_id, normalized_email, None, payload.role, str(context.get('email') or '').strip().lower(), action_type='member_added')
        payload_result = build_household_members_payload(conn, household_id, str(context.get('email') or '').strip().lower())
        capability_payload = build_capabilities_payload(conn, context)
    refresh_runtime_users_from_db()
    try:
        invite_result = send_household_invitation_email(
            normalized_email,
            household_name,
            'admin' if payload.role == 'owner' else 'lid',
            password_value if not existing_user else None,
        )
    except HTTPException as exc:
        invite_result = {'status': 'failed', 'message': normalize_api_error_message(exc.detail, 'Uitnodigingsmail kon niet worden verzonden.')}
    except Exception as exc:
        invite_result = {'status': 'failed', 'message': f'Uitnodigingsmail niet verzonden. Onverwachte fout: {normalize_api_error_message(exc, "onbekende fout")}. {build_outbound_email_configuration_summary()}'}
    payload_result['is_household_admin'] = True
    payload_result['permissions'] = capability_payload['permissions']
    payload_result['member_permission_policies'] = capability_payload['member_permission_policies']
    payload_result['supported_permissions'] = capability_payload['supported_permissions']
    payload_result['can_manage_member_permissions'] = capability_payload['can_manage_member_permissions']
    payload_result['invite_email_status'] = invite_result.get('status')
    payload_result['invite_email_message'] = invite_result.get('message')
    payload_result['invite_email_recipient'] = normalized_email
    payload_result['invite_email_diagnostics'] = {
        'status': invite_result.get('status'),
        'message': invite_result.get('message'),
        'configuration_summary': build_outbound_email_configuration_summary(),
    }
    return payload_result


@app.put("/api/household/members/{member_email}")
def update_household_member(member_email: str, payload: HouseholdMemberUpdateRequest, authorization: Optional[str] = Header(None)):
    context = require_household_admin_context(authorization)
    household_id = str(context['active_household_id'])
    normalized_email = str(member_email or '').strip().lower()
    if not normalized_email:
        raise HTTPException(status_code=400, detail='E-mailadres is verplicht')
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id, role FROM household_memberships WHERE household_id = :household_id AND user_email = :email LIMIT 1"),
            {'household_id': household_id, 'email': normalized_email},
        ).mappings().first()
        if not existing:
            raise HTTPException(status_code=404, detail='Gebruiker is niet gekoppeld aan dit huishouden')
        current_role = str(existing.get('role') or 'member')
        if current_role == 'owner' and payload.role != 'owner' and count_household_admins(conn, household_id) <= 1:
            raise HTTPException(status_code=409, detail='Er moet minimaal één admin in het huishouden overblijven')
        conn.execute(
            text("UPDATE household_memberships SET role = :role, updated_at = CURRENT_TIMESTAMP WHERE id = :id"),
            {'id': existing['id'], 'role': payload.role},
        )
        log_household_role_change(conn, household_id, normalized_email, current_role, payload.role, str(context.get('email') or '').strip().lower(), action_type='role_changed')
        payload_result = build_household_members_payload(conn, household_id, str(context.get('email') or '').strip().lower())
        capability_payload = build_capabilities_payload(conn, context)
    refresh_runtime_users_from_db()
    payload_result['is_household_admin'] = True
    payload_result['permissions'] = capability_payload['permissions']
    payload_result['member_permission_policies'] = capability_payload['member_permission_policies']
    payload_result['supported_permissions'] = capability_payload['supported_permissions']
    payload_result['can_manage_member_permissions'] = capability_payload['can_manage_member_permissions']
    return payload_result


@app.delete("/api/household/members/{member_email}")
def delete_household_member(member_email: str, authorization: Optional[str] = Header(None)):
    context = require_household_admin_context(authorization)
    household_id = str(context['active_household_id'])
    normalized_email = str(member_email or '').strip().lower()
    if not normalized_email:
        raise HTTPException(status_code=400, detail='E-mailadres is verplicht')
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id, role FROM household_memberships WHERE household_id = :household_id AND user_email = :email LIMIT 1"),
            {'household_id': household_id, 'email': normalized_email},
        ).mappings().first()
        if not existing:
            raise HTTPException(status_code=404, detail='Gebruiker is niet gekoppeld aan dit huishouden')
        if str(existing.get('role') or 'member') == 'owner' and count_household_admins(conn, household_id) <= 1:
            raise HTTPException(status_code=409, detail='De laatste admin van het huishouden kan niet worden verwijderd')
        conn.execute(text("DELETE FROM household_memberships WHERE id = :id"), {'id': existing['id']})
        log_household_role_change(conn, household_id, normalized_email, str(existing.get('role') or 'member'), None, str(context.get('email') or '').strip().lower(), action_type='member_removed')
        payload_result = build_household_members_payload(conn, household_id, str(context.get('email') or '').strip().lower())
        capability_payload = build_capabilities_payload(conn, context)
    refresh_runtime_users_from_db()
    payload_result['is_household_admin'] = True
    payload_result['permissions'] = capability_payload['permissions']
    payload_result['member_permission_policies'] = capability_payload['member_permission_policies']
    payload_result['supported_permissions'] = capability_payload['supported_permissions']
    payload_result['can_manage_member_permissions'] = capability_payload['can_manage_member_permissions']
    return payload_result


@app.get("/api/household/automation-settings")
def get_household_automation_settings(authorization: Optional[str] = Header(None)):
    context = require_household_context(authorization)
    household_id = str(context['active_household_id'])
    is_household_admin = context['display_role'] == 'admin'
    with engine.begin() as conn:
        mode = get_household_auto_consume_mode(conn, household_id)
        has_explicit_value = has_household_auto_consume_mode(conn, household_id)
    return {
        "household_id": household_id,
        "mode": mode,
        "auto_consume_on_repurchase": mode != ARTICLE_AUTO_CONSUME_NONE,
        "has_explicit_value": has_explicit_value,
        "is_household_admin": is_household_admin,
    }


@app.put("/api/household/automation-settings")
def update_household_automation_settings(payload: HouseholdAutomationSettingsUpdateRequest, authorization: Optional[str] = Header(None)):
    context = require_household_admin_context(authorization)
    household_id = str(context['active_household_id'])
    with engine.begin() as conn:
        mode = set_household_auto_consume_mode(conn, household_id, payload.mode)
    return {
        "household_id": household_id,
        "mode": mode,
        "auto_consume_on_repurchase": mode != ARTICLE_AUTO_CONSUME_NONE,
        "has_explicit_value": True,
        "is_household_admin": True,
    }


@app.get("/api/household/almost-out-settings")
def get_household_almost_out_settings_endpoint(authorization: Optional[str] = Header(None)):
    context = require_household_context(authorization)
    household_id = str(context['active_household_id'])
    is_household_admin = context['display_role'] == 'admin'
    with engine.begin() as conn:
        settings = get_household_almost_out_settings(conn, household_id)
    return {
        'household_id': household_id,
        'prediction_enabled': bool(settings.get('prediction_enabled')),
        'prediction_days': int(settings.get('prediction_days') or 0),
        'policy_mode': normalize_almost_out_policy_mode(settings.get('policy_mode')),
        'is_household_admin': is_household_admin,
    }


@app.put("/api/household/almost-out-settings")
def update_household_almost_out_settings_endpoint(payload: HouseholdAlmostOutSettingsUpdateRequest, authorization: Optional[str] = Header(None)):
    context = require_household_admin_context(authorization)
    household_id = str(context['active_household_id'])
    with engine.begin() as conn:
        settings = set_household_almost_out_settings(
            conn,
            household_id,
            prediction_enabled=payload.prediction_enabled,
            prediction_days=payload.prediction_days,
            policy_mode=payload.policy_mode,
        )
    return {
        'household_id': household_id,
        **settings,
        'is_household_admin': True,
    }


@app.get("/api/household/store-import-settings")
def get_store_import_settings(authorization: Optional[str] = Header(None)):
    context = require_household_context(authorization)
    household_id = str(context['active_household_id'])
    can_edit = context['display_role'] == 'admin'
    with engine.begin() as conn:
        level = get_household_store_import_simplification_level(conn, household_id)
    return {
        "household_id": household_id,
        "store_import_simplification_level": level,
        "can_edit_store_import_simplification_level": can_edit,
        "is_household_admin": can_edit,
    }


@app.put("/api/household/store-import-settings")
def update_store_import_settings(payload: StoreImportSimplificationUpdateRequest, authorization: Optional[str] = Header(None)):
    context = require_household_admin_context(authorization)
    household_id = str(context['active_household_id'])
    with engine.begin() as conn:
        level = set_household_store_import_simplification_level(conn, household_id, payload.store_import_simplification_level)
    return {
        "household_id": household_id,
        "store_import_simplification_level": level,
        "can_edit_store_import_simplification_level": True,
        "is_household_admin": True,
    }


@app.get("/api/settings/article-field-visibility")
def get_article_field_visibility(authorization: Optional[str] = Header(None)):
    user = get_current_user_from_authorization(authorization)
    household = get_household_payload_for_user(user)
    with engine.begin() as conn:
        visibility = get_household_article_field_visibility(conn, household["id"])
    return visibility


@app.put("/api/settings/article-field-visibility")
def update_article_field_visibility(payload: dict, authorization: Optional[str] = Header(None)):
    context = require_household_admin_context(authorization)
    with engine.begin() as conn:
        visibility = set_household_article_field_visibility(conn, str(context['active_household_id']), payload)
    return visibility


@app.get("/api/settings/privacy-data-sharing")
def get_privacy_data_sharing_settings(authorization: Optional[str] = Header(None)):
    user = get_current_user_from_authorization(authorization)
    normalized_email = str(user.get("email") or '').strip().lower()
    with engine.begin() as conn:
        settings = get_user_privacy_settings(conn, normalized_email)
    return {
        **settings,
        "user_email": normalized_email,
        "screen_title": "Privacy & Datadeling",
        "is_user_managed": True,
    }


@app.put("/api/settings/privacy-data-sharing")
def update_privacy_data_sharing_settings(payload: UserPrivacySettingsUpdateRequest, authorization: Optional[str] = Header(None)):
    user = get_current_user_from_authorization(authorization)
    normalized_email = str(user.get("email") or '').strip().lower()
    with engine.begin() as conn:
        settings = set_user_privacy_settings(conn, normalized_email, payload.normalized_settings())
    return {
        **settings,
        "user_email": normalized_email,
        "screen_title": "Privacy & Datadeling",
        "is_user_managed": True,
        "settings_status": "saved",
        "settings_message": "Privacy- en datadeelrechten opgeslagen.",
    }



@app.get("/api/household-articles/{household_article_id}")
def get_household_article_resource_endpoint(household_article_id: str, authorization: Optional[str] = Header(None)):
    context = require_household_context(authorization)
    household_id = str(context.get('active_household_id') or '')
    with engine.begin() as conn:
        return resolve_household_article_detail_service(conn, household_id, article_id=str(household_article_id or '').strip(), create_if_missing=False)


@app.patch("/api/household-articles/{household_article_id}")
def patch_household_article_details_by_id(household_article_id: str, payload: ArticleHouseholdDetailsUpdateRequest, authorization: Optional[str] = Header(None)):
    context = require_household_context(authorization)
    display_role = str(context.get('display_role') or '').strip().lower()
    if display_role not in {'admin', 'lid'}:
        raise HTTPException(status_code=403, detail='Alleen admin en lid mogen artikeldetails aanpassen')
    household_id = str(context.get('active_household_id') or '')
    with engine.begin() as conn:
        article_row = get_household_article_row_by_id(conn, household_id, str(household_article_id or '').strip())
        if not article_row:
            raise HTTPException(status_code=404, detail='Artikel niet gevonden')
        details = update_household_article_details_by_id(conn, household_id, str(article_row.get('id') or '').strip(), payload)
    return {
        'status': 'ok',
        'household_article_id': str(household_article_id or '').strip(),
        'details': details,
        'current_user_display_role': display_role,
    }


@app.get("/api/household-articles/{household_article_id}/inventory")
def get_household_article_inventory_endpoint(household_article_id: str, authorization: Optional[str] = Header(None)):
    context = require_household_context(authorization)
    household_id = str(context.get('active_household_id') or '')
    with engine.begin() as conn:
        details = resolve_household_article_detail_service(conn, household_id, article_id=str(household_article_id or '').strip(), create_if_missing=False)
        return {
            'household_article_id': str(details.get('household_article_id') or household_article_id),
            'article_id': str(details.get('article_id') or details.get('household_article_id') or household_article_id),
            'items': details.get('inventory') or [],
        }


@app.get("/api/household-articles/{household_article_id}/locations")
def get_household_article_locations_endpoint(household_article_id: str, authorization: Optional[str] = Header(None)):
    context = require_household_context(authorization)
    household_id = str(context.get('active_household_id') or '')
    with engine.begin() as conn:
        details = resolve_household_article_detail_service(conn, household_id, article_id=str(household_article_id or '').strip(), create_if_missing=False)
        return {
            'household_article_id': str(details.get('household_article_id') or household_article_id),
            'article_id': str(details.get('article_id') or details.get('household_article_id') or household_article_id),
            'items': details.get('locations') or [],
        }


@app.get("/api/household-articles/{household_article_id}/events")
def get_household_article_events_endpoint(household_article_id: str, authorization: Optional[str] = Header(None)):
    context = require_household_context(authorization)
    household_id = str(context.get('active_household_id') or '')
    with engine.begin() as conn:
        details = resolve_household_article_detail_service(conn, household_id, article_id=str(household_article_id or '').strip(), create_if_missing=False)
        return {
            'household_article_id': str(details.get('household_article_id') or household_article_id),
            'article_id': str(details.get('article_id') or details.get('household_article_id') or household_article_id),
            'items': details.get('events') or [],
        }


@app.get("/api/household-articles/{household_article_id}/product")
def get_household_article_product_endpoint(household_article_id: str, authorization: Optional[str] = Header(None)):
    context = require_household_context(authorization)
    household_id = str(context.get('active_household_id') or '')
    with engine.begin() as conn:
        details = resolve_household_article_detail_service(conn, household_id, article_id=str(household_article_id or '').strip(), create_if_missing=False)
        return {
            'household_article_id': str(details.get('household_article_id') or household_article_id),
            'article_id': str(details.get('article_id') or details.get('household_article_id') or household_article_id),
            'article_name': details.get('article_name') or '',
            'product': details.get('product') or {},
            'product_details': details.get('product_details') or details.get('product') or {},
        }


@app.get("/api/household-articles/{household_article_id}/settings")
def get_household_article_settings_endpoint(household_article_id: str, authorization: Optional[str] = Header(None)):
    context = require_household_context(authorization)
    household_id = str(context.get('active_household_id') or '')
    with engine.begin() as conn:
        return get_household_article_settings(conn, household_id, str(household_article_id or '').strip())


@app.put("/api/household-articles/{household_article_id}/settings")
def update_household_article_settings_endpoint(household_article_id: str, payload: HouseholdArticleSettingsUpdateRequest, authorization: Optional[str] = Header(None)):
    context = require_household_context(authorization)
    display_role = str(context.get('display_role') or '').strip().lower()
    if display_role not in {'admin', 'lid'}:
        raise HTTPException(status_code=403, detail='Alleen admin en lid mogen huishoudinstellingen aanpassen')
    household_id = str(context.get('active_household_id') or '')
    with engine.begin() as conn:
        return update_household_article_settings(conn, household_id, str(household_article_id or '').strip(), payload)


@app.post("/api/household-articles/{household_article_id}/archive")
def archive_household_article_endpoint(household_article_id: str, payload: HouseholdArticleArchiveRequest | None = None, authorization: Optional[str] = Header(None)):
    context = require_household_admin_context(authorization)
    household_id = str(context['active_household_id'])
    with engine.begin() as conn:
        return archive_household_article_by_id(conn, household_id, str(household_article_id or '').strip(), (payload.reason if payload else None))


@app.delete("/api/household-articles/{household_article_id}")
def delete_household_article_endpoint(household_article_id: str, payload: HouseholdArticleDeleteRequest | None = None, authorization: Optional[str] = Header(None)):
    context = require_household_admin_context(authorization)
    household_id = str(context['active_household_id'])
    with engine.begin() as conn:
        return delete_household_article_by_id(conn, household_id, str(household_article_id or '').strip(), (payload.reason if payload else None), bool(payload.force) if payload else False)


@app.get("/api/households/{household_id}/almost-out")
def get_household_almost_out_endpoint(household_id: str, authorization: Optional[str] = Header(None)):
    context = require_household_context(authorization, str(household_id or '').strip())
    resolved_household_id = str(context.get('active_household_id') or household_id or '').strip()
    with engine.begin() as conn:
        settings = get_household_almost_out_settings(conn, resolved_household_id)
        items = build_almost_out_items(conn, resolved_household_id)
        return {
            'household_id': resolved_household_id,
            'settings': settings,
            'items': items,
            'count': len(items),
        }


@app.get("/api/household-articles/{household_article_id}/automation-override")
def get_household_article_automation_override(household_article_id: str, authorization: Optional[str] = Header(None)):
    user = get_current_user_from_authorization(authorization)
    household = get_household_payload_for_user(user)
    household_id = str(household["id"])
    with engine.begin() as conn:
        article_row = get_household_article_row_by_id(conn, household_id, str(household_article_id or '').strip())
        if not article_row:
            raise HTTPException(status_code=404, detail="Onbekend artikel")
        resolved_article_id = str(article_row.get("id") or "").strip()
        article_name = str(article_row.get("naam") or article_row.get("name") or "").strip()
        mode = get_household_article_auto_consume_override(conn, household_id, resolved_article_id)
        has_explicit_override = has_household_article_auto_consume_override(conn, household_id, resolved_article_id)
        consumable = get_article_consumable_state(conn, household_id, resolved_article_id, article_name)
    return {
        "article_id": resolved_article_id,
        "household_article_id": resolved_article_id,
        "requested_article_id": str(household_article_id),
        "mode": mode,
        "has_explicit_override": has_explicit_override,
        "consumable": consumable,
        "article_name": article_name,
    }


@app.put("/api/household-articles/{household_article_id}/automation-override")
def update_household_article_automation_override(household_article_id: str, payload: ArticleAutomationOverrideUpdateRequest, authorization: Optional[str] = Header(None)):
    context = require_household_admin_context(authorization)
    household_id = str(context['active_household_id'])
    with engine.begin() as conn:
        article_row = get_household_article_row_by_id(conn, household_id, str(household_article_id or '').strip())
        if not article_row:
            raise HTTPException(status_code=404, detail="Onbekend artikel")
        resolved_article_id = str(article_row.get("id") or "").strip()
        article_name = str(article_row.get("naam") or article_row.get("name") or "").strip()
        mode = set_household_article_auto_consume_override(conn, household_id, resolved_article_id, payload.mode)
        consumable = get_article_consumable_state(conn, household_id, resolved_article_id, article_name)
    return {
        "article_id": resolved_article_id,
        "household_article_id": resolved_article_id,
        "requested_article_id": str(household_article_id),
        "mode": mode,
        "has_explicit_override": True,
        "consumable": consumable,
        "article_name": article_name,
    }


@app.post("/api/household-articles/{household_article_id}/enrich")
def enrich_household_article_by_id(household_article_id: str, authorization: Optional[str] = Header(None)):
    context = require_household_context(authorization)
    household_id = str(context.get('active_household_id') or '')
    with engine.begin() as conn:
        article_row = get_household_article_row_by_id(conn, household_id, str(household_article_id or '').strip())
        if not article_row:
            raise HTTPException(status_code=404, detail='Artikel niet gevonden')
        details = build_household_article_resource(conn, household_id, str(article_row.get('id') or ''))
        return {
            'status': details.get('product_details', {}).get('enrichment_status', {}).get('status') or 'skipped',
            'article_id': article_row.get('id'),
            'household_article_id': article_row.get('id'),
            'article_name': article_row.get('naam') or '',
            'product_details': details.get('product_details') or {},
        }


@app.get("/api/articles/{article_id}")
def get_article_detail_by_id(article_id: str, authorization: Optional[str] = Header(None)):
    context = require_household_context(authorization)
    household_id = str(context.get('active_household_id') or '')
    with engine.begin() as conn:
        details = resolve_household_article_detail_service(conn, household_id, article_id=article_id, create_if_missing=False)
        return {
            **details,
            'id': details.get('household_article_id') or details.get('article_id'),
            'article_id': details.get('household_article_id') or details.get('article_id'),
            'identity': (details.get('product_details') or {}).get('identity'),
            'enrichment': (details.get('product_details') or {}).get('enrichment'),
        }


@app.get("/api/articles/{article_id}/automation-override")
def get_article_automation_override(article_id: str, authorization: Optional[str] = Header(None)):
    context = require_household_context(authorization)
    household_id = str(context.get('active_household_id') or '')
    with engine.begin() as conn:
        article_row = resolve_household_article_reference(conn, household_id, article_id=article_id, create_if_missing=False)
        if not article_row:
            raise HTTPException(status_code=404, detail="Onbekend artikel")
    return get_household_article_automation_override(str(article_row.get('id') or ''), authorization)


@app.put("/api/articles/{article_id}/automation-override")
def update_article_automation_override(article_id: str, payload: ArticleAutomationOverrideUpdateRequest, authorization: Optional[str] = Header(None)):
    context = require_household_admin_context(authorization)
    household_id = str(context['active_household_id'])
    with engine.begin() as conn:
        article_row = resolve_household_article_reference(conn, household_id, article_id=article_id, create_if_missing=False)
        if not article_row:
            raise HTTPException(status_code=404, detail="Onbekend artikel")
    return update_household_article_automation_override(str(article_row.get('id') or ''), payload, authorization)


@app.put("/api/dev/household/almost-out-settings")
def update_dev_household_almost_out_settings(payload: HouseholdAlmostOutSettingsUpdateRequest, household_id: str = Query("demo-household")):
    with engine.begin() as conn:
        settings = set_household_almost_out_settings(
            conn,
            household_id,
            prediction_enabled=payload.prediction_enabled,
            prediction_days=payload.prediction_days,
            policy_mode=payload.policy_mode,
        )
    return {
        'household_id': household_id,
        **settings,
        'is_household_admin': True,
    }


@app.put("/api/dev/household/store-import-settings")
def update_dev_store_import_settings(payload: StoreImportSimplificationUpdateRequest, household_id: str = Query("demo-household")):
    effective_household_id = (household_id or "demo-household").strip() or "demo-household"
    with engine.begin() as conn:
        level = set_household_store_import_simplification_level(conn, effective_household_id, payload.store_import_simplification_level)
    return {
        "household_id": effective_household_id,
        "store_import_simplification_level": level,
        "can_edit_store_import_simplification_level": True,
        "is_household_admin": True,
    }


@app.put("/api/dev/household/automation-settings")
def update_dev_household_automation_settings(payload: HouseholdAutomationSettingsUpdateRequest, household_id: str = Query("demo-household")):
    effective_household_id = (household_id or "demo-household").strip() or "demo-household"
    with engine.begin() as conn:
        mode = set_household_auto_consume_mode(conn, effective_household_id, payload.mode)
    return {
        "household_id": effective_household_id,
        "mode": mode,
        "auto_consume_on_repurchase": mode != ARTICLE_AUTO_CONSUME_NONE,
        "is_household_admin": True,
    }


@app.put("/api/dev/articles/{article_id}/automation-override")
def update_dev_article_automation_override(article_id: str, payload: ArticleAutomationOverrideUpdateRequest, household_id: str = Query("demo-household")):
    effective_household_id = (household_id or "demo-household").strip() or "demo-household"
    with engine.begin() as conn:
        article = resolve_review_article_option(conn, article_id, effective_household_id)
        if not article:
            raise HTTPException(status_code=404, detail="Onbekend artikel")
        mode = set_household_article_auto_consume_override(conn, effective_household_id, article["id"], payload.mode)
    return {
        "household_id": effective_household_id,
        "article_id": article["id"],
        "mode": mode,
    }


# SQLite datamodel initialization
from app.db import engine, Base

def ensure_release_1031_schema():
    with engine.begin() as conn:
        household_article_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(household_articles)")).fetchall()}
        if "barcode" not in household_article_columns:
            conn.execute(text("ALTER TABLE household_articles ADD COLUMN barcode TEXT"))
        if "article_number" not in household_article_columns:
            conn.execute(text("ALTER TABLE household_articles ADD COLUMN article_number TEXT"))
        if "external_source" not in household_article_columns:
            conn.execute(text("ALTER TABLE household_articles ADD COLUMN external_source TEXT"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_household_articles_household_barcode ON household_articles (household_id, barcode)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_household_articles_household_article_number ON household_articles (household_id, article_number)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_household_articles_household_article_number ON household_articles (household_id, article_number)"))

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS inventory_events (
                    id TEXT PRIMARY KEY,
                    household_id TEXT NOT NULL,
                    article_id TEXT,
                    article_name TEXT NOT NULL,
                    location_id TEXT,
                    location_label TEXT,
                    event_type TEXT NOT NULL,
                    quantity NUMERIC NOT NULL,
                    old_quantity NUMERIC,
                    new_quantity NUMERIC,
                    source TEXT NOT NULL,
                    note TEXT,
                    purchase_date TEXT,
                    supplier_name TEXT,
                    article_number TEXT,
                    price NUMERIC,
                    currency TEXT,
                    barcode TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        inventory_event_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(inventory_events)")).fetchall()}
        if "purchase_date" not in inventory_event_columns:
            conn.execute(text("ALTER TABLE inventory_events ADD COLUMN purchase_date TEXT"))
        if "supplier_name" not in inventory_event_columns:
            conn.execute(text("ALTER TABLE inventory_events ADD COLUMN supplier_name TEXT"))
        if "price" not in inventory_event_columns:
            conn.execute(text("ALTER TABLE inventory_events ADD COLUMN price NUMERIC"))
        if "currency" not in inventory_event_columns:
            conn.execute(text("ALTER TABLE inventory_events ADD COLUMN currency TEXT"))
        if "article_number" not in inventory_event_columns:
            conn.execute(text("ALTER TABLE inventory_events ADD COLUMN article_number TEXT"))
        if "barcode" not in inventory_event_columns:
            conn.execute(text("ALTER TABLE inventory_events ADD COLUMN barcode TEXT"))


def ensure_release_1041_schema():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS spaces (
                    id TEXT PRIMARY KEY,
                    naam TEXT NOT NULL,
                    household_id TEXT,
                    active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
        )
        space_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(spaces)")).fetchall()}
        if "active" not in space_columns:
            conn.execute(text("ALTER TABLE spaces ADD COLUMN active INTEGER NOT NULL DEFAULT 1"))
        conn.execute(text("UPDATE spaces SET active = 1 WHERE active IS NULL"))


def ensure_release_1046_schema():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS sublocations (
                    id TEXT PRIMARY KEY,
                    naam TEXT NOT NULL,
                    space_id TEXT,
                    active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
        )
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(sublocations)")).fetchall()}
        if "active" not in columns:
            conn.execute(text("ALTER TABLE sublocations ADD COLUMN active INTEGER NOT NULL DEFAULT 1"))
        conn.execute(text("UPDATE sublocations SET active = 1 WHERE active IS NULL"))


from app.models import household, space, sublocation, inventory, store_provider, store_connection, purchase_import, receipt

Base.metadata.create_all(bind=engine)
ensure_household_settings_schema()
ensure_user_settings_schema()
ensure_household_permission_policies_schema()
ensure_household_role_change_audit_schema()
ensure_household_articles_schema()
ensure_product_enrichment_schema()
ensure_global_product_catalog_schema()
ensure_release_b_household_article_global_product_integrity()
ensure_release_c_product_enrichment_centralization()
ensure_release_2_schema()
ensure_release_3_schema()
ensure_release_4_schema()
ensure_release_803_schema()
ensure_release_813_schema()
ensure_release_814_schema()
ensure_release_902_schema()
ensure_release_932_schema()
ensure_release_933_schema()
ensure_release_935_schema()
ensure_release_940_schema()
ensure_release_941_receipt_edit_schema()
ensure_release_963_schema()
ensure_release_965_schema()
ensure_release_1031_schema()
ensure_release_1041_schema()
ensure_release_1046_schema()
ensure_release_1113_schema()
bootstrap_auth_registry()
refresh_runtime_users_from_db()
ensure_receipt_storage_root()
seed_store_providers()
admin_household = ensure_household("admin@rezzerv.local")
admin_household_id = str(admin_household.get("id") or "1")
ensure_default_receipt_sources(engine, RECEIPT_STORAGE_ROOT, admin_household_id)
dedupe_receipts_for_household(engine, admin_household_id)


def ensure_ui_test_seed_data():
    household = ensure_household("admin@rezzerv.local")
    household_id = str(household.get("id") or "1")

    with engine.begin() as conn:
        def ensure_space(name: str):
            row = conn.execute(
                text("SELECT id FROM spaces WHERE household_id = :household_id AND lower(naam) = lower(:naam) LIMIT 1"),
                {"household_id": household_id, "naam": name},
            ).mappings().first()
            if row:
                return row["id"]
            return conn.execute(
                text("INSERT INTO spaces (id, naam, household_id) VALUES (lower(hex(randomblob(16))), :naam, :household_id) RETURNING id"),
                {"naam": name, "household_id": household_id},
            ).scalar_one()

        def ensure_sublocation(space_id: str, name: str):
            row = conn.execute(
                text("SELECT id FROM sublocations WHERE space_id = :space_id AND lower(naam) = lower(:naam) LIMIT 1"),
                {"space_id": space_id, "naam": name},
            ).mappings().first()
            if row:
                return row["id"]
            return conn.execute(
                text("INSERT INTO sublocations (id, naam, space_id) VALUES (lower(hex(randomblob(16))), :naam, :space_id) RETURNING id"),
                {"naam": name, "space_id": space_id},
            ).scalar_one()

        keuken_id = ensure_space('Keuken')
        berging_id = ensure_space('Berging')
        badkamer_id = ensure_space('Badkamer')
        kast1_id = ensure_sublocation(keuken_id, 'Kast 1')
        kitchen_koelkast_id = ensure_sublocation(keuken_id, 'Koelkast')
        voorraadkast_id = ensure_sublocation(berging_id, 'Voorraadkast')
        boven_id = ensure_sublocation(berging_id, 'Boven')
        badkamerkast_id = ensure_sublocation(badkamer_id, 'Kast')

        batch_count = conn.execute(
            text("SELECT COUNT(*) FROM purchase_import_batches WHERE household_id = :household_id"),
            {"household_id": household_id},
        ).scalar() or 0

        if int(batch_count) == 0:
            provider_rows = conn.execute(
                text("SELECT id, code, name FROM store_providers WHERE code IN ('jumbo', 'lidl') ORDER BY code"),
            ).mappings().all()
            providers = {row['code']: dict(row) for row in provider_rows}

            def ensure_connection(provider_code: str, external_ref: str):
                provider = providers.get(provider_code)
                if not provider:
                    return None
                existing = conn.execute(
                    text("SELECT id FROM household_store_connections WHERE household_id = :household_id AND store_provider_id = :store_provider_id LIMIT 1"),
                    {"household_id": household_id, "store_provider_id": provider['id']},
                ).mappings().first()
                if existing:
                    return existing['id']
                return conn.execute(
                    text("""
                    INSERT INTO household_store_connections (
                        id, household_id, store_provider_id, connection_status, external_account_ref, linked_at, created_at, updated_at
                    ) VALUES (
                        lower(hex(randomblob(16))), :household_id, :store_provider_id, 'active', :external_account_ref, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    ) RETURNING id
                    """),
                    {"household_id": household_id, "store_provider_id": provider['id'], "external_account_ref": external_ref},
                ).scalar_one()

            def insert_batch(provider_code: str, connection_id: str, source_reference: str, import_status: str, batch_metadata: dict, lines: list[dict]):
                provider = providers.get(provider_code)
                if not provider or not connection_id:
                    return None
                batch_id = str(uuid.uuid4())
                raw_payload = json.dumps({
                    'mock_profile': 'seed',
                    'provider_code': provider_code,
                    'batch_metadata': batch_metadata,
                    'lines': [
                        {
                            'external_line_ref': line['external_line_ref'],
                            'external_article_code': line['external_article_code'],
                            'article_name_raw': line['article_name_raw'],
                            'brand_raw': line.get('brand_raw') or '',
                            'quantity_raw': line['quantity_raw'],
                            'unit_raw': line['unit_raw'],
                            'line_price_raw': line['line_price_raw'],
                            'currency_code': line.get('currency_code') or 'EUR',
                        } for line in lines
                    ],
                })
                conn.execute(
                    text("""
                    INSERT INTO purchase_import_batches (id, household_id, store_provider_id, connection_id, source_type, source_reference, import_status, raw_payload, created_at)
                    VALUES (:id, :household_id, :store_provider_id, :connection_id, 'mock', :source_reference, :import_status, :raw_payload, CURRENT_TIMESTAMP)
                    """),
                    {
                        'id': batch_id,
                        'household_id': household_id,
                        'store_provider_id': provider['id'],
                        'connection_id': connection_id,
                        'source_reference': source_reference,
                        'import_status': import_status,
                        'raw_payload': raw_payload,
                    },
                )
                for index, line in enumerate(lines, start=1):
                    conn.execute(
                        text("""
                        INSERT INTO purchase_import_lines (
                            id, batch_id, external_line_ref, external_article_code, article_name_raw, brand_raw, quantity_raw, unit_raw, line_price_raw, currency_code,
                            match_status, review_decision, ui_sort_order, matched_household_article_id, target_location_id, processing_status, suggested_household_article_id, suggested_location_id, suggestion_confidence, suggestion_reason, is_auto_prefilled, article_override_mode, location_override_mode, created_at
                        ) VALUES (
                            lower(hex(randomblob(16))), :batch_id, :external_line_ref, :external_article_code, :article_name_raw, :brand_raw, :quantity_raw, :unit_raw, :line_price_raw, :currency_code,
                            :match_status, :review_decision, :ui_sort_order, :matched_household_article_id, :target_location_id, :processing_status, :suggested_household_article_id, :suggested_location_id, :suggestion_confidence, :suggestion_reason, :is_auto_prefilled, :article_override_mode, :location_override_mode, CURRENT_TIMESTAMP
                        )
                        """),
                        {
                            'batch_id': batch_id,
                            'ui_sort_order': index,
                            'external_line_ref': line['external_line_ref'],
                            'external_article_code': line['external_article_code'],
                            'article_name_raw': line['article_name_raw'],
                            'brand_raw': line.get('brand_raw') or '',
                            'quantity_raw': line['quantity_raw'],
                            'unit_raw': line['unit_raw'],
                            'line_price_raw': line['line_price_raw'],
                            'currency_code': line.get('currency_code') or 'EUR',
                            'match_status': line.get('match_status') or 'unmatched',
                            'review_decision': line.get('review_decision') or 'pending',
                            'matched_household_article_id': line.get('matched_household_article_id'),
                            'target_location_id': line.get('target_location_id'),
                            'processing_status': line.get('processing_status') or 'pending',
                            'suggested_household_article_id': line.get('suggested_household_article_id'),
                            'suggested_location_id': line.get('suggested_location_id'),
                            'suggestion_confidence': line.get('suggestion_confidence'),
                            'suggestion_reason': line.get('suggestion_reason'),
                            'is_auto_prefilled': line.get('is_auto_prefilled', 0),
                            'article_override_mode': line.get('article_override_mode', 'auto'),
                            'location_override_mode': line.get('location_override_mode', 'auto'),
                        },
                    )
                return batch_id

            kitchen_kast1 = kast1_id
            kitchen_koelkast = kitchen_koelkast_id
            berging_boven = boven_id

            jumbo_connection_id = ensure_connection('jumbo', 'jumbo-klantkaart')
            lidl_connection_id = ensure_connection('lidl', 'lidl-klantkaart')

            insert_batch(
                'jumbo',
                jumbo_connection_id,
                'mock:seed-jumbo-open',
                'in_review',
                {'purchase_date': '15-03-2026', 'store_name': 'Jumbo', 'store_label': 'Jumbo, Marktplein 8, Utrecht'},
                [
                    {
                        'external_line_ref': 'seed-jumbo-1', 'external_article_code': 'JUMBO-SEED-1', 'article_name_raw': 'Magere yoghurt', 'brand_raw': 'Jumbo',
                        'quantity_raw': 1, 'unit_raw': 'liter', 'line_price_raw': 1.59, 'currency_code': 'EUR',
                        'match_status': 'matched', 'review_decision': 'selected', 'matched_household_article_id': build_live_article_option_id('Melk'),
                        'target_location_id': kitchen_kast1, 'processing_status': 'pending', 'suggested_household_article_id': build_live_article_option_id('Melk'),
                        'suggested_location_id': kitchen_kast1, 'suggestion_confidence': 'high', 'suggestion_reason': 'Automatisch voorbereid — niveau Gebalanceerd', 'is_auto_prefilled': 1,
                    },
                    {
                        'external_line_ref': 'seed-jumbo-2', 'external_article_code': 'JUMBO-SEED-2', 'article_name_raw': 'Appelsap', 'brand_raw': 'Jumbo',
                        'quantity_raw': 1, 'unit_raw': 'liter', 'line_price_raw': 1.99, 'currency_code': 'EUR',
                        'match_status': 'unmatched', 'review_decision': 'selected', 'processing_status': 'pending',
                    },
                    {
                        'external_line_ref': 'seed-jumbo-3', 'external_article_code': 'JUMBO-SEED-3', 'article_name_raw': 'Pindakaas', 'brand_raw': 'Calvé',
                        'quantity_raw': 1, 'unit_raw': 'pot', 'line_price_raw': 3.49, 'currency_code': 'EUR',
                        'match_status': 'unmatched', 'review_decision': 'ignored', 'processing_status': 'pending',
                    },
                    {
                        'external_line_ref': 'seed-jumbo-4', 'external_article_code': 'JUMBO-SEED-4', 'article_name_raw': 'Tomaten', 'brand_raw': 'Jumbo',
                        'quantity_raw': 6, 'unit_raw': 'stuks', 'line_price_raw': 2.19, 'currency_code': 'EUR',
                        'match_status': 'matched', 'review_decision': 'selected', 'matched_household_article_id': build_live_article_option_id('Tomaten'),
                        'target_location_id': None, 'processing_status': 'pending', 'suggested_household_article_id': build_live_article_option_id('Tomaten'),
                        'suggested_location_id': kitchen_koelkast, 'suggestion_confidence': 'medium', 'suggestion_reason': 'Controleer voorstel — niveau Gebalanceerd', 'is_auto_prefilled': 0,
                    },
                ],
            )

            insert_batch(
                'lidl',
                lidl_connection_id,
                'mock:seed-lidl-processed',
                'processed',
                {'purchase_date': '14-03-2026', 'store_name': 'Lidl', 'store_label': 'Lidl, Hoofdstraat 12, Utrecht'},
                [
                    {
                        'external_line_ref': 'seed-lidl-1', 'external_article_code': 'LIDL-SEED-1', 'article_name_raw': 'Tuna', 'brand_raw': 'Lidl',
                        'quantity_raw': 1, 'unit_raw': 'blik', 'line_price_raw': 1.89, 'currency_code': 'EUR',
                        'match_status': 'matched', 'review_decision': 'selected', 'matched_household_article_id': build_live_article_option_id('Tuna'),
                        'target_location_id': berging_boven, 'processing_status': 'processed', 'processed_event_id': None if False else None,
                    },
                ],
            )

ensure_ui_test_seed_data()


REGRESSION_FIXTURE_ARTICLE_NAME = "Regressie-artikel"
REGRESSION_FIXTURE_SPACE_NAME = "Regressie voorraad"
REGRESSION_FIXTURE_SUBLOCATION_NAME = "Fixture"
REGRESSION_FIXTURE_NOTE = "Tijdelijke regressiefixture"
REGRESSION_RECEIPT_HASH_PREFIX = "regression-seed::"
REGRESSION_ARTICLE_NAMES = [
    REGRESSION_FIXTURE_ARTICLE_NAME,
    "Melk",
    "Tomaten",
]
BROWSER_REGRESSION_HOUSEHOLD_ID = 'demo-household'
BROWSER_REGRESSION_SPACE_NAME = 'Voorraad test'
BROWSER_REGRESSION_SUBLOCATION_NAME = 'Plank test'
BROWSER_REGRESSION_WORKSPACE_NAME = 'Schuur'
BROWSER_REGRESSION_WORKSPACE_SUBLOCATION_NAME = 'Werkbank'
BROWSER_REGRESSION_NOTE = 'Browser regressiefixture'
BROWSER_REGRESSION_ARTICLES = [
    {'naam': 'Mosterd', 'aantal': 1, 'space_name': BROWSER_REGRESSION_SPACE_NAME, 'sublocation_name': BROWSER_REGRESSION_SUBLOCATION_NAME},
    {'naam': 'Boormachine', 'aantal': 1, 'space_name': BROWSER_REGRESSION_WORKSPACE_NAME, 'sublocation_name': BROWSER_REGRESSION_WORKSPACE_SUBLOCATION_NAME},
    {'naam': 'Tomaten', 'aantal': 3, 'space_name': BROWSER_REGRESSION_SPACE_NAME, 'sublocation_name': BROWSER_REGRESSION_SUBLOCATION_NAME},
]


def log_regression_action(action: str, **payload: Any) -> None:
    try:
        logger.info('regression.%s %s', action, json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:
        logger.info('regression.%s %s', action, payload)


def ensure_regression_inventory_fixture(household_id: str) -> dict:
    normalized_household_id = str(household_id or '').strip() or '1'
    with engine.begin() as conn:
        space_id = conn.execute(
            text("SELECT id FROM spaces WHERE household_id = :household_id AND lower(trim(naam)) = lower(trim(:naam)) LIMIT 1"),
            {"household_id": normalized_household_id, "naam": REGRESSION_FIXTURE_SPACE_NAME},
        ).scalar()
        if not space_id:
            space_id = conn.execute(
                text("INSERT INTO spaces (id, naam, household_id) VALUES (lower(hex(randomblob(16))), :naam, :household_id) RETURNING id"),
                {"naam": REGRESSION_FIXTURE_SPACE_NAME, "household_id": normalized_household_id},
            ).scalar_one()

        sublocation_id = conn.execute(
            text("SELECT id FROM sublocations WHERE space_id = :space_id AND lower(trim(naam)) = lower(trim(:naam)) LIMIT 1"),
            {"space_id": space_id, "naam": REGRESSION_FIXTURE_SUBLOCATION_NAME},
        ).scalar()
        if not sublocation_id:
            sublocation_id = conn.execute(
                text("INSERT INTO sublocations (id, naam, space_id) VALUES (lower(hex(randomblob(16))), :naam, :space_id) RETURNING id"),
                {"naam": REGRESSION_FIXTURE_SUBLOCATION_NAME, "space_id": space_id},
            ).scalar_one()

        conn.execute(
            text("DELETE FROM inventory_events WHERE household_id = :household_id AND (source = 'regression_fixture' OR note = :note)"),
            {"household_id": normalized_household_id, "note": REGRESSION_FIXTURE_NOTE},
        )
        conn.execute(
            text(
                """
                DELETE FROM inventory
                WHERE household_id = :household_id
                  AND (
                    archive_reason = :note
                    OR (
                      COALESCE(space_id, '') = COALESCE(:space_id, '')
                      AND COALESCE(sublocation_id, '') = COALESCE(:sublocation_id, '')
                      AND lower(trim(naam)) = lower(trim(:article_name))
                    )
                  )
                """
            ),
            {
                "household_id": normalized_household_id,
                "note": REGRESSION_FIXTURE_NOTE,
                "space_id": space_id,
                "sublocation_id": sublocation_id,
                "article_name": REGRESSION_FIXTURE_ARTICLE_NAME,
            },
        )

        ensured_article_option_id = ensure_household_article(conn, normalized_household_id, REGRESSION_FIXTURE_ARTICLE_NAME)
        household_article_row = get_household_article_row_by_name(conn, normalized_household_id, REGRESSION_FIXTURE_ARTICLE_NAME)
        household_article_id = str(household_article_row.get('id') or '').strip() if household_article_row else ''

        inventory_id = conn.execute(
            text(
                """
                INSERT INTO inventory (id, naam, aantal, household_id, space_id, sublocation_id, status, updated_at)
                VALUES (lower(hex(randomblob(16))), :naam, 1, :household_id, :space_id, :sublocation_id, 'active', CURRENT_TIMESTAMP)
                RETURNING id
                """
            ),
            {
                "naam": REGRESSION_FIXTURE_ARTICLE_NAME,
                "household_id": normalized_household_id,
                "space_id": space_id,
                "sublocation_id": sublocation_id,
            },
        ).scalar_one()
        create_inventory_event(
            conn,
            household_id=normalized_household_id,
            article_id=inventory_id,
            article_name=REGRESSION_FIXTURE_ARTICLE_NAME,
            resolved_location={
                'location_id': sublocation_id or space_id,
                'space_id': space_id,
                'sublocation_id': sublocation_id,
                'location_label': ' / '.join(part for part in [REGRESSION_FIXTURE_SPACE_NAME, REGRESSION_FIXTURE_SUBLOCATION_NAME] if part),
            },
            event_type='purchase',
            quantity=1,
            source='regression_fixture',
            note=REGRESSION_FIXTURE_NOTE,
            old_quantity=0,
            new_quantity=1,
        )

    payload = {
        "articleId": household_article_id or str(inventory_id),
        "householdArticleId": household_article_id or None,
        "inventoryId": str(inventory_id),
        "articleOptionId": ensured_article_option_id,
        "articleName": REGRESSION_FIXTURE_ARTICLE_NAME,
        "spaceName": REGRESSION_FIXTURE_SPACE_NAME,
        "sublocationName": REGRESSION_FIXTURE_SUBLOCATION_NAME,
        "spaceId": str(space_id),
        "sublocationId": str(sublocation_id),
    }
    log_regression_action('fixture.ensure_inventory', household_id=normalized_household_id, **payload)
    return payload


def cleanup_regression_inventory_state(household_id: str) -> dict:
    normalized_household_id = str(household_id or '').strip() or '1'
    normalized_fixture_names = [name.strip().lower() for name in REGRESSION_ARTICLE_NAMES if str(name or '').strip()]
    with engine.begin() as conn:
        fixture_space_id = conn.execute(
            text("SELECT id FROM spaces WHERE household_id = :household_id AND lower(trim(naam)) = lower(trim(:space_name)) LIMIT 1"),
            {"household_id": normalized_household_id, "space_name": REGRESSION_FIXTURE_SPACE_NAME},
        ).scalar()
        fixture_sublocation_id = None
        if fixture_space_id:
            fixture_sublocation_id = conn.execute(
                text("SELECT id FROM sublocations WHERE space_id = :space_id AND lower(trim(naam)) = lower(trim(:sublocation_name)) LIMIT 1"),
                {"space_id": fixture_space_id, "sublocation_name": REGRESSION_FIXTURE_SUBLOCATION_NAME},
            ).scalar()

        conn.execute(
            text("DELETE FROM inventory_events WHERE household_id = :household_id AND (source = 'regression_fixture' OR note = :note)"),
            {"household_id": normalized_household_id, "note": REGRESSION_FIXTURE_NOTE},
        )
        conn.execute(
            text(
                """
                DELETE FROM inventory
                WHERE household_id = :household_id
                  AND (
                    archive_reason = :note
                    OR (
                      :space_id IS NOT NULL
                      AND COALESCE(space_id, '') = COALESCE(:space_id, '')
                      AND COALESCE(sublocation_id, '') = COALESCE(:sublocation_id, '')
                      AND lower(trim(naam)) IN :names
                    )
                  )
                """
            ).bindparams(bindparam('names', expanding=True)),
            {
                "household_id": normalized_household_id,
                "note": REGRESSION_FIXTURE_NOTE,
                "space_id": fixture_space_id,
                "sublocation_id": fixture_sublocation_id,
                "names": normalized_fixture_names,
            },
        )
        conn.execute(
            text("DELETE FROM sublocations WHERE id IN (SELECT sl.id FROM sublocations sl JOIN spaces s ON s.id = sl.space_id WHERE s.household_id = :household_id AND lower(trim(s.naam)) = lower(:space_name) AND lower(trim(sl.naam)) = lower(:sublocation_name))"),
            {"household_id": normalized_household_id, "space_name": REGRESSION_FIXTURE_SPACE_NAME, "sublocation_name": REGRESSION_FIXTURE_SUBLOCATION_NAME},
        )
        conn.execute(
            text("DELETE FROM spaces WHERE household_id = :household_id AND lower(trim(naam)) = lower(:space_name) AND id NOT IN (SELECT DISTINCT space_id FROM inventory WHERE space_id IS NOT NULL)"),
            {"household_id": normalized_household_id, "space_name": REGRESSION_FIXTURE_SPACE_NAME},
        )
        inventory_count = conn.execute(
            text("SELECT COUNT(*) FROM inventory WHERE household_id = :household_id AND COALESCE(status, 'active') = 'active' AND COALESCE(aantal, 0) > 0"),
            {"household_id": normalized_household_id},
        ).scalar() or 0
        history_count = conn.execute(
            text("SELECT COUNT(*) FROM inventory_events WHERE household_id = :household_id"),
            {"household_id": normalized_household_id},
        ).scalar() or 0
    payload = {
        "inventory_count": int(inventory_count),
        "history_count": int(history_count),
    }
    log_regression_action('fixture.cleanup_inventory', household_id=normalized_household_id, **payload)
    return payload


def cleanup_regression_fixture_state(household_id: str) -> dict:
    normalized_household_id = str(household_id or '').strip() or '1'
    receipt_cleanup = clear_regression_receipt_state(normalized_household_id)
    inventory_cleanup = cleanup_regression_inventory_state(normalized_household_id)
    payload = {
        "status": "ok",
        "household_id": normalized_household_id,
        "inventory_count": int(inventory_cleanup.get('inventory_count', 0)),
        "history_count": int(inventory_cleanup.get('history_count', 0)),
        "receipt_cleanup": receipt_cleanup,
    }
    log_regression_action('fixture.cleanup', **payload)
    return payload


def reset_dev_tables():
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM purchase_import_lines"))
        conn.execute(text("DELETE FROM purchase_import_batches"))
        conn.execute(text("DELETE FROM household_store_connections"))
        conn.execute(text("DELETE FROM store_import_memory"))
        conn.execute(text("DELETE FROM inventory_events"))
        conn.execute(text("DELETE FROM household_articles"))
        conn.execute(text("DELETE FROM inventory"))
        conn.execute(text("DELETE FROM sublocations"))
        conn.execute(text("DELETE FROM spaces"))

def count_table(table_name: str) -> int:
    with engine.begin() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar() or 0

@app.get("/api/dev/status")
def get_dev_status(authorization: Optional[str] = Header(None)):
    require_platform_admin_user(authorization)
    return {
        "spaces": count_table("spaces"),
        "sublocations": count_table("sublocations"),
        "inventory": count_table("inventory"),
    }

@app.post("/api/dev/browser-regression/reset-fixture")
def reset_browser_regression_fixture(authorization: Optional[str] = Header(None)):
    require_platform_admin_user(authorization)
    with engine.begin() as conn:
        fixture_names = [str(item['naam']).strip().lower() for item in BROWSER_REGRESSION_ARTICLES]
        conn.execute(
            text("DELETE FROM inventory_events WHERE household_id = :household_id AND (source = 'browser_regression_fixture' OR note = :note)"),
            {"household_id": BROWSER_REGRESSION_HOUSEHOLD_ID, "note": BROWSER_REGRESSION_NOTE},
        )
        conn.execute(
            text(
                """
                DELETE FROM inventory
                WHERE household_id = :household_id
                  AND lower(trim(naam)) IN :names
                  AND space_id IN (
                    SELECT id FROM spaces
                    WHERE household_id = :household_id
                      AND lower(trim(naam)) IN (lower(trim(:pantry_space)), lower(trim(:workspace_space)))
                  )
                """
            ).bindparams(bindparam('names', expanding=True)),
            {
                "household_id": BROWSER_REGRESSION_HOUSEHOLD_ID,
                "names": fixture_names,
                "pantry_space": BROWSER_REGRESSION_SPACE_NAME,
                "workspace_space": BROWSER_REGRESSION_WORKSPACE_NAME,
            },
        )
        conn.execute(
            text("DELETE FROM sublocations WHERE id IN (SELECT sl.id FROM sublocations sl JOIN spaces s ON s.id = sl.space_id WHERE s.household_id = :household_id AND ((lower(trim(s.naam)) = lower(trim(:pantry_space)) AND lower(trim(sl.naam)) = lower(trim(:pantry_sublocation))) OR (lower(trim(s.naam)) = lower(trim(:workspace_space)) AND lower(trim(sl.naam)) = lower(trim(:workspace_sublocation)))))"),
            {"household_id": BROWSER_REGRESSION_HOUSEHOLD_ID, "pantry_space": BROWSER_REGRESSION_SPACE_NAME, "pantry_sublocation": BROWSER_REGRESSION_SUBLOCATION_NAME, "workspace_space": BROWSER_REGRESSION_WORKSPACE_NAME, "workspace_sublocation": BROWSER_REGRESSION_WORKSPACE_SUBLOCATION_NAME},
        )
        conn.execute(
            text("DELETE FROM spaces WHERE household_id = :household_id AND lower(trim(naam)) IN (lower(trim(:pantry_space)), lower(trim(:workspace_space))) AND id NOT IN (SELECT DISTINCT space_id FROM inventory WHERE space_id IS NOT NULL)"),
            {"household_id": BROWSER_REGRESSION_HOUSEHOLD_ID, "pantry_space": BROWSER_REGRESSION_SPACE_NAME, "workspace_space": BROWSER_REGRESSION_WORKSPACE_NAME},
        )

        kitchen_id = conn.execute(
            text("SELECT id FROM spaces WHERE household_id = :household_id AND lower(trim(naam)) = lower(trim(:naam)) LIMIT 1"),
            {"household_id": BROWSER_REGRESSION_HOUSEHOLD_ID, "naam": BROWSER_REGRESSION_WORKSPACE_NAME},
        ).scalar()
        if not kitchen_id:
            kitchen_id = conn.execute(
                text("INSERT INTO spaces (id, naam, household_id) VALUES (lower(hex(randomblob(16))), :naam, :household_id) RETURNING id"),
                {"naam": BROWSER_REGRESSION_WORKSPACE_NAME, "household_id": BROWSER_REGRESSION_HOUSEHOLD_ID},
            ).scalar_one()
        workbench_id = conn.execute(
            text("SELECT id FROM sublocations WHERE space_id = :space_id AND lower(trim(naam)) = lower(trim(:naam)) LIMIT 1"),
            {"space_id": kitchen_id, "naam": BROWSER_REGRESSION_WORKSPACE_SUBLOCATION_NAME},
        ).scalar()
        if not workbench_id:
            workbench_id = conn.execute(
                text("INSERT INTO sublocations (id, naam, space_id) VALUES (lower(hex(randomblob(16))), :naam, :space_id) RETURNING id"),
                {"naam": BROWSER_REGRESSION_WORKSPACE_SUBLOCATION_NAME, "space_id": kitchen_id},
            ).scalar_one()

        pantry_id = conn.execute(
            text("SELECT id FROM spaces WHERE household_id = :household_id AND lower(trim(naam)) = lower(trim(:naam)) LIMIT 1"),
            {"household_id": BROWSER_REGRESSION_HOUSEHOLD_ID, "naam": BROWSER_REGRESSION_SPACE_NAME},
        ).scalar()
        if not pantry_id:
            pantry_id = conn.execute(
                text("INSERT INTO spaces (id, naam, household_id) VALUES (lower(hex(randomblob(16))), :naam, :household_id) RETURNING id"),
                {"naam": BROWSER_REGRESSION_SPACE_NAME, "household_id": BROWSER_REGRESSION_HOUSEHOLD_ID},
            ).scalar_one()
        shelf_id = conn.execute(
            text("SELECT id FROM sublocations WHERE space_id = :space_id AND lower(trim(naam)) = lower(trim(:naam)) LIMIT 1"),
            {"space_id": pantry_id, "naam": BROWSER_REGRESSION_SUBLOCATION_NAME},
        ).scalar()
        if not shelf_id:
            shelf_id = conn.execute(
                text("INSERT INTO sublocations (id, naam, space_id) VALUES (lower(hex(randomblob(16))), :naam, :space_id) RETURNING id"),
                {"naam": BROWSER_REGRESSION_SUBLOCATION_NAME, "space_id": pantry_id},
            ).scalar_one()

        created_rows = []
        for item in BROWSER_REGRESSION_ARTICLES:
            target_space_id = pantry_id if item['space_name'] == BROWSER_REGRESSION_SPACE_NAME else kitchen_id
            target_sublocation_id = shelf_id if item['sublocation_name'] == BROWSER_REGRESSION_SUBLOCATION_NAME else workbench_id
            inventory_id = conn.execute(
                text(
                    """
                    INSERT INTO inventory (id, naam, aantal, household_id, space_id, sublocation_id, status, updated_at)
                    VALUES (lower(hex(randomblob(16))), :naam, :aantal, :household_id, :space_id, :sublocation_id, 'active', CURRENT_TIMESTAMP)
                    RETURNING id
                    """
                ),
                {
                    "naam": item['naam'],
                    "aantal": int(item['aantal']),
                    "household_id": BROWSER_REGRESSION_HOUSEHOLD_ID,
                    "space_id": target_space_id,
                    "sublocation_id": target_sublocation_id,
                },
            ).scalar_one()
            create_inventory_event(
                conn,
                household_id=BROWSER_REGRESSION_HOUSEHOLD_ID,
                article_id=inventory_id,
                article_name=item['naam'],
                resolved_location={
                    'location_id': target_sublocation_id or target_space_id,
                    'space_id': target_space_id,
                    'sublocation_id': target_sublocation_id,
                    'location_label': ' / '.join(part for part in [item['space_name'], item['sublocation_name']] if part),
                },
                event_type='purchase',
                quantity=int(item['aantal']),
                source='browser_regression_fixture',
                note=BROWSER_REGRESSION_NOTE,
                old_quantity=0,
                new_quantity=int(item['aantal']),
            )
            created_rows.append({
                'id': str(inventory_id),
                'naam': item['naam'],
                'aantal': int(item['aantal']),
                'space_name': item['space_name'],
                'sublocation_name': item['sublocation_name'],
            })

    payload = {
        'status': 'ok',
        'dataset': 'browser_regression_fixture',
        'household_id': BROWSER_REGRESSION_HOUSEHOLD_ID,
        'kitchen_id': str(kitchen_id),
        'workbench_id': str(workbench_id),
        'pantry_id': str(pantry_id),
        'shelf_id': str(shelf_id),
        'deterministic_articles': created_rows,
    }
    log_regression_action('fixture.browser_reset', **payload)
    return payload

@app.post("/api/dev/reset-data")
def reset_data():
    reset_dev_tables()
    return {"status": "ok"}


@app.post("/api/dev/diagnostics/store-location-options")
def run_store_location_diagnostic(payload: DiagnosticRequest):
    effective_household_id = str(payload.household_id or 'demo-household')
    test_space_name = f"ZZ diagnose ruimte {uuid.uuid4().hex[:6]}"
    test_sublocation_name = f"ZZ diagnose sub {uuid.uuid4().hex[:6]}"

    with engine.begin() as conn:
        space_row = conn.execute(
            text("INSERT INTO spaces (id, naam, household_id) VALUES (lower(hex(randomblob(16))), :naam, :household_id) RETURNING id"),
            {"naam": test_space_name, "household_id": effective_household_id},
        ).first()
        space_id = space_row[0] if space_row else None
        sub_row = conn.execute(
            text("INSERT INTO sublocations (id, naam, space_id) VALUES (lower(hex(randomblob(16))), :naam, :space_id) RETURNING id"),
            {"naam": test_sublocation_name, "space_id": space_id},
        ).first()
        sublocation_id = sub_row[0] if sub_row else None

        options = conn.execute(
            text(
                """
                SELECT
                    s.id AS space_id,
                    s.naam AS space_name,
                    s.household_id AS household_id,
                    sl.id AS sublocation_id,
                    sl.naam AS sublocation_name
                FROM spaces s
                LEFT JOIN sublocations sl ON sl.space_id = s.id
                WHERE (s.household_id = 'demo-household' OR s.household_id = :household_id)
                  AND COALESCE(s.active, 1) = 1
                ORDER BY s.naam ASC, sl.naam ASC
                """
            ),
            {"household_id": effective_household_id},
        ).mappings().all()

    expected_label = f"{test_space_name} / {test_sublocation_name}"
    labels = [f"{row['space_name']} / {row['sublocation_name']}" if row['sublocation_name'] else row['space_name'] for row in options]
    matching_option = next((row for row in options if str(row['space_id']) == str(space_id) and str(row['sublocation_id']) == str(sublocation_id)), None)

    return {
        "status": "ok",
        "household_id": effective_household_id,
        "created": {
            "space_id": space_id,
            "space_name": test_space_name,
            "sublocation_id": sublocation_id,
            "sublocation_name": test_sublocation_name,
            "expected_label": expected_label,
        },
        "visible_in_store_location_options": matching_option is not None,
        "matching_option": {
            "id": matching_option['sublocation_id'] or matching_option['space_id'],
            "label": expected_label,
            "household_id": matching_option['household_id'],
        } if matching_option else None,
        "options_count": len(options),
        "recent_labels": labels[-10:],
    }


@app.get("/api/dev/diagnostics/store-process-validation")
def run_store_process_validation_diagnostic(householdId: str = Query(...)):
    with engine.begin() as conn:
        batch = conn.execute(
            text(
                """
                SELECT id, import_status
                FROM purchase_import_batches
                WHERE household_id = :household_id
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT 1
                """
            ),
            {"household_id": effective_household_id},
        ).mappings().first()

        location_rows = conn.execute(
            text(
                """
                SELECT sl.id AS id
                FROM spaces s
                LEFT JOIN sublocations sl ON sl.space_id = s.id
                WHERE s.household_id = 'demo-household' OR s.household_id = :household_id
                """
            ),
            {"household_id": effective_household_id},
        ).mappings().all()
        valid_location_ids = {str(row['id']) for row in location_rows if row['id']}

        article_rows = get_store_review_article_options(conn)
        valid_article_ids = {str(row['id']) for row in article_rows}

        if not batch:
            return {
                "status": "ok",
                "has_batch": False,
                "message": "Geen kassabonbatch beschikbaar voor diagnose",
                "valid_location_ids_count": len(valid_location_ids),
                "valid_article_ids_count": len(valid_article_ids),
            }

        lines = conn.execute(
            text(
                """
                SELECT id, article_name_raw, review_decision, matched_household_article_id, target_location_id, processing_status
                FROM purchase_import_lines
                WHERE batch_id = :batch_id
                ORDER BY created_at ASC, id ASC
                """
            ),
            {"batch_id": batch['id']},
        ).mappings().all()

    detailed = []
    selected_count = 0
    missing_article = 0
    missing_valid_location = 0
    for line in lines:
        decision = line['review_decision'] or 'selected'
        is_selected = decision == 'selected' and (line['processing_status'] or 'pending') != 'processed'
        article_valid = bool(line['matched_household_article_id']) and str(line['matched_household_article_id']) in valid_article_ids
        location_valid = bool(line['target_location_id']) and str(line['target_location_id']) in valid_location_ids
        if is_selected:
            selected_count += 1
            if not article_valid:
                missing_article += 1
            if not location_valid:
                missing_valid_location += 1
        detailed.append({
            "line_id": line['id'],
            "article_name_raw": line['article_name_raw'],
            "review_decision": decision,
            "matched_household_article_id": line['matched_household_article_id'],
            "target_location_id": line['target_location_id'],
            "article_valid": article_valid,
            "location_valid": location_valid,
            "processing_status": line['processing_status'] or 'pending',
        })

    return {
        "status": "ok",
        "has_batch": True,
        "batch_id": batch['id'],
        "batch_status": batch['import_status'],
        "selected_lines": selected_count,
        "missing_article_count": missing_article,
        "missing_valid_location_count": missing_valid_location,
        "valid_location_ids_count": len(valid_location_ids),
        "valid_article_ids_count": len(valid_article_ids),
        "lines": detailed,
    }





@app.get("/api/articles/household-details")
def get_article_household_details(article_name: Optional[str] = None, article_id: Optional[str] = None, authorization: Optional[str] = Header(None)):
    context = require_household_context(authorization)
    household_id = str(context.get('active_household_id') or '')
    with engine.begin() as conn:
        return resolve_household_article_detail_service(conn, household_id, article_id=article_id, article_name=article_name, create_if_missing=False)


@app.get("/api/inventory/{inventory_id}/article-detail")
def get_inventory_article_detail(inventory_id: str, authorization: Optional[str] = Header(None)):
    context = require_household_context(authorization)
    household_id = str(context.get('active_household_id') or '')
    with engine.begin() as conn:
        details = get_household_article_details_for_inventory(conn, household_id, inventory_id)
        return resolve_household_article_detail_service(conn, household_id, article_id=str(details.get('household_article_id') or details.get('article_id') or ''), create_if_missing=False) | {'inventory_id': details.get('inventory_id')}


@app.get("/api/articles/product-details")
def get_article_product_details_endpoint(article_name: Optional[str] = None, article_id: Optional[str] = None, authorization: Optional[str] = Header(None)):
    context = require_household_context(authorization)
    household_id = str(context.get('active_household_id') or '')
    with engine.begin() as conn:
        details = resolve_household_article_detail_service(conn, household_id, article_id=article_id, article_name=article_name, create_if_missing=False)
        return {
            'household_article_id': str(details.get('household_article_id') or details.get('article_id') or ''),
            'article_id': str(details.get('article_id') or details.get('household_article_id') or ''),
            'article_name': details.get('article_name') or '',
            'product_details': details.get('product_details') or {},
            'product': details.get('product') or {},
        }


@app.get("/api/products/sources")
def get_product_sources(authorization: Optional[str] = Header(None)):
    require_household_context(authorization)
    return {
        'items': get_configured_product_sources(),
        'source_order': list(PRODUCT_SOURCE_ORDER),
    }


@app.post("/api/products/identify")
def identify_article_product(payload: ProductIdentifyRequest, authorization: Optional[str] = Header(None)):
    context = require_inventory_write_context(authorization, payload.household_id)
    household_id = str(context.get('active_household_id') or '')
    with engine.begin() as conn:
        article_row = get_household_article_row_by_name(conn, household_id, payload.article_name)
        if not article_row:
            raise HTTPException(status_code=404, detail='Artikel niet gevonden')
        identity = upsert_product_identity(conn, str(article_row.get('id')), 'gtin', payload.barcode, 'manual', confidence_score=1.0, is_primary=True)
        update_household_article_barcode(conn, household_id, payload.article_name, payload.barcode)
        return {
            'status': 'ok',
            'article_id': article_row.get('id'),
            'article_name': article_row.get('naam') or payload.article_name,
            'primary_identity': {
                'identity_type': identity.get('identity_type') if identity else 'gtin',
                'identity_value': identity.get('identity_value') if identity else payload.barcode,
                'source': identity.get('source') if identity else 'manual',
                'confidence_score': float(identity['confidence_score']) if identity and identity.get('confidence_score') is not None else 1.0,
                'is_primary': True,
            },
        }


@app.post("/api/products/enrich")
def enrich_article_product(payload: ProductEnrichRequest, authorization: Optional[str] = Header(None)):
    context = require_household_context(authorization, requested_household_id=payload.household_id)
    household_id = str(context.get('active_household_id') or '')
    with engine.begin() as conn:
        article_row = get_household_article_row_by_name(conn, household_id, payload.article_name)
        if not article_row:
            raise HTTPException(status_code=404, detail='Artikel niet gevonden')
        external_link = get_latest_external_article_link(conn, household_id, payload.article_name)
        barcode_value = article_row.get('barcode') or external_link.get('barcode')
        enrichment = ensure_article_product_enrichment(conn, str(article_row.get('id')), barcode_value, force_refresh=bool(payload.force_refresh))
        status = get_article_enrichment_status(conn, str(article_row.get('id')))
        return {
            'status': status.get('status') or ('found' if enrichment else 'skipped'),
            'article_id': article_row.get('id'),
            'article_name': article_row.get('naam') or payload.article_name,
            'identity': get_primary_product_identity(conn, str(article_row.get('id'))),
            'enrichment_status': status,
            'enrichment': enrichment if enrichment and enrichment.get('lookup_status') == 'found' else (enrichment if (enrichment and enrichment.get('title')) else None),
        }


@app.post("/api/products/enrich/retry")
def retry_enrich_article_product(payload: ProductEnrichRequest, authorization: Optional[str] = Header(None)):
    forced_payload = ProductEnrichRequest(household_id=payload.household_id, article_name=payload.article_name, force_refresh=True)
    return enrich_article_product(forced_payload, authorization)


@app.post("/api/articles/{article_id}/enrich")
def enrich_article_by_id(article_id: str, authorization: Optional[str] = Header(None)):
    context = require_household_context(authorization)
    household_id = str(context.get('active_household_id') or '')
    with engine.begin() as conn:
        article_row = resolve_household_article_reference(conn, household_id, article_id=article_id, create_if_missing=True)
        if not article_row:
            raise HTTPException(status_code=404, detail='Artikel niet gevonden')
    return enrich_household_article_by_id(str(article_row.get('id') or ''), authorization)


@app.patch("/api/articles/household-details")
def patch_article_household_details(payload: ArticleHouseholdDetailsUpdateRequest, article_name: Optional[str] = None, article_id: Optional[str] = None, authorization: Optional[str] = Header(None)):
    context = require_household_context(authorization)
    household_id = str(context.get('active_household_id') or '')
    with engine.begin() as conn:
        resolved_row = resolve_household_article_reference(conn, household_id, article_id=article_id, article_name=article_name, create_if_missing=True)
        if not resolved_row:
            raise HTTPException(status_code=404, detail='Artikel niet gevonden')
    return patch_household_article_details_by_id(str(resolved_row.get('id') or ''), payload, authorization)

@app.post("/api/articles/{article_id}/archive")
def archive_article_by_id_adapter(article_id: str, payload: HouseholdArticleArchiveRequest | None = None, authorization: Optional[str] = Header(None)):
    context = require_household_admin_context(authorization)
    household_id = str(context['active_household_id'])
    with engine.begin() as conn:
        article_row = resolve_household_article_reference(conn, household_id, article_id=article_id, create_if_missing=False)
        if not article_row:
            raise HTTPException(status_code=404, detail='Artikel niet gevonden')
        return archive_household_article_by_id(conn, household_id, str(article_row.get('id') or ''), (payload.reason if payload else None))


@app.delete("/api/articles/{article_id}")
def delete_article_by_id_adapter(article_id: str, payload: HouseholdArticleDeleteRequest | None = None, authorization: Optional[str] = Header(None)):
    context = require_household_admin_context(authorization)
    household_id = str(context['active_household_id'])
    with engine.begin() as conn:
        article_row = resolve_household_article_reference(conn, household_id, article_id=article_id, create_if_missing=False)
        if not article_row:
            raise HTTPException(status_code=404, detail='Artikel niet gevonden')
        return delete_household_article_by_id(conn, household_id, str(article_row.get('id') or ''), (payload.reason if payload else None), bool(payload.force) if payload else False)


@app.post("/api/inventory/{inventory_id}/external-product-link")
def update_inventory_external_product_link(inventory_id: str, payload: ArticleExternalProductLinkUpdateRequest, authorization: Optional[str] = Header(None)):
    context = require_household_context(authorization)
    display_role = str(context.get('display_role') or '').strip().lower()
    if display_role not in {'admin', 'lid'}:
        raise HTTPException(status_code=403, detail='Alleen admin en lid mogen externe productkoppelingen aanpassen')
    household_id = str(context.get('active_household_id') or '')
    normalized_reference_id = str(inventory_id or '').strip()
    with engine.begin() as conn:
        article_name = None
        if normalized_reference_id.startswith('article::'):
            article_name = normalize_household_article_name(normalized_reference_id.split('::', 1)[1])
        else:
            inventory_row = conn.execute(
                text(
                    """
                    SELECT id, naam AS article_name
                    FROM inventory
                    WHERE household_id = :household_id AND id = :inventory_id
                    LIMIT 1
                    """
                ),
                {'household_id': household_id, 'inventory_id': normalized_reference_id},
            ).mappings().first()
            if inventory_row:
                article_name = normalize_household_article_name(inventory_row.get('article_name') or '')
            else:
                household_article_row = conn.execute(
                    text(
                        """
                        SELECT id, naam
                        FROM household_articles
                        WHERE household_id = :household_id AND id = :article_id
                        LIMIT 1
                        """
                    ),
                    {'household_id': household_id, 'article_id': normalized_reference_id},
                ).mappings().first()
                if household_article_row:
                    article_name = normalize_household_article_name(household_article_row.get('naam') or '')
        if not article_name:
            raise HTTPException(status_code=404, detail='Artikel niet gevonden')
        details = update_household_article_external_link(conn, household_id, article_name, barcode=payload.barcode, article_number=payload.article_number, source='manual')
        return {'status': 'ok', 'details': details}


@app.post("/api/articles/barcode-scan")
def scan_article_barcode(payload: BarcodeLookupRequest, authorization: Optional[str] = Header(None)):
    context = require_inventory_write_context(authorization, payload.household_id)
    household_id = str(context.get("active_household_id") or "demo-household")
    with engine.begin() as conn:
        barcode_resolution = resolve_household_article_for_barcode(
            conn,
            household_id,
            payload.barcode,
            create_global_product=True,
            create_household_article=False,
        )
        article = barcode_resolution.get('article')
        catalog_match = barcode_resolution.get('catalog_match') or {}
        if article:
            article_name = str(article.get("naam") or "").strip()
            article_id = str(article.get("id") or build_live_article_option_id(article_name)).strip()
            product = dict(catalog_match.get('product') or {})
            return {
                "status": "ok",
                "found": True,
                "external_match": False,
                "barcode": payload.barcode,
                "global_product_id": barcode_resolution.get('global_product_id'),
                "lookup_status": catalog_match.get('lookup_status'),
                "article": {
                    "id": article_id,
                    "name": article_name,
                    "barcode": payload.barcode,
                    "article_number": article.get('article_number'),
                    "brand": product.get("brand") or article.get('brand_or_maker'),
                    "consumable": bool(article.get("consumable")) if article.get("consumable") is not None else infer_consumable_from_name(article_name),
                    "source": "household",
                },
                "product": product or None,
                "enrichment": catalog_match.get('enrichment'),
                "matched_via_global_product": bool(barcode_resolution.get('global_article') and not barcode_resolution.get('direct_article')),
            }
        product = dict(catalog_match.get('product') or {})
        if product:
            suggested_name = product.get('name') or normalize_household_article_name(product.get('title') or '') or None
            return {
                "status": "ok",
                "found": False,
                "external_match": catalog_match.get('lookup_status') == 'found',
                "barcode": payload.barcode,
                "global_product_id": catalog_match.get('global_product_id'),
                "lookup_status": catalog_match.get('lookup_status'),
                "article": {
                    "id": None,
                    "name": suggested_name,
                    "barcode": payload.barcode,
                    "article_number": None,
                    "brand": product.get("brand"),
                    "consumable": True,
                    "source": product.get("source") or "catalog",
                    "quantity_label": (catalog_match.get('enrichment') or {}).get("size_value"),
                    "packaging": (catalog_match.get('enrichment') or {}).get("size_unit"),
                },
                "product": product,
                "enrichment": catalog_match.get('enrichment'),
                "suggested_article_name": suggested_name,
            }
    return {
        "status": "ok",
        "found": False,
        "external_match": False,
        "barcode": payload.barcode,
        "global_product_id": None,
        "lookup_status": 'not_found',
        "article": None,
        "suggested_article_name": None,
    }


@app.post("/api/purchases/manual")
def create_manual_purchase(payload: ManualPurchaseCreateRequest, authorization: Optional[str] = Header(None)):
    context = require_inventory_write_context(authorization, payload.household_id)
    household_id = str(context.get("active_household_id") or "demo-household")
    with engine.begin() as conn:
        space_id, sublocation_id = resolve_space_and_sublocation_ids(
            conn,
            household_id,
            space_id=payload.space_id,
            sublocation_id=payload.sublocation_id,
            space_name=payload.space_name,
            sublocation_name=payload.sublocation_name,
        )
        resolved_location = build_resolved_location_payload(conn, household_id, space_id, sublocation_id)
        article_id = ensure_household_article(conn, household_id, payload.article_name)
        event_note = build_incidental_purchase_note(
            source_label="Incidentele aankoop handmatig",
            article_name=payload.article_name,
            supplier=payload.supplier,
            purchase_date=payload.purchase_date,
            price=payload.price,
            currency=payload.currency,
            article_number=payload.article_number,
            note=payload.note,
        )
        event_id = create_inventory_event(
            conn,
            household_id=household_id,
            article_id=article_id,
            article_name=payload.article_name,
            resolved_location=resolved_location,
            event_type="purchase",
            quantity=payload.quantity,
            source="manual",
            note=event_note,
            old_quantity=get_article_total_quantity(conn, household_id, payload.article_name),
            new_quantity=get_article_total_quantity(conn, household_id, payload.article_name) + int(payload.quantity),
            purchase_date=payload.purchase_date,
            supplier_name=payload.supplier,
            article_number=payload.article_number,
            price=payload.price,
            currency=payload.currency,
        )
        inventory_id = apply_inventory_purchase(conn, household_id, payload.article_name, payload.quantity, resolved_location)
        sync_household_article_price_metrics(conn, household_id, article_id, ensure_household_article_global_product_link(conn, article_id, None))
        return build_purchase_response_payload(conn, inventory_id=inventory_id, event_id=event_id, household_id=household_id)


@app.post("/api/purchases/barcode")
def create_barcode_purchase(payload: BarcodePurchaseCreateRequest, authorization: Optional[str] = Header(None)):
    context = require_inventory_write_context(authorization, payload.household_id)
    household_id = str(context.get("active_household_id") or "demo-household")
    explicit_article_name = normalize_household_article_name(payload.article_name)
    with engine.begin() as conn:
        barcode_resolution = resolve_household_article_for_barcode(
            conn,
            household_id,
            payload.barcode,
            product_name_hint=explicit_article_name,
            create_global_product=True,
            create_household_article=not explicit_article_name,
        )
        catalog_match = barcode_resolution.get('catalog_match') or {}
        existing_article = barcode_resolution.get('article')
        existing_article_name = normalize_household_article_name((existing_article or {}).get("naam")) if existing_article else ''
        suggested_catalog_name = normalize_household_article_name(((catalog_match.get('product') or {}).get('name')) or '')
        resolved_global_product_id = barcode_resolution.get('global_product_id')
        should_reuse_existing_article = bool(existing_article_name) and (not explicit_article_name or existing_article_name.lower() == explicit_article_name.lower())
        article_name = explicit_article_name or (existing_article_name if should_reuse_existing_article else '') or suggested_catalog_name
        if not article_name and resolved_global_product_id:
            created_option = ensure_household_article_for_global_product(
                conn,
                household_id,
                resolved_global_product_id,
                article_name_hint=suggested_catalog_name or explicit_article_name,
                barcode=payload.barcode,
                brand=((catalog_match.get('product') or {}).get('brand')),
            )
            if created_option and created_option.startswith('article::'):
                article_name = created_option.split('::', 1)[1]
                existing_article = get_household_article_row_by_name(conn, household_id, article_name)
                existing_article_name = article_name
        if not article_name:
            raise HTTPException(status_code=400, detail="Artikelnaam ontbreekt om op te slaan.")
        if resolved_global_product_id:
            option_id = ensure_household_article_for_global_product(
                conn,
                household_id,
                resolved_global_product_id,
                article_name_hint=article_name,
                barcode=payload.barcode,
                brand=((catalog_match.get('product') or {}).get('brand')),
            )
            if option_id and option_id.startswith('article::'):
                article_name = option_id.split('::', 1)[1]
        article_id = ensure_household_article(conn, household_id, article_name)
        if resolved_global_product_id:
            set_household_article_global_product_id(conn, article_id, resolved_global_product_id)
        barcode_linked_to_requested_article = False
        if payload.barcode:
            reassign_household_article_barcode(conn, household_id, article_name, payload.barcode)
            try:
                upsert_product_identity(conn, article_id, 'gtin', payload.barcode, 'barcode_scan', confidence_score=1.0, is_primary=True)
            except HTTPException:
                pass
            ensure_household_article_global_product_link(conn, article_id, payload.barcode)
            barcode_linked_to_requested_article = True

        space_id, sublocation_id = resolve_space_and_sublocation_ids(
            conn,
            household_id,
            space_id=payload.space_id,
            sublocation_id=payload.sublocation_id,
            space_name=payload.space_name,
            sublocation_name=payload.sublocation_name,
        )
        resolved_location = build_resolved_location_payload(conn, household_id, space_id, sublocation_id)
        old_total = get_article_total_quantity(conn, household_id, article_name)
        event_note = build_incidental_purchase_note(
            source_label="Incidentele aankoop barcode",
            article_name=article_name,
            supplier=payload.supplier,
            purchase_date=payload.purchase_date,
            price=payload.price,
            currency=payload.currency,
            barcode=payload.barcode,
            article_number=payload.article_number,
            note=payload.note,
        )
        event_id = create_inventory_event(
            conn,
            household_id=household_id,
            article_id=article_id,
            article_name=article_name,
            resolved_location=resolved_location,
            event_type="purchase",
            quantity=payload.quantity,
            source="barcode",
            note=event_note,
            old_quantity=old_total,
            new_quantity=old_total + int(payload.quantity),
            purchase_date=payload.purchase_date,
            supplier_name=payload.supplier,
            article_number=payload.article_number,
            price=payload.price,
            currency=payload.currency,
            barcode=payload.barcode,
        )
        inventory_id = apply_inventory_purchase(conn, household_id, article_name, payload.quantity, resolved_location)
        sync_household_article_price_metrics(conn, household_id, article_id, resolved_global_product_id)
        response = build_purchase_response_payload(conn, inventory_id=inventory_id, event_id=event_id, household_id=household_id)
        response["article"] = {
            "id": article_id,
            "name": article_name,
            "barcode": payload.barcode,
        }
        response["global_product_id"] = catalog_match.get('global_product_id')
        response["product_lookup_status"] = catalog_match.get('lookup_status')
        response["product"] = catalog_match.get('product')
        response["barcode_found_existing_article"] = bool(existing_article)
        response["barcode_linked_to_requested_article"] = barcode_linked_to_requested_article
        response["requested_article_name"] = explicit_article_name or None
        return response


@app.post("/api/inventory-events")
def mutate_inventory_event(payload: InventoryEventMutationRequest, authorization: Optional[str] = Header(None)):
    context = require_inventory_write_context(authorization, payload.household_id)
    household_id = str(context.get("active_household_id") or "demo-household")
    with engine.begin() as conn:
        event_type = payload.event_type

        if event_type == 'purchase':
            article_name = normalize_household_article_name(payload.article_name)
            if not article_name:
                raise HTTPException(status_code=400, detail="Artikelnaam is verplicht voor een aankoop")
            if int(payload.quantity or 0) <= 0:
                raise HTTPException(status_code=400, detail="Aantal moet groter zijn dan 0")
            space_id, sublocation_id = resolve_space_and_sublocation_ids(
                conn,
                household_id,
                space_id=payload.space_id,
                sublocation_id=payload.sublocation_id,
                space_name=payload.space_name,
                sublocation_name=payload.sublocation_name,
            )
            resolved_location = build_resolved_location_payload(conn, household_id, space_id, sublocation_id)
            old_total = get_article_total_quantity(conn, household_id, article_name)
            article_id = ensure_household_article(conn, household_id, article_name)
            event_id = create_inventory_event(
                conn,
                household_id=household_id,
                article_id=article_id,
                article_name=article_name,
                resolved_location=resolved_location,
                event_type='purchase',
                quantity=int(payload.quantity),
                old_quantity=old_total,
                new_quantity=old_total + int(payload.quantity),
                source='manual_inventory_api',
                note=(payload.note or '').strip() or 'Voorraad handmatig toegevoegd via mutatie-endpoint.',
            )
            inventory_id = apply_inventory_purchase(conn, household_id, article_name, payload.quantity, resolved_location)
            sync_household_article_price_metrics(conn, household_id, article_id, ensure_household_article_global_product_link(conn, article_id, None))
            return {
                'status': 'ok',
                'inventory': build_inventory_row_response(conn, inventory_id=inventory_id, household_id=household_id),
                'event': build_inventory_event_response(conn, event_id=event_id, household_id=household_id),
            }

        if payload.inventory_id:
            inventory_row = fetch_inventory_row(conn, inventory_id=payload.inventory_id, household_id=household_id)
            article_name = normalize_household_article_name(inventory_row.get('article_name'))
            resolved_location = build_location_payload_from_inventory_row(inventory_row)
        else:
            article_name = normalize_household_article_name(payload.article_name)
            if not article_name:
                raise HTTPException(status_code=400, detail="Artikelnaam of inventory_id is verplicht")
            space_id, sublocation_id = resolve_space_and_sublocation_ids(
                conn,
                household_id,
                space_id=payload.space_id,
                sublocation_id=payload.sublocation_id,
                space_name=payload.space_name,
                sublocation_name=payload.sublocation_name,
            )
            resolved_location = build_resolved_location_payload(conn, household_id, space_id, sublocation_id)
            inventory_row = fetch_inventory_row_by_article_and_location(
                conn,
                household_id=household_id,
                article_name=article_name,
                resolved_location=resolved_location,
            )

        old_total = get_article_total_quantity(conn, household_id, article_name)
        inventory_id = str(inventory_row['id'])
        current_row_quantity = int(inventory_row.get('quantity') or 0)

        if event_type == 'consume':
            consume_quantity = int(payload.quantity or 0)
            if consume_quantity <= 0:
                raise HTTPException(status_code=400, detail="Aantal moet groter zijn dan 0")
            updated_row = apply_inventory_row_consumption(
                conn,
                inventory_id=inventory_id,
                household_id=household_id,
                quantity=consume_quantity,
            )
            new_total = old_total - consume_quantity
            event_id = create_inventory_event(
                conn,
                household_id=household_id,
                article_id=inventory_id,
                article_name=article_name,
                resolved_location=resolved_location,
                event_type='consume',
                quantity=-consume_quantity,
                old_quantity=old_total,
                new_quantity=new_total,
                source='manual_inventory_api',
                note=(payload.note or '').strip() or 'Voorraad handmatig verbruikt via mutatie-endpoint.',
            )
            return {
                'status': 'ok',
                'inventory': build_inventory_row_response(conn, inventory_id=inventory_id, household_id=household_id),
                'event': build_inventory_event_response(conn, event_id=event_id, household_id=household_id),
                'article_total_quantity': new_total,
                'row_previous_quantity': current_row_quantity,
                'row_new_quantity': int(updated_row.get('quantity') or 0),
            }

        adjusted_quantity = int(payload.quantity)
        update_inventory_row_quantity(conn, inventory_id=inventory_id, new_quantity=adjusted_quantity)
        if adjusted_quantity == 0:
            delete_inventory_row_if_empty(conn, inventory_id=inventory_id)
        new_total = old_total - current_row_quantity + adjusted_quantity
        event_id = create_inventory_event(
            conn,
            household_id=household_id,
            article_id=inventory_id,
            article_name=article_name,
            resolved_location=resolved_location,
            event_type='manual_adjustment',
            quantity=adjusted_quantity - current_row_quantity,
            old_quantity=old_total,
            new_quantity=new_total,
            source='manual_inventory_api',
            note=(payload.note or '').strip() or 'Voorraad handmatig aangepast via mutatie-endpoint.',
        )
        return {
            'status': 'ok',
            'inventory': build_inventory_row_response(conn, inventory_id=inventory_id, household_id=household_id),
            'event': build_inventory_event_response(conn, event_id=event_id, household_id=household_id),
            'article_total_quantity': new_total,
            'row_previous_quantity': current_row_quantity,
            'row_new_quantity': adjusted_quantity,
        }


@app.post("/api/inventory-transfers")
def transfer_inventory(payload: InventoryTransferRequest, authorization: Optional[str] = Header(None)):
    context = require_inventory_write_context(authorization, payload.household_id)
    household_id = str(context.get("active_household_id") or "demo-household")
    with engine.begin() as conn:
        if payload.inventory_id:
            source_row = fetch_inventory_row(conn, inventory_id=payload.inventory_id, household_id=household_id)
            article_name = normalize_household_article_name(source_row.get('article_name'))
            source_location = build_location_payload_from_inventory_row(source_row)
        else:
            article_name = normalize_household_article_name(payload.article_name)
            if not article_name:
                raise HTTPException(status_code=400, detail="Artikelnaam of inventory_id is verplicht voor een verplaatsing")
            from_space_id, from_sublocation_id = resolve_space_and_sublocation_ids(
                conn,
                household_id,
                space_id=payload.from_space_id,
                sublocation_id=payload.from_sublocation_id,
                space_name=payload.from_space_name,
                sublocation_name=payload.from_sublocation_name,
            )
            source_location = build_resolved_location_payload(conn, household_id, from_space_id, from_sublocation_id)
            source_row = fetch_inventory_row_by_article_and_location(
                conn,
                household_id=household_id,
                article_name=article_name,
                resolved_location=source_location,
            )

        to_space_id, to_sublocation_id = resolve_space_and_sublocation_ids(
            conn,
            household_id,
            space_id=payload.to_space_id,
            sublocation_id=payload.to_sublocation_id,
            space_name=payload.to_space_name,
            sublocation_name=payload.to_sublocation_name,
        )
        target_location = build_resolved_location_payload(conn, household_id, to_space_id, to_sublocation_id)
        if str(source_location.get('space_id') or '') == str(target_location.get('space_id') or '') and str(source_location.get('sublocation_id') or '') == str(target_location.get('sublocation_id') or ''):
            raise HTTPException(status_code=400, detail="Bron- en doellocatie zijn gelijk")

        transfer_quantity = int(payload.quantity or 0)
        current_source_quantity = int(source_row.get('quantity') or 0)
        if transfer_quantity <= 0:
            raise HTTPException(status_code=400, detail="Aantal moet groter zijn dan 0")
        if transfer_quantity > current_source_quantity:
            raise HTTPException(status_code=400, detail="Verplaatsing zou negatieve voorraad veroorzaken")

        old_total = get_article_total_quantity(conn, household_id, article_name)
        updated_source = apply_inventory_row_consumption(
            conn,
            inventory_id=str(source_row['id']),
            household_id=household_id,
            quantity=transfer_quantity,
        )
        target_inventory_id = apply_inventory_purchase(conn, household_id, article_name, transfer_quantity, target_location)
        note_prefix = (payload.note or '').strip()
        source_note = f"Verplaatst naar {target_location.get('location_label') or 'doellocatie'}"
        target_note = f"Verplaatst vanuit {source_location.get('location_label') or 'bronlocatie'}"
        if note_prefix:
            source_note = f"{source_note} — {note_prefix}"
            target_note = f"{target_note} — {note_prefix}"
        source_event_id = create_inventory_event(
            conn,
            household_id=household_id,
            article_id=str(source_row['id']),
            article_name=article_name,
            resolved_location=source_location,
            event_type='transfer_out',
            quantity=-transfer_quantity,
            old_quantity=old_total,
            new_quantity=old_total,
            source='manual_inventory_api',
            note=source_note,
        )
        target_event_id = create_inventory_event(
            conn,
            household_id=household_id,
            article_id=str(target_inventory_id),
            article_name=article_name,
            resolved_location=target_location,
            event_type='transfer_in',
            quantity=transfer_quantity,
            old_quantity=old_total,
            new_quantity=old_total,
            source='manual_inventory_api',
            note=target_note,
        )
        return {
            'status': 'ok',
            'article_name': article_name,
            'article_total_quantity': old_total,
            'source_inventory': build_inventory_row_response(conn, inventory_id=str(source_row['id']), household_id=household_id),
            'target_inventory': build_inventory_row_response(conn, inventory_id=str(target_inventory_id), household_id=household_id),
            'events': [
                build_inventory_event_response(conn, event_id=source_event_id, household_id=household_id),
                build_inventory_event_response(conn, event_id=target_event_id, household_id=household_id),
            ],
        }




@app.post("/api/dev/spaces")
def create_space(payload: SpaceCreate, authorization: Optional[str] = Header(None)):
    require_platform_admin_user(authorization)
    household_id = (payload.household_id or 'demo-household').strip() if payload.household_id else 'demo-household'
    with engine.begin() as conn:
        result = conn.execute(
            text("INSERT INTO spaces (id, naam, household_id) VALUES (lower(hex(randomblob(16))), :naam, :household_id) RETURNING id"),
            {"naam": payload.naam, "household_id": household_id},
        )
        row = result.first()
    return {"status": "ok", "id": row[0] if row else None, "household_id": household_id}

@app.post("/api/dev/sublocations")
def create_sublocation(payload: SublocationCreate, authorization: Optional[str] = Header(None)):
    require_platform_admin_user(authorization)
    with engine.begin() as conn:
        # validate parent space
        exists = conn.execute(
            text("SELECT id FROM spaces WHERE id = :id"),
            {"id": payload.space_id},
        ).first()
        if not exists:
            raise HTTPException(status_code=400, detail="Onbekende space_id")
        result = conn.execute(
            text("INSERT INTO sublocations (id, naam, space_id) VALUES (lower(hex(randomblob(16))), :naam, :space_id) RETURNING id"),
            {"naam": payload.naam, "space_id": payload.space_id},
        )
        row = result.first()
    return {"status": "ok", "id": row[0] if row else None}

@app.post("/api/dev/inventory")
def create_inventory(payload: InventoryCreate, authorization: Optional[str] = Header(None)):
    require_platform_admin_user(authorization)
    with engine.begin() as conn:
        space_id, sublocation_id = resolve_space_and_sublocation_ids(
            conn,
            'demo-household',
            space_id=payload.space_id,
            sublocation_id=payload.sublocation_id,
        )

        result = conn.execute(
            text("""
            INSERT INTO inventory (id, naam, aantal, household_id, space_id, sublocation_id)
            VALUES (lower(hex(randomblob(16))), :naam, :aantal, 'demo-household', :space_id, :sublocation_id)
            RETURNING id
            """),
            {
                "naam": payload.naam,
                "aantal": payload.aantal,
                "space_id": space_id,
                "sublocation_id": sublocation_id,
            },
        )
        row = result.first()
        new_id = row[0] if row else None
        if new_id:
            resolved_location = conn.execute(
                text(
                    """
                    SELECT COALESCE(s.naam, '') AS locatie, COALESCE(sl.naam, '') AS sublocatie
                    FROM spaces s
                    LEFT JOIN sublocations sl ON sl.id = :sublocation_id
                    WHERE s.id = :space_id
                    """
                ),
                {"space_id": space_id, "sublocation_id": sublocation_id},
            ).mappings().first() or {}
            location_label = ' / '.join(part for part in [resolved_location.get('locatie', ''), resolved_location.get('sublocatie', '')] if part)
            seed_inventory_event(
                conn,
                article_name=payload.naam,
                quantity=int(payload.aantal or 0),
                old_quantity=0,
                new_quantity=int(payload.aantal or 0),
                event_type='purchase',
                source='manual_seed',
                note='Voorraadregel aangemaakt',
                location_id=sublocation_id or space_id,
                location_label=location_label,
            )
    return {"status": "ok", "id": new_id if row else None}


@app.put("/api/dev/inventory/{inventory_id}")
def update_inventory(inventory_id: str, payload: InventoryUpdate, authorization: Optional[str] = Header(None)):
    require_platform_admin_user(authorization)
    with engine.begin() as conn:
        existing = conn.execute(
            text(
                """
                SELECT
                  i.id,
                  i.household_id,
                  i.naam,
                  i.aantal,
                  i.space_id,
                  i.sublocation_id,
                  COALESCE(s.naam, '') AS locatie,
                  COALESCE(sl.naam, '') AS sublocatie
                FROM inventory i
                LEFT JOIN spaces s ON s.id = i.space_id
                LEFT JOIN sublocations sl ON sl.id = i.sublocation_id
                WHERE i.id = :id
                """
            ),
            {"id": inventory_id},
        ).mappings().first()
        if not existing:
            raise HTTPException(status_code=404, detail="Onbekende inventory-regel")

        household_id = existing.get('household_id') or 'demo-household'
        old_quantity = int(existing.get('aantal') or 0)
        new_quantity = int(payload.aantal or 0)

        space_id, sublocation_id = resolve_space_and_sublocation_ids(
            conn,
            household_id,
            space_id=payload.space_id,
            sublocation_id=payload.sublocation_id,
            space_name=payload.space_name,
            sublocation_name=payload.sublocation_name,
        )

        updated_row, event_id = apply_manual_inventory_adjustment(
            conn,
            inventory_id=inventory_id,
            household_id=household_id,
            old_article_name=existing.get('naam') or payload.naam,
            new_article_name=payload.naam,
            old_quantity=old_quantity,
            new_quantity=new_quantity,
            resolved_location={
                'space_id': space_id,
                'sublocation_id': sublocation_id,
                'location_id': sublocation_id or space_id,
                'location_label': ' / '.join(part for part in [
                    payload.space_name or existing.get('locatie') or '',
                    payload.sublocation_name or existing.get('sublocatie') or '',
                ] if part),
            },
        )
    return updated_row

@app.post("/api/dev/articles/archive")
def archive_article(payload: ArticleArchiveRequest, authorization: Optional[str] = Header(None)):
    require_platform_admin_user(authorization)
    article_name = (payload.article_name or "").strip()
    if not article_name:
        raise HTTPException(status_code=400, detail="article_name is verplicht")

    reason = (payload.reason or "").strip() or "Handmatig gearchiveerd vanuit Artikeldetail"
    effective_household_id = get_request_household_id(authorization)

    with engine.begin() as conn:
        article_row = get_household_article_row_by_name(conn, effective_household_id, article_name)
        if not article_row:
            raise HTTPException(status_code=404, detail="Geen actief artikel gevonden om te archiveren")
        return archive_household_article_by_id(conn, effective_household_id, str(article_row.get('id') or ''), reason)


@app.get("/api/dev/inventory-preview")
def inventory_preview(response: Response, authorization: Optional[str] = Header(None)):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    effective_household_id = get_request_household_id(authorization)
    with engine.begin() as conn:
        rows = conn.execute(
            text("""
            SELECT
              i.id,
              i.naam AS artikel,
              i.aantal AS aantal,
              i.space_id AS space_id,
              i.sublocation_id AS sublocation_id,
              ha.id AS household_article_id,
              COALESCE(ha.custom_name, i.naam, '') AS household_article_name,
              COALESCE(gp.name, ha.naam, i.naam, '') AS product_name,
              COALESCE(s.naam, '') AS locatie,
              COALESCE(sl.naam, '') AS sublocatie,
              COALESCE(i.status, 'active') AS status
            FROM inventory i
            LEFT JOIN spaces s ON s.id = i.space_id
            LEFT JOIN sublocations sl ON sl.id = i.sublocation_id
            LEFT JOIN household_articles ha ON ha.household_id = i.household_id AND lower(trim(ha.naam)) = lower(trim(i.naam))
            LEFT JOIN global_products gp ON gp.id = ha.global_product_id
            WHERE i.household_id = :household_id
              AND COALESCE(i.status, 'active') = 'active'
              AND COALESCE(i.aantal, 0) > 0
            ORDER BY i.updated_at DESC, i.created_at ASC, i.id ASC
            """),
            {"household_id": effective_household_id},
        ).mappings().all()
    return {"rows": [dict(r) for r in rows]}



@app.get("/api/dev/article-history")
def article_history(article_name: str, authorization: Optional[str] = Header(None)):
    article_name = (article_name or "").strip()
    if not article_name:
        raise HTTPException(status_code=400, detail="article_name is verplicht")

    effective_household_id = get_request_household_id(authorization)
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                  id,
                  article_id,
                  article_name,
                  location_id,
                  location_label,
                  event_type,
                  quantity,
                  old_quantity,
                  new_quantity,
                  source,
                  note,
                  created_at
                FROM inventory_events
                WHERE household_id = :household_id
                  AND lower(article_name) = lower(:article_name)
                ORDER BY datetime(created_at) DESC, id DESC
                """
            ),
            {"article_name": article_name, "household_id": effective_household_id},
        ).mappings().all()

    return {"rows": [
        {
            "id": row["id"],
            "article_id": row["article_id"],
            "article_name": row["article_name"],
            "location_id": row["location_id"],
            "location_label": row["location_label"],
            "event_type": row["event_type"],
            "quantity": row["quantity"],
            "old_quantity": row["old_quantity"],
            "new_quantity": row["new_quantity"],
            "source": row["source"],
            "note": row["note"],
            "created_at": normalize_datetime(row["created_at"]),
        }
        for row in rows
    ]}




def seed_inventory_event(conn, *, article_name: str, quantity: int, old_quantity: int, new_quantity: int, event_type: str = 'purchase', source: str = 'seed_demo', note: str = 'Initiële demodata', location_id: str | None = None, location_label: str = ''):
    conn.execute(
        text(
            """
            INSERT INTO inventory_events (
              id, household_id, article_id, article_name, location_id, location_label, event_type, quantity, old_quantity, new_quantity, source, note
            ) VALUES (
              lower(hex(randomblob(16))), 'demo-household', :article_id, :article_name, :location_id, :location_label, :event_type, :quantity, :old_quantity, :new_quantity, :source, :note
            )
            """
        ),
        {
            'article_id': build_live_article_option_id(article_name),
            'article_name': article_name,
            'location_id': location_id or '',
            'location_label': location_label,
            'event_type': event_type,
            'quantity': quantity,
            'old_quantity': old_quantity,
            'new_quantity': new_quantity,
            'source': source,
            'note': note,
        },
    )

@app.post("/api/dev/generate-demo-data")
def generate_demo_data(authorization: Optional[str] = Header(None)):
    require_platform_admin_user(authorization)
    reset_dev_tables()

    with engine.begin() as conn:
        kitchen_id = conn.execute(
            text("INSERT INTO spaces (id, naam, household_id) VALUES (lower(hex(randomblob(16))), 'Keuken', 'demo-household') RETURNING id")
        ).scalar_one()
        pantry_id = conn.execute(
            text("INSERT INTO spaces (id, naam, household_id) VALUES (lower(hex(randomblob(16))), 'Berging', 'demo-household') RETURNING id")
        ).scalar_one()
        bathroom_id = conn.execute(
            text("INSERT INTO spaces (id, naam, household_id) VALUES (lower(hex(randomblob(16))), 'Badkamer', 'demo-household') RETURNING id")
        ).scalar_one()

        kast1_id = conn.execute(
            text("INSERT INTO sublocations (id, naam, space_id) VALUES (lower(hex(randomblob(16))), 'Kast 1', :space_id) RETURNING id"),
            {"space_id": kitchen_id},
        ).scalar_one()
        koelkast_id = conn.execute(
            text("INSERT INTO sublocations (id, naam, space_id) VALUES (lower(hex(randomblob(16))), 'Koelkast', :space_id) RETURNING id"),
            {"space_id": kitchen_id},
        ).scalar_one()
        voorraadkast_id = conn.execute(
            text("INSERT INTO sublocations (id, naam, space_id) VALUES (lower(hex(randomblob(16))), 'Voorraadkast', :space_id) RETURNING id"),
            {"space_id": pantry_id},
        ).scalar_one()
        diepvries_id = conn.execute(
            text("INSERT INTO sublocations (id, naam, space_id) VALUES (lower(hex(randomblob(16))), 'Diepvries', :space_id) RETURNING id"),
            {"space_id": pantry_id},
        ).scalar_one()
        badkamerkast_id = conn.execute(
            text("INSERT INTO sublocations (id, naam, space_id) VALUES (lower(hex(randomblob(16))), 'Kast', :space_id) RETURNING id"),
            {"space_id": bathroom_id},
        ).scalar_one()

        demo_rows = [
            ("Rijst", 2, kitchen_id, kast1_id),
            ("Pasta", 3, pantry_id, voorraadkast_id),
            ("Koffie", 1, kitchen_id, kast1_id),
            ("Shampoo", 4, bathroom_id, badkamerkast_id),
            ("Tomaten", 3, kitchen_id, koelkast_id),
            ("Tomaten", 2, pantry_id, voorraadkast_id),
            ("Erwten", 5, pantry_id, voorraadkast_id),
            ("IJs", 2, pantry_id, diepvries_id),
            ("Melk", 2, kitchen_id, koelkast_id),
            ("Thee", 8, kitchen_id, kast1_id),
            ("Zout", 1, kitchen_id, kast1_id),
        ]

        space_lookup = {
            kitchen_id: 'Keuken',
            pantry_id: 'Berging',
            bathroom_id: 'Badkamer',
        }
        sublocation_lookup = {
            kast1_id: 'Kast 1',
            koelkast_id: 'Koelkast',
            voorraadkast_id: 'Voorraadkast',
            diepvries_id: 'Diepvries',
            badkamerkast_id: 'Kast',
        }

        for naam, aantal, space_id, sublocation_id in demo_rows:
            conn.execute(
                text("""
                INSERT INTO inventory (id, naam, aantal, household_id, space_id, sublocation_id)
                VALUES (lower(hex(randomblob(16))), :naam, :aantal, 'demo-household', :space_id, :sublocation_id)
                """),
                {
                    "naam": naam,
                    "aantal": aantal,
                    "space_id": space_id,
                    "sublocation_id": sublocation_id,
                },
            )
            seed_inventory_event(
                conn,
                article_name=naam,
                quantity=int(aantal),
                old_quantity=0,
                new_quantity=int(aantal),
                event_type='purchase',
                source='seed_demo',
                note='Initiële demo-voorraad',
                location_id=sublocation_id or space_id,
                location_label=' / '.join(part for part in [space_lookup.get(space_id, ''), sublocation_lookup.get(sublocation_id, '')] if part),
            )

    return {
        "status": "ok",
        "spaces": count_table("spaces"),
        "sublocations": count_table("sublocations"),
        "inventory": count_table("inventory"),
    }


@app.post("/api/dev/generate-layer1-receipt-fixture")
def generate_layer1_receipt_fixture(authorization: Optional[str] = Header(None)):
    require_platform_admin_user(authorization)
    household = ensure_household("admin@rezzerv.local")
    household_id = str(household.get("id") or "1")
    clear_regression_receipt_state(household_id)
    ensure_ui_test_seed_data()

    with engine.begin() as conn:
        kitchen_kast1 = conn.execute(
            text(
                """
                SELECT sl.id
                FROM sublocations sl
                JOIN spaces s ON s.id = sl.space_id
                WHERE s.household_id = :household_id
                  AND lower(s.naam) = 'keuken'
                  AND lower(sl.naam) = 'kast 1'
                LIMIT 1
                """
            ),
            {'household_id': household_id},
        ).scalar()
        if not kitchen_kast1:
            raise HTTPException(status_code=500, detail="Layer1 receipt fixture locatie kon niet worden voorbereid")

        raw_receipt_id = str(uuid.uuid4())
        receipt_table_id = str(uuid.uuid4())
        conn.execute(
            text(
                """
                INSERT INTO raw_receipts (
                    id, household_id, source_id, original_filename, mime_type, storage_path, sha256_hash,
                    duplicate_of_raw_receipt_id, raw_status, imported_at, created_at
                ) VALUES (
                    :id, :household_id, NULL, :original_filename, :mime_type, :storage_path, :sha256_hash,
                    NULL, 'imported', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                'id': raw_receipt_id,
                'household_id': household_id,
                'original_filename': 'layer1-fixture.eml',
                'mime_type': 'message/rfc822',
                'storage_path': str((Path(__file__).resolve().parent / 'testing' / 'receipt_parsing' / 'raw' / 'Lidl2.eml').resolve()),
                'sha256_hash': f'layer1-fixture::{receipt_table_id}',
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO receipt_tables (
                    id, raw_receipt_id, household_id, store_name, store_branch, purchase_at, total_amount,
                    discount_total, currency, parse_status, confidence_score, line_count, created_at, updated_at
                ) VALUES (
                    :id, :raw_receipt_id, :household_id, 'Jumbo', 'Regressiefixture', '2026-03-25T09:00:00', 3.58,
                    0.0, 'EUR', 'parsed', 0.99, 2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                'id': receipt_table_id,
                'raw_receipt_id': raw_receipt_id,
                'household_id': household_id,
            },
        )
        receipt_lines = [
            {
                'id': str(uuid.uuid4()),
                'line_index': 1,
                'raw_label': 'Magere yoghurt',
                'quantity': 1.0,
                'unit': 'liter',
                'unit_price': 1.59,
                'line_total': 1.59,
                'discount_amount': 0.0,
            },
            {
                'id': str(uuid.uuid4()),
                'line_index': 2,
                'raw_label': 'Appelsap',
                'quantity': 1.0,
                'unit': 'liter',
                'unit_price': 1.99,
                'line_total': 1.99,
                'discount_amount': 0.0,
            },
        ]
        for line in receipt_lines:
            conn.execute(
                text(
                    """
                    INSERT INTO receipt_table_lines (
                        id, receipt_table_id, line_index, raw_label, normalized_label, quantity, unit,
                        unit_price, line_total, discount_amount, barcode, article_match_status, matched_article_id,
                        confidence_score, created_at, updated_at
                    ) VALUES (
                        :id, :receipt_table_id, :line_index, :raw_label, :normalized_label, :quantity, :unit,
                        :unit_price, :line_total, :discount_amount, NULL, 'unmatched', NULL,
                        0.99, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    'id': line['id'],
                    'receipt_table_id': receipt_table_id,
                    'line_index': line['line_index'],
                    'raw_label': line['raw_label'],
                    'normalized_label': str(line['raw_label']).strip().lower(),
                    'quantity': line['quantity'],
                    'unit': line['unit'],
                    'unit_price': line['unit_price'],
                    'line_total': line['line_total'],
                    'discount_amount': line['discount_amount'],
                },
            )

        batch_id = ensure_unpack_batch_for_receipt(conn, {
            'receipt_table_id': receipt_table_id,
            'household_id': household_id,
            'store_name': 'Jumbo',
            'purchase_at': '2026-03-25T09:00:00',
            'created_at': '2026-03-25T09:00:00',
            'currency': 'EUR',
        })

        batch_lines = conn.execute(
            text(
                """
                SELECT id, article_name_raw
                FROM purchase_import_lines
                WHERE batch_id = :batch_id
                ORDER BY ui_sort_order ASC, created_at ASC, id ASC
                """
            ),
            {'batch_id': batch_id},
        ).mappings().all()
        complete_line = next((row for row in batch_lines if str(row.get('article_name_raw') or '').strip().lower() == 'magere yoghurt'), None)
        incomplete_line = next((row for row in batch_lines if str(row.get('article_name_raw') or '').strip().lower() == 'appelsap'), None)
        if not complete_line or not incomplete_line:
            raise HTTPException(status_code=500, detail="Layer1 receipt fixture lines konden niet worden voorbereid")

        conn.execute(
            text(
                """
                UPDATE purchase_import_lines
                SET matched_household_article_id = :article_id,
                    suggested_household_article_id = :article_id,
                    target_location_id = :target_location_id,
                    suggested_location_id = :target_location_id,
                    match_status = 'matched',
                    review_decision = 'selected',
                    processing_status = 'pending',
                    suggestion_confidence = 'high',
                    suggestion_reason = 'Vaste layer1-regressiefixture',
                    is_auto_prefilled = 1,
                    article_override_mode = 'auto',
                    location_override_mode = 'auto'
                WHERE id = :line_id
                """
            ),
            {
                'line_id': str(complete_line['id']),
                'article_id': build_live_article_option_id('Melk'),
                'target_location_id': kitchen_kast1,
            },
        )
        conn.execute(
            text(
                """
                UPDATE purchase_import_lines
                SET matched_household_article_id = NULL,
                    suggested_household_article_id = NULL,
                    target_location_id = NULL,
                    suggested_location_id = NULL,
                    match_status = 'unmatched',
                    review_decision = 'selected',
                    processing_status = 'pending',
                    suggestion_confidence = NULL,
                    suggestion_reason = NULL,
                    is_auto_prefilled = 0,
                    article_override_mode = 'manual',
                    location_override_mode = 'manual'
                WHERE id = :line_id
                """
            ),
            {'line_id': str(incomplete_line['id'])},
        )
        update_batch_status(conn, batch_id)

    return {
        "householdId": household_id,
        "connectionId": '',
        "batchId": batch_id,
        "latestBatchId": batch_id,
        "completeLineId": str(complete_line['id']),
        "incompleteLineId": str(incomplete_line['id']),
    }


@app.post("/api/dev/generate-receipt-export-fixture")
def generate_receipt_export_fixture(authorization: Optional[str] = Header(None), ):
    ensure_ui_test_seed_data()

    household = ensure_household("admin@rezzerv.local")
    household_id = str(household.get("id") or "1")
    clear_regression_receipt_state(household_id)

    with engine.begin() as conn:
        connection = conn.execute(
            text(
                """
                SELECT hsc.id AS connection_id, hsc.store_provider_id
                FROM household_store_connections hsc
                JOIN store_providers sp ON sp.id = hsc.store_provider_id
                WHERE hsc.household_id = :household_id
                  AND sp.code = 'jumbo'
                ORDER BY hsc.created_at DESC, hsc.id DESC
                LIMIT 1
                """
            ),
            {"household_id": household_id},
        ).mappings().first()
        if not connection:
            raise HTTPException(status_code=500, detail="Export fixture connection kon niet worden voorbereid")

        connection_id = str(connection["connection_id"])
        store_provider_id = str(connection["store_provider_id"])
        target_location_id = conn.execute(
            text(
                """
                SELECT sl.id
                FROM sublocations sl
                JOIN spaces s ON s.id = sl.space_id
                WHERE s.household_id = :household_id
                  AND lower(s.naam) = 'keuken'
                  AND lower(sl.naam) = 'kast 1'
                LIMIT 1
                """
            ),
            {"household_id": household_id},
        ).scalar()
        if not target_location_id:
            raise HTTPException(status_code=500, detail="Export fixture locatie kon niet worden voorbereid")

        batch_id = str(uuid.uuid4())
        export_line_id = uuid.uuid4().hex
        ignored_line_id = uuid.uuid4().hex
        export_article_name = 'Export test compleet'
        ignored_article_name = 'Export test genegeerd'
        raw_payload = json.dumps({
            'mock_profile': 'export-regression-fixture',
            'provider_code': 'jumbo',
            'batch_metadata': {
                'purchase_date': '18-03-2026',
                'store_name': 'Rezzerv Testdataset',
                'store_label': 'Rezzerv Testdataset, Exportcontrole',
            },
            'lines': [
                {
                    'external_line_ref': 'export-fixture-line-1',
                    'external_article_code': 'EXPORT-FIXTURE-1',
                    'article_name_raw': export_article_name,
                    'brand_raw': 'Rezzerv Test',
                    'quantity_raw': 1,
                    'unit_raw': 'stuk',
                    'line_price_raw': 9.99,
                    'currency_code': 'EUR',
                },
                {
                    'external_line_ref': 'export-fixture-line-2',
                    'external_article_code': 'EXPORT-FIXTURE-2',
                    'article_name_raw': ignored_article_name,
                    'brand_raw': 'Rezzerv Test',
                    'quantity_raw': 1,
                    'unit_raw': 'stuk',
                    'line_price_raw': 1.11,
                    'currency_code': 'EUR',
                },
            ],
        })

        conn.execute(
            text(
                """
                INSERT INTO purchase_import_batches (
                    id, household_id, store_provider_id, connection_id, source_type, source_reference, import_status, raw_payload, created_at
                ) VALUES (
                    :id, :household_id, :store_provider_id, :connection_id, 'mock', :source_reference, 'in_review', :raw_payload, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                'id': batch_id,
                'household_id': household_id,
                'store_provider_id': store_provider_id,
                'connection_id': connection_id,
                'source_reference': 'mock:export-regression-fixture',
                'raw_payload': raw_payload,
            },
        )

        conn.execute(
            text(
                """
                INSERT INTO purchase_import_lines (
                    id, batch_id, external_line_ref, external_article_code, article_name_raw, brand_raw, quantity_raw, unit_raw, line_price_raw, currency_code,
                    match_status, review_decision, ui_sort_order, matched_household_article_id, target_location_id, processing_status,
                    suggested_household_article_id, suggested_location_id, suggestion_confidence, suggestion_reason, is_auto_prefilled,
                    article_override_mode, location_override_mode, created_at
                ) VALUES (
                    :id, :batch_id, :external_line_ref, :external_article_code, :article_name_raw, :brand_raw, :quantity_raw, :unit_raw, :line_price_raw, :currency_code,
                    'matched', 'pending', 1, :matched_household_article_id, :target_location_id, 'pending',
                    :matched_household_article_id, :target_location_id, 'high', :suggestion_reason, 1,
                    'auto', 'auto', CURRENT_TIMESTAMP
                )
                """
            ),
            {
                'id': export_line_id,
                'batch_id': batch_id,
                'external_line_ref': 'export-fixture-line-1',
                'external_article_code': 'EXPORT-FIXTURE-1',
                'article_name_raw': export_article_name,
                'brand_raw': 'Rezzerv Test',
                'quantity_raw': 1,
                'unit_raw': 'stuk',
                'line_price_raw': 9.99,
                'currency_code': 'EUR',
                'matched_household_article_id': build_live_article_option_id('Melk'),
                'target_location_id': target_location_id,
                'suggestion_reason': 'Vaste export-regressiefixture',
            },
        )

        conn.execute(
            text(
                """
                INSERT INTO purchase_import_lines (
                    id, batch_id, external_line_ref, external_article_code, article_name_raw, brand_raw, quantity_raw, unit_raw, line_price_raw, currency_code,
                    match_status, review_decision, ui_sort_order, matched_household_article_id, target_location_id, processing_status,
                    article_override_mode, location_override_mode, created_at
                ) VALUES (
                    :id, :batch_id, :external_line_ref, :external_article_code, :article_name_raw, :brand_raw, :quantity_raw, :unit_raw, :line_price_raw, :currency_code,
                    'unmatched', 'ignored', 2, NULL, NULL, 'pending',
                    'manual', 'manual', CURRENT_TIMESTAMP
                )
                """
            ),
            {
                'id': ignored_line_id,
                'batch_id': batch_id,
                'external_line_ref': 'export-fixture-line-2',
                'external_article_code': 'EXPORT-FIXTURE-2',
                'article_name_raw': ignored_article_name,
                'brand_raw': 'Rezzerv Test',
                'quantity_raw': 1,
                'unit_raw': 'stuk',
                'line_price_raw': 1.11,
                'currency_code': 'EUR',
            },
        )

        update_batch_status(conn, batch_id)

    return {
        'householdId': household_id,
        'connectionId': connection_id,
        'batchId': batch_id,
        'latestBatchId': batch_id,
        'exportLineId': export_line_id,
        'ignoredLineId': ignored_line_id,
        'exportArticleName': export_article_name,
        'sourceReference': 'mock:export-regression-fixture',
    }

@app.get("/api/dev/export-receipt-export-fixture")
def export_receipt_export_fixture(batchId: Optional[str] = Query(default=None), lineId: Optional[str] = Query(default=None)):
    fixture = None
    if not batchId or not lineId:
        fixture = generate_receipt_export_fixture()
    target_batch_id = str(batchId or (fixture or {}).get('latestBatchId') or (fixture or {}).get('batchId') or '')
    target_line_id = str(lineId or (fixture or {}).get('exportLineId') or '')
    if not target_batch_id or not target_line_id:
        raise HTTPException(status_code=500, detail='Export fixture ids ontbreken')

    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                    pil.id AS line_id,
                    pil.batch_id,
                    pil.article_name_raw,
                    pil.quantity_raw,
                    pil.unit_raw,
                    pil.line_price_raw,
                    COALESCE(ha.naam, '') AS household_article_name,
                    CASE
                        WHEN s.naam IS NOT NULL AND sl.naam IS NOT NULL THEN s.naam || ' / ' || sl.naam
                        WHEN s.naam IS NOT NULL THEN s.naam
                        ELSE ''
                    END AS location_label
                FROM purchase_import_lines pil
                LEFT JOIN household_articles ha ON ha.id = pil.matched_household_article_id
                LEFT JOIN sublocations sl ON sl.id = pil.target_location_id
                LEFT JOIN spaces s ON s.id = sl.space_id
                WHERE pil.batch_id = :batch_id AND pil.id = :line_id
                LIMIT 1
                """
            ),
            {'batch_id': target_batch_id, 'line_id': target_line_id},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail='Export fixture regel niet gevonden')

    def csv_escape(value):
        return '"' + str(value if value is not None else '').replace('"', '""') + '"'

    quantity = row['quantity_raw']
    unit = (row['unit_raw'] or '').strip()
    if quantity is None:
        quantity_label = ''
    elif isinstance(quantity, (int, float)):
        quantity_label = f"{quantity:g} {unit}".strip()
    else:
        quantity_label = f"{quantity} {unit}".strip()
    price = row['line_price_raw']
    price_label = f"{float(price):.2f}" if price is not None else ''

    header = ['Bonartikel', 'Aantal', 'Gekoppeld artikel', 'Locatie', 'Prijs', 'Status']
    data = [
        row['article_name_raw'] or '',
        quantity_label,
        row['household_article_name'] or '',
        row['location_label'] or '',
        price_label,
        'Klaar',
    ]
    csv = ';'.join(csv_escape(value) for value in header) + '\n' + ';'.join(csv_escape(value) for value in data)
    headers = {
        'Content-Disposition': 'attachment; filename="rezzerv-export-testdataset.csv"',
        'X-Rezzerv-Row-Count': '1',
        'X-Rezzerv-Source': 'receipt-export-fixture',
    }
    return Response(content=csv, media_type='text/csv; charset=utf-8', headers=headers)


@app.get("/api/store-providers")
def get_store_providers():
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, code, name, status, import_mode
                FROM store_providers
                WHERE status = 'active'
                ORDER BY name ASC
                """
            )
        ).mappings().all()
    return [dict(row) for row in rows]


@app.post("/api/store-connections")
def create_store_connection(payload: StoreConnectionCreate, authorization: Optional[str] = Header(None)):
    provider = ensure_store_provider(payload.store_provider_code)
    context = require_household_admin_context(authorization, str(payload.household_id))
    effective_household_id = str(context['active_household_id'])

    with engine.begin() as conn:
        existing = conn.execute(
            text(
                """
                SELECT hsc.id, hsc.household_id, hsc.store_provider_id, hsc.connection_status,
                       hsc.linked_at, sp.code AS store_provider_code
                FROM household_store_connections hsc
                JOIN store_providers sp ON sp.id = hsc.store_provider_id
                WHERE hsc.household_id = :household_id
                  AND hsc.store_provider_id = :store_provider_id
                """
            ),
            {
                "household_id": effective_household_id,
                "store_provider_id": provider["id"],
            },
        ).mappings().first()

        if existing:
            result = dict(existing)
            result["linked_at"] = normalize_datetime(result.get("linked_at"))
            return result

        connection_id = str(uuid.uuid4())
        conn.execute(
            text(
                """
                INSERT INTO household_store_connections (
                    id, household_id, store_provider_id, connection_status, linked_at
                ) VALUES (
                    :id, :household_id, :store_provider_id, 'active', CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "id": connection_id,
                "household_id": effective_household_id,
                "store_provider_id": provider["id"],
            },
        )
        created = conn.execute(
            text(
                """
                SELECT hsc.id, hsc.household_id, hsc.store_provider_id, hsc.connection_status,
                       hsc.linked_at, sp.code AS store_provider_code
                FROM household_store_connections hsc
                JOIN store_providers sp ON sp.id = hsc.store_provider_id
                WHERE hsc.id = :id
                """
            ),
            {"id": connection_id},
        ).mappings().first()

    result = dict(created)
    result["linked_at"] = normalize_datetime(result.get("linked_at"))
    return result


@app.get("/api/store-connections")
def get_store_connections(householdId: str = Query(...), authorization: Optional[str] = Header(None)):
    effective_household_id = resolve_authorized_household_id(authorization, householdId, require_authorization=True)
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    hsc.id,
                    hsc.household_id,
                    hsc.connection_status,
                    hsc.linked_at,
                    hsc.last_sync_at,
                    sp.code AS store_provider_code,
                    sp.name AS store_provider_name
                FROM household_store_connections hsc
                JOIN store_providers sp ON sp.id = hsc.store_provider_id
                WHERE hsc.household_id = :household_id
                ORDER BY hsc.linked_at ASC
                """
            ),
            {"household_id": effective_household_id},
        ).mappings().all()

    results = []
    for row in rows:
        item = dict(row)
        item["linked_at"] = normalize_datetime(item.get("linked_at"))
        item["last_sync_at"] = normalize_datetime(item.get("last_sync_at"))
        results.append(item)
    return results


@app.post("/api/store-connections/{connection_id}/pull-purchases")
def pull_purchases(connection_id: str, payload: PullPurchasesRequest, authorization: Optional[str] = Header(None)):
    batch_id = str(uuid.uuid4())
    now_iso = utc_now_iso()

    with engine.begin() as conn:
        connection = conn.execute(
            text(
                """
                SELECT
                    hsc.id, hsc.household_id, hsc.store_provider_id, hsc.connection_status,
                    sp.code AS store_provider_code, sp.name AS store_provider_name
                FROM household_store_connections hsc
                JOIN store_providers sp ON sp.id = hsc.store_provider_id
                WHERE hsc.id = :id
                """
            ),
            {"id": connection_id},
        ).mappings().first()

        if not connection:
            raise HTTPException(status_code=404, detail="Onbekende store connection")

        require_household_admin_context(authorization, str(connection["household_id"]))

        if connection["connection_status"] != "active":
            raise HTTPException(status_code=400, detail="Store connection is niet actief")

        lines = get_provider_mock_lines(connection["store_provider_code"], payload.mock_profile)
        batch_metadata = get_provider_mock_batch_metadata(connection["store_provider_code"], payload.mock_profile)
        raw_payload = json.dumps({"mock_profile": payload.mock_profile, "provider_code": connection["store_provider_code"], "batch_metadata": batch_metadata, "lines": lines})
        conn.execute(
            text(
                """
                INSERT INTO purchase_import_batches (
                    id, household_id, store_provider_id, connection_id, source_type,
                    source_reference, import_status, raw_payload, created_at
                ) VALUES (
                    :id, :household_id, :store_provider_id, :connection_id, 'mock',
                    :source_reference, 'new', :raw_payload, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "id": batch_id,
                "household_id": connection["household_id"],
                "store_provider_id": connection["store_provider_id"],
                "connection_id": connection_id,
                "source_reference": f"mock:{payload.mock_profile}",
                "raw_payload": raw_payload,
            },
        )

        for line in lines:
            conn.execute(
                text(
                    """
                    INSERT INTO purchase_import_lines (
                        id, batch_id, external_line_ref, external_article_code, article_name_raw,
                        brand_raw, quantity_raw, unit_raw, line_price_raw, currency_code,
                        match_status, review_decision, ui_sort_order, created_at
                    ) VALUES (
                        :id, :batch_id, :external_line_ref, :external_article_code, :article_name_raw,
                        :brand_raw, :quantity_raw, :unit_raw, :line_price_raw, :currency_code,
                        'unmatched', 'selected', :ui_sort_order, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "batch_id": batch_id,
                    "ui_sort_order": lines.index(line) + 1,
                    **line,
                },
            )

        prefill_summary = apply_prefill_to_batch(conn, batch_id, str(connection["household_id"]), connection["store_provider_code"])

        conn.execute(
            text(
                """
                UPDATE household_store_connections
                SET last_sync_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {"id": connection_id},
        )

    return {
        "batch_id": batch_id,
        "connection_id": connection_id,
        "store_provider_code": connection["store_provider_code"],
        "store_provider_name": connection["store_provider_name"],
        "source_type": "mock",
        "import_status": "new",
        "line_count": len(lines),
        "created_at": now_iso,
        "purchase_date": batch_metadata["purchase_date"],
        "store_name": batch_metadata["store_name"],
        "store_label": batch_metadata["store_label"],
        "prefill_summary": prefill_summary,
    }


@app.get("/api/purchase-import-batches/{batch_id}")
def get_purchase_import_batch(batch_id: str):
    with engine.begin() as conn:
        batch = conn.execute(
            text(
                """
                SELECT
                    pib.id AS batch_id,
                    pib.household_id,
                    sp.code AS store_provider_code,
                    sp.name AS store_provider_name,
                    pib.connection_id,
                    pib.source_type,
                    pib.source_reference,
                    pib.import_status,
                    pib.raw_payload,
                    pib.created_at
                FROM purchase_import_batches pib
                JOIN store_providers sp ON sp.id = pib.store_provider_id
                WHERE pib.id = :id
                """
            ),
            {"id": batch_id},
        ).mappings().first()

        if not batch:
            raise HTTPException(status_code=404, detail="Onbekende purchase import batch")

        batch = dict(batch)
        if batch["source_type"] == "receipt":
            receipt_table_id = str(batch.get("source_reference") or "")
            if receipt_table_id.startswith("receipt:"):
                receipt_table_id = receipt_table_id.split(":", 1)[1].strip()
            if receipt_table_id:
                receipt_header = conn.execute(
                    text("""
                    SELECT id AS receipt_table_id, household_id, store_name, store_branch, purchase_at, created_at, currency
                    FROM receipt_tables
                    WHERE id = :id
                    LIMIT 1
                    """),
                    {"id": receipt_table_id},
                ).mappings().first()
                if receipt_header:
                    sync_unpack_batch_lines_for_receipt(conn, batch_id, dict(receipt_header))
        if batch["import_status"] != "processed":
            refresh_batch_status = update_batch_status(conn, batch_id)
            batch["import_status"] = refresh_batch_status

        batch["store_import_simplification_level"] = get_household_store_import_simplification_level(conn, str(batch["household_id"]))

        lines = conn.execute(
            text(
                """
                SELECT
                    id, article_name_raw, brand_raw, quantity_raw, unit_raw,
                    line_price_raw, currency_code, match_status, review_decision,
                    matched_household_article_id, target_location_id,
                    suggested_household_article_id, suggested_location_id, suggestion_confidence, suggestion_reason, is_auto_prefilled,
                    article_override_mode, location_override_mode,
                    processing_status, processed_at, processed_event_id, processing_error, final_location_id
                FROM purchase_import_lines
                WHERE batch_id = :batch_id
                ORDER BY COALESCE(ui_sort_order, 999999), created_at ASC, id ASC
                """
            ),
            {"batch_id": batch_id},
        ).mappings().all()

    batch_result = dict(batch)
    raw_payload = {}
    try:
        raw_payload = json.loads(batch_result.get("raw_payload") or "{}")
    except Exception:
        raw_payload = {}
    batch_metadata = raw_payload.get("batch_metadata") or get_provider_mock_batch_metadata(batch_result.get("store_provider_code"), "default")
    batch_result["created_at"] = normalize_datetime(batch_result.get("created_at"))
    batch_result["purchase_date"] = batch_metadata.get("purchase_date")
    batch_result["store_name"] = batch_metadata.get("store_name") or batch_result.get("store_provider_name")
    batch_result["store_label"] = batch_metadata.get("store_label") or batch_result.get("store_provider_name")
    def build_line_explanation(line):
        article_from_memory = bool(line.get("suggested_household_article_id"))
        location_from_memory = bool(line.get("suggested_location_id"))
        memory_found = article_from_memory or location_from_memory
        simplification_level = batch_result.get("store_import_simplification_level") or "gebalanceerd"
        simplification_label = {
            "voorzichtig": "Voorzichtig",
            "gebalanceerd": "Gebalanceerd",
            "maximaal_gemak": "Maximaal gemak",
        }.get(simplification_level, "Gebalanceerd")

        if line.get("is_auto_prefilled") and line.get("matched_household_article_id") and line.get("target_location_id"):
            preparation_mode = "auto_ready"
        elif memory_found and (line.get('article_override_mode') or 'auto') == 'auto' and (line.get('location_override_mode') or 'auto') == 'auto':
            preparation_mode = "suggest_only"
        else:
            preparation_mode = "none"

        if article_from_memory and location_from_memory:
            memory_text = "Eerdere mapping gevonden: artikel + locatie"
        elif article_from_memory:
            memory_text = "Eerdere mapping gevonden: artikel"
        elif location_from_memory:
            memory_text = "Eerdere mapping gevonden: locatie"
        else:
            memory_text = "Geen eerdere mapping gevonden"

        if preparation_mode == "auto_ready":
            explanation = f"{memory_text}. Automatisch voorbereid door niveau {simplification_label}"
        elif preparation_mode == "suggest_only":
            if simplification_level == "voorzichtig":
                explanation = f"{memory_text}. Alleen voorstel door niveau {simplification_label}"
            else:
                explanation = f"{memory_text}. Controleer voorstel bij niveau {simplification_label}"
        else:
            explanation = memory_text

        return {
            "memory_match_found": memory_found,
            "article_from_memory": article_from_memory,
            "location_from_memory": location_from_memory,
            "applied_simplification_level": simplification_level,
            "preparation_mode": preparation_mode,
            "preparation_explanation": explanation,
        }

    batch_result["lines"] = [
        {
            **dict(line),
            **build_line_explanation(dict(line)),
            "review_decision": line["review_decision"] or "pending",
            "processing_status": line["processing_status"] or "pending",
            "quantity_raw": float(line["quantity_raw"]) if line["quantity_raw"] is not None else None,
            "line_price_raw": float(line["line_price_raw"]) if line["line_price_raw"] is not None else None,
            "processed_at": normalize_datetime(line["processed_at"]),
            "is_auto_prefilled": bool(line["is_auto_prefilled"]),
            "article_override_mode": line.get("article_override_mode") or 'auto',
            "location_override_mode": line.get("location_override_mode") or 'auto',
        }
        for line in lines
    ]
    selected_count = sum(1 for line in batch_result["lines"] if line.get("review_decision") == "selected")
    ignored_count = sum(1 for line in batch_result["lines"] if line.get("review_decision") == "ignored")
    pending_count = sum(1 for line in batch_result["lines"] if line.get("review_decision") == "pending")
    processed_count = sum(1 for line in batch_result["lines"] if line.get("processing_status") == "processed")
    failed_count = sum(1 for line in batch_result["lines"] if line.get("processing_status") == "failed")
    batch_result["summary"] = {
        "total": len(batch_result["lines"]),
        "selected": selected_count,
        "ignored": ignored_count,
        "pending": pending_count,
        "processed": processed_count,
        "failed": failed_count,
    }
    return batch_result


@app.get("/api/store-review-articles")
def get_store_review_articles(q: Optional[str] = Query(None)):
    query = (q or "").strip().lower()
    with engine.begin() as conn:
        all_items = get_store_review_article_options(conn)

    items = []
    for item in all_items:
        haystack = f"{item['name']} {item.get('brand') or ''}".lower()
        if not query or query in haystack:
            items.append(item)
    return items




@app.get("/api/spaces")
def list_spaces(householdId: Optional[str] = Query(None), authorization: Optional[str] = Header(None)):
    context = require_household_context(authorization, householdId)
    household_id = str(context["active_household_id"])
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    s.id,
                    s.naam,
                    COALESCE(s.active, 1) AS active,
                    COUNT(DISTINCT sl.id) AS sublocation_count,
                    COUNT(DISTINCT i.id) AS inventory_count
                FROM spaces s
                LEFT JOIN sublocations sl ON sl.space_id = s.id
                LEFT JOIN inventory i ON i.space_id = s.id AND i.household_id = s.household_id
                WHERE s.household_id = :household_id
                GROUP BY s.id, s.naam, COALESCE(s.active, 1)
                ORDER BY lower(s.naam) ASC
                """
            ),
            {"household_id": household_id},
        ).mappings().all()
    return {
        "household_id": household_id,
        "is_household_admin": str(context.get("display_role") or "").strip().lower() == "admin",
        "items": [
            {
                "id": row["id"],
                "naam": row["naam"],
                "active": bool(row["active"]),
                "sublocation_count": int(row["sublocation_count"] or 0),
                "inventory_count": int(row["inventory_count"] or 0),
            }
            for row in rows
        ],
    }


@app.post("/api/spaces")
def create_household_space(payload: SpaceCreate, authorization: Optional[str] = Header(None)):
    context = require_household_admin_context(authorization, payload.household_id)
    household_id = str(context["active_household_id"])
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM spaces WHERE household_id = :household_id AND lower(trim(naam)) = lower(trim(:naam)) LIMIT 1"),
            {"household_id": household_id, "naam": payload.naam},
        ).mappings().first()
        if existing:
            raise HTTPException(status_code=400, detail="Deze ruimte bestaat al in dit huishouden")
        row = conn.execute(
            text(
                """
                INSERT INTO spaces (id, naam, household_id, active)
                VALUES (lower(hex(randomblob(16))), :naam, :household_id, :active)
                RETURNING id, naam, COALESCE(active, 1) AS active
                """
            ),
            {"naam": payload.naam, "household_id": household_id, "active": 1 if payload.active else 0},
        ).mappings().first()
    return {"space": {"id": row["id"], "naam": row["naam"], "active": bool(row["active"])}, "message": "Ruimte opgeslagen."}


@app.put("/api/spaces/{space_id}")
def update_household_space(space_id: str, payload: SpaceUpdateRequest, authorization: Optional[str] = Header(None)):
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id, household_id FROM spaces WHERE id = :id LIMIT 1"),
            {"id": space_id},
        ).mappings().first()
        if not existing:
            raise HTTPException(status_code=404, detail="Onbekende ruimte")
        context = require_household_admin_context(authorization, str(existing["household_id"]))
        duplicate = conn.execute(
            text("SELECT id FROM spaces WHERE household_id = :household_id AND id <> :id AND lower(trim(naam)) = lower(trim(:naam)) LIMIT 1"),
            {"household_id": context["active_household_id"], "id": space_id, "naam": payload.naam},
        ).mappings().first()
        if duplicate:
            raise HTTPException(status_code=400, detail="Deze ruimte bestaat al in dit huishouden")
        row = conn.execute(
            text(
                """
                UPDATE spaces
                   SET naam = :naam,
                       active = :active
                 WHERE id = :id
             RETURNING id, naam, COALESCE(active, 1) AS active
                """
            ),
            {"id": space_id, "naam": payload.naam, "active": 1 if payload.active else 0},
        ).mappings().first()
    return {"space": {"id": row["id"], "naam": row["naam"], "active": bool(row["active"])}, "message": "Ruimte opgeslagen."}


@app.delete("/api/spaces/{space_id}")
def delete_household_space(space_id: str, authorization: Optional[str] = Header(None)):
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id, household_id, naam FROM spaces WHERE id = :id LIMIT 1"),
            {"id": space_id},
        ).mappings().first()
        if not existing:
            raise HTTPException(status_code=404, detail="Onbekende ruimte")
        context = require_household_admin_context(authorization, str(existing["household_id"]))
        sublocation_count = int(conn.execute(text("SELECT COUNT(*) FROM sublocations WHERE space_id = :space_id"), {"space_id": space_id}).scalar() or 0)
        inventory_count = int(conn.execute(text("SELECT COUNT(*) FROM inventory WHERE household_id = :household_id AND space_id = :space_id"), {"household_id": context["active_household_id"], "space_id": space_id}).scalar() or 0)
        unpack_count = int(conn.execute(text("""
            SELECT COUNT(*)
            FROM purchase_import_lines pil
            JOIN purchase_import_batches pib ON pib.id = pil.batch_id
            WHERE pib.household_id = :household_id
              AND COALESCE(pib.import_status, '') <> 'archived'
              AND (
                    pil.target_location_id = :space_id
                    OR pil.target_location_id IN (SELECT id FROM sublocations WHERE space_id = :space_id)
                    OR COALESCE(pil.final_location_id, '') = :space_id
                    OR pil.final_location_id IN (SELECT id FROM sublocations WHERE space_id = :space_id)
                  )
        """), {"household_id": context["active_household_id"], "space_id": space_id}).scalar() or 0)
        if sublocation_count > 0 or inventory_count > 0 or unpack_count > 0:
            raise HTTPException(status_code=400, detail="Deze locatie kan niet worden verwijderd omdat er nog artikelen aan gekoppeld zijn")
        conn.execute(text("DELETE FROM spaces WHERE id = :id"), {"id": space_id})
    return {"status": "ok", "message": "Locatie verwijderd."}



@app.get("/api/sublocations")
def list_sublocations(householdId: Optional[str] = Query(None), authorization: Optional[str] = Header(None)):
    context = require_household_context(authorization, householdId)
    household_id = str(context["active_household_id"])
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    sl.id,
                    sl.naam,
                    sl.space_id,
                    COALESCE(sl.active, 1) AS active,
                    s.naam AS space_name,
                    COUNT(DISTINCT i.id) AS inventory_count
                FROM sublocations sl
                JOIN spaces s ON s.id = sl.space_id
                LEFT JOIN inventory i ON i.sublocation_id = sl.id AND i.household_id = s.household_id
                WHERE s.household_id = :household_id
                GROUP BY sl.id, sl.naam, sl.space_id, COALESCE(sl.active, 1), s.naam
                ORDER BY lower(s.naam) ASC, lower(sl.naam) ASC
                """
            ),
            {"household_id": household_id},
        ).mappings().all()
    return {
        "household_id": household_id,
        "is_household_admin": str(context.get("display_role") or "").strip().lower() == "admin",
        "items": [
            {
                "id": row["id"],
                "naam": row["naam"],
                "space_id": row["space_id"],
                "space_name": row["space_name"],
                "active": bool(row["active"]),
                "inventory_count": int(row["inventory_count"] or 0),
            }
            for row in rows
        ],
    }


@app.post("/api/sublocations")
def create_household_sublocation(payload: SublocationCreate, authorization: Optional[str] = Header(None)):
    with engine.begin() as conn:
        space = conn.execute(
            text("SELECT id, household_id FROM spaces WHERE id = :id LIMIT 1"),
            {"id": payload.space_id},
        ).mappings().first()
        if not space:
            raise HTTPException(status_code=404, detail="Onbekende ruimte")
        context = require_household_admin_context(authorization, str(space["household_id"]))
        duplicate = conn.execute(
            text("SELECT sl.id FROM sublocations sl WHERE sl.space_id = :space_id AND lower(trim(sl.naam)) = lower(trim(:naam)) LIMIT 1"),
            {"space_id": payload.space_id, "naam": payload.naam},
        ).mappings().first()
        if duplicate:
            raise HTTPException(status_code=400, detail="Deze sublocatie bestaat al binnen deze ruimte")
        row = conn.execute(
            text("""
                INSERT INTO sublocations (id, naam, space_id, active)
                VALUES (lower(hex(randomblob(16))), :naam, :space_id, :active)
                RETURNING id, naam, space_id, COALESCE(active, 1) AS active
            """),
            {"naam": payload.naam, "space_id": payload.space_id, "active": 1 if payload.active else 0},
        ).mappings().first()
    return {"sublocation": {"id": row["id"], "naam": row["naam"], "space_id": row["space_id"], "active": bool(row["active"])}, "message": "Sublocatie opgeslagen."}


@app.put("/api/sublocations/{sublocation_id}")
def update_household_sublocation(sublocation_id: str, payload: SublocationUpdateRequest, authorization: Optional[str] = Header(None)):
    with engine.begin() as conn:
        existing = conn.execute(
            text("""
                SELECT sl.id, sl.space_id, s.household_id
                FROM sublocations sl
                JOIN spaces s ON s.id = sl.space_id
                WHERE sl.id = :id
                LIMIT 1
            """),
            {"id": sublocation_id},
        ).mappings().first()
        if not existing:
            raise HTTPException(status_code=404, detail="Onbekende sublocatie")
        target_space = conn.execute(text("SELECT id, household_id FROM spaces WHERE id = :id LIMIT 1"), {"id": payload.space_id}).mappings().first()
        if not target_space or str(target_space["household_id"]) != str(existing["household_id"]):
            raise HTTPException(status_code=400, detail="Ongeldige ruimte voor deze sublocatie")
        context = require_household_admin_context(authorization, str(existing["household_id"]))
        duplicate = conn.execute(
            text("SELECT id FROM sublocations WHERE space_id = :space_id AND id <> :id AND lower(trim(naam)) = lower(trim(:naam)) LIMIT 1"),
            {"space_id": payload.space_id, "id": sublocation_id, "naam": payload.naam},
        ).mappings().first()
        if duplicate:
            raise HTTPException(status_code=400, detail="Deze sublocatie bestaat al binnen deze ruimte")
        row = conn.execute(
            text("""
                UPDATE sublocations
                   SET naam = :naam,
                       space_id = :space_id,
                       active = :active
                 WHERE id = :id
             RETURNING id, naam, space_id, COALESCE(active, 1) AS active
            """),
            {"id": sublocation_id, "naam": payload.naam, "space_id": payload.space_id, "active": 1 if payload.active else 0},
        ).mappings().first()
    return {"sublocation": {"id": row["id"], "naam": row["naam"], "space_id": row["space_id"], "active": bool(row["active"])}, "message": "Sublocatie opgeslagen."}


@app.delete("/api/sublocations/{sublocation_id}")
def delete_household_sublocation(sublocation_id: str, authorization: Optional[str] = Header(None)):
    with engine.begin() as conn:
        existing = conn.execute(
            text("""
                SELECT sl.id, sl.naam, sl.space_id, s.household_id
                FROM sublocations sl
                JOIN spaces s ON s.id = sl.space_id
                WHERE sl.id = :id
                LIMIT 1
            """),
            {"id": sublocation_id},
        ).mappings().first()
        if not existing:
            raise HTTPException(status_code=404, detail="Onbekende sublocatie")
        context = require_household_admin_context(authorization, str(existing["household_id"]))
        inventory_count = int(conn.execute(text("SELECT COUNT(*) FROM inventory WHERE household_id = :household_id AND sublocation_id = :sublocation_id"), {"household_id": context["active_household_id"], "sublocation_id": sublocation_id}).scalar() or 0)
        unpack_count = int(conn.execute(text("""
            SELECT COUNT(*)
            FROM purchase_import_lines pil
            JOIN purchase_import_batches pib ON pib.id = pil.batch_id
            WHERE pib.household_id = :household_id
              AND COALESCE(pib.import_status, '') <> 'archived'
              AND (pil.target_location_id = :sublocation_id OR COALESCE(pil.final_location_id, '') = :sublocation_id)
        """), {"household_id": context["active_household_id"], "sublocation_id": sublocation_id}).scalar() or 0)
        if inventory_count > 0 or unpack_count > 0:
            raise HTTPException(status_code=400, detail="Deze sublocatie kan niet worden verwijderd omdat er nog artikelen aan gekoppeld zijn")
        conn.execute(text("DELETE FROM sublocations WHERE id = :id"), {"id": sublocation_id})
    return {"status": "ok", "message": "Sublocatie verwijderd."}


@app.get("/api/store-location-options")
def get_store_location_options(householdId: Optional[str] = Query(None), authorization: Optional[str] = Header(None)):
    context = require_household_context(authorization, householdId)
    effective_household_id = str(context["active_household_id"])
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    s.id AS space_id,
                    s.naam AS space_name,
                    sl.id AS sublocation_id,
                    sl.naam AS sublocation_name
                FROM spaces s
                LEFT JOIN sublocations sl ON sl.space_id = s.id AND COALESCE(sl.active, 1) = 1
                WHERE s.household_id = :household_id
                  AND COALESCE(s.active, 1) = 1
                ORDER BY lower(s.naam) ASC, lower(sl.naam) ASC
                """
            ),
            {"household_id": effective_household_id},
        ).mappings().all()
    return [
        {
            "id": row["sublocation_id"] or row["space_id"],
            "space_id": row["space_id"],
            "sublocation_id": row["sublocation_id"],
            "label": f"{row['space_name']} / {row['sublocation_name']}" if row["sublocation_name"] else row["space_name"],
        }
        for row in rows
    ]




@app.post("/api/purchase-import-batches/{batch_id}/prefill")
def prefill_purchase_import_batch(batch_id: str):
    with engine.begin() as conn:
        batch = conn.execute(
            text(
                """
                SELECT pib.id, pib.household_id, sp.code AS store_provider_code
                FROM purchase_import_batches pib
                JOIN store_providers sp ON sp.id = pib.store_provider_id
                WHERE pib.id = :id
                """
            ),
            {"id": batch_id},
        ).mappings().first()
        if not batch:
            raise HTTPException(status_code=404, detail="Onbekende purchase import batch")
        summary = apply_prefill_to_batch(conn, batch_id, str(batch["household_id"]), batch["store_provider_code"])
        status = update_batch_status(conn, batch_id)
    return {"batch_id": batch_id, "import_status": status, **summary}


@app.get("/api/store-connections/{connection_id}/latest-batch")
def get_latest_purchase_import_batch_for_connection(connection_id: str):
    with engine.begin() as conn:
        batch = conn.execute(
            text(
                """
                SELECT id AS batch_id, import_status, created_at
                FROM purchase_import_batches
                WHERE connection_id = :connection_id
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            ),
            {"connection_id": connection_id},
        ).mappings().first()
    if not batch:
        return {"batch_id": None, "import_status": None, "created_at": None}
    result = dict(batch)
    result["created_at"] = normalize_datetime(result.get("created_at"))
    return result


@app.post("/api/purchase-import-lines/{line_id}/review")
def review_purchase_import_line(line_id: str, payload: ReviewLineRequest):
    with engine.begin() as conn:
        line = conn.execute(
            text("SELECT id, batch_id FROM purchase_import_lines WHERE id = :id"),
            {"id": line_id},
        ).mappings().first()
        if not line:
            raise HTTPException(status_code=404, detail="Onbekende importregel")

        conn.execute(
            text(
                """
                UPDATE purchase_import_lines
                SET review_decision = :review_decision, reviewed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {"review_decision": payload.review_decision, "id": line_id},
        )
        status = update_batch_status(conn, line["batch_id"])
        updated = conn.execute(
            text(
                """
                SELECT id, batch_id, review_decision, matched_household_article_id, target_location_id, match_status, article_override_mode, location_override_mode
                FROM purchase_import_lines WHERE id = :id
                """
            ),
            {"id": line_id},
        ).mappings().first()
    result = dict(updated)
    result["batch_status"] = status
    return result


@app.post("/api/purchase-import-lines/{line_id}/map")
def map_purchase_import_line(line_id: str, payload: MapLineRequest):
    with engine.begin() as conn:
        line = conn.execute(
            text("SELECT id, batch_id FROM purchase_import_lines WHERE id = :id"),
            {"id": line_id},
        ).mappings().first()
        if not line:
            raise HTTPException(status_code=404, detail="Onbekende importregel")

        article_id = resolve_household_article_selection_to_id(
            conn,
            str((conn.execute(text("SELECT household_id FROM purchase_import_batches WHERE id = :id LIMIT 1"), {"id": line["batch_id"]}).mappings().first() or {}).get('household_id') or ''),
            payload.household_article_id,
            create_if_missing=True,
        ) if payload.household_article_id else None
        match_status = 'matched' if article_id else 'unmatched'
        next_review_decision = 'pending' if not article_id else None
        conn.execute(
            text(
                """
                UPDATE purchase_import_lines
                SET matched_household_article_id = :article_id,
                    match_status = :match_status,
                    article_override_mode = :article_override_mode,
                    review_decision = CASE WHEN :next_review_decision IS NOT NULL THEN :next_review_decision ELSE review_decision END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {
                "article_id": article_id,
                "match_status": match_status,
                "article_override_mode": 'manual' if article_id else 'cleared',
                "next_review_decision": next_review_decision,
                "id": line_id,
            },
        )
        batch_row = conn.execute(text("SELECT household_id FROM purchase_import_batches WHERE id = :id LIMIT 1"), {"id": line["batch_id"]}).mappings().first()
        sync_purchase_import_line_product_links(conn, line_id, str((batch_row or {}).get('household_id') or ''))
        status = update_batch_status(conn, line["batch_id"])
        updated = conn.execute(
            text(
                """
                SELECT id, batch_id, review_decision, matched_household_article_id, matched_global_product_id, target_location_id, match_status, article_override_mode, location_override_mode
                FROM purchase_import_lines WHERE id = :id
                """
            ),
            {"id": line_id},
        ).mappings().first()
    result = dict(updated)
    result["batch_status"] = status
    return result


@app.post("/api/purchase-import-lines/{line_id}/create-article")
def create_article_from_purchase_import_line(line_id: str, payload: CreateArticleFromLineRequest, authorization: Optional[str] = Header(None)):
    with engine.begin() as conn:
        line = conn.execute(
            text(
                """
                SELECT pil.id, pil.batch_id, pib.household_id
                FROM purchase_import_lines pil
                JOIN purchase_import_batches pib ON pib.id = pil.batch_id
                WHERE pil.id = :id
                """
            ),
            {"id": line_id},
        ).mappings().first()
        if not line:
            raise HTTPException(status_code=404, detail="Onbekende importregel")

        context = require_household_context(authorization, str(line["household_id"]))
        require_household_permission(conn, context, PERMISSION_ARTICLE_CREATE)

        article_option_id = ensure_household_article(conn, str(line["household_id"]), payload.article_name, consumable=infer_consumable_from_name(payload.article_name))
        conn.execute(
            text(
                """
                UPDATE purchase_import_lines
                SET matched_household_article_id = :article_id, match_status = 'matched', article_override_mode = 'manual', updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {"article_id": article_option_id, "id": line_id},
        )
        sync_purchase_import_line_product_links(conn, line_id, str(line["household_id"]))
        status = update_batch_status(conn, line["batch_id"])
        article = resolve_review_article_option(conn, article_option_id, str(line["household_id"]))

    synced = None
    with engine.begin() as conn:
        synced = conn.execute(text("SELECT matched_global_product_id FROM purchase_import_lines WHERE id = :id LIMIT 1"), {"id": line_id}).mappings().first()
    return {
        "line_id": line_id,
        "batch_id": line["batch_id"],
        "batch_status": status,
        "article_option": article,
        "matched_household_article_id": article_option_id,
        "matched_global_product_id": (synced or {}).get('matched_global_product_id'),
    }


@app.post("/api/purchase-import-lines/{line_id}/target-location")
def set_purchase_import_line_target_location(line_id: str, payload: TargetLocationRequest):
    with engine.begin() as conn:
        line = conn.execute(
            text("SELECT id, batch_id FROM purchase_import_lines WHERE id = :id"),
            {"id": line_id},
        ).mappings().first()
        if not line:
            raise HTTPException(status_code=404, detail="Onbekende importregel")

        resolved_location, line_ref = validate_purchase_import_target_location(conn, line_id, payload.target_location_id)
        if payload.target_location_id and not resolved_location:
            return JSONResponse(
                status_code=422,
                content={
                    "detail": f"Ongeldige target_location_id voor {line_ref.get('display_label') or line_id}",
                    "line_id": line_ref.get("line_id") or str(line_id),
                    "external_line_ref": line_ref.get("external_line_ref") or "",
                    "ui_line_number": line_ref.get("ui_line_number"),
                    "article_name": line_ref.get("article_name") or "",
                    "target_location_id": payload.target_location_id,
                    "status": "rejected",
                    "reason": "invalid_target_location_id",
                },
            )

        next_review_decision = 'pending' if not payload.target_location_id else None
        conn.execute(
            text(
                """
                UPDATE purchase_import_lines
                SET target_location_id = :target_location_id,
                    location_override_mode = :location_override_mode,
                    review_decision = CASE WHEN :next_review_decision IS NOT NULL THEN :next_review_decision ELSE review_decision END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {
                "target_location_id": payload.target_location_id,
                "location_override_mode": 'manual' if payload.target_location_id else 'cleared',
                "next_review_decision": next_review_decision,
                "id": line_id,
            },
        )
        status = update_batch_status(conn, line["batch_id"])
        updated = conn.execute(
            text(
                """
                SELECT id, batch_id, review_decision, matched_household_article_id, target_location_id, match_status, article_override_mode, location_override_mode
                FROM purchase_import_lines WHERE id = :id
                """
            ),
            {"id": line_id},
        ).mappings().first()
    result = dict(updated)
    result["batch_status"] = status
    result["line_reference"] = line_ref
    if resolved_location:
        result["resolved_location"] = resolved_location
    return result


@app.post("/api/purchase-import-batches/{batch_id}/complete-review")
def complete_purchase_import_batch_review(batch_id: str):
    with engine.begin() as conn:
        batch = conn.execute(
            text("SELECT id FROM purchase_import_batches WHERE id = :id"),
            {"id": batch_id},
        ).first()
        if not batch:
            raise HTTPException(status_code=404, detail="Onbekende purchase import batch")
        status = update_batch_status(conn, batch_id)
        if status == "new":
            status = "in_review"
            conn.execute(text("UPDATE purchase_import_batches SET import_status = 'in_review' WHERE id = :id"), {"id": batch_id})
    return {"batch_id": batch_id, "import_status": status}

def classify_article_resolution(original_article_id: str | None, original_article_name: str | None, resolved_article_id: str | None, resolved_article_name: str | None) -> str:
    original_id = str(original_article_id or '').strip()
    resolved_id = str(resolved_article_id or '').strip()
    original_name = normalize_household_article_name(original_article_name)
    final_name = normalize_household_article_name(resolved_article_name)
    if not resolved_id or not final_name:
        return 'geen match'
    if original_id == resolved_id and original_name and final_name and original_name.lower() == final_name.lower():
        return 'exact match'
    if original_id.startswith('live::'):
        return 'bestaand huishoudartikel'
    if final_name and original_name and final_name.lower() != original_name.lower():
        return 'live canonicalisatie'
    return 'bestaand huishoudartikel'


def count_history_events_for_article(conn, article_id: str | None, article_name: str | None, event_id: str | None = None) -> tuple[int, bool]:
    resolved_id = str(article_id or '').strip()
    resolved_name = normalize_household_article_name(article_name)
    if not resolved_name:
        return 0, False
    rows = conn.execute(
        text(
            """
            SELECT id
            FROM inventory_events
            WHERE (article_id = :article_id OR lower(trim(article_name)) = lower(trim(:article_name)))
            ORDER BY datetime(created_at) DESC, id DESC
            """
        ),
        {"article_id": resolved_id, "article_name": resolved_name},
    ).mappings().all()
    ids = [str(row['id']) for row in rows]
    return len(ids), bool(event_id and str(event_id) in ids)


def build_purchase_import_line_diagnostic(
    *,
    line: dict,
    batch: dict,
    selected_article_input: str | None,
    original_article: dict | None,
    resolved_article: dict | None,
    resolved_location: dict | None,
    purchase_quantity: int,
    pre_purchase_total: int,
    purchase_event_created: bool,
    purchase_event_id: str | None,
    history_contains_purchase_event: bool,
    history_lookup_article_id: str | None,
    history_lookup_result_count: int,
    auto_consume_household_mode: str,
    auto_consume_article_override: str,
    auto_consume_effective_mode: str,
    auto_consume_should_apply: bool,
    auto_consume_decision_reason: str,
    auto_consume_requested_deduction_quantity: int,
    auto_consume_applied_deduction_quantity: int,
    auto_consume_event_created: bool,
    auto_consume_event_id: str | None,
    inventory_after_purchase_total: int,
    inventory_after_auto_consume_total: int,
    processing_status: str = 'pending',
    processed_from_saved_batch_data: bool = True,
    failure_stage: str = 'none',
    failure_message: str = '',
) -> dict:
    resolved_article_id = str(resolved_article.get('id') or '') if resolved_article else ''
    resolved_article_name = str(resolved_article.get('name') or '') if resolved_article else ''
    original_article_id = str(original_article.get('id') or '') if original_article else str(selected_article_input or '')
    original_article_name = str(original_article.get('name') or '') if original_article else ''
    return {
        'line_id': line.get('id'),
        'receipt_line_text': line.get('article_name_raw') or '',
        'selected_article_input': selected_article_input or '',
        'resolved_article_id': resolved_article_id,
        'resolved_article_name': resolved_article_name,
        'resolution_reason': classify_article_resolution(original_article_id, original_article_name, resolved_article_id, resolved_article_name),
        'purchase_quantity': int(purchase_quantity or 0),
        'target_space_id': resolved_location.get('space_id') if resolved_location else None,
        'target_space_name': resolved_location.get('space_name') if resolved_location else None,
        'target_sublocation_id': resolved_location.get('sublocation_id') if resolved_location else None,
        'target_sublocation_name': resolved_location.get('sublocation_name') if resolved_location else None,
        'purchase_event_created': bool(purchase_event_created),
        'purchase_event_id': purchase_event_id,
        'inventory_before_total': int(pre_purchase_total or 0),
        'inventory_after_purchase_total': int(inventory_after_purchase_total or 0),
        'history_contains_purchase_event': bool(history_contains_purchase_event),
        'history_lookup_article_id': history_lookup_article_id or '',
        'history_lookup_result_count': int(history_lookup_result_count or 0),
        'auto_consume_household_mode': auto_consume_household_mode,
        'auto_consume_article_override': auto_consume_article_override,
        'auto_consume_effective_mode': auto_consume_effective_mode,
        'auto_consume_should_apply': bool(auto_consume_should_apply),
        'auto_consume_decision_reason': auto_consume_decision_reason,
        'auto_consume_requested_deduction_quantity': int(auto_consume_requested_deduction_quantity or 0),
        'auto_consume_applied_deduction_quantity': int(auto_consume_applied_deduction_quantity or 0),
        'auto_consume_event_created': bool(auto_consume_event_created),
        'auto_consume_event_id': auto_consume_event_id,
        'inventory_after_auto_consume_total': int(inventory_after_auto_consume_total or 0),
        'processing_status': processing_status or 'pending',
        'stored_matched_article_id': str(line.get('matched_household_article_id') or ''),
        'stored_target_location_id': str(line.get('target_location_id') or ''),
        'processed_from_saved_batch_data': bool(processed_from_saved_batch_data),
        'failure_stage': failure_stage or 'none',
        'failure_message': failure_message or '',
    }


def store_purchase_import_line_diagnostic(conn, line_id: str, diagnostic: dict):
    conn.execute(
        text(
            "UPDATE purchase_import_lines SET processing_diagnostics = :processing_diagnostics, updated_at = CURRENT_TIMESTAMP WHERE id = :id"
        ),
        {"processing_diagnostics": json.dumps(diagnostic, ensure_ascii=False), "id": line_id},
    )


def build_purchase_import_batch_diagnostics(conn, batch_id: str):
    rows = conn.execute(
        text(
            """
            SELECT id, article_name_raw, matched_household_article_id, target_location_id, article_override_mode, location_override_mode, processing_status, processing_error, processing_diagnostics
            FROM purchase_import_lines
            WHERE batch_id = :batch_id
            ORDER BY COALESCE(ui_sort_order, 999999), created_at ASC, id ASC
            """
        ),
        {"batch_id": batch_id},
    ).mappings().all()
    diagnostics = []
    for row in rows:
        raw = row.get('processing_diagnostics')
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    parsed.setdefault('processing_status', (row.get('processing_status') or 'pending'))
                    parsed.setdefault('stored_matched_article_id', str(row.get('matched_household_article_id') or ''))
                    parsed.setdefault('stored_target_location_id', str(row.get('target_location_id') or ''))
                    parsed.setdefault('article_override_mode', row.get('article_override_mode') or 'auto')
                    parsed.setdefault('location_override_mode', row.get('location_override_mode') or 'auto')
                    parsed.setdefault('processed_from_saved_batch_data', True)
                    diagnostics.append(parsed)
                    continue
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        processing_status = (row.get('processing_status') or 'pending').strip() if isinstance(row.get('processing_status'), str) else (row.get('processing_status') or 'pending')
        is_processed = processing_status == 'processed'
        is_failed = processing_status == 'failed'
        diagnostics.append({
            'line_id': row['id'],
            'receipt_line_text': row.get('article_name_raw') or '',
            'selected_article_input': row.get('matched_household_article_id') or '',
            'resolved_article_id': row.get('matched_household_article_id') or '',
            'resolved_article_name': '',
            'resolution_reason': 'nog niet verwerkt' if not is_processed and not is_failed else 'geen diagnose beschikbaar',
            'purchase_quantity': 0,
            'target_space_id': None,
            'target_space_name': None,
            'target_sublocation_id': None,
            'target_sublocation_name': None,
            'purchase_event_created': False,
            'purchase_event_id': None,
            'inventory_before_total': 0,
            'inventory_after_purchase_total': 0,
            'history_contains_purchase_event': False,
            'history_lookup_article_id': row.get('matched_household_article_id') or '',
            'history_lookup_result_count': 0,
            'auto_consume_household_mode': ARTICLE_AUTO_CONSUME_NONE,
            'auto_consume_article_override': ARTICLE_AUTO_CONSUME_FOLLOW_HOUSEHOLD,
            'auto_consume_effective_mode': ARTICLE_AUTO_CONSUME_NONE,
            'auto_consume_should_apply': False,
            'auto_consume_decision_reason': row.get('processing_error') or ('nog niet verwerkt' if not is_processed and not is_failed else 'geen diagnose beschikbaar'),
            'auto_consume_requested_deduction_quantity': 0,
            'auto_consume_applied_deduction_quantity': 0,
            'auto_consume_event_created': False,
            'auto_consume_event_id': None,
            'inventory_after_auto_consume_total': 0,
            'processing_status': processing_status,
            'stored_matched_article_id': str(row.get('matched_household_article_id') or ''),
            'stored_target_location_id': str(row.get('target_location_id') or ''),
            'article_override_mode': row.get('article_override_mode') or 'auto',
            'location_override_mode': row.get('location_override_mode') or 'auto',
            'processed_from_saved_batch_data': True,
            'failure_stage': 'none' if not is_failed else 'purchase_event_write',
            'failure_message': row.get('processing_error') or '',
        })
    return {'batch_id': batch_id, 'line_diagnostics': diagnostics}


@app.get("/api/dev/purchase-import-batches/{batch_id}/diagnostics")
def get_purchase_import_batch_diagnostics(batch_id: str, authorization: Optional[str] = Header(None)):
    require_platform_admin_user(authorization)
    with engine.begin() as conn:
        batch = conn.execute(text("SELECT id FROM purchase_import_batches WHERE id = :id"), {"id": batch_id}).mappings().first()
        if not batch:
            raise HTTPException(status_code=404, detail="Onbekende purchase import batch")
        return build_purchase_import_batch_diagnostics(conn, batch_id)




@app.post("/api/purchase-import-batches/{batch_id}/process")
def process_purchase_import_batch(batch_id: str, payload: ProcessBatchRequest, authorization: Optional[str] = Header(None)):
    current_line_id = None
    current_line_name = None
    current_stage = 'batch_start'
    try:
        with engine.begin() as conn:
            batch = conn.execute(
                text(
                    """
                    SELECT pib.id, pib.household_id, pib.import_status, sp.code AS store_provider_code
                    FROM purchase_import_batches pib
                    JOIN store_providers sp ON sp.id = pib.store_provider_id
                    WHERE pib.id = :id
                    """
                ),
                {"id": batch_id},
            ).mappings().first()
            if not batch:
                raise HTTPException(status_code=404, detail="Onbekende purchase import batch")
            context = require_household_context(authorization, str(batch["household_id"]))
            if str(context.get("display_role") or "").strip().lower() == "viewer":
                raise HTTPException(status_code=403, detail="Kijkers mogen kassabonnen wel opvoeren, maar niet naar voorraad verwerken")

            lines = conn.execute(
                text(
                    """
                    SELECT id, article_name_raw, brand_raw, external_article_code, quantity_raw, unit_raw, review_decision, matched_household_article_id,
                           matched_global_product_id, target_location_id, processing_status, processed_event_id
                    FROM purchase_import_lines
                    WHERE batch_id = :batch_id
                    ORDER BY COALESCE(ui_sort_order, 999999), created_at ASC, id ASC
                    """
                ),
                {"batch_id": batch_id},
            ).mappings().all()

            selected_lines = [line for line in lines if (line["review_decision"] or "pending") == "selected"]
            results = []
            processable_lines = []
            skipped_count = 0

            for line in selected_lines:
                line_id = line["id"]
                current_line_id = line_id
                current_line_name = line.get("article_name_raw") or ''
                line_reference = build_purchase_import_line_reference(conn, line_id)
                if payload.mode == "ready_only":
                    article_id = line.get("matched_household_article_id")
                    matched_global_product_id = str(line.get("matched_global_product_id") or '').strip()
                    location_id = line.get("target_location_id")
                    if not article_id and not matched_global_product_id:
                        results.append({
                            "line_id": line_id,
                            "line_reference": line_reference,
                            "status": "skipped",
                            "reason": "Nog geen artikel of product gekoppeld",
                            "failure_stage": "article_resolution",
                        })
                        skipped_count += 1
                        continue
                    if not location_id:
                        results.append({
                            "line_id": line_id,
                            "line_reference": line_reference,
                            "status": "skipped",
                            "reason": "Nog geen locatie gekozen",
                            "failure_stage": "purchase_event_write",
                        })
                        skipped_count += 1
                        continue
                processable_lines.append(line)

            if not processable_lines:
                if payload.mode == "ready_only":
                    raise HTTPException(status_code=400, detail="Geen klaarstaande regels om naar voorraad te verwerken")
                raise HTTPException(status_code=400, detail="Er zijn geen geselecteerde regels om te verwerken")

            processed_count = 0
            failed_count = 0

            for line in processable_lines:
                line_id = line["id"]
                current_line_id = line_id
                current_line_name = line.get("article_name_raw") or ''
                line_reference = build_purchase_import_line_reference(conn, line_id)
                if line["processing_status"] == "processed" and line["processed_event_id"]:
                    results.append({"line_id": line_id, "line_reference": line_reference, "status": "processed", "event_id": line["processed_event_id"], "message": "Al eerder verwerkt"})
                    processed_count += 1
                    continue

                article_id = line["matched_household_article_id"]
                matched_global_product_id = str(line.get("matched_global_product_id") or '').strip()
                if not article_id and matched_global_product_id:
                    article_id = ensure_household_article_for_global_product(
                        conn,
                        str(batch["household_id"]),
                        matched_global_product_id,
                        article_name_hint=line.get("article_name_raw"),
                        barcode=line.get("external_article_code"),
                        brand=line.get("brand_raw"),
                    )
                    if article_id:
                        conn.execute(
                            text(
                                """
                                UPDATE purchase_import_lines
                                SET matched_household_article_id = :matched_household_article_id,
                                    suggested_household_article_id = COALESCE(suggested_household_article_id, :matched_household_article_id),
                                    match_status = 'matched',
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE id = :id
                                """
                            ),
                            {'id': line_id, 'matched_household_article_id': article_id},
                        )
                synced_links = sync_purchase_import_line_product_links(conn, line_id, str(batch["household_id"]))
                if synced_links:
                    article_id = synced_links.get('matched_household_article_id') or article_id
                    matched_global_product_id = synced_links.get('matched_global_product_id') or matched_global_product_id
                selected_article_input = str(article_id or matched_global_product_id or '')
                original_article = resolve_review_article_option(conn, article_id, str(batch["household_id"])) if article_id else None
                article = resolve_processing_article(conn, str(batch["household_id"]), original_article)
                if article:
                    article_id = article["id"]
                if not article:
                    error = "Geen geldige artikelkoppeling gekozen"
                    diagnostic = build_purchase_import_line_diagnostic(
                        line=line, batch=batch, selected_article_input=selected_article_input, original_article=original_article, resolved_article=None,
                        resolved_location=None, purchase_quantity=0, pre_purchase_total=0, purchase_event_created=False, purchase_event_id=None,
                        history_contains_purchase_event=False, history_lookup_article_id=selected_article_input, history_lookup_result_count=0,
                        auto_consume_household_mode=get_household_auto_consume_mode(conn, str(batch["household_id"])),
                        auto_consume_article_override=ARTICLE_AUTO_CONSUME_FOLLOW_HOUSEHOLD,
                        auto_consume_effective_mode=ARTICLE_AUTO_CONSUME_NONE, auto_consume_should_apply=False,
                        auto_consume_decision_reason='Geen geldige artikelkoppeling gekozen', auto_consume_requested_deduction_quantity=0,
                        auto_consume_applied_deduction_quantity=0, auto_consume_event_created=False, auto_consume_event_id=None,
                        inventory_after_purchase_total=0, inventory_after_auto_consume_total=0, processing_status='failed', failure_stage='article_resolution', failure_message=error,
                    )
                    store_purchase_import_line_diagnostic(conn, line_id, diagnostic)
                    conn.execute(text("UPDATE purchase_import_lines SET processing_status = 'failed', processing_error = :error, updated_at = CURRENT_TIMESTAMP WHERE id = :id"), {"error": error, "id": line_id})
                    results.append({"line_id": line_id, "line_reference": line_reference, "status": "failed", "error": error, "diagnostic": diagnostic})
                    failed_count += 1
                    continue

                resolved_location = resolve_target_location(conn, line["target_location_id"])
                if not resolved_location:
                    error = "Geen geldige locatie gekozen"
                    diagnostic = build_purchase_import_line_diagnostic(
                        line=line, batch=batch, selected_article_input=selected_article_input, original_article=original_article, resolved_article=article,
                        resolved_location=None, purchase_quantity=0, pre_purchase_total=0, purchase_event_created=False, purchase_event_id=None,
                        history_contains_purchase_event=False, history_lookup_article_id=str(article_id), history_lookup_result_count=0,
                        auto_consume_household_mode=get_household_auto_consume_mode(conn, str(batch["household_id"])),
                        auto_consume_article_override=get_household_article_auto_consume_override(conn, str(batch["household_id"]), str(article_id)),
                        auto_consume_effective_mode=ARTICLE_AUTO_CONSUME_NONE, auto_consume_should_apply=False,
                        auto_consume_decision_reason='Geen geldige locatie gekozen', auto_consume_requested_deduction_quantity=0,
                        auto_consume_applied_deduction_quantity=0, auto_consume_event_created=False, auto_consume_event_id=None,
                        inventory_after_purchase_total=0, inventory_after_auto_consume_total=0, processing_status='failed', failure_stage='purchase_event_write', failure_message=error,
                    )
                    store_purchase_import_line_diagnostic(conn, line_id, diagnostic)
                    conn.execute(text("UPDATE purchase_import_lines SET processing_status = 'failed', processing_error = :error, updated_at = CURRENT_TIMESTAMP WHERE id = :id"), {"error": error, "id": line_id})
                    results.append({"line_id": line_id, "line_reference": line_reference, "status": "failed", "error": error, "diagnostic": diagnostic})
                    failed_count += 1
                    continue

                quantity = normalize_store_import_quantity(line.get("quantity_raw"), line.get("unit_raw"))
                if quantity <= 0:
                    error = "Ongeldige hoeveelheid"
                    diagnostic = build_purchase_import_line_diagnostic(
                        line=line, batch=batch, selected_article_input=selected_article_input, original_article=original_article, resolved_article=article,
                        resolved_location=resolved_location, purchase_quantity=0, pre_purchase_total=0, purchase_event_created=False, purchase_event_id=None,
                        history_contains_purchase_event=False, history_lookup_article_id=str(article_id), history_lookup_result_count=0,
                        auto_consume_household_mode=get_household_auto_consume_mode(conn, str(batch["household_id"])),
                        auto_consume_article_override=get_household_article_auto_consume_override(conn, str(batch["household_id"]), str(article_id)),
                        auto_consume_effective_mode=ARTICLE_AUTO_CONSUME_NONE, auto_consume_should_apply=False,
                        auto_consume_decision_reason='Ongeldige hoeveelheid', auto_consume_requested_deduction_quantity=0,
                        auto_consume_applied_deduction_quantity=0, auto_consume_event_created=False, auto_consume_event_id=None,
                        inventory_after_purchase_total=0, inventory_after_auto_consume_total=0, processing_status='failed', failure_stage='purchase_event_write', failure_message=error,
                    )
                    store_purchase_import_line_diagnostic(conn, line_id, diagnostic)
                    conn.execute(text("UPDATE purchase_import_lines SET processing_status = 'failed', processing_error = :error, updated_at = CURRENT_TIMESTAMP WHERE id = :id"), {"error": error, "id": line_id})
                    results.append({"line_id": line_id, "line_reference": line_reference, "status": "failed", "error": error, "diagnostic": diagnostic})
                    failed_count += 1
                    continue

                article_name = article["name"]
                note = build_store_import_note(batch["store_provider_code"], batch_id, line_id, line["article_name_raw"])
                pre_purchase_total = get_article_total_quantity(conn, batch["household_id"], article_name)
                auto_consume_decision = determine_auto_consume_decision(
                    conn,
                    str(batch["household_id"]),
                    str(article_id),
                    article_name,
                    pre_purchase_total,
                    quantity,
                )
                household_mode = auto_consume_decision["household_mode"]
                article_override = auto_consume_decision["article_override"]
                effective_mode = auto_consume_decision["effective_mode"]
                decision_reason = auto_consume_decision["decision_reason"]
                should_auto_consume = auto_consume_decision["should_auto_consume"]
                requested_deduction_quantity = auto_consume_decision["requested_deduction_quantity"]
                current_stage = 'purchase_event_write'
                event_id = None
                auto_event_id = None
                inventory_after_purchase_total = pre_purchase_total
                inventory_after_auto_consume_total = pre_purchase_total
                history_lookup_result_count = 0
                history_contains_purchase_event = False
                applied_deduction_quantity = 0
                try:
                    event_id = create_inventory_purchase_event(
                        conn,
                        batch["household_id"],
                        article_id,
                        article_name,
                        quantity,
                        resolved_location,
                        note,
                        supplier_name=batch.get("store_name") or batch.get("store_label") or batch.get("store_provider_name") or batch.get("store_provider_code"),
                        price=float(line.get("line_price_raw")) if line.get("line_price_raw") is not None else None,
                        currency=line.get("currency_code") or "EUR",
                        article_number=line.get("external_article_code"),
                        barcode=line.get("barcode") or None,
                    )
                    purchase_inventory_id = apply_inventory_purchase(conn, batch["household_id"], article_name, quantity, resolved_location)
                    sync_household_article_price_metrics(conn, batch["household_id"], article_id, ensure_household_article_global_product_link(conn, article_id, line.get("barcode") or None))
                    inventory_after_purchase_total = get_article_total_quantity(conn, batch["household_id"], article_name)
                    current_stage = 'history_lookup'
                    history_lookup_result_count, history_contains_purchase_event = count_history_events_for_article(conn, str(article_id), article_name, event_id)
                    current_stage = 'auto_consume_decision'
                    applied_deduction_quantity = 0
                    if should_auto_consume:
                        current_stage = 'auto_consume_write'
                        auto_event_id = create_auto_repurchase_event(conn, batch["household_id"], article_id, article_name, resolved_location, quantity=requested_deduction_quantity)
                        consumption_result = apply_inventory_consumption(
                            conn,
                            batch["household_id"],
                            article_name,
                            requested_deduction_quantity,
                            resolved_location,
                            mode=effective_mode,
                            protected_quantity_on_purchase_row=int(quantity),
                            protected_purchase_inventory_id=purchase_inventory_id,
                        )
                        applied_deduction_quantity = int(consumption_result.get("applied_quantity") or 0)
                    inventory_after_auto_consume_total = get_article_total_quantity(conn, batch["household_id"], article_name)
                except Exception as exc:
                    detail_parts = [
                        f'exception_type={exc.__class__.__name__}',
                        f'exception_message={str(exc) or exc.__class__.__name__}',
                        f'article_id={article_id}',
                        f'article_name={article_name}',
                        f'quantity={quantity}',
                        f'location_id={resolved_location.get("location_id") if resolved_location else None}',
                        f'location_label={resolved_location.get("location_label") if resolved_location else None}',
                    ]
                    error = ' | '.join(detail_parts)
                    diagnostic = build_purchase_import_line_diagnostic(
                        line=line, batch=batch, selected_article_input=selected_article_input, original_article=original_article, resolved_article=article,
                        resolved_location=resolved_location, purchase_quantity=int(quantity), pre_purchase_total=int(pre_purchase_total),
                        purchase_event_created=bool(event_id), purchase_event_id=event_id, history_contains_purchase_event=history_contains_purchase_event,
                        history_lookup_article_id=str(article_id), history_lookup_result_count=history_lookup_result_count,
                        auto_consume_household_mode=household_mode, auto_consume_article_override=article_override, auto_consume_effective_mode=effective_mode,
                        auto_consume_should_apply=should_auto_consume, auto_consume_decision_reason=decision_reason,
                        auto_consume_requested_deduction_quantity=requested_deduction_quantity,
                        auto_consume_applied_deduction_quantity=applied_deduction_quantity if auto_event_id else 0, auto_consume_event_created=bool(auto_event_id),
                        auto_consume_event_id=auto_event_id, inventory_after_purchase_total=int(inventory_after_purchase_total),
                        inventory_after_auto_consume_total=int(inventory_after_auto_consume_total),
                        processing_status='failed', failure_stage=current_stage, failure_message=error,
                    )
                    diagnostic['backend_trace_excerpt'] = traceback.format_exc(limit=2)
                    store_purchase_import_line_diagnostic(conn, line_id, diagnostic)
                    conn.execute(text("UPDATE purchase_import_lines SET processing_status = 'failed', processing_error = :error, updated_at = CURRENT_TIMESTAMP WHERE id = :id"), {"error": error, "id": line_id})
                    results.append({"line_id": line_id, "line_reference": line_reference, "status": "failed", "error": error, "diagnostic": diagnostic})
                    failed_count += 1
                    continue
                diagnostic = build_purchase_import_line_diagnostic(
                    line=line, batch=batch, selected_article_input=selected_article_input, original_article=original_article, resolved_article=article,
                    resolved_location=resolved_location, purchase_quantity=int(quantity), pre_purchase_total=int(pre_purchase_total),
                    purchase_event_created=bool(event_id), purchase_event_id=event_id, history_contains_purchase_event=history_contains_purchase_event,
                    history_lookup_article_id=str(article_id), history_lookup_result_count=history_lookup_result_count,
                    auto_consume_household_mode=household_mode, auto_consume_article_override=article_override, auto_consume_effective_mode=effective_mode,
                    auto_consume_should_apply=should_auto_consume, auto_consume_decision_reason=decision_reason,
                    auto_consume_requested_deduction_quantity=requested_deduction_quantity,
                    auto_consume_applied_deduction_quantity=applied_deduction_quantity if auto_event_id else 0, auto_consume_event_created=bool(auto_event_id),
                    auto_consume_event_id=auto_event_id, inventory_after_purchase_total=int(inventory_after_purchase_total),
                    inventory_after_auto_consume_total=int(inventory_after_auto_consume_total),
                    processing_status='processed', failure_stage='none', failure_message='',
                )
                store_purchase_import_line_diagnostic(conn, line_id, diagnostic)
                conn.execute(
                    text(
                        """
                        UPDATE purchase_import_lines
                        SET processing_status = 'processed', processed_at = CURRENT_TIMESTAMP,
                            processed_event_id = :event_id, processing_error = NULL,
                            final_location_id = :final_location_id, updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                        """
                    ),
                    {"event_id": event_id, "final_location_id": resolved_location["location_id"], "id": line_id},
                )
                remember_store_import_choice(
                    conn,
                    str(batch["household_id"]),
                    batch["store_provider_code"],
                    line["article_name_raw"],
                    line.get("brand_raw"),
                    article_id,
                    resolved_location["location_id"],
                )
                results.append({"line_id": line_id, "status": "processed", "event_id": event_id, "auto_event_id": auto_event_id, "diagnostic": diagnostic})
                processed_count += 1

            batch_status = update_batch_status(conn, batch_id)
            if batch_status in {"processed", "partially_processed"}:
                conn.execute(text("UPDATE purchase_import_batches SET processed_at = CURRENT_TIMESTAMP WHERE id = :id"), {"id": batch_id})

            diagnostics = build_purchase_import_batch_diagnostics(conn, batch_id)

        return {
            "batch_id": batch_id,
            "status": batch_status,
            "processed_count": processed_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "results": results,
            "diagnostics": diagnostics,
        }
    except HTTPException:
        raise
    except Exception as exc:
        detail = f"Verwerking naar voorraad mislukt bij regel '{current_line_name or current_line_id or '?'}' op stap {current_stage}: {exc.__class__.__name__}: {str(exc) or exc.__class__.__name__}"
        logger.exception('Procesfout batch %s regel %s', batch_id, current_line_id)
        raise HTTPException(status_code=500, detail=detail)


def clear_regression_receipt_state(household_id: str):
    effective_household_id = str(household_id or '').strip() or '1'
    with engine.begin() as conn:
        raw_rows = conn.execute(
            text(
                """
                SELECT id, original_filename
                FROM raw_receipts
                WHERE household_id = :household_id
                  AND (
                    COALESCE(sha256_hash, '') LIKE :hash_prefix
                    OR lower(COALESCE(original_filename, '')) LIKE 'seed-%'
                    OR lower(COALESCE(original_filename, '')) LIKE 'regression-%'
                    OR lower(COALESCE(original_filename, '')) LIKE 'regressie-bon-%'
                  )
                """
            ),
            {'household_id': effective_household_id, 'hash_prefix': f'{REGRESSION_RECEIPT_HASH_PREFIX}%'},
        ).mappings().all()
        raw_ids = [str(row['id']) for row in raw_rows]

        receipt_rows = []
        if raw_ids:
            receipt_rows = conn.execute(
                text("SELECT id, raw_receipt_id FROM receipt_tables WHERE household_id = :household_id AND raw_receipt_id IN :ids").bindparams(bindparam('ids', expanding=True)),
                {'household_id': effective_household_id, 'ids': raw_ids},
            ).mappings().all()
        receipt_ids = [str(row['id']) for row in receipt_rows]
        batch_reference_ids = [f'receipt:{receipt_id}' for receipt_id in receipt_ids]
        batch_ids = [
            str(row['id'])
            for row in conn.execute(
                text(
                    """
                    SELECT id
                    FROM purchase_import_batches
                    WHERE household_id = :household_id
                      AND (
                        source_reference = 'mock:export-regression-fixture'
                        OR (source_type = 'receipt' AND source_reference IN :references)
                      )
                    """
                ).bindparams(bindparam('references', expanding=True)),
                {'household_id': effective_household_id, 'references': batch_reference_ids or ['__none__']},
            ).mappings().all()
        ]

        if batch_ids:
            processed_event_ids = [
                str(row['processed_event_id'])
                for row in conn.execute(
                    text("SELECT processed_event_id FROM purchase_import_lines WHERE batch_id IN :ids AND processed_event_id IS NOT NULL").bindparams(bindparam('ids', expanding=True)),
                    {'ids': batch_ids},
                ).mappings().all()
                if row.get('processed_event_id')
            ]
            if processed_event_ids:
                conn.execute(
                    text("DELETE FROM inventory_events WHERE id IN :ids").bindparams(bindparam('ids', expanding=True)),
                    {'ids': processed_event_ids},
                )
            conn.execute(text("DELETE FROM purchase_import_lines WHERE batch_id IN :ids").bindparams(bindparam('ids', expanding=True)), {'ids': batch_ids})
            conn.execute(text("DELETE FROM purchase_import_batches WHERE id IN :ids").bindparams(bindparam('ids', expanding=True)), {'ids': batch_ids})

        if receipt_ids:
            conn.execute(text("DELETE FROM receipt_table_lines WHERE receipt_table_id IN :ids").bindparams(bindparam('ids', expanding=True)), {'ids': receipt_ids})
            conn.execute(text("DELETE FROM receipt_inbound_events WHERE receipt_table_id IN :ids").bindparams(bindparam('ids', expanding=True)), {'ids': receipt_ids})
            conn.execute(text("DELETE FROM receipt_tables WHERE id IN :ids").bindparams(bindparam('ids', expanding=True)), {'ids': receipt_ids})
        if raw_ids:
            conn.execute(text("DELETE FROM receipt_email_messages WHERE raw_receipt_id IN :ids").bindparams(bindparam('ids', expanding=True)), {'ids': raw_ids})
            conn.execute(text("DELETE FROM receipt_inbound_events WHERE raw_receipt_id IN :ids").bindparams(bindparam('ids', expanding=True)), {'ids': raw_ids})
            conn.execute(text("DELETE FROM raw_receipts WHERE id IN :ids").bindparams(bindparam('ids', expanding=True)), {'ids': raw_ids})

    return {
        'raw_receipt_count': len(raw_ids),
        'receipt_table_count': len(receipt_ids),
        'batch_count': len(batch_ids),
    }




def _cleanup_almost_out_prediction_regression_fixture(conn, household_id: str) -> None:
    article_rows = conn.execute(
        text(
            """
            SELECT id, global_product_id
            FROM household_articles
            WHERE household_id = :household_id
              AND lower(trim(COALESCE(custom_name, naam))) LIKE 'rt ao %'
            """
        ),
        {'household_id': str(household_id)},
    ).mappings().all()
    article_ids = [str(row.get('id') or '').strip() for row in article_rows if str(row.get('id') or '').strip()]
    product_ids = [str(row.get('global_product_id') or '').strip() for row in article_rows if str(row.get('global_product_id') or '').strip()]

    conn.execute(
        text(
            """
            DELETE FROM inventory
            WHERE household_id = :household_id
              AND lower(trim(naam)) LIKE 'rt ao %'
            """
        ),
        {'household_id': str(household_id)},
    )
    conn.execute(
        text(
            """
            DELETE FROM inventory_events
            WHERE household_id = :household_id
              AND lower(trim(article_name)) LIKE 'rt ao %'
            """
        ),
        {'household_id': str(household_id)},
    )

    if article_ids:
        conn.execute(text("DELETE FROM household_article_notes WHERE household_article_id IN :ids").bindparams(bindparam('ids', expanding=True)), {'ids': article_ids})
        conn.execute(text("DELETE FROM household_article_settings WHERE household_article_id IN :ids").bindparams(bindparam('ids', expanding=True)), {'ids': article_ids})
        conn.execute(text("DELETE FROM household_articles WHERE id IN :ids").bindparams(bindparam('ids', expanding=True)), {'ids': article_ids})
    if product_ids:
        conn.execute(text("DELETE FROM global_products WHERE id IN :ids").bindparams(bindparam('ids', expanding=True)), {'ids': product_ids})


def _seed_almost_out_prediction_regression_fixture(conn, household_id: str) -> dict[str, Any]:
    _cleanup_almost_out_prediction_regression_fixture(conn, household_id)
    now = datetime.now(timezone.utc)
    articles = [
        {
            'key': 'prediction_only',
            'household_name': 'RT AO Koffie',
            'product_name': 'RT Gemalen koffie 500g',
            'current_quantity': 1,
            'min_stock': 0,
            'ideal_stock': 2,
            'status': 'active',
            'packaging_unit': 'pak',
            'packaging_quantity': 1,
            'purchase_offsets_days': [25, 15, 5],
        },
        {
            'key': 'stock_only',
            'household_name': 'RT AO Kerrie',
            'product_name': 'RT Curry Powder 100g',
            'current_quantity': 0,
            'min_stock': 1,
            'ideal_stock': 2,
            'status': 'active',
            'packaging_unit': 'pot',
            'packaging_quantity': 1,
            'purchase_offsets_days': [20],
        },
        {
            'key': 'neither',
            'household_name': 'RT AO Mosterd',
            'product_name': 'RT Dijon Mosterd 200g',
            'current_quantity': 3,
            'min_stock': 1,
            'ideal_stock': 3,
            'status': 'active',
            'packaging_unit': 'pot',
            'packaging_quantity': 1,
            'purchase_offsets_days': [75, 45, 15],
        },
    ]

    seeded_articles: dict[str, dict[str, Any]] = {}
    for article in articles:
        product_id = str(uuid.uuid4())
        article_id = str(uuid.uuid4())
        household_name = article['household_name']
        product_name = article['product_name']
        conn.execute(
            text(
                """
                INSERT INTO global_products (id, name, source, status, created_at, updated_at)
                VALUES (:id, :name, 'regression_fixture', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            ),
            {'id': product_id, 'name': product_name},
        )
        conn.execute(
            text(
                """
                INSERT INTO household_articles (
                    id, household_id, naam, consumable, created_at, updated_at, custom_name,
                    min_stock, ideal_stock, global_product_id, status, source
                ) VALUES (
                    :id, :household_id, :naam, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :custom_name,
                    :min_stock, :ideal_stock, :global_product_id, :status, 'regression_fixture'
                )
                """
            ),
            {
                'id': article_id,
                'household_id': str(household_id),
                'naam': household_name,
                'custom_name': household_name,
                'min_stock': article['min_stock'],
                'ideal_stock': article['ideal_stock'],
                'global_product_id': product_id,
                'status': article['status'],
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO inventory (id, naam, aantal, household_id, space_id, sublocation_id, status, created_at, updated_at)
                VALUES (:id, :naam, :aantal, :household_id, NULL, NULL, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            ),
            {
                'id': str(uuid.uuid4()),
                'naam': household_name,
                'aantal': int(article['current_quantity']),
                'household_id': str(household_id),
            },
        )
        for setting_key, setting_value in {
            'packaging_unit': article['packaging_unit'],
            'packaging_quantity': article['packaging_quantity'],
            'default_location_id': None,
            'default_sublocation_id': None,
            'auto_restock': False,
        }.items():
            conn.execute(
                text(
                    """
                    INSERT INTO household_article_settings (id, household_article_id, setting_key, setting_value, created_at, updated_at)
                    VALUES (:id, :household_article_id, :setting_key, :setting_value, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT(household_article_id, setting_key)
                    DO UPDATE SET setting_value = excluded.setting_value, updated_at = CURRENT_TIMESTAMP
                    """
                ),
                {
                    'id': str(uuid.uuid4()),
                    'household_article_id': article_id,
                    'setting_key': setting_key,
                    'setting_value': json.dumps(setting_value),
                },
            )
        for offset_days in article['purchase_offsets_days']:
            purchase_dt = now - timedelta(days=int(offset_days))
            conn.execute(
                text(
                    """
                    INSERT INTO inventory_events (
                        id, household_id, article_id, article_name, location_id, location_label, event_type, quantity,
                        old_quantity, new_quantity, source, note, created_at, purchase_date, supplier_name
                    ) VALUES (
                        :id, :household_id, :article_id, :article_name, NULL, NULL, 'purchase', :quantity,
                        NULL, NULL, 'regression_fixture', :note, :created_at, :purchase_date, 'Regression seed'
                    )
                    """
                ),
                {
                    'id': str(uuid.uuid4()),
                    'household_id': str(household_id),
                    'article_id': article_id,
                    'article_name': household_name,
                    'quantity': 1,
                    'note': 'RT almost-out prediction fixture',
                    'created_at': purchase_dt.isoformat(),
                    'purchase_date': purchase_dt.date().isoformat(),
                },
            )
        seeded_articles[article['key']] = {
            'household_article_id': article_id,
            'household_name': household_name,
            'product_name': product_name,
        }

    set_household_almost_out_settings(conn, household_id, prediction_enabled=False, prediction_days=14, policy_mode=ALMOST_OUT_POLICY_ADVISORY)
    return {
        'household_id': str(household_id),
        'articles': seeded_articles,
    }


def _evaluate_almost_out_prediction_scenario(conn, household_id: str, *, scenario_id: str, label: str, prediction_enabled: bool, prediction_days: int, policy_mode: str, expected_keys: list[str], fixture_meta: dict[str, Any]) -> dict[str, Any]:
    settings = set_household_almost_out_settings(
        conn,
        household_id,
        prediction_enabled=prediction_enabled,
        prediction_days=prediction_days,
        policy_mode=policy_mode,
    )
    items = build_almost_out_items(conn, household_id)
    actual_keys = []
    trigger_map = {}
    for item in items:
        article_id = str(item.get('household_article_id') or '').strip()
        matched_key = None
        for fixture_key, fixture_article in fixture_meta.get('articles', {}).items():
            if article_id and article_id == fixture_article.get('household_article_id'):
                matched_key = fixture_key
                break
        if matched_key:
            actual_keys.append(matched_key)
            trigger_map[matched_key] = item.get('trigger_type')
    expected_sorted = sorted(expected_keys)
    actual_sorted = sorted(actual_keys)
    passed = expected_sorted == actual_sorted
    error = None
    if not passed:
        error = f"Verwacht {expected_sorted}, kreeg {actual_sorted}"
    return {
        'name': label,
        'scenario_id': scenario_id,
        'status': 'passed' if passed else 'failed',
        'error': error,
        'settings': settings,
        'expected_article_keys': expected_sorted,
        'actual_article_keys': actual_sorted,
        'trigger_types': trigger_map,
        'article_names': {key: fixture_meta.get('articles', {}).get(key, {}).get('household_name') for key in expected_sorted or actual_sorted},
    }


def run_almost_out_prediction_regression_suite() -> dict[str, Any]:
    household_id = str(ensure_household('admin@rezzerv.local').get('id') or '1')
    with engine.begin() as conn:
        fixture_meta = _seed_almost_out_prediction_regression_fixture(conn, household_id)
        results = [
            _evaluate_almost_out_prediction_scenario(
                conn, household_id,
                scenario_id='prediction_off',
                label='Prediction uit: alleen stock-only artikel verschijnt',
                prediction_enabled=False, prediction_days=14, policy_mode=ALMOST_OUT_POLICY_ADVISORY,
                expected_keys=['stock_only'], fixture_meta=fixture_meta,
            ),
            _evaluate_almost_out_prediction_scenario(
                conn, household_id,
                scenario_id='prediction_14_advisory',
                label='Prediction aan 14 dagen advisory: prediction-only en stock-only verschijnen',
                prediction_enabled=True, prediction_days=14, policy_mode=ALMOST_OUT_POLICY_ADVISORY,
                expected_keys=['prediction_only', 'stock_only'], fixture_meta=fixture_meta,
            ),
            _evaluate_almost_out_prediction_scenario(
                conn, household_id,
                scenario_id='prediction_3_advisory',
                label='Prediction aan 3 dagen advisory: prediction-only verdwijnt weer',
                prediction_enabled=True, prediction_days=3, policy_mode=ALMOST_OUT_POLICY_ADVISORY,
                expected_keys=['stock_only'], fixture_meta=fixture_meta,
            ),
            _evaluate_almost_out_prediction_scenario(
                conn, household_id,
                scenario_id='prediction_14_override',
                label='Prediction aan 14 dagen override: prediction-only en stock-only via fallback',
                prediction_enabled=True, prediction_days=14, policy_mode=ALMOST_OUT_POLICY_OVERRIDE,
                expected_keys=['prediction_only', 'stock_only'], fixture_meta=fixture_meta,
            ),
        ]
    passed = sum(1 for item in results if item['status'] == 'passed')
    failed = sum(1 for item in results if item['status'] == 'failed')
    return {
        'test_type': 'almost_out_prediction',
        'status': 'failed' if failed else 'passed',
        'passed_count': passed,
        'failed_count': failed,
        'results': results,
        'fixture': fixture_meta,
    }


@app.post("/api/dev/regression/almost-out-prediction")
def run_almost_out_prediction_regression_endpoint():
    report = run_almost_out_prediction_regression_suite()
    testing_service.complete_external_test('almost_out_prediction', report.get('results', []))
    return report

@app.post("/api/dev/regression/almost-out-self-test")
def run_almost_out_backend_self_test_endpoint():
    report = run_almost_out_backend_self_test(engine)
    testing_service.complete_external_test('almost_out_self_test', report.get('results', []))
    return report

@app.post("/api/dev/regression/reset")
def reset_regression_fixture_state():
    household_id = str(ensure_household("admin@rezzerv.local").get("id") or "1")
    cleanup = cleanup_regression_fixture_state(household_id)
    fixture = ensure_regression_inventory_fixture(household_id)
    version_path = Path(__file__).resolve().parents[2] / "VERSION.txt"
    version = version_path.read_text(encoding="utf-8").strip() if version_path.exists() else None
    payload = {
        "status": "ok",
        "dataset": "ui_seed_with_inventory_fixture",
        "household_id": household_id,
        "version": version,
        "cleanup": cleanup,
        "inventory_fixture": fixture,
    }
    log_regression_action('fixture.reset', **payload)
    return payload


@app.post("/api/dev/regression/ensure-inventory-fixture")
def ensure_regression_inventory_fixture_endpoint():
    household_id = str(ensure_household("admin@rezzerv.local").get("id") or "1")
    fixture = ensure_regression_inventory_fixture(household_id)
    return {
        "status": "ok",
        "household_id": household_id,
        **fixture,
    }


@app.post("/api/dev/regression/cleanup")
def cleanup_regression_fixture_state_endpoint():
    household_id = str(ensure_household("admin@rezzerv.local").get("id") or "1")
    return cleanup_regression_fixture_state(household_id)

@app.get("/api/dev/regression/receipt-fixture-file")
def get_regression_receipt_fixture_file(kind: str = Query('manual')):
    fixtures_root = Path(__file__).resolve().parent / 'testing' / 'receipt_parsing' / 'raw'
    fixture_map = {
        'manual': {
            'path': fixtures_root / 'Jumbo bon.jpeg',
            'filename': 'regression-manual.jpg',
            'media_type': 'image/jpeg',
        },
        'email': {
            'path': fixtures_root / 'Lidl3.eml',
            'filename': 'regression-email.eml',
            'media_type': 'message/rfc822',
        },
        'camera': {
            'path': fixtures_root / 'ALDI-kassabon-NL-voorbeeld.jpg',
            'filename': 'regression-camera.jpg',
            'media_type': 'image/jpeg',
        },
        'share': {
            'path': fixtures_root / 'AH_kassabon_2026-03-14 171300_8770.pdf',
            'filename': 'regression-share.pdf',
            'media_type': 'application/pdf',
        },
    }
    selected = fixture_map.get(str(kind or '').strip().lower())
    if not selected:
        raise HTTPException(status_code=400, detail='Onbekend regressie-fixturetype')
    file_path = selected['path']
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail='Regressie-fixturebestand ontbreekt')
    return FileResponse(path=file_path, filename=selected['filename'], media_type=selected['media_type'])


@app.post("/api/dev/regression/seed-kassa-receipts")
def seed_regression_kassa_receipts(authorization: Optional[str] = Header(None)):
    require_platform_admin_user(authorization)
    household = ensure_household("admin@rezzerv.local")
    household_id = str(household.get('id') or '1')
    ensure_default_receipt_sources(engine, RECEIPT_STORAGE_ROOT, household_id)
    fixtures_root = Path(__file__).resolve().parent / 'testing' / 'receipt_parsing' / 'raw'
    reviewed_storage = str((fixtures_root / 'Lidl2.eml').resolve())
    review_storage = str((fixtures_root / 'ALDI-kassabon-NL-voorbeeld.jpg').resolve())
    new_storage = str((fixtures_root / 'Lidl3.eml').resolve())

    clear_regression_receipt_state(household_id)

    with engine.begin() as conn:
        def insert_receipt(*, receipt_id: str, storage_path: str, original_filename: str, mime_type: str, sha_seed: str, store_name: str,
                           purchase_at: str | None, total_amount: float | None, discount_total: float | None, parse_status: str,
                           lines: list[dict[str, Any]]):
            raw_receipt_id = str(uuid.uuid4())
            conn.execute(
                text("""
                INSERT INTO raw_receipts (
                    id, household_id, source_id, original_filename, mime_type, storage_path, sha256_hash,
                    duplicate_of_raw_receipt_id, raw_status, imported_at, created_at
                ) VALUES (
                    :id, :household_id, NULL, :original_filename, :mime_type, :storage_path, :sha256_hash,
                    NULL, 'imported', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """),
                {
                    'id': raw_receipt_id,
                    'household_id': household_id,
                    'original_filename': original_filename,
                    'mime_type': mime_type,
                    'storage_path': storage_path,
                    'sha256_hash': f'regression-seed::{sha_seed}::{receipt_id}',
                },
            )
            conn.execute(
                text("""
                INSERT INTO receipt_tables (
                    id, raw_receipt_id, household_id, store_name, store_branch, purchase_at, total_amount,
                    discount_total, currency, parse_status, confidence_score, line_count, created_at, updated_at
                ) VALUES (
                    :id, :raw_receipt_id, :household_id, :store_name, NULL, :purchase_at, :total_amount,
                    :discount_total, 'EUR', :parse_status, 0.99, :line_count, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """),
                {
                    'id': receipt_id,
                    'raw_receipt_id': raw_receipt_id,
                    'household_id': household_id,
                    'store_name': store_name,
                    'purchase_at': purchase_at,
                    'total_amount': total_amount,
                    'discount_total': discount_total,
                    'parse_status': parse_status,
                    'line_count': len(lines),
                },
            )
            for index, line in enumerate(lines, start=1):
                conn.execute(
                    text("""
                    INSERT INTO receipt_table_lines (
                        id, receipt_table_id, line_index, raw_label, normalized_label, quantity, unit,
                        unit_price, line_total, discount_amount, barcode, article_match_status, matched_article_id,
                        confidence_score, created_at, updated_at
                    ) VALUES (
                        :id, :receipt_table_id, :line_index, :raw_label, :normalized_label, :quantity, :unit,
                        :unit_price, :line_total, :discount_amount, NULL, 'unmatched', NULL,
                        0.99, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """),
                    {
                        'id': str(uuid.uuid4()),
                        'receipt_table_id': receipt_id,
                        'line_index': index,
                        'raw_label': line['raw_label'],
                        'normalized_label': str(line['raw_label']).strip().lower(),
                        'quantity': line.get('quantity'),
                        'unit': line.get('unit') or '',
                        'unit_price': line.get('unit_price'),
                        'line_total': line.get('line_total'),
                        'discount_amount': line.get('discount_amount'),
                    },
                )
            return raw_receipt_id

        reviewed_receipt_id = str(uuid.uuid4())
        review_receipt_id = str(uuid.uuid4())
        new_receipt_id = str(uuid.uuid4())

        insert_receipt(
            receipt_id=reviewed_receipt_id,
            storage_path=reviewed_storage,
            original_filename='seed-reviewed.eml',
            mime_type='message/rfc822',
            sha_seed='reviewed',
            store_name='Lidl',
            purchase_at='2026-03-21T12:34:00',
            total_amount=2.49,
            discount_total=0.0,
            parse_status='parsed',
            lines=[{'raw_label': 'Melk', 'quantity': 1, 'unit': 'stuk', 'unit_price': 2.49, 'line_total': 2.49, 'discount_amount': 0.0}],
        )
        insert_receipt(
            receipt_id=review_receipt_id,
            storage_path=review_storage,
            original_filename='seed-review.jpg',
            mime_type='image/jpeg',
            sha_seed='review-needed',
            store_name='ALDI',
            purchase_at='2026-03-21T13:15:00',
            total_amount=1.99,
            discount_total=0.0,
            parse_status='review_needed',
            lines=[{'raw_label': 'Tomaten', 'quantity': 1, 'unit': 'stuk', 'unit_price': 1.99, 'line_total': 1.99, 'discount_amount': 0.0}],
        )
        insert_receipt(
            receipt_id=new_receipt_id,
            storage_path=new_storage,
            original_filename='seed-new.eml',
            mime_type='message/rfc822',
            sha_seed='new',
            store_name='Jumbo',
            purchase_at='2026-03-21T14:00:00',
            total_amount=None,
            discount_total=None,
            parse_status='partial',
            lines=[],
        )

        reviewed_batch_id = ensure_unpack_batch_for_receipt(conn, {
            'receipt_table_id': reviewed_receipt_id,
            'household_id': household_id,
            'store_name': 'Lidl',
            'purchase_at': '2026-03-21T12:34:00',
            'created_at': '2026-03-21T12:34:00',
            'currency': 'EUR',
        })
        review_batch_id = ensure_unpack_batch_for_receipt(conn, {
            'receipt_table_id': review_receipt_id,
            'household_id': household_id,
            'store_name': 'ALDI',
            'purchase_at': '2026-03-21T13:15:00',
            'created_at': '2026-03-21T13:15:00',
            'currency': 'EUR',
        })

    return {
        'status': 'ok',
        'household_id': household_id,
        'receipts': {
            'reviewed': {'receipt_table_id': reviewed_receipt_id, 'batch_id': reviewed_batch_id, 'store_name': 'Lidl', 'inbox_status': 'Gecontroleerd', 'article_name': 'Melk'},
            'review_needed': {'receipt_table_id': review_receipt_id, 'batch_id': review_batch_id, 'store_name': 'ALDI', 'inbox_status': 'Controle nodig', 'article_name': 'Tomaten'},
            'new': {'receipt_table_id': new_receipt_id, 'store_name': 'Jumbo', 'inbox_status': 'Handmatig'},
        },
    }


@app.post("/api/dev/run-smoke-tests", response_model=TestStartResponse)
def run_smoke_tests(authorization: Optional[str] = Header(None)):
    require_platform_admin_user(authorization)
    return testing_service.start_external_test("smoke")


@app.post("/api/dev/run-regression-tests", response_model=TestStartResponse)
def run_regression_tests(authorization: Optional[str] = Header(None)):
    require_platform_admin_user(authorization)
    return testing_service.start_external_test("regression")

@app.post("/api/dev/run-layer1-tests", response_model=TestStartResponse)
def run_layer1_tests(authorization: Optional[str] = Header(None)):
    require_platform_admin_user(authorization)
    return testing_service.start_external_test("layer1")

@app.post("/api/dev/run-layer2-tests", response_model=TestStartResponse)
def run_layer2_tests(authorization: Optional[str] = Header(None)):
    require_platform_admin_user(authorization)
    return testing_service.start_external_test("layer2")

@app.post("/api/dev/run-layer3-tests", response_model=TestStartResponse)
def run_layer3_tests(authorization: Optional[str] = Header(None)):
    require_platform_admin_user(authorization)
    return testing_service.start_external_test("layer3")

@app.post("/api/dev/run-parsing-fixture-tests")
def run_parsing_fixture_tests(authorization: Optional[str] = Header(None)):
    require_platform_admin_user(authorization)
    started = testing_service.start_external_test("parsing_fixture")
    if not started.get("started"):
        raise HTTPException(status_code=409, detail="Er loopt al een andere test")
    results = run_receipt_parsing_baseline_suite("fixture")
    testing_service.complete_external_test("parsing_fixture", results)
    return testing_service.get_report()

@app.post("/api/dev/run-parsing-raw-tests")
def run_parsing_raw_tests(authorization: Optional[str] = Header(None)):
    require_platform_admin_user(authorization)
    started = testing_service.start_external_test("parsing_raw")
    if not started.get("started"):
        raise HTTPException(status_code=409, detail="Er loopt al een andere test")
    results = run_receipt_parsing_baseline_suite("raw")
    testing_service.complete_external_test("parsing_raw", results)
    return testing_service.get_report()


@app.post("/api/dev/test-report", response_model=TestStatusResponse)
def complete_test_report(payload: TestCompleteRequest):
    results = [item.model_dump() for item in payload.results]
    return testing_service.complete_external_test(payload.test_type, results)


@app.get("/api/dev/test-status", response_model=TestStatusResponse)
def get_test_status():
    return testing_service.get_status()


@app.get("/api/dev/test-report/latest", response_model=TestReportResponse)
def get_latest_test_report():
    return testing_service.get_report()

@app.post("/api/dev/generate-large-dataset")
def generate_large_dataset(authorization: Optional[str] = Header(None)):
    require_platform_admin_user(authorization)
    import random
    reset_dev_tables()

    spaces=["Keuken","Berging","Badkamer","Garage","Kantoor"]
    sub=["Kast 1","Kast 2","Koelkast","Diepvries","Plank"]

    with engine.begin() as conn:

        space_ids=[]
        for s in spaces:
            sid=conn.execute(
                text("INSERT INTO spaces (id, naam, household_id) VALUES (lower(hex(randomblob(16))), :naam, 'demo-household') RETURNING id"),
                {"naam":s}
            ).scalar_one()
            space_ids.append(sid)

        sub_ids=[]
        for sid in space_ids:
            for name in sub:
                subid=conn.execute(
                    text("INSERT INTO sublocations (id, naam, space_id) VALUES (lower(hex(randomblob(16))), :naam, :sid) RETURNING id"),
                    {"naam":name,"sid":sid}
                ).scalar_one()
                sub_ids.append((sid,subid))

        products=[
            "Rijst","Pasta","Tomaten","Koffie","Thee","Melk","Yoghurt","Bonen",
            "Mais","Erwten","Zout","Peper","Olijfolie","Suiker","Meel"
        ]

        for i in range(200):
            naam=random.choice(products)+" "+str(i)
            aantal=random.randint(1,10)
            sid,subid=random.choice(sub_ids)

            conn.execute(
                text("""
                INSERT INTO inventory (id, naam, aantal, household_id, space_id, sublocation_id)
                VALUES (lower(hex(randomblob(16))), :naam, :aantal, 'demo-household', :sid, :subid)
                """),
                {"naam":naam,"aantal":aantal,"sid":sid,"subid":subid}
            )

    return {"status":"ok","inventory":count_table("inventory")}


@app.post("/api/dev/generate-article-testdata")
def generate_article_testdata(authorization: Optional[str] = Header(None)):
    require_platform_admin_user(authorization)
    """Dataset speciaal voor testen Artikel Details"""
    import random

    reset_dev_tables()

    spaces=["Keuken","Berging","Koelkast","Voorraadkast"]
    sublocs=["Kast 1","Kast 2","Boven","Onder","Plank A","Plank B"]

    with engine.begin() as conn:

        space_ids=[]
        for s in spaces:
            sid=conn.execute(
                text("INSERT INTO spaces (id, naam, household_id) VALUES (lower(hex(randomblob(16))), :naam, 'demo-household') RETURNING id"),
                {"naam":s}
            ).scalar_one()
            space_ids.append(sid)

        sub_ids=[]
        for sid in space_ids:
            for name in sublocs[:3]:
                subid=conn.execute(
                    text("INSERT INTO sublocations (id, naam, space_id) VALUES (lower(hex(randomblob(16))), :naam, :sid) RETURNING id"),
                    {"naam":name,"sid":sid}
                ).scalar_one()
                sub_ids.append((sid,subid))

        artikelen=[
            "Tomaten","Spaghetti","Koffie","Thee","Melk","Yoghurt","Rijst",
            "Bonen","Mais","Olijfolie","Pasta saus","Paprika","Tuna"
        ]

        # meerdere voorraadlocaties per artikel
        for artikel in artikelen:
            locaties=random.sample(sub_ids, random.randint(1,3))

            for sid,subid in locaties:
                conn.execute(
                    text("""
                    INSERT INTO inventory (id, naam, aantal, household_id, space_id, sublocation_id)
                    VALUES (lower(hex(randomblob(16))), :naam, :aantal, 'demo-household', :sid, :subid)
                    """),
                    {
                        "naam":artikel,
                        "aantal":random.randint(1,8),
                        "sid":sid,
                        "subid":subid
                    }
                )

    return {"status":"ok","inventory":count_table("inventory")}



from app.api.router import api_router
app.include_router(api_router)

from fastapi import FastAPI, HTTPException, Header, Query, Request, Response, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from pydantic import BaseModel, Field, field_validator
import base64
import hashlib
import hmac
import html
import json
import os
from pathlib import Path
import secrets
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
import re
from typing import Any, List, Optional
from app.schemas.testing import TestStartResponse, TestStatusResponse, TestReportResponse, TestCompleteRequest
from app.services.testing_service import testing_service
from app.services.receipt_service import ensure_default_receipt_sources, ensure_share_receipt_source, ingest_receipt, reparse_receipt, scan_receipt_source, serialize_receipt_row
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
import logging
from sqlalchemy import text

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
RECEIPT_INBOUND_PATH = '/api/receipts/inbound'



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

# In-memory opslag (MVP login)
households = {}
users = {
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

class SpaceCreate(BaseModel):
    naam: str
    household_id: Optional[str] = None

class SublocationCreate(BaseModel):
    naam: str
    space_id: str

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


class ArticleArchiveRequest(BaseModel):
    article_name: str
    reason: Optional[str] = None


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
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_household_articles_household_name ON household_articles (household_id, naam)"))


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
        conn.execute(
            text(
                """
                INSERT INTO household_articles (id, household_id, naam, consumable, updated_at)
                VALUES (:id, :household_id, :naam, :consumable, CURRENT_TIMESTAMP)
                """
            ),
            {"id": str(uuid.uuid4()), "household_id": str(household_id), "naam": normalized, "consumable": 1 if resolved_consumable else 0},
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
    return build_live_article_option_id(final_name)


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

def build_auth_token(email: str) -> str:
    return f"rezzerv-dev-token::{email}"


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

    user = users.get(email)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    return {"email": email, **user}


def get_household_payload_for_user(user: dict):
    household = ensure_household(user["email"])
    return {
        **household,
        "current_user_email": user["email"],
        "is_household_admin": user.get("role") == "admin",
        "can_edit_store_import_simplification_level": user.get("role") == "admin",
    }


def get_request_household_id(authorization: str | None, fallback: str = "demo-household") -> str:
    if authorization:
        try:
            user = get_current_user_from_authorization(authorization)
            household = get_household_payload_for_user(user)
            return str(household.get("id") or fallback)
        except HTTPException:
            pass
    return str(fallback)


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


def build_live_article_option_id(article_name: str) -> str:
    return f"live::{(article_name or '').strip()}"


def get_store_review_article_options(conn):
    items = [dict(item) for item in MOCK_ARTICLE_OPTIONS]
    seen_names = {item["name"].strip().lower() for item in items if item.get("name")}

    live_names = conn.execute(
        text(
            """
            SELECT DISTINCT article_name, consumable
            FROM (
                SELECT naam AS article_name, consumable FROM household_articles WHERE trim(COALESCE(naam, '')) <> ''
                UNION
                SELECT naam AS article_name, NULL AS consumable FROM inventory WHERE trim(COALESCE(naam, '')) <> ''
            ) src
            ORDER BY lower(article_name) ASC
            """
        )
    ).mappings().all()

    for row in live_names:
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
            "consumable": bool(row["consumable"]) if row.get("consumable") is not None else infer_consumable_from_name(article_name),
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
    if article_id.startswith("live::"):
        article_name = article_id.split("::", 1)[1].strip()
        if article_name:
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
):
    safe_location = require_resolved_location(resolved_location)
    event_id = str(uuid.uuid4())
    conn.execute(
        text(
            """
            INSERT INTO inventory_events (
                id, household_id, article_id, article_name, location_id, location_label,
                event_type, quantity, old_quantity, new_quantity, source, note, created_at
            ) VALUES (
                :id, :household_id, :article_id, :article_name, :location_id, :location_label,
                :event_type, :quantity, :old_quantity, :new_quantity, :source, :note, CURRENT_TIMESTAMP
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
            INSERT INTO inventory (id, naam, aantal, household_id, space_id, sublocation_id)
            VALUES (:id, :naam, :aantal, :household_id, :space_id, :sublocation_id)
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
              COALESCE(s.naam, '') AS locatie,
              COALESCE(sl.naam, '') AS sublocatie,
              COALESCE(i.status, 'active') AS status
            FROM inventory i
            LEFT JOIN spaces s ON s.id = i.space_id
            LEFT JOIN sublocations sl ON sl.id = i.sublocation_id
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


def create_inventory_purchase_event(conn, household_id: str, article_id: str, article_name: str, quantity: float, resolved_location: dict, note: str):
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
    return bool(RESEND_API_KEY)


def resend_json_request(path: str, method: str = 'GET', *, data: Any = None, timeout: float = 30.0) -> dict[str, Any]:
    if not resend_is_configured():
        raise HTTPException(status_code=503, detail='De Resend API-sleutel is nog niet geconfigureerd in Rezzerv.')
    url = f"{RESEND_API_BASE_URL}/{path.lstrip('/')}"
    request_headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {RESEND_API_KEY}',
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
            detail = parsed.get('message') or parsed.get('error') or parsed.get('detail')
        except Exception:
            detail = body or exc.reason
        raise HTTPException(status_code=exc.code, detail=normalize_api_error_message(detail, 'Resend-verzoek is mislukt.'))
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=normalize_api_error_message(exc.reason, 'Resend is momenteel niet bereikbaar.'))


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
    result = ingest_receipt(
        engine=engine,
        receipt_storage_root=RECEIPT_STORAGE_ROOT,
        household_id=str(household_id),
        filename=payload['selected_filename'],
        file_bytes=payload['selected_bytes'],
        source_id=effective_source_id,
        mime_type=payload['selected_mime_type'],
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
    result['source_id'] = effective_source_id
    result['source_label'] = default_email_source.get('label', 'E-mail')
    result['sender_email'] = payload.get('sender_email')
    result['sender_name'] = payload.get('sender_name')
    result['subject'] = payload.get('subject')
    result['received_at'] = payload.get('received_at')
    return result


def ensure_household(email: str):
    user = users.get(email, {})
    household_key = user.get("household_key", email)
    if household_key not in households:
        households[household_key] = {
            "id": str(user.get("household_id") or len(households) + 1),
            "naam": user.get("household_name") or "Mijn huishouden",
            "created_at": datetime.utcnow().isoformat(),
        }
    return households[household_key]


@app.get("/api/health")
def health():
    return {"status": "ok"}




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
        result = ingest_receipt(
            engine=engine,
            receipt_storage_root=RECEIPT_STORAGE_ROOT,
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
        result = ingest_receipt(
            engine=engine,
            receipt_storage_root=RECEIPT_STORAGE_ROOT,
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
):
    effective_household_id = str(household_id).strip() or "1"
    ensure_default_receipt_sources(engine, RECEIPT_STORAGE_ROOT, effective_household_id)
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Leeg bestand")
    result = ingest_receipt(
        engine=engine,
        receipt_storage_root=RECEIPT_STORAGE_ROOT,
        household_id=effective_household_id,
        filename=file.filename or "receipt",
        file_bytes=file_bytes,
        source_id=f"{effective_household_id}-manual-upload",
        mime_type=file.content_type,
    )
    status_code = 200 if result.get("duplicate") else 201
    return JSONResponse(status_code=status_code, content=result)


@app.post("/api/receipts/delete")
def delete_receipts(payload: ReceiptDeleteRequest):
    receipt_ids = [str(value).strip() for value in (payload.receipt_table_ids or []) if str(value).strip()]
    if not receipt_ids:
        raise HTTPException(status_code=400, detail="receipt_table_ids is verplicht")
    placeholders = ", ".join([f":id_{idx}" for idx, _ in enumerate(receipt_ids)])
    params = {f"id_{idx}": value for idx, value in enumerate(receipt_ids)}
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT rt.id AS receipt_table_id, rt.raw_receipt_id
                FROM receipt_tables rt
                WHERE rt.id IN ({placeholders})
                  AND rt.deleted_at IS NULL
                """
            ),
            params,
        ).mappings().all()
        if not rows:
            return {'deleted_receipt_table_ids': [], 'deleted_count': 0}
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
def list_receipt_sources(householdId: str = Query(...)):
    effective_household_id = str(householdId).strip() or '1'
    return {'items': list_receipt_sources_for_household(effective_household_id)}


@app.post("/api/receipt-sources")
def register_receipt_source(payload: ReceiptSourceCreateRequest):
    return create_receipt_source(payload)


@app.get("/api/receipt-sources/email-route")
def get_receipt_email_route(householdId: str = Query(...)):
    effective_household_id = str(householdId).strip() or '1'
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
def get_receipt_gmail_status(householdId: str = Query(...)):
    effective_household_id = str(householdId).strip() or '1'
    status = get_receipt_gmail_account(effective_household_id, create_if_missing=True)
    status['gmail_route_address'] = build_household_email_address(effective_household_id)
    status['configured'] = gmail_is_configured()
    return status


@app.get("/api/receipts/gmail/connect-url")
def get_receipt_gmail_connect_url(
    request: Request,
    householdId: str = Query(...),
    frontendOrigin: str = Query(''),
):
    if not gmail_is_configured():
        raise HTTPException(status_code=503, detail='De Gmail-koppeling is nog niet geconfigureerd in Rezzerv. Voeg eerst Google OAuth clientgegevens toe.')
    effective_household_id = str(householdId).strip() or '1'
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
def sync_receipt_gmail_mailbox(householdId: str = Query(...)):
    effective_household_id = str(householdId).strip() or '1'
    result = sync_gmail_receipts(effective_household_id)
    return result


@app.post("/api/receipts/email-import")
async def import_email_receipt(
    household_id: str = Form(...),
    email_file: UploadFile = File(...),
):
    effective_household_id = str(household_id).strip() or '1'
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
def source_scan_receipts(payload: ReceiptSourceScanRequest):
    source_id = (payload.source_id or "").strip()
    if not source_id:
        raise HTTPException(status_code=400, detail="source_id is verplicht")
    try:
        result = scan_receipt_source(engine, RECEIPT_STORAGE_ROOT, source_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Onbekende receipt-bron")
    return result


@app.get("/api/receipts")
def list_receipts(householdId: str = Query(...)):
    effective_household_id = str(householdId).strip() or "1"
    ensure_default_receipt_sources(engine, RECEIPT_STORAGE_ROOT, effective_household_id)
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                WITH ranked_receipts AS (
                    SELECT
                        rt.id AS receipt_table_id,
                        rt.raw_receipt_id,
                        rt.store_name,
                        rt.purchase_at,
                        rt.total_amount,
                        rt.currency,
                        rt.parse_status,
                        rt.line_count,
                        COALESCE(rs.label, 'Manual upload') AS source_label,
                        rem.sender_email,
                        rem.sender_name,
                        rem.subject AS email_subject,
                        rem.received_at AS email_received_at,
                        rt.created_at,
                        COALESCE((
                            SELECT SUM(COALESCE(rtl.line_total, 0))
                            FROM receipt_table_lines rtl
                            WHERE rtl.receipt_table_id = rt.id
                        ), 0) AS line_total_sum,
                        COALESCE(NULLIF(rr.sha256_hash, ''), rt.id) AS dedupe_key,
                        ROW_NUMBER() OVER (
                            PARTITION BY COALESCE(NULLIF(rr.sha256_hash, ''), rt.id)
                            ORDER BY COALESCE(rt.purchase_at, rt.created_at) DESC, rt.created_at DESC, rt.id DESC
                        ) AS dedupe_rank
                    FROM receipt_tables rt
                    JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                    LEFT JOIN receipt_sources rs ON rs.id = rr.source_id
                    LEFT JOIN receipt_email_messages rem ON rem.raw_receipt_id = rr.id
                    WHERE rt.household_id = :household_id
                      AND rt.deleted_at IS NULL
                      AND rr.deleted_at IS NULL
                )
                SELECT
                    receipt_table_id,
                    raw_receipt_id,
                    store_name,
                    purchase_at,
                    total_amount,
                    currency,
                    parse_status,
                    line_count,
                    source_label,
                    sender_email,
                    sender_name,
                    email_subject,
                    email_received_at,
                    created_at,
                    line_total_sum
                FROM ranked_receipts
                WHERE dedupe_rank = 1
                ORDER BY COALESCE(purchase_at, created_at) DESC, created_at DESC
                """
            ),
            {"household_id": effective_household_id},
        ).mappings().all()
    return {"items": [serialize_receipt_row(dict(row)) for row in rows]}


@app.get("/api/receipts/{receipt_table_id}/preview")
def get_receipt_preview(receipt_table_id: str):
    with engine.begin() as conn:
        record = conn.execute(
            text(
                """
                SELECT rt.id AS receipt_table_id, rr.original_filename, rr.mime_type, rr.storage_path
                FROM receipt_tables rt
                JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
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
def get_receipt_detail(receipt_table_id: str):
    with engine.begin() as conn:
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
                    rt.currency,
                    rt.parse_status,
                    rt.confidence_score,
                    rt.line_count,
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
                        SELECT SUM(COALESCE(rtl.line_total, 0))
                        FROM receipt_table_lines rtl
                        WHERE rtl.receipt_table_id = rt.id
                    ), 0) AS line_total_sum
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
                    normalized_label,
                    quantity,
                    unit,
                    unit_price,
                    line_total,
                    discount_amount,
                    barcode,
                    article_match_status,
                    matched_article_id,
                    confidence_score
                FROM receipt_table_lines
                WHERE receipt_table_id = :receipt_table_id
                ORDER BY line_index ASC, created_at ASC
                """
            ),
            {"receipt_table_id": receipt_table_id},
        ).mappings().all()
    payload = serialize_receipt_row(dict(header))
    payload["lines"] = [serialize_receipt_row(dict(line)) for line in lines]
    return payload


@app.post("/api/receipts/{receipt_table_id}/reparse")
def reparse_receipt_table(receipt_table_id: str):
    result = reparse_receipt(engine, RECEIPT_STORAGE_ROOT, receipt_table_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Receipt table niet gevonden")
    return result


@app.post("/api/auth/login")
def login(payload: LoginRequest):
    user = users.get(payload.email)

    if user and user["password"] == payload.password:
        household = ensure_household(payload.email)
        ensure_default_receipt_sources(engine, RECEIPT_STORAGE_ROOT, str(household.get("id") or "1"))

        return {
            "token": build_auth_token(payload.email),
            "user": {"email": payload.email, "role": user.get("role", "member")}
        }

    raise HTTPException(status_code=401, detail="Ongeldige inloggegevens")


@app.get("/api/household")
def get_household(authorization: Optional[str] = Header(None)):
    user = get_current_user_from_authorization(authorization)
    household = get_household_payload_for_user(user)
    with engine.begin() as conn:
        household["store_import_simplification_level"] = get_household_store_import_simplification_level(conn, household["id"])
    return household


@app.get("/api/household/automation-settings")
def get_household_automation_settings(authorization: Optional[str] = Header(None)):
    user = get_current_user_from_authorization(authorization)
    household = get_household_payload_for_user(user)
    with engine.begin() as conn:
        mode = get_household_auto_consume_mode(conn, household["id"])
        has_explicit_value = has_household_auto_consume_mode(conn, household["id"])
    return {
        "household_id": household["id"],
        "mode": mode,
        "auto_consume_on_repurchase": mode != ARTICLE_AUTO_CONSUME_NONE,
        "has_explicit_value": has_explicit_value,
        "is_household_admin": household["is_household_admin"],
    }


@app.put("/api/household/automation-settings")
def update_household_automation_settings(payload: HouseholdAutomationSettingsUpdateRequest, authorization: Optional[str] = Header(None)):
    user = get_current_user_from_authorization(authorization)
    household = get_household_payload_for_user(user)
    if not household["is_household_admin"]:
        raise HTTPException(status_code=403, detail="Alleen de beheerder van het huishouden mag dit wijzigen")
    with engine.begin() as conn:
        mode = set_household_auto_consume_mode(conn, household["id"], payload.mode)
    return {
        "household_id": household["id"],
        "mode": mode,
        "auto_consume_on_repurchase": mode != ARTICLE_AUTO_CONSUME_NONE,
        "has_explicit_value": True,
        "is_household_admin": household["is_household_admin"],
    }


@app.get("/api/household/store-import-settings")
def get_store_import_settings(authorization: Optional[str] = Header(None)):
    user = get_current_user_from_authorization(authorization)
    household = get_household_payload_for_user(user)
    with engine.begin() as conn:
        level = get_household_store_import_simplification_level(conn, household["id"])
    return {
        "household_id": household["id"],
        "store_import_simplification_level": level,
        "can_edit_store_import_simplification_level": household["can_edit_store_import_simplification_level"],
        "is_household_admin": household["is_household_admin"],
    }


@app.put("/api/household/store-import-settings")
def update_store_import_settings(payload: StoreImportSimplificationUpdateRequest, authorization: Optional[str] = Header(None)):
    user = get_current_user_from_authorization(authorization)
    household = get_household_payload_for_user(user)
    if not household["can_edit_store_import_simplification_level"]:
        raise HTTPException(status_code=403, detail="Alleen de beheerder van het huishouden mag dit wijzigen")
    with engine.begin() as conn:
        level = set_household_store_import_simplification_level(conn, household["id"], payload.store_import_simplification_level)
    return {
        "household_id": household["id"],
        "store_import_simplification_level": level,
        "can_edit_store_import_simplification_level": household["can_edit_store_import_simplification_level"],
        "is_household_admin": household["is_household_admin"],
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
    user = get_current_user_from_authorization(authorization)
    household = get_household_payload_for_user(user)
    with engine.begin() as conn:
        visibility = set_household_article_field_visibility(conn, household["id"], payload)
    return visibility


@app.get("/api/articles/{article_id}/automation-override")
def get_article_automation_override(article_id: str, authorization: Optional[str] = Header(None)):
    user = get_current_user_from_authorization(authorization)
    household = get_household_payload_for_user(user)
    with engine.begin() as conn:
        article = resolve_review_article_option(conn, article_id, household["id"])
        if not article:
            raise HTTPException(status_code=404, detail="Onbekend artikel")
        mode = get_household_article_auto_consume_override(conn, household["id"], article["id"])
        has_explicit_override = has_household_article_auto_consume_override(conn, household["id"], article["id"])
        consumable = get_article_consumable_state(conn, household["id"], article["id"], article.get("name"))
    return {
        "article_id": article["id"],
        "mode": mode,
        "has_explicit_override": has_explicit_override,
        "consumable": consumable,
        "article_name": article.get("name") or "",
    }


@app.put("/api/articles/{article_id}/automation-override")
def update_article_automation_override(article_id: str, payload: ArticleAutomationOverrideUpdateRequest, authorization: Optional[str] = Header(None)):
    user = get_current_user_from_authorization(authorization)
    household = get_household_payload_for_user(user)
    with engine.begin() as conn:
        article = resolve_review_article_option(conn, article_id, household["id"])
        if not article:
            raise HTTPException(status_code=404, detail="Onbekend artikel")
        mode = set_household_article_auto_consume_override(conn, household["id"], article["id"], payload.mode)
        consumable = get_article_consumable_state(conn, household["id"], article["id"], article.get("name"))
    return {
        "article_id": article["id"],
        "mode": mode,
        "has_explicit_override": True,
        "consumable": consumable,
        "article_name": article.get("name") or "",
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
from app.models import household, space, sublocation, inventory, store_provider, store_connection, purchase_import, receipt

Base.metadata.create_all(bind=engine)
ensure_household_settings_schema()
ensure_household_articles_schema()
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
ensure_receipt_storage_root()
seed_store_providers()
admin_household = ensure_household("admin@rezzerv.local")
ensure_default_receipt_sources(engine, RECEIPT_STORAGE_ROOT, str(admin_household.get("id") or "1"))


def ensure_ui_test_seed_data():
    household = ensure_household("admin@rezzerv.local")
    household_id = str(household.get("id") or "1")

    with engine.begin() as conn:
        inventory_count = conn.execute(
            text("SELECT COUNT(*) FROM inventory WHERE household_id = :household_id"),
            {"household_id": household_id},
        ).scalar() or 0

        if int(inventory_count) == 0:
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
            koelkast_id = ensure_sublocation(keuken_id, 'Koelkast')
            voorraadkast_id = ensure_sublocation(berging_id, 'Voorraadkast')
            boven_id = ensure_sublocation(berging_id, 'Boven')
            badkamerkast_id = ensure_sublocation(badkamer_id, 'Kast')

            demo_rows = [
                ('Melk', 1, keuken_id, kast1_id),
                ('Tuna', 1, berging_id, boven_id),
                ('Tomaten', 2, keuken_id, koelkast_id),
                ('Pasta', 3, berging_id, voorraadkast_id),
                ('Shampoo', 1, badkamer_id, badkamerkast_id),
            ]
            space_lookup = {keuken_id: 'Keuken', berging_id: 'Berging', badkamer_id: 'Badkamer'}
            sub_lookup = {kast1_id: 'Kast 1', koelkast_id: 'Koelkast', voorraadkast_id: 'Voorraadkast', boven_id: 'Boven', badkamerkast_id: 'Kast'}

            for naam, aantal, space_id, sublocation_id in demo_rows:
                conn.execute(
                    text("INSERT INTO inventory (id, naam, aantal, household_id, space_id, sublocation_id, status) VALUES (lower(hex(randomblob(16))), :naam, :aantal, :household_id, :space_id, :sublocation_id, :status)"),
                    {"naam": naam, "aantal": aantal, "household_id": household_id, "space_id": space_id, "sublocation_id": sublocation_id, "status": "active"},
                )
                create_inventory_event(
                    conn,
                    household_id=household_id,
                    article_id=build_live_article_option_id(naam),
                    article_name=naam,
                    resolved_location={
                        'space_id': space_id,
                        'sublocation_id': sublocation_id,
                        'location_id': sublocation_id or space_id,
                        'location_label': ' / '.join(part for part in [space_lookup.get(space_id, ''), sub_lookup.get(sublocation_id, '')] if part),
                    },
                    event_type='purchase',
                    quantity=int(aantal),
                    source='seed_ui_demo',
                    note='Initiële testvoorraad',
                    old_quantity=0,
                    new_quantity=int(aantal),
                )

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

            kitchen_kast1 = conn.execute(text("SELECT sl.id FROM sublocations sl JOIN spaces s ON s.id = sl.space_id WHERE s.household_id = :household_id AND lower(s.naam) = 'keuken' AND lower(sl.naam) = 'kast 1' LIMIT 1"), {'household_id': household_id}).scalar()
            kitchen_koelkast = conn.execute(text("SELECT sl.id FROM sublocations sl JOIN spaces s ON s.id = sl.space_id WHERE s.household_id = :household_id AND lower(s.naam) = 'keuken' AND lower(sl.naam) = 'koelkast' LIMIT 1"), {'household_id': household_id}).scalar()
            berging_boven = conn.execute(text("SELECT sl.id FROM sublocations sl JOIN spaces s ON s.id = sl.space_id WHERE s.household_id = :household_id AND lower(s.naam) = 'berging' AND lower(sl.naam) = 'boven' LIMIT 1"), {'household_id': household_id}).scalar()

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
def get_dev_status():
    return {
        "spaces": count_table("spaces"),
        "sublocations": count_table("sublocations"),
        "inventory": count_table("inventory"),
    }

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
                WHERE s.household_id = 'demo-household' OR s.household_id = :household_id
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
            {"household_id": householdId},
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
            {"household_id": householdId},
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

@app.post("/api/dev/spaces")
def create_space(payload: SpaceCreate):
    household_id = (payload.household_id or 'demo-household').strip() if payload.household_id else 'demo-household'
    with engine.begin() as conn:
        result = conn.execute(
            text("INSERT INTO spaces (id, naam, household_id) VALUES (lower(hex(randomblob(16))), :naam, :household_id) RETURNING id"),
            {"naam": payload.naam, "household_id": household_id},
        )
        row = result.first()
    return {"status": "ok", "id": row[0] if row else None, "household_id": household_id}

@app.post("/api/dev/sublocations")
def create_sublocation(payload: SublocationCreate):
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
def create_inventory(payload: InventoryCreate):
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
def update_inventory(inventory_id: str, payload: InventoryUpdate):
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
    article_name = (payload.article_name or "").strip()
    if not article_name:
        raise HTTPException(status_code=400, detail="article_name is verplicht")

    reason = (payload.reason or "").strip() or "Handmatig gearchiveerd vanuit Artikeldetail"
    effective_household_id = get_request_household_id(authorization)

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT i.id, i.naam, i.aantal, i.space_id, i.sublocation_id,
                       COALESCE(s.naam, '') AS space_name,
                       COALESCE(sl.naam, '') AS sublocation_name
                FROM inventory i
                LEFT JOIN spaces s ON s.id = i.space_id
                LEFT JOIN sublocations sl ON sl.id = i.sublocation_id
                WHERE i.household_id = :household_id
                  AND lower(trim(i.naam)) = lower(trim(:article_name))
                  AND COALESCE(i.status, 'active') = 'active'
                  AND COALESCE(i.aantal, 0) > 0
                ORDER BY i.updated_at DESC, i.created_at ASC, i.id ASC
                """
            ),
            {"household_id": effective_household_id, "article_name": article_name},
        ).mappings().all()

        if not rows:
            raise HTTPException(status_code=404, detail="Geen actief artikel gevonden om te archiveren")

        archived_ids = []
        total_archived_quantity = 0
        for row in rows:
            old_quantity = int(row.get("aantal") or 0)
            total_archived_quantity += old_quantity
            conn.execute(
                text(
                    """
                    UPDATE inventory
                    SET status = 'archived',
                        archived_at = CURRENT_TIMESTAMP,
                        archive_reason = :reason,
                        aantal = 0,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    """
                ),
                {"id": row["id"], "reason": reason},
            )
            resolved_location = {
                "location_id": row.get("sublocation_id") or row.get("space_id"),
                "space_id": row.get("space_id"),
                "sublocation_id": row.get("sublocation_id"),
                "location_label": " / ".join(part for part in [row.get("space_name") or "", row.get("sublocation_name") or ""] if part),
            }
            create_inventory_event(
                conn,
                household_id=effective_household_id,
                article_id=row["id"],
                article_name=row["naam"],
                resolved_location=resolved_location,
                event_type='archive',
                quantity=0,
                source='article_archive',
                note=reason,
                old_quantity=old_quantity,
                new_quantity=0,
            )
            archived_ids.append(str(row["id"]))

    return {
        "status": "ok",
        "article_name": article_name,
        "archived_inventory_ids": archived_ids,
        "archived_count": len(archived_ids),
        "archived_quantity": total_archived_quantity,
        "archive_reason": reason,
    }


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
              COALESCE(s.naam, '') AS locatie,
              COALESCE(sl.naam, '') AS sublocatie,
              COALESCE(i.status, 'active') AS status
            FROM inventory i
            LEFT JOIN spaces s ON s.id = i.space_id
            LEFT JOIN sublocations sl ON sl.id = i.sublocation_id
            WHERE i.household_id = :household_id
              AND COALESCE(i.status, 'active') = 'active'
              AND COALESCE(i.aantal, 0) > 0
            ORDER BY i.updated_at DESC, i.created_at ASC, i.id ASC
            """)
            ,{"household_id": effective_household_id}
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
def generate_demo_data():
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
def generate_layer1_receipt_fixture():
    reset_dev_tables()
    ensure_ui_test_seed_data()

    household = ensure_household("admin@rezzerv.local")
    household_id = str(household.get("id") or "1")

    with engine.begin() as conn:
        connection = conn.execute(
            text(
                """
                SELECT hsc.id AS connection_id
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
            raise HTTPException(status_code=500, detail="Layer1 receipt fixture connection kon niet worden voorbereid")

        connection_id = str(connection["connection_id"])
        batch = conn.execute(
            text(
                """
                SELECT pib.id AS batch_id
                FROM purchase_import_batches pib
                WHERE pib.connection_id = :connection_id
                  AND COALESCE(pib.import_status, 'new') != 'processed'
                ORDER BY pib.created_at DESC, pib.id DESC
                LIMIT 1
                """
            ),
            {"connection_id": connection_id},
        ).mappings().first()

        if not batch:
            raise HTTPException(status_code=500, detail="Layer1 receipt fixture batch kon niet worden voorbereid")

        batch_id = str(batch["batch_id"])
        line_rows = conn.execute(
            text(
                """
                SELECT id, article_name_raw, matched_household_article_id, target_location_id, processing_status
                FROM purchase_import_lines
                WHERE batch_id = :batch_id
                ORDER BY COALESCE(ui_sort_order, 999999), created_at ASC, id ASC
                """
            ),
            {"batch_id": batch_id},
        ).mappings().all()

        complete_line_id = None
        incomplete_line_id = None

        for row in line_rows:
            article_name = str(row.get("article_name_raw") or "").strip().lower()
            if not complete_line_id and article_name == 'magere yoghurt':
                complete_line_id = str(row['id'])
            if not incomplete_line_id and article_name == 'appelsap':
                incomplete_line_id = str(row['id'])

        if not complete_line_id:
            for row in line_rows:
                if row.get('matched_household_article_id') and row.get('target_location_id') and str(row.get('processing_status') or '').lower() == 'pending':
                    complete_line_id = str(row['id'])
                    break

        if not incomplete_line_id:
            for row in line_rows:
                has_valid_article = bool(row.get('matched_household_article_id'))
                has_valid_location = bool(row.get('target_location_id'))
                if (not has_valid_article or not has_valid_location) and str(row.get('processing_status') or '').lower() == 'pending':
                    incomplete_line_id = str(row['id'])
                    break

        if not complete_line_id or not incomplete_line_id:
            raise HTTPException(status_code=500, detail="Layer1 receipt fixture lines konden niet worden voorbereid")

        return {
            "householdId": household_id,
            "connectionId": connection_id,
            "batchId": batch_id,
            "latestBatchId": batch_id,
            "completeLineId": complete_line_id,
            "incompleteLineId": incomplete_line_id,
        }


@app.post("/api/dev/generate-receipt-export-fixture")
def generate_receipt_export_fixture():
    reset_dev_tables()
    ensure_ui_test_seed_data()

    household = ensure_household("admin@rezzerv.local")
    household_id = str(household.get("id") or "1")

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
def create_store_connection(payload: StoreConnectionCreate):
    provider = ensure_store_provider(payload.store_provider_code)

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
                "household_id": payload.household_id,
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
                "household_id": payload.household_id,
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
def get_store_connections(householdId: str = Query(...)):
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
            {"household_id": householdId},
        ).mappings().all()

    results = []
    for row in rows:
        item = dict(row)
        item["linked_at"] = normalize_datetime(item.get("linked_at"))
        item["last_sync_at"] = normalize_datetime(item.get("last_sync_at"))
        results.append(item)
    return results


@app.post("/api/store-connections/{connection_id}/pull-purchases")
def pull_purchases(connection_id: str, payload: PullPurchasesRequest):
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


@app.get("/api/store-location-options")
def get_store_location_options(householdId: str = Query(...)):
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
                LEFT JOIN sublocations sl ON sl.space_id = s.id
                WHERE s.household_id = 'demo-household' OR s.household_id = :household_id
                ORDER BY s.naam ASC, sl.naam ASC
                """
            ),
            {"household_id": householdId},
        ).mappings().all()
    return [
        {
            "id": row["sublocation_id"] or row["space_id"],
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

        article_id = payload.household_article_id
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


@app.post("/api/purchase-import-lines/{line_id}/create-article")
def create_article_from_purchase_import_line(line_id: str, payload: CreateArticleFromLineRequest):
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
        status = update_batch_status(conn, line["batch_id"])
        article = resolve_review_article_option(conn, article_option_id, str(line["household_id"]))

    return {
        "line_id": line_id,
        "batch_id": line["batch_id"],
        "batch_status": status,
        "article_option": article,
        "matched_household_article_id": article_option_id,
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
def get_purchase_import_batch_diagnostics(batch_id: str):
    with engine.begin() as conn:
        batch = conn.execute(text("SELECT id FROM purchase_import_batches WHERE id = :id"), {"id": batch_id}).mappings().first()
        if not batch:
            raise HTTPException(status_code=404, detail="Onbekende purchase import batch")
        return build_purchase_import_batch_diagnostics(conn, batch_id)




@app.post("/api/purchase-import-batches/{batch_id}/process")
def process_purchase_import_batch(batch_id: str, payload: ProcessBatchRequest):
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

            lines = conn.execute(
                text(
                    """
                    SELECT id, article_name_raw, brand_raw, quantity_raw, unit_raw, review_decision, matched_household_article_id,
                           target_location_id, processing_status, processed_event_id
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
                if payload.mode == "ready_only":
                    article_id = line.get("matched_household_article_id")
                    location_id = line.get("target_location_id")
                    if not article_id:
                        results.append({
                            "line_id": line_id,
                            "status": "skipped",
                            "reason": "Nog geen artikel gekoppeld",
                            "failure_stage": "article_resolution",
                        })
                        skipped_count += 1
                        continue
                    if not location_id:
                        results.append({
                            "line_id": line_id,
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
                if line["processing_status"] == "processed" and line["processed_event_id"]:
                    results.append({"line_id": line_id, "status": "processed", "event_id": line["processed_event_id"], "message": "Al eerder verwerkt"})
                    processed_count += 1
                    continue

                article_id = line["matched_household_article_id"]
                selected_article_input = str(article_id or '')
                original_article = resolve_review_article_option(conn, article_id, str(batch["household_id"]))
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
                    results.append({"line_id": line_id, "status": "failed", "error": error, "diagnostic": diagnostic})
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
                    results.append({"line_id": line_id, "status": "failed", "error": error, "diagnostic": diagnostic})
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
                    results.append({"line_id": line_id, "status": "failed", "error": error, "diagnostic": diagnostic})
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
                    event_id = create_inventory_purchase_event(conn, batch["household_id"], article_id, article_name, quantity, resolved_location, note)
                    purchase_inventory_id = apply_inventory_purchase(conn, batch["household_id"], article_name, quantity, resolved_location)
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
                    results.append({"line_id": line_id, "status": "failed", "error": error, "diagnostic": diagnostic})
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


@app.post("/api/dev/regression/reset")
def reset_regression_fixture_state():
    reset_dev_tables()
    ensure_ui_test_seed_data()
    version_path = Path(__file__).resolve().parents[2] / "VERSION.txt"
    version = version_path.read_text(encoding="utf-8").strip() if version_path.exists() else None
    return {
        "status": "ok",
        "dataset": "ui_seed",
        "household_id": str(ensure_household("admin@rezzerv.local").get("id") or "1"),
        "version": version,
    }


@app.post("/api/dev/run-smoke-tests", response_model=TestStartResponse)
def run_smoke_tests():
    return testing_service.start_external_test("smoke")


@app.post("/api/dev/run-regression-tests", response_model=TestStartResponse)
def run_regression_tests():
    return testing_service.start_external_test("regression")

@app.post("/api/dev/run-layer1-tests", response_model=TestStartResponse)
def run_layer1_tests():
    return testing_service.start_external_test("layer1")

@app.post("/api/dev/run-layer2-tests", response_model=TestStartResponse)
def run_layer2_tests():
    return testing_service.start_external_test("layer2")

@app.post("/api/dev/run-layer3-tests", response_model=TestStartResponse)
def run_layer3_tests():
    return testing_service.start_external_test("layer3")


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
def generate_large_dataset():
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
def generate_article_testdata():
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

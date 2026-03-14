from fastapi import FastAPI, HTTPException, Header, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
import json
import uuid
from typing import List, Optional
from app.schemas.testing import TestStartResponse, TestStatusResponse, TestReportResponse, TestCompleteRequest
from app.services.testing_service import testing_service
from datetime import datetime
import logging
from sqlalchemy import text

app = FastAPI()
logger = logging.getLogger('rezzerv.api')


@app.exception_handler(Exception)
async def unhandled_api_exception_handler(request: Request, exc: Exception):
    if request.url.path.startswith('/api/'):
        logger.exception('Onverwerkte API-fout op %s', request.url.path)
        return JSONResponse(status_code=500, content={'detail': 'Interne serverfout in de API'})
    raise exc

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
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
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
    {"id": "1", "name": "Tomaten", "brand": "Mutti"},
    {"id": "2", "name": "Spaghetti", "brand": "Barilla"},
    {"id": "3", "name": "Koffie", "brand": "Douwe Egberts"},
    {"id": "4", "name": "Melk", "brand": "Campina"},
    {"id": "5", "name": "Banaan", "brand": "Huismerk"},
    {"id": "6", "name": "Volkoren pasta", "brand": "Barilla"},
]


MOCK_ARTICLE_LOOKUP = {item["id"]: item for item in MOCK_ARTICLE_OPTIONS}


STORE_IMPORT_SIMPLIFICATION_KEY = "store_import_simplification_level"
STORE_IMPORT_SIMPLIFICATION_ALLOWED = {"voorzichtig", "gebalanceerd", "maximaal_gemak"}
STORE_IMPORT_SIMPLIFICATION_DEFAULT = "gebalanceerd"
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
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT
            )
            """
        ))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_household_articles_household_name ON household_articles (household_id, naam)"))


def normalize_household_article_name(value: str | None) -> str:
    return " ".join(str(value or "").strip().split())


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


def ensure_household_article(conn, household_id: str, article_name: str) -> str:
    normalized = normalize_household_article_name(article_name)
    if not normalized:
        raise HTTPException(status_code=400, detail="Artikelnaam is verplicht")

    existing_name = find_existing_household_article_name(conn, household_id, normalized)
    final_name = existing_name or normalized
    if not existing_name:
        conn.execute(
            text(
                """
                INSERT INTO household_articles (id, household_id, naam, updated_at)
                VALUES (:id, :household_id, :naam, CURRENT_TIMESTAMP)
                """
            ),
            {"id": str(uuid.uuid4()), "household_id": str(household_id), "naam": normalized},
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
            SELECT DISTINCT article_name
            FROM (
                SELECT naam AS article_name FROM inventory WHERE trim(COALESCE(naam, '')) <> ''
                UNION
                SELECT naam AS article_name FROM household_articles WHERE trim(COALESCE(naam, '')) <> ''
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
        items.append({"id": build_live_article_option_id(article_name), "name": article_name, "brand": ""})
        seen_names.add(normalized)

    return items


def resolve_review_article_option(conn, article_id: str | None):
    if not article_id:
        return None
    article_id = str(article_id)
    if article_id in MOCK_ARTICLE_LOOKUP:
        return dict(MOCK_ARTICLE_LOOKUP[article_id])
    if article_id.startswith("live::"):
        article_name = article_id.split("::", 1)[1].strip()
        if article_name:
            return {"id": article_id, "name": article_name, "brand": ""}
        return None

    inventory_match = conn.execute(
        text(
            """
            SELECT article_name AS naam
            FROM (
                SELECT naam AS article_name FROM inventory
                UNION
                SELECT naam AS article_name FROM household_articles
            ) src
            WHERE lower(article_name) = lower(:article_name)
            LIMIT 1
            """
        ),
        {"article_name": article_id},
    ).mappings().first()
    if inventory_match and inventory_match.get("naam"):
        article_name = inventory_match["naam"].strip()
        return {"id": build_live_article_option_id(article_name), "name": article_name, "brand": ""}

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
                    is_auto_prefilled = :is_auto_prefilled,
                    matched_household_article_id = CASE WHEN :can_auto_fill = 1 THEN :matched_household_article_id ELSE NULL END,
                    target_location_id = CASE WHEN :can_auto_fill = 1 THEN :target_location_id ELSE NULL END,
                    match_status = CASE WHEN :can_auto_fill = 1 AND :matched_household_article_id IS NOT NULL THEN 'matched' ELSE 'unmatched' END,
                    review_decision = CASE WHEN :can_auto_fill = 1 THEN 'selected' ELSE 'pending' END,
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
              COALESCE(sl.naam, '') AS sublocatie
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


def apply_inventory_consumption(conn, household_id: str, article_name: str, quantity: float, resolved_location: dict):
    safe_location = require_resolved_location(resolved_location)
    space_id = safe_location["space_id"]
    sublocation_id = safe_location["sublocation_id"]
    quantity_int = int(quantity)
    if quantity_int <= 0:
        return None

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
        return None

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
    return existing["id"]


def create_auto_repurchase_event(conn, household_id: str, article_id: str, article_name: str, resolved_location: dict, quantity: float = 1):
    quantity_int = int(quantity)
    if quantity_int <= 0:
        return None
    old_total = get_article_total_quantity(conn, household_id, article_name)
    if old_total <= 0:
        return None
    new_total = max(0, old_total - quantity_int)
    return create_inventory_event(
        conn,
        household_id=household_id,
        article_id=article_id,
        article_name=article_name,
        resolved_location=resolved_location,
        event_type='auto_repurchase',
        quantity=-quantity_int,
        old_quantity=old_total,
        new_quantity=new_total,
        source='auto_repurchase',
        note='Automatisch 1 eenheid afgeboekt bij herhaalaankoop.',
    )


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


@app.post("/api/auth/login")
def login(payload: LoginRequest):
    user = users.get(payload.email)

    if user and user["password"] == payload.password:
        ensure_household(payload.email)

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


# SQLite datamodel initialization
from app.db import engine, Base
from app.models import household, space, sublocation, inventory, store_provider, store_connection, purchase_import

Base.metadata.create_all(bind=engine)
ensure_household_settings_schema()
ensure_household_articles_schema()
ensure_release_2_schema()
ensure_release_3_schema()
ensure_release_4_schema()
seed_store_providers()

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

@app.get("/api/dev/inventory-preview")
def inventory_preview(response: Response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    with engine.begin() as conn:
        rows = conn.execute(
            text("""
            SELECT
              i.id,
              i.naam AS artikel,
              i.aantal AS aantal,
              COALESCE(s.naam, '') AS locatie,
              COALESCE(sl.naam, '') AS sublocatie
            FROM inventory i
            LEFT JOIN spaces s ON s.id = i.space_id
            LEFT JOIN sublocations sl ON sl.id = i.sublocation_id
            WHERE COALESCE(i.aantal, 0) > 0
            ORDER BY i.updated_at DESC, i.created_at ASC, i.id ASC
            """)
        ).mappings().all()
    return {"rows": [dict(r) for r in rows]}



@app.get("/api/dev/article-history")
def article_history(article_name: str):
    article_name = (article_name or "").strip()
    if not article_name:
        raise HTTPException(status_code=400, detail="article_name is verplicht")

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
                WHERE lower(article_name) = lower(:article_name)
                ORDER BY datetime(created_at) DESC, id DESC
                """
            ),
            {"article_name": article_name},
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

        if batch["import_status"] != "processed":
            apply_prefill_to_batch(conn, batch_id, str(batch["household_id"]), batch["store_provider_code"])
            refresh_batch_status = update_batch_status(conn, batch_id)
            batch = dict(batch)
            batch["import_status"] = refresh_batch_status
        else:
            batch = dict(batch)

        batch["store_import_simplification_level"] = get_household_store_import_simplification_level(conn, str(batch["household_id"]))

        lines = conn.execute(
            text(
                """
                SELECT
                    id, article_name_raw, brand_raw, quantity_raw, unit_raw,
                    line_price_raw, currency_code, match_status, review_decision,
                    matched_household_article_id, target_location_id,
                    suggested_household_article_id, suggested_location_id, suggestion_confidence, suggestion_reason, is_auto_prefilled,
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
        elif memory_found:
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
                SELECT id, batch_id, review_decision, matched_household_article_id, target_location_id, match_status
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
        conn.execute(
            text(
                """
                UPDATE purchase_import_lines
                SET matched_household_article_id = :article_id, match_status = :match_status, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {"article_id": article_id, "match_status": match_status, "id": line_id},
        )
        status = update_batch_status(conn, line["batch_id"])
        updated = conn.execute(
            text(
                """
                SELECT id, batch_id, review_decision, matched_household_article_id, target_location_id, match_status
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

        article_option_id = ensure_household_article(conn, str(line["household_id"]), payload.article_name)
        conn.execute(
            text(
                """
                UPDATE purchase_import_lines
                SET matched_household_article_id = :article_id, match_status = 'matched', updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {"article_id": article_option_id, "id": line_id},
        )
        status = update_batch_status(conn, line["batch_id"])
        article = resolve_review_article_option(conn, article_option_id)

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

        conn.execute(
            text(
                """
                UPDATE purchase_import_lines
                SET target_location_id = :target_location_id, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {"target_location_id": payload.target_location_id, "id": line_id},
        )
        status = update_batch_status(conn, line["batch_id"])
        updated = conn.execute(
            text(
                """
                SELECT id, batch_id, review_decision, matched_household_article_id, target_location_id, match_status
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


@app.post("/api/purchase-import-batches/{batch_id}/process")
def process_purchase_import_batch(batch_id: str, payload: ProcessBatchRequest):
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
        if payload.mode == "ready_only":
            selected_lines = [
                line for line in selected_lines
                if line["matched_household_article_id"] and line["target_location_id"]
            ]
        if not selected_lines:
            if payload.mode == "ready_only":
                raise HTTPException(status_code=400, detail="Er zijn geen volledig gekoppelde regels om te verwerken")
            raise HTTPException(status_code=400, detail="Er zijn geen geselecteerde regels om te verwerken")

        results = []
        processed_count = 0
        failed_count = 0

        for line in selected_lines:
            line_id = line["id"]
            if line["processing_status"] == "processed" and line["processed_event_id"]:
                results.append({"line_id": line_id, "status": "processed", "event_id": line["processed_event_id"], "message": "Al eerder verwerkt"})
                processed_count += 1
                continue

            article_id = line["matched_household_article_id"]
            article = resolve_review_article_option(conn, article_id)
            if not article:
                error = "Geen geldige artikelkoppeling gekozen"
                conn.execute(text("UPDATE purchase_import_lines SET processing_status = 'failed', processing_error = :error, updated_at = CURRENT_TIMESTAMP WHERE id = :id"), {"error": error, "id": line_id})
                results.append({"line_id": line_id, "status": "failed", "error": error})
                failed_count += 1
                continue

            resolved_location = resolve_target_location(conn, line["target_location_id"])
            if not resolved_location:
                error = "Geen geldige locatie gekozen"
                conn.execute(text("UPDATE purchase_import_lines SET processing_status = 'failed', processing_error = :error, updated_at = CURRENT_TIMESTAMP WHERE id = :id"), {"error": error, "id": line_id})
                results.append({"line_id": line_id, "status": "failed", "error": error})
                failed_count += 1
                continue

            quantity = normalize_store_import_quantity(line.get("quantity_raw"), line.get("unit_raw"))
            if quantity <= 0:
                error = "Ongeldige hoeveelheid"
                conn.execute(text("UPDATE purchase_import_lines SET processing_status = 'failed', processing_error = :error, updated_at = CURRENT_TIMESTAMP WHERE id = :id"), {"error": error, "id": line_id})
                results.append({"line_id": line_id, "status": "failed", "error": error})
                failed_count += 1
                continue

            article_name = article["name"]
            note = build_store_import_note(batch["store_provider_code"], batch_id, line_id, line["article_name_raw"])
            auto_consume_ids = {str(item) for item in (payload.auto_consume_article_ids or [])}
            pre_purchase_total = get_article_total_quantity(conn, batch["household_id"], article_name)
            should_auto_consume = str(article_id) in auto_consume_ids and pre_purchase_total > 0
            event_id = create_inventory_purchase_event(conn, batch["household_id"], article_id, article_name, quantity, resolved_location, note)
            apply_inventory_purchase(conn, batch["household_id"], article_name, quantity, resolved_location)
            auto_event_id = None
            if should_auto_consume:
                auto_event_id = create_auto_repurchase_event(conn, batch["household_id"], article_id, article_name, resolved_location, quantity=1)
                apply_inventory_consumption(conn, batch["household_id"], article_name, 1, resolved_location)
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
            results.append({"line_id": line_id, "status": "processed", "event_id": event_id, "auto_event_id": auto_event_id})
            processed_count += 1

        batch_status = update_batch_status(conn, batch_id)
        if batch_status in {"processed", "partially_processed"}:
            conn.execute(text("UPDATE purchase_import_batches SET processed_at = CURRENT_TIMESTAMP WHERE id = :id"), {"id": batch_id})

    return {
        "batch_id": batch_id,
        "status": batch_status,
        "processed_count": processed_count,
        "failed_count": failed_count,
        "results": results,
    }


@app.post("/api/dev/run-smoke-tests", response_model=TestStartResponse)
def run_smoke_tests():
    return testing_service.start_external_test("smoke")


@app.post("/api/dev/run-regression-tests", response_model=TestStartResponse)
def run_regression_tests():
    return testing_service.start_external_test("regression")


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

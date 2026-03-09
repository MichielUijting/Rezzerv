from fastapi import FastAPI, HTTPException, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
import json
import uuid
from typing import Optional
from app.schemas.testing import TestStartResponse, TestStatusResponse, TestReportResponse, TestCompleteRequest
from app.services.testing_service import testing_service
from datetime import datetime
from sqlalchemy import text

app = FastAPI()


@app.exception_handler(Exception)
async def unhandled_api_exception_handler(request: Request, exc: Exception):
    if request.url.path.startswith('/api/'):
        return JSONResponse(status_code=500, content={'detail': 'Interne serverfout in de winkelkoppeling'})
    raise exc

# In-memory opslag (MVP login)
households = {}
users = {
    "admin@rezzerv.local": {
        "password": "Rezzerv123"
    }
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

class SublocationCreate(BaseModel):
    naam: str
    space_id: str

class InventoryCreate(BaseModel):
    naam: str
    aantal: int
    space_id: str
    sublocation_id: Optional[str] = None


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
    household_article_id: str | int

    @field_validator("household_article_id", mode="before")
    @classmethod
    def normalize_article_id(cls, value):
        if value is None or str(value).strip() == "":
            raise ValueError("household_article_id is verplicht")
        return str(value)


class TargetLocationRequest(BaseModel):
    target_location_id: Optional[str] = None



class ProcessBatchRequest(BaseModel):
    processed_by: str = "ui"
    mode: str = "selected_only"

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value):
        if value != "selected_only":
            raise ValueError("Alleen selected_only wordt ondersteund")
        return value



MOCK_LIDL_PURCHASES = {
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


def build_live_article_option_id(article_name: str) -> str:
    return f"live::{(article_name or '').strip()}"


def get_store_review_article_options(conn):
    items = [dict(item) for item in MOCK_ARTICLE_OPTIONS]
    seen_names = {item["name"].strip().lower() for item in items if item.get("name")}

    live_names = conn.execute(
        text(
            """
            SELECT DISTINCT naam AS article_name
            FROM inventory
            WHERE trim(COALESCE(naam, '')) <> ''
            ORDER BY lower(naam) ASC
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
            SELECT naam
            FROM inventory
            WHERE lower(naam) = lower(:article_name)
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
        existing = conn.execute(
            text("SELECT id FROM store_providers WHERE code = :code"),
            {"code": "lidl"},
        ).first()
        if not existing:
            conn.execute(
                text(
                    """
                    INSERT INTO store_providers (id, code, name, status, import_mode)
                    VALUES (:id, :code, :name, :status, :import_mode)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "code": "lidl",
                    "name": "Lidl",
                    "status": "active",
                    "import_mode": "mock",
                },
            )




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
                    source TEXT NOT NULL,
                    note TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )



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
    lines = conn.execute(
        text(
            """
            SELECT id, article_name_raw, brand_raw
            FROM purchase_import_lines
            WHERE batch_id = :batch_id
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
        is_safe_match = bool(matched_article_id)
        should_auto_select = is_safe_match and bool(preferred_location_id) and times_confirmed >= 1
        suggestion_reason = "Automatisch voorgesteld" if should_auto_select else "Controleer voorstel"

        conn.execute(
            text(
                """
                UPDATE purchase_import_lines
                SET suggested_household_article_id = :suggested_article_id,
                    suggested_location_id = :suggested_location_id,
                    suggestion_confidence = :suggestion_confidence,
                    suggestion_reason = :suggestion_reason,
                    is_auto_prefilled = :is_auto_prefilled,
                    matched_household_article_id = COALESCE(:matched_household_article_id, matched_household_article_id),
                    target_location_id = COALESCE(:target_location_id, target_location_id),
                    match_status = CASE WHEN :matched_household_article_id IS NOT NULL THEN 'matched' ELSE match_status END,
                    review_decision = CASE WHEN :should_auto_select = 1 THEN 'selected' ELSE review_decision END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {
                "id": line["id"],
                "suggested_article_id": matched_article_id,
                "suggested_location_id": preferred_location_id,
                "suggestion_confidence": "high" if should_auto_select else "medium",
                "suggestion_reason": suggestion_reason,
                "is_auto_prefilled": 1 if should_auto_select or matched_article_id or preferred_location_id else 0,
                "matched_household_article_id": matched_article_id,
                "target_location_id": preferred_location_id,
                "should_auto_select": 1 if should_auto_select else 0,
            },
        )
        if matched_article_id:
            article_prefills += 1
        if preferred_location_id:
            location_prefills += 1
        if should_auto_select:
            fully_prefilled += 1

    return {
        "article_prefills": article_prefills,
        "location_prefills": location_prefills,
        "fully_prefilled": fully_prefilled,
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


def apply_inventory_purchase(conn, household_id: str, article_name: str, quantity: float, resolved_location: dict):
    space_id = resolved_location["space_id"]
    sublocation_id = resolved_location["sublocation_id"]

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


def create_inventory_purchase_event(conn, household_id: str, article_id: str, article_name: str, quantity: float, resolved_location: dict, note: str):
    event_id = str(uuid.uuid4())
    conn.execute(
        text(
            """
            INSERT INTO inventory_events (
                id, household_id, article_id, article_name, location_id, location_label,
                event_type, quantity, source, note, created_at
            ) VALUES (
                :id, :household_id, :article_id, :article_name, :location_id, :location_label,
                'purchase', :quantity, 'store_import', :note, CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "id": event_id,
            "household_id": household_id,
            "article_id": article_id,
            "article_name": article_name,
            "location_id": resolved_location["location_id"],
            "location_label": resolved_location["location_label"],
            "quantity": quantity,
            "note": note,
        },
    )
    return event_id


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
    if email not in households:
        households[email] = {
            "id": len(households) + 1,
            "naam": "Mijn huishouden",
            "created_at": datetime.utcnow().isoformat()
        }
    return households[email]


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/login")
def login(payload: LoginRequest):
    user = users.get(payload.email)

    if user and user["password"] == payload.password:
        ensure_household(payload.email)

        return {
            "token": "rezzerv-dev-token",
            "user": {"email": payload.email}
        }

    raise HTTPException(status_code=401, detail="Ongeldige inloggegevens")


@app.get("/api/household")
def get_household(authorization: Optional[str] = Header(None)):
    if authorization != "Bearer rezzerv-dev-token":
        raise HTTPException(status_code=401, detail="Unauthorized")

    email = "admin@rezzerv.local"

    household = ensure_household(email)
    return household


# SQLite datamodel initialization
from app.db import engine, Base
from app.models import household, space, sublocation, inventory, store_provider, store_connection, purchase_import

Base.metadata.create_all(bind=engine)
ensure_release_2_schema()
ensure_release_3_schema()
ensure_release_4_schema()
seed_store_providers()

def reset_dev_tables():
    with engine.begin() as conn:
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

@app.post("/api/dev/spaces")
def create_space(payload: SpaceCreate):
    with engine.begin() as conn:
        result = conn.execute(
            text("INSERT INTO spaces (id, naam, household_id) VALUES (lower(hex(randomblob(16))), :naam, 'demo-household') RETURNING id"),
            {"naam": payload.naam},
        )
        row = result.first()
    return {"status": "ok", "id": row[0] if row else None}

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
        if payload.sublocation_id:
            sub = conn.execute(
                text("SELECT id, space_id FROM sublocations WHERE id = :id"),
                {"id": payload.sublocation_id},
            ).first()
            if not sub:
                raise HTTPException(status_code=400, detail="Onbekende sublocation_id")
            space_id = sub[1]
        else:
            space = conn.execute(
                text("SELECT id FROM spaces WHERE id = :id"),
                {"id": payload.space_id},
            ).first()
            if not space:
                raise HTTPException(status_code=400, detail="Onbekende space_id")
            space_id = payload.space_id

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
                "sublocation_id": payload.sublocation_id,
            },
        )
        row = result.first()
    return {"status": "ok", "id": row[0] if row else None}

@app.get("/api/dev/inventory-preview")
def inventory_preview():
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
            ORDER BY i.naam ASC
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
            "source": row["source"],
            "note": row["note"],
            "created_at": normalize_datetime(row["created_at"]),
        }
        for row in rows
    ]}


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
            ("Tomaten", 6, kitchen_id, koelkast_id),
            ("Koffie", 1, kitchen_id, kast1_id),
            ("Shampoo", 4, bathroom_id, badkamerkast_id),
            ("Erwten", 5, pantry_id, voorraadkast_id),
            ("IJs", 2, pantry_id, diepvries_id),
            ("Melk", 2, kitchen_id, koelkast_id),
            ("Thee", 8, kitchen_id, kast1_id),
        ]

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
    lines = MOCK_LIDL_PURCHASES.get(payload.mock_profile)
    if not lines:
        raise HTTPException(status_code=400, detail="Onbekend mock_profile")

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

        raw_payload = json.dumps({"mock_profile": payload.mock_profile, "lines": lines})
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
                        'unmatched', 'pending', :ui_sort_order, CURRENT_TIMESTAMP
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
        "store_provider_code": "lidl",
        "source_type": "mock",
        "import_status": "new",
        "line_count": len(lines),
        "created_at": now_iso,
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
                    pib.connection_id,
                    pib.source_type,
                    pib.source_reference,
                    pib.import_status,
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
    batch_result["created_at"] = normalize_datetime(batch_result.get("created_at"))
    batch_result["lines"] = [
        {
            **dict(line),
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
        raise HTTPException(status_code=404, detail="Nog geen importbatch voor deze winkelkoppeling")
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

        conn.execute(
            text(
                """
                UPDATE purchase_import_lines
                SET matched_household_article_id = :article_id, match_status = 'matched', updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {"article_id": payload.household_article_id, "id": line_id},
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
                WHERE id = :id
                """
            ),
            {"id": batch_id},
        ).mappings().first()
        if not batch:
            raise HTTPException(status_code=404, detail="Onbekende purchase import batch")

        lines = conn.execute(
            text(
                """
                SELECT id, article_name_raw, brand_raw, quantity_raw, review_decision, matched_household_article_id,
                       target_location_id, processing_status, processed_event_id
                FROM purchase_import_lines
                WHERE batch_id = :batch_id
                ORDER BY COALESCE(ui_sort_order, 999999), created_at ASC, id ASC
                """
            ),
            {"batch_id": batch_id},
        ).mappings().all()

        selected_lines = [line for line in lines if (line["review_decision"] or "pending") == "selected"]
        if not selected_lines:
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

            quantity = float(line["quantity_raw"] or 0)
            if quantity <= 0:
                error = "Ongeldige hoeveelheid"
                conn.execute(text("UPDATE purchase_import_lines SET processing_status = 'failed', processing_error = :error, updated_at = CURRENT_TIMESTAMP WHERE id = :id"), {"error": error, "id": line_id})
                results.append({"line_id": line_id, "status": "failed", "error": error})
                failed_count += 1
                continue

            article_name = article["name"]
            note = f"store_import;lidl;batch={batch_id};line={line_id};raw={line['article_name_raw']}"
            event_id = create_inventory_purchase_event(conn, batch["household_id"], article_id, article_name, quantity, resolved_location, note)
            apply_inventory_purchase(conn, batch["household_id"], article_name, quantity, resolved_location)
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
            results.append({"line_id": line_id, "status": "processed", "event_id": event_id})
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

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

app = FastAPI()

# In-memory opslag (MVP)
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
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LoginRequest(BaseModel):
    email: str
    password: str


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
from app.models import household, space, sublocation, inventory

Base.metadata.create_all(bind=engine)
from app.models import location, sublocation, inventory_item


from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db import SessionLocal

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/api/locations")
def get_locations(db: Session = Depends(get_db)):
    items = db.query(location.Location).all()
    return [{"id": i.id, "name": i.name} for i in items]

@router.get("/api/inventory")
def get_inventory(db: Session = Depends(get_db)):
    items = db.query(inventory_item.InventoryItem).all()
    return [
        {
            "id": i.id,
            "name": i.name,
            "quantity": i.quantity,
            "location_id": i.location_id,
            "sublocation_id": i.sublocation_id
        }
        for i in items
    ]

app.include_router(router)

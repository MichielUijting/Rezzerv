from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

app = FastAPI()

from sqlalchemy import text
import time
from app.db.session import engine
from app.db.base import Base

# Database retry
for attempt in range(10):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        break
    except Exception:
        time.sleep(1)
else:
    raise Exception("Database not reachable after retries")

# Create tables
Base.metadata.create_all(bind=engine)


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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# Allow frontend (served via nginx on localhost:5173)
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

@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.post("/api/auth/login")
def login(payload: LoginRequest):
    # M1-minimal: hardcoded credentials
    if payload.email == "admin@rezzerv.local" and payload.password == "Rezzerv123":
        return {"token": "rezzerv-dev-token", "user": {"email": payload.email}}
    raise HTTPException(status_code=401, detail="Ongeldige inloggegevens")

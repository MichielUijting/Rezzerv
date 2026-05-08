from fastapi import APIRouter

router = APIRouter(
    prefix="/api/admin",
    tags=["receipt-admin"],
)

from fastapi import APIRouter

router = APIRouter(
    prefix="/api/receipts",
    tags=["receipts"],
)

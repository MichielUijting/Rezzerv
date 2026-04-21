from fastapi import APIRouter

from app.api.routes.debug import router as debug_router

api_router = APIRouter()
api_router.include_router(debug_router)

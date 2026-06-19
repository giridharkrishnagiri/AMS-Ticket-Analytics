from fastapi import APIRouter

from app.api.dashboard import router as dashboard_router
from app.api.health import router as health_router
from app.api.mappings import router as mappings_router
from app.api.sla import router as sla_router
from app.api.uploads import router as uploads_router

api_router = APIRouter()
api_router.include_router(dashboard_router)
api_router.include_router(health_router)
api_router.include_router(mappings_router)
api_router.include_router(sla_router)
api_router.include_router(uploads_router)

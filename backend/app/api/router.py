from fastapi import APIRouter

from app.api.admin import router as admin_router
from app.api.application_dimensions import router as application_dimensions_router
from app.api.application_inventory import router as application_inventory_router
from app.api.dashboard import router as dashboard_router
from app.api.health import router as health_router
from app.api.mappings import router as mappings_router
from app.api.projects import router as projects_router
from app.api.sla import router as sla_router
from app.api.uploads import router as uploads_router

api_router = APIRouter()
api_router.include_router(admin_router)
api_router.include_router(application_dimensions_router)
api_router.include_router(application_inventory_router)
api_router.include_router(dashboard_router)
api_router.include_router(health_router)
api_router.include_router(mappings_router)
api_router.include_router(projects_router)
api_router.include_router(sla_router)
api_router.include_router(uploads_router)

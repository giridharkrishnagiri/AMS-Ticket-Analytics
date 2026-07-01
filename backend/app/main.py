from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app.api.router import api_routers
from app.core.config import get_settings
from app.services.storage import storage_service


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    storage_service.ensure_storage_dirs()
    yield


settings = get_settings()


def include_api_routes(app: FastAPI, *, prefix: str) -> None:
    for api_router in api_routers:
        for route in api_router.routes:
            if isinstance(route, APIRoute):
                app.add_api_route(
                    f"{prefix}{route.path}",
                    route.endpoint,
                    response_model=route.response_model,
                    status_code=route.status_code,
                    tags=route.tags,
                    dependencies=route.dependencies,
                    summary=route.summary,
                    description=route.description,
                    response_description=route.response_description,
                    responses=route.responses,
                    deprecated=route.deprecated,
                    methods=route.methods,
                    operation_id=route.operation_id,
                    response_model_include=route.response_model_include,
                    response_model_exclude=route.response_model_exclude,
                    response_model_by_alias=route.response_model_by_alias,
                    response_model_exclude_unset=route.response_model_exclude_unset,
                    response_model_exclude_defaults=route.response_model_exclude_defaults,
                    response_model_exclude_none=route.response_model_exclude_none,
                    include_in_schema=route.include_in_schema,
                    response_class=route.response_class,
                    name=route.name,
                    openapi_extra=route.openapi_extra,
                    generate_unique_id_function=route.generate_unique_id_function,
                )


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

include_api_routes(app, prefix="/api")

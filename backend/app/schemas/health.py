from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthCheckItem(BaseModel):
    name: str
    status: str
    message: str
    duration_ms: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    checked_at: datetime
    storage_root: str
    checks: list[HealthCheckItem] = Field(default_factory=list)
    database: dict[str, Any] = Field(default_factory=dict)
    frontends: dict[str, Any] = Field(default_factory=dict)

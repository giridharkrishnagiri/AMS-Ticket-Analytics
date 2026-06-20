from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class ProjectOptionResponse(BaseModel):
    id: UUID
    name: str
    code: str
    client_id: UUID
    customer_name: str
    customer_code: str
    label: str

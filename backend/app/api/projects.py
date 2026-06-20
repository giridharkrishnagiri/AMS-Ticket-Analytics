from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Client, Project
from app.schemas.project import ProjectOptionResponse

router = APIRouter(prefix="/projects", tags=["projects"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[ProjectOptionResponse])
def list_projects(
    db: DbSession,
    active_only: Annotated[bool, Query()] = True,
) -> list[ProjectOptionResponse]:
    statement = select(Project, Client).join(Client, Project.client_id == Client.id)
    if active_only:
        statement = statement.where(Project.is_active.is_(True), Client.is_active.is_(True))
    statement = statement.order_by(Client.name.asc(), Project.name.asc())

    return [
        ProjectOptionResponse(
            id=project.id,
            name=project.name,
            code=project.code,
            client_id=client.id,
            customer_name=client.name,
            customer_code=client.code,
            label=f"{client.name} - {project.name}",
        )
        for project, client in db.execute(statement).all()
    ]

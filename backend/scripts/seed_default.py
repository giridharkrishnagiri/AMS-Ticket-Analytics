from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Client, Project

DEFAULT_CLIENT_CODE = "DEFAULT"
DEFAULT_CLIENT_NAME = "Mondelez"
DEFAULT_PROJECT_CODE = "AMS-TICKET-INTELLIGENCE"
DEFAULT_PROJECT_NAME = "AMS Apps & Volumetrics Analytics"
DEFAULT_INCIDENT_SOURCE_PATH = r"C:\Users\giridharkr\Downloads\Incidents"
DEFAULT_SERVICE_CATALOG_SOURCE_PATH = r"C:\Users\giridharkr\Downloads\SC Tasks"


def seed_default_client_and_project() -> None:
    with SessionLocal() as db:
        client = db.scalar(select(Client).where(Client.code == DEFAULT_CLIENT_CODE))
        if client is None:
            client = Client(
                name=DEFAULT_CLIENT_NAME,
                code=DEFAULT_CLIENT_CODE,
                description="Default customer for local AMS Ticket Intelligence setup.",
            )
            db.add(client)
            db.flush()
        else:
            client.name = DEFAULT_CLIENT_NAME

        project = db.scalar(
            select(Project).where(
                Project.client_id == client.id,
                Project.code == DEFAULT_PROJECT_CODE,
            )
        )
        if project is None:
            project = Project(
                client_id=client.id,
                name=DEFAULT_PROJECT_NAME,
                code=DEFAULT_PROJECT_CODE,
                description=(
                    "Default project for monthly incident and service catalog task uploads."
                ),
                default_incident_source_path=DEFAULT_INCIDENT_SOURCE_PATH,
                default_service_catalog_source_path=DEFAULT_SERVICE_CATALOG_SOURCE_PATH,
            )
            db.add(project)
        else:
            project.name = DEFAULT_PROJECT_NAME
            project.default_incident_source_path = DEFAULT_INCIDENT_SOURCE_PATH
            project.default_service_catalog_source_path = DEFAULT_SERVICE_CATALOG_SOURCE_PATH

        db.commit()
        print(f"Seeded client '{client.code}' and project '{DEFAULT_PROJECT_CODE}'.")


if __name__ == "__main__":
    seed_default_client_and_project()

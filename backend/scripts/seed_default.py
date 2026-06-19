from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Client, Project

DEFAULT_CLIENT_CODE = "DEFAULT"
DEFAULT_PROJECT_CODE = "AMS-TICKET-INTELLIGENCE"
DEFAULT_INCIDENT_SOURCE_PATH = r"C:\Users\giridharkr\Downloads\Incidents"
DEFAULT_SERVICE_CATALOG_SOURCE_PATH = r"C:\Users\giridharkr\Downloads\SC Tasks"


def seed_default_client_and_project() -> None:
    with SessionLocal() as db:
        client = db.scalar(select(Client).where(Client.code == DEFAULT_CLIENT_CODE))
        if client is None:
            client = Client(
                name="Default AMS Client",
                code=DEFAULT_CLIENT_CODE,
                description="Default client for local AMS Ticket Intelligence setup.",
            )
            db.add(client)
            db.flush()

        project = db.scalar(
            select(Project).where(
                Project.client_id == client.id,
                Project.code == DEFAULT_PROJECT_CODE,
            )
        )
        if project is None:
            project = Project(
                client_id=client.id,
                name="AMS Ticket Intelligence",
                code=DEFAULT_PROJECT_CODE,
                description=(
                    "Default project for monthly incident and service catalog task uploads."
                ),
                default_incident_source_path=DEFAULT_INCIDENT_SOURCE_PATH,
                default_service_catalog_source_path=DEFAULT_SERVICE_CATALOG_SOURCE_PATH,
            )
            db.add(project)
        else:
            project.default_incident_source_path = DEFAULT_INCIDENT_SOURCE_PATH
            project.default_service_catalog_source_path = DEFAULT_SERVICE_CATALOG_SOURCE_PATH

        db.commit()
        print(f"Seeded client '{client.code}' and project '{DEFAULT_PROJECT_CODE}'.")


if __name__ == "__main__":
    seed_default_client_and_project()

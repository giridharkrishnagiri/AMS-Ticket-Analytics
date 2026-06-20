from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, event, select

from app.db.session import SessionLocal
from app.main import app
from app.models import ApplicationDimension, Client, Project, Ticket, UploadBatch, UploadedFile


def create_project():
    db = SessionLocal()
    suffix = uuid4().hex[:12]
    client = Client(name=f"Dimension Client {suffix}", code=f"DIM-C-{suffix}")
    db.add(client)
    db.flush()

    project = Project(
        client_id=client.id,
        name=f"Dimension Project {suffix}",
        code=f"DIM-P-{suffix}",
    )
    db.add(project)
    db.flush()

    upload_batch = UploadBatch(
        project_id=project.id,
        month_key="2026-06",
        batch_name=f"Dimension Batch {suffix}",
        status="NORMALIZED",
        file_count=1,
        total_size_bytes=1,
    )
    db.add(upload_batch)
    db.flush()

    uploaded_file = UploadedFile(
        upload_batch_id=upload_batch.id,
        project_id=project.id,
        ticket_type="INCIDENT",
        original_filename="incidents.csv",
        saved_filename="incidents.csv",
        storage_path="C:\\temp\\incidents.csv",
        size_bytes=1,
        status="NORMALIZED",
    )
    db.add(uploaded_file)
    db.flush()
    db.commit()
    return db, client.id, project.id, upload_batch.id, uploaded_file.id


def cleanup_client(db, client_id: UUID) -> None:
    db.rollback()
    db.execute(delete(Client).where(Client.id == client_id))
    db.commit()
    db.close()


def add_dimension(
    db,
    project_id: UUID,
    application_name: str,
    *,
    application_alias: str | None = None,
    business_service_alias: str | None = None,
    cmdb_ci_alias: str | None = None,
    is_active: bool = True,
) -> ApplicationDimension:
    dimension = ApplicationDimension(
        project_id=project_id,
        customer_name=f"Customer {application_name}",
        tower_name="Applications Tower",
        cluster_name=f"Cluster {application_name}",
        application_group_name=f"Group {application_name}",
        application_name=application_name,
        application_alias=application_alias,
        business_service_alias=business_service_alias,
        cmdb_ci_alias=cmdb_ci_alias,
        is_active=is_active,
    )
    db.add(dimension)
    db.flush()
    return dimension


def add_ticket(
    db,
    project_id: UUID,
    upload_batch_id: UUID,
    uploaded_file_id: UUID,
    ticket_number: str,
    *,
    application: str | None = None,
    business_service: str | None = None,
    cmdb_ci: str | None = None,
    service_offering: str | None = None,
    catalog_item: str | None = None,
    application_dimension_id: UUID | None = None,
    customer_name: str | None = None,
    payload_size: int = 0,
) -> None:
    db.add(
        Ticket(
            project_id=project_id,
            upload_batch_id=upload_batch_id,
            uploaded_file_id=uploaded_file_id,
            ticket_number=ticket_number,
            ticket_type="INCIDENT",
            month_key="2026-06",
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            short_description=f"{ticket_number} title",
            state="Closed",
            priority="P3",
            assignment_group="AMS",
            application=application,
            business_service=business_service,
            cmdb_ci=cmdb_ci,
            service_offering=service_offering,
            catalog_item=catalog_item,
            application_dimension_id=application_dimension_id,
            customer_name=customer_name,
            reopen_count=0,
            normalized_payload={"large": "x" * payload_size},
        )
    )


def test_application_dimension_crud_endpoints() -> None:
    db, client_id, project_id, _batch_id, _file_id = create_project()
    try:
        with TestClient(app) as client:
            create_response = client.post(
                "/api/application-dimensions",
                json={
                    "project_id": str(project_id),
                    "customer_name": "BCBSNJ",
                    "tower_name": "Applications Tower",
                    "cluster_name": "Claims Cluster",
                    "application_group_name": "Claims Applications",
                    "application_name": "Claims App",
                    "application_alias": "Claims Portal",
                    "business_service_alias": "Claims Service",
                    "cmdb_ci_alias": "CI Claims",
                    "notes": "Initial mapping",
                },
            )

        assert create_response.status_code == 201
        created = create_response.json()
        assert created["application_name"] == "Claims App"
        assert created["is_active"] is True

        with TestClient(app) as client:
            update_response = client.put(
                f"/api/application-dimensions/{created['id']}",
                json={"tower_name": "New Tower", "notes": "Updated"},
            )
            delete_response = client.delete(f"/api/application-dimensions/{created['id']}")
            list_response = client.get(
                "/api/application-dimensions",
                params={"project_id": str(project_id)},
            )

        assert update_response.status_code == 200
        assert update_response.json()["tower_name"] == "New Tower"
        assert delete_response.status_code == 200
        assert delete_response.json()["is_active"] is False
        assert list_response.status_code == 200
        assert list_response.json()[0]["is_active"] is False
    finally:
        cleanup_client(db, client_id)


def test_bulk_upload_trims_nulls_and_updates_duplicate_mapping() -> None:
    db, client_id, project_id, _batch_id, _file_id = create_project()
    try:
        csv_payload = "\n".join(
            [
                "customer_name,tower_name,cluster_name,application_group_name,application_name,"
                "application_alias,business_service_alias,cmdb_ci_alias,notes",
                " BCBSNJ , Applications Tower , Claims , Claims Apps , Claims App , "
                "Claims Portal , , CI Claims , first",
                "BCBSNJ,Applications Tower,Claims,Claims Apps,Claims App,Claims Portal,,"
                "CI Claims,second",
                "BCBSNJ,Applications Tower,Claims,Claims Apps,,Alias Only,,,bad",
            ]
        )

        with TestClient(app) as client:
            response = client.post(
                "/api/application-dimensions/bulk-upload",
                data={"project_id": str(project_id)},
                files={
                    "file": (
                        "dimensions.csv",
                        csv_payload.encode("utf-8"),
                        "text/csv",
                    )
                },
            )

        assert response.status_code == 201
        payload = response.json()
        assert payload["total_rows"] == 3
        assert payload["inserted_count"] == 1
        assert payload["updated_count"] == 1
        assert payload["skipped_count"] == 1

        dimensions = list(
            db.scalars(
                select(ApplicationDimension).where(
                    ApplicationDimension.project_id == project_id
                )
            )
        )
        assert len(dimensions) == 1
        assert dimensions[0].customer_name == "BCBSNJ"
        assert dimensions[0].business_service_alias is None
        assert dimensions[0].notes == "second"
    finally:
        cleanup_client(db, client_id)


def test_enrich_tickets_uses_priority_and_preserves_existing_when_requested() -> None:
    db, client_id, project_id, batch_id, file_id = create_project()
    try:
        old_dimension = add_dimension(
            db,
            project_id,
            "Existing App",
            application_alias="Existing Alias",
        )
        add_dimension(db, project_id, "Alias App", application_alias="Alias Match")
        add_dimension(db, project_id, "Name Match")
        add_dimension(db, project_id, "Business App", business_service_alias="Business Service")
        add_dimension(db, project_id, "CMDB App", cmdb_ci_alias="CI Match")
        add_dimension(db, project_id, "Offering App", business_service_alias="Offering Match")
        add_dimension(db, project_id, "Catalog App", application_alias="Catalog Match")
        add_dimension(
            db,
            project_id,
            "Inactive App",
            application_alias="Inactive Match",
            is_active=False,
        )
        db.flush()

        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-ALIAS",
            application=" alias match ",
            payload_size=200_000,
        )
        add_ticket(db, project_id, batch_id, file_id, "INC-NAME", application="name match")
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-BUSINESS",
            business_service="BUSINESS SERVICE",
        )
        add_ticket(db, project_id, batch_id, file_id, "INC-CI", cmdb_ci="ci match")
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-OFFERING",
            service_offering="Offering Match",
        )
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-CATALOG",
            catalog_item="Catalog Match",
        )
        add_ticket(db, project_id, batch_id, file_id, "INC-INACTIVE", application="Inactive Match")
        add_ticket(db, project_id, batch_id, file_id, "INC-UNMATCHED", application="No Match")
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-EXISTING",
            application="Alias Match",
            application_dimension_id=old_dimension.id,
            customer_name="Preserved Customer",
        )
        db.commit()

        captured_sql: list[str] = []

        def capture_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
            captured_sql.append(str(statement).lower())

        event.listen(db.bind, "before_cursor_execute", capture_sql)
        try:
            with TestClient(app) as client:
                preserve_response = client.post(
                    "/api/application-dimensions/enrich-tickets",
                    json={"project_id": str(project_id), "replace_existing": False},
                )
        finally:
            event.remove(db.bind, "before_cursor_execute", capture_sql)

        assert preserve_response.status_code == 200
        preserve_payload = preserve_response.json()
        assert preserve_payload["total_tickets"] == 9
        assert preserve_payload["updated_tickets"] == 6
        assert preserve_payload["matched_tickets"] == 7
        assert preserve_payload["unmatched_tickets"] == 2
        assert preserve_payload["match_counts_by_source"]["application_alias"] == 1
        assert preserve_payload["match_counts_by_source"]["application_name"] == 1
        assert preserve_payload["match_counts_by_source"]["business_service_alias"] == 1
        assert preserve_payload["match_counts_by_source"]["cmdb_ci_alias"] == 1
        assert preserve_payload["match_counts_by_source"]["service_offering"] == 1
        assert preserve_payload["match_counts_by_source"]["catalog_item"] == 1
        assert any(
            row["value"] == "No Match"
            for row in preserve_payload["top_unmatched_applications"]
        )

        existing_ticket = db.scalar(
            select(Ticket).where(
                Ticket.project_id == project_id,
                Ticket.ticket_number == "INC-EXISTING",
            )
        )
        assert existing_ticket is not None
        assert existing_ticket.customer_name == "Preserved Customer"
        assert not any(
            "select" in statement
            and "normalized_payload" in statement.split("from", maxsplit=1)[0]
            for statement in captured_sql
        )

        with TestClient(app) as client:
            replace_response = client.post(
                "/api/application-dimensions/enrich-tickets",
                json={"project_id": str(project_id), "replace_existing": True},
            )
            filter_response = client.get(
                "/api/dashboard/filter-values",
                params={"project_id": str(project_id)},
            )
            trend_response = client.get(
                "/api/dashboard/trends/reopen-count",
                params={
                    "project_id": str(project_id),
                    "customer_name": "Customer Alias App",
                    "time_grain": "MONTHLY",
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-30",
                },
            )

        assert replace_response.status_code == 200
        replace_payload = replace_response.json()
        assert replace_payload["updated_tickets"] == 7
        assert replace_payload["matched_tickets"] == 7

        db.refresh(existing_ticket)
        assert existing_ticket.customer_name == "Customer Alias App"
        assert filter_response.status_code == 200
        filter_payload = filter_response.json()
        assert "Customer Alias App" in filter_payload["customers"]
        assert "Applications Tower" in filter_payload["towers"]
        assert "Group Alias App" in filter_payload["application_groups"]
        assert "Alias App" in filter_payload["application_names"]
        assert trend_response.status_code == 200
        assert trend_response.json()[0]["total_tickets"] == 2
    finally:
        cleanup_client(db, client_id)


def test_enrichment_summary_endpoint_returns_compact_counts() -> None:
    db, client_id, project_id, batch_id, file_id = create_project()
    try:
        dimension = add_dimension(db, project_id, "Summary App", application_alias="Summary")
        add_ticket(
            db,
            project_id,
            batch_id,
            file_id,
            "INC-SUMMARY",
            application="Summary",
            application_dimension_id=dimension.id,
            customer_name="Customer Summary App",
        )
        add_ticket(db, project_id, batch_id, file_id, "INC-SUMMARY-UNMATCHED", application="Other")
        db.commit()

        with TestClient(app) as client:
            response = client.get(
                "/api/application-dimensions/enrichment-summary",
                params={"project_id": str(project_id)},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total_tickets"] == 2
        assert payload["matched_tickets"] == 1
        assert payload["unmatched_tickets"] == 1
        assert payload["match_rate_pct"] == 50.0
    finally:
        cleanup_client(db, client_id)

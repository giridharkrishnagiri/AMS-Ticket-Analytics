# AMS Ticket Intelligence

AMS Ticket Intelligence is a Windows-friendly full-stack MVP foundation for analyzing AMS incident and service catalog ticket data.

## Technology Stack

- Backend: Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, PostgreSQL
- Dependency management: uv
- Frontend: React, TypeScript, Vite
- Storage: local filesystem folders for uploaded files and generated exports
- MVP runtime: no Docker required

## Project Structure

```text
backend/
  app/
    api/
    core/
    db/
    models/
    schemas/
    services/
  alembic/
frontend/
  src/
run_backend.bat
run_frontend.bat
seed_default_data.bat
```

## Prerequisites For Windows

Install these before running the app:

1. Python 3.12
2. uv for Python dependency management
3. Node.js 20 LTS or newer
4. PostgreSQL 15 or newer

Confirm the tools are available from PowerShell:

```powershell
python --version
uv --version
node --version
npm --version
psql --version
```

The batch files use a local backend uv cache folder at `backend\.uv-cache` so setup works even when the default Windows uv cache path is unavailable.

## Database Setup

Create a PostgreSQL database named `ams_ticket_intelligence`. One option is to use `psql`:

```powershell
createdb -U postgres ams_ticket_intelligence
```

If your PostgreSQL username, password, host, or database name is different, update `backend\.env` after copying the example file.

## Environment Files

From the project root, copy the example files:

```powershell
copy backend\.env.example backend\.env
copy frontend\.env.example frontend\.env
```

The backend reads database settings from `backend\.env`. Example:

```text
DATABASE_URL=postgresql+psycopg://ams_user:replace_with_your_password@localhost:5432/ams_ticket_intelligence
```

Verify that the backend is reading `backend\.env`:

```powershell
cd backend
uv run python -c "from app.core.config import Settings; print(Settings().database_url)"
```

## Backend Setup And Run

Use the batch file from the project root:

```powershell
.\run_backend.bat
```

The backend will run at:

```text
http://127.0.0.1:8000
```

Health check:

```text
http://127.0.0.1:8000/api/health
```

API docs:

```text
http://127.0.0.1:8000/api/docs
```

## Frontend Setup And Run

Use the batch file from the project root:

```powershell
.\run_frontend.bat
```

The batch file uses `npm.cmd` to avoid PowerShell `npm.ps1` execution-policy issues.

The frontend will run at:

```text
http://127.0.0.1:5173
```

The home page calls `GET /api/health` and shows the backend status.

The Upload Center tab lets you upload Incident and Service Catalog Task CSV/XLSX files. Enter the project UUID, choose the ticket type, choose the upload period type, enter a batch name, select one or more files, then submit. Monthly extracts require a Month-Year. Snapshot extracts require a snapshot date and do not require or store a fake Month-Year. After upload, the page refreshes the batch list and shows files for the selected batch.

Upload Center ingestion workflow:

1. Upload one or more CSV/XLSX files.
2. Select the uploaded batch from Active Upload Batches.
3. Click `Ingest File` beside each uploaded file that should be staged.
4. Review the Job Status table and use `Refresh Jobs` when needed.
5. Review Raw Row Preview for the top staged rows.
6. Review Validation Summary for row totals, missing key fields, duplicates, detected source columns, and rows by file.
7. Use `Clear Files`, `Clear Details`, `Clear Preview`, or `Clear Summary` to clear browser display state only. These actions do not delete uploaded files or database records.

Upload Center separates active staging work from historical completed work:

- Active Upload Batches shows batches that still need ingestion, mapping, normalization, or failure review.
- Historical Batches shows normalized or archived batches.
- `Delete Batch` is available only for staging batches that do not have normalized tickets. It soft-deletes the staging batch from the active/history worklists and is blocked when normalized tickets already exist.
- Normalized batches are not hard deleted by default. Archive keeps raw rows, uploaded file metadata, and normalized tickets for auditability.

Batch lifecycle statuses:

- `UPLOADED`: files uploaded and waiting for ingestion.
- `INGESTING`: at least one ingestion job is running or some files are still pending.
- `INGESTED`: all uploaded files in the batch completed ingestion.
- `INGESTION_FAILED`: one or more files failed ingestion.
- `NORMALIZING`: mapping is being applied.
- `NORMALIZED`: tickets were successfully created in `tickets`.
- `NORMALIZATION_FAILED`: mapping ran but did not fully normalize the batch.
- `ARCHIVED`: normalized batch hidden from active worklists but preserved in history.
- `DELETED`: staging batch hidden from normal views after explicit delete.

The Mapping Wizard tab is organized around reusable project and ticket-type templates. Select a project, choose `INCIDENT` or `SERVICE_CATALOG_TASK`, optionally select a representative batch for source-column inspection, load the remembered or suggested mapping, adjust source-column dropdowns, save the mapping template, and apply it to either one selected batch or all batches of that ticket type. Applying a mapping deletes and recreates normalized tickets only for the selected apply scope. Raw uploaded files and staged raw rows are not deleted.

## Database Migrations

The project includes an initial Alembic migration for foundation tables. Run migrations from the backend folder:

```powershell
cd backend
uv sync --dev
uv run alembic upgrade head
```

Then seed the default local client and project:

```powershell
cd ..
.\seed_default_data.bat
```

The seed stores these default source folders on the project record:

```text
Incidents: C:\Users\giridharkr\Downloads\Incidents
Service Catalog tasks: C:\Users\giridharkr\Downloads\SC Tasks
```

To create a future migration after changing SQLAlchemy models:

```powershell
cd backend
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
```

## Local File Storage

The backend creates local storage folders automatically on startup:

```text
backend\storage\uploads
backend\storage\exports
```

These folders are intentionally ignored by Git because they will contain user-uploaded source files and generated exports.

## Upload And Ingestion API

Upload support stores original CSV/XLSX files. Ingestion support streams one uploaded file at a time into `ticket_raw_rows`. Normalization into `tickets` happens later through the Mapping Wizard or mapping API.

Start the backend first:

```powershell
.\run_backend.bat
```

Upload one incident file:

```powershell
cd backend
curl.exe -X POST "http://127.0.0.1:8000/api/uploads" `
  -F "project_id=PUT_PROJECT_UUID_HERE" `
  -F "ticket_type=INCIDENT" `
  -F "period_type=MONTHLY" `
  -F "month_key=2026-06" `
  -F "batch_name=June 2026 Incidents" `
  -F "files=@C:\Users\giridharkr\Downloads\Incidents\sample.csv"
```

Upload multiple service catalog task files:

```powershell
cd backend
curl.exe -X POST "http://127.0.0.1:8000/api/uploads" `
  -F "project_id=PUT_PROJECT_UUID_HERE" `
  -F "ticket_type=SERVICE_CATALOG_TASK" `
  -F "period_type=MONTHLY" `
  -F "month_key=2026-06" `
  -F "batch_name=June 2026 SC Tasks" `
  -F "files=@C:\Users\giridharkr\Downloads\SC Tasks\sample-1.xlsx" `
  -F "files=@C:\Users\giridharkr\Downloads\SC Tasks\sample-2.xlsx"
```

Upload an open Incident snapshot without Month-Year:

```powershell
cd backend
curl.exe -X POST "http://127.0.0.1:8000/api/uploads" `
  -F "project_id=PUT_PROJECT_UUID_HERE" `
  -F "ticket_type=INCIDENT" `
  -F "period_type=SNAPSHOT" `
  -F "snapshot_date=2026-06-17" `
  -F "batch_name=Open Incidents Snapshot - 2026-06-17" `
  -F "files=@C:\Users\giridharkr\Downloads\Incidents\open-incidents.csv"
```

If `snapshot_date` is omitted for a snapshot upload, the backend defaults it to today's date. Monthly uploads still require `month_key`.

List upload batches:

```powershell
curl.exe "http://127.0.0.1:8000/api/uploads/batches?view=active"
curl.exe "http://127.0.0.1:8000/api/uploads/batches?view=history"
curl.exe "http://127.0.0.1:8000/api/uploads/batches?view=all"
```

Delete a pre-normalized staging batch:

```powershell
curl.exe -X DELETE "http://127.0.0.1:8000/api/uploads/batches/PUT_UPLOAD_BATCH_UUID_HERE"
```

Archive a normalized batch without deleting data:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/uploads/batches/PUT_UPLOAD_BATCH_UUID_HERE/archive"
```

List uploaded files for a batch:

```powershell
curl.exe "http://127.0.0.1:8000/api/uploads/batches/PUT_UPLOAD_BATCH_UUID_HERE/files"
```

Check an ingestion job:

```powershell
curl.exe "http://127.0.0.1:8000/api/uploads/ingestion-jobs/PUT_INGESTION_JOB_UUID_HERE"
```

Trigger ingestion for one uploaded file:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/uploads/files/PUT_UPLOADED_FILE_UUID_HERE/ingest"
```

Preview the first staged raw rows for a batch:

```powershell
curl.exe "http://127.0.0.1:8000/api/uploads/batches/PUT_UPLOAD_BATCH_UUID_HERE/raw-rows/preview?limit=5"
```

Show validation summary for a batch:

```powershell
curl.exe "http://127.0.0.1:8000/api/uploads/batches/PUT_UPLOAD_BATCH_UUID_HERE/validation-summary"
```

The validation summary reports total raw rows, likely missing ticket IDs, likely missing created dates, duplicate ticket IDs when detectable, detected source columns, and row counts by uploaded file.

## Mapping Wizard And Normalization API

The Mapping Wizard is available in the frontend navigation after Upload Center. Use it after upload and ingestion:

1. Select the project ID and ticket type.
2. Optionally select a representative ingested or normalized upload batch.
3. Click `Load Source Columns`.
4. Click `Load Suggested Mapping`.
5. Review and adjust source-column dropdowns.
6. Save the mapping template if the mapping should be reused.
7. Choose `Selected batch only` or `All batches of selected ticket type`.
8. Click `Apply Mapping`.

Get detected source columns from staged raw rows:

```powershell
curl.exe "http://127.0.0.1:8000/api/mappings/batches/PUT_UPLOAD_BATCH_UUID_HERE/source-columns"
```

Get detected source columns across all staged rows for a project and ticket type:

```powershell
curl.exe "http://127.0.0.1:8000/api/mappings/source-columns?project_id=PUT_PROJECT_UUID_HERE&ticket_type=INCIDENT"
```

Get a remembered or suggested mapping from detected columns to normalized ticket fields:

```powershell
curl.exe "http://127.0.0.1:8000/api/mappings/batches/PUT_UPLOAD_BATCH_UUID_HERE/suggested-mapping"
```

For project and ticket-type templates, the suggested mapping endpoint first returns a saved mapping from `source_column_mappings` when one exists. If no saved template exists, it returns the built-in deterministic mapping:

```powershell
curl.exe "http://127.0.0.1:8000/api/mappings/suggested-mapping?project_id=PUT_PROJECT_UUID_HERE&ticket_type=INCIDENT"
```

Built-in Incident suggestions map `business_duration_seconds` from ServiceNow `business_stc`. Built-in Service Catalog Task suggestions map `business_duration_seconds` from ServiceNow `business_duration`. Both map `reassignment_count` from ServiceNow `reassignment_count`.

Save a mapping template for a project and ticket type:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/mappings/templates" `
  -H "Content-Type: application/json" `
  -d "{\"project_id\":\"PUT_PROJECT_UUID_HERE\",\"ticket_type\":\"INCIDENT\",\"mapping\":{\"ticket_id\":\"number\",\"title\":\"short_description\",\"status\":\"state\",\"priority\":\"priority\",\"assignment_group\":\"assignment_group\",\"created_at\":\"sys_created_on\",\"resolved_at\":\"resolved_at\",\"sla_breached\":\"sla_breached\"}}"
```

Retrieve a saved mapping template:

```powershell
curl.exe "http://127.0.0.1:8000/api/mappings/templates?project_id=PUT_PROJECT_UUID_HERE&ticket_type=INCIDENT"
```

Apply a mapping to staged raw rows and create normalized tickets:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/mappings/batches/PUT_UPLOAD_BATCH_UUID_HERE/apply" `
  -H "Content-Type: application/json" `
  -d "{\"mapping\":{\"ticket_id\":\"number\",\"title\":\"short_description\",\"status\":\"state\",\"priority\":\"priority\",\"assignment_group\":\"assignment_group\",\"created_at\":\"sys_created_on\",\"resolved_at\":\"resolved_at\",\"sla_breached\":\"sla_breached\"},\"delete_existing\":true}"
```

If `mapping` is omitted from the apply request, the backend uses the saved template for the batch project and staged ticket type. Re-applying is idempotent for the selected batch because existing normalized tickets for that upload batch are deleted and recreated before the new apply result is committed.

Apply a mapping with an explicit scope:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/mappings/apply" `
  -H "Content-Type: application/json" `
  -d "{\"project_id\":\"PUT_PROJECT_UUID_HERE\",\"ticket_type\":\"INCIDENT\",\"scope\":\"TICKET_TYPE\",\"mapping\":{\"ticket_id\":\"number\",\"title\":\"short_description\",\"created_at\":\"sys_created_on\",\"business_duration_seconds\":\"business_stc\",\"reassignment_count\":\"reassignment_count\"},\"delete_existing\":true,\"save_as_default_for_ticket_type\":true}"
```

Use `scope` = `BATCH` with `upload_batch_id` to re-normalize one selected batch. Use `scope` = `TICKET_TYPE` to re-normalize all batches for the selected project and ticket type. Incident mappings are applied only to Incident batches, and Service Catalog Task mappings are applied only to Service Catalog Task batches.

For larger mappings, PowerShell is easier if you store JSON in a file.

Example `C:\AIProjects\incident_mapping.json`:

```json
{
  "mapping": {
    "ticket_id": "number",
    "title": "short_description",
    "description": "description",
    "status": "state",
    "priority": "priority",
    "urgency": "urgency",
    "impact": "impact",
    "category": "category",
    "subcategory": "subcategory",
    "application": "business_service",
    "configuration_item": "cmdb_ci",
    "assignment_group": "assignment_group",
    "assigned_to": "assigned_to",
    "requester": "caller_id",
    "created_by": "opened_by",
    "created_at": "sys_created_on",
    "resolved_at": "resolved_at",
    "closed_at": "closed_at",
    "sla_breached": "made_sla",
    "reopen_count": "reopen_count",
    "reassignment_count": "reassignment_count",
    "business_duration_seconds": "business_stc",
    "resolution_code": "close_code",
    "resolution_notes": "close_notes"
  },
  "delete_existing": true
}
```

Example `C:\AIProjects\sctask_mapping.json`:

```json
{
  "mapping": {
    "ticket_id": "number",
    "title": "short_description",
    "description": "description",
    "status": "state",
    "priority": "priority",
    "category": "sc_catalog",
    "application": "cmdb_ci_business_app",
    "configuration_item": "cmdb_ci",
    "assignment_group": "assignment_group",
    "assigned_to": "assigned_to",
    "requester": "request.requested_for",
    "created_by": "sys_created_by",
    "created_channel": "contact_type",
    "created_at": "sys_created_on",
    "closed_at": "closed_at",
    "sla_breached": "made_sla",
    "business_duration_seconds": "business_duration",
    "reassignment_count": "reassignment_count",
    "resolution_notes": "close_notes"
  },
  "delete_existing": true
}
```

Apply those files with `--data-binary`:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/mappings/batches/PUT_INCIDENT_BATCH_UUID_HERE/apply" `
  -H "Content-Type: application/json" `
  --data-binary "@C:\AIProjects\incident_mapping.json"

curl.exe -X POST "http://127.0.0.1:8000/api/mappings/batches/PUT_SCTASK_BATCH_UUID_HERE/apply" `
  -H "Content-Type: application/json" `
  --data-binary "@C:\AIProjects\sctask_mapping.json"
```

Additional future source columns, such as response SLA, resolution SLA, SLA target, SLA breached, response due, resolution due, actual response time, and actual resolution time, are preserved in `tickets.normalized_payload.raw_payload_json` even before explicit normalized database fields are added.

For dashboard metrics, map Incident ServiceNow `business_stc` to `business_duration_seconds`, Service Catalog Task ServiceNow `business_duration` to `business_duration_seconds`, and `reassignment_count` to `reassignment_count` in the Mapping Wizard. Business duration is stored as seconds; dashboard MTTR APIs convert it to days by dividing by `86400`. Existing uploaded batches should be re-applied through the Mapping Wizard after adding these mappings so the new ticket columns are populated.

## Incident SLA Upload And Enrichment

Incident SLA data is loaded from separate ServiceNow SLA extracts and staged in `incident_sla_rows`. The original SLA row is preserved in `incident_sla_rows.raw_data`; summary and enrichment queries do not select that JSON payload.

The frontend has an `SLA Upload` tab with:

1. Project ID input.
2. Incident SLA CSV picker.
3. Upload button.
4. Enrich Incident SLA button.
5. Compact SLA summary and unmatched incident sample.

Backend endpoints:

- `POST /api/sla/incidents/upload`
- `POST /api/sla/incidents/enrich`
- `GET /api/sla/incidents/summary?project_id=...`
- `GET /api/sla/incidents/unmatched?project_id=...&limit=100&offset=0`

Upload one Incident SLA CSV:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/sla/incidents/upload" `
  -F "project_id=PUT_PROJECT_UUID_HERE" `
  -F "file=@C:\Users\giridharkr\Downloads\Incidents_SLA\PUT_FILE_NAME_HERE.csv"
```

Upload all monthly Incident SLA CSV files from January 2025 through June 2026:

```powershell
Get-ChildItem "C:\Users\giridharkr\Downloads\Incidents_SLA" -Filter *.csv | ForEach-Object {
  curl.exe -X POST "http://127.0.0.1:8000/api/sla/incidents/upload" `
    -F "project_id=PUT_PROJECT_UUID_HERE" `
    -F "file=@$($_.FullName)"
}
```

Enrich matching Incident tickets:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/sla/incidents/enrich" `
  -H "Content-Type: application/json" `
  -d "{\"project_id\":\"PUT_PROJECT_UUID_HERE\",\"ticket_type\":\"INCIDENT\",\"replace_existing\":true}"
```

Selection logic is deterministic:

- Match `incident_sla_rows.inc_number` to `tickets.ticket_number`.
- Enrich only `tickets.ticket_type = 'INCIDENT'`.
- Response SLA uses rows with `taskslatable_sla.target = Response`.
- Resolution SLA uses rows with `taskslatable_sla.target = Resolution`.
- Prefer SLA names containing `Accenture`.
- If no Accenture row exists, fall back to SLA names containing `Default`.
- If multiple preferred rows exist, choose `Completed` stage first, then the lowest source row number.

The enrichment writes:

- `response_sla_breached`
- `resolution_sla_breached`
- `response_sla_business_elapsed_seconds`
- `resolution_sla_business_elapsed_seconds`
- `response_sla_name`
- `resolution_sla_name`
- `response_sla_updated_at`
- `resolution_sla_updated_at`
- `sla_enriched_at`

The existing `tickets.sla_breached` column is preserved for backward compatibility and is not overwritten by Incident SLA enrichment.

Get compact SLA summary:

```powershell
curl.exe "http://127.0.0.1:8000/api/sla/incidents/summary?project_id=PUT_PROJECT_UUID_HERE"
```

Get unmatched SLA incident numbers:

```powershell
curl.exe "http://127.0.0.1:8000/api/sla/incidents/unmatched?project_id=PUT_PROJECT_UUID_HERE&limit=100&offset=0"
```

Manual SQL checks after enrichment:

```sql
SELECT
  COUNT(*) AS incident_count,
  COUNT(response_sla_breached) AS response_sla_populated,
  COUNT(resolution_sla_breached) AS resolution_sla_populated,
  COUNT(response_sla_business_elapsed_seconds) AS response_business_elapsed_populated,
  COUNT(resolution_sla_business_elapsed_seconds) AS resolution_business_elapsed_populated,
  COUNT(response_sla_name) AS response_sla_name_populated,
  COUNT(resolution_sla_name) AS resolution_sla_name_populated
FROM tickets
WHERE ticket_type = 'INCIDENT';
```

```sql
SELECT
  ticket_number,
  response_sla_name,
  response_sla_breached,
  response_sla_business_elapsed_seconds,
  resolution_sla_name,
  resolution_sla_breached,
  resolution_sla_business_elapsed_seconds
FROM tickets
WHERE ticket_type = 'INCIDENT'
AND (
  response_sla_name IS NOT NULL
  OR resolution_sla_name IS NOT NULL
)
LIMIT 50;
```

## Legacy Application Dimension Configuration

The previous `Application Dimensions` backend API remains available for compatibility. New user-facing work should use `Application Inventory`, which better matches the real CMDB/Application data.

Supported dimension fields:

- `customer_name`
- `tower_name`
- `cluster_name`
- `application_group_name`
- `application_name`
- `application_alias`
- `business_service_alias`
- `cmdb_ci_alias`
- `notes`

The existing JSON alias columns remain available in the database for compatibility, but Prompt 10 matching uses the singular alias columns above.

Application dimension endpoints:

- `GET /api/application-dimensions?project_id=...`
- `POST /api/application-dimensions`
- `PUT /api/application-dimensions/{id}`
- `DELETE /api/application-dimensions/{id}`
- `POST /api/application-dimensions/bulk-upload`
- `POST /api/application-dimensions/enrich-tickets`
- `GET /api/application-dimensions/enrichment-summary?project_id=...`

Example CSV:

```csv
customer_name,tower_name,cluster_name,application_group_name,application_name,application_alias,business_service_alias,cmdb_ci_alias,notes
BCBSNJ,Applications Tower,Claims Cluster,Claims Applications,Sample App,Sample App,,,Test mapping
```

Upload a dimension CSV:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/application-dimensions/bulk-upload" `
  -F "project_id=PUT_PROJECT_UUID_HERE" `
  -F "file=@C:\AIProjects\application_dimensions.csv"
```

Enrich tickets:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/application-dimensions/enrich-tickets" `
  -H "Content-Type: application/json" `
  -d "{\"project_id\":\"PUT_PROJECT_UUID_HERE\",\"replace_existing\":true}"
```

Matching is deterministic, project-scoped, case-insensitive, trimmed, and active-dimension-only. Priority order:

1. `tickets.application` to `application_dimensions.application_alias`
2. `tickets.application` to `application_dimensions.application_name`
3. `tickets.business_service` to `application_dimensions.business_service_alias`
4. `tickets.cmdb_ci` to `application_dimensions.cmdb_ci_alias`
5. `tickets.service_offering` to `application_dimensions.business_service_alias`
6. `tickets.catalog_item` to `application_dimensions.application_alias`

Ticket enrichment updates only:

- `tickets.application_dimension_id`
- `tickets.customer_name`
- `tickets.tower_name`
- `tickets.cluster_name`
- `tickets.application_group_name`
- `tickets.application_name`

Raw ticket fields such as `application`, `business_service`, `cmdb_ci`, `service_offering`, `catalog_item`, and uploaded source data are preserved. Dashboard dimension filters use the enriched ticket columns so aggregate dashboard queries stay simple and do not require dimension joins.

## Application Inventory Upload And Enrichment

The frontend navigation includes an `Application Inventory` tab. Use it to upload CMDB/Application Inventory CSV or XLSX files and enrich normalized tickets by Business Service CI Name.

The inventory upload supports:

- `.xlsx` files with a `Group-App-BizService` worksheet.
- `.csv` files with headers in the first row.
- Excel header detection by finding the row containing `Business Service CI Name`; this supports the real workbook where row 2 contains the useful headers.
- Core columns A through K mapped to normalized inventory fields.
- Columns L through CC, and any other unmapped columns, preserved as JSONB in `application_inventory_items.cmdb_payload` using original header names.

Core inventory columns:

- `Application Number (APM)` -> `application_number_apm`
- `Parent Business Application` -> `parent_application_name`
- `Support group name` -> `assignment_group`
- `Support group's owner` -> `assignment_group_owner`
- `Application Owner` -> `application_owner`
- `Business Service CI Name` -> `business_service_ci_name`
- `Support Lead (Managed by)` -> `support_lead`
- `Functional Track` -> `functional_track`
- `AMS Owner` -> `ams_owner`
- `Supported By Vendor` -> `supported_by_vendor`
- `Active` -> `active`

Application Inventory endpoints:

- `GET /api/application-inventory?project_id=...`
- `POST /api/application-inventory/upload`
- `POST /api/application-inventory/enrich-tickets`
- `GET /api/application-inventory/enrichment-summary?project_id=...`
- `GET /api/application-inventory/unmatched-business-services?project_id=...`
- `GET /api/application-inventory/filter-values?project_id=...`
- `PUT /api/application-inventory/{id}`
- `DELETE /api/application-inventory/{id}`
- `GET /api/projects`

Upload Application Inventory:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/application-inventory/upload" `
  -F "project_id=PUT_PROJECT_UUID_HERE" `
  -F "file=@C:\AIProjects\CMDB_CI_Support_Groups_Support_owners - Updated.xlsx"
```

Enrich tickets from Application Inventory:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/application-inventory/enrich-tickets" `
  -H "Content-Type: application/json" `
  -d "{\"project_id\":\"PUT_PROJECT_UUID_HERE\",\"replace_existing\":true}"
```

Check enrichment coverage:

```powershell
curl.exe "http://127.0.0.1:8000/api/application-inventory/enrichment-summary?project_id=PUT_PROJECT_UUID_HERE"
curl.exe "http://127.0.0.1:8000/api/application-inventory/unmatched-business-services?project_id=PUT_PROJECT_UUID_HERE&limit=100"
curl.exe "http://127.0.0.1:8000/api/application-inventory/filter-values?project_id=PUT_PROJECT_UUID_HERE"
```

Ticket enrichment uses deterministic SQL `UPDATE ... FROM` statements and does not loop through all tickets in Python.

Matching order:

1. `tickets.business_service` to `application_inventory_items.business_service_ci_name`
2. Remaining unmatched `tickets.application` to `application_inventory_items.business_service_ci_name`

When a Business Service CI Name appears multiple times, enrichment chooses one inventory row per ticket deterministically:

1. Active rows first.
2. Prefer inventory rows whose `assignment_group` matches the ticket assignment group.
3. Then lowest `source_row_number`.
4. Then earliest `created_at`.

Enrichment updates only denormalized inventory fields on `tickets`:

- `application_inventory_id`
- `parent_application_number`
- `parent_application_name`
- `business_service_ci_name`
- `application_owner`
- `support_lead`
- `functional_track`
- `ams_owner`
- `supported_by_vendor`
- `assignment_group_owner`

It does not alter raw ticket fields such as `application`, `business_service`, `cmdb_ci`, `assignment_group`, or `normalized_payload`. Dashboard filter values now include future inventory filters such as Functional Track, AMS Owner, Supported By Vendor, Support Lead, Application Owner, Business Service CI Name, and Parent Application Name.

## Dashboard API And UI

The Dashboard tab uses compact backend aggregate APIs only. It does not request raw ticket rows or `tickets.normalized_payload`.

Dashboard endpoints support `time_grain=DAILY|WEEKLY|MONTHLY|QUARTERLY|YEARLY`; the default is `MONTHLY`. Common filters include `project_id`, repeated or comma-separated `ticket_type`, `priority`, `state`, `assignment_group`, `application`, customer/application hierarchy filters, `start_date`, `end_date`, and `month_key`.

Completion date rules are explicit:

- Incident completion uses `tickets.resolved_at`.
- Service Catalog Task completion uses `tickets.closed_at`.
- Incident actual duration is `resolved_at - created_at`.
- SC Task actual duration is `closed_at - created_at`.
- Business MTTR uses `business_duration_seconds / 86400`.

Open-end count uses two counts for each period end:

- Count A: tickets created on or before period end where the effective completion date is after period end.
- Count B: tickets created on or before period end where the effective completion date is null and state is not a defensive final state such as closed, resolved, complete, completed, cancelled, or canceled.
- `open_end_count = Count A + Count B`.

Created, resolved, and open trend:

```powershell
curl.exe "http://127.0.0.1:8000/api/dashboard/trends/created-resolved-open?project_id=PUT_PROJECT_UUID_HERE&time_grain=MONTHLY"
```

MTTR trend:

```powershell
curl.exe "http://127.0.0.1:8000/api/dashboard/trends/mttr?project_id=PUT_PROJECT_UUID_HERE&ticket_type=INCIDENT"
```

SLA trend:

```powershell
curl.exe "http://127.0.0.1:8000/api/dashboard/trends/sla?project_id=PUT_PROJECT_UUID_HERE"
```

The generic SLA trend endpoint is kept for backward compatibility. The Dashboard tab now uses enriched Incident-only SLA analytics from the response and resolution SLA columns populated by Incident SLA enrichment. Service Catalog Tasks are excluded from SLA metrics because they do not have contractual SLAs.

Incident SLA adherence trend:

```powershell
curl.exe "http://127.0.0.1:8000/api/dashboard/trends/incident-sla?project_id=PUT_PROJECT_UUID_HERE&time_grain=MONTHLY&start_date=2025-01-01&end_date=2026-05-31"
```

Incident SLA KPI summary:

```powershell
curl.exe "http://127.0.0.1:8000/api/dashboard/summary/incident-sla?project_id=PUT_PROJECT_UUID_HERE&start_date=2025-01-01&end_date=2026-05-31"
```

Incident SLA name distribution:

```powershell
curl.exe "http://127.0.0.1:8000/api/dashboard/breakdowns/incident-sla-names?project_id=PUT_PROJECT_UUID_HERE&name_type=BOTH&start_date=2025-01-01&end_date=2026-05-31"
```

Incident SLA metrics are reported as two separate contractual obligations:

- Response SLA adherence % = response SLA met count / response SLA applicable count.
- Resolution SLA adherence % = resolution SLA met count / resolution SLA applicable count.

The dashboard does not calculate or show an overall Incident SLA adherence metric. Breach counts and breach percentages remain secondary context only.

Reopen trend:

```powershell
curl.exe "http://127.0.0.1:8000/api/dashboard/trends/reopen-count?project_id=PUT_PROJECT_UUID_HERE"
```

Reassignment trend:

```powershell
curl.exe "http://127.0.0.1:8000/api/dashboard/trends/reassignment-count?project_id=PUT_PROJECT_UUID_HERE"
```

Creation source trend:

```powershell
curl.exe "http://127.0.0.1:8000/api/dashboard/trends/creation-source?project_id=PUT_PROJECT_UUID_HERE"
```

Technical vs Functional breakdown:

```powershell
curl.exe "http://127.0.0.1:8000/api/dashboard/breakdowns/technical-functional?project_id=PUT_PROJECT_UUID_HERE"
```

Filter values:

```powershell
curl.exe "http://127.0.0.1:8000/api/dashboard/filter-values?project_id=PUT_PROJECT_UUID_HERE"
```

Multi-select filters can be repeated or comma-separated:

```powershell
curl.exe "http://127.0.0.1:8000/api/dashboard/trends/created-resolved-open?project_id=PUT_PROJECT_UUID_HERE&priority=P1&priority=P2"
curl.exe "http://127.0.0.1:8000/api/dashboard/trends/created-resolved-open?project_id=PUT_PROJECT_UUID_HERE&ticket_type=INCIDENT,SERVICE_CATALOG_TASK"
```

The `application_dimensions` table is prepared for one-time customer/application hierarchy configuration: customer, tower or cluster, application group, and application. Configuration upload/UI will come later.

System-created classification is deterministic for now, using stored `is_system_created` or obvious creator text such as monitoring, alert, system, integration, scheduler, and service account. LLM-assisted classification may be added later.

Technical vs Functional classification is prepared for Incidents only. SC Tasks are requests and are returned as not applicable. AI classification for Incident technical/functional type will come later.

## Initial Database Model

The initial schema includes:

- `clients`
- `projects`
- `upload_batches`
- `uploaded_files`
- `ingestion_jobs`
- `source_column_mappings`
- `ticket_raw_rows`
- `tickets`
- `incident_sla_rows`
- `dashboard_aggregates`
- `export_jobs`

`ticket_raw_rows` keeps full source-row JSON for traceability and future column changes. Dashboards should use `tickets` and `dashboard_aggregates`, not raw rows directly.

## Development Checks

Backend:

```powershell
cd backend
uv sync --dev
uv run ruff check .
uv run pytest
```

Frontend:

```powershell
cd frontend
npm.cmd install
npm.cmd run typecheck
npm.cmd run build
```

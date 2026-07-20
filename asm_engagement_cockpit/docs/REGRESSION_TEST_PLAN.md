# ASM Engagement Cockpit Regression Test Plan

## 1. Purpose

This test plan validates that the full ASM Engagement Cockpit still works after all MVPs.

Run this checklist before final demo, handover, or deployment.

## 2. Test Environment

| Item | Expected |
|---|---|
| Backend | http://localhost:8020 |
| Frontend | http://localhost:3020 |
| Database | PostgreSQL on local port 5434 |
| Backend env | backend/.env |
| Frontend env | frontend/.env |

## 3. Build and Startup Tests

### 3.1 Backend Import Test

cd /home/induser1/giri/AIProjects/asm_engagement_cockpit/backend

uv run python -c "import app.main; print('backend import OK')"

Pass criteria:

backend import OK
### 3.2 Frontend Build Test
cd /home/induser1/giri/AIProjects/asm_engagement_cockpit/frontend

npm run build

Pass criteria:

Build completes successfully
### 3.3 Backend Startup Test
cd /home/induser1/giri/AIProjects/asm_engagement_cockpit

bash ./start_backend.sh

Pass criteria:

Backend starts on port 8020
No import errors
No database connection errors
### 3.4 Frontend Startup Test
cd /home/induser1/giri/AIProjects/asm_engagement_cockpit

bash ./start_frontend.sh

Pass criteria:

Frontend starts on port 3020
Page loads in browser
## 4. API Health Tests
### 4.1 Health Endpoint
curl http://localhost:8020/api/health

Pass criteria:

status is ok
### 4.2 Diagnostics Endpoint

From UI:

Runtime Config section loads backend diagnostics
Database status is connected

Pass criteria:

Diagnostics table renders successfully
## 5. Login and Session Tests
### 5.1 Login Optional Mode

Use:

VITE_APP_LOGIN_REQUIRED=false
API_AUTH_ENABLED=false

Pass criteria:

Application loads without login
Login panel still appears
Login succeeds with backend credentials
Logout clears local session
### 5.2 Login Required Mode

Use:

VITE_APP_LOGIN_REQUIRED=true
API_AUTH_ENABLED=true

Pass criteria:

Application opens to login-only screen
Login succeeds
Cockpit loads after login
Logout returns to login-only state
Protected API calls work after login
## 6. Core Hierarchy Tests

Validate these sections load:

Dashboard
Engagements
Workstreams
Deliverables
Tasks
Sub-tasks

Pass criteria:

Tables render without frontend errors
Counts are visible
Statuses display correctly
## 7. Reminders Tests

Validate:

Active Reminders section loads
Refresh Reminders works
Overdue/due-soon reminders display

Pass criteria:

Refresh Reminders completes without error
Reminder cards display or empty state appears
## 8. Data Gathering Tests

Validate sections:

Data Points
Stakeholder Questions

Pass criteria:

Data point table loads
Stakeholder question table loads
Expected/actual date fields display
Status fields display
## 9. Findings and Analysis Tests

Validate sections:

Findings
Analysis Outputs
Dictation & Refinement

Pass criteria:

Findings table loads
Analysis table loads
Dictation/refinement panel loads
Manual text refinement works
Save as finding works if a sub-task is selected
Save as analysis works if a sub-task is selected
## 10. File Upload Tests

Validate:

File Upload section loads
Upload form displays
Uploaded files table displays

Pass criteria:

File upload succeeds for a small test file
Uploaded file appears in the table
Download link works if available
## 11. LLM Feature Tests

Only run when OPENAI_API_KEY is configured.

Validate sections:

LLM Recommendations
Deliverable Reviews
Recommendation Management
Timesheet Summary

Pass criteria:

LLM recommendation generation succeeds
Deliverable review generation succeeds
Recommendation decision/revision/action item flows work
Timesheet summary generation succeeds
OpenAI tracing is enabled if OPENAI_TRACING=true
## 12. Timesheet Tests

Validate:

Timesheets section loads
Daily timesheet entry can be created
Weekly timesheet submission works
Timesheet summary can be generated if OpenAI is configured

Pass criteria:

Timesheet entry appears after save
Weekly submission returns submitted count
Summary appears after generation
## 13. Review Workflow Tests

Validate:

Review Workflow section loads
Deliverable can be submitted for review
Review decision can be recorded
Review action item can be created
Action item can be marked complete

Pass criteria:

Workflow table updates
Action table updates
Deliverable review status updates
## 14. Role-Based Views Tests

Validate:

Role-Based Views section loads
Role filter works
Health filter works
Search filter works
Filtered tables update

Pass criteria:

No TypeScript or runtime errors
Filter results update based on selected values
## 15. Runtime Config Tests

Validate:

Runtime Config section loads
Frontend config table loads
Backend diagnostics table loads
Session token configured status updates after login

Pass criteria:

Frontend and backend runtime configuration values are visible
## 16. Operations Dashboard Tests

Validate:

Operations dashboard loads
Bootstrap Current User works
Users table updates
Roles table loads
Generate Notifications from Reminders works
Notifications table loads
Mark Read works
Dismiss works
Create Audit Event works
Audit table updates
Create Executive Snapshot works
Executive Snapshots table updates

Pass criteria:

All operations dashboard actions complete without API errors
## 17. Export and Reporting Tests

Validate:

Reports & Exports section loads
CSV export buttons work
Combined CSV export works

Pass criteria:

CSV files download successfully
Exported data matches visible cockpit data
## 18. Final Acceptance Criteria

MVP 17 is accepted when:

Backend import test passes
Frontend build passes
Backend starts cleanly
Frontend starts cleanly
Health endpoint works
Login/session flow works
Dashboard loads
All major tables load
Operations dashboard works
Executive snapshot works
Notifications work
File upload works
Reports/exports work
README is current
Runbook is current
Regression test plan is current
MVP completion summary is current
Code is committed and pushed to GitHub
# ASM Engagement Cockpit Production Runbook

## 1. Purpose

This runbook explains how to operate, validate, troubleshoot, and hand over ASM Engagement Cockpit.

The application is currently designed for local or controlled internal deployment. Before true production use, the team should review authentication, authorization, secret handling, backup policy, logging policy, and data retention.

## 2. Application Components

| Component | Description |
|---|---|
| Backend | FastAPI service running on port 8020 |
| Frontend | React/Vite application running on port 3020 |
| Database | PostgreSQL container exposed on local port 5434 |
| Upload Storage | Local filesystem directory under data/uploads |
| LLM Integration | OpenAI-enabled flows for recommendations, reviews, and timesheet summaries |

## 3. Default Local URLs

| Service | URL |
|---|---|
| Frontend | http://localhost:3020 |
| Backend API | http://localhost:8020/api |
| Backend Docs | http://localhost:8020/docs |
| Health Check | http://localhost:8020/api/health |
| Runtime Diagnostics | http://localhost:8020/api/diagnostics/runtime |

## 4. Start Procedure

### 4.1 Start PostgreSQL

cd /home/induser1/giri/AIProjects/asm_engagement_cockpit

docker compose up -d

### 4.2 Start Backend
cd /home/induser1/giri/AIProjects/asm_engagement_cockpit

bash ./start_backend.sh

Expected behavior:

Backend starts on http://0.0.0.0:8020
Health endpoint responds successfully
Database tables are created automatically at startup

### 4.3 Start Frontend
cd /home/induser1/giri/AIProjects/asm_engagement_cockpit

bash ./start_frontend.sh

Expected behavior:

Frontend starts on http://localhost:3020
Application dashboard loads
Login/session panel appears
Runtime Config section appears
Operations dashboard appears

## 5. Stop Procedure

Stop frontend and backend terminals with:

Ctrl + C

Stop PostgreSQL container:

cd /home/induser1/giri/AIProjects/asm_engagement_cockpit

docker compose down

## 6. Environment Configuration
### 6.1 Backend Environment

Backend file:

backend/.env

Template:

backend/.env.example

Important variables:

Variable	Purpose
APP_NAME	Application display name
APP_ENV	local/dev/prod style marker
DATABASE_URL	SQLAlchemy PostgreSQL connection string
OPENAI_API_KEY	OpenAI API key for LLM features
OPENAI_TRACING	Enables tracing for supported LLM flows
OPENAI_MODEL	Model name used by LLM features
API_AUTH_ENABLED	Enables backend API protection
API_AUTH_KEY	Static API key for service/API access
APP_LOGIN_ENABLED	Enables local login endpoint
APP_LOGIN_USERNAME	Local login username
APP_LOGIN_PASSWORD	Local login password
APP_LOGIN_DISPLAY_NAME	Display name shown after login
APP_SESSION_SECRET_KEY	Secret used to sign session tokens
APP_SESSION_DURATION_MINUTES	Session token duration
LOG_REQUESTS	Enables request logging middleware

## 6.2 Frontend Environment

Frontend file:

frontend/.env

Template:

frontend/.env.example

Important variables:

Variable	Purpose
VITE_API_BASE_URL	Backend API base URL
VITE_API_AUTH_ENABLED	Enables sending X-API-Key
VITE_API_AUTH_KEY	API key value when API-key mode is used
VITE_APP_LOGIN_REQUIRED	Requires login before loading cockpit

## 7. Recommended Local Modes
### 7.1 Development Mode

Use this while building and debugging:

Backend:

API_AUTH_ENABLED=false

Frontend:

VITE_API_AUTH_ENABLED=false
VITE_APP_LOGIN_REQUIRED=false

### 7.2 Protected Validation Mode

Use this before demo or handover:

Backend:

API_AUTH_ENABLED=true

Frontend:

VITE_API_AUTH_ENABLED=false
VITE_APP_LOGIN_REQUIRED=true

Expected behavior:

Frontend opens login-only screen
User logs in
Frontend stores session token in localStorage
Protected write APIs succeed using session token
Logout clears local session

## 8. Health Checks
### 8.1 Backend Import Check
cd /home/induser1/giri/AIProjects/asm_engagement_cockpit/backend

uv run python -c "import app.main; print('backend import OK')"

Expected:

backend import OK

### 8.2 API Health Check
curl http://localhost:8020/api/health

Expected:

{
  "status": "ok",
  "app_name": "ASM Engagement Cockpit",
  "app_env": "local"
}
### 8.3 Runtime Diagnostics
curl http://localhost:8020/api/diagnostics/runtime

If authentication is enabled, use the UI after login or send a bearer token.

## 9. Frontend Build Check
cd /home/induser1/giri/AIProjects/asm_engagement_cockpit/frontend

npm run build

Expected:

Build completes successfully

## 10. Common Troubleshooting
### 10.1 Backend cannot connect to database

Check PostgreSQL container:

docker ps

Restart database:

docker compose up -d

Check DATABASE_URL in:

backend/.env
### 10.2 Frontend cannot reach backend

Check backend is running:

curl http://localhost:8020/api/health

Check frontend env:

frontend/.env

Expected:

VITE_API_BASE_URL=http://localhost:8020/api

Restart frontend after changing .env.

### 10.3 Login fails

Check backend .env:

APP_LOGIN_USERNAME
APP_LOGIN_PASSWORD
APP_SESSION_SECRET_KEY
APP_LOGIN_ENABLED

Restart backend after changing backend .env.

### 10.4 Protected APIs return 401

Confirm:

API_AUTH_ENABLED=true

Then either:

Log in from UI so session token is sent automatically, or
Send Authorization: Bearer <token> in curl.
### 10.5 OpenAI features fail

Check:

OPENAI_API_KEY
OPENAI_MODEL
OPENAI_TRACING

Restart backend after changing backend .env.

### 10.6 File upload fails

Check upload folder exists:

data/uploads/

Check backend terminal logs for permission or path errors.

## 11. Backup Guidance

For local development, back up:

PostgreSQL data volume
backend/.env
frontend/.env
data/uploads/

Before serious use, define:

Database backup frequency
Upload file backup location
Retention period
Restore procedure
Secret rotation procedure
## 12. Production Hardening Recommendations

Before real production deployment, implement or review:

Real enterprise authentication
Database-managed users and hashed passwords
Role-based backend authorization enforcement
HTTPS termination
Secret manager usage
Structured logging
Database migrations
File storage backup strategy
Error monitoring
Deployment pipeline
Automated regression tests
Data retention and privacy policy
## 13. Release Checklist

Before tagging a release:

Backend import check passes
Frontend build passes
Health check passes
Runtime diagnostics works
Login works
Protected mode works
Seed data loads if required
Core dashboard loads
Operations dashboard loads
Executive snapshot works
Notifications work
Timesheet summary works
LLM features work if OpenAI key is configured
README is current
Runbook is current
Regression test plan is current
GitHub push completed
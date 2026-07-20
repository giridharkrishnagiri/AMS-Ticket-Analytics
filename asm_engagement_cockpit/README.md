# ASM Engagement Cockpit

ASM Engagement Cockpit is a consulting execution tracker for Application Support and Maintenance engagements.

It helps track workstreams, deliverables, tasks, sub-tasks, reminders, stakeholder follow-ups, findings, analysis outputs, evidence, file uploads, LLM recommendations, review workflows, timesheets, governance activity, notifications, and executive reporting.

## Project Purpose

The goal of this application is to support ASM consulting and delivery governance by providing one cockpit for:

- Engagement execution tracking
- Workstream and deliverable ownership
- Task and sub-task management
- Date tracking and revised-date history
- Persistent reminders
- Data gathering and stakeholder Q&A
- Findings and analysis capture
- Dictation and text refinement
- File and evidence management
- LLM recommendations and deliverable reviews
- Timesheet tracking and accomplishment summaries
- Review workflow and approval lifecycle
- Recommendation lifecycle management
- Role-based views and filters
- Runtime diagnostics
- Login/session foundation
- Operations, governance, notifications, and executive summaries

## Technology Stack

### Backend

- Python 3.12
- FastAPI
- SQLAlchemy
- PostgreSQL
- uv
- OpenAI Agents SDK for selected LLM flows
- Local filesystem upload storage

### Frontend

- React
- TypeScript
- Vite
- TanStack Query
- Browser localStorage for lightweight session storage

### Database

- PostgreSQL running through Docker Compose

## Default Local Ports

| Component | Port |
|---|---:|
| Backend | 8020 |
| Frontend | 3020 |
| PostgreSQL | 5434 |

## Repository Structure

```text
asm_engagement_cockpit/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models/
│   │   ├── schemas/
│   │   └── routers and MVP modules
│   ├── .env
│   ├── .env.example
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   ├── .env
│   ├── .env.example
│   └── package.json
├── docs/
│   ├── PRODUCTION_RUNBOOK.md
│   ├── REGRESSION_TEST_PLAN.md
│   └── MVP_COMPLETION_SUMMARY.md
├── data/
│   └── uploads/
├── docker-compose.yml
├── start_backend.sh
├── start_frontend.sh
└── README.md
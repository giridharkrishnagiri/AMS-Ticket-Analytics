# AMS GenAI Analytics Workbench

This is the separate experimental GenAI workbench for the AMS Applications & Volumetrics Analytics backend. It keeps GenAI administration and testing outside the existing dashboard UI.

## Run

```powershell
cd "C:\AIProjects\AI Ticket Analytics for AMS Consulting Project"
.\run_backend.bat
.\run_genai_frontend.bat
```

The workbench runs at `http://127.0.0.1:3025`.

## Backend

The app calls the existing FastAPI backend. Configure the API base with:

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
```

The client accepts either the backend root URL or a URL ending in `/api`.

For corporate-managed laptops, the backend uses the Windows/system certificate store for LiteLLM/OpenAI connectivity. If your environment still requires a specific certificate bundle, configure the backend with:

```text
SSL_CERT_FILE=C:\path\to\corporate-ca-bundle.pem
```

## MVP Scope

- AI configuration admin
- Prompt template viewing and overrides
- Safety and data-access settings
- LiteLLM connection test
- Recent usage logs
- Phase 1C chat UI with persisted chat sessions and messages
- Chat responses through the configured LiteLLM model

Phase 1C chat does not query live Applications, Tickets, SLA, OLA, Problem, or Change data. It can
answer general questions about the workbench and future capabilities, and it will state when
data-aware Q&A is not available yet.

Future phases will add governed analytics tools, data-aware Q&A, AI chart generation, and
recommendations.

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

If your network uses corporate SSL inspection, configure the backend with a trusted CA bundle before testing LiteLLM/OpenAI connectivity:

```text
SSL_CERT_FILE=C:\path\to\corporate-ca-bundle.pem
```

## MVP Scope

- AI configuration admin
- Prompt template viewing and overrides
- Safety and data-access settings
- LiteLLM connection test
- Recent usage logs

Future phases will add governed chat, governed analytics tools, AI chart generation, and recommendations.

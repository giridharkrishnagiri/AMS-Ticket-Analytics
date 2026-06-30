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
- Phase 1D Tools Lab for deterministic governed analytics tools
- Recent governed tool-run history
- Phase 1E data-aware chat through LangGraph and governed analytics tools
- Phase 2A AI Charts workspace for governed Plotly charts
- Chat chart requests that generate persisted chart specs from governed tool results
- Phase 2B safe AI Charts editing controls, chart duplication, reset, archive, and limited
  compatible 3D scatter support

Phase 1E chat can answer supported Applications, Tickets, and SLA/OLA questions through approved
governed analytics tools. The LLM does not write SQL, does not access the database directly, and
does not receive raw ticket rows or payload fields.

Phase 1D Tools Lab executes approved backend aggregate tools directly. It does not use an LLM,
does not generate SQL, and remains available for direct tool testing.

Phase 2A chart requests use governed analytics tool results only. The backend creates sanitized
Plotly-compatible JSON specs, stores generated charts, and the AI Charts page renders the chart and
its verification data table. No SQL generation, raw ticket charting, or raw payload charting is
allowed. Full 3-D charting was deferred beyond the initial Phase 2A chart foundation.

Phase 2B adds safe chart presentation editing in AI Charts. Users can edit titles, subtitles,
compatible chart types, orientation, top-N row limits, labels, legends, sorting, and axis titles.
Charts can be saved, duplicated, reset, and archived. Limited 3D scatter rendering is available
only when the governed table has three real numeric measures. Chart editing does not allow SQL,
raw data access, arbitrary JavaScript, or raw payload exposure.

The existing main dashboard UI remains unchanged.

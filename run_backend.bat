@echo off
setlocal

cd /d "%~dp0backend"

set UV_CACHE_DIR=%CD%\.uv-cache

echo Installing or updating backend dependencies with uv...
uv sync --dev
if errorlevel 1 (
    echo Backend dependency setup failed.
    exit /b 1
)

if /I "%AMS_BACKEND_RELOAD%"=="0" (
    echo Starting AMS Ticket Intelligence backend without reload at http://127.0.0.1:8000
    uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
) else (
    echo Starting AMS Ticket Intelligence backend with reload at http://127.0.0.1:8000
    uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
)

endlocal

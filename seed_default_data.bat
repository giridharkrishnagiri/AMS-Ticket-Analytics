@echo off
setlocal

cd /d "%~dp0backend"

set UV_CACHE_DIR=%CD%\.uv-cache

echo Seeding default AMS client and project...
uv run python -m scripts.seed_default
if errorlevel 1 (
    echo Seed failed. Confirm PostgreSQL is running and backend\.env has the correct DATABASE_URL.
    exit /b 1
)

echo Seed completed.

endlocal
@echo off
setlocal

cd /d "%~dp0backend"

if "%AMS_BACKEND_PORT%"=="" set "AMS_BACKEND_PORT=8001"
if "%AMS_BACKEND_RELOAD%"=="" set "AMS_BACKEND_RELOAD=0"

set UV_CACHE_DIR=%CD%\.uv-cache

echo Installing or updating backend dependencies with uv...
uv sync --dev
if errorlevel 1 (
    echo Backend dependency setup failed.
    exit /b 1
)

echo Checking backend port %AMS_BACKEND_PORT%...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$port=[int]'%AMS_BACKEND_PORT%'; $listener=Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $port -State Listen -ErrorAction SilentlyContinue; if ($listener) { Write-Host ('Port {0} is already in use by process id(s): {1}' -f $port, (($listener | Select-Object -ExpandProperty OwningProcess -Unique) -join ', ')); exit 1 }"
if errorlevel 1 (
    echo Backend port %AMS_BACKEND_PORT% is already in use. Stop the existing backend or set AMS_BACKEND_PORT to another port.
    exit /b 1
)

if /I "%AMS_BACKEND_RELOAD%"=="1" (
    echo Starting AMS Ticket Intelligence backend with reload at http://127.0.0.1:%AMS_BACKEND_PORT%
    uv run uvicorn app.main:app --host 127.0.0.1 --port %AMS_BACKEND_PORT% --reload
) else (
    echo Starting AMS Ticket Intelligence backend without reload at http://127.0.0.1:%AMS_BACKEND_PORT%
    uv run uvicorn app.main:app --host 127.0.0.1 --port %AMS_BACKEND_PORT%
)

endlocal

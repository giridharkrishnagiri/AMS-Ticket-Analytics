@echo off
setlocal

if /i "%~1"=="analytics" goto analytics_backend
if /i "%~1"=="cockpit" goto cockpit_backend

set "COCKPIT_ROOT=C:\AIProjects\asm_engagement_cockpit"

if not exist "%~dp0backend\app\main.py" (
    echo AMS Ticket Intelligence backend was not found at "%~dp0backend".
    exit /b 1
)

if not exist "%COCKPIT_ROOT%\backend\app\main.py" (
    echo ASM Engagement Cockpit backend was not found at "%COCKPIT_ROOT%\backend".
    exit /b 1
)

echo Starting backend services in separate windows...
echo AMS Ticket Intelligence backend: http://127.0.0.1:8001
echo ASM Engagement Cockpit backend: http://127.0.0.1:8020

start "AMS Ticket Intelligence Backend" "%ComSpec%" /k call "%~f0" analytics
start "ASM Engagement Cockpit Backend" "%ComSpec%" /k call "%~f0" cockpit

endlocal
exit /b 0

:analytics_backend
cd /d "%~dp0backend"

if "%AMS_BACKEND_PORT%"=="" set "AMS_BACKEND_PORT=8001"
if "%AMS_BACKEND_RELOAD%"=="" set "AMS_BACKEND_RELOAD=1"
if "%AMS_BACKEND_SHUTDOWN_TIMEOUT%"=="" set "AMS_BACKEND_SHUTDOWN_TIMEOUT=10"
if "%AMS_PROCESSING_PIPELINE_VERSION%"=="" set "AMS_PROCESSING_PIPELINE_VERSION=v2"

set "UV_CACHE_DIR=%CD%\.uv-cache"

echo Using processing pipeline version: %AMS_PROCESSING_PIPELINE_VERSION%
echo Installing or updating backend dependencies with uv...
uv sync --dev
if errorlevel 1 (
    echo Backend dependency setup failed.
    exit /b 1
)

echo Checking backend port %AMS_BACKEND_PORT% and stale backend wrappers...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$port=[int]'%AMS_BACKEND_PORT%'; $listener=$null; for ($attempt=1; $attempt -le 10; $attempt++) { $listener=Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $port -State Listen -ErrorAction SilentlyContinue; if (-not $listener) { break }; Write-Host ('Port {0} is still in use; retrying {1}/10...' -f $port, $attempt); Start-Sleep -Seconds 1 }; if ($listener) { $pids=$listener | Select-Object -ExpandProperty OwningProcess -Unique; Write-Host ('Port {0} is already in use by process id(s): {1}' -f $port, ($pids -join ', ')); foreach ($id in $pids) { $proc=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $id) -ErrorAction SilentlyContinue; if ($proc) { Write-Host ('PID {0}: {1}' -f $id, $proc.CommandLine) } else { Write-Host ('PID {0}: process details are not available; it may be exiting or orphaned.' -f $id) } }; exit 1 }; $portPattern='--port\s+' + [regex]::Escape([string]$port) + '(\s|$)'; $stale=Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -and $_.CommandLine -match 'app\.main:app' -and $_.CommandLine -match $portPattern }; if ($stale) { $stalePids=$stale | Select-Object -ExpandProperty ProcessId -Unique; Write-Host ('Stopping stale backend wrapper process id(s): {0}' -f ($stalePids -join ', ')); foreach ($proc in $stale) { Write-Host ('PID {0}: {1}' -f $proc.ProcessId, $proc.CommandLine) }; Stop-Process -Id $stalePids -Force -ErrorAction SilentlyContinue; foreach ($id in $stalePids) { Wait-Process -Id $id -Timeout 5 -ErrorAction SilentlyContinue } }; exit 0"
if errorlevel 1 (
    echo Backend port %AMS_BACKEND_PORT% is already in use. Stop the existing backend or set AMS_BACKEND_PORT to another port.
    exit /b 1
)

if exist ".venv\Scripts\python.exe" (
    set "BACKEND_PYTHON=.venv\Scripts\python.exe"
) else (
    set "BACKEND_PYTHON=python"
)

if /I "%AMS_BACKEND_RELOAD%"=="1" (
    echo Starting AMS Ticket Intelligence backend with reload at http://127.0.0.1:%AMS_BACKEND_PORT%
    "%BACKEND_PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port %AMS_BACKEND_PORT% --reload --timeout-graceful-shutdown %AMS_BACKEND_SHUTDOWN_TIMEOUT%
) else (
    echo Starting AMS Ticket Intelligence backend without reload at http://127.0.0.1:%AMS_BACKEND_PORT%
    "%BACKEND_PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port %AMS_BACKEND_PORT% --timeout-graceful-shutdown %AMS_BACKEND_SHUTDOWN_TIMEOUT%
)

exit /b %ERRORLEVEL%

:cockpit_backend
set "COCKPIT_ROOT=C:\AIProjects\asm_engagement_cockpit"
set "COCKPIT_BACKEND=%COCKPIT_ROOT%\backend"
set "COCKPIT_ENV=%COCKPIT_BACKEND%\.env"

cd /d "%COCKPIT_BACKEND%"

if not exist "%COCKPIT_ENV%" (
    echo ASM Engagement Cockpit backend .env was not found at "%COCKPIT_ENV%".
    echo Configure DATABASE_URL for the existing AMS database and asm_engagement_cockpit schema before starting.
    exit /b 1
)

findstr /b /i "DATABASE_URL=postgresql+psycopg2://ams_user:ams_app_password@localhost:5432/ams_ticket_intelligence" "%COCKPIT_ENV%" >nul 2>&1
if errorlevel 1 (
    echo ASM Engagement Cockpit DATABASE_URL is not pointing to the shared AMS database on localhost:5432.
    echo Update "%COCKPIT_ENV%" before starting the cockpit backend.
    exit /b 1
)

findstr /i "search_path%%3Dasm_engagement_cockpit" "%COCKPIT_ENV%" >nul 2>&1
if errorlevel 1 (
    echo ASM Engagement Cockpit DATABASE_URL must include search_path%%3Dasm_engagement_cockpit.
    echo Update "%COCKPIT_ENV%" before starting the cockpit backend.
    exit /b 1
)

set "UV_CACHE_DIR=%CD%\.uv-cache"

echo Installing or updating ASM Engagement Cockpit backend dependencies with uv...
uv sync --dev
if errorlevel 1 (
    echo ASM Engagement Cockpit backend dependency setup failed.
    exit /b 1
)

echo Starting ASM Engagement Cockpit backend at http://127.0.0.1:8020
uv run uvicorn app.main:app --host 127.0.0.1 --port 8020 --reload --reload-dir "%COCKPIT_BACKEND%"

exit /b %ERRORLEVEL%

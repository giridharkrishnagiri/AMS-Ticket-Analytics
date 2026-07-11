@echo off
setlocal

cd /d "%~dp0backend"

if "%AMS_BACKEND_PORT%"=="" set "AMS_BACKEND_PORT=8001"
if "%AMS_BACKEND_RELOAD%"=="" set "AMS_BACKEND_RELOAD=0"
if "%AMS_BACKEND_SHUTDOWN_TIMEOUT%"=="" set "AMS_BACKEND_SHUTDOWN_TIMEOUT=10"
if "%AMS_PROCESSING_PIPELINE_VERSION%"=="" set "AMS_PROCESSING_PIPELINE_VERSION=v2"

set UV_CACHE_DIR=%CD%\.uv-cache

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

endlocal

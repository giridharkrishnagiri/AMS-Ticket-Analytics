@echo off
setlocal

if /i "%~1"=="analytics" goto analytics_frontend
if /i "%~1"=="cockpit" goto cockpit_frontend

set "COCKPIT_ROOT=C:\AIProjects\asm_engagement_cockpit"

if not exist "%~dp0frontend\package.json" (
    echo AMS Ticket Intelligence frontend was not found at "%~dp0frontend".
    exit /b 1
)

if not exist "%COCKPIT_ROOT%\frontend\package.json" (
    echo ASM Engagement Cockpit frontend was not found at "%COCKPIT_ROOT%\frontend".
    exit /b 1
)

echo Starting frontend services in separate windows...
echo AMS Ticket Intelligence frontend: http://127.0.0.1:5173
echo ASM Engagement Cockpit frontend: http://127.0.0.1:3020

start "AMS Ticket Intelligence Frontend" "%ComSpec%" /k call "%~f0" analytics
start "ASM Engagement Cockpit Frontend" "%ComSpec%" /k call "%~f0" cockpit

endlocal
exit /b 0

:analytics_frontend
cd /d "%~dp0frontend"

if "%AMS_BACKEND_PORT%"=="" set "AMS_BACKEND_PORT=8001"
if "%VITE_API_BASE_URL%"=="" set "VITE_API_BASE_URL=http://127.0.0.1:%AMS_BACKEND_PORT%/api"
if "%CHOKIDAR_USEPOLLING%"=="" set "CHOKIDAR_USEPOLLING=true"
if "%CHOKIDAR_INTERVAL%"=="" set "CHOKIDAR_INTERVAL=500"

if not exist node_modules (
    echo Installing frontend dependencies with npm...
    call npm.cmd install
    if errorlevel 1 (
        echo Frontend dependency setup failed.
        exit /b 1
    )
)

echo Frontend API base URL: %VITE_API_BASE_URL%
echo Frontend hot reload: enabled via Vite dev server
echo Frontend file watcher polling: %CHOKIDAR_USEPOLLING% ^(interval %CHOKIDAR_INTERVAL%ms^)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$base='%VITE_API_BASE_URL%'.TrimEnd('/'); $pingUrl=$base + '/health/ping'; $healthUrl=$base + '/health'; $lastError=$null; for ($attempt=1; $attempt -le 15; $attempt++) { try { $response=Invoke-WebRequest -Uri $pingUrl -UseBasicParsing -TimeoutSec 2; Write-Host ('Backend API reachable: HTTP {0} ({1})' -f $response.StatusCode, $pingUrl); exit 0 } catch { $lastError=$_.Exception.Message; if ($attempt -lt 15) { Write-Host ('Waiting for backend API at {0} ({1}/15)...' -f $pingUrl, $attempt); Start-Sleep -Seconds 1 } } }; try { $response=Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 12; Write-Host ('Backend full health reachable: HTTP {0} ({1})' -f $response.StatusCode, $healthUrl); exit 0 } catch { Write-Host ('Warning: backend API is not reachable at {0}. Start run_backend.bat first, or verify AMS_BACKEND_PORT. Last ping error: {1}; full health error: {2}' -f $pingUrl, $lastError, $_.Exception.Message); exit 0 }"

echo Starting AMS Ticket Intelligence frontend at http://127.0.0.1:5173
call npm.cmd run dev -- --host 127.0.0.1 --port 5173

exit /b %ERRORLEVEL%

:cockpit_frontend
set "COCKPIT_FRONTEND=C:\AIProjects\asm_engagement_cockpit\frontend"

cd /d "%COCKPIT_FRONTEND%"

if not exist node_modules (
    echo Installing ASM Engagement Cockpit frontend dependencies with npm...
    call npm.cmd install
    if errorlevel 1 (
        echo ASM Engagement Cockpit frontend dependency setup failed.
        exit /b 1
    )
)

echo Starting ASM Engagement Cockpit frontend at http://127.0.0.1:3020
call npm.cmd run dev -- --host 127.0.0.1 --port 3020

exit /b %ERRORLEVEL%

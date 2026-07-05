@echo off
setlocal

cd /d "%~dp0frontend"

if "%AMS_BACKEND_PORT%"=="" set "AMS_BACKEND_PORT=8001"
if "%VITE_API_BASE_URL%"=="" set "VITE_API_BASE_URL=http://127.0.0.1:%AMS_BACKEND_PORT%/api"

if not exist node_modules (
    echo Installing frontend dependencies with npm...
    npm.cmd install
    if errorlevel 1 (
        echo Frontend dependency setup failed.
        exit /b 1
    )
)

echo Frontend API base URL: %VITE_API_BASE_URL%
powershell -NoProfile -ExecutionPolicy Bypass -Command "$base='%VITE_API_BASE_URL%'.TrimEnd('/'); $pingUrl=$base + '/health/ping'; $healthUrl=$base + '/health'; $lastError=$null; for ($attempt=1; $attempt -le 15; $attempt++) { try { $response=Invoke-WebRequest -Uri $pingUrl -UseBasicParsing -TimeoutSec 2; Write-Host ('Backend API reachable: HTTP {0} ({1})' -f $response.StatusCode, $pingUrl); exit 0 } catch { $lastError=$_.Exception.Message; if ($attempt -lt 15) { Write-Host ('Waiting for backend API at {0} ({1}/15)...' -f $pingUrl, $attempt); Start-Sleep -Seconds 1 } } }; try { $response=Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 12; Write-Host ('Backend full health reachable: HTTP {0} ({1})' -f $response.StatusCode, $healthUrl); exit 0 } catch { Write-Host ('Warning: backend API is not reachable at {0}. Start run_backend.bat first, or verify AMS_BACKEND_PORT. Last ping error: {1}; full health error: {2}' -f $pingUrl, $lastError, $_.Exception.Message); exit 0 }"

echo Starting AMS Ticket Intelligence frontend at http://127.0.0.1:5173
npm.cmd run dev -- --host 127.0.0.1 --port 5173

endlocal

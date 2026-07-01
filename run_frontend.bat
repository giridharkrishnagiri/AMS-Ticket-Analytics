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
powershell -NoProfile -ExecutionPolicy Bypass -Command "$url='%VITE_API_BASE_URL%/health'; try { $response=Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5; Write-Host ('Backend health reachable: HTTP {0}' -f $response.StatusCode) } catch { Write-Host ('Warning: backend health is not reachable at {0}. Start run_backend.bat first, or verify AMS_BACKEND_PORT. {1}' -f $url, $_.Exception.Message) }"

echo Starting AMS Ticket Intelligence frontend at http://127.0.0.1:5173
npm.cmd run dev -- --host 127.0.0.1 --port 5173

endlocal

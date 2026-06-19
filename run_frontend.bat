@echo off
setlocal

cd /d "%~dp0frontend"

if not exist node_modules (
    echo Installing frontend dependencies with npm...
    npm.cmd install
    if errorlevel 1 (
        echo Frontend dependency setup failed.
        exit /b 1
    )
)

echo Starting AMS Ticket Intelligence frontend at http://127.0.0.1:5173
npm.cmd run dev -- --host 127.0.0.1 --port 5173

endlocal

@echo off
setlocal

if "%AMS_BACKEND_PORT%"=="" set "AMS_BACKEND_PORT=8001"
if "%VITE_API_BASE_URL%"=="" set "VITE_API_BASE_URL=http://127.0.0.1:%AMS_BACKEND_PORT%"

cd /d "%~dp0genai_frontend"

echo GenAI frontend API base URL: %VITE_API_BASE_URL%
npm.cmd run dev
endlocal

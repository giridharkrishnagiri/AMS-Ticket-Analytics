#!/usr/bin/env bash
set -e

PROJECT_PATH="/home/induser1/giri/AIProjects/asm_engagement_cockpit"
BACKEND_PORT="8020"
BACKEND_PATH="$PROJECT_PATH/backend"

echo "============================================"
echo "ASM Engagement Cockpit - Start Backend"
echo "============================================"

cd "$PROJECT_PATH"

echo ""
echo "Starting PostgreSQL Docker container if needed..."
docker compose up -d

echo ""
echo "Checking backend files..."
test -f "$BACKEND_PATH/app/main.py"
test -f "$BACKEND_PATH/app/__init__.py"
test -f "$BACKEND_PATH/app/models/__init__.py"
test -f "$BACKEND_PATH/app/schemas/__init__.py"

echo ""
echo "Testing Python import for app.main..."
cd "$BACKEND_PATH"
uv run python -c "import app.main; print('app.main import OK')"

echo ""
echo "Starting backend on port $BACKEND_PORT with auto-reload enabled..."
echo "Health URL: http://localhost:$BACKEND_PORT/api/health"
echo "API Docs:   http://localhost:$BACKEND_PORT/docs"
echo ""
echo "Watching for backend changes under:"
echo "$BACKEND_PATH"
echo ""

uv run uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "$BACKEND_PORT" \
  --reload \
  --reload-dir "$BACKEND_PATH"
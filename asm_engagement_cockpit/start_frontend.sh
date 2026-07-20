#!/usr/bin/env bash
set -e

PROJECT_PATH="/home/induser1/giri/AIProjects/asm_engagement_cockpit"
FRONTEND_PORT="3020"

echo "============================================"
echo "ASM Engagement Cockpit - Start Frontend"
echo "============================================"

cd "$PROJECT_PATH/frontend"

if [ ! -d "node_modules" ]; then
  echo ""
  echo "node_modules not found. Installing frontend dependencies..."
  npm install
fi

echo ""
echo "Starting frontend on port $FRONTEND_PORT..."
echo "Frontend URL: http://localhost:$FRONTEND_PORT"
npm run dev
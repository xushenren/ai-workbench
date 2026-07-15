#!/bin/bash
echo "Starting backend..."
cd backend/secureguard-deploy
uvicorn backend.app:app --port 9000 --host 0.0.0.0 &
BACKEND_PID=$!
sleep 2
echo "Starting frontend..."
cd ../../frontend_src
npm run dev -- --host 0.0.0.0 &
wait $BACKEND_PID

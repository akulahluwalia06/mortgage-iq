#!/bin/bash
# Start Canadian Mortgage Predictor (backend + frontend)

echo "🍁 Starting Canadian Mortgage Predictor..."

# Backend
cd "$(dirname "$0")/backend"
/Users/akulahluwalia/anaconda3/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo "✅ Backend running at http://localhost:8000 (PID $BACKEND_PID)"

# Frontend
cd "$(dirname "$0")/frontend"
npm start &
FRONTEND_PID=$!
echo "✅ Frontend starting at http://localhost:3000 (PID $FRONTEND_PID)"

echo ""
echo "Press Ctrl+C to stop both servers"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Stopped.'" INT TERM
wait

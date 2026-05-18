#!/bin/bash
set -e

echo "Starting Incident Brain..."

cd "$(dirname "$0")"

if [ ! -f backend/.env ]; then
    echo "Creating .env from example..."
    cp backend/.env.example backend/.env
    echo "Please edit backend/.env with your API keys before continuing."
    exit 1
fi

echo "Starting backend..."
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo "Starting frontend..."
cd ../frontend
npm run dev &
FRONTEND_PID=$!

echo "Incident Brain is running!"
echo "  Frontend: http://localhost:3000"
echo "  Backend:  http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait

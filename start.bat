@echo off
echo ============================================================
echo Starting Agent Guardian (Backend + Frontend)
echo Backend API : http://127.0.0.1:8000
echo Frontend UI : http://localhost:3000
echo ============================================================
start "Agent Guardian Backend" cmd /k "uv run uvicorn api.main:app --host 127.0.0.1 --port 8000"
start "Agent Guardian Frontend" cmd /k "npm --prefix frontend run start"

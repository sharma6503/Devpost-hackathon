@echo off
echo ============================================================
echo Starting Agent Guardian in Development Mode
echo Backend API : http://127.0.0.1:8000
echo Frontend UI : http://localhost:3000
echo ============================================================
start "Agent Guardian Backend" cmd /k "uv run uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir agent_guardian --reload-dir api"
start "Agent Guardian Frontend" cmd /k "npm --prefix frontend run dev"

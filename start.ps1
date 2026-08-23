Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Starting Agent Guardian (Backend + Frontend)" -ForegroundColor Green
Write-Host "Backend API : http://127.0.0.1:8000" -ForegroundColor Yellow
Write-Host "Frontend UI : http://localhost:3000" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan

Start-Process powershell -ArgumentList "-NoExit", "-Command", "uv run uvicorn api.main:app --host 127.0.0.1 --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "npm --prefix frontend run start"

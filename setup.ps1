# One-time setup for Windows. Right-click → "Run with PowerShell", or in a terminal:  .\setup.ps1
# If you get "running scripts is disabled", run once:  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
Write-Host "Creating virtual environment (.venv)..." -ForegroundColor Cyan
python -m venv .venv
Write-Host "Installing packages from requirements.txt..." -ForegroundColor Cyan
.\.venv\Scripts\python.exe -m pip install --upgrade pip | Out-Null
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env; Write-Host "Created .env from .env.example" }
Write-Host "Seeding demo data..." -ForegroundColor Cyan
.\.venv\Scripts\python.exe seed.py
Write-Host ""
Write-Host "All set! Start the server with:" -ForegroundColor Green
Write-Host "   .\.venv\Scripts\Activate.ps1"
Write-Host "   uvicorn app.main:app --reload --port 8000"
Write-Host "then open http://localhost:8000/docs" -ForegroundColor Green

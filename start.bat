@echo off
REM ============================================================
REM  start.bat  -  double-click this. It does everything:
REM    first time: creates .venv, installs packages, seeds demo data
REM    every time: starts the server and opens Swagger in your browser
REM  Close this window (or Ctrl+C) to stop the server.
REM ============================================================
cd /d "%~dp0"
title TechNexus Backend

where python >nul 2>&1
if errorlevel 1 (
  echo.
  echo  Python is not installed or not on PATH.
  echo  Install it from https://www.python.org/downloads/  and tick "Add python.exe to PATH".
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo  [1/3] First run: creating virtual environment...
  python -m venv .venv
  echo  [2/3] Installing packages ^(1-3 minutes, needs internet^)...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo  Package install failed. Check your internet connection and run start.bat again.
    pause
    exit /b 1
  )
)

if not exist ".env" copy .env.example .env >nul

if not exist "telehealth.db" (
  echo  [3/3] Creating demo data...
  ".venv\Scripts\python.exe" seed.py
)

echo.
echo  ============================================================
echo   Server starting at  http://localhost:8000
echo   Swagger docs:       http://localhost:8000/docs
echo   Login: admin@technexus.io  /  1234   (or phone 9000000010 for a health worker)
echo   Close this window to stop the server.
echo  ============================================================
echo.
start "" http://localhost:8000/docs
".venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
pause

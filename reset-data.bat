@echo off
REM Wipes the database and recreates fresh demo data. Run this before every demo.
cd /d "%~dp0"
".venv\Scripts\python.exe" seed.py
pause

@echo off
REM Fresh demo data + all 45 end-to-end checks. Should end with "45 passed, 0 failed".
cd /d "%~dp0"
".venv\Scripts\python.exe" seed.py
".venv\Scripts\python.exe" smoke_test.py
pause

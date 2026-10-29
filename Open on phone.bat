@echo off
cd /d "%~dp0"
set PYTHONUNBUFFERED=1
echo Starting the phone page...
start "" "http://127.0.0.1:8765"
".venv\Scripts\python.exe" phone_server.py
pause

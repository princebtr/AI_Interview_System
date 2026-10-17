@echo off
cd /d "%~dp0server"
if not exist .venv\Scripts\python.exe (
  echo server\.venv not found. Create it with:
  echo   cd server ^&^& python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  exit /b 1
)
echo Starting Django backend on http://localhost:8000 ...
.venv\Scripts\python.exe manage.py runserver 8000

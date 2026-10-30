#!/bin/bash
# Starts the Django backend (auth + AI) on port 8000.
cd "$(dirname "$0")/server"
PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "server/.venv not found. Create it with:"
  echo "  cd server && python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi
echo "Starting Django backend on http://localhost:8000 ..."
exec "$PY" manage.py runserver 8000

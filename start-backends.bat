@echo off
echo Starting Interview System Backends...
echo.

echo Starting Express Backend (Port 5000)...
start "Express Backend" cmd /k "cd express && npm run dev"

echo Starting Flask AI Backend (Port 5001)...
start "Flask AI Backend" cmd /k "cd server && python app.py"

echo.
echo Both backends are starting...
echo Express Backend: http://localhost:5000
echo Flask AI Backend: http://localhost:5001
echo.
echo Press any key to exit...
pause

@echo off
echo Starting Covelike UI...

start "Covelike Backend" cmd /k "cd /d D:\Covelike-UI\backend && C:\seedvc-pipeline\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000"

timeout /t 3 /nobreak > nul

start "Covelike Frontend" cmd /k "cd /d D:\Covelike-UI\frontend && npm run dev -- --host"

echo.
echo Backend: http://localhost:8000
echo Frontend: http://localhost:5173
echo.

@echo off
echo Installing Covelike UI...

echo.
echo [1/2] Installing backend dependencies...
cd /d D:\Covelike-UI\backend
C:\seedvc-pipeline\venv\Scripts\pip.exe install -r requirements.txt

echo.
echo [2/2] Installing frontend dependencies...
cd /d D:\Covelike-UI\frontend
call npm install

echo.
echo Installation complete!
echo.
echo To run:
echo   1. Start backend: D:\Covelike-UI\backend\run.bat
echo   2. Start frontend: D:\Covelike-UI\frontend\run.bat
echo.
pause

@echo off
cd /d D:\Covelike-UI\backend
C:\seedvc-pipeline\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause

@echo off
setlocal

echo Starting PM MVP container...
docker compose up --build -d
if errorlevel 1 exit /b 1

echo App should be available at http://localhost:8000

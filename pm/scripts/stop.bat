@echo off
setlocal

echo Stopping PM MVP container...
docker compose down --remove-orphans
if errorlevel 1 exit /b 1

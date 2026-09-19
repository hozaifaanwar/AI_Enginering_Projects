# Scripts Agent Guide

This folder provides start and stop scripts for all target operating systems.

## Scripts

- Windows PowerShell:
- `start.ps1`
- `stop.ps1`
- Windows CMD:
- `start.bat`
- `stop.bat`
- macOS/Linux:
- `start.sh`
- `stop.sh`

All scripts operate from the repository root and call `docker compose` commands.

## Current Behavior

- Start scripts build and launch the app container in detached mode.
- Stop scripts stop and remove containers created by compose.

## Notes

- Part 2 only validates scaffold startup and health endpoints.
- Future phases may expand scripts with extra checks or logs if required.